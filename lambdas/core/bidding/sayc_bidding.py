"""
SAYC (Standard American Yellow Card) Bidding System Implementation

This module implements the complete SAYC bidding system directly in code,
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


class SAYCBidding:
    """Complete SAYC bidding system implementation."""
    
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
            
        # Check if current player is the opening bidder and has already made one bid
        opening_bid = context.bidding_sequence[0]
        if opening_bid.seat != context.current_seat:
            return False
            
        # Count non-pass bids by current player
        player_bids = [bid for bid in context.bidding_sequence 
                      if bid.seat == context.current_seat and bid.bid != 'pass']
        return len(player_bids) >= 1
    
    def _make_rebid_bid(self, context: BiddingContext) -> str:
        """Make a rebid after partner's response."""
        # Determine if this is opener's rebid or responder's rebid
        opening_bid = context.bidding_sequence[0]
        if opening_bid.seat == context.current_seat:
            return self._make_opener_rebid(context)
        else:
            return self._make_responder_rebid(context)
    
    def _make_opener_rebid(self, context: BiddingContext) -> str:
        """Make opener's rebid after partner's response."""
        analysis = context.hand_analysis
        opening_bid = context.bidding_sequence[0].bid
        response_bid = context.bidding_sequence[-1].bid
        
        # Check for Jacoby 2NT response first (highest priority)
        if response_bid == "2NT" and opening_bid in ["1H", "1S"]:
            return self._make_jacoby_2nt_rebid(analysis, opening_bid)
        
        # Check for 2NT response to minor suit opening (13-15 points, game force)
        if response_bid == "2NT" and opening_bid in ["1C", "1D"]:
            return self._make_minor_2nt_rebid(analysis, opening_bid)
        
        # Other rebids based on hand strength
        if analysis.hcp >= 19:  # Maximum hand
            return self._make_maximum_rebid(analysis, opening_bid, response_bid)
        elif analysis.hcp >= 17:  # Medium hand
            return self._make_medium_rebid(analysis, opening_bid, response_bid)
        else:  # Minimum hand (13-16)
            return self._make_minimum_rebid(analysis, opening_bid, response_bid)
    
    def _make_jacoby_2nt_rebid(self, analysis: HandAnalysis, opening_bid: str) -> str:
        """Make rebid after Jacoby 2NT response."""
        suit = opening_bid[1]  # H or S
        
        # Check for singleton or void
        for check_suit in ['C', 'D', 'S'] if suit == 'H' else ['C', 'D', 'H']:
            if analysis.suit_lengths.get(check_suit, 0) <= 1:
                return f"3{check_suit}"
        
        # No singleton/void - show strength
        if analysis.hcp < 15:
            return f"4{suit}"  # Less than 15 points
        elif analysis.hcp < 18:
            return "3NT"  # 15-17 points
        else:
            return f"3{suit}"  # 18+ points
    
    def _make_minor_2nt_rebid(self, analysis: HandAnalysis, opening_bid: str) -> str:
        """Make rebid after 2NT response to minor suit opening (13-15 points, game force)."""
        # According to SAYC: 1C-2NT = 13-15 points, game force
        # Opener should accept game invitation with 15+ points
        if analysis.hcp >= 15:
            return "3NT"
        else:
            # With less than 15 points, opener should still bid 3NT to accept the invitation
            # since responder has 13-15 and opener has 12-14, we have 25-29 total
            return "3NT"
    
    def _make_maximum_rebid(self, analysis: HandAnalysis, opening_bid: str, response_bid: str) -> str:
        """Make rebid with maximum hand (19+ points)."""
        suit = opening_bid[1]
        
        # Jump in notrump
        if analysis.balanced:
            return "2NT"
        
        # Double jump raise of responder's suit
        if self._has_support_for_suit(analysis, response_bid[1], 4):
            return f"4{response_bid[1]}"
        
        # Double jump rebid of opener's suit
        if analysis.suit_lengths.get(suit, 0) >= 6:
            return f"4{suit}"
        
        # Jump shift in new suit
        for new_suit in ['C', 'D', 'H', 'S']:
            if new_suit != suit and analysis.suit_lengths.get(new_suit, 0) >= 4:
                return f"3{new_suit}"
        
        # Fallback
        return "2NT"
    
    def _make_medium_rebid(self, analysis: HandAnalysis, opening_bid: str, response_bid: str) -> str:
        """Make rebid with medium hand (17-18 points)."""
        suit = opening_bid[1]
        
        # Jump raise of responder's suit
        if self._has_support_for_suit(analysis, response_bid[1], 4):
            return f"3{response_bid[1]}"
        
        # Jump rebid of opener's suit
        if analysis.suit_lengths.get(suit, 0) >= 6:
            return f"3{suit}"
        
        # Reverse bid in new suit
        for new_suit in ['C', 'D', 'H', 'S']:
            if new_suit != suit and analysis.suit_lengths.get(new_suit, 0) >= 4:
                return f"2{new_suit}"
        
        # Non-reverse new suit
        for new_suit in ['C', 'D', 'H', 'S']:
            if new_suit != suit and analysis.suit_lengths.get(new_suit, 0) >= 4:
                return f"2{new_suit}"
        
        # Fallback
        return "2NT"
    
    def _make_minimum_rebid(self, analysis: HandAnalysis, opening_bid: str, response_bid: str) -> str:
        """Make rebid with minimum hand (13-16 points)."""
        suit = opening_bid[1]
        
        # Nonjump rebid of notrump
        if analysis.balanced:
            return "1NT"
        
        # Nonjump rebid of opener's suit
        if analysis.suit_lengths.get(suit, 0) >= 6:
            return f"2{suit}"
        
        # Non-reverse new suit - prioritize by suit order
        for new_suit in ['C', 'D', 'H', 'S']:
            if new_suit != suit and analysis.suit_lengths.get(new_suit, 0) >= 4:
                return f"2{new_suit}"
        
        # Nonjump raise of responder's suit (lower priority)
        if self._has_support_for_suit(analysis, response_bid[1], 3):
            return f"2{response_bid[1]}"
        
        # Fallback
        return "1NT"
    
    def _has_support_for_suit(self, analysis: HandAnalysis, suit: str, min_cards: int) -> bool:
        """Check if hand has support for a suit."""
        return analysis.suit_lengths.get(suit, 0) >= min_cards
    
    def _make_responder_rebid(self, context: BiddingContext) -> str:
        """Make responder's rebid after opener's rebid."""
        analysis = context.hand_analysis
        opening_bid = context.bidding_sequence[0].bid
        opener_rebid = context.bidding_sequence[-1].bid
        responder_response = context.bidding_sequence[-2].bid  # Responder's original response
        
        # Check if opener rebid 1NT
        if opener_rebid == "1NT":
            return self._make_responder_rebid_after_1nt(analysis, opening_bid)
        
        # Check if responder's original response was 2NT (Jacoby 2NT)
        if responder_response == "2NT":
            return self._make_responder_rebid_after_2nt_response(analysis, opening_bid, opener_rebid)
        
        # Check if opener rebid a suit
        if opener_rebid[1] in ['C', 'D', 'H', 'S']:
            return self._make_responder_rebid_after_suit(analysis, opening_bid, opener_rebid, context)
        
        # Fallback
        return "pass"
    
    def _make_responder_rebid_after_2nt_response(self, analysis: HandAnalysis, opening_bid: str, opener_rebid: str) -> str:
        """Make responder rebid after 2NT response and opener's rebid."""
        # Invitational bids (11-12 points)
        if analysis.hcp >= 11:
            # 2NT invitation
            if analysis.balanced:
                return "2NT"
            
            # Raise of opener's rebid suit
            if analysis.suit_lengths.get(opener_rebid[1], 0) >= 4:
                return f"3{opener_rebid[1]}"
            
            # Raise of original suit
            if analysis.suit_lengths.get(opening_bid[1], 0) >= 4:
                return f"3{opening_bid[1]}"
        
        # Signoff in partscore (6-10 points)
        if analysis.hcp < 11:
            # Preference for original suit
            if analysis.suit_lengths.get(opening_bid[1], 0) >= 2:
                return f"2{opening_bid[1]}"
            
            # Preference for opener's rebid suit
            if analysis.suit_lengths.get(opener_rebid[1], 0) >= 2:
                return f"2{opener_rebid[1]}"
            
            return "pass"
        
        return "pass"
    
    def _make_responder_rebid_after_1nt(self, analysis: HandAnalysis, opening_bid: str) -> str:
        """Make responder rebid after opener's 1NT rebid."""
        # Game force with new suit (13+ points)
        if analysis.hcp >= 13:
            for suit in ['C', 'D', 'H', 'S']:
                if analysis.suit_lengths.get(suit, 0) >= 5:
                    return f"3{suit}"
        
        # Invitational raise (11-12 points)
        if analysis.hcp >= 11:
            for suit in ['C', 'D', 'H', 'S']:
                if analysis.suit_lengths.get(suit, 0) >= 5:
                    return f"3{suit}"
        
        # Signoff in game
        if analysis.hcp >= 15:
            return "3NT"
        
        # Non-forcing new suit (5+ cards)
        for suit in ['C', 'D', 'H', 'S']:
            if analysis.suit_lengths.get(suit, 0) >= 5:
                return f"2{suit}"
        
        return "pass"
    
    def _make_responder_rebid_after_suit(self, analysis: HandAnalysis, opening_bid: str, opener_rebid: str, context: BiddingContext) -> str:
        """Make responder rebid after opener's suit rebid."""
        # Get responder's original response
        responder_original_response = context.bidding_sequence[-2].bid if len(context.bidding_sequence) >= 2 else None
        
        # Game force with new suit (13+ points)
        if analysis.hcp >= 13:
            for suit in ['C', 'D', 'H', 'S']:
                if analysis.suit_lengths.get(suit, 0) >= 5:
                    return f"3{suit}"
        
        # Invitational bids (11-12 points)
        if analysis.hcp >= 11:
            # Check for fourth suit forcing first (highest priority for 11-12 points)
            if self._is_fourth_suit_forcing(opening_bid, opener_rebid):
                fourth_suit = self._get_fourth_suit(opening_bid, opener_rebid)
                return fourth_suit
            
            # 2NT invitation
            if analysis.balanced:
                return "2NT"
            
            # Raise of original suit
            if analysis.suit_lengths.get(opening_bid[1], 0) >= 4:
                return f"3{opening_bid[1]}"
            
            # Raise of opener's rebid suit
            if analysis.suit_lengths.get(opener_rebid[1], 0) >= 4:
                return f"3{opener_rebid[1]}"
            
            # New suit at 3-level (invitational)
            for suit in ['C', 'D', 'H', 'S']:
                if suit != opening_bid[1] and suit != opener_rebid[1] and analysis.suit_lengths.get(suit, 0) >= 4:
                    return f"3{suit}"
        
        # Signoff in partscore (6-10 points)
        if analysis.hcp < 11:
            # Check if we have a preference based on the original response
            # If responder originally bid a suit, prefer that suit
            if responder_original_response and responder_original_response[1] in ['C', 'D', 'H', 'S']:
                if analysis.suit_lengths.get(responder_original_response[1], 0) >= 2:
                    return f"2{responder_original_response[1]}"
            
            # Preference for original suit (higher priority)
            if analysis.suit_lengths.get(opening_bid[1], 0) >= 2:
                return f"2{opening_bid[1]}"
            
            # Preference for opener's rebid suit
            if analysis.suit_lengths.get(opener_rebid[1], 0) >= 2:
                return f"2{opener_rebid[1]}"
            
            return "pass"
        
        return "pass"
    
    def _is_fourth_suit_forcing(self, opening_bid: str, opener_rebid: str) -> bool:
        """Check if this is a 4th suit forcing situation."""
        # 4th suit forcing only applies in very specific sequences
        # The classic example is: 1H-1S-2C where responder can bid 2D as fourth suit forcing
        # This creates a gap where diamonds (the fourth suit) can be bid artificially
        
        # Check if opener rebid a suit
        if opener_rebid[1] not in ['C', 'D', 'H', 'S']:
            return False
            
        suits_bid = {opening_bid[1], opener_rebid[1]}
        if len(suits_bid) != 2:
            return False
            
        # Fourth suit forcing occurs when there's a gap in the bidding that allows
        # responder to bid a suit that hasn't been mentioned yet
        # The specific pattern is: opener opens major, responder bids other major,
        # opener rebids lowest suit (clubs), creating a gap for diamonds
        
        # Only allow fourth suit forcing in the specific sequence: 1H-1S-2C or 1S-1H-2C
        # where clubs is the lowest suit and creates a gap for diamonds
        if (opening_bid in ["1H", "1S"] and opener_rebid == "2C"):
            return True
            
        return False
    
    def _get_fourth_suit(self, opening_bid: str, opener_rebid: str) -> str:
        """Get the 4th suit for forcing bid."""
        suits_bid = {opening_bid[1], opener_rebid[1]}
        all_suits = ['C', 'D', 'H', 'S']
        fourth_suit = [suit for suit in all_suits if suit not in suits_bid][0]
        return f"2{fourth_suit}"
    
    def _is_competitive_bid(self, context: BiddingContext) -> bool:
        """Check if this is a competitive bid (after opponent's bid)."""
        if len(context.bidding_sequence) < 1:
            return False
            
        # Check if there are any opponent bids
        opponent_bids = [bid for bid in context.bidding_sequence 
                        if bid.seat != context.current_seat and bid.bid != 'pass']
        return len(opponent_bids) > 0
    
    def _make_competitive_bid(self, context: BiddingContext) -> str:
        """Make a competitive bid after opponent's bid."""
        # For now, just return pass - competitive bidding is complex
        return "pass"
    
    def _make_opening_bid(self, context: BiddingContext) -> str:
        """Make an opening bid according to SAYC system."""
        analysis = context.hand_analysis
        
        # Check for 3NT opening first (25-27 HCP, balanced)
        if self._is_3nt_opening(analysis):
            return "3NT"
        
        # Check for 2NT opening (20-21 HCP, balanced)
        if self._is_2nt_opening(analysis):
            return "2NT"
        
        # Check for 1NT opening (15-17 HCP, balanced)
        if self._is_1nt_opening(analysis):
            return "1NT"
        
        # Check for strong 2C opening (22+ HCP or 9+ tricks)
        if self._is_2c_opening(analysis):
            return "2C"
        
        # Check for preemptive bids (3-level) - check before weak two
        if self._is_3c_opening(analysis):
            return "3C"
        if self._is_3d_opening(analysis):
            return "3D"
        if self._is_3h_opening(analysis):
            return "3H"
        if self._is_3s_opening(analysis):
            return "3S"
        
        # Check for weak two bids (5-11 HCP, 6-card suit)
        if self._is_2d_opening(analysis):
            return "2D"
        if self._is_2h_opening(analysis):
            return "2H"
        if self._is_2s_opening(analysis):
            return "2S"
        
        # Check for one-level suit openings (12+ HCP) - check majors first
        if self._is_1h_opening(analysis):
            return "1H"
        if self._is_1s_opening(analysis):
            return "1S"
        if self._is_1d_opening(analysis):
            return "1D"
        if self._is_1c_opening(analysis):
            return "1C"
        
        # No opening bid found
        return "pass"
    
    def _is_1nt_opening(self, analysis: HandAnalysis) -> bool:
        """1NT = 15-17 HCP, balanced (4333, 4432, or 5332 with 5-card minor)"""
        if not (15 <= analysis.hcp <= 17):
            return False
        
        # Check for balanced distribution
        if not analysis.balanced:
            return False
        
        # Check for 5-card major (don't open 1NT with 5+ major)
        if analysis.suit_lengths.get('H', 0) >= 5 or analysis.suit_lengths.get('S', 0) >= 5:
            return False
        
        return True
    
    def _is_2nt_opening(self, analysis: HandAnalysis) -> bool:
        """2NT = 20-21 HCP, balanced"""
        if not (20 <= analysis.hcp <= 21):
            return False
        
        # Check for balanced distribution
        if not analysis.balanced:
            return False
        
        # Check for 5-card major (don't open 2NT with 5+ major)
        if analysis.suit_lengths.get('H', 0) >= 5 or analysis.suit_lengths.get('S', 0) >= 5:
            return False
        
        return True
    
    def _is_3nt_opening(self, analysis: HandAnalysis) -> bool:
        """3NT = 25-27 HCP, balanced"""
        if not (25 <= analysis.hcp <= 27):
            return False
        
        # Check for balanced distribution
        if not analysis.balanced:
            return False
        
        return True
    
    def _is_2c_opening(self, analysis: HandAnalysis) -> bool:
        """2C = 22+ HCP or 9+ tricks (strong artificial opening)"""
        # 22+ HCP - this is the clear case for 2C opening
        if analysis.hcp >= 22:
            return True
        
        # For hands with 20-21 HCP, they should open 2NT if balanced
        # Only open 2C if unbalanced with very strong playing strength
        # This is a simplified implementation - in practice, you'd need more sophisticated evaluation
        if analysis.hcp >= 20 and not analysis.balanced:
            return True
        
        return False
    
    def _is_2d_opening(self, analysis: HandAnalysis) -> bool:
        """2D = 5-11 HCP, 6-card diamond suit"""
        if not (5 <= analysis.hcp <= 11):
            return False
        
        if analysis.suit_lengths.get('D', 0) < 6:
            return False
        
        # Should not have 4+ cards in a major side suit (unless 3rd seat)
        # For now, we'll implement basic version
        return True
    
    def _is_2h_opening(self, analysis: HandAnalysis) -> bool:
        """2H = 5-11 HCP, 6-card heart suit"""
        if not (5 <= analysis.hcp <= 11):
            return False
        
        if analysis.suit_lengths.get('H', 0) < 6:
            return False
        
        return True
    
    def _is_2s_opening(self, analysis: HandAnalysis) -> bool:
        """2S = 5-11 HCP, 6-card spade suit"""
        if not (5 <= analysis.hcp <= 11):
            return False
        
        if analysis.suit_lengths.get('S', 0) < 6:
            return False
        
        return True
    
    def _is_3c_opening(self, analysis: HandAnalysis) -> bool:
        """3C = preemptive with 7+ clubs"""
        if analysis.suit_lengths.get('C', 0) < 7:
            return False
        
        # Preemptive - should be weak
        if analysis.hcp > 10:
            return False
        
        return True
    
    def _is_3d_opening(self, analysis: HandAnalysis) -> bool:
        """3D = preemptive with 7+ diamonds"""
        if analysis.suit_lengths.get('D', 0) < 7:
            return False
        
        # Preemptive - should be weak
        if analysis.hcp > 10:
            return False
        
        return True
    
    def _is_3h_opening(self, analysis: HandAnalysis) -> bool:
        """3H = preemptive with 7+ hearts"""
        if analysis.suit_lengths.get('H', 0) < 7:
            return False
        
        # Preemptive - should be weak
        if analysis.hcp > 10:
            return False
        
        return True
    
    def _is_3s_opening(self, analysis: HandAnalysis) -> bool:
        """3S = preemptive with 7+ spades"""
        if analysis.suit_lengths.get('S', 0) < 7:
            return False
        
        # Preemptive - should be weak
        if analysis.hcp > 10:
            return False
        
        return True
    
    def _is_1c_opening(self, analysis: HandAnalysis) -> bool:
        """1C = 12+ HCP, longest suit is clubs, or 3-3 in minors"""
        if analysis.hcp < 12:
            return False
        
        # Check if clubs is the longest suit
        max_length = max(analysis.suit_lengths.values())
        if analysis.suit_lengths.get('C', 0) == max_length:
            return True
        
        # Check for 3-3 in minors
        if (analysis.suit_lengths.get('C', 0) == 3 and 
            analysis.suit_lengths.get('D', 0) == 3):
            return True
        
        return False
    
    def _is_1d_opening(self, analysis: HandAnalysis) -> bool:
        """1D = 12+ HCP, longest suit is diamonds, or 4-4 in minors"""
        if analysis.hcp < 12:
            return False
        
        # Check if diamonds is the longest suit
        max_length = max(analysis.suit_lengths.values())
        if analysis.suit_lengths.get('D', 0) == max_length:
            return True
        
        # Check for 4-4 in minors
        if (analysis.suit_lengths.get('C', 0) == 4 and 
            analysis.suit_lengths.get('D', 0) == 4):
            return True
        
        return False
    
    def _is_1h_opening(self, analysis: HandAnalysis) -> bool:
        """1H = 12+ HCP, 5+ hearts"""
        if analysis.hcp < 12:
            return False
        
        if analysis.suit_lengths.get('H', 0) < 5:
            return False
        
        return True
    
    def _is_1s_opening(self, analysis: HandAnalysis) -> bool:
        """1S = 12+ HCP, 5+ spades"""
        if analysis.hcp < 12:
            return False
        
        if analysis.suit_lengths.get('S', 0) < 5:
            return False
        
        return True
    
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
        """Make a response bid to partner's opening."""
        analysis = context.hand_analysis
        opening_bid = self._get_opening_bid(context)
        
        if not opening_bid:
            return "pass"
        
        # Handle 1NT responses
        if opening_bid.bid == "1NT":
            return self._make_1nt_response(context)
        
        # Handle 2NT responses
        elif opening_bid.bid == "2NT":
            return self._make_2nt_response(context)
        
        # Handle 3NT responses
        elif opening_bid.bid == "3NT":
            return self._make_3nt_response(context)
        
        # Handle 2C responses
        elif opening_bid.bid == "2C":
            return self._make_2c_response(context)
        
        # Handle suit opening responses
        elif opening_bid.bid in ["1C", "1D", "1H", "1S"]:
            return self._make_suit_response(context)
        
        # Handle weak two responses
        elif opening_bid.bid in ["2D", "2H", "2S"]:
            return self._make_weak_two_response(context)
        
        # Handle preemptive responses
        elif opening_bid.bid in ["3C", "3D", "3H", "3S"]:
            return self._make_preemptive_response(context)
        
        return "pass"
    
    def _make_rebid_bid(self, context: BiddingContext) -> str:
        """Make a rebid (to be implemented in next section)."""
        # TODO: Implement rebid logic
        return "pass"
    
    def _make_competitive_bid(self, context: BiddingContext) -> str:
        """Make a competitive bid (to be implemented in next section)."""
        # TODO: Implement competitive bidding logic
        return "pass"
    
    def _make_1nt_response(self, context: BiddingContext) -> str:
        """Make a response to 1NT opening."""
        analysis = context.hand_analysis
        
        # Check highest priority responses first
        
        # 4NT quantitative (invites 6NT) - highest priority
        if self._is_4nt_quantitative(analysis):
            return "4NT"
        
        # 4C Gerber (asking for aces)
        if self._is_4c_gerber(analysis):
            return "4C"
        
        # 3H, 3S responses (6+ in suit, invites slam)
        if self._is_3h_response(analysis):
            return "3H"
        if self._is_3s_response(analysis):
            return "3S"
        
        # 3C, 3D responses (6+ in suit, invites 3NT)
        if self._is_3c_response(analysis):
            return "3C"
        if self._is_3d_response(analysis):
            return "3D"
        
        # 2S response (requires 1NT bidder to rebid 3C) - special case
        if self._is_2s_response(analysis):
            return "2S"
        
        # Jacoby transfers
        if self._is_2d_transfer(analysis):
            return "2D"  # Transfer to hearts
        if self._is_2h_transfer(analysis):
            return "2H"  # Transfer to spades
        
        # Stayman (2C)
        if self._is_stayman(analysis):
            return "2C"
        
        # 2NT response (5+ cards in suit, non-forcing)
        if self._is_2nt_response(analysis):
            return "2NT"
        
        # Pass with weak hand
        return "pass"
    
    def _is_2s_response(self, analysis: HandAnalysis) -> bool:
        """2S response - asks opener to choose between minors (3C or 3D)."""
        # This response asks the 1NT opener to choose between 3C or 3D
        # Used when responder has a long minor suit and wants opener to choose
        max_length = max(analysis.suit_lengths.values())
        longest_suit = max(analysis.suit_lengths, key=analysis.suit_lengths.get)
        
        return (analysis.hcp >= 8 and 
                max_length >= 5 and
                longest_suit in ['C', 'D'])  # Long minor suit
    
    def _is_2d_transfer(self, analysis: HandAnalysis) -> bool:
        """2D = Jacoby transfer to hearts (5+ hearts)."""
        return (analysis.hcp >= 8 and 
                analysis.suit_lengths.get('H', 0) >= 5 and
                analysis.suit_lengths.get('S', 0) < 4)  # Don't use transfer with 4+ spades
    
    def _is_2h_transfer(self, analysis: HandAnalysis) -> bool:
        """2H = Jacoby transfer to spades (5+ spades)."""
        return (analysis.hcp >= 8 and 
                analysis.suit_lengths.get('S', 0) >= 5)
    
    def _is_stayman(self, analysis: HandAnalysis) -> bool:
        """2C = Stayman (requires 8+ HCP and doubleton, singleton, or void)."""
        # Check for singleton, void, or doubleton
        has_shortness = any(length <= 2 for length in analysis.suit_lengths.values())
        
        # Stayman requires 8+ HCP and either shortness or 4+ in a major
        return (analysis.hcp >= 8 and 
                (has_shortness or 
                 analysis.suit_lengths.get('H', 0) >= 4 or 
                 analysis.suit_lengths.get('S', 0) >= 4))
    
    def _is_3c_response(self, analysis: HandAnalysis) -> bool:
        """3C = 6+ clubs, invites 3NT."""
        return (analysis.hcp >= 8 and 
                analysis.suit_lengths.get('C', 0) >= 6)
    
    def _is_3d_response(self, analysis: HandAnalysis) -> bool:
        """3D = 6+ diamonds, invites 3NT."""
        return (analysis.hcp >= 8 and 
                analysis.suit_lengths.get('D', 0) >= 6)
    
    def _is_3h_response(self, analysis: HandAnalysis) -> bool:
        """3H = 6+ hearts, invites slam."""
        return (analysis.hcp >= 8 and 
                analysis.suit_lengths.get('H', 0) >= 6)
    
    def _is_3s_response(self, analysis: HandAnalysis) -> bool:
        """3S = 6+ spades, invites slam."""
        return (analysis.hcp >= 8 and 
                analysis.suit_lengths.get('S', 0) >= 6)
    
    def _is_4c_gerber(self, analysis: HandAnalysis) -> bool:
        """4C = Gerber (asking for aces)."""
        return analysis.hcp >= 15  # Strong enough for ace asking
    
    def _is_4nt_quantitative(self, analysis: HandAnalysis) -> bool:
        """4NT = Quantitative (invites 6NT)."""
        return 16 <= analysis.hcp <= 17  # Invitational range (exclude 15 HCP)
    
    def _is_2nt_response(self, analysis: HandAnalysis) -> bool:
        """2NT = 5+ cards in suit, non-forcing."""
        # This is a general response for 5+ card suits
        max_length = max(analysis.suit_lengths.values())
        return (analysis.hcp >= 6 and 
                max_length >= 5 and
                analysis.hcp < 8 and
                not (analysis.suit_lengths.get('H', 0) >= 5 or 
                     analysis.suit_lengths.get('S', 0) >= 5) and
                not (analysis.suit_lengths.get('H', 0) >= 4 or 
                     analysis.suit_lengths.get('S', 0) >= 4))  # Not strong enough for Stayman
    
    def _make_2nt_response(self, context: BiddingContext) -> str:
        """Make a response to 2NT opening."""
        analysis = context.hand_analysis
        
        # 3C Stayman
        if self._is_stayman(analysis):
            return "3C"
        
        # 3D, 3H Jacoby transfers
        if self._is_2d_transfer(analysis):
            return "3D"  # Transfer to hearts
        if self._is_2h_transfer(analysis):
            return "3H"  # Transfer to spades
        
        # 4C Gerber
        if self._is_4c_gerber(analysis):
            return "4C"
        
        # 4NT quantitative
        if self._is_4nt_quantitative(analysis):
            return "4NT"
        
        return "pass"
    
    def _make_3nt_response(self, context: BiddingContext) -> str:
        """Make a response to 3NT opening."""
        analysis = context.hand_analysis
        
        # 4C Stayman (not Gerber)
        if self._is_stayman(analysis):
            return "4C"
        
        # 4D, 4H Jacoby transfers
        if self._is_2d_transfer(analysis):
            return "4D"  # Transfer to hearts
        if self._is_2h_transfer(analysis):
            return "4H"  # Transfer to spades
        
        # 4NT Blackwood (not quantitative)
        if analysis.hcp >= 15:
            return "4NT"
        
        return "pass"
    
    def _make_2c_response(self, context: BiddingContext) -> str:
        """Make a response to 2C opening."""
        # TODO: Implement 2C responses
        return "pass"
    
    def _make_suit_response(self, context: BiddingContext) -> str:
        """Make a response to suit opening (1C, 1D, 1H, 1S)."""
        analysis = context.hand_analysis
        opening_bid = self._get_opening_bid(context)
        
        if not opening_bid:
            return "pass"
        
        opening_suit = opening_bid.bid[1]  # Get suit from bid (C, D, H, S)
        
        # Handle major suit responses (1H, 1S)
        if opening_suit in ['H', 'S']:
            return self._make_major_suit_response(context, opening_suit)
        
        # Handle minor suit responses (1C, 1D)
        else:
            return self._make_minor_suit_response(context, opening_suit)
    
    def _make_major_suit_response(self, context: BiddingContext, opening_suit: str) -> str:
        """Make response to major suit opening (1H or 1S)."""
        analysis = context.hand_analysis
        
        # 4H/4S = Preemptive raise (5+ cards, singleton/void)
        if self._is_preemptive_raise(analysis, opening_suit):
            return f"4{opening_suit}"
        
        # 3NT = 15-17 HCP, balanced, 2 cards in opener's suit
        if self._is_3nt_response_major(analysis, opening_suit):
            return "3NT"
        
        # 2NT = Jacoby 2NT (13+ points, 3+ cards in opener's suit)
        if self._is_jacoby_2nt(analysis, opening_suit):
            return "2NT"
        
        # 3H/3S = Limit raise (10-12 points, 3+ cards in opener's suit)
        if self._is_limit_raise(analysis, opening_suit):
            return f"3{opening_suit}"
        
        # 2H/2S = Simple raise (6-10 points, 3+ cards in opener's suit)
        if self._is_simple_raise(analysis, opening_suit):
            return f"2{opening_suit}"
        
        # 2C/2D = New suit response (11+ points, 4+ cards)
        if self._is_new_suit_response(analysis, opening_suit):
            return self._get_new_suit_bid(analysis, opening_suit)
        
        # 1NT = 6-10 points, denies 4+ in other major or 3+ in opener's suit
        if self._is_1nt_response_major(analysis, opening_suit):
            return "1NT"
        
        # 1S response to 1H (6+ points, 4+ spades, one-round force)
        if opening_suit == 'H' and self._is_1s_response_to_1h(analysis):
            return "1S"
        
        # Pass with weak hand
        return "pass"
    
    def _make_minor_suit_response(self, context: BiddingContext, opening_suit: str) -> str:
        """Make response to minor suit opening (1C or 1D)."""
        analysis = context.hand_analysis
        
        # 2NT = 13-15 points, balanced
        if self._is_2nt_response_minor(analysis):
            return "2NT"
        
        # 1H/1S = Major suit response (6+ points, 4+ cards)
        if self._is_major_response_to_minor(analysis):
            return self._get_major_response_bid(analysis)
        
        # 1D response to 1C (6+ points, 4+ diamonds)
        if opening_suit == 'C' and self._is_1d_response_to_1c(analysis):
            return "1D"
        
        # 1NT = 6-12 points, balanced
        if self._is_1nt_response_minor(analysis):
            return "1NT"
        
        # 2C/2D = Raise opener's minor (6-10 points, 3+ cards)
        if self._is_minor_raise(analysis, opening_suit):
            return f"2{opening_suit}"
        
        # Pass with weak hand
        return "pass"
    
    def _make_weak_two_response(self, context: BiddingContext) -> str:
        """Make a response to weak two opening."""
        # TODO: Implement weak two responses
        return "pass"
    
    def _make_preemptive_response(self, context: BiddingContext) -> str:
        """Make a response to preemptive opening."""
        # TODO: Implement preemptive responses
        return "pass"
    
    # Major suit response helper methods
    def _is_preemptive_raise(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """4H/4S = Preemptive raise (5+ cards, singleton/void)."""
        return (analysis.hcp < 10 and 
                analysis.suit_lengths.get(opening_suit, 0) >= 5 and
                any(length <= 1 for length in analysis.suit_lengths.values()))
    
    def _is_3nt_response_major(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """3NT = 15-17 HCP, balanced, 2 cards in opener's suit."""
        return (15 <= analysis.hcp <= 17 and 
                analysis.balanced and
                analysis.suit_lengths.get(opening_suit, 0) == 2)
    
    def _is_jacoby_2nt(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """2NT = Jacoby 2NT (13+ points, 3+ cards in opener's suit)."""
        return (analysis.hcp >= 13 and 
                analysis.suit_lengths.get(opening_suit, 0) >= 3)
    
    def _is_limit_raise(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """3H/3S = Limit raise (10-12 points, 3+ cards in opener's suit)."""
        return (10 <= analysis.hcp <= 12 and 
                analysis.suit_lengths.get(opening_suit, 0) >= 3)
    
    def _is_simple_raise(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """2H/2S = Simple raise (6-10 points, 3+ cards in opener's suit)."""
        return (6 <= analysis.hcp <= 10 and 
                analysis.suit_lengths.get(opening_suit, 0) >= 3)
    
    def _is_new_suit_response(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """2C/2D = New suit response (11+ points, 4+ cards)."""
        return (analysis.hcp >= 11 and 
                max(analysis.suit_lengths.values()) >= 4)
    
    def _get_new_suit_bid(self, analysis: HandAnalysis, opening_suit: str) -> str:
        """Get the new suit bid for 2-level response."""
        # Find the longest suit that's not the opening suit
        other_suits = {suit: length for suit, length in analysis.suit_lengths.items() 
                      if suit != opening_suit and length >= 4}
        if other_suits:
            longest_other_suit = max(other_suits, key=other_suits.get)
            return f"2{longest_other_suit}"
        return "pass"
    
    def _is_1nt_response_major(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """1NT = 6-10 points, denies 4+ in other major or 3+ in opener's suit."""
        other_major = 'S' if opening_suit == 'H' else 'H'
        return (6 <= analysis.hcp <= 10 and
                analysis.suit_lengths.get(other_major, 0) < 4 and
                analysis.suit_lengths.get(opening_suit, 0) < 3)
    
    def _is_1s_response_to_1h(self, analysis: HandAnalysis) -> bool:
        """1S response to 1H (6+ points, 4+ spades, one-round force)."""
        return (analysis.hcp >= 6 and 
                analysis.suit_lengths.get('S', 0) >= 4)
    
    # Minor suit response helper methods
    def _is_2nt_response_minor(self, analysis: HandAnalysis) -> bool:
        """2NT = 13-15 points, balanced."""
        return (13 <= analysis.hcp <= 15 and analysis.balanced)
    
    def _is_1nt_response_minor(self, analysis: HandAnalysis) -> bool:
        """1NT = 6-12 points, balanced."""
        return (6 <= analysis.hcp <= 12 and analysis.balanced)
    
    def _is_minor_raise(self, analysis: HandAnalysis, opening_suit: str) -> bool:
        """2C/2D = Raise opener's minor (6-10 points, 3+ cards)."""
        return (6 <= analysis.hcp <= 10 and 
                analysis.suit_lengths.get(opening_suit, 0) >= 3)
    
    def _is_major_response_to_minor(self, analysis: HandAnalysis) -> bool:
        """1H/1S = Major suit response (6+ points, 4+ cards)."""
        return (analysis.hcp >= 6 and 
                (analysis.suit_lengths.get('H', 0) >= 4 or 
                 analysis.suit_lengths.get('S', 0) >= 4))
    
    def _get_major_response_bid(self, analysis: HandAnalysis) -> str:
        """Get the major suit response bid."""
        if analysis.suit_lengths.get('H', 0) >= 4:
            return "1H"
        elif analysis.suit_lengths.get('S', 0) >= 4:
            return "1S"
        return "pass"
    
    def _is_1d_response_to_1c(self, analysis: HandAnalysis) -> bool:
        """1D response to 1C (6+ points, 4+ diamonds)."""
        return (analysis.hcp >= 6 and 
                analysis.suit_lengths.get('D', 0) >= 4)
    
    def _make_overcall(self, context: BiddingContext) -> str:
        """Make an overcall after opponent's opening bid."""
        analysis = context.hand_analysis
        opening_bid = context.bidding_sequence[0].bid
        
        # Check highest priority overcalls first
        
        # Penalty double over game-level openings
        if self._is_penalty_double(analysis, opening_bid):
            return "X"
        
        # Michaels cuebid - highest priority for 5-5 hands
        if self._is_michaels_cuebid(analysis, opening_bid):
            return self._get_michaels_cuebid(opening_bid)
        
        # Unusual notrump (2NT)
        if self._is_unusual_2nt(analysis, opening_bid):
            return "2NT"
        
        # Takeout double over partscore openings
        if self._is_takeout_double(analysis, opening_bid):
            return "X"
        
        # Jump suit overcalls (preemptive)
        jump_bid = self._get_jump_overcall(analysis, opening_bid)
        if jump_bid:
            return jump_bid
        
        # 1NT overcall
        if self._is_1nt_overcall(analysis, opening_bid):
            return "1NT"
        
        # Non-jump suit overcalls
        suit_bid = self._get_suit_overcall(analysis, opening_bid)
        if suit_bid:
            return suit_bid
        
        # Balancing/reopening
        if self._is_balancing_position(context):
            balancing_bid = self._get_balancing_bid(analysis, opening_bid)
            if balancing_bid:
                return balancing_bid
        
        # Pass with weak hand
        return "pass"
    
    def _is_penalty_double(self, analysis: HandAnalysis, opening_bid: str) -> bool:
        """Check if this is a penalty double over game-level opening."""
        if not opening_bid.startswith(('4', '5', '6', '7')):
            return False
        
        # Need strong defensive hand with length in opponent's suit
        suit = opening_bid[1]
        suit_length = analysis.suit_lengths.get(suit, 0)
        
        return (analysis.hcp >= 15 and 
                suit_length >= 4 and
                analysis.stoppers.get(suit, False))
    
    def _is_takeout_double(self, analysis: HandAnalysis, opening_bid: str) -> bool:
        """Check if this is a takeout double over partscore opening."""
        if opening_bid.startswith(('4', '5', '6', '7')):
            return False  # Game-level openings use penalty doubles
        
        # Need 8+ points, short in opponent's suit, support for unbid suits
        suit = opening_bid[1]
        suit_length = analysis.suit_lengths.get(suit, 0)
        
        # Count support for unbid suits
        unbid_suits = ['C', 'D', 'H', 'S']
        unbid_suits.remove(suit)
        support_count = sum(1 for s in unbid_suits if analysis.suit_lengths.get(s, 0) >= 3)
        
        # Takeout double requires very short in opponent's suit (singleton or void)
        return (analysis.hcp >= 8 and 
                suit_length <= 1 and
                support_count >= 2)
    
    def _is_michaels_cuebid(self, analysis: HandAnalysis, opening_bid: str) -> bool:
        """Check if this is a Michaels cuebid."""
        # Only over single suit openings (no previous bids by partner)
        
        suit = opening_bid[1]
        
        if suit in ['C', 'D']:  # Minor opening - show majors
            return (analysis.hcp >= 8 and
                    analysis.suit_lengths.get('H', 0) >= 5 and
                    analysis.suit_lengths.get('S', 0) >= 5)
        else:  # Major opening - show other major + minor
            other_major = 'H' if suit == 'S' else 'S'
            return (analysis.hcp >= 10 and
                    analysis.suit_lengths.get(other_major, 0) >= 5 and
                    (analysis.suit_lengths.get('C', 0) >= 5 or 
                     analysis.suit_lengths.get('D', 0) >= 5))
    
    def _get_michaels_cuebid(self, opening_bid: str) -> str:
        """Get the Michaels cuebid (cuebid opponent's suit at 2-level)."""
        suit = opening_bid[1]
        return f"2{suit}"
    
    def _is_unusual_2nt(self, analysis: HandAnalysis, opening_bid: str) -> bool:
        """Check if this is unusual 2NT showing 5-5 in two lowest unbid suits."""
        if not opening_bid.startswith('1'):
            return False
        
        suit = opening_bid[1]
        
        # Determine the two lowest unbid suits
        if suit == 'C':
            unbid_suits = ['D', 'H']
        elif suit == 'D':
            unbid_suits = ['H', 'S']
        elif suit == 'H':
            unbid_suits = ['C', 'D']
        else:  # S
            unbid_suits = ['C', 'D']
        
        # Check for 5-5 in the two lowest unbid suits
        suit1_length = analysis.suit_lengths.get(unbid_suits[0], 0)
        suit2_length = analysis.suit_lengths.get(unbid_suits[1], 0)
        
        return (suit1_length >= 5 and suit2_length >= 5)
    
    def _get_jump_overcall(self, analysis: HandAnalysis, opening_bid: str) -> Optional[str]:
        """Get jump overcall if applicable (preemptive)."""
        if not opening_bid.startswith('1'):
            return None
        
        # Find longest suit
        max_length = max(analysis.suit_lengths.values())
        longest_suit = max(analysis.suit_lengths, key=analysis.suit_lengths.get)
        
        # Check if this is a preemptive hand
        if (max_length >= 6 and analysis.hcp <= 10):
            if longest_suit == 'S' and max_length >= 6:
                return "2S"
            elif longest_suit == 'H' and max_length >= 6:
                return "2H"
            elif longest_suit == 'D' and max_length >= 6:
                return "2D"
            elif longest_suit == 'C' and max_length >= 7:
                return "3C"
            elif longest_suit == 'D' and max_length >= 7:
                return "3D"
        
        return None
    
    def _is_1nt_overcall(self, analysis: HandAnalysis, opening_bid: str) -> bool:
        """Check if this is a 1NT overcall."""
        if not opening_bid.startswith('1'):
            return False
        
        suit = opening_bid[1]
        
        return (analysis.hcp >= 15 and 
                analysis.hcp <= 18 and
                analysis.balanced and
                analysis.stoppers.get(suit, False))
    
    def _get_suit_overcall(self, analysis: HandAnalysis, opening_bid: str) -> Optional[str]:
        """Get non-jump suit overcall if applicable."""
        if not opening_bid.startswith('1'):
            return None
        
        suit = opening_bid[1]
        
        # Find best suit to overcall, prioritizing higher suits
        for overcall_suit in ['S', 'H', 'D', 'C']:
            if overcall_suit == suit:
                continue  # Don't overcall opponent's suit
            
            suit_length = analysis.suit_lengths.get(overcall_suit, 0)
            
            # 2-level overcall takes priority over 1-level
            if suit_length >= 6 and analysis.hcp >= 10:
                return f"2{overcall_suit}"
            elif suit_length >= 5 and analysis.hcp >= 8:
                return f"1{overcall_suit}"
        
        return None
    
    def _is_balancing_position(self, context: BiddingContext) -> bool:
        """Check if this is a balancing position."""
        if len(context.bidding_sequence) < 2:
            return False
        
        # Balancing if opponent opened, partner passed, and it's our turn
        # Partner is the seat that's not current_seat and not the opener
        opener_seat = context.bidding_sequence[0].seat
        partner_seat = None
        for seat in ['N', 'E', 'S', 'W']:
            if seat != context.current_seat and seat != opener_seat:
                partner_seat = seat
                break
        
        return (opener_seat != context.current_seat and
                len(context.bidding_sequence) >= 2 and
                context.bidding_sequence[1].seat == partner_seat and
                context.bidding_sequence[1].bid == "pass")
    
    def _get_balancing_bid(self, analysis: HandAnalysis, opening_bid: str) -> Optional[str]:
        """Get balancing bid if applicable."""
        if not opening_bid.startswith('1'):
            return None
        
        # 1NT balancing shows 10-15 points
        if (analysis.hcp >= 10 and 
            analysis.hcp <= 15 and 
            analysis.balanced):
            return "1NT"
        
        # Other balancing bids same as direct seat but lighter
        suit_bid = self._get_suit_overcall(analysis, opening_bid)
        if suit_bid and analysis.hcp >= 6:  # Lighter requirements
            return suit_bid
        
        return None
