"""Board records are derived only from committed, fully cleared boards."""
import copy

import pytest

from lambdas.core.game import agreements, archives, rules, runtime
from test_bridge_lifecycle import server, fixed_deal, room_fixture, call


@pytest.fixture(autouse=True)
def isolated_archive(monkeypatch):
    store = archives.MemoryArchiveStore()
    monkeypatch.setattr(archives, "store", store)
    return store


def passed_out(server):
    db, request = server()
    assert request("startRoom")[0] == 200
    for seat in rules.SEATS:
        assert request("makeBid", f"user-{seat}", bid="pass")[0] == 200
    return db, request


def test_passed_out_archive_and_immutable_versions(server, isolated_archive):
    db, request = passed_out(server)
    game = db.room["gameData"]
    status, payload = request("getBoardArchive", boardId=game["boardId"])
    assert status == 200
    board = payload["board"]
    assert board["initialHands"] == fixed_deal()
    assert board["auction"] == game["bids"] and board["tricks"] == []
    assert board["contract"] is None and board["result"]["passedOut"]
    assert board["agreements"] == agreements.board_agreements()
    assert isolated_archive.put_completed(db.room) == board
    changed = copy.deepcopy(db.room)
    changed["gameData"]["initialHands"]["North"].reverse()
    with pytest.raises(archives.ArchiveConflict):
        isolated_archive.put_completed(changed)
    board["initialHands"]["North"].clear()
    assert len(isolated_archive.get("room", game["boardId"])["initialHands"]["North"]) == 13
    assert request("listBoardArchives")[1]["boards"][0]["boardId"] == game["boardId"]
    assert "initialHands" not in request("listBoardArchives")[1]["boards"][0]


def test_live_board_never_archived_and_no_hidden_agreement_fields(server, isolated_archive):
    db, request = server()
    request("startRoom")
    board_id = db.room["gameData"]["boardId"]
    assert request("getBoardArchive", boardId=board_id)[0] == 409
    assert isolated_archive.get("room", board_id) is None
    assert request("listBoardArchives")[1]["boards"] == []
    status, card = request("getAgreementCard")
    assert status == 200
    assert card["card"]["version"] == agreements.CURRENT_VERSION
    assert "15–17" in card["card"]["supported"][0]["description"]
    assert card["card"]["unsupported"] and card["card"]["deviations"]
    assert "hands" not in str(card) and "initialHands" not in str(card)
    assert request("getAgreementCard", version="future")[0] == 400
    assert request("getAgreementCard", version=[])[0] == 400
    frozen = copy.deepcopy(db.room["gameData"]["agreements"])
    request("makeBid", bid="1NT", agreements={"NS": {"version": "future"}})
    assert db.room["gameData"]["agreements"] == frozen
    assert request("getBoardArchive", "outsider", boardId=board_id)[0] == 403
    assert request("listBoardArchives", "outsider")[0] == 403
    assert request("getAgreementCard", "outsider")[0] == 403


def test_catalog_upgrade_never_changes_board_or_archive_agreement(server, monkeypatch):
    db, request = passed_out(server)
    original = copy.deepcopy(db.room["gameData"]["agreements"])
    board_id = db.room["gameData"]["boardId"]
    future_card = agreements.card()
    future_card["version"] = "test-next-version"
    monkeypatch.setitem(agreements._CARDS, "test-next-version", future_card)
    monkeypatch.setattr(agreements, "CURRENT_VERSION", "test-next-version")
    assert request("getBoardArchive", boardId=board_id)[1]["board"]["agreements"] == original
    assert request("getGameState")[1]["publicState"]["agreements"] == original
    assert request("getAgreementCard", version="sayc-supported-1")[1]["card"]["version"] == "sayc-supported-1"
    assert request("nextBoard", boardId=board_id)[0] == 200
    assert db.room["gameData"]["agreements"]["NS"]["version"] == "test-next-version"
    assert request("getBoardArchive", boardId=board_id)[1]["board"]["agreements"] == original


def test_final_trick_clearance_archive_and_full_replay(server, isolated_archive):
    db, request = server()
    request("startRoom")
    for seat, bid in zip(rules.SEATS, ("1NT", "pass", "pass", "pass")):
        assert request("makeBid", f"user-{seat}", bid=bid)[0] == 200
    while db.room["state"] != "completed":
        game = db.room["gameData"]
        if game.get("completedTrick"):
            if len(game["tricks"]) == 13:
                assert request("getBoardArchive", boardId=game["boardId"])[0] == 409
                assert isolated_archive.get("room", game["boardId"]) is None
            db.now = game["pendingAction"]["dueAt"]
            assert request("getGameState")[0] == 200
        else:
            seat = rules.controller(game)
            assert request("playCard", f"user-{seat}",
                           card=rules.legal_cards(game)[0])[0] == 200
    board = request("getBoardArchive", boardId=db.room["gameData"]["boardId"])[1]["board"]
    replay = room_fixture()
    rules.new_board(replay, board["initialHands"])
    for entry in board["auction"]:
        rules.apply_call(replay, entry["seat"], entry["bid"])
    for trick in board["tricks"]:
        for play in trick["plays"]:
            rules.apply_card(replay, play["seat"], play["card"], timestamp=play["timestamp"])
    assert replay["gameData"]["result"] == board["result"]
    assert replay["gameData"]["tricks"] == board["tricks"]
    assert sum(len(trick["plays"]) for trick in board["tricks"]) == 52


def test_next_board_stale_retry_and_match_no_double_count(server):
    db, request = passed_out(server)
    first_id = db.room["gameData"]["boardId"]
    revision = db.room["revision"]
    scoreboard = request("getMatchScoreboard")[1]["scoreboard"]
    assert scoreboard == {"completedBoards": 1, "scoreNS": 0, "scoreEW": 0,
                          "lastBoardId": first_id}
    assert request("nextBoard")[0] == 400
    assert request("nextBoard", revision=True)[0] == 400
    assert request("nextBoard", revision=revision, boardId=first_id)[0] == 200
    second_id = db.room["gameData"]["boardId"]
    assert second_id != first_id
    assert request("nextBoard", revision=revision, boardId=first_id)[0] == 409
    # Finish another board so a delayed retry could otherwise skip board three.
    for seat in ("East", "South", "West", "North"):
        assert request("makeBid", f"user-{seat}", bid="pass")[0] == 200
    assert request("nextBoard", boardId=first_id)[0] == 409
    assert db.room["gameData"]["boardNumber"] == 2
    for _ in range(3):
        assert request("getGameState")[0] == 200
    assert request("getMatchScoreboard")[1]["scoreboard"]["completedBoards"] == 2
    assert request("getBoardArchive", boardId=first_id)[0] == 200
    assert request("listBoardArchives", limit=1)[1]["nextBeforeBoardNumber"] == 2
    assert request("listBoardArchives", beforeBoardNumber=2)[1]["boards"][0]["boardId"] == first_id


def test_nonzero_cumulative_duplicate_scores_and_idempotent_finish():
    room = room_fixture()
    total = 0
    for number in range(1, 4):
        rules.new_board(room, fixed_deal())
        game = room["gameData"]
        for bid in ("1NT", "pass", "pass", "pass"):
            call(room, bid)
        while room["state"] != "completed":
            rules.apply_card(room, game["turn"], rules.legal_cards(game)[0])
        total += game["result"]["scoreNS"]
        assert game["scores"] == {"NS": total, "EW": -total}
        assert game["scoreboard"]["scoreNS"] == total
        assert game["scoreboard"]["completedBoards"] == number
        before = copy.deepcopy(room)
        rules.finish_board(room)
        assert room == before


def test_archive_authorization_cross_room_embargo_and_input_limits(server, isolated_archive):
    db, request = passed_out(server)
    board_id = db.room["gameData"]["boardId"]
    assert isolated_archive.get("other-room", board_id) is None
    for limit in (0, 101, True, "2"):
        assert request("listBoardArchives", limit=limit)[0] == 400
    assert request("listBoardArchives", beforeBoardNumber=0)[0] == 400
    assert request("getBoardArchive", boardId="other-board")[0] == 404
    db.room["eventId"] = "future-duplicate-event"
    assert request("getBoardArchive", boardId=board_id)[0] == 403
    assert request("listBoardArchives")[1]["boards"] == []


def test_failed_room_cas_does_not_publish_archive(server, isolated_archive):
    db, request = server()
    request("startRoom")
    for seat in rules.SEATS[:3]:
        request("makeBid", f"user-{seat}", bid="pass")
    db.conflict_next = True
    assert request("makeBid", "user-West", bid="pass")[0] == 409
    assert isolated_archive.list("room") == []
    assert db.room["state"] == "bidding"


def test_practice_pace_solo_only_validated_and_pending_not_shortened(server):
    db, request = server(humans=("North",))
    request("startRoom")
    assert request("setPracticePace", practiceMode=True, robotCardDelayMs=100,
                   trickHoldMs=1000, revision=db.room["revision"])[0] == 200
    request("makeBid", bid="1NT")
    game = db.room["gameData"]
    assert game["pendingAction"]["kind"] == "robotCard"
    pending = copy.deepcopy(game["pendingAction"])
    status, snapshot = request("setPracticePace", practiceMode=True,
                               robotCardDelayMs=10000, trickHoldMs=10000)
    assert status == 200
    assert db.room["gameData"]["pendingAction"] == pending
    assert snapshot["publicState"]["practiceMode"] is True
    assert snapshot["publicState"]["pacing"]["robotCardDelayMs"] == 10000
    db.now = pending["dueAt"]
    request("getGameState")
    assert rules.controller(db.room["gameData"]) == "North"
    request("playCard", card=rules.legal_cards(db.room["gameData"])[0])
    assert db.room["gameData"]["pendingAction"]["dueAt"] == db.now + 10000
    for bad in (True, 99, 10001, 1.5, "100"):
        assert request("setPracticePace", practiceMode=True,
                       robotCardDelayMs=bad, trickHoldMs=1000)[0] == 400
    db.room["eventId"] = "event"
    assert request("setPracticePace", practiceMode=True, robotCardDelayMs=100,
                   trickHoldMs=1000)[0] == 403
    db2, request2 = server()
    request2("startRoom")
    assert request2("setPracticePace", practiceMode=True, robotCardDelayMs=100,
                    trickHoldMs=1000)[0] == 403
