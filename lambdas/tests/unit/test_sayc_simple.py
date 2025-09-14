"""
Simple test suite for SAYC opening bids
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYCOpeningBidsSimple(unittest.TestCase):
    """Test SAYC opening bid logic with simple test cases."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bidding = SAYCBidding()
        self.context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[],
            hand_analysis=HandAnalysis(
                hcp=0,
                distribution_points=0,
                total_points=0,
                longest_suit="C",
                longest_suit_length=0,
                suit_lengths={'C': 0, 'D': 0, 'H': 0, 'S': 0},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': False, 'S': False},
                controls=0
            )
        )
    
    def test_1nt_opening_15_hcp_balanced(self):
        """Test 1NT opening with 15 HCP balanced hand."""
        analysis = HandAnalysis(
            hcp=15,
            distribution_points=0,
            total_points=15,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=True,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=4
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1NT")
    
    def test_1nt_opening_17_hcp_balanced(self):
        """Test 1NT opening with 17 HCP balanced hand."""
        analysis = HandAnalysis(
            hcp=17,
            distribution_points=0,
            total_points=17,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=True,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=4
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1NT")
    
    def test_no_1nt_with_5_card_major(self):
        """Test that 1NT is not opened with 5+ card major."""
        analysis = HandAnalysis(
            hcp=16,
            distribution_points=0,
            total_points=16,
            longest_suit="H",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 3, 'H': 5, 'S': 2},
            balanced=False,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=4
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1H")  # Should open 1H instead
    
    def test_2nt_opening_20_hcp_balanced(self):
        """Test 2NT opening with 20 HCP balanced hand."""
        analysis = HandAnalysis(
            hcp=20,
            distribution_points=0,
            total_points=20,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=True,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=5
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2NT")
    
    def test_2nt_opening_21_hcp_balanced(self):
        """Test 2NT opening with 21 HCP balanced hand."""
        analysis = HandAnalysis(
            hcp=21,
            distribution_points=0,
            total_points=21,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=True,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=5
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2NT")
    
    def test_3nt_opening_25_hcp_balanced(self):
        """Test 3NT opening with 25 HCP balanced hand."""
        analysis = HandAnalysis(
            hcp=25,
            distribution_points=0,
            total_points=25,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=True,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=6
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3NT")
    
    def test_2c_opening_22_hcp(self):
        """Test 2C opening with 22+ HCP."""
        analysis = HandAnalysis(
            hcp=22,
            distribution_points=0,
            total_points=22,
            longest_suit="C",
            longest_suit_length=5,
            suit_lengths={'C': 5, 'D': 4, 'H': 3, 'S': 1},
            balanced=False,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=6
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2C")
    
    def test_2d_opening_weak_two(self):
        """Test 2D opening with weak two values."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="D",
            longest_suit_length=6,
            suit_lengths={'C': 3, 'D': 6, 'H': 3, 'S': 1},
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': False, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2D")
    
    def test_2h_opening_weak_two(self):
        """Test 2H opening with weak two values."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=6,
            suit_lengths={'C': 3, 'D': 3, 'H': 6, 'S': 1},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': True, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2H")
    
    def test_2s_opening_weak_two(self):
        """Test 2S opening with weak two values."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="S",
            longest_suit_length=6,
            suit_lengths={'C': 3, 'D': 3, 'H': 1, 'S': 6},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': False, 'S': True},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2S")
    
    def test_3c_opening_preemptive(self):
        """Test 3C opening with preemptive values."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="C",
            longest_suit_length=7,
            suit_lengths={'C': 7, 'D': 3, 'H': 2, 'S': 1},
            balanced=False,
            stoppers={'C': True, 'D': False, 'H': False, 'S': False},
            controls=1
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3C")
    
    def test_3d_opening_preemptive(self):
        """Test 3D opening with preemptive values."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="D",
            longest_suit_length=7,
            suit_lengths={'C': 3, 'D': 7, 'H': 2, 'S': 1},
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': False, 'S': False},
            controls=1
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3D")
    
    def test_3h_opening_preemptive(self):
        """Test 3H opening with preemptive values."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=7,
            suit_lengths={'C': 3, 'D': 2, 'H': 7, 'S': 1},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': True, 'S': False},
            controls=1
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3H")
    
    def test_3s_opening_preemptive(self):
        """Test 3S opening with preemptive values."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="S",
            longest_suit_length=7,
            suit_lengths={'C': 3, 'D': 2, 'H': 1, 'S': 7},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': False, 'S': True},
            controls=1
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3S")
    
    def test_1h_opening_5_card_major(self):
        """Test 1H opening with 5+ hearts."""
        analysis = HandAnalysis(
            hcp=12,
            distribution_points=0,
            total_points=12,
            longest_suit="H",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 3, 'H': 5, 'S': 2},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': True, 'S': False},
            controls=3
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1H")
    
    def test_1s_opening_5_card_major(self):
        """Test 1S opening with 5+ spades."""
        analysis = HandAnalysis(
            hcp=12,
            distribution_points=0,
            total_points=12,
            longest_suit="S",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 3, 'H': 2, 'S': 5},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': False, 'S': True},
            controls=3
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1S")
    
    def test_1d_opening_longest_suit(self):
        """Test 1D opening when diamonds is longest suit."""
        analysis = HandAnalysis(
            hcp=12,
            distribution_points=0,
            total_points=12,
            longest_suit="D",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 5, 'H': 3, 'S': 2},
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': False, 'S': False},
            controls=3
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1D")
    
    def test_1d_opening_4_4_minors(self):
        """Test 1D opening with 4-4 in minors."""
        analysis = HandAnalysis(
            hcp=12,
            distribution_points=0,
            total_points=12,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 4, 'D': 4, 'H': 4, 'S': 1},
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': False, 'S': False},
            controls=3
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1D")
    
    def test_1c_opening_longest_suit(self):
        """Test 1C opening when clubs is longest suit."""
        analysis = HandAnalysis(
            hcp=12,
            distribution_points=0,
            total_points=12,
            longest_suit="C",
            longest_suit_length=5,
            suit_lengths={'C': 5, 'D': 3, 'H': 3, 'S': 2},
            balanced=False,
            stoppers={'C': True, 'D': False, 'H': False, 'S': False},
            controls=3
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1C")
    
    def test_1c_opening_3_3_minors(self):
        """Test 1C opening with 3-3 in minors."""
        analysis = HandAnalysis(
            hcp=12,
            distribution_points=0,
            total_points=12,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
            balanced=False,
            stoppers={'C': True, 'D': False, 'H': False, 'S': False},
            controls=3
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1C")
    
    def test_pass_with_insufficient_values(self):
        """Test pass with insufficient values for opening."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': False, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "pass")


if __name__ == '__main__':
    unittest.main()

