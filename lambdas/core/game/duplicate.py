"""Small fixed-table duplicate events, explicitly enabled only by the local adapter."""
import copy
import hashlib
import hmac
import secrets
import threading
import uuid

from botocore.exceptions import ClientError

from lambdas.core.game import rules
from lambdas.core.robot.robot_utils import is_robot_seat

OPERATIONS = ("createDuplicateEvent", "joinDuplicateEvent",
              "startDuplicateEvent", "getDuplicateEvent")
IMP_THRESHOLDS = (20, 50, 90, 130, 170, 220, 270, 320, 370, 430, 500,
                  600, 750, 900, 1100, 1300, 1500, 1750, 2000, 2250,
                  2500, 3000, 3500, 4000)
lock = threading.RLock()
store = None


class DynamoEventStore:
    def __init__(self, table):
        self.table = table

    def get(self, event_id):
        return self.table.get_item(Key={"eventId": event_id}, ConsistentRead=True).get("Item")

    def commit(self, event, rooms=()):
        """One transaction freezes event assignment and every affected room."""
        previous = int(event.get("revision", 0))
        candidate = copy.deepcopy(event)
        candidate["revision"] = previous + 1
        writes = [{"Put": {
            "TableName": self.table.name, "Item": candidate,
            "ConditionExpression": "attribute_not_exists(eventId)" if previous == 0 else "#r = :r",
            **({"ExpressionAttributeNames": {"#r": "revision"},
                "ExpressionAttributeValues": {":r": previous}} if previous else {}),
        }}]
        for table, room in rooms:
            revision = int(room.get("revision", 0))
            room["revision"] = revision + 1
            room.setdefault("gameData", {})["revision"] = revision + 1
            writes.append({"Put": {
                "TableName": table.name, "Item": room,
                "ConditionExpression": "attribute_exists(roomId) AND "
                    "(attribute_not_exists(#r) OR #r = :r)" if revision == 0
                    else "attribute_exists(roomId) AND #r = :r",
                "ExpressionAttributeNames": {"#r": "revision"},
                "ExpressionAttributeValues": {":r": revision},
            }})
        try:
            self.table.meta.client.transact_write_items(TransactItems=writes)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("TransactionCanceledException",
                                                  "ConditionalCheckFailedException"):
                from lambdas.core.game.runtime import GameRequestError
                raise GameRequestError(409, "Event or table changed; refresh before retrying") from exc
            raise
        event["revision"] = previous + 1


def require_store():
    if store is None:
        from lambdas.core.game.runtime import GameRequestError
        raise GameRequestError(503, "Duplicate events are enabled only in the isolated local server")
    return store


def human_users(room):
    return {user for user in room["seats"].values() if user and not is_robot_seat(user)}


def imps(difference):
    magnitude = sum(abs(difference) >= threshold for threshold in IMP_THRESHOLDS)
    return magnitude if difference >= 0 else -magnitude


def comparisons(scores):
    """NS points for each fixed table; EW points are the exact complement."""
    if len(scores) == 2:
        value = imps(scores[0] - scores[1])
        return [(value, -value), (-value, value)]
    maximum = 2 * (len(scores) - 1)
    points = [sum(2 if score > other else 1 if score == other else 0
                  for j, other in enumerate(scores) if j != i)
              for i, score in enumerate(scores)]
    return [(value, maximum - value) for value in points]


def public(event):
    tables = [{"tableNumber": int(entry["tableNumber"]), "roomId": entry["roomId"]}
              for entry in event["tables"]]
    totals = [{"tableNumber": table["tableNumber"], "pointsNS": 0, "pointsEW": 0}
              for table in tables]
    boards = []
    for board in event["boards"]:
        results = board.get("results", {})
        released = len(results) == event["tableCount"]
        item = {"boardNumber": board["boardNumber"], "boardId": board["boardId"],
                "completedTables": len(results), "released": released, "results": []}
        if released:
            scores = [int(results[table["roomId"]]["scoreNS"]) for table in tables]
            for index, (ns, ew) in enumerate(comparisons(scores)):
                item["results"].append({
                    "tableNumber": index + 1, "scoreNS": scores[index],
                    "scoreEW": -scores[index], "pointsNS": ns, "pointsEW": ew})
                totals[index]["pointsNS"] += ns
                totals[index]["pointsEW"] += ew
        boards.append(item)
    return {key: copy.deepcopy(event[key]) for key in
            ("eventId", "organizerId", "status", "tableCount", "boardCount", "scoring")} | {
                "tables": tables, "boards": boards, "totals": totals}


def member(event, user_id):
    return any(user_id in entry["members"] for entry in event["tables"])


def archive_released(event_id, board_number, user_id, room_id):
    if store is None:
        return False
    event = store.get(event_id)
    if not event or not any(entry["roomId"] == room_id and user_id in entry["members"]
                            for entry in event["tables"]):
        return False
    return any(board["boardNumber"] == board_number
               and len(board.get("results", {})) == event["tableCount"]
               for board in event["boards"])


def record_completion(room):
    from lambdas.core.game import archives
    if not room.get("eventId") or not archives.eligible(room) or store is None:
        return
    with lock:
        event = store.get(room["eventId"])
        if not event or event["status"] not in ("started", "completed"):
            return
        game = room["gameData"]
        board = next((item for item in event["boards"] if item["boardId"] == game["boardId"]), None)
        if board is None or not any(table["roomId"] == room["roomId"] for table in event["tables"]):
            raise ValueError("Event completion does not match an assigned board")
        results = board.setdefault("results", {})
        score = {"scoreNS": game["result"]["scoreNS"], "scoreEW": game["result"]["scoreEW"]}
        if room["roomId"] in results:
            if results[room["roomId"]] != score:
                raise ValueError("Event result is immutable")
            return
        results[room["roomId"]] = score
        if all(len(item.get("results", {})) == event["tableCount"] for item in event["boards"]):
            event["status"] = "completed"
        require_store().commit(event)


def deal_for_room(room):
    from lambdas.core.game.runtime import GameRequestError
    event = require_store().get(room["eventId"])
    if not event or event["status"] != "started":
        raise GameRequestError(409, "Event is not running")
    table = next((entry for entry in event["tables"] if entry["roomId"] == room["roomId"]), None)
    if not table or human_users(room) != set(table["members"]):
        raise GameRequestError(403, "Event table membership is frozen")
    number = int(room.get("gameData", {}).get("boardNumber", 0)) + 1
    if number > event["boardCount"]:
        raise GameRequestError(409, "All event boards at this table are finished")
    board = event["boards"][number - 1]
    rules.new_board(room, board["hands"])
    room["gameData"].update(boardId=board["boardId"], eventId=event["eventId"], practiceMode=False)


def request(db, user_id, operation, data, send, context=None):
    from lambdas.core.game import runtime
    repository = require_store()
    with lock:
        event_id = data.get("eventId")
        if operation != "createDuplicateEvent":
            if not isinstance(event_id, str) or not event_id:
                raise runtime.GameRequestError(400, "eventId is required")
            event = repository.get(event_id)
            if not event:
                raise runtime.GameRequestError(404, "Event does not exist")
        room_table = db.get_table("ROOM_TABLE")
        token = None
        changed_rooms = []
        if operation in ("createDuplicateEvent", "joinDuplicateEvent"):
            room_id = data.get("roomId")
            if not isinstance(room_id, str) or not room_id:
                raise runtime.GameRequestError(400, "roomId is required")
            found = db.find_room_by_id(room_id, room_table)
            if not found:
                raise runtime.GameRequestError(404, "Room does not exist")
            room = copy.deepcopy(found)
            if room["ownerId"] != user_id or user_id not in human_users(room):
                raise runtime.GameRequestError(403, "Only the seated room owner may enroll a table")
            if room.get("state") != "waiting" or room.get("eventId") or room.get("gameData", {}).get("boardNumber"):
                raise runtime.GameRequestError(409, "Only a fresh waiting room may join an event")
            if operation == "createDuplicateEvent":
                table_count, board_count = data.get("tableCount"), data.get("boardCount")
                if type(table_count) is not int or not 2 <= table_count <= 4:
                    raise runtime.GameRequestError(400, "tableCount must be an integer from 2 to 4")
                if type(board_count) is not int or not 1 <= board_count <= 8:
                    raise runtime.GameRequestError(400, "boardCount must be an integer from 1 to 8")
                token = secrets.token_urlsafe(32)
                event = {"eventId": str(uuid.uuid4()), "organizerId": user_id,
                         "status": "waiting", "tableCount": table_count, "boardCount": board_count,
                         "scoring": "IMPs" if table_count == 2 else "matchpoints",
                         "invitationHash": hashlib.sha256(token.encode()).hexdigest(),
                         "tables": [], "boards": []}
            else:
                supplied = data.get("invitationToken")
                if not isinstance(supplied, str) or not hmac.compare_digest(
                        hashlib.sha256(supplied.encode()).hexdigest(), event["invitationHash"]):
                    raise runtime.GameRequestError(403, "A valid event invitation is required")
                if event["status"] != "waiting" or len(event["tables"]) >= event["tableCount"]:
                    raise runtime.GameRequestError(409, "Event enrollment is closed")
            if any(human_users(room) & set(entry["members"]) for entry in event["tables"]):
                raise runtime.GameRequestError(403, "Each player may occupy only one event table")
            event["tables"].append({"tableNumber": len(event["tables"]) + 1,
                                    "roomId": room_id, "members": sorted(human_users(room))})
            room["eventId"] = event["eventId"]
            room.setdefault("gameData", {})["eventId"] = event["eventId"]
            room["gameData"]["practiceMode"] = False
            repository.commit(event, [(room_table, room)])
            changed_rooms.append(room)
        elif operation == "startDuplicateEvent":
            if event["organizerId"] != user_id:
                raise runtime.GameRequestError(403, "Only the organizer may start the event")
            if event["status"] == "waiting":
                if len(event["tables"]) != event["tableCount"]:
                    raise runtime.GameRequestError(409, "Every event table must be enrolled")
                rooms = []
                for entry in event["tables"]:
                    found = db.find_room_by_id(entry["roomId"], room_table)
                    if not found or found.get("eventId") != event["eventId"] or found["state"] != "waiting":
                        raise runtime.GameRequestError(409, "An event room is not ready")
                    room = copy.deepcopy(found)
                    if human_users(room) != set(entry["members"]):
                        raise runtime.GameRequestError(409, "Event membership changed")
                    for seat in rules.SEATS:
                        if not room["seats"].get(seat):
                            room["seats"][seat] = f"ROBOT_{seat}"
                    rooms.append(room)
                event["boards"] = [{"boardNumber": number, "boardId": str(uuid.uuid4()),
                                     "hands": rules.deal_cards(), "results": {}}
                                    for number in range(1, int(event["boardCount"]) + 1)]
                event["status"] = "started"
                board = event["boards"][0]
                for room in rooms:
                    rules.new_board(room, board["hands"])
                    room["gameData"].update(boardId=board["boardId"], practiceMode=False)
                    runtime.plan_next_action(room, runtime.Pacing.for_room(room), runtime.now_ms())
                repository.commit(event, [(room_table, room) for room in rooms])
                changed_rooms = rooms
        elif operation == "getDuplicateEvent":
            if not member(event, user_id):
                raise runtime.GameRequestError(403, "Only event participants may view this event")
            # Recover completion after an interrupted room -> event publication.
            for entry in event["tables"]:
                found = db.find_room_by_id(entry["roomId"], room_table)
                if found:
                    record_completion(found)
            event = repository.get(event["eventId"])
        else:
            raise runtime.GameRequestError(400, "Unknown duplicate operation")
        for room in changed_rooms:
            runtime.publish(db, send, room, "gameState", "Duplicate event updated")
            if operation == "startDuplicateEvent":
                runtime.advance_robots(db, room_table, send, room, context)
        event = repository.get(event["eventId"])
        action = {"createDuplicateEvent": "duplicateEventCreated",
                  "joinDuplicateEvent": "duplicateEventJoined",
                  "startDuplicateEvent": "duplicateEventStarted",
                  "getDuplicateEvent": "duplicateEvent"}[operation]
        payload = {"action": action, "eventId": event["eventId"], "event": public(event)}
        if token:
            payload["invitationToken"] = token
        return payload
