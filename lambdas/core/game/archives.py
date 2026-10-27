"""Immutable board records and atomic durable completion publication."""
import copy
import os
import threading

from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError


class ArchiveConflict(ValueError):
    pass


def eligible(room):
    game = room.get("gameData", {})
    result = game.get("result")
    return bool(room.get("state") == "completed"
                and game.get("currentPhase") == "completed"
                and game.get("boardId") and game.get("initialHands")
                and result and not game.get("completedTrick")
                and not game.get("currentTrick")
                and (result.get("passedOut") or len(game.get("tricks", [])) == 13
                     or game.get("claimSettlement")))


def embargo_allows(room, board, user_id):
    """Event release applies to every archive path, including old board lists."""
    event_id = board.get("eventId") or room.get("eventId")
    if not event_id:
        return True
    from lambdas.core.game import duplicate
    return duplicate.archive_released(event_id, board["boardNumber"], user_id, room["roomId"])


def record(room):
    game = room["gameData"]
    return {
        "schemaVersion": 1, "roomId": room["roomId"], "boardId": game["boardId"],
        "boardNumber": game["boardNumber"], "dealer": game["dealer"],
        "vulnerability": game["vulnerability"],
        "initialHands": copy.deepcopy(game["initialHands"]),
        "auction": copy.deepcopy(game["bids"]),
        "tricks": copy.deepcopy(game["tricks"]),
        "contract": game.get("contract"),
        "contractMultiplier": game.get("contractMultiplier", 1),
        "declarer": game.get("declarer"), "openingLeader": game.get("openingLeader"),
        "result": copy.deepcopy(game["result"]),
        "agreements": copy.deepcopy(game["agreements"]),
        "completedAt": game["completedAt"],
        "eventId": game.get("eventId"),
        "claimSettlement": copy.deepcopy(game.get("claimSettlement")),
    }


class MemoryArchiveStore:
    def __init__(self):
        self._boards = {}
        self._lock = threading.RLock()

    def put_completed(self, room):
        if not eligible(room):
            return None
        board = record(room)
        key = (board["roomId"], board["boardId"])
        with self._lock:
            existing = self._boards.get(key)
            if existing is not None and existing != board:
                raise ArchiveConflict("Immutable board record already exists")
            self._boards.setdefault(key, copy.deepcopy(board))
        return copy.deepcopy(board)

    def get(self, room_id, board_id):
        with self._lock:
            return copy.deepcopy(self._boards.get((room_id, board_id)))

    def list(self, room_id, *, limit=50, before=None):
        with self._lock:
            boards = [copy.deepcopy(board) for (room, _), board in self._boards.items()
                      if room == room_id and (before is None or board["boardNumber"] < before)]
        boards.sort(key=lambda board: board["boardNumber"], reverse=True)
        return boards[:limit]


class DynamoArchiveStore:
    """Partition by roomId, sort numerically by boardNumber; never expire records."""

    def __init__(self, table):
        self.table = table

    def _write(self, board):
        return {
            "TableName": self.table.name,
            "Item": {"roomId": board["roomId"], "boardNumber": board["boardNumber"],
                     "board": board},
            "ConditionExpression": "attribute_not_exists(roomId) OR #board = :board",
            "ExpressionAttributeNames": {"#board": "board"},
            "ExpressionAttributeValues": {":board": board},
        }

    def put_completed(self, room):
        if not eligible(room):
            return None
        board = record(room)
        write = self._write(board)
        write.pop("TableName")
        try:
            self.table.put_item(**write)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ArchiveConflict("Immutable board record already exists") from exc
            raise
        return board

    def get(self, room_id, board_id):
        # A filtered partition query avoids an eventually consistent boardId GSI.
        kwargs = {
            "KeyConditionExpression": Key("roomId").eq(room_id),
            "FilterExpression": Attr("board.boardId").eq(board_id),
            "ConsistentRead": True,
        }
        while True:
            response = self.table.query(**kwargs)
            if response.get("Items"):
                return response["Items"][0]["board"]
            if not response.get("LastEvaluatedKey"):
                return None
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def list(self, room_id, *, limit=50, before=None):
        key = Key("roomId").eq(room_id)
        if before is not None:
            key &= Key("boardNumber").lt(before)
        kwargs = {"KeyConditionExpression": key, "ConsistentRead": True,
                  "ScanIndexForward": False, "Limit": limit}
        boards = []
        while len(boards) < limit:
            kwargs["Limit"] = limit - len(boards)
            response = self.table.query(**kwargs)
            boards.extend(item["board"] for item in response.get("Items", []))
            if not response.get("LastEvaluatedKey"):
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return boards

    def commit_completed(self, room_table, room, **room_condition):
        """Room scores, archive and duplicate results commit together or not at all."""
        from lambdas.core.game import duplicate
        from lambdas.core.game.runtime import GameRequestError, RoomConflictError

        board = record(room)
        for _ in range(5):
            event = duplicate.completion_event(room, required=True) if room.get("eventId") else None
            writes = [
                {"Put": {"TableName": room_table.name, "Item": room, **room_condition}},
                {"Put": self._write(board)},
            ]
            if event is not None:
                previous = int(event.get("revision", 0))
                event["revision"] = previous + 1
                writes.append({"Put": {
                    "TableName": duplicate.store.table.name, "Item": event,
                    "ConditionExpression": "#revision = :expected",
                    "ExpressionAttributeNames": {"#revision": "revision"},
                    "ExpressionAttributeValues": {":expected": previous},
                }})
            try:
                self.table.meta.client.transact_write_items(TransactItems=writes)
                return
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "TransactionCanceledException":
                    raise
                reasons = exc.response.get("CancellationReasons", [])
                if reasons and reasons[0].get("Code") == "ConditionalCheckFailed":
                    raise RoomConflictError(409, "Room changed; request getGameState before retrying") from exc
                if len(reasons) > 1 and reasons[1].get("Code") == "ConditionalCheckFailed":
                    raise ArchiveConflict("Immutable board record already exists") from exc
                if (len(reasons) == 3 and reasons[2].get("Code") == "ConditionalCheckFailed"
                        and all(reason.get("Code") in ("None", "ConditionalCheckFailed")
                                for reason in reasons)):
                    continue
                raise
        raise GameRequestError(409, "Event changed; refresh before retrying")


store = MemoryArchiveStore()


def configure_from_environment(db=None):
    """Lambda must explicitly configure durable storage; local memory stays local."""
    global store
    lambda_mode = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    table_name = os.environ.get("BOARD_ARCHIVES_TABLE")
    if not table_name:
        if lambda_mode:
            raise RuntimeError("BOARD_ARCHIVES_TABLE is required in Lambda")
        return store
    if lambda_mode:
        from lambdas.core.game import duplicate
        event_table = os.environ.get("DUPLICATE_EVENTS_TABLE")
        if not event_table:
            raise RuntimeError("DUPLICATE_EVENTS_TABLE is required in Lambda")
        if (not isinstance(duplicate.store, duplicate.DynamoEventStore)
                or duplicate.store.table.name != event_table):
            raise RuntimeError("Durable duplicate event storage must be initialized before archives")
    if not isinstance(store, DynamoArchiveStore) or store.table.name != table_name:
        if db is None:
            import boto3
            table = boto3.resource("dynamodb").Table(table_name)
        else:
            table = db.get_table("BOARD_ARCHIVES_TABLE")
        store = DynamoArchiveStore(table)
    return store


def get_store():
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("BOARD_ARCHIVES_TABLE"):
        return configure_from_environment()
    return store
