"""Atomic Moto event storage, comparisons and cross-table information boundaries."""
import copy
import json

import boto3
import pytest
from moto import mock_aws

from lambdas.core.game import archives, duplicate, rules, runtime
from lambdas.core.rooms import lifecycle
from lambdas.core.robot.practice import PracticeDenied, require_solo
from lambdas.api.websocket.websocket_claims_duplicate import ClaimsDuplicateHandler
from test_bridge_lifecycle import room_fixture


class EventDB:
    def __init__(self, table):
        self.table = table
        self.websocket_connections_table = self

    def get_table(self, _):
        return self.table

    def find_room_by_id(self, room_id, table=None):
        return next((room for room in self.table.scan(ConsistentRead=True)["Items"]
                     if room["roomId"] == room_id), None)

    def query(self, **kwargs):
        user = kwargs["ExpressionAttributeValues"][":connectionId"].removeprefix("conn-")
        return {"Items": [{"userId": user, "status": "connected", "authType": "guest",
                           "authExpiresAt": 4102444800}]}

    def get_user_connection_records(self, user):
        return [{"connectionId": "conn-" + user, "authExpiresAt": 4102444800}]

    def get_user_connections(self, user):
        return []


@pytest.fixture
def event_server(monkeypatch):
    with mock_aws():
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        rooms = dynamo.create_table(
            TableName="claim-test-rooms", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "roomId", "KeyType": "HASH"},
                       {"AttributeName": "ownerId", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}
                                  for key in ("roomId", "ownerId")])
        events = dynamo.create_table(
            TableName="claim-test-events", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "eventId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "eventId", "AttributeType": "S"}])
        monkeypatch.setattr(duplicate, "store", duplicate.DynamoEventStore(events))
        monkeypatch.setattr(archives, "store", archives.MemoryArchiveStore())
        monkeypatch.setattr(runtime, "now_ms", lambda: 1800000000000)
        db = EventDB(rooms)
        handler = ClaimsDuplicateHandler()

        def create_room(index, humans=rules.SEATS):
            room = room_fixture(humans)
            room["roomId"] = f"table-{index}"
            room["seats"] = {seat: f"player-{index}-{seat}" if seat in humans else ""
                             for seat in rules.SEATS}
            room["ownerId"] = f"player-{index}-{humans[0]}"
            rooms.put_item(Item=room)
            return room

        def request(operation, user, **data):
            event = {"requestContext": {"connectionId": "conn-" + user, "routeKey": operation},
                     "body": json.dumps({"data": data})}
            result = runtime.process_game_request(handler, event, None, operation, db, lambda *args: None)
            return result["statusCode"], json.loads(result["body"])

        yield db, create_room, request


def enroll(event_server, count=2, boards=2, humans=rules.SEATS):
    db, create_room, request = event_server
    rooms = [create_room(index, humans) for index in range(1, count + 1)]
    status, created = request("createDuplicateEvent", rooms[0]["ownerId"],
                              roomId=rooms[0]["roomId"], tableCount=count, boardCount=boards)
    assert status == 200, created
    event_id, token = created["eventId"], created["invitationToken"]
    for room in rooms[1:]:
        status, joined = request("joinDuplicateEvent", room["ownerId"],
                                 eventId=event_id, roomId=room["roomId"], invitationToken=token)
        assert status == 200, joined
    return rooms, event_id, token


def pass_board(db, request, room_id):
    room = db.find_room_by_id(room_id)
    assert request("getGameState", room["ownerId"], roomId=room_id)[0] == 200
    room = db.find_room_by_id(room_id)
    for _ in range(4):
        game = room["gameData"]
        status, payload = request("makeBid", room["seats"][game["turn"]],
                                  roomId=room_id, bid="pass", revision=int(room["revision"]))
        assert status == 200, payload
        room = db.find_room_by_id(room_id)
    return room


def test_two_table_event_same_deals_embargo_next_board_and_completion(event_server):
    db, _, request = event_server
    rooms, event_id, token = enroll(event_server)
    owner = rooms[0]["ownerId"]
    assert request("startDuplicateEvent", rooms[1]["ownerId"], eventId=event_id)[0] == 403
    assert request("startRoom", owner, roomId=rooms[0]["roomId"])[0] == 409
    status, started = request("startDuplicateEvent", owner, eventId=event_id)
    assert status == 200, started
    one, two = [db.find_room_by_id(room["roomId"]) for room in rooms]
    assert one["gameData"]["initialHands"] == two["gameData"]["initialHands"]
    assert one["gameData"]["boardId"] == two["gameData"]["boardId"]
    assert one["gameData"]["dealer"] == two["gameData"]["dealer"] == "North"
    assert "hands" not in str(started) and "invitationHash" not in str(started)
    first = pass_board(db, request, rooms[0]["roomId"])
    board_id = first["gameData"]["boardId"]
    assert request("getBoardArchive", owner, roomId=first["roomId"], boardId=board_id)[0] == 403
    assert request("listBoardArchives", owner, roomId=first["roomId"])[1]["boards"] == []
    public = request("getDuplicateEvent", owner, eventId=event_id)[1]["event"]
    assert public["boards"][0]["completedTables"] == 1
    assert public["boards"][0]["results"] == [] and not public["boards"][0]["released"]
    # Tables may advance independently. An old board must remain embargoed.
    assert request("nextBoard", owner, roomId=first["roomId"], boardId=board_id)[0] == 200
    assert request("getBoardArchive", owner, roomId=first["roomId"], boardId=board_id)[0] == 403
    pass_board(db, request, rooms[1]["roomId"])
    assert request("getBoardArchive", owner, roomId=first["roomId"], boardId=board_id)[0] == 200
    assert request("getBoardArchive", owner, roomId=two["roomId"], boardId=board_id)[0] == 403
    public = request("getDuplicateEvent", owner, eventId=event_id)[1]["event"]
    assert public["boards"][0]["released"] and public["boards"][0]["results"][0]["pointsNS"] == 0
    assert request("nextBoard", owner, roomId=first["roomId"], boardId=board_id)[0] == 400
    first = pass_board(db, request, first["roomId"])
    assert request("nextBoard", owner, roomId=first["roomId"], boardId=board_id)[0] == 409
    assert request("nextBoard", owner, roomId=first["roomId"],
                   boardId=first["gameData"]["boardId"])[0] == 409
    second = db.find_room_by_id(two["roomId"])
    assert request("nextBoard", two["ownerId"], roomId=two["roomId"],
                   boardId=second["gameData"]["boardId"])[0] == 200
    pass_board(db, request, two["roomId"])
    final = request("getDuplicateEvent", owner, eventId=event_id)[1]["event"]
    assert final["status"] == "completed" and all(board["released"] for board in final["boards"])
    assert final["scoring"] == "IMPs"
    assert request("startDuplicateEvent", owner, eventId=event_id)[1]["event"] == final
    assert len(archives.store.list(first["roomId"])) == 2


@pytest.mark.parametrize("scores,expected", [
    ([420, 170], [(6, -6), (-6, 6)]),
    ([0, 0], [(0, 0), (0, 0)]),
    ([100, 100, -50], [(3, 1), (3, 1), (0, 4)]),
    ([0, 0, 0], [(2, 2), (2, 2), (2, 2)]),
    ([100, 0, 0, -100], [(6, 0), (3, 3), (3, 3), (0, 6)]),
])
def test_standard_imps_and_matchpoint_ties(scores, expected):
    assert duplicate.comparisons(scores) == expected
    assert duplicate.imps(19) == 0 and duplicate.imps(20) == 1
    assert duplicate.imps(-3990) == -23 and duplicate.imps(4000) == 24


def test_three_table_ties_bounds_auth_and_frozen_membership(event_server):
    db, create_room, request = event_server
    room = create_room(1)
    owner = room["ownerId"]
    for tables, boards in [(1, 1), (5, 1), (True, 1), (2, 0), (2, 9), (2, "1")]:
        assert request("createDuplicateEvent", owner, roomId=room["roomId"],
                       tableCount=tables, boardCount=boards)[0] == 400
    assert request("createDuplicateEvent", "outsider", roomId=room["roomId"],
                   tableCount=3, boardCount=1)[0] == 403
    status, created = request("createDuplicateEvent", owner, roomId=room["roomId"],
                              tableCount=3, boardCount=1)
    assert status == 200
    event_id, token = created["eventId"], created["invitationToken"]
    assert request("getDuplicateEvent", "outsider", eventId=event_id)[0] == 403
    assert request("getDuplicateEvent", owner, eventId=event_id)[0] == 200
    assert request("startDuplicateEvent", owner, eventId=event_id)[0] == 409
    bound = db.find_room_by_id(room["roomId"])
    for mutate in (
        lambda: lifecycle.change_seat(db.table, bound, owner, "East"),
        lambda: lifecycle.leave_room(db.table, bound, owner),
        lambda: lifecycle.replace_player(db, db.table, bound, owner, "East"),
        lambda: lifecycle.control_room(db.table, bound, owner, "transferOwnership",
                                       {"newOwnerId": bound["seats"]["East"]}, db=db),
        lambda: lifecycle.join_room(db, db.table, bound, "outsider"),
    ):
        with pytest.raises(runtime.GameRequestError) as exc:
            mutate()
        assert exc.value.status == 409
    bound = db.find_room_by_id(room["roomId"])
    assert lifecycle.join_room(db, db.table, bound, owner)[2] is True
    # Existing overlapping membership is checked, not just the enrolling owner.
    overlap = create_room(9)
    overlap["seats"]["South"] = bound["seats"]["South"]
    db.table.put_item(Item=overlap)
    assert request("joinDuplicateEvent", overlap["ownerId"], roomId=overlap["roomId"],
                   eventId=event_id, invitationToken=token)[0] == 403
    for index in (2, 3):
        next_room = create_room(index)
        assert request("joinDuplicateEvent", next_room["ownerId"], roomId=next_room["roomId"],
                       eventId=event_id, invitationToken="bad")[0] == 403
        assert request("joinDuplicateEvent", next_room["ownerId"], roomId=next_room["roomId"],
                       eventId=event_id, invitationToken=token)[0] == 200
    assert request("startDuplicateEvent", owner, eventId=event_id)[0] == 200
    for index in (1, 2, 3):
        pass_board(db, request, f"table-{index}")
    public = request("getDuplicateEvent", owner, eventId=event_id)[1]["event"]
    assert public["scoring"] == "matchpoints"
    assert [row["pointsNS"] for row in public["boards"][0]["results"]] == [2, 2, 2]
    assert public["totals"] == [{"tableNumber": i, "pointsNS": 2, "pointsEW": 2} for i in (1, 2, 3)]


def test_event_solo_policies_and_atomic_revision_guard(event_server):
    db, create_room, request = event_server
    one = create_room(1, ("North",))
    status, created = request("createDuplicateEvent", one["ownerId"], roomId=one["roomId"],
                              tableCount=2, boardCount=1)
    assert status == 200
    bound = db.find_room_by_id(one["roomId"])
    bound["seats"].update({seat: f"ROBOT_{seat}" for seat in ("East", "South", "West")})
    with pytest.raises(PracticeDenied):
        require_solo(bound, one["ownerId"])
    assert request("setPracticePace", one["ownerId"], roomId=one["roomId"],
                   practiceMode=True, robotCardDelayMs=100, trickHoldMs=1000)[0] == 403
    before = duplicate.store.get(created["eventId"])
    candidate = copy.deepcopy(before)
    stale_room = db.find_room_by_id(one["roomId"])
    concurrent = copy.deepcopy(stale_room)
    runtime.save_room(db.table, concurrent)
    candidate["status"] = "started"
    with pytest.raises(runtime.GameRequestError) as exc:
        duplicate.store.commit(candidate, [(db.table, stale_room)])
    assert exc.value.status == 409
    assert duplicate.store.get(created["eventId"]) == before


def test_event_hint_and_computer_settings_denied_by_socket_handler(event_server, monkeypatch):
    from lambdas.api.websocket import websocket_practice
    db, create_room, request = event_server
    room = create_room(1, ("North",))
    assert request("createDuplicateEvent", room["ownerId"], roomId=room["roomId"],
                   tableCount=2, boardCount=1)[0] == 200
    monkeypatch.setattr(websocket_practice, "db_utils", db)
    monkeypatch.setattr(websocket_practice, "broadcast_to_connection", lambda *args: None)
    for action in ("getPracticeHint", "setComputerLevel"):
        event = {"requestContext": {"connectionId": "conn-" + room["ownerId"], "routeKey": action},
                 "body": json.dumps({"data": {"roomId": room["roomId"], "computerLevel": "heuristic"}})}
        result = websocket_practice.WebSocketPracticeHandler().process_websocket_request(event, None)
        assert result["statusCode"] == 403
