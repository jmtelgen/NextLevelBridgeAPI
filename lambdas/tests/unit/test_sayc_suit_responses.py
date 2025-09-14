"""
Test suite for SAYC suit opening responses
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYCSuitResponses(unittest.TestCase):
    """Test SAYC suit opening response logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bidding = SAYCBidding()
    
    def test_1h_simple_raise(self):
        """Test 2H simple raise to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="H",
                longest_suit_length=3,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "2H")
    
    def test_1h_limit_raise(self):
        """Test 3H limit raise to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=11,
                distribution_points=0,
                total_points=11,
                longest_suit="H",
                longest_suit_length=3,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "3H")
    
    def test_1h_jacoby_2nt(self):
        """Test 2NT Jacoby to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=13,
                distribution_points=0,
                total_points=13,
                longest_suit="H",
                longest_suit_length=3,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "2NT")
    
    def test_1h_3nt_response(self):
        """Test 3NT response to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=16,
                distribution_points=0,
                total_points=16,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 2, 'S': 4},  # 2 hearts
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': False, 'S': True},
                controls=4
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "3NT")
    
    def test_1h_1s_response(self):
        """Test 1S response to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 2, 'S': 4},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': False, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "1S")
    
    def test_1h_1nt_response(self):
        """Test 1NT response to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 2, 'S': 2},  # No 4+ spades, <3 hearts
                balanced=False,
                stoppers={'C': True, 'D': False, 'H': False, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "1NT")
    
    def test_1h_2c_response(self):
        """Test 2C new suit response to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=12,
                distribution_points=0,
                total_points=12,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 2, 'S': 4},
                balanced=False,
                stoppers={'C': True, 'D': False, 'H': False, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "2C")
    
    def test_1h_preemptive_raise(self):
        """Test 4H preemptive raise to 1H opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 1, 'D': 3, 'H': 5, 'S': 4},  # Singleton club
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "4H")
    
    def test_1c_1nt_response(self):
        """Test 1NT response to 1C opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1C", position=1)],
            hand_analysis=HandAnalysis(
                hcp=10,
                distribution_points=0,
                total_points=10,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},  # No 4+ major
                balanced=True,
                stoppers={'C': True, 'D': False, 'H': False, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "1NT")
    
    def test_1c_2nt_response(self):
        """Test 2NT response to 1C opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1C", position=1)],
            hand_analysis=HandAnalysis(
                hcp=14,
                distribution_points=0,
                total_points=14,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
                balanced=True,
                stoppers={'C': False, 'D': False, 'H': True, 'S': False},
                controls=3
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "2NT")
    
    def test_1c_1h_response(self):
        """Test 1H response to 1C opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1C", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "1H")
    
    def test_1c_1d_response(self):
        """Test 1D response to 1C opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1C", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="D",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 4, 'H': 3, 'S': 3},
                balanced=False,
                stoppers={'C': False, 'D': True, 'H': False, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "1D")
    
    def test_1c_2c_raise(self):
        """Test 2C raise to 1C opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1C", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="C",
                longest_suit_length=3,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 3},  # No 4+ major
                balanced=False,
                stoppers={'C': True, 'D': False, 'H': False, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "2C")
    
    def test_1s_simple_raise(self):
        """Test 2S simple raise to 1S opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1S", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="S",
                longest_suit_length=3,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "2S")
    
    def test_1d_1nt_response(self):
        """Test 1NT response to 1D opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1D", position=1)],
            hand_analysis=HandAnalysis(
                hcp=10,
                distribution_points=0,
                total_points=10,
                longest_suit="D",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 4, 'H': 3, 'S': 3},  # No 4+ major
                balanced=True,
                stoppers={'C': False, 'D': True, 'H': False, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "1NT")
    
    def test_1d_2d_raise(self):
        """Test 2D raise to 1D opening."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1D", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="D",
                longest_suit_length=3,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 3},  # No 4+ major
                balanced=False,
                stoppers={'C': False, 'D': True, 'H': False, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "2D")
    
    def test_weak_hand_pass(self):
        """Test pass with weak hand."""
        context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=4,
                distribution_points=0,
                total_points=4,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 2, 'S': 4},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': False, 'S': False},
                controls=1
            )
        )
        
        bid = self.bidding._make_response_bid(context)
        self.assertEqual(bid, "pass")


if __name__ == '__main__':
    unittest.main()
