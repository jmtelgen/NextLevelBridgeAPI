from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from lambdas.core.game import rules
from lambdas.core.robot import fair_play as ai
from lambdas.core.robot import level_policy as levels
from lambdas.core.robot import practice
from scripts import benchmark_computer_levels as benchmark


class ZeroSolver:
    def solve_board(self, **kwargs):
        return [("S2", 0)]


def solo_room(human="East"):
    room = {"roomId": "room", "ownerId": "human", "revision": 7,
            "computerLevel": "heuristic", "state": "playing",
            "seats": {seat: "human" if seat == human else "ROBOT_" + seat for seat in ai.SEATS},
            "gameData": {"currentPhase": "playing", "turn": "East",
                         "declarer": "North", "dummy": "South", "contract": "3NT",
                         "currentTrick": [], "tricks": [], "bids": [],
                         "hands": {seat: [rank + suit for rank in ai.RANKS]
                                   for seat, suit in zip(ai.SEATS, ai.SUITS)}}}
    return room


@pytest.mark.parametrize("name,samples,budget", [
    ("heuristic", 0, 0), ("standard", 4, 50), ("thoughtful", 8, 100),
])
def test_exact_named_policy_budgets(name, samples, budget, monkeypatch):
    policy = levels.level_policy(name)
    assert (policy.samples, policy.budget_ms) == (samples, budget)
    state = ai.observe(solo_room(), "East")
    selected = Mock(return_value=ai.Decision("2H", "sampled_dds", samples))
    monkeypatch.setattr(ai, "choose_card", selected)
    decision = levels.choose(state, name, seed=9)
    assert decision.card in ai.legal_cards(state.hand, state.trick)
    if samples:
        config = selected.call_args.args[1]
        assert (config.seed, config.samples, config.budget_ms) == (9, samples, budget)
    else:
        selected.assert_not_called()


@pytest.mark.parametrize("invalid", [None, True, 1, {}, [], "expert", "Standard", "", "standard "])
def test_invalid_level_is_not_a_fallback(invalid):
    with pytest.raises(ValueError):
        levels.room_level({"computerLevel": invalid})
    assert levels.room_level({}).name == "standard"


@pytest.mark.parametrize("invalid", [True, -1, 1.5, "0", 2**32])
def test_invalid_seed_is_not_a_fallback(invalid):
    with pytest.raises(ValueError):
        levels.choose(ai.observe(solo_room(), "East"), "standard", seed=invalid)


def test_corrupt_persisted_level_cannot_enter_runtime_fallback():
    from lambdas.core.game import runtime
    room = solo_room()
    room["computerLevel"] = "expert"
    before = deepcopy(room)
    db, table, send = Mock(), Mock(), Mock()
    with pytest.raises(ValueError, match="computerLevel"):
        runtime.advance_robots(db, table, send, room)
    assert room == before
    table.put_item.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("name", list(levels.LEVELS))
def test_each_level_ignores_actual_hidden_world(name):
    first = solo_room()
    second = deepcopy(first)
    second["gameData"]["hands"]["North"] = ["ZZ"]
    second["gameData"]["hands"]["South"] = []
    a, b = ai.observe(first, "East"), ai.observe(second, "East")
    assert a == b
    assert levels.choose(a, name, solver_factory=ZeroSolver) == levels.choose(b, name, solver_factory=ZeroSolver)


def test_hint_reads_only_lawful_hand_and_never_returns_hidden_hands():
    room = solo_room()

    class Guard(dict):
        def get(self, seat, default=None):
            assert seat == "East", "Hint inspected a hidden hand"
            return super().get(seat, default)

    room["gameData"]["hands"] = Guard(room["gameData"]["hands"])
    hint = practice.practice_hint(room, "human")
    assert hint["legalActions"] == ai.legal_cards(room["gameData"]["hands"]["East"], [])
    assert hint["suggestion"]["mode"] == "heuristic"
    assert not {"hands", "deal", "par", "samples"} & set(hint)


def test_hint_without_suggestion_does_not_compute(monkeypatch):
    compute = Mock(side_effect=AssertionError("No analysis requested"))
    monkeypatch.setattr(practice, "_cached_decision", compute)
    assert practice.practice_hint(solo_room(), "human", suggest=False)["suggestion"] is None


@pytest.mark.parametrize("change", [
    lambda room: room["seats"].update(South="second-human"),
    lambda room: room["seats"].update(South=None),
    lambda room: room.update(eventId="event"),
    lambda room: room.update(mode="ranked"),
    lambda room: room["gameData"].update(competitive=True),
])
def test_solo_competitive_and_membership_enforcement(change):
    room = solo_room()
    change(room)
    with pytest.raises(practice.PracticeDenied):
        practice.practice_hint(room, "human")


def test_actor_and_declarer_dummy_control():
    room = solo_room("North")
    with pytest.raises(practice.PracticeDenied):
        practice.practice_hint(room, "human")
    rules.apply_card(room, "East", "2H")
    hint = practice.practice_hint(room, "human", suggest=False)
    assert (hint["actor"], hint["controller"]) == ("South", "North")
    assert "void in H" in hint["explanation"]
    room["gameData"]["completedTrick"] = {"plays": []}
    with pytest.raises(practice.PracticeDenied):
        practice.practice_hint(room, "human")


def test_inconsistent_dummy_metadata_cannot_expose_an_opponents_hand():
    room = solo_room("North")
    room["gameData"]["dummy"] = "East"
    with pytest.raises(practice.PracticeDenied, match="control metadata"):
        practice.practice_hint(room, "human")


def test_follow_suit_and_bidding_visible_hcp_shape():
    room = solo_room()
    room["gameData"]["hands"]["East"] = ["2H", "AH", "AS"]
    room["gameData"]["currentTrick"] = [{"seat": "North", "card": "KH"}]
    hint = practice.practice_hint(room, "human", suggest=False)
    assert hint["legalActions"] == ["2H", "AH"]
    assert "must follow H" in hint["explanation"]
    room = solo_room()
    room["gameData"]["currentPhase"] = "bidding"
    hint = practice.practice_hint(room, "human")
    assert hint["handHcp"] == 10 and hint["shape"] == {"S": 0, "H": 13, "D": 0, "C": 0}
    assert hint["legalActions"] == rules.legal_calls(room["gameData"], "East")
    assert hint["suggestion"] is None


def test_bounded_cache_and_honest_degraded_analysis(monkeypatch):
    practice._cached_decision.cache_clear()
    selected = Mock(return_value=ai.Decision("2H", "heuristic", 0, "SECRET hidden allocation"))
    monkeypatch.setattr(practice, "choose", selected)
    first = practice.practice_hint(solo_room(), "human")
    assert first == practice.practice_hint(solo_room(), "human")
    selected.assert_called_once()
    assert first["suggestion"]["degraded"] is True
    assert "SECRET" not in json.dumps(first)
    assert practice._cached_decision.cache_info().maxsize == 128
    practice._cached_decision.cache_clear()


def test_level_benchmark_smoke_and_validation():
    report = benchmark.run_benchmark(pairs=3, seed=19, solver_factory=ZeroSolver)
    assert report["pairedBoards"] == 3
    assert len(report["comparisons"]) == 3
    assert all(leg["actions"] == 52 for pair in report["pairs"] for leg in pair["legs"])
    assert report["biddingStrengthChanged"] is report["expertStrengthProven"] is False
    assert all(policy["illegal_actions"] == 0 for policy in report["policies"].values())
    for invalid in [True, 0, 65]:
        with pytest.raises(ValueError):
            benchmark.run_benchmark(pairs=invalid)
