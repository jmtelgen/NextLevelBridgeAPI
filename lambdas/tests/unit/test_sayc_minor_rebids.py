"""
Test suite for SAYC minor suit opener rebids after 1C/1D openings.
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYCMinorRebids(unittest.TestCase):
    """Test minor suit opener rebids after 1C/1D opening and partner's response."""
    
    def setUp(self):
        self.bidding = SAYCBidding()
    
    def test_1c_opening_2nt_response_rebid(self):
        """Test opener rebids after 2NT response to 1C opening."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="2NT", position=2)  # 13-15 points, game force
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3NT")
    
    def test_1c_opening_2nt_response_rebid_16_17(self):
        """Test opener rebids 3NT after 2NT response with 16-17 points."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="2NT", position=2)  # 13-15 points, game force
            ],
            hand_analysis=HandAnalysis(
                hcp=16,
                distribution_points=0,
                total_points=16,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3NT")
    
    def test_1c_opening_1h_response_rebid_nt(self):
        """Test opener rebids 1NT after 1H response to 1C opening."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=14,
                distribution_points=0,
                total_points=14,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "1NT")
    
    def test_1c_opening_1h_response_rebid_2c(self):
        """Test opener rebids 2C after 1H response with 6+ clubs."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="C",
                longest_suit_length=6,
                suit_lengths={'C': 6, 'D': 2, 'H': 3, 'S': 2},  # 6 clubs
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2C")
    
    def test_1c_opening_1h_response_rebid_2d(self):
        """Test opener rebids 2D after 1H response with 4+ diamonds."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="D",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 4, 'H': 3, 'S': 3},  # 4 diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2D")
    
    def test_1c_opening_1h_response_rebid_2s(self):
        """Test opener rebids 2S after 1H response with 4+ spades."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 3, 'S': 4},  # 4 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2S")
    
    def test_1c_opening_1h_response_rebid_3c(self):
        """Test opener jump rebids 3C after 1H response with strong hand and 6+ clubs."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=18,
                distribution_points=0,
                total_points=18,
                longest_suit="C",
                longest_suit_length=6,
                suit_lengths={'C': 6, 'D': 2, 'H': 3, 'S': 2},  # 6 clubs
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3C")
    
    def test_1c_opening_1h_response_rebid_2nt(self):
        """Test opener rebids 2NT after 1H response with strong balanced hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1C", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=17,
                distribution_points=0,
                total_points=17,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2NT")
    
    def test_1d_opening_1h_response_rebid_nt(self):
        """Test opener rebids 1NT after 1H response to 1D opening."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1D", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=14,
                distribution_points=0,
                total_points=14,
                longest_suit="D",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 4, 'H': 3, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "1NT")
    
    def test_1d_opening_1h_response_rebid_2d(self):
        """Test opener rebids 2D after 1H response with 6+ diamonds."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1D", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="D",
                longest_suit_length=6,
                suit_lengths={'C': 2, 'D': 6, 'H': 3, 'S': 2},  # 6 diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2D")
    
    def test_1d_opening_1h_response_rebid_2s(self):
        """Test opener rebids 2S after 1H response with 4+ spades."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1D", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 4, 'H': 3, 'S': 4},  # 4 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2S")
    
    def test_1d_opening_1h_response_rebid_2c(self):
        """Test opener rebids 2C after 1H response with 4+ clubs."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1D", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 4, 'H': 3, 'S': 2},  # 4 clubs
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2C")
    
    def test_1d_opening_1h_response_rebid_3d(self):
        """Test opener jump rebids 3D after 1H response with strong hand and 6+ diamonds."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1D", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=18,
                distribution_points=0,
                total_points=18,
                longest_suit="D",
                longest_suit_length=6,
                suit_lengths={'C': 2, 'D': 6, 'H': 3, 'S': 2},  # 6 diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3D")
    
    def test_1d_opening_1h_response_rebid_2nt(self):
        """Test opener rebids 2NT after 1H response with strong balanced hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1D", position=1),
                Bid(seat="E", bid="1H", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=17,
                distribution_points=0,
                total_points=17,
                longest_suit="D",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 4, 'H': 3, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2NT")


if __name__ == '__main__':
    unittest.main()
