"""
Bidding System utility class implementing the Fantoni-Nunes system.

This class handles opening bids, responses, and rebids according to the
Fantoni-Nunes bidding system as documented in bridge_bidding_alg.txt.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from lambdas.core.hand_evaluation.hand_evaluator import HandAnalysis, HandEvaluator


@dataclass
class BiddingContext:
    """Context for bidding decisions."""
    seat: str
    vulnerability: str
    position: int  # 1st, 2nd, 3rd, 4th seat
    previous_bids: List[Dict]
    partner_bids: List[Dict]
    opponents_bids: List[Dict]


class BiddingSystem:
    """Implements the Fantoni-Nunes bidding system."""
    
    def __init__(self):
        self.hand_evaluator = HandEvaluator()
    
    def get_opening_bid(self, hand: List[str], context: BiddingContext) -> Optional[str]:
        """
        Determine the opening bid for a hand.
        
        Args:
            hand: List of cards
            context: Bidding context
            
        Returns:
            Opening bid or None if should pass
        """
        analysis = self.hand_evaluator.evaluate_hand(hand)
        
        # Check if we should open
        if not self._should_open(analysis, context):
            return None
        
        # 1C opening: 15+ balanced or 14+ with 5+C or 444-1red
        if self._is_1c_opening(analysis):
            return '1C'
        
        # 1D opening: 14+ with 5+D or 444-1black
        if self._is_1d_opening(analysis):
            return '1D'
        
        # 1H opening: 14+ with 5+H (12+ if 4S)
        if self._is_1h_opening(analysis):
            return '1H'
        
        # 1S opening: 14+ with 5+S (12+ if 4H)
        if self._is_1s_opening(analysis):
            return '1S'
        
        # 1NT opening: 12-14 balanced (11+ NV)
        if self._is_1nt_opening(analysis):
            return '1NT'
        
        # 2-level openings
        two_bid = self._get_two_level_opening(analysis, context)
        if two_bid:
            return two_bid
        
        # 3-level preempts
        three_bid = self._get_three_level_preempt(analysis, context)
        if three_bid:
            return three_bid
        
        return None
    
    def get_response(self, hand: List[str], opening_bid: str, context: BiddingContext) -> Optional[str]:
        """
        Determine response to partner's opening bid.
        
        Args:
            hand: List of cards
            opening_bid: Partner's opening bid
            context: Bidding context
            
        Returns:
            Response bid or None if should pass
        """
        analysis = self.hand_evaluator.evaluate_hand(hand)
        
        if opening_bid == '1C':
            return self._respond_to_1c(analysis, context)
        elif opening_bid == '1D':
            return self._respond_to_1d(analysis, context)
        elif opening_bid == '1H':
            return self._respond_to_1h(analysis, context)
        elif opening_bid == '1S':
            return self._respond_to_1s(analysis, context)
        elif opening_bid == '1NT':
            return self._respond_to_1nt(analysis, context)
        
        return None
    
    def _should_open(self, analysis: HandAnalysis, context: BiddingContext) -> bool:
        """Check if hand is strong enough to open."""
        # Minimum opening requirements
        if analysis.total_points < 10:
            return False
        
        # Position adjustments
        if context.position == 3:  # 3rd seat
            return analysis.total_points >= 8
        elif context.position == 4:  # 4th seat
            return analysis.total_points >= 12
        
        return analysis.total_points >= 10
    
    def _is_1c_opening(self, analysis: HandAnalysis) -> bool:
        """Check if hand qualifies for 1C opening."""
        # 15+ balanced (4333/4432/5m332)
        if analysis.balanced and analysis.hcp >= 15:
            return True
        
        # 14+ with 5+C
        if analysis.longest_suit == 'C' and analysis.longest_suit_length >= 5 and analysis.hcp >= 14:
            return True
        
        # 444-1red (4-4-4-1 with red singleton)
        if self._is_4441_red(analysis):
            return True
        
        return False
    
    def _is_1d_opening(self, analysis: HandAnalysis) -> bool:
        """Check if hand qualifies for 1D opening."""
        # 14+ with 5+D
        if analysis.longest_suit == 'D' and analysis.longest_suit_length >= 5 and analysis.hcp >= 14:
            return True
        
        # 444-1black (4-4-4-1 with black singleton)
        if self._is_4441_black(analysis):
            return True
        
        return False
    
    def _is_1h_opening(self, analysis: HandAnalysis) -> bool:
        """Check if hand qualifies for 1H opening."""
        # 14+ with 5+H (12+ if 4S)
        if analysis.longest_suit == 'H' and analysis.longest_suit_length >= 5:
            if analysis.suit_lengths.get('S', 0) >= 4:
                return analysis.hcp >= 12
            else:
                return analysis.hcp >= 14
        
        return False
    
    def _is_1s_opening(self, analysis: HandAnalysis) -> bool:
        """Check if hand qualifies for 1S opening."""
        # 14+ with 5+S (12+ if 4H)
        if analysis.longest_suit == 'S' and analysis.longest_suit_length >= 5:
            if analysis.suit_lengths.get('H', 0) >= 4:
                return analysis.hcp >= 12
            else:
                return analysis.hcp >= 14
        
        return False
    
    def _is_1nt_opening(self, analysis: HandAnalysis) -> bool:
        """Check if hand qualifies for 1NT opening."""
        if not analysis.balanced:
            return False
        
        # 12-14 (11+ NV)
        if analysis.hcp >= 12 and analysis.hcp <= 14:
            return True
        
        return False
    
    def _get_two_level_opening(self, analysis: HandAnalysis, context: BiddingContext) -> Optional[str]:
        """Get 2-level opening bid."""
        # 2C: 10-13 with 5C-4other or 6+C
        if (analysis.longest_suit == 'C' and 
            analysis.longest_suit_length >= 5 and 
            10 <= analysis.hcp <= 13):
            return '2C'
        
        # 2D: 10-13 with 5D-4M/4+m or 6+D
        if (analysis.longest_suit == 'D' and 
            analysis.longest_suit_length >= 5 and 
            10 <= analysis.hcp <= 13):
            return '2D'
        
        # 2H: 10-13 with 5H-4+m or 6+H
        if (analysis.longest_suit == 'H' and 
            analysis.longest_suit_length >= 5 and 
            10 <= analysis.hcp <= 13):
            return '2H'
        
        # 2S: 10-13 with 5S-4+m or 6+S
        if (analysis.longest_suit == 'S' and 
            analysis.longest_suit_length >= 5 and 
            10 <= analysis.hcp <= 13):
            return '2S'
        
        # 2NT: 21-22 balanced
        if analysis.balanced and 21 <= analysis.hcp <= 22:
            return '2NT'
        
        return None
    
    def _get_three_level_preempt(self, analysis: HandAnalysis, context: BiddingContext) -> Optional[str]:
        """Get 3-level preempt bid."""
        # Need 7+ cards in suit for preempt
        if analysis.longest_suit_length >= 7:
            suit = analysis.longest_suit
            return f'3{suit}'
        
        return None
    
    def _respond_to_1c(self, analysis: HandAnalysis, context: BiddingContext) -> Optional[str]:
        """Respond to 1C opening."""
        # 1D: 4+H, 0-9
        if (analysis.suit_lengths.get('H', 0) >= 4 and 
            analysis.hcp <= 9):
            return '1D'
        
        # 1H: 4+S, 0-9
        if (analysis.suit_lengths.get('S', 0) >= 4 and 
            analysis.hcp <= 9):
            return '1H'
        
        # 1S: 4+H, 14-20/GF
        if (analysis.suit_lengths.get('H', 0) >= 4 and 
            analysis.hcp >= 14):
            return '1S'
        
        # 1NT: 15-18, denies 4H
        if (analysis.hcp >= 15 and analysis.hcp <= 18 and 
            analysis.suit_lengths.get('H', 0) < 4):
            return '1NT'
        
        # 2C: 14-17, 6+C or 4D-5C
        if (analysis.hcp >= 14 and analysis.hcp <= 17 and
            (analysis.suit_lengths.get('C', 0) >= 6 or
             (analysis.suit_lengths.get('D', 0) >= 4 and analysis.suit_lengths.get('C', 0) >= 5))):
            return '2C'
        
        return None
    
    def _respond_to_1d(self, analysis: HandAnalysis, context: BiddingContext) -> Optional[str]:
        """Respond to 1D opening."""
        # 1H: 4+H, 0-9
        if (analysis.suit_lengths.get('H', 0) >= 4 and 
            analysis.hcp <= 9):
            return '1H'
        
        # 1S: 4+S, 0-9
        if (analysis.suit_lengths.get('S', 0) >= 4 and 
            analysis.hcp <= 9):
            return '1S'
        
        # 1NT: 18+ unbalanced
        if analysis.hcp >= 18 and not analysis.balanced:
            return '1NT'
        
        return None
    
    def _respond_to_1h(self, analysis: HandAnalysis, context: BiddingContext) -> Optional[str]:
        """Respond to 1H opening."""
        # 1S: 4+S, 0-9
        if (analysis.suit_lengths.get('S', 0) >= 4 and 
            analysis.hcp <= 9):
            return '1S'
        
        # 1NT: no 4M, 0-9
        if (analysis.suit_lengths.get('S', 0) < 4 and 
            analysis.suit_lengths.get('H', 0) < 4 and
            analysis.hcp <= 9):
            return '1NT'
        
        # 2C: 10+ balanced or clubs or H raise
        if analysis.hcp >= 10:
            return '2C'
        
        return None
    
    def _respond_to_1s(self, analysis: HandAnalysis, context: BiddingContext) -> Optional[str]:
        """Respond to 1S opening."""
        # 1NT: 0-9 no 4S
        if (analysis.suit_lengths.get('S', 0) < 4 and 
            analysis.hcp <= 9):
            return '1NT'
        
        # 2C: 10+ balanced or clubs or S raise
        if analysis.hcp >= 10:
            return '2C'
        
        return None
    
    def _respond_to_1nt(self, analysis: HandAnalysis, context: BiddingContext) -> Optional[str]:
        """Respond to 1NT opening."""
        # 2C: Stayman
        if analysis.hcp >= 10:
            return '2C'
        
        return None
    
    def _is_4441_red(self, analysis: HandAnalysis) -> bool:
        """Check if hand is 444-1 with red singleton."""
        lengths = sorted(analysis.suit_lengths.values())
        if lengths != [1, 4, 4, 4]:
            return False
        
        # Check if singleton is red (H or D)
        for suit, length in analysis.suit_lengths.items():
            if length == 1 and suit in ['H', 'D']:
                return True
        
        return False
    
    def _is_4441_black(self, analysis: HandAnalysis) -> bool:
        """Check if hand is 444-1 with black singleton."""
        lengths = sorted(analysis.suit_lengths.values())
        if lengths != [1, 4, 4, 4]:
            return False
        
        # Check if singleton is black (C or S)
        for suit, length in analysis.suit_lengths.items():
            if length == 1 and suit in ['C', 'S']:
                return True
        
        return False
