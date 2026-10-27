"""Consent, identity, freeze, resumption and settlement without wall-clock sleeps."""
import copy
import json

import pytest

from lambdas.core.game import archives, claims, rules, runtime
from lambdas.api.websocket.websocket_claims_duplicate import ClaimsDuplicateHandler
from test_bridge_lifecycle import server, contract_room, fixed_deal


@pytest.fixture
def claim_server(server, monkeypatch):
    monkeypatch.setattr(archives, "store", archives.MemoryArchiveStore())

    def build(humans=rules.SEATS):
        db, normal = server(humans)
        handler = ClaimsDuplicateHandler()

        def request(operation, user=None, **data):
            user = user or db.room["ownerId"]
            game = db.room["gameData"]
            event = {"requestContext": {"routeKey": operation, "connectionId": f"conn-{user}"},
                     "body": json.dumps({"data": {
                         "roomId": "room", "boardId": game.get("boardId"),
                         "revision": db.room.get("revision", 0), "proposalId": "proposal-1", **data}})}
            result = runtime.process_game_request(
                handler, event, None, operation, db, db.send, hands_factory=fixed_deal)
            return result["statusCode"], json.loads(result["body"])

        normal("startRoom")
        for seat in rules.SEATS:
            game = db.room["gameData"]
            if game["currentPhase"] != "bidding":
                break
            actor = rules.controller(game)
            if db.room["seats"][actor].startswith("ROBOT"):
                continue
            assert normal("makeBid", db.room["seats"][actor],
                          bid="1NT" if not game["bids"] else "pass")[0] == 200
        return db, normal, request

    return build


def test_unanimous_positive_claim_and_idempotent_score_archive(claim_server):
    db, normal, request = claim_server()
    original = copy.deepcopy(db.room["gameData"])
    revision = db.room["revision"]
    status, state = request("proposeClaim", "user-East", tricks=5)
    assert status == 200
    assert state["publicState"]["claim"]["requiredSeats"] == ["North", "South", "West"]
    assert state["publicState"]["dummyHand"] is None
    assert not state["privateState"]["isMyTurn"] and state["privateState"]["legalCards"] == []
    assert normal("playCard", "user-East", card=rules.legal_cards(original)[0])[0] == 409
    assert normal("getBoardArchive", boardId=original["boardId"])[0] == 409
    count = len(db.saved)
    assert request("proposeClaim", "user-East", tricks=5, revision=revision)[0] == 200
    assert len(db.saved) == count
    assert request("respondClaim", "user-North", accept=True)[0] == 200
    assert request("respondClaim", "user-South", accept=True)[0] == 200
    db.conflict_next = True
    assert request("respondClaim", "user-West", accept=True)[0] == 409
    assert db.room["state"] == "playing"
    assert archives.store.get("room", original["boardId"]) is None
    assert request("respondClaim", "user-West", accept=True)[0] == 200
    game = db.room["gameData"]
    assert game["result"]["declarerTricks"] == 8
    assert game["result"]["scoreNS"] == rules.duplicate_score("1NT", 1, 8, False)
    assert game["result"]["settledByClaim"]
    assert game["scoreboard"]["completedBoards"] == 1
    assert game["tricks"] == [] and game["hands"] == original["hands"]
    board = normal("getBoardArchive", boardId=game["boardId"])[1]["board"]
    assert board["claimSettlement"]["allocation"] == {"EW": 5, "NS": 8}
    assert board["tricks"] == [] and board["initialHands"] == original["initialHands"]
    before = copy.deepcopy(db.room)
    assert request("respondClaim", "user-West", accept=True, revision=revision)[0] == 200
    assert db.room == before
    for _ in range(3):
        normal("getGameState")
    assert db.room["gameData"]["scoreboard"]["completedBoards"] == 1


def test_reject_cancel_expiry_resume_exact_position_and_no_reveal(claim_server):
    db, normal, request = claim_server()
    original = copy.deepcopy(db.room["gameData"])
    request("proposeClaim", "user-East", tricks=13)
    assert request("respondClaim", "user-North", accept=False)[0] == 200
    game = db.room["gameData"]
    assert game["claim"]["status"] == "rejected"
    for key in ("hands", "currentTrick", "tricks", "turn", "bids"):
        assert game[key] == original[key]
    assert normal("getGameState")[1]["publicState"]["dummyHand"] is None
    assert request("proposeClaim", "user-East", tricks=0, proposalId="cancel")[0] == 200
    assert request("cancelClaim", "user-East", proposalId="cancel")[0] == 200
    assert db.room["gameData"]["claim"]["status"] == "cancelled"
    assert request("proposeClaim", "user-East", tricks=0, proposalId="expire")[0] == 200
    tick = {"roomId": "room", "revision": db.room["revision"],
            **db.room["gameData"]["pendingAction"]}
    assert runtime.process_due_tick(db, db.send, tick) == tick
    db.now = db.room["gameData"]["claim"]["expiresAt"]
    runtime.process_due_tick(db, db.send, tick)
    assert db.room["gameData"]["claim"]["status"] == "expired"
    assert rules.controller(db.room["gameData"]) == "East"
    assert db.room["gameData"]["hands"] == original["hands"]
    assert runtime.process_due_tick(db, db.send, tick) is None


def test_claim_tampering_authorization_ids_bounds_and_disconnect(claim_server, monkeypatch):
    db, normal, request = claim_server()
    for value in (-1, 14, True, "1", None):
        assert request("proposeClaim", "user-East", tricks=value)[0] == 400
    assert request("proposeClaim", "user-North", tricks=1)[0] == 400
    assert request("proposeClaim", "outsider", tricks=1)[0] == 403
    assert request("proposeClaim", "user-East", tricks=1, boardId="stale")[0] == 400
    assert request("proposeClaim", "user-East", tricks=1, proposalId="../bad")[0] == 400
    assert request("proposeClaim", "user-East", tricks=1, revision=-1)[0] == 409
    assert request("proposeClaim", "user-East", tricks=1)[0] == 200
    assert request("respondClaim", "user-East", accept=True)[0] == 400
    assert request("cancelClaim", "user-North")[0] == 400
    assert request("respondClaim", "user-North", accept=1)[0] == 400
    assert request("respondClaim", "user-North", accept=True, proposalId="fake")[0] == 400
    assert request("respondClaim", "user-North", accept=True)[0] == 200
    assert request("respondClaim", "user-North", accept=False)[0] == 400
    original_records = db.get_user_connection_records
    monkeypatch.setattr(db, "get_user_connection_records",
                        lambda user: [] if user == "user-West" else original_records(user))
    assert normal("getGameState")[0] == 200
    assert db.room["gameData"]["claim"]["status"] == "disconnected"
    assert "result" not in db.room["gameData"]


def test_robots_reject_positive_claim_but_full_concession_works(claim_server):
    db, normal, request = claim_server(("North",))
    # Let the robot opening lead occur, then North controls robot dummy.
    pending = db.room["gameData"]["pendingAction"]
    db.now = pending["dueAt"]
    normal("getGameState")
    game = db.room["gameData"]
    assert rules.controller(game) == "North"
    assert request("proposeClaim", tricks=1)[0] == 400
    assert request("proposeClaim", tricks=0)[0] == 200
    game = db.room["gameData"]
    assert game["claim"]["status"] == "accepted"
    assert game["result"]["declarerTricks"] == 0
    assert game["claimSettlement"]["allocation"] == {"NS": 0, "EW": 13}
    assert len(game["claimSettlement"]["unplayedTrick"]) == 1
    assert normal("getBoardArchive", boardId=game["boardId"])[0] == 200


def test_human_partner_consent_and_stable_trick_hold(claim_server):
    db, normal, request = claim_server()
    request("proposeClaim", "user-East", tricks=0)
    assert request("respondClaim", "user-North", accept=True)[0] == 200
    assert request("respondClaim", "user-South", accept=True)[0] == 200
    assert db.room["state"] == "playing"  # East cannot concede West's tricks without West.
    assert request("respondClaim", "user-West", accept=False)[0] == 200
    for _ in range(4):
        game = db.room["gameData"]
        assert normal("playCard", f"user-{rules.controller(game)}",
                      card=rules.legal_cards(game)[0])[0] == 200
    assert db.room["gameData"]["completedTrick"]
    assert request("proposeClaim", f"user-{db.room['gameData']['turn']}",
                   proposalId="hold", tricks=0)[0] == 400


def test_presence_persistence_closes_pending_claim_on_disconnect(claim_server):
    db, normal, request = claim_server()
    assert request("proposeClaim", "user-East", tricks=0)[0] == 200
    room = copy.deepcopy(db.room)
    # Runtime persistence closes a proposal if presence refresh detects a disconnect.
    room["presence"]["West"] = {"userId": "user-West", "connections": {},
                                 "disconnectedAt": 0, "reservedUntil": 1}
    runtime.save_room(db, room)
    assert db.room["gameData"]["claim"]["status"] == "disconnected"
    assert db.room["gameData"]["hands"] == room["gameData"]["hands"]


def test_suspended_deadline_is_shifted_not_shortened_and_proposals_bounded():
    room = contract_room()
    game = room["gameData"]
    game["pendingAction"] = {"kind": "robotCard", "dueAt": 1700}
    claims.apply(room, "East", "proposeClaim", {
        "boardId": game["boardId"], "proposalId": "clock", "tricks": 1}, 1000)
    claims.apply(room, "North", "respondClaim", {
        "boardId": game["boardId"], "proposalId": "clock", "accept": False}, 9000)
    assert game["pendingAction"] == {"kind": "robotCard", "dueAt": 9700}
    for index in range(1, 16):
        data = {"boardId": game["boardId"], "proposalId": f"p{index}", "tricks": 0}
        claims.apply(room, "East", "proposeClaim", data, 10000)
        claims.apply(room, "East", "cancelClaim", data, 10001)
    with pytest.raises(ValueError, match="16-proposal"):
        claims.apply(room, "East", "proposeClaim",
                     {"boardId": game["boardId"], "proposalId": "p17", "tricks": 0}, 10002)
