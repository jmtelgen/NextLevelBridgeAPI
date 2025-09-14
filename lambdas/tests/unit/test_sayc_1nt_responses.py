"""
Test suite for SAYC 1NT responses
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYC1NTResponses(unittest.TestCase):
    """Test SAYC 1NT response logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bidding = SAYCBidding()
        # Create a 1NT opening context
        self.context = BiddingContext(
            current_seat="S",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1NT", position=1)],
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
    
    def test_2d_transfer_5_hearts(self):
        """Test 2D Jacoby transfer with 5+ hearts."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 3, 'H': 5, 'S': 2},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': True, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2D")
    
    def test_2h_transfer_5_spades(self):
        """Test 2H Jacoby transfer with 5+ spades."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="S",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 3, 'H': 2, 'S': 5},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': False, 'S': True},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2H")
    
    def test_no_transfer_with_4_spades(self):
        """Test that 2D transfer is not used with 4+ spades."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 2, 'H': 5, 'S': 4},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': True, 'S': True},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2C")  # Should use Stayman instead
    
    def test_stayman_with_4_4_majors(self):
        """Test Stayman with 4-4 in majors."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 2, 'H': 4, 'S': 4},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': True, 'S': True},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2C")
    
    def test_stayman_with_4_hearts(self):
        """Test Stayman with 4 hearts."""
        analysis = HandAnalysis(
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
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2C")
    
    def test_stayman_with_4_spades(self):
        """Test Stayman with 4 spades."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="S",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': False, 'S': True},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2C")
    
    def test_stayman_with_shortness(self):
        """Test Stayman with shortness (singleton/void)."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 1, 'D': 4, 'H': 4, 'S': 4},  # Singleton club
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': True, 'S': True},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2C")
    
    def test_no_stayman_with_less_than_8_hcp(self):
        """Test that Stayman is not used with less than 8 HCP."""
        analysis = HandAnalysis(
            hcp=6,
            distribution_points=0,
            total_points=6,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 1, 'D': 4, 'H': 4, 'S': 4},  # Singleton club
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': True, 'S': True},
            controls=1
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "pass")  # Should not use Stayman with 6 HCP
    
    def test_2s_response_long_minor(self):
        """Test 2S response with long minor suit."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="D",
            longest_suit_length=5,
            suit_lengths={'C': 3, 'D': 5, 'H': 3, 'S': 2},  # 5 diamonds
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': False, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2S")
    
    def test_2s_response_long_clubs(self):
        """Test 2S response with long clubs."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="C",
            longest_suit_length=5,
            suit_lengths={'C': 5, 'D': 3, 'H': 3, 'S': 2},  # 5 clubs
            balanced=False,
            stoppers={'C': True, 'D': False, 'H': False, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2S")
    
    def test_3c_response_6_clubs(self):
        """Test 3C response with 6+ clubs."""
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="C",
            longest_suit_length=6,
            suit_lengths={'C': 6, 'D': 3, 'H': 3, 'S': 1},
            balanced=False,
            stoppers={'C': True, 'D': False, 'H': False, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "3C")
    
    def test_3d_response_6_diamonds(self):
        """Test 3D response with 6+ diamonds."""
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
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "3D")
    
    def test_3h_response_6_hearts(self):
        """Test 3H response with 6+ hearts."""
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
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "3H")
    
    def test_3s_response_6_spades(self):
        """Test 3S response with 6+ spades."""
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
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "3S")
    
    def test_4c_gerber_strong_hand(self):
        """Test 4C Gerber with strong hand."""
        analysis = HandAnalysis(
            hcp=15,
            distribution_points=0,
            total_points=15,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=False,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=4
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "4C")
    
    def test_4nt_quantitative_invitational(self):
        """Test 4NT quantitative with invitational hand."""
        analysis = HandAnalysis(
            hcp=16,
            distribution_points=0,
            total_points=16,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=True,
            stoppers={'C': True, 'D': True, 'H': True, 'S': True},
            controls=4
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "4NT")
    
    def test_2nt_response_weak_5_card_suit(self):
        """Test 2NT response with weak 5-card suit."""
        analysis = HandAnalysis(
            hcp=6,
            distribution_points=0,
            total_points=6,
            longest_suit="C",
            longest_suit_length=5,
            suit_lengths={'C': 5, 'D': 3, 'H': 3, 'S': 2},  # 5 clubs, not hearts
            balanced=False,
            stoppers={'C': True, 'D': False, 'H': False, 'S': False},
            controls=1
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "2NT")
    
    def test_pass_weak_hand(self):
        """Test pass with weak hand."""
        analysis = HandAnalysis(
            hcp=4,
            distribution_points=0,
            total_points=4,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
            balanced=False,
            stoppers={'C': False, 'D': False, 'H': False, 'S': False},
            controls=1
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "pass")
    
    def test_2nt_response_2nt_opening(self):
        """Test 2NT response to 2NT opening."""
        # Change context to 2NT opening
        self.context.bidding_sequence = [Bid(seat="N", bid="2NT", position=1)]
        
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': True, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "3C")  # Stayman over 2NT
    
    def test_3nt_response_3nt_opening(self):
        """Test 3NT response to 3NT opening."""
        # Change context to 3NT opening
        self.context.bidding_sequence = [Bid(seat="N", bid="3NT", position=1)]
        
        analysis = HandAnalysis(
            hcp=8,
            distribution_points=0,
            total_points=8,
            longest_suit="H",
            longest_suit_length=4,
            suit_lengths={'C': 3, 'D': 4, 'H': 4, 'S': 2},
            balanced=False,
            stoppers={'C': False, 'D': True, 'H': True, 'S': False},
            controls=2
        )
        self.context.hand_analysis = analysis
        
        bid = self.bidding._make_response_bid(self.context)
        self.assertEqual(bid, "4C")  # Stayman over 3NT


if __name__ == '__main__':
    unittest.main()
