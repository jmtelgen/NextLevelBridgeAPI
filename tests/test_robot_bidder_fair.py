from copy import deepcopy
from unittest.mock import Mock

import pytest

from lambdas.core.robot.robot_bidder import RobotBidder


def bidder_with_call(proposed):
    bidder = RobotBidder.__new__(RobotBidder)
    bidder.use_sayc = True
    bidder.sayc_bidding = object()
    bidder._make_sayc_bid = Mock(return_value=proposed)
    bidder.advanced_engine = Mock()
    return bidder


def auction(bids=None):
    return {
        "seats": {"East": "ROBOT_East"},
        "gameData": {
            "currentPhase": "bidding", "turn": "East", "dealer": "North",
            "bids": bids or [],
            "hands": {"East": ["AH", "KH", "QH", "JH", "TH", "9H", "8H",
                               "7H", "6H", "5H", "4H", "3H", "2H"]},
        },
    }


@pytest.mark.parametrize("proposed,expected", [
    ("1N", "1NT"), ("1NT", "1NT"), ("PASS", "pass"), ("7NT", "7NT"),
    ("garbage", "pass"), ("double", "pass"), ("redouble", "pass"),
])
def test_live_sayc_call_is_normalized_and_legal(proposed, expected):
    bidder = bidder_with_call(proposed)
    data = auction()
    before = deepcopy(data)
    assert bidder.make_bid(data, "East") == expected
    assert data == before
    bidder.advanced_engine.make_bid.assert_not_called()


def test_live_bid_does_not_underbid_or_double_partner(caplog):
    data = auction([{"seat": "West", "bid": "2S"}])
    for proposed in ("1H", "2H", "double"):
        assert bidder_with_call(proposed).make_bid(data, "East") == "pass"
    assert "illegal_sayc_call" in caplog.text


def test_legal_double_redouble():
    data = auction([{"seat": "North", "bid": "2S"}])
    assert bidder_with_call("X").make_bid(data, "East") == "double"
    data = auction([{"seat": "West", "bid": "2S"}, {"seat": "North", "bid": "double"}])
    assert bidder_with_call("XX").make_bid(data, "East") == "redouble"


def test_bidding_never_reads_concealed_hands_and_preserves_own_cards():
    data = auction()

    class ProtectedHands(dict):
        def get(self, seat, default=None):
            assert seat == "East", "bidder inspected a concealed hand"
            return super().get(seat, default)

    data["gameData"]["hands"] = ProtectedHands(data["gameData"]["hands"])
    bidder = bidder_with_call("1H")
    assert bidder.make_bid(data, "East") == "1H"
    assert bidder._make_sayc_bid.call_args.args[0] == data["gameData"]["hands"]["East"]


def test_live_fallback_never_invokes_advanced_or_par_engine():
    bidder = bidder_with_call("1H")
    bidder.use_sayc = False
    bidder.use_advanced = True
    bidder._make_basic_bid = Mock(return_value="pass")
    assert bidder.make_bid(auction(), "East") == "pass"
    bidder.advanced_engine.make_bid.assert_not_called()


def test_real_rule_based_sayc_bid_is_legal():
    from lambdas.core.game.rules import legal_calls
    data = auction()
    selected = RobotBidder().make_bid(data, "East")
    assert selected in legal_calls(data["gameData"], "East")
