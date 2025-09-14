"""
Hand Evaluator utility class for bridge bidding analysis.

This class provides methods to evaluate bridge hands for bidding purposes,
including high card points, distribution points, suit analysis, and hand strength assessment.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class HandAnalysis:
    """Data class to hold hand analysis results."""
    hcp: int
    distribution_points: int
    total_points: int
    longest_suit: str
    longest_suit_length: int
    suit_lengths: Dict[str, int]
    balanced: bool
    stoppers: Dict[str, bool]
    controls: int


class HandEvaluator:
    """Evaluates bridge hands for bidding purposes."""
    
    # High card point values
    HCP_VALUES = {
        'A': 4, 'K': 3, 'Q': 2, 'J': 1
    }
    
    # Suit order for analysis
    SUITS = ['C', 'D', 'H', 'S']
    
    def __init__(self):
        pass
    
    def evaluate_hand(self, hand: List[str]) -> HandAnalysis:
        """
        Perform comprehensive hand analysis.
        
        Args:
            hand: List of cards in format ['AS', 'KH', 'QD', 'JC', ...]
            
        Returns:
            HandAnalysis object with all evaluation results
        """
        suit_lengths = self._get_suit_lengths(hand)
        hcp = self._calculate_hcp(hand)
        distribution_points = self._calculate_distribution_points(suit_lengths)
        total_points = hcp + distribution_points
        longest_suit, longest_suit_length = self._get_longest_suit(suit_lengths)
        balanced = self._is_balanced(suit_lengths)
        stoppers = self._get_stoppers(hand, suit_lengths)
        controls = self._count_controls(hand)
        
        return HandAnalysis(
            hcp=hcp,
            distribution_points=distribution_points,
            total_points=total_points,
            longest_suit=longest_suit,
            longest_suit_length=longest_suit_length,
            suit_lengths=suit_lengths,
            balanced=balanced,
            stoppers=stoppers,
            controls=controls
        )
    
    def _get_suit_lengths(self, hand: List[str]) -> Dict[str, int]:
        """Get the length of each suit in the hand."""
        suit_lengths = {'C': 0, 'D': 0, 'H': 0, 'S': 0}
        
        for card in hand:
            if len(card) >= 2:
                suit = card[1]  # Second character is the suit
                if suit in suit_lengths:
                    suit_lengths[suit] += 1
        
        return suit_lengths
    
    def _calculate_hcp(self, hand: List[str]) -> int:
        """Calculate high card points."""
        hcp = 0
        
        for card in hand:
            if len(card) >= 2:
                rank = card[0]  # First character is the rank
                hcp += self.HCP_VALUES.get(rank, 0)
        
        return hcp
    
    def _calculate_distribution_points(self, suit_lengths: Dict[str, int]) -> int:
        """Calculate distribution points based on suit lengths."""
        distribution_points = 0
        
        for suit, length in suit_lengths.items():
            if length == 0:
                distribution_points += 3  # Void
            elif length == 1:
                distribution_points += 2  # Singleton
            elif length == 2:
                distribution_points += 1  # Doubleton
        
        return distribution_points
    
    def _get_longest_suit(self, suit_lengths: Dict[str, int]) -> Tuple[str, int]:
        """Get the longest suit and its length."""
        longest_suit = max(suit_lengths.keys(), key=lambda x: suit_lengths[x])
        longest_length = suit_lengths[longest_suit]
        return longest_suit, longest_length
    
    def _is_balanced(self, suit_lengths: Dict[str, int]) -> bool:
        """Check if hand is balanced (4333, 4432, 5332)."""
        lengths = sorted(suit_lengths.values(), reverse=True)
        
        # Check for balanced patterns
        if lengths == [4, 3, 3, 3]:  # 4333
            return True
        elif lengths == [4, 4, 3, 2]:  # 4432
            return True
        elif lengths == [5, 3, 3, 2]:  # 5332
            return True
        
        return False
    
    def _get_stoppers(self, hand: List[str], suit_lengths: Dict[str, int]) -> Dict[str, bool]:
        """Check for stoppers in each suit."""
        stoppers = {}
        
        for suit in self.SUITS:
            stoppers[suit] = self._has_stopper(hand, suit, suit_lengths[suit])
        
        return stoppers
    
    def _has_stopper(self, hand: List[str], suit: str, suit_length: int) -> bool:
        """Check if hand has a stopper in the given suit."""
        if suit_length == 0:
            return False
        
        # Get cards in this suit
        suit_cards = [card for card in hand if len(card) >= 2 and card[1] == suit]
        
        # Check for different types of stoppers
        if self._has_ace(suit_cards):
            return True
        elif self._has_king_queen(suit_cards):
            return True
        elif self._has_queen_jack_ten(suit_cards):
            return True
        elif suit_length >= 4 and self._has_any_honor(suit_cards):
            return True
        
        return False
    
    def _has_ace(self, suit_cards: List[str]) -> bool:
        """Check if suit has an ace."""
        return any(card[0] == 'A' for card in suit_cards)
    
    def _has_king_queen(self, suit_cards: List[str]) -> bool:
        """Check if suit has both king and queen."""
        has_king = any(card[0] == 'K' for card in suit_cards)
        has_queen = any(card[0] == 'Q' for card in suit_cards)
        return has_king and has_queen
    
    def _has_queen_jack_ten(self, suit_cards: List[str]) -> bool:
        """Check if suit has queen, jack, and ten."""
        has_queen = any(card[0] == 'Q' for card in suit_cards)
        has_jack = any(card[0] == 'J' for card in suit_cards)
        has_ten = any(card[0] == 'T' for card in suit_cards)
        return has_queen and has_jack and has_ten
    
    def _has_any_honor(self, suit_cards: List[str]) -> bool:
        """Check if suit has any honor (A, K, Q, J)."""
        return any(card[0] in ['A', 'K', 'Q', 'J'] for card in suit_cards)
    
    def _count_controls(self, hand: List[str]) -> int:
        """Count controls (A=2, K=1)."""
        controls = 0
        
        for card in hand:
            if len(card) >= 2:
                rank = card[0]
                if rank == 'A':
                    controls += 2
                elif rank == 'K':
                    controls += 1
        
        return controls
    
    def get_suit_quality(self, hand: List[str], suit: str) -> int:
        """Get the quality of a suit (honors and length)."""
        suit_cards = [card for card in hand if len(card) >= 2 and card[1] == suit]
        suit_length = len(suit_cards)
        
        if suit_length == 0:
            return 0
        
        # Count honors
        honor_count = sum(1 for card in suit_cards if card[0] in ['A', 'K', 'Q', 'J'])
        
        # Calculate quality based on honors and length
        quality = suit_length * 2 + honor_count * 3
        
        return quality
    
    def has_fit(self, hand: List[str], partner_suit: str, min_fit: int = 8) -> bool:
        """Check if hand has a fit with partner's suit."""
        suit_lengths = self._get_suit_lengths(hand)
        our_length = suit_lengths.get(partner_suit, 0)
        
        # Assume partner has at least 4 cards in their suit
        # Combined length should be at least min_fit
        return our_length + 4 >= min_fit
    
    def get_hand_description(self, hand: List[str]) -> str:
        """Get a text description of the hand."""
        analysis = self.evaluate_hand(hand)
        
        description = f"HCP: {analysis.hcp}, "
        description += f"Distribution: {analysis.distribution_points}, "
        description += f"Total: {analysis.total_points}, "
        description += f"Longest: {analysis.longest_suit}{analysis.longest_suit_length}, "
        description += f"Balanced: {analysis.balanced}"
        
        return description
