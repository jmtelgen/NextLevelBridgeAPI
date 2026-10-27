"""Separate immutable board records, retained for the local server's lifetime.

Only committed completed rooms may be inserted. A production adapter must replace
this process-local store with conditional durable writes before deployment.
"""
import copy
import threading


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


store = MemoryArchiveStore()
