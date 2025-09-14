"""
Test suite for SAYC overcall logic
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYCOvercalls(unittest.TestCase):
    """Test SAYC overcall logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bidding = SAYCBidding()
    
    # Penalty Double Tests
    def test_penalty_double_4h(self):
        """Test penalty double over 4H opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="4H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=16,
                distribution_points=0,
                total_points=16,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 3, 'D': 3, 'H': 5, 'S': 2},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': False},
                controls=4
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "X")
    
    def test_penalty_double_4s(self):
        """Test penalty double over 4S opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="4S", position=1)],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': False, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "X")
    
    # Takeout Double Tests
    def test_takeout_double_1h(self):
        """Test takeout double over 1H opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=12,
                distribution_points=0,
                total_points=12,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 4, 'H': 1, 'S': 4},  # Short hearts
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': False, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "X")
    
    def test_takeout_double_1s(self):
        """Test takeout double over 1S opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1S", position=1)],
            hand_analysis=HandAnalysis(
                hcp=10,
                distribution_points=0,
                total_points=10,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 4, 'H': 4, 'S': 1},  # Short spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "X")
    
    # Michaels Cuebid Tests
    def test_michaels_cuebid_1c_majors(self):
        """Test Michaels cuebid over 1C showing majors."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1C", position=1)],
            hand_analysis=HandAnalysis(
                hcp=10,
                distribution_points=0,
                total_points=10,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 1, 'D': 2, 'H': 5, 'S': 5},  # 5-5 majors
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "2C")
    
    def test_michaels_cuebid_1h_major_minor(self):
        """Test Michaels cuebid over 1H showing spades + minor."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=12,
                distribution_points=0,
                total_points=12,
                longest_suit="S",
                longest_suit_length=5,
                suit_lengths={'C': 5, 'D': 1, 'H': 2, 'S': 5},  # 5-5 spades + minor
                balanced=False,
                stoppers={'C': True, 'D': False, 'H': False, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "2H")
    
    # Unusual Notrump Tests
    def test_unusual_2nt_1c(self):
        """Test unusual 2NT over 1C showing diamonds and hearts."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1C", position=1)],
            hand_analysis=HandAnalysis(
                hcp=8,
                distribution_points=0,
                total_points=8,
                longest_suit="D",
                longest_suit_length=5,
                suit_lengths={'C': 1, 'D': 5, 'H': 5, 'S': 2},  # 5-5 diamonds and hearts
                balanced=False,
                stoppers={'C': False, 'D': True, 'H': True, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "2NT")
    
    def test_unusual_2nt_1h(self):
        """Test unusual 2NT over 1H showing minors."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=9,
                distribution_points=0,
                total_points=9,
                longest_suit="C",
                longest_suit_length=5,
                suit_lengths={'C': 5, 'D': 5, 'H': 1, 'S': 2},  # 5-5 minors
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': False, 'S': False},
                controls=2
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "2NT")
    
    # Jump Suit Overcall Tests
    def test_jump_overcall_2s_over_1d(self):
        """Test jump overcall 2S over 1D (weak two hand)."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1D", position=1)],
            hand_analysis=HandAnalysis(
                hcp=6,
                distribution_points=0,
                total_points=6,
                longest_suit="S",
                longest_suit_length=6,
                suit_lengths={'C': 2, 'D': 2, 'H': 3, 'S': 6},  # 6 spades
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': False, 'S': True},
                controls=1
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "2S")
    
    def test_jump_overcall_3c_over_1d(self):
        """Test jump overcall 3C over 1D (preemptive)."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1D", position=1)],
            hand_analysis=HandAnalysis(
                hcp=5,
                distribution_points=0,
                total_points=5,
                longest_suit="C",
                longest_suit_length=7,
                suit_lengths={'C': 7, 'D': 1, 'H': 3, 'S': 2},  # 7 clubs
                balanced=False,
                stoppers={'C': True, 'D': False, 'H': False, 'S': False},
                controls=1
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "3C")
    
    # 1NT Overcall Tests
    def test_1nt_overcall_1h(self):
        """Test 1NT overcall over 1H opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=16,
                distribution_points=0,
                total_points=16,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},  # Balanced
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},  # Stopper in hearts
                controls=4
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "1NT")
    
    def test_1nt_overcall_1s(self):
        """Test 1NT overcall over 1S opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1S", position=1)],
            hand_analysis=HandAnalysis(
                hcp=17,
                distribution_points=0,
                total_points=17,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},  # Balanced
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},  # Stopper in spades
                controls=4
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "1NT")
    
    # Non-jump Suit Overcall Tests
    def test_1s_overcall_1h(self):
        """Test 1S overcall over 1H opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=10,
                distribution_points=0,
                total_points=10,
                longest_suit="S",
                longest_suit_length=5,
                suit_lengths={'C': 3, 'D': 3, 'H': 2, 'S': 5},  # 5 spades
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': False, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "1S")
    
    def test_2h_overcall_1s(self):
        """Test 2H overcall over 1S opening."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1S", position=1)],
            hand_analysis=HandAnalysis(
                hcp=12,
                distribution_points=0,
                total_points=12,
                longest_suit="H",
                longest_suit_length=6,
                suit_lengths={'C': 2, 'D': 3, 'H': 6, 'S': 2},  # 6 hearts
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': True, 'S': False},
                controls=3
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "2H")
    
    # Balancing/Reopening Tests
    def test_balancing_1nt_after_1h_pass(self):
        """Test balancing 1NT after 1H-Pass."""
        context = BiddingContext(
            current_seat="W",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="pass", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=12,
                distribution_points=0,
                total_points=12,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},  # Balanced
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "1NT")
    
    def test_weak_hand_pass(self):
        """Test pass with weak hand."""
        context = BiddingContext(
            current_seat="E",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[Bid(seat="N", bid="1H", position=1)],
            hand_analysis=HandAnalysis(
                hcp=5,
                distribution_points=0,
                total_points=5,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},
                balanced=False,
                stoppers={'C': False, 'D': False, 'H': False, 'S': False},
                controls=1
            )
        )
        
        bid = self.bidding._make_overcall(context)
        self.assertEqual(bid, "pass")


if __name__ == '__main__':
    unittest.main()
