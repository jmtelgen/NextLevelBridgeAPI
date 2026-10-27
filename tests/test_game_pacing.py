"""Authoritative clock tests: no sleeps, no AWS, no client-driven catch-up."""
import copy
from unittest.mock import Mock

import pytest

from lambdas.api.game import game_tick
from lambdas.core.game import rules, runtime
from lambdas.core.game.pacing import Pacing
from test_bridge_lifecycle import MemoryDB, contract_room, server  # noqa: F401


def opening(server, humans=("North",)):
    db, request = server(humans)
    assert request("startRoom")[0] == 200
    if humans == ("North",):
        assert request("makeBid", bid="1NT")[0] == 200
    else:
        assert request("makeBid", bid="pass")[0] == 200
    assert db.room["gameData"]["pendingAction"]["kind"] == "robotCard"
    return db, request


def run_tick(db):
    return runtime.process_due_tick(db, db.send, game_tick.tick_for_room(db.room))


def test_card_cannot_play_early_and_exact_deadline_plays_once(server, monkeypatch):
    db, request = opening(server)
    engine = Mock(side_effect=lambda room, seat: rules.legal_cards(room["gameData"])[0])
    monkeypatch.setattr(runtime, "execute_robot_card_play", engine)
    initial = copy.deepcopy(db.room)
    deadline = initial["gameData"]["pendingAction"]["dueAt"]
    assert deadline == db.now + 700
    for user in ("user-North",) * 20:
        assert request("getGameState", user)[0] == 200
        assert db.room == initial
    db.now = deadline - 1
    assert run_tick(db) is not None
    assert request("getGameState")[0] == 200
    assert db.room == initial
    engine.assert_not_called()
    db.now = deadline
    original_tick = game_tick.tick_for_room(db.room)
    assert run_tick(db) is None
    engine.assert_called_once()
    assert len(db.room["gameData"]["currentTrick"]) == 1
    assert db.room["revision"] == initial["revision"] + 1
    after = copy.deepcopy(db.room)
    assert runtime.process_due_tick(db, db.send, original_tick) is None
    for _ in range(10):
        assert request("getGameState")[0] == 200
    assert db.room == after
    engine.assert_called_once()


def test_late_multiclient_polling_cannot_skip_robot_delays(server):
    db, request = opening(server, humans=("West",))
    db.extra_connections["user-West"] = ["second-tab"]
    db.now += 100000
    assert request("getGameState")[0] == 200
    game = db.room["gameData"]
    assert len(game["currentTrick"]) == 1
    assert game["pendingAction"] == {"kind": "robotCard", "dueAt": db.now + 700}
    revision = db.room["revision"]
    for _ in range(30):
        assert request("getGameState")[0] == 200
        assert db.room["revision"] == revision
    db.now += 700
    assert run_tick(db) is None
    assert len(db.room["gameData"]["currentTrick"]) == 2
    assert any(connection == "second-tab" for connection, _ in db.messages)


@pytest.mark.parametrize("human_winner", [False, True])
def test_fourth_card_hold_clear_then_next_lead_timeline(server, human_winner):
    db, request = opening(server)
    game = db.room["gameData"]
    game["hands"] = {
        "East": ["2H", "2C"], "South": ["3H", "3C"],
        "West": ["4H" if human_winner else "AH", "AC"],
        "North": ["AH" if human_winner else "4H", "4C"],
    }
    db.now = game["pendingAction"]["dueAt"]
    run_tick(db)
    assert request("playCard", card="3H")[0] == 200
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    run_tick(db)
    assert request("playCard", card="AH" if human_winner else "4H")[0] == 200
    held = copy.deepcopy(db.room)
    game = held["gameData"]
    assert game["currentTrick"] == []
    assert len(game["completedTrick"]["plays"]) == 4
    assert game["completedTrick"] == game["previousTrick"] == game["tricks"][-1]
    assert game["turn"] == ("North" if human_winner else "West")
    assert rules.legal_cards(game) == []
    assert rules.controller(game) is None
    assert game["pendingAction"] == {"kind": "clearTrick", "dueAt": db.now + 1200}
    assert request("playCard", card="4C")[0] == 400
    assert db.room == held
    db.now += 1199
    for _ in range(10):
        status, snapshot = request("getGameState")
        assert status == 200
        assert snapshot["publicState"]["completedTrick"] is not None
        assert snapshot["publicState"]["serverTimeMs"] == db.now
        assert not snapshot["privateState"]["isMyTurn"]
        assert snapshot["privateState"]["legalCards"] == []
    assert db.room == held
    db.now += 1
    assert request("playCard", card="4C")[0] == 400
    assert db.room == held
    run_tick(db)
    cleared = db.room["gameData"]
    assert cleared["completedTrick"] is None
    assert cleared["currentTrick"] == []
    assert db.room["revision"] == held["revision"] + 1
    assert db.messages[-1][1]["action"] == "trickCleared"
    if human_winner:
        assert cleared["pendingAction"] is None
        assert request("getGameState")[1]["privateState"]["isMyTurn"]
        assert request("playCard", card="4C")[0] == 200
    else:
        assert cleared["pendingAction"] == {"kind": "robotCard", "dueAt": db.now + 700}
        assert request("getGameState")[0] == 200
        assert db.room["gameData"]["currentTrick"] == []
        db.now += 700
        run_tick(db)
    assert len(db.room["gameData"]["currentTrick"]) == 1
    assert db.room["gameData"]["currentTrick"][0]["seat"] == game["turn"]


def test_final_fourth_card_visible_before_scoring_and_result(server):
    db, request = opening(server)
    game = db.room["gameData"]
    trick = {"leader": "East", "winner": "North", "plays": [
        {"seat": seat, "card": rank + "H"} for seat, rank in zip(rules.SEATS, "2345")]}
    game["tricks"] = [copy.deepcopy(trick) for _ in range(12)]
    game["hands"] = {"East": ["2C"], "South": ["3C"], "West": ["4C"], "North": ["AC"]}
    db.now = game["pendingAction"]["dueAt"]
    run_tick(db)
    assert request("playCard", card="3C")[0] == 200
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    run_tick(db)
    assert request("playCard", card="AC")[0] == 200
    assert len(db.room["gameData"]["tricks"]) == 13
    assert db.room["state"] == "playing"
    snapshot = request("getGameState")[1]
    assert snapshot["publicState"]["completedTrick"] is not None
    assert snapshot["publicState"]["result"] is None
    assert snapshot["publicState"]["scores"] == {"NS": 0, "EW": 0}
    assert request("nextBoard")[0] == 400
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    final_tick = game_tick.tick_for_room(db.room)
    run_tick(db)
    result = copy.deepcopy(db.room)
    assert db.room["state"] == "completed"
    assert db.room["gameData"]["completedTrick"] is None
    assert db.room["gameData"]["result"] is not None
    assert db.room["gameData"]["pendingAction"] is None
    runtime.process_due_tick(db, db.send, final_tick)
    assert db.room == result


def test_concurrent_due_snapshots_only_one_commit_and_publish(server):
    db, _ = opening(server)
    first, second = copy.deepcopy(db.room), copy.deepcopy(db.room)
    db.now = first["gameData"]["pendingAction"]["dueAt"]
    db.messages.clear()
    runtime.advance_robots(db, db, db.send, first)
    count = len(db.messages)
    with pytest.raises(runtime.GameRequestError) as error:
        runtime.advance_robots(db, db, db.send, second)
    assert error.value.status == 409
    assert len(db.messages) == count
    assert len(db.room["gameData"]["currentTrick"]) == 1


def test_old_robot_room_acquires_deadline_once_without_playing(server):
    db, request = opening(server)
    del db.room["gameData"]["pendingAction"]
    initial_revision = db.room["revision"]
    assert request("getGameState")[0] == 200
    assert db.room["revision"] == initial_revision + 1
    assert db.room["gameData"]["currentTrick"] == []
    planned = copy.deepcopy(db.room)
    db.now += 1
    request("getGameState")
    assert db.room == planned


@pytest.mark.parametrize("name,value", [
    ("ROBOT_CARD_DELAY_MS", "0"), ("ROBOT_CARD_DELAY_MS", "99"),
    ("ROBOT_CARD_DELAY_MS", "-1"), ("ROBOT_CARD_DELAY_MS", "nan"),
    ("ROBOT_CARD_DELAY_MS", "700.0"), ("ROBOT_CARD_DELAY_MS", "10001"),
    ("ROBOT_CARD_DELAY_MS", ""), ("ROBOT_CARD_DELAY_MS", " 700"),
    ("TRICK_HOLD_MS", "999"), ("TRICK_HOLD_MS", "10001"),
    ("TRICK_HOLD_MS", "1200.5"), ("TRICK_HOLD_MS", "１２３４"),
])
def test_invalid_pacing_fails_before_mutation(server, monkeypatch, name, value):
    db, request = server()
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        Pacing.from_environment()
    before = copy.deepcopy(db.room)
    status, _ = request("startRoom")
    assert status == 503
    assert db.room == before
    assert not db.saved


def test_configured_delays_are_persisted_and_dummy_control_stays_human(server, monkeypatch):
    monkeypatch.setenv("ROBOT_CARD_DELAY_MS", "800")
    monkeypatch.setenv("TRICK_HOLD_MS", "1400")
    db, request = opening(server)
    assert db.room["gameData"]["pendingAction"]["dueAt"] == db.now + 800
    db.now += 800
    run_tick(db)
    game = db.room["gameData"]
    assert game["turn"] == "South"
    assert game["pendingAction"] is None
    assert not game["robotPending"]
    snapshot = request("getGameState")[1]
    assert snapshot["privateState"]["isMyTurn"]
    assert snapshot["privateState"]["playSeat"] == "South"
    assert snapshot["publicState"]["pacing"] == {"robotCardDelayMs": 800, "trickHoldMs": 1400}


def test_budget_stop_has_durable_continuation_and_no_busy_loop(server):
    db, request = opening(server)
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    tick = game_tick.tick_for_room(db.room)
    context = Mock(get_remaining_time_in_millis=lambda: 1000)
    before = copy.deepcopy(db.room)
    assert runtime.process_due_tick(db, db.send, tick, context) == tick
    assert db.room == before
    assert run_tick(db) is None


def test_robot_engine_exception_falls_back_only_when_due(server, monkeypatch):
    db, request = opening(server)
    engine = Mock(side_effect=RuntimeError("engine unavailable"))
    monkeypatch.setattr(runtime, "execute_robot_card_play", engine)
    expected = rules.legal_cards(db.room["gameData"])[0]
    assert request("getGameState")[0] == 200
    engine.assert_not_called()
    db.now = db.room["gameData"]["pendingAction"]["dueAt"]
    run_tick(db)
    engine.assert_called_once()
    assert db.room["gameData"]["currentTrick"][0]["card"] == expected
