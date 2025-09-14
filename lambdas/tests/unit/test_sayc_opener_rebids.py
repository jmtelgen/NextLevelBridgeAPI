"""
Test suite for SAYC opener rebids after major suit openings.
"""

import unittest
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis


class TestSAYCOpenerRebids(unittest.TestCase):
    """Test opener rebids after 1H/1S opening and partner's response."""
    
    def setUp(self):
        self.bidding = SAYCBidding()
    
    def test_jacoby_2nt_singleton_club(self):
        """Test opener shows singleton club after Jacoby 2NT."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="2NT", position=2)  # Jacoby 2NT
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 1, 'D': 3, 'H': 5, 'S': 4},  # Singleton club
                balanced=False,
                stoppers={'C': False, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3C")
    
    def test_jacoby_2nt_singleton_diamond(self):
        """Test opener shows singleton diamond after Jacoby 2NT."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="2NT", position=2)  # Jacoby 2NT
            ],
            hand_analysis=HandAnalysis(
                hcp=16,
                distribution_points=0,
                total_points=16,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 3, 'D': 1, 'H': 5, 'S': 4},  # Singleton diamond
                balanced=False,
                stoppers={'C': True, 'D': False, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3D")
    
    def test_jacoby_2nt_singleton_spade(self):
        """Test opener shows singleton spade after Jacoby 2NT."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="2NT", position=2)  # Jacoby 2NT
            ],
            hand_analysis=HandAnalysis(
                hcp=17,
                distribution_points=0,
                total_points=17,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 3, 'D': 4, 'H': 5, 'S': 1},  # Singleton spade
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': False},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3S")
    
    def test_jacoby_2nt_no_singleton_weak(self):
        """Test opener shows 4H with weak hand, no singleton after Jacoby 2NT."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="2NT", position=2)  # Jacoby 2NT
            ],
            hand_analysis=HandAnalysis(
                hcp=14,
                distribution_points=0,
                total_points=14,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 2, 'D': 3, 'H': 5, 'S': 3},  # No singleton
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "4H")
    
    def test_jacoby_2nt_no_singleton_medium(self):
        """Test opener shows 3NT with medium hand, no singleton after Jacoby 2NT."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="2NT", position=2)  # Jacoby 2NT
            ],
            hand_analysis=HandAnalysis(
                hcp=16,
                distribution_points=0,
                total_points=16,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 2, 'D': 3, 'H': 5, 'S': 3},  # No singleton
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3NT")
    
    def test_jacoby_2nt_no_singleton_strong(self):
        """Test opener shows 3H with strong hand, no singleton after Jacoby 2NT."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="2NT", position=2)  # Jacoby 2NT
            ],
            hand_analysis=HandAnalysis(
                hcp=18,
                distribution_points=0,
                total_points=18,
                longest_suit="H",
                longest_suit_length=5,
                suit_lengths={'C': 2, 'D': 3, 'H': 5, 'S': 3},  # No singleton
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=4
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3H")
    
    def test_minimum_hand_nt_rebid(self):
        """Test opener rebids 1NT with minimum balanced hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=14,
                distribution_points=0,
                total_points=14,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "1NT")
    
    def test_minimum_hand_raise_responder_suit(self):
        """Test opener raises responder's suit with minimum hand and 3+ support."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 3, 'H': 4, 'S': 4},  # 4 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2S")
    
    def test_minimum_hand_rebid_opener_suit(self):
        """Test opener rebids own suit with minimum hand and 6+ cards."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=14,
                distribution_points=0,
                total_points=14,
                longest_suit="H",
                longest_suit_length=6,
                suit_lengths={'C': 2, 'D': 2, 'H': 6, 'S': 3},  # 6 hearts
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2H")
    
    def test_minimum_hand_new_suit(self):
        """Test opener bids new suit with minimum hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=15,
                distribution_points=0,
                total_points=15,
                longest_suit="C",
                longest_suit_length=4,
                suit_lengths={'C': 4, 'D': 3, 'H': 3, 'S': 3},  # 4 clubs
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=2
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2C")
    
    def test_medium_hand_jump_raise(self):
        """Test opener jump raises responder's suit with medium hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=17,
                distribution_points=0,
                total_points=17,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 3, 'H': 4, 'S': 4},  # 4 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3S")
    
    def test_medium_hand_jump_rebid(self):
        """Test opener jump rebids own suit with medium hand and 6+ cards."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=18,
                distribution_points=0,
                total_points=18,
                longest_suit="H",
                longest_suit_length=6,
                suit_lengths={'C': 2, 'D': 2, 'H': 6, 'S': 3},  # 6 hearts
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3H")
    
    def test_medium_hand_reverse(self):
        """Test opener makes reverse bid with medium hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=17,
                distribution_points=0,
                total_points=17,
                longest_suit="D",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 4, 'H': 4, 'S': 3},  # 4 diamonds
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=3
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2D")
    
    def test_maximum_hand_jump_nt(self):
        """Test opener jump rebids notrump with maximum hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=20,
                distribution_points=0,
                total_points=20,
                longest_suit="H",
                longest_suit_length=4,
                suit_lengths={'C': 3, 'D': 3, 'H': 4, 'S': 3},
                balanced=True,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=4
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "2NT")
    
    def test_maximum_hand_double_jump_raise(self):
        """Test opener double jump raises responder's suit with maximum hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=19,
                distribution_points=0,
                total_points=19,
                longest_suit="S",
                longest_suit_length=4,
                suit_lengths={'C': 2, 'D': 3, 'H': 4, 'S': 4},  # 4 spades
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=4
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "4S")
    
    def test_maximum_hand_double_jump_rebid(self):
        """Test opener double jump rebids own suit with maximum hand and 6+ cards."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=21,
                distribution_points=0,
                total_points=21,
                longest_suit="H",
                longest_suit_length=6,
                suit_lengths={'C': 2, 'D': 2, 'H': 6, 'S': 3},  # 6 hearts
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=4
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "4H")
    
    def test_maximum_hand_jump_shift(self):
        """Test opener jump shifts to new suit with maximum hand."""
        context = BiddingContext(
            current_seat="N",
            dealer="N",
            vulnerability="None",
            bidding_sequence=[
                Bid(seat="N", bid="1H", position=1),
                Bid(seat="E", bid="1S", position=2)
            ],
            hand_analysis=HandAnalysis(
                hcp=20,
                distribution_points=0,
                total_points=20,
                longest_suit="C",
                longest_suit_length=5,
                suit_lengths={'C': 5, 'D': 3, 'H': 3, 'S': 2},  # 5 clubs
                balanced=False,
                stoppers={'C': True, 'D': True, 'H': True, 'S': True},
                controls=4
            )
        )
        
        bid = self.bidding._make_opener_rebid(context)
        self.assertEqual(bid, "3C")


if __name__ == '__main__':
    unittest.main()
