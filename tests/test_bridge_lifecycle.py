"""Offline rules and complete-game regression tests; no AWS clients are called."""
import copy
import importlib
import json

import pytest
from botocore.exceptions import ClientError

from lambdas.core.game import rules, runtime
from lambdas.shared.utils.seat_filtering import create_seat_based_response


def room_fixture(humans=rules.SEATS):
    return {
        "roomId": "room", "ownerId": f"user-{humans[0]}", "roomName": "Bridge",
        "isPrivate": False, "state": "waiting",
        "seats": {seat: f"user-{seat}" if seat in humans else f"ROBOT_{seat}"
                  for seat in rules.SEATS},
        "gameData": {},
    }


def fixed_deal():
    deck = [rank + suit for rank in rules.RANKS for suit in rules.SUITS]
    return {seat: deck[index * 13:(index + 1) * 13]
            for index, seat in enumerate(rules.SEATS)}


def call(room, bid):
    rules.apply_call(room, room["gameData"]["turn"], bid)


def contract_room(contract="1NT"):
    room = room_fixture()
    rules.new_board(room, fixed_deal())
    for bid in (contract, "pass", "pass", "pass"):
        call(room, bid)
    return room


@pytest.mark.parametrize("contract,multiplier,tricks,vulnerable,expected", [
    ("1C", 1, 7, False, 70), ("2D", 1, 9, True, 110),
    ("3NT", 1, 9, False, 400), ("3NT", 1, 10, True, 630),
    ("4H", 1, 10, False, 420), ("4S", 1, 10, True, 620),
    ("5C", 1, 11, False, 400), ("6NT", 1, 12, False, 990),
    ("6H", 1, 12, True, 1430), ("7NT", 1, 13, True, 2220),
    ("7C", 1, 13, False, 1440), ("2H", 2, 8, False, 470),
    ("2H", 4, 8, True, 840), ("1NT", 2, 8, False, 280),
    ("1NT", 4, 8, True, 1160), ("3NT", 1, 8, False, -50),
    ("3NT", 1, 7, True, -200), ("4S", 2, 9, False, -100),
    ("4S", 2, 8, False, -300), ("4S", 2, 7, False, -500),
    ("4S", 2, 6, False, -800), ("4S", 2, 8, True, -500),
    ("4S", 4, 7, True, -1600), ("4S", 4, 6, False, -1600),
])
def test_duplicate_score(contract, multiplier, tricks, vulnerable, expected):
    assert rules.duplicate_score(contract, multiplier, tricks, vulnerable) == expected


def test_auction_legality_doubling_redoubling_and_declarer():
    room = room_fixture()
    rules.new_board(room)
    assert "double" not in rules.legal_calls(room["gameData"])
    for bid in ("1H", "double", "redouble", "pass", "pass", "pass"):
        call(room, bid)
    game = room["gameData"]
    assert room["state"] == "playing"
    assert (game["contract"], game["contractMultiplier"]) == ("1H", 4)
    assert (game["declarer"], game["dummy"], game["turn"]) == ("North", "South", "East")
    assert rules.legal_calls(game) == []


def test_declarer_first_strain_bidder_on_winning_side_not_opponents():
    bids = [{"seat": seat, "bid": bid} for seat, bid in [
        ("North", "1H"), ("East", "2H"), ("South", "pass"), ("West", "3H"),
        ("North", "pass"), ("East", "4H"), ("South", "pass"),
        ("West", "pass"), ("North", "pass")]]
    assert rules.declarer_and_leader(bids) == ("East", "South")


def test_double_after_passes_keeps_full_contract_history():
    room = room_fixture()
    rules.new_board(room)
    for bid in ("3NT", "pass", "pass", "double", "pass", "pass", "pass"):
        call(room, bid)
    assert room["gameData"]["contract"] == "3NT"
    assert room["gameData"]["contractMultiplier"] == 2


def test_invalid_calls_do_not_mutate():
    room = room_fixture()
    rules.new_board(room)
    call(room, "2H")
    for illegal in ("1NT", "2D", "2H", "redouble", "DOUBLE", "", None):
        before = copy.deepcopy(room)
        with pytest.raises(ValueError):
            call(room, illegal)
        assert room == before
    call(room, "pass")
    assert "double" not in rules.legal_calls(room["gameData"])
    with pytest.raises(ValueError):
        rules.apply_call(room, "West", "3C")


def test_all_pass_and_next_board_vulnerability_rotation():
    room = room_fixture()
    for number in range(1, 18):
        rules.new_board(room)
        assert room["gameData"]["dealer"] == rules.SEATS[(number - 1) % 4]
        assert room["gameData"]["vulnerability"] == rules.VULNERABILITIES[(number - 1) % 16]
        assert room["gameData"]["boardNumber"] == number
        hands = [card for cards in room["gameData"]["hands"].values() for card in cards]
        assert len(hands) == len(set(hands)) == 52
        for _ in range(4):
            call(room, "pass")
        assert room["state"] == "completed"
        assert room["gameData"]["turn"] is None
        assert room["gameData"]["result"]["passedOut"]
        assert room["gameData"]["scores"] == {"NS": 0, "EW": 0}


@pytest.mark.parametrize("contract,cards,winner", [
    ("3NT", ["2H", "AS", "KH", "QH"], "South"),
    ("4S", ["AH", "2S", "KH", "AS"], "West"),
    ("4H", ["AS", "2H", "KS", "AH"], "West"),
])
def test_trick_winner(contract, cards, winner):
    plays = [{"seat": seat, "card": card} for seat, card in zip(rules.SEATS, cards)]
    assert rules.trick_winner(plays, contract) == winner


def test_follow_suit_and_first_trick_serialization():
    room = contract_room()
    game = room["gameData"]
    game["hands"] = {"East": ["2H"], "South": ["AH", "AS"], "West": ["KH"], "North": ["3H"]}
    rules.apply_card(room, "East", "2H")
    before = copy.deepcopy(room)
    with pytest.raises(ValueError):
        rules.apply_card(room, "South", "AS")
    assert room == before
    for seat, card in (("South", "AH"), ("West", "KH"), ("North", "3H")):
        rules.apply_card(room, seat, card)
    assert game["turn"] == "South"
    assert game["currentTrick"] == []
    assert game["tricks"][0]["leader"] == "East"
    response = create_seat_based_response(game, room["seats"], "user-North").dict()
    assert response["publicState"]["tricks"][0]["winner"] == "South"
    assert response["publicState"]["previousTrick"]["plays"][0]["card"] == "2H"


def test_dummy_reveal_and_private_legal_control():
    room = contract_room()
    game = room["gameData"]
    for seat in rules.SEATS:
        state = create_seat_based_response(game, room["seats"], f"user-{seat}").dict()
        assert state["publicState"]["dummyHand"] is None
        assert "hands" not in state["publicState"]
        assert state["privateState"]["hand"] == game["hands"][seat]
    rules.apply_card(room, "East", rules.legal_cards(game)[0])
    declarer = create_seat_based_response(game, room["seats"], "user-North").dict()
    dummy = create_seat_based_response(game, room["seats"], "user-South").dict()
    assert declarer["publicState"]["dummyHand"] == game["hands"]["South"]
    assert declarer["privateState"]["isMyTurn"]
    assert declarer["privateState"]["playSeat"] == "South"
    assert declarer["privateState"]["legalCards"] == rules.legal_cards(game)
    assert not dummy["privateState"]["isMyTurn"]
    assert dummy["privateState"]["legalCards"] == []


def test_stale_dummy_flag_cannot_reveal_unled_hand():
    room = contract_room()
    game = room["gameData"]
    game["dummyRevealed"] = True
    state = create_seat_based_response(game, room["seats"], "user-East").dict()
    assert not state["publicState"]["dummyRevealed"]
    assert state["publicState"]["dummyHand"] is None


class MemoryDB:
    def __init__(self, room):
        self.room = copy.deepcopy(room)
        self.saved = []
        self.messages = []
        self.table = self
        self.websocket_connections_table = self
        self.extra_connections = {}
        self.conflict_next = False
        self.now = 1800000000000
        self.room["presence"] = {
            seat: {"userId": user, "connections": {f"conn-{user}": 4102444800}}
            for seat, user in self.room["seats"].items()
            if user and not user.startswith("ROBOT_")}

    def get_table(self, name):
        assert name == "ROOM_TABLE"
        return self

    def find_room_by_id(self, room_id, table=None):
        return copy.deepcopy(self.room) if room_id == self.room["roomId"] else None

    def query(self, **kwargs):
        connection = kwargs["ExpressionAttributeValues"][":connectionId"]
        return {"Items": [{"userId": connection.removeprefix("conn-"), "status": "connected",
                           "authExpiresAt": 4102444800, "authType": "guest"}]}

    def get_user_connections(self, user):
        return [f"conn-{user}"] + self.extra_connections.get(user, [])

    def get_user_connection_records(self, user):
        return [{"connectionId": connection, "userId": user, "authExpiresAt": 4102444800}
                for connection in [f"conn-{user}"] + self.extra_connections.get(user, [])]

    def update_user_room(self, *args):
        return True

    def put_item(self, **kwargs):
        assert "ConditionExpression" in kwargs
        expected = kwargs["ExpressionAttributeValues"][":expected"]
        if self.conflict_next or expected != self.room.get("revision", 0):
            self.conflict_next = False
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.room = copy.deepcopy(kwargs["Item"])
        self.saved.append(copy.deepcopy(self.room))

    def send(self, connection, payload):
        json.dumps(payload)
        self.messages.append((connection, copy.deepcopy(payload)))


@pytest.fixture
def server(monkeypatch):
    modules = {name: importlib.import_module(f"lambdas.api.websocket.websocket_{name}")
               for name in ("start_room", "make_bid", "play_card", "board_records")}

    def build(humans=rules.SEATS, real_play=False):
        db = MemoryDB(room_fixture(humans))
        monkeypatch.setattr(runtime, "now_ms", lambda: db.now)
        for module in modules.values():
            monkeypatch.setattr(module, "db_utils", db)
            monkeypatch.setattr(module, "broadcast_to_connection", db.send)
        monkeypatch.setattr(runtime, "execute_robot_bid",
                            lambda room, seat: "1NT" if not room["gameData"]["bids"] else "pass")
        if not real_play:
            monkeypatch.setattr(runtime, "execute_robot_card_play",
                                lambda room, seat: rules.legal_cards(room["gameData"], seat)[0])
        start = modules["start_room"].WebSocketStartRoomHandler()
        monkeypatch.setattr(start, "_deal_cards", fixed_deal)
        handlers = {
            "startRoom": start, "nextBoard": start, "getGameState": start,
            "makeBid": modules["make_bid"].WebSocketMakeBidHandler(),
            "playCard": modules["play_card"].WebSocketPlayCardHandler(),
        }
        handlers.update({route: modules["board_records"].BoardRecordsHandler()
                         for route in (*runtime.READ_FEATURES, "setPracticePace")})

        def request(route, user=None, context=None, **data):
            user = user or db.room["ownerId"]
            event = {"requestContext": {"routeKey": route, "connectionId": f"conn-{user}"},
                     "body": json.dumps({"roomId": "room", "userId": user, **data})}
            result = handlers[route].process_websocket_request(event, context)
            return result["statusCode"], json.loads(result["body"])

        return db, request
    return build


def drain_pending(db, request):
    for _ in range(128):
        pending = db.room["gameData"].get("pendingAction")
        if not pending:
            return
        db.now = pending["dueAt"]
        assert request("getGameState")[0] == 200
    pytest.fail("Autonomous work did not reach a human turn")


@pytest.mark.parametrize("humans", [
    rules.SEATS, ("North",), ("East",), ("South",), ("West",),
    ("North", "South"), ("North", "East"), ("East", "West"),
    ("North", "East", "South"),
])
def test_complete_game_and_next_board(server, humans):
    db, request = server(humans)
    status, payload = request("startRoom")
    assert status == 200
    steps = 0
    while db.room["state"] != "completed":
        drain_pending(db, request)
        if db.room["state"] == "completed":
            break
        game = db.room["gameData"]
        controller = rules.controller(game)
        user = db.room["seats"][controller]
        assert not user.startswith("ROBOT_")
        if game["currentPhase"] == "bidding":
            bid = "1NT" if not game["bids"] else "pass"
            status, _ = request("makeBid", user, bid=bid, revision=db.room["revision"])
        else:
            status, _ = request("playCard", user, card=rules.legal_cards(game)[0],
                                revision=db.room["revision"])
        assert status == 200
        steps += 1
        assert steps < 70
    game = db.room["gameData"]
    assert len(game["tricks"]) == 13
    cards = [play["card"] for trick in game["tricks"] for play in trick["plays"]]
    assert len(cards) == len(set(cards)) == 52
    assert all(not hand for hand in game["hands"].values())
    assert game["result"]["scoreNS"] == -game["result"]["scoreEW"]
    assert game["scores"]["NS"] == game["result"]["scoreNS"]
    assert [room["revision"] for room in db.saved] == list(range(1, len(db.saved) + 1))
    for connection, update in db.messages:
        assert "gameData" not in update
        assert "hands" not in update
        assert "gameData" not in update["room"]
        assert "hands" not in update["publicState"]
        user = connection.removeprefix("conn-")
        assert update["privateState"]["seat"] == user.removeprefix("user-")
        assert "hands" not in update["privateState"]
        if not update["publicState"]["dummyRevealed"]:
            assert update["publicState"]["dummyHand"] is None
    result = copy.deepcopy(game["result"])
    revision = db.room["revision"]
    status, snapshot = request("getGameState")
    assert status == 200
    assert snapshot["publicState"]["result"] == result
    assert db.room["revision"] == revision
    status, next_board = request("nextBoard", revision=db.room["revision"])
    assert status == 200
    assert next_board["publicState"]["boardNumber"] == 2
    assert next_board["publicState"]["dealer"] == "East"
    assert next_board["publicState"]["scores"]["NS"] == result["scoreNS"]
    assert next_board["publicState"]["result"] is None


def test_connection_spoof_and_stale_write_are_rejected(server):
    db, request = server()
    assert request("startRoom")[0] == 200
    before = copy.deepcopy(db.room)
    assert request("makeBid", bid="1C", userId="user-East")[0] == 403
    assert db.room == before
    assert request("makeBid", bid="1C", revision=0)[0] == 409
    assert db.room == before
    db.conflict_next = True
    assert request("makeBid", bid="1C")[0] == 409
    assert db.room == before
    assert db.messages[-1][1]["action"] == "error"


def test_dummy_cannot_play_own_hand_or_defenders_control_it(server):
    db, request = server()
    request("startRoom")
    for seat, bid in zip(rules.SEATS, ("1NT", "pass", "pass", "pass")):
        assert request("makeBid", f"user-{seat}", bid=bid)[0] == 200
    assert request("playCard", "user-East", card=rules.legal_cards(db.room["gameData"])[0])[0] == 200
    before = copy.deepcopy(db.room)
    card = rules.legal_cards(db.room["gameData"])[0]
    assert request("playCard", "user-South", card=card)[0] == 400
    assert request("playCard", "user-West", card=card)[0] == 400
    assert db.room == before
    assert request("playCard", "user-North", card=card)[0] == 200


def test_reconnect_snapshot_waiting_and_multitab_delivery(server):
    db, request = server()
    status, waiting = request("getGameState")
    assert status == 200
    assert waiting["publicState"]["currentPhase"] == "waiting"
    assert waiting["room"]["ownerId"] == "user-North"
    db.extra_connections["user-East"] = ["extra-east"]
    request("startRoom")
    assert any(connection == "extra-east" and payload["seat"] == "East"
               for connection, payload in db.messages)
    status, reconnect = request("getGameState", "user-East")
    assert status == 200
    assert reconnect["privateState"]["hand"] == db.room["gameData"]["hands"]["East"]
    assert reconnect["publicState"]["dummyHand"] is None


def test_persisted_robot_moves_survive_snapshot_and_resume(server):
    db, request = server(("West",))
    class LowBudget:
        def get_remaining_time_in_millis(self):
            return 1000
    assert request("startRoom", context=LowBudget())[0] == 200
    assert db.room["gameData"]["bids"] == []
    assert db.room["gameData"]["robotPending"]
    assert request("getGameState")[0] == 200
    assert [bid["seat"] for bid in db.room["gameData"]["bids"]] == ["North", "East", "South"]
    saved = copy.deepcopy(db.room)
    assert request("getGameState")[0] == 200
    assert db.room == saved


def test_robot_exception_and_illegal_card_fallback(server, monkeypatch):
    db, request = server(("North",))
    request("startRoom")
    monkeypatch.setattr(runtime, "execute_robot_bid", lambda *args: "7INVALID")
    assert request("makeBid", bid="1NT")[0] == 200
    drain_pending(db, request)
    # East robot leads, human North is declarer and must now play South dummy.
    assert db.room["gameData"]["turn"] == "South"
    monkeypatch.setattr(runtime, "execute_robot_card_play", lambda *args: "ZZ")
    assert request("playCard", card=rules.legal_cards(db.room["gameData"])[0])[0] == 200
    expected = rules.legal_cards(db.room["gameData"])[0]
    drain_pending(db, request)
    assert db.room["gameData"]["currentTrick"][-1]["seat"] == "West"
    assert db.room["gameData"]["currentTrick"][-1]["card"] == expected


def test_legacy_completed_trick_migration():
    room = contract_room()
    room["gameData"]["tricks"] = [{"cards": [
        {"seat": seat, "card": rank + "H"} for seat, rank in zip(rules.SEATS, "2345")
    ], "winner": "West"}]
    runtime.normalize_room(room)
    state = create_seat_based_response(room["gameData"], room["seats"], "user-East").dict()
    assert state["publicState"]["tricks"][0]["leader"] == "North"
    assert state["publicState"]["tricks"][0]["winner"] == "West"
    assert state["publicState"]["dummyRevealed"]


def test_complete_game_with_real_fair_robot_selector(server, monkeypatch):
    monkeypatch.setenv("ROBOT_PLAY_SAMPLES", "1")
    monkeypatch.setenv("ROBOT_PLAY_BUDGET_MS", "50")
    db, request = server(("North",), real_play=True)
    request("startRoom")
    assert request("makeBid", bid="1NT")[0] == 200
    for _ in range(30):
        drain_pending(db, request)
        if db.room["state"] == "completed":
            break
        assert rules.controller(db.room["gameData"]) == "North"
        card = rules.legal_cards(db.room["gameData"])[0]
        assert request("playCard", card=card)[0] == 200
    assert db.room["state"] == "completed"
    assert len(db.room["gameData"]["tricks"]) == 13
    assert db.room["gameData"]["result"]["declarerTricks"] in range(14)


def test_completed_board_cannot_be_scored_twice(server):
    db, request = server()
    request("startRoom")
    for seat in rules.SEATS:
        assert request("makeBid", f"user-{seat}", bid="pass")[0] == 200
    before = copy.deepcopy(db.room)
    assert request("makeBid", bid="1C")[0] == 400
    assert request("playCard", card="AS")[0] == 400
    assert request("startRoom")[0] == 400
    assert request("nextBoard", "user-East")[0] == 403
    assert db.room == before


def test_connection_requires_one_known_nonrobot_identity():
    class Connections:
        def __init__(self, items):
            self.items = items
            self.websocket_connections_table = self

        def query(self, **kwargs):
            assert kwargs["ConsistentRead"]
            return {"Items": self.items}

    event = {"requestContext": {"connectionId": "connection"}}
    for items in ([], [{"userId": "user", "status": "disconnected"}],
                  [{"userId": "a", "status": "connected"},
                   {"userId": "b", "status": "connected"}]):
        with pytest.raises(runtime.GameRequestError) as error:
            runtime.connection_user(Connections(items), event)
        assert error.value.status == 401
    with pytest.raises(runtime.GameRequestError) as error:
        runtime.connection_user(Connections([{
            "userId": "ROBOT_North", "status": "connected",
            "authExpiresAt": 4102444800, "authType": "guest"}]), event)
    assert error.value.status == 403
    with pytest.raises(runtime.GameRequestError) as error:
        runtime.connection_user(Connections([]), {})
    assert error.value.status == 401


def test_room_and_connections_paginate_without_losing_matches():
    from lambdas.shared.database.db_utils import DatabaseUtils

    class Pages:
        def __init__(self, pages):
            self.pages = iter(pages)
            self.calls = []

        def scan(self, **kwargs):
            self.calls.append(kwargs)
            return next(self.pages)

    db = DatabaseUtils.__new__(DatabaseUtils)
    rooms = Pages([{"Items": [], "LastEvaluatedKey": {"key": "page"}},
                   {"Items": [{"roomId": "wanted"}]}])
    assert db.find_room_by_id("wanted", rooms) == {"roomId": "wanted"}
    assert rooms.calls[0]["ConsistentRead"]
    assert rooms.calls[1]["ExclusiveStartKey"] == {"key": "page"}
    def record(connection):
        return {"connectionId": connection, "userId": "user", "status": "connected",
                "authType": "guest", "authExpiresAt": 4102444800}
    connections = Pages([
        {"Items": [record("b")], "LastEvaluatedKey": {"key": "page"}},
        {"Items": [record("a"), record("b")]},
    ])
    db._websocket_connections_table = connections
    assert db.get_user_connections("user") == ["a", "b"]
    assert connections.calls[1]["ExclusiveStartKey"] == {"key": "page"}


def test_delivery_failure_does_not_lose_accepted_move(server, monkeypatch):
    db, request = server()
    request("startRoom")
    monkeypatch.setattr(db, "get_user_connections", lambda user: (_ for _ in ()).throw(RuntimeError("offline")))
    assert request("makeBid", bid="1C")[0] == 200
    assert db.room["gameData"]["bids"][-1]["bid"] == "1C"
    assert db.room["revision"] == 2


def test_new_routes_reject_unseated_user_and_premature_next_board(server):
    db, request = server()
    assert request("getGameState", "unseated")[0] == 403
    assert request("nextBoard")[0] == 400
    assert db.room["state"] == "waiting"
    request("startRoom")
    assert request("nextBoard")[0] == 400


@pytest.mark.parametrize("name,class_name,fields", [
    ("join_room", "WebSocketJoinRoomHandler", {}),
    ("change_seat", "WebSocketChangeSeatHandler", {"newSeat": "East"}),
])
def test_seat_mutations_cannot_overwrite_started_board(server, monkeypatch, name, class_name, fields):
    db, request = server()
    request("startRoom")
    before = copy.deepcopy(db.room)
    module = importlib.import_module(f"lambdas.api.websocket.websocket_{name}")
    monkeypatch.setattr(module, "db_utils", db)
    handler = getattr(module, class_name)()
    event = {"requestContext": {"routeKey": "joinRoom" if name == "join_room" else "changeSeat",
                                "connectionId": "conn-user-North"},
             "body": json.dumps({"roomId": "room", "userId": "user-North", **fields})}
    result = handler.process_websocket_request(event, None)
    assert result["statusCode"] == (200 if name == "join_room" else 409)
    if name == "join_room":
        assert json.loads(result["body"])["updateType"] == "userReconnected"
    assert db.room == before


def test_waiting_join_is_conditional_and_never_broadcasts_hands(server, monkeypatch):
    db, _ = server()
    db.room["seats"]["East"] = None
    db.room["gameData"] = {
        "currentPhase": "waiting", "turn": "North", "bids": [], "tricks": [],
        "hands": fixed_deal(),
    }
    module = importlib.import_module("lambdas.api.websocket.websocket_join_room")
    monkeypatch.setattr(module, "db_utils", db)
    monkeypatch.setattr(module, "broadcast_to_connection", db.send)
    monkeypatch.setattr(db, "update_user_room", lambda *args: True, raising=False)
    monkeypatch.setattr(db, "get_room_connection", lambda user: f"conn-{user}", raising=False)
    handler = module.WebSocketJoinRoomHandler()
    monkeypatch.setattr(handler, "_convert_seats_to_usernames", lambda seats: seats)
    event = {"requestContext": {"routeKey": "joinRoom", "connectionId": "conn-new-user"},
             "body": json.dumps({"roomId": "room", "userId": "new-user"})}
    result = handler.process_websocket_request(event, None)
    assert result["statusCode"] == 200
    assert db.room["revision"] == 2  # Presence cleanup and seat acquisition each use CAS.
    for _, payload in db.messages:
        assert "gameData" not in payload["room"]
        assert "hands" not in payload["publicState"]


@pytest.mark.parametrize("sort_key", [None, "ownerId"])
def test_real_dynamodb_expression_rejects_stale_and_deleted_items(sort_key):
    import boto3
    try:
        from moto import mock_aws
    except ImportError:
        from moto import mock_dynamodb as mock_aws
    from lambdas.shared.database.db_utils import DatabaseUtils

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        keys = [{"AttributeName": "roomId", "KeyType": "HASH"}]
        attributes = [{"AttributeName": "roomId", "AttributeType": "S"}]
        if sort_key:
            keys.append({"AttributeName": sort_key, "KeyType": "RANGE"})
            attributes.append({"AttributeName": sort_key, "AttributeType": "S"})
        table = dynamodb.create_table(
            TableName="rooms", KeySchema=keys, AttributeDefinitions=attributes,
            BillingMode="PAY_PER_REQUEST")
        room = room_fixture()
        table.put_item(Item=room)
        db = DatabaseUtils()
        winner = db.find_room_by_id("room", table)
        stale = copy.deepcopy(winner)
        rules.new_board(winner, fixed_deal())
        runtime.save_room(table, winner)
        rules.new_board(stale, fixed_deal())
        with pytest.raises(runtime.GameRequestError) as error:
            runtime.save_room(table, stale)
        assert error.value.status == 409
        assert db.find_room_by_id("room", table)["revision"] == 1
        key = {"roomId": "room"}
        if sort_key:
            key[sort_key] = room[sort_key]
        table.delete_item(Key=key)
        with pytest.raises(runtime.GameRequestError) as error:
            runtime.save_room(table, winner)
        assert error.value.status == 409
        assert db.find_room_by_id("room", table) is None


def test_dynamodb_decimal_nested_result_is_json_safe():
    from decimal import Decimal
    room = contract_room()
    room["gameData"]["result"] = {
        "scoreNS": Decimal("400"), "scoreEW": Decimal("-400"),
        "target": Decimal("9"), "made": True,
    }
    room["gameData"]["revision"] = Decimal("8")
    room["gameData"]["scores"] = {"NS": Decimal("400"), "EW": Decimal("-400")}
    payload = runtime.personalized(room, "user-North", "gameState", "Snapshot")
    assert json.loads(json.dumps(payload))["publicState"]["result"]["scoreNS"] == 400


@pytest.mark.parametrize("humans", [rules.SEATS, ("North",), ("South",)])
def test_full_game_with_emulated_dynamodb_persistence(server, monkeypatch, humans):
    import boto3
    try:
        from moto import mock_aws
    except ImportError:
        from moto import mock_dynamodb as mock_aws

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="game-rooms", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "roomId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "roomId", "AttributeType": "S"}])
        connections = dynamodb.create_table(
            TableName="connections", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "connectionId", "KeyType": "HASH"},
                       {"AttributeName": "currentRoomId", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "connectionId", "AttributeType": "S"},
                                  {"AttributeName": "currentRoomId", "AttributeType": "S"}])
        db, request = server(humans)
        table.put_item(Item=db.room)
        for seat in humans:
            connections.put_item(Item={
                "connectionId": f"conn-user-{seat}", "currentRoomId": "room",
                "userId": f"user-{seat}", "status": "connected",
                "authExpiresAt": 4102444800, "authType": "guest"})
        db.websocket_connections_table = connections

        def persist(**kwargs):
            table.put_item(**kwargs)
            db.room = table.get_item(Key={"roomId": "room"}, ConsistentRead=True)["Item"]
            db.saved.append(copy.deepcopy(db.room))

        monkeypatch.setattr(db, "put_item", persist)
        assert request("startRoom")[0] == 200
        for _ in range(60):
            drain_pending(db, request)
            if db.room["state"] == "completed":
                break
            game = db.room["gameData"]
            user = db.room["seats"][rules.controller(game)]
            if game["currentPhase"] == "bidding":
                assert request("makeBid", user, bid="1NT" if not game["bids"] else "pass")[0] == 200
            else:
                assert request("playCard", user, card=rules.legal_cards(game)[0])[0] == 200
        final = table.get_item(Key={"roomId": "room"}, ConsistentRead=True)["Item"]
        assert final["state"] == "completed"
        assert len(final["gameData"]["tricks"]) == 13
        assert sum(len(trick["plays"]) for trick in final["gameData"]["tricks"]) == 52
        assert all(not hand for hand in final["gameData"]["hands"].values())
        assert request("getGameState")[1]["publicState"]["result"]["made"] in (True, False)
        assert db.messages[-1][1]["publicState"]["currentPhase"] == "completed"
        assert request("nextBoard", revision=int(db.room["revision"]))[0] == 200
        assert db.room["gameData"]["boardNumber"] == 2
