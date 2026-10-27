"""Explicit supported NT agreements; no perfect-information bidding oracle."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from lambdas.core.bidding.sayc_bidding import Bid, BiddingContext, SAYCBidding
from lambdas.core.game.rules import legal_calls
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis, HandEvaluator
from lambdas.core.robot.robot_bidder import RobotBidder


def analysis(hcp, lengths=(4, 3, 3, 3)):
    suits = dict(zip("CDHS", lengths))
    distribution = sum(3 - length for length in lengths if length <= 2)
    return HandAnalysis(
        hcp=hcp, distribution_points=distribution, total_points=hcp + distribution,
        longest_suit=max(suits, key=suits.get), longest_suit_length=max(lengths),
        suit_lengths=suits, balanced=sorted(lengths) in ([3, 3, 3, 4], [2, 3, 4, 4], [2, 3, 3, 5]),
        stoppers=dict.fromkeys("CDHS", False), controls=0,
    )


def context(values, opening=None):
    bids = ([Bid("North", opening, 1), Bid("East", "pass", 2)] if opening else [])
    return BiddingContext("South" if opening else "North", "North", "None", bids, values)


@pytest.mark.parametrize("hcp,expected", [
    (11, "pass"), (12, "1C"), (14, "1C"), (15, "1NT"), (17, "1NT"),
    (18, "1C"), (19, "1C"), (20, "2NT"), (21, "2NT"), (22, "2C"),
    (24, "2C"), (25, "3NT"), (27, "3NT"), (28, "2C"),
])
@pytest.mark.parametrize("lengths", [(4, 3, 3, 3), (4, 4, 3, 2), (5, 3, 3, 2)])
def test_balanced_nt_opening_hcp_boundaries(hcp, expected, lengths):
    if lengths == (4, 4, 3, 2) and expected == "1C":
        expected = "1D"
    assert SAYCBidding()._make_opening_bid(context(analysis(hcp, lengths))) == expected


@pytest.mark.parametrize("hcp,lengths,expected", [
    (15, (3, 3, 5, 2), "1H"), (17, (3, 3, 2, 5), "1S"),
    (20, (3, 3, 5, 2), "1H"), (21, (3, 3, 2, 5), "1S"),
    (25, (3, 3, 5, 2), "3NT"),  # Existing high-NT agreement allows a five-card major.
    (15, (5, 4, 2, 2), "1C"), (20, (5, 4, 2, 2), "2C"),
    (21, (5, 4, 2, 2), "2C"), (25, (5, 4, 2, 2), "2C"),
])
def test_existing_shape_agreements_not_silently_changed(hcp, lengths, expected):
    assert SAYCBidding()._make_opening_bid(context(analysis(hcp, lengths))) == expected


@pytest.mark.parametrize("opening,hcp,expected", [
    ("1NT", 0, "pass"), ("1NT", 7, "pass"), ("1NT", 8, "2NT"), ("1NT", 9, "2NT"),
    ("1NT", 10, "3NT"), ("1NT", 14, "3NT"), ("1NT", 15, "3NT"),
    ("1NT", 16, "4NT"), ("1NT", 17, "4NT"),
    ("2NT", 0, "pass"), ("2NT", 3, "pass"), ("2NT", 4, "3NT"),
    ("2NT", 10, "3NT"), ("2NT", 11, "4NT"), ("2NT", 12, "4NT"),
])
@pytest.mark.parametrize("lengths", [(4, 3, 3, 3), (4, 4, 3, 2)])
def test_natural_balanced_nt_response_boundaries(opening, hcp, expected, lengths):
    assert SAYCBidding()._make_response_bid(context(analysis(hcp, lengths), opening)) == expected


@pytest.mark.parametrize("opening,lengths,expected", [
    ("1NT", (3, 2, 4, 4), "2C"), ("1NT", (3, 3, 5, 2), "2D"),
    ("1NT", (3, 3, 2, 5), "2H"), ("1NT", (5, 3, 3, 2), "2S"),
    ("2NT", (3, 2, 4, 4), "3C"),
])
def test_natural_response_does_not_override_existing_conventions(opening, lengths, expected):
    assert SAYCBidding()._make_response_bid(context(analysis(8, lengths), opening)) == expected


@pytest.mark.parametrize("hand,hcp,expected", [
    (["AS", "KS", "QS", "2S", "AH", "KH", "2H", "KD", "3D", "2D", "JC", "3C", "2C"], 20, "2NT"),
    (["AS", "KS", "QS", "2S", "AH", "KH", "2H", "KD", "3D", "2D", "QC", "3C", "2C"], 21, "2NT"),
    (["AS", "KS", "QS", "JS", "AH", "KH", "QH", "KD", "QD", "2D", "JC", "3C", "2C"], 25, "3NT"),
])
def test_valid_thirteen_card_openings_end_to_end(hand, hcp, expected):
    assert len(hand) == len(set(hand)) == 13
    values = HandEvaluator().evaluate_hand(hand)
    assert values.hcp == hcp and values.balanced
    assert SAYCBidding().make_bid(hand, context(values)) == expected


@pytest.mark.parametrize("opening,hand,expected", [
    ("1NT", ["AC", "JC", "3C", "2C", "KH", "3H", "2H", "3S", "4S", "2S", "3D", "4D", "2D"], "2NT"),
    ("1NT", ["AC", "KC", "3C", "2C", "KH", "3H", "2H", "3S", "4S", "2S", "3D", "4D", "2D"], "3NT"),
    ("2NT", ["AC", "4C", "3C", "2C", "4H", "3H", "2H", "3S", "4S", "2S", "3D", "4D", "2D"], "3NT"),
])
def test_live_natural_response_is_legal_own_hand_only_and_never_dds(opening, hand, expected):
    class OwnHandOnly(dict):
        def get(self, seat, default=None):
            assert seat == "South", "SAYC response inspected a concealed hand"
            return super().get(seat, default)

    bidder = RobotBidder()
    bidder.advanced_engine = Mock()
    bidder.advanced_engine.make_bid.side_effect = AssertionError("A live bid must not consult a par/DDS engine")
    room = {"gameData": {
        "currentPhase": "bidding", "turn": "South", "dealer": "North",
        "bids": [{"seat": "North", "bid": opening}, {"seat": "East", "bid": "pass"}],
        "hands": OwnHandOnly({"South": hand}),
    }}
    before = deepcopy(room)
    assert bidder.make_bid(room, "South") == expected
    assert expected in legal_calls(room["gameData"], "South")
    assert room == before
    bidder.advanced_engine.make_bid.assert_not_called()
