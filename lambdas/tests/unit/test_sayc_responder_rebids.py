"""
Test suite for SAYC responder rebids after major suit openings.
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYCResponderRebids(unittest.TestCase):
    """Test responder rebids after 1H/1S opening and opener's rebid."""
    
    def setUp(self):
        self.bidding = SAYCBidding()
    
    def test_after_1nt_rebid_game_force_new_suit(self):
        """Test responder game forces with new suit after 1NT rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="1NT", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=13,
                distribution_points=0,
                total_points=13,
                longest_suit="D",
                longest_suit_length=5,
                suit_lengths={'C': 2, 'D': 5, 'H': 3, 'S': 3},  # 5 diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3D")
    
    def test_after_1nt_rebid_invitational_raise(self):
        """Test responder invites game with raise after 1NT rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="1NT", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 2, 'D': 3, 'H': 5, 'S': 3},  # 5 hearts
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3H")
    
    def test_after_1nt_rebid_signoff_game(self):
        """Test responder signs off in game after 1NT rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="1NT", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3NT")
    
    def test_after_1nt_rebid_nonforcing_new_suit(self):
        """Test responder non-forcing new suit after 1NT rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="1NT", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="C",
                longest_suit_length=5,
                suit_lengths={'C': 5, 'D': 3, 'H': 3, 'S': 2},  # 5 clubs
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "2C")
    
    def test_after_suit_rebid_signoff_partscore(self):
        """Test responder signs off in partscore after suit rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="2C", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 3, 'H': 3, 'S': 5},  # 5 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "2S")
    
    def test_after_suit_rebid_invitational_nt(self):
        """Test responder invites game with 2NT after suit rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="2D", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "2NT")
    
    def test_after_suit_rebid_invitational_raise(self):
        """Test responder invites game with raise after suit rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="2D", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=12,
                distribution_points=0,
                total_points=12,
                longest_suit="D",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 4, 'H': 3, 'S': 4},  # 4 diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3D")
    
    def test_after_suit_rebid_invitational_original_suit(self):
        """Test responder invites game with raise of original suit after suit rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="2D", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 3, 'H': 4, 'S': 4},  # 4 hearts
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3H")
    
    def test_after_suit_rebid_game_force_new_suit(self):
        """Test responder game forces with new suit after suit rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="2C", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=13,
                distribution_points=0,
                total_points=13,
                longest_suit="D",
                longest_suit_length=5,
                suit_lengths={'C': 2, 'D': 5, 'H': 3, 'S': 3},  # 5 diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3D")
    
    def test_after_suit_rebid_preference(self):
        """Test responder shows preference after suit rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1S", position=1),
                Bid(seat="E", bid="2C", position=2),
                Bid(seat="N", bid="2H", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="S",
                longest_suit_length=2,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},  # 4 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3S")
    
    def test_after_suit_rebid_game_force_original_suit(self):
        """Test responder game forces with original suit after suit rebid."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1S", position=1),
                Bid(seat="E", bid="2C", position=2),
                Bid(seat="N", bid="2H", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=13,
                distribution_points=0,
                total_points=13,
                longest_suit="S",
                longest_suit_length=5,
                suit_lengths={'C': 2, 'D': 3, 'H': 3, 'S': 5},  # 5 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3S")
    
    def test_fourth_suit_forcing(self):
        """Test responder uses 4th suit forcing."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2),
                Bid(seat="N", bid="2C", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=12,
                distribution_points=0,
                total_points=12,
                longest_suit="D",
                longest_suit_length=3,
                suit_lengths={'C': 2, 'D': 3, 'H': 3, 'S': 5},  # 4th suit is diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "2D")
    
    def test_after_2nt_response_invitational_raise(self):
        """Test responder invites game with raise after 2NT response."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1S", position=1),
                Bid(seat="E", bid="2C", position=2),
                Bid(seat="N", bid="2D", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},  # 4 clubs
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3C")
    
    def test_after_2nt_response_invitational_nt(self):
        """Test responder invites game with 2NT after 2NT response."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1S", position=1),
                Bid(seat="E", bid="2C", position=2),
                Bid(seat="N", bid="2H", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="S",
                longest_suit_length=3,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "2NT")
    
    def test_after_2nt_response_invitational_original_suit(self):
        """Test responder invites game with raise of original suit after 2NT response."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1S", position=1),
                Bid(seat="E", bid="2C", position=2),
                Bid(seat="N", bid="2H", position=3)
            ],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 3, 'H': 3, 'S': 5},  # 4 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_responder_rebid(context)
        self.assertEqual(bid, "3S")


if __name__ == '__main__':
    unittest.main()
