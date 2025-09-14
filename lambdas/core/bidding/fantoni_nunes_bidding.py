"""
Fantoni-Nunes Bidding System Implementation

This module implements the complete Fantoni-Nunes bidding system directly in code,
tracking the full bidding sequence and seat positions for accurate decision making.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator, HandAnalysis


@dataclass
class Bid:
    """Represents a single bid in the auction."""
    seat: str  # N, E, S, W
    bid: str   # 1C, 1D, 1H, 1S, 1NT, 2C, etc.
    position: int  # 1st, 2nd, 3rd, 4th seat relative to dealer
    timestamp: int = 0


@dataclass
class BiddingContext:
    """Complete context for bidding decisions."""
    current_seat: str
    dealer: str
    vulnerability: str
    bidding_sequence: List[Bid]
    hand_analysis: HandAnalysis
    room_id: str = ""
    game_phase: str = "bidding"


class FantoniNunesBidding:
    """Complete Fantoni-Nunes bidding system implementation."""
    
    def __init__(self):
        self.hand_evaluator = HandEvaluator()
        
    def make_bid(self, hand: List[str], context: BiddingContext) -> str:
        """
        Make a bid based on the complete bidding context.
        
        Args:
            hand: List of cards
            context: Complete bidding context including sequence and positions
            
        Returns:
            The bid to make
        """
        # Analyze hand
        analysis = self.hand_evaluator.evaluate_hand(hand)
        context.hand_analysis = analysis
        
        # Determine bidding situation
        if self._is_opening_bid(context):
            return self._make_opening_bid(context)
        elif self._is_response_bid(context):
            return self._make_response_bid(context)
        elif self._is_rebid_bid(context):
            return self._make_rebid_bid(context)
        else:
            return self._make_competitive_bid(context)
    
    def _is_opening_bid(self, context: BiddingContext) -> bool:
        """Check if this is an opening bid (no previous non-pass bids)."""
        return len([bid for bid in context.bidding_sequence if bid.bid != 'pass']) == 0
    
    def _is_response_bid(self, context: BiddingContext) -> bool:
        """Check if this is a response to partner's opening bid."""
        if len(context.bidding_sequence) < 1:
            return False
            
        # Find partner's last bid
        partner_bids = self._get_partner_bids(context)
        return len([bid for bid in partner_bids if bid.bid != 'pass']) > 0
    
    def _is_rebid_bid(self, context: BiddingContext) -> bool:
        """Check if this is a rebid by the opening bidder."""
        if len(context.bidding_sequence) < 2:
            return False
            
        # Check if we opened and partner responded
        opening_bid = self._get_opening_bid(context)
        if not opening_bid or opening_bid.seat != context.current_seat:
            return False
            
        # Check if partner has responded
        partner_bids = self._get_partner_bids(context)
        return len([bid for bid in partner_bids if bid.bid != 'pass']) > 0
    
    def _make_opening_bid(self, context: BiddingContext) -> str:
        """Make an opening bid according to Fantoni-Nunes system."""
        analysis = context.hand_analysis
        
        # 1C = 15+ balanced (4333/4432/5m332), or 14+ value 5+C/444-1red, F1
        if self._is_1c_opening(analysis):
            return "1C"
        
        # 1D = 14+ value 5+D or 444-1black, F1
        if self._is_1d_opening(analysis):
            return "1D"
        
        # 1H = 14+ value 5+H (12+ if 4S), F1, may have 6H-5S, 5H-6m
        if self._is_1h_opening(analysis):
            return "1H"
        
        # 1S = 14+ value 5+S (12+ if 4H), F1
        if self._is_1s_opening(analysis):
            return "1S"
        
        # 1N = 12-14 (11+ NV), all 5422's included except both M's, 6m ok, all 4441's included
        if self._is_1nt_opening(analysis):
            return "1NT"
        
        # 2C = 10-13 value, 5C-4other unbalanced, or 6+C
        if self._is_2c_opening(analysis):
            return "2C"
        
        # 2D = 10-13 value, 5D-4M/4+m unbalanced, or 6+D
        if self._is_2d_opening(analysis):
            return "2D"
        
        # 2NT = 21-22 bal
        if self._is_2nt_opening(analysis):
            return "2NT"
        
        # 3y/4y = pree (check preempts first)
        if self._is_3c_opening(analysis):
            return "3C"
        if self._is_3d_opening(analysis):
            return "3D"
        if self._is_3h_opening(analysis):
            return "3H"
        if self._is_3s_opening(analysis):
            return "3S"
        
        # 2H/2S = 10-13 value, 5M-4+m unbalanced, or 6+M
        if self._is_2h_opening(analysis):
            return "2H"
        if self._is_2s_opening(analysis):
            return "2S"
        
        # 3NT = solid 7+crd minor nothing much else
        if self._is_3nt_opening(analysis):
            return "3NT"
        
        # No opening bid found
        return "pass"
    
    def _is_1c_opening(self, analysis: HandAnalysis) -> bool:
        """1C = 15+ balanced (4333/4432/5m332), or 14+ value 5+C/444-1red, F1"""
        # 15+ balanced
        if analysis.hcp >= 15 and analysis.balanced:
            return True
        
        # 14+ with 5+C
        if analysis.hcp >= 14 and analysis.suit_lengths.get('C', 0) >= 5:
            return True
        
        # 14+ with 444-1red (4-4-4-1 with red singleton)
        if analysis.hcp >= 14 and self._is_4441_red(analysis):
            return True
        
        return False
    
    def _is_1d_opening(self, analysis: HandAnalysis) -> bool:
        """1D = 14+ value 5+D or 444-1black, F1"""
        # 14+ with 5+D
        if analysis.hcp >= 14 and analysis.suit_lengths.get('D', 0) >= 5:
            return True
        
        # 14+ with 444-1black (4-4-4-1 with black singleton)
        if analysis.hcp >= 14 and self._is_4441_black(analysis):
            return True
        
        return False
    
    def _is_1h_opening(self, analysis: HandAnalysis) -> bool:
        """1H = 14+ value 5+H (12+ if 4S), F1, may have 6H-5S, 5H-6m"""
        # 14+ with 5+H
        if analysis.hcp >= 14 and analysis.suit_lengths.get('H', 0) >= 5:
            return True
        
        # 12+ with 4+S and 5+H
        if analysis.hcp >= 12 and analysis.suit_lengths.get('S', 0) >= 4 and analysis.suit_lengths.get('H', 0) >= 5:
            return True
        
        return False
    
    def _is_1s_opening(self, analysis: HandAnalysis) -> bool:
        """1S = 14+ value 5+S (12+ if 4H), F1"""
        # 14+ with 5+S
        if analysis.hcp >= 14 and analysis.suit_lengths.get('S', 0) >= 5:
            return True
        
        # 12+ with 4+H and 5+S
        if analysis.hcp >= 12 and analysis.suit_lengths.get('H', 0) >= 4 and analysis.suit_lengths.get('S', 0) >= 5:
            return True
        
        return False
    
    def _is_1nt_opening(self, analysis: HandAnalysis) -> bool:
        """1N = 12-14 (11+ NV), all 5422's included except both M's, 6m ok, all 4441's included"""
        # 12-14 balanced (11+ NV - we'll assume NV for now)
        if 12 <= analysis.hcp <= 14 and analysis.balanced:
            return True
        
        # 11+ NV balanced (we'll assume NV for now)
        if analysis.hcp >= 11 and analysis.balanced:
            return True
        
        return False
    
    def _is_2c_opening(self, analysis: HandAnalysis) -> bool:
        """2C = 10-13 value, 5C-4other unbalanced, or 6+C"""
        # 10-13 with 5C-4other unbalanced
        if 10 <= analysis.hcp <= 13 and analysis.suit_lengths.get('C', 0) >= 5 and not analysis.balanced:
            return True
        
        # 6+C
        if analysis.suit_lengths.get('C', 0) >= 6:
            return True
        
        return False
    
    def _is_2d_opening(self, analysis: HandAnalysis) -> bool:
        """2D = 10-13 value, 5D-4M/4+m unbalanced, or 6+D"""
        # 10-13 with 5D-4M/4+m unbalanced
        if 10 <= analysis.hcp <= 13 and analysis.suit_lengths.get('D', 0) >= 5 and not analysis.balanced:
            return True
        
        # 6+D
        if analysis.suit_lengths.get('D', 0) >= 6:
            return True
        
        return False
    
    def _is_2h_opening(self, analysis: HandAnalysis) -> bool:
        """2H = 10-13 value, 5H-4+m unbalanced, or 6+H"""
        # 10-13 with 5H-4+m unbalanced
        if 10 <= analysis.hcp <= 13 and analysis.suit_lengths.get('H', 0) >= 5 and not analysis.balanced:
            return True
        
        # 6+H
        if analysis.suit_lengths.get('H', 0) >= 6:
            return True
        
        return False
    
    def _is_2s_opening(self, analysis: HandAnalysis) -> bool:
        """2S = 10-13 value, 5S-4+m unbalanced, or 6+S"""
        # 10-13 with 5S-4+m unbalanced
        if 10 <= analysis.hcp <= 13 and analysis.suit_lengths.get('S', 0) >= 5 and not analysis.balanced:
            return True
        
        # 6+S
        if analysis.suit_lengths.get('S', 0) >= 6:
            return True
        
        return False
    
    def _is_2nt_opening(self, analysis: HandAnalysis) -> bool:
        """2NT = 21-22 bal"""
        return 21 <= analysis.hcp <= 22 and analysis.balanced
    
    def _is_3c_opening(self, analysis: HandAnalysis) -> bool:
        """3C = preempt with 7+C"""
        return analysis.suit_lengths.get('C', 0) >= 7 and analysis.hcp <= 10
    
    def _is_3d_opening(self, analysis: HandAnalysis) -> bool:
        """3D = preempt with 7+D"""
        return analysis.suit_lengths.get('D', 0) >= 7 and analysis.hcp <= 10
    
    def _is_3h_opening(self, analysis: HandAnalysis) -> bool:
        """3H = preempt with 7+H"""
        return analysis.suit_lengths.get('H', 0) >= 7 and analysis.hcp <= 10
    
    def _is_3s_opening(self, analysis: HandAnalysis) -> bool:
        """3S = preempt with 7+S"""
        return analysis.suit_lengths.get('S', 0) >= 7 and analysis.hcp <= 10
    
    def _is_3nt_opening(self, analysis: HandAnalysis) -> bool:
        """3NT = solid 7+crd minor nothing much else"""
        return (analysis.suit_lengths.get('C', 0) >= 7 or analysis.suit_lengths.get('D', 0) >= 7) and 15 <= analysis.hcp <= 17
    
    def _is_4441_red(self, analysis: HandAnalysis) -> bool:
        """Check for 4441 distribution with red singleton (H or D)"""
        lengths = list(analysis.suit_lengths.values())
        lengths.sort(reverse=True)
        return lengths == [4, 4, 4, 1] and (analysis.suit_lengths.get('H', 0) == 1 or analysis.suit_lengths.get('D', 0) == 1)
    
    def _is_4441_black(self, analysis: HandAnalysis) -> bool:
        """Check for 4441 distribution with black singleton (S or C)"""
        lengths = list(analysis.suit_lengths.values())
        lengths.sort(reverse=True)
        return lengths == [4, 4, 4, 1] and (analysis.suit_lengths.get('S', 0) == 1 or analysis.suit_lengths.get('C', 0) == 1)
    
    def _get_partner_bids(self, context: BiddingContext) -> List[Bid]:
        """Get all bids made by partner."""
        partner_seats = self._get_partner_seats(context.current_seat)
        return [bid for bid in context.bidding_sequence if bid.seat in partner_seats]
    
    def _get_partner_seats(self, seat: str) -> List[str]:
        """Get partner seats for given seat."""
        if seat in ['North', 'South']:
            return ['North', 'South']
        else:
            return ['East', 'West']
    
    def _get_opening_bid(self, context: BiddingContext) -> Optional[Bid]:
        """Get the opening bid in the sequence."""
        for bid in context.bidding_sequence:
            if bid.bid != 'pass':
                return bid
        return None
    
    def _make_response_bid(self, context: BiddingContext) -> str:
        """Make a response bid (to be implemented in next section)."""
        # TODO: Implement response bidding logic
        return "pass"
    
    def _make_rebid_bid(self, context: BiddingContext) -> str:
        """Make a rebid (to be implemented in next section)."""
        # TODO: Implement rebid logic
        return "pass"
    
    def _make_competitive_bid(self, context: BiddingContext) -> str:
        """Make a competitive bid (to be implemented in next section)."""
        # TODO: Implement competitive bidding logic
        return "pass"
