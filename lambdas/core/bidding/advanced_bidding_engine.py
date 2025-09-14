"""
Advanced Bidding Engine implementing the full Fantoni-Nunes system.

This engine uses the parsed algorithm rules from bridge_bidding_alg.txt
for intelligent bidding decisions based on the complete Fantoni-Nunes system.
"""

import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator, HandAnalysis
from core.bidding.bidding_parser import BiddingAlgorithmParser, BiddingRule, BiddingSequence


@dataclass
class BiddingDecision:
    """Represents a bidding decision with reasoning."""
    bid: str
    confidence: float
    reasoning: str
    rule_used: Optional[BiddingRule] = None


class AdvancedBiddingEngine:
    """Advanced bidding engine implementing full Fantoni-Nunes system."""
    
    def __init__(self, algorithm_file_path: str):
        self.hand_evaluator = HandEvaluator()
        self.parser = BiddingAlgorithmParser(algorithm_file_path)
        self.algorithm_rules = self.parser.parse_algorithm_file()
    
    def make_bid(self, hand: List[str], bidding_context: Dict) -> BiddingDecision:
        """
        Make an intelligent bid using the full Fantoni-Nunes system.
        
        Args:
            hand: List of cards
            bidding_context: Complete bidding context including previous bids, position, etc.
            
        Returns:
            BiddingDecision with bid, confidence, and reasoning
        """
        # Analyze hand
        hand_analysis = self.hand_evaluator.evaluate_hand(hand)
        analysis_dict = {
            'hcp': hand_analysis.hcp,
            'total_points': hand_analysis.total_points,
            'suit_lengths': hand_analysis.suit_lengths,
            'balanced': hand_analysis.balanced,
            'longest_suit': hand_analysis.longest_suit,
            'longest_suit_length': hand_analysis.longest_suit_length,
            'stoppers': hand_analysis.stoppers,
            'controls': hand_analysis.controls
        }
        
        # Determine if this is an opening bid or response
        if self._is_opening_bid(bidding_context):
            return self._make_opening_bid(hand, hand_analysis, analysis_dict, bidding_context)
        else:
            return self._make_response_bid(hand, hand_analysis, analysis_dict, bidding_context)
    
    def _is_opening_bid(self, context: Dict) -> bool:
        """Check if this should be an opening bid."""
        previous_bids = context.get('previous_bids', [])
        return len(previous_bids) == 0 or all(bid.get('bid') == 'pass' for bid in previous_bids)
    
    def _make_opening_bid(self, hand: List[str], analysis: HandAnalysis, 
                         analysis_dict: Dict, context: Dict) -> BiddingDecision:
        """Make an opening bid using the full algorithm."""
        
        # Try each opening bid in order of preference (preempts first for strong hands)
        opening_bids = ['3C', '3D', '3H', '3S', '3NT', '1C', '1D', '1H', '1S', '1NT', '2C', '2D', '2H', '2S', '2NT']
        
        for bid in opening_bids:
            rule = self.parser.find_matching_rule(analysis_dict, opening=bid)
            if rule:
                return BiddingDecision(
                    bid=bid,
                    confidence=0.9,
                    reasoning=f"Algorithm rule: {rule.description}",
                    rule_used=rule
                )
        
        # Fallback to pass
        return BiddingDecision(
            bid='pass',
            confidence=0.5,
            reasoning="No matching opening bid found"
        )
    
    def _make_response_bid(self, hand: List[str], analysis: HandAnalysis,
                          analysis_dict: Dict, context: Dict) -> BiddingDecision:
        """Make a response bid using the full algorithm."""
        
        # Find partner's last bid
        partner_last_bid = self._get_partner_last_bid(context)
        if not partner_last_bid:
            return BiddingDecision(bid='pass', confidence=0.5, reasoning="No partner bid found")
        
        # Get response rules for partner's opening
        response_rules = self.parser.get_response_rules(partner_last_bid)
        
        # Try each possible response
        for response, rule in response_rules.items():
            if self._rule_matches(rule, analysis_dict):
                return BiddingDecision(
                    bid=response,
                    confidence=0.8,
                    reasoning=f"Response to {partner_last_bid}: {rule.description}",
                    rule_used=rule
                )
        
        # Fallback to pass
        return BiddingDecision(
            bid='pass',
            confidence=0.4,
            reasoning=f"No suitable response to {partner_last_bid}"
        )
    
    
    def _get_partner_last_bid(self, context: Dict) -> Optional[str]:
        """Get partner's last non-pass bid."""
        previous_bids = context.get('previous_bids', [])
        current_seat = context.get('seat', 'North')
        
        # Find partner's bids
        partner_bids = []
        for bid in previous_bids:
            bidder_seat = bid.get('seat', '')
            if self._are_partners(current_seat, bidder_seat):
                partner_bids.append(bid)
        
        # Get last non-pass bid
        for bid in reversed(partner_bids):
            if bid.get('bid') != 'pass':
                return bid.get('bid')
        
        return None
    
    def _are_partners(self, seat1: str, seat2: str) -> bool:
        """Check if two seats are partners."""
        return ((seat1 in ['North', 'South'] and seat2 in ['North', 'South']) or
                (seat1 in ['East', 'West'] and seat2 in ['East', 'West']))
    
    def _rule_matches(self, rule: BiddingRule, analysis_dict: Dict) -> bool:
        """Check if a rule matches the hand analysis."""
        # Check HCP range
        if rule.hcp_range:
            hcp = analysis_dict.get('hcp', 0)
            if not (rule.hcp_range[0] <= hcp <= rule.hcp_range[1]):
                return False
        
        # Check suit requirements
        if rule.suit_requirements:
            suit_lengths = analysis_dict.get('suit_lengths', {})
            for suit, min_length in rule.suit_requirements.items():
                if suit_lengths.get(suit, 0) < min_length:
                    return False
        
        # Check balanced requirement
        if rule.balanced is not None:
            if analysis_dict.get('balanced', False) != rule.balanced:
                return False
        
        return True
    
    def get_hand_evaluation(self, hand: List[str]) -> Dict:
        """Get comprehensive hand evaluation."""
        analysis = self.hand_evaluator.evaluate_hand(hand)
        
        return {
            'hcp': analysis.hcp,
            'distribution_points': analysis.distribution_points,
            'total_points': analysis.total_points,
            'longest_suit': analysis.longest_suit,
            'longest_suit_length': analysis.longest_suit_length,
            'suit_lengths': analysis.suit_lengths,
            'balanced': analysis.balanced,
            'stoppers': analysis.stoppers,
            'controls': analysis.controls,
            'description': self.hand_evaluator.get_hand_description(hand)
        }
    
    def get_available_bids(self, hand: List[str], context: Dict) -> List[BiddingDecision]:
        """Get all possible bids for a hand with confidence scores."""
        analysis = self.hand_evaluator.evaluate_hand(hand)
        analysis_dict = {
            'hcp': analysis.hcp,
            'total_points': analysis.total_points,
            'suit_lengths': analysis.suit_lengths,
            'balanced': analysis.balanced,
            'longest_suit': analysis.longest_suit,
            'longest_suit_length': analysis.longest_suit_length,
            'stoppers': analysis.stoppers,
            'controls': analysis.controls
        }
        
        decisions = []
        
        if self._is_opening_bid(context):
            # Get all possible opening bids
            opening_rules = self.parser.get_opening_rules()
            for bid, rules in opening_rules.items():
                for rule in rules:
                    if self._rule_matches(rule, analysis_dict):
                        decision = BiddingDecision(
                            bid=bid,
                            confidence=0.8,
                            reasoning=rule.description,
                            rule_used=rule
                        )
                        decisions.append(decision)
        else:
            # Get all possible responses
            partner_bid = self._get_partner_last_bid(context)
            if partner_bid:
                response_rules = self.parser.get_response_rules(partner_bid)
                for response, rule in response_rules.items():
                    if self._rule_matches(rule, analysis_dict):
                        decision = BiddingDecision(
                            bid=response,
                            confidence=0.7,
                            reasoning=f"Response to {partner_bid}: {rule.description}",
                            rule_used=rule
                        )
                        decisions.append(decision)
        
        # Always include pass as an option
        decisions.append(BiddingDecision(
            bid='pass',
            confidence=0.3,
            reasoning="Conservative pass"
        ))
        
        return sorted(decisions, key=lambda x: x.confidence, reverse=True)
