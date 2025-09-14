"""
Test suite for SAYC opening bids
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYCOpeningBids(unittest.TestCase):
    """Test SAYC opening bid logic."""
    
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
    
    def test_1nt_opening_balanced_15_hcp(self):
        """Test 1NT opening with 15 HCP balanced hand."""
        # Create a proper balanced hand with 15 HCP
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
    
    def test_1nt_opening_balanced_17_hcp(self):
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
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 5+ hearts
        analysis.suit_lengths['H'] = 5
        analysis.balanced = False
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertNotEqual(bid, "1NT")
    
    def test_2nt_opening_20_hcp(self):
        """Test 2NT opening with 20 HCP balanced hand."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 20 HCP
        analysis.hcp = 20
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2NT")
    
    def test_2nt_opening_21_hcp(self):
        """Test 2NT opening with 21 HCP balanced hand."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 21 HCP
        analysis.hcp = 21
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2NT")
    
    def test_3nt_opening_25_hcp(self):
        """Test 3NT opening with 25 HCP balanced hand."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 25 HCP
        analysis.hcp = 25
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3NT")
    
    def test_2c_opening_22_hcp(self):
        """Test 2C opening with 22+ HCP."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 22 HCP
        analysis.hcp = 22
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2C")
    
    def test_2d_opening_weak_two(self):
        """Test 2D opening with weak two values."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 6+ diamonds and 5-11 HCP
        analysis.suit_lengths['D'] = 6
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2D")
    
    def test_2h_opening_weak_two(self):
        """Test 2H opening with weak two values."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 6+ hearts and 5-11 HCP
        analysis.suit_lengths['H'] = 6
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2H")
    
    def test_2s_opening_weak_two(self):
        """Test 2S opening with weak two values."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 6+ spades and 5-11 HCP
        analysis.suit_lengths['S'] = 6
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "2S")
    
    def test_3c_opening_preemptive(self):
        """Test 3C opening with preemptive values."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 7+ clubs and weak hand
        analysis.suit_lengths['C'] = 7
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3C")
    
    def test_3d_opening_preemptive(self):
        """Test 3D opening with preemptive values."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 7+ diamonds and weak hand
        analysis.suit_lengths['D'] = 7
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3D")
    
    def test_3h_opening_preemptive(self):
        """Test 3H opening with preemptive values."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 7+ hearts and weak hand
        analysis.suit_lengths['H'] = 7
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3H")
    
    def test_3s_opening_preemptive(self):
        """Test 3S opening with preemptive values."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 7+ spades and weak hand
        analysis.suit_lengths['S'] = 7
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "3S")
    
    def test_1c_opening_longest_suit(self):
        """Test 1C opening when clubs is longest suit."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force clubs as longest suit and 12+ HCP
        analysis.suit_lengths['C'] = 5
        analysis.suit_lengths['D'] = 4
        analysis.suit_lengths['H'] = 3
        analysis.suit_lengths['S'] = 1
        analysis.hcp = 12
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1C")
    
    def test_1c_opening_3_3_minors(self):
        """Test 1C opening with 3-3 in minors."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 3-3 in minors and 12+ HCP
        analysis.suit_lengths['C'] = 3
        analysis.suit_lengths['D'] = 3
        analysis.suit_lengths['H'] = 4
        analysis.suit_lengths['S'] = 3
        analysis.hcp = 12
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1C")
    
    def test_1d_opening_longest_suit(self):
        """Test 1D opening when diamonds is longest suit."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force diamonds as longest suit and 12+ HCP
        analysis.suit_lengths['C'] = 3
        analysis.suit_lengths['D'] = 5
        analysis.suit_lengths['H'] = 3
        analysis.suit_lengths['S'] = 2
        analysis.hcp = 12
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1D")
    
    def test_1d_opening_4_4_minors(self):
        """Test 1D opening with 4-4 in minors."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 4-4 in minors and 12+ HCP
        analysis.suit_lengths['C'] = 4
        analysis.suit_lengths['D'] = 4
        analysis.suit_lengths['H'] = 3
        analysis.suit_lengths['S'] = 2
        analysis.hcp = 12
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1D")
    
    def test_1h_opening_5_card_major(self):
        """Test 1H opening with 5+ hearts."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 5+ hearts and 12+ HCP
        analysis.suit_lengths['C'] = 3
        analysis.suit_lengths['D'] = 3
        analysis.suit_lengths['H'] = 5
        analysis.suit_lengths['S'] = 2
        analysis.hcp = 12
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1H")
    
    def test_1s_opening_5_card_major(self):
        """Test 1S opening with 5+ spades."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force 5+ spades and 12+ HCP
        analysis.suit_lengths['C'] = 3
        analysis.suit_lengths['D'] = 3
        analysis.suit_lengths['H'] = 2
        analysis.suit_lengths['S'] = 5
        analysis.hcp = 12
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1S")
    
    def test_pass_with_insufficient_values(self):
        """Test pass with insufficient values for opening."""
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        # Force low HCP
        analysis.hcp = 8
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "pass")
    
    def test_rule_of_21_application(self):
        """Test Rule of 21 application for marginal hands."""
        # This would need more sophisticated implementation
        # For now, just test that 12+ HCP hands open
        hand = ["AS", "KQ", "J9", "T8", "7", "6", "5", "4", "3", "2", "A", "K", "Q", "J"]
        analysis = self.bidding.hand_evaluator.evaluate_hand(hand)
        analysis.hcp = 12
        analysis.suit_lengths['C'] = 5
        analysis.suit_lengths['D'] = 4
        analysis.suit_lengths['H'] = 3
        analysis.suit_lengths['S'] = 1
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_opening_bid(self.context)
        self.assertEqual(bid, "1C")


if __name__ == '__main__':
    unittest.main()
