"""Fairness, constraint, native-adapter and runtime contract regressions."""

from copy import deepcopy
from dataclasses import replace
import random
from unittest.mock import Mock

import pytest

from lambdas.core.robot import fair_play as ai
from lambdas.core.robot.robot_utils import (
    _get_available_cards, _get_card_rank, execute_robot_card_play,
    get_robot_turns_sequence,
)


def room():
    return {
        "seats": {seat: "ROBOT_" + seat for seat in ai.SEATS},
        "gameData": {
            "currentPhase": "playing", "turn": "East", "declarer": "North",
            "contract": "3NT", "currentTrick": [], "tricks": [],
            "hands": {seat: [value + suit for value in ai.RANKS]
                      for seat, suit in zip(ai.SEATS, ai.SUITS)},
        },
    }


def play(data, seat, value):
    game = data["gameData"]
    game["hands"][seat].remove(value)
    game["currentTrick"].append({"seat": seat, "card": value})
    game["turn"] = ai.next_seat(seat)
    if len(game["currentTrick"]) == 4:
        plays = game["currentTrick"]
        winner = ai.trick_winner(plays, ai._trump(game))
        game["tricks"].append({"leader": plays[0]["seat"], "plays": plays, "winner": winner})
        game["currentTrick"] = []
        game["turn"] = winner


class ContinuationSolver:
    def __init__(self, score=0):
        self.score = score
        self.calls = []

    def solve_board(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return [("S2", self.score)]


@pytest.mark.parametrize("value,expected", [
    ("AS", "AS"), ("SA", "AS"), ("10H", "TH"), ("H10", "TH"), (" cq ", "QC"),
])
def test_card_normalization(value, expected):
    assert ai.card(value) == expected


@pytest.mark.parametrize("value", ["", "1S", "ZZ", "ASX"])
def test_bad_card_rejected(value):
    with pytest.raises(ValueError):
        ai.card(value)


def test_follow_suit_and_rank_are_not_reversed():
    assert _get_available_cards(["AS", "2S", "KH"], [{"card": "TS"}]) == ["AS", "2S"]
    assert _get_available_cards(["SA", "S2", "HK"], [{"card": "ST"}]) == ["SA", "S2"]
    assert _get_card_rank("AS") == _get_card_rank("SA") == 14
    assert ai.legal_cards(["2H", "AC"], [{"card": "AS"}]) == ["2H", "AC"]


def test_opening_projection_never_reads_dummy_or_opponents():
    data = room()

    class ProtectedHands(dict):
        def get(self, seat, default=None):
            assert seat == "East", "concealed hand was read"
            return super().get(seat, default)

    data["gameData"]["hands"] = ProtectedHands(data["gameData"]["hands"])
    data["gameData"]["dummyRevealed"] = True  # Not sufficient without a public lead.
    state = ai.observe(data, "East")
    assert list(dict(state.known)) == ["East"]
    assert sum(dict(state.counts).values()) == 52


def test_dummy_projection_knows_controller_and_dummy_only_after_lead():
    data = room()
    with pytest.raises(ValueError, match="opening lead"):
        ai.observe(data, "South")
    play(data, "East", "2H")
    state = ai.observe(data, "South")
    assert state.controller == "North"
    assert set(dict(state.known)) == {"North", "South"}
    assert state.hand == tuple(sorted(data["gameData"]["hands"]["South"]))


def test_opening_leader_is_left_of_declarer():
    with pytest.raises(ValueError, match="opening leader"):
        ai.observe(room(), "North")
    assert ai.observe(room(), "East").leader == "East"


@pytest.mark.parametrize("after_lead", [False, True])
def test_no_peeking_same_visible_state_seed_same_samples_and_action(after_lead):
    left = room()
    if after_lead:
        play(left, "East", "2H")
        play(left, "South", "2D")
        actor, hidden = "West", ("North", "East")
    else:
        actor, hidden = "East", ("North", "South")
    right = deepcopy(left)
    hands = right["gameData"]["hands"]
    # Concealed lengths and contents may even be corrupt; neither is an input.
    hands[hidden[0]], hands[hidden[1]] = ["ZZ"], []
    a, b = ai.observe(left, actor), ai.observe(right, actor)
    assert a == b
    assert ai.sample_deal(a, random.Random(97)) == ai.sample_deal(b, random.Random(97))
    config = ai.PlayConfig(seed=97, samples=3, budget_ms=0)
    assert ai.choose_card(a, config, ContinuationSolver) == ai.choose_card(b, config, ContinuationSolver)


def test_samples_conserve_deck_counts_known_hands_and_voids():
    data = room()
    play(data, "East", "2H")
    play(data, "South", "2D")
    play(data, "West", "2C")
    state = ai.observe(data, "North")
    assert "H" in dict(state.voids)["South"]
    assert "H" in dict(state.voids)["West"]
    for seed in range(30):
        deal = ai.sample_deal(state, random.Random(seed))
        all_cards = list(state.played) + [value for values in deal.values() for value in values]
        assert len(all_cards) == len(set(all_cards)) == 52
        assert set(all_cards) == set(ai.DECK)
        for seat in ai.SEATS:
            assert len(deal[seat]) == dict(state.counts)[seat]
            assert all(value[1] not in dict(state.voids)[seat] for value in deal[seat])
        for seat, known in state.known:
            assert deal[seat] == sorted(known)


def test_impossible_constraints_terminate_with_explicit_error():
    state = ai.observe(room(), "East")
    impossible = replace(state, voids=tuple((seat, tuple(ai.SUITS)) for seat in ai.SEATS))
    with pytest.raises(ValueError, match="contradicts"):
        ai.sample_deal(impossible, random.Random(0))
    impossible = replace(state, voids=(("North", tuple(ai.SUITS)), ("East", ()),
                                      ("South", tuple(ai.SUITS)), ("West", tuple(ai.SUITS))))
    with pytest.raises(ValueError, match="No hidden allocation"):
        ai.sample_deal(impossible, random.Random(0))


def test_duplicate_known_public_card_rejected():
    data = room()
    play(data, "East", "2H")
    data["gameData"]["hands"]["North"][0] = "2H"
    with pytest.raises(ValueError, match="overlap"):
        ai.sample_deal(ai.observe(data, "South"), random.Random(0))


@pytest.mark.parametrize("length", [0, 1, 2])
def test_partial_trick_passes_actual_leader_and_inverts_next_side(length):
    data = room()
    for seat, value in [("East", "2H"), ("South", "2D")][:length]:
        play(data, seat, value)
    actor = ("East", "South", "West")[length]
    state = ai.observe(data, actor)
    deal = ai.sample_deal(state, random.Random(8))
    solver = ContinuationSolver(score=3)
    candidate = ai.legal_cards(state.hand, state.trick)[0]
    # The next player always belongs to the opposite partnership on a partial trick.
    assert ai.evaluate_candidate(solver, state, deal, candidate) == 10
    call = solver.calls[0]
    assert call["first"] == "E"
    assert len(call["current_trick"]) == length + 1
    assert call["current_trick"][-1] == candidate[::-1]
    assert candidate[::-1] not in call["hands"][actor[0]]
    assert (call["target"], call["solutions"], call["mode"]) == (-1, 1, 1)


def test_fourth_card_resolves_trick_and_leads_from_winner():
    data = room()
    for seat, value in [("East", "2H"), ("South", "2D"), ("West", "2C")]:
        play(data, seat, value)
    state = ai.observe(data, "North")
    solver = ContinuationSolver(score=3)
    deal = ai.sample_deal(state, random.Random(5))
    # East won: next side is opponent; twelve tricks remain, current trick lost.
    assert ai.evaluate_candidate(solver, state, deal, "2S") == 9
    assert solver.calls[0]["first"] == "E"
    assert solver.calls[0]["current_trick"] == []


def test_completed_trick_winner_may_be_actor_partner():
    data = room()
    data["gameData"]["contract"] = "4S"
    for seat, value in [("East", "2H"), ("South", "2D"), ("West", "2C")]:
        play(data, seat, value)
    state = ai.observe(data, "North")
    solver = ContinuationSolver(score=3)
    assert ai.evaluate_candidate(solver, state, ai.sample_deal(state, random.Random(5)), "AS") == 4
    assert solver.calls[0]["first"] == "N"


def test_all_candidates_share_identical_sampled_worlds(monkeypatch):
    state = ai.observe(room(), "East")
    batches = []

    def evaluate(solver, observation, deal, candidate):
        batches.append((candidate, deepcopy(deal)))
        return ai.rank(candidate) % 3

    monkeypatch.setattr(ai, "evaluate_candidate", evaluate)
    decision = ai.choose_card(state, ai.PlayConfig(seed=5, samples=3, budget_ms=0), ContinuationSolver)
    size = len(state.hand)
    assert decision.samples == 3
    for index in range(3):
        batch = batches[index * size:(index + 1) * size]
        assert len({candidate for candidate, _ in batch}) == size
        assert all(deal == batch[0][1] for _, deal in batch)


def test_dds_unavailable_is_logged_deterministic_legal_fallback(caplog):
    state = ai.observe(room(), "East")
    unavailable = Mock(side_effect=RuntimeError("native library unavailable"))
    decision = ai.choose_card(state, solver_factory=unavailable)
    assert decision.mode == "heuristic"
    assert decision.card == ai.heuristic(state)
    assert decision.card in ai.legal_cards(state.hand, state.trick)
    assert "robot_play_degraded" in caplog.text
    assert "native library unavailable" in caplog.text


def test_budget_drops_incomplete_candidate_batch(caplog):
    state = ai.observe(room(), "East")
    ticks = iter([0, 0, 0, 1])
    decision = ai.choose_card(
        state, ai.PlayConfig(samples=3, budget_ms=1),
        ContinuationSolver, clock=lambda: next(ticks),
    )
    assert decision.mode == "heuristic"
    assert decision.samples == 0
    assert decision.reason == "budget_exhausted"
    assert "budget_exhausted" in caplog.text


def test_fallback_does_not_overtake_partner_and_uses_cheapest_winner():
    data = room()
    for seat, value in [("East", "2H"), ("South", "2D")]:
        play(data, seat, value)
    state = ai.observe(data, "West")
    assert ai.heuristic(state) == "2C"  # Partner East is winning.
    state = replace(state, actor="West", known=(("West", ("3H", "AH", "2C")),),
                    current=(("North", "2H"), ("East", "4H"), ("South", "5H")))
    assert ai.heuristic(state) == "AH"  # Follow suit, beat opponent South.


def test_selector_preserves_storage_spelling_without_mutating(monkeypatch):
    data = room()
    data["gameData"]["hands"]["East"] = [value[::-1] for value in data["gameData"]["hands"]["East"]]
    before = deepcopy(data)
    monkeypatch.setattr(ai, "choose_card", lambda state, config: ai.Decision("AH", "heuristic", 0))
    assert execute_robot_card_play(data, "East") == "HA"
    assert data == before


def test_robot_compatibility_helper_only_returns_actual_turn_and_controller():
    data = room()
    data["gameData"]["turn"] = "West"
    assert get_robot_turns_sequence(data, "North") == [("West", "play")]
    data["gameData"]["turn"] = "South"
    data["seats"]["North"] = "human-declarer"
    assert get_robot_turns_sequence(data, "East") == []
    data["seats"]["North"] = "ROBOT_North"
    data["seats"]["South"] = "human-dummy"
    assert get_robot_turns_sequence(data, "East") == [("South", "play")]
    data["gameData"]["currentPhase"] = "finished"
    assert get_robot_turns_sequence(data, "East") == []


@pytest.mark.integration
def test_native_dds_known_answer_partial_leader_and_side():
    try:
        solver = ai.default_solver()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    # One trick remains; East's ace of hearts wins unless North can trump.
    hands = {"North": ["2S"], "East": ["AH"], "South": ["2D"], "West": ["2C"]}
    state = ai.Observation(
        actor="South", controller="North", known=(), played=(),
        current=(("East", "AH"),), counts=(), voids=(), leader="East", trump="N",
    )
    hands["East"] = []
    assert ai.evaluate_candidate(solver, state, hands, "2D") == 0
    state = replace(state, trump="S")
    assert ai.evaluate_candidate(solver, state, hands, "2D") == 1
    # Fourth card completes the final trick; no zero-card DDS call is made.
    state = replace(state, actor="North", current=(("East", "AH"), ("South", "2D"), ("West", "2C")))
    assert ai.evaluate_candidate(solver, state, {"North": ["2S"], "East": [], "South": [], "West": []}, "2S") == 1


@pytest.mark.integration
def test_complete_deal_fallback_is_legal_and_conserves_all_52_cards():
    data = room()
    unavailable = Mock(side_effect=RuntimeError("intentional fallback exercise"))
    actions = 0
    while len(data["gameData"]["tricks"]) < 13:
        actor = data["gameData"]["turn"]
        state = ai.observe(data, actor)
        decision = ai.choose_card(state, solver_factory=unavailable)
        assert decision.card in ai.legal_cards(state.hand, state.trick)
        play(data, actor, decision.card)
        actions += 1
    assert actions == 52
    assert not any(data["gameData"]["hands"].values())
    assert len({entry["card"] for trick in data["gameData"]["tricks"] for entry in trick["plays"]}) == 52


@pytest.mark.integration
def test_native_sampled_full_deal_with_authoritative_rules():
    from lambdas.core.game.rules import apply_card, legal_cards
    try:
        ai.default_solver()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    data = room()
    deck = list(ai.DECK)
    random.Random(17).shuffle(deck)
    data["gameData"]["hands"] = {seat: deck[index * 13:(index + 1) * 13]
                                 for index, seat in enumerate(ai.SEATS)}
    modes = []
    while data["gameData"]["currentPhase"] == "playing":
        game = data["gameData"]
        actor = game["turn"]
        decision = ai.choose_card(ai.observe(data, actor), ai.PlayConfig(seed=17, samples=1, budget_ms=0))
        assert decision.card in legal_cards(game, actor)
        assert decision.mode in ("sampled_dds", "forced")
        modes.append(decision.mode)
        apply_card(data, actor, decision.card)
    assert len(modes) == 52
    assert "sampled_dds" in modes
    assert len(data["gameData"]["tricks"]) == 13
    assert not any(data["gameData"]["hands"].values())
