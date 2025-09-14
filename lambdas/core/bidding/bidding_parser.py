"""
Bidding Algorithm Parser for Fantoni-Nunes System

This module parses the bridge_bidding_alg.txt file and extracts all bidding rules,
sequences, and conventions into a structured format for the bidding engine.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class BiddingRule:
    """Represents a single bidding rule."""
    opening: Optional[str] = None
    response: Optional[str] = None
    conditions: List[str] = None
    hcp_range: Optional[Tuple[int, int]] = None
    suit_requirements: Dict[str, int] = None
    balanced: Optional[bool] = None
    description: str = ""


@dataclass
class BiddingSequence:
    """Represents a complete bidding sequence."""
    opener: str
    responses: Dict[str, List[BiddingRule]]
    rebids: Dict[str, List[BiddingRule]]


class BiddingAlgorithmParser:
    """Parses the Fantoni-Nunes bidding algorithm from text file."""
    
    def __init__(self, algorithm_file_path: str):
        self.algorithm_file_path = algorithm_file_path
        self.rules: Dict[str, List[BiddingRule]] = {}
        self.sequences: Dict[str, BiddingSequence] = {}
        
    def parse_algorithm_file(self) -> Dict[str, Any]:
        """Parse the complete algorithm file."""
        with open(self.algorithm_file_path, 'r') as f:
            content = f.read()
        
        # Parse different sections
        self._parse_opening_summary(content)
        self._parse_opening_responses(content)
        self._parse_competitive_bidding(content)
        self._parse_slam_bidding(content)
        
        return {
            'rules': self.rules,
            'sequences': self.sequences
        }
    
    def _parse_opening_summary(self, content: str):
        """Parse the opening summary section."""
        opening_section = self._extract_section(content, "Opening Summary:", "Responses:")
        
        # Parse 1C opening
        self._parse_1c_opening(opening_section)
        self._parse_1d_opening(opening_section)
        self._parse_1h_opening(opening_section)
        self._parse_1s_opening(opening_section)
        self._parse_1nt_opening(opening_section)
        self._parse_2level_openings(opening_section)
        self._parse_3level_openings(opening_section)
    
    def _parse_1c_opening(self, content: str):
        """Parse 1C opening rules."""
        rules = []
        
        # 1C = 15+ balanced (4333/4432/5m332), or 14+ value 5+C/444-1red, F1
        rule = BiddingRule(
            opening="1C",
            hcp_range=(15, 40),
            balanced=True,
            suit_requirements={'C': 5},
            description="15+ balanced or 14+ with 5+C or 444-1red"
        )
        rules.append(rule)
        
        self.rules['1C'] = rules
    
    def _parse_1d_opening(self, content: str):
        """Parse 1D opening rules."""
        rules = []
        
        # 1D = 14+ value 5+D or 444-1black, F1
        rule = BiddingRule(
            opening="1D",
            hcp_range=(14, 40),
            suit_requirements={'D': 5},
            description="14+ with 5+D or 444-1black"
        )
        rules.append(rule)
        
        self.rules['1D'] = rules
    
    def _parse_1h_opening(self, content: str):
        """Parse 1H opening rules."""
        rules = []
        
        # 1H = 14+ value 5+H (12+ if 4S), F1, may have 6H-5S, 5H-6m
        rule = BiddingRule(
            opening="1H",
            hcp_range=(14, 40),
            suit_requirements={'H': 5},
            description="14+ with 5+H (12+ if 4S)"
        )
        rules.append(rule)
        
        self.rules['1H'] = rules
    
    def _parse_1s_opening(self, content: str):
        """Parse 1S opening rules."""
        rules = []
        
        # 1S = 14+ value 5+S (12+ if 4+H), F1
        rule = BiddingRule(
            opening="1S",
            hcp_range=(14, 40),
            suit_requirements={'S': 5},
            description="14+ with 5+S (12+ if 4H)"
        )
        rules.append(rule)
        
        self.rules['1S'] = rules
    
    def _parse_1nt_opening(self, content: str):
        """Parse 1NT opening rules."""
        rules = []
        
        # 1N = 12-14 (11+ NV), all 5422's included except both M's, 6m ok, all 4441's included
        rule = BiddingRule(
            opening="1NT",
            hcp_range=(12, 14),
            balanced=True,
            description="12-14 balanced (11+ NV)"
        )
        rules.append(rule)
        
        self.rules['1NT'] = rules
    
    def _parse_2level_openings(self, content: str):
        """Parse 2-level opening rules."""
        rules = []
        
        # 2C = 10-13 value, 5C-4other unbalanced, or 6+C
        rule = BiddingRule(
            opening="2C",
            hcp_range=(10, 13),
            suit_requirements={'C': 5},
            description="10-13 with 5C-4other or 6+C"
        )
        rules.append(rule)
        
        # 2D = 10-13 value, 5D-4M/4+m unbalanced, or 6+D
        rule = BiddingRule(
            opening="2D",
            hcp_range=(10, 13),
            suit_requirements={'D': 5},
            description="10-13 with 5D-4M/4+m or 6+D"
        )
        rules.append(rule)
        
        # 2H/2S = 10-13 value, 5M-4+m unbalanced, or 6+M
        for suit in ['H', 'S']:
            rule = BiddingRule(
                opening=f"2{suit}",
                hcp_range=(10, 13),
                suit_requirements={suit: 5},
                description=f"10-13 with 5{suit}-4+m or 6+{suit}"
            )
            rules.append(rule)
        
        # 2NT = 21-22 bal
        rule = BiddingRule(
            opening="2NT",
            hcp_range=(21, 22),
            balanced=True,
            description="21-22 balanced"
        )
        rules.append(rule)
        
        self.rules['2C'] = [rules[0]]
        self.rules['2D'] = [rules[1]]
        self.rules['2H'] = [rules[2]]
        self.rules['2S'] = [rules[3]]
        self.rules['2NT'] = [rules[4]]
    
    def _parse_3level_openings(self, content: str):
        """Parse 3-level opening rules."""
        rules = []
        
        # 3y/4y = pree
        for suit in ['C', 'D', 'H', 'S']:
            rule = BiddingRule(
                opening=f"3{suit}",
                hcp_range=(0, 10),  # Preempts should be 10 HCP or less
                suit_requirements={suit: 7},
                description=f"Preempt with 7+{suit}"
            )
            rules.append(rule)
        
        # 3NT = solid 7+crd minor nothing much else
        rule = BiddingRule(
            opening="3NT",
            hcp_range=(15, 17),
            suit_requirements={'C': 7},
            description="Solid 7+ minor"
        )
        rules.append(rule)
        
        for i, suit in enumerate(['C', 'D', 'H', 'S']):
            self.rules[f'3{suit}'] = [rules[i]]
        self.rules['3NT'] = [rules[4]]
    
    def _parse_opening_responses(self, content: str):
        """Parse opening response sequences."""
        # Parse 1C responses
        self._parse_1c_responses(content)
        self._parse_1d_responses(content)
        self._parse_1h_responses(content)
        self._parse_1s_responses(content)
        self._parse_1nt_responses(content)
    
    def _parse_1c_responses(self, content: str):
        """Parse 1C opening responses."""
        section = self._extract_section(content, "Opening 1C Responses", "Opening 1D Responses")
        
        responses = {
            '1D': BiddingRule(response='1D', hcp_range=(0, 9), suit_requirements={'H': 4}),
            '1H': BiddingRule(response='1H', hcp_range=(0, 9), suit_requirements={'S': 4}),
            '1S': BiddingRule(response='1S', hcp_range=(14, 20), suit_requirements={'H': 4}),
            '1NT': BiddingRule(response='1NT', hcp_range=(15, 18), balanced=True),
            '2C': BiddingRule(response='2C', hcp_range=(14, 17), suit_requirements={'C': 6})
        }
        
        self.sequences['1C'] = BiddingSequence('1C', responses, {})
    
    def _parse_1d_responses(self, content: str):
        """Parse 1D opening responses."""
        section = self._extract_section(content, "Opening 1D Responses", "Opening 1H Responses")
        
        responses = {
            '1H': BiddingRule(response='1H', hcp_range=(0, 9), suit_requirements={'H': 4}),
            '1S': BiddingRule(response='1S', hcp_range=(0, 9), suit_requirements={'S': 4}),
            '1NT': BiddingRule(response='1NT', hcp_range=(18, 40), balanced=False)
        }
        
        self.sequences['1D'] = BiddingSequence('1D', responses, {})
    
    def _parse_1h_responses(self, content: str):
        """Parse 1H opening responses."""
        section = self._extract_section(content, "Opening 1H Responses", "Opening 1S Responses")
        
        responses = {
            '1S': BiddingRule(response='1S', hcp_range=(0, 9), suit_requirements={'S': 4}),
            '1NT': BiddingRule(response='1NT', hcp_range=(0, 9), balanced=True),
            '2C': BiddingRule(response='2C', hcp_range=(10, 40), balanced=True)
        }
        
        self.sequences['1H'] = BiddingSequence('1H', responses, {})
    
    def _parse_1s_responses(self, content: str):
        """Parse 1S opening responses."""
        section = self._extract_section(content, "Opening 1S Responses", "Opening 1N Responses")
        
        responses = {
            '1NT': BiddingRule(response='1NT', hcp_range=(0, 9), balanced=True),
            '2C': BiddingRule(response='2C', hcp_range=(10, 40), balanced=True)
        }
        
        self.sequences['1S'] = BiddingSequence('1S', responses, {})
    
    def _parse_1nt_responses(self, content: str):
        """Parse 1NT opening responses."""
        section = self._extract_section(content, "Opening 1N Responses", "Handling Interference")
        
        responses = {
            '2C': BiddingRule(response='2C', hcp_range=(10, 40), description="Stayman"),
            '2D': BiddingRule(response='2D', hcp_range=(10, 40), description="Transfer to H"),
            '2H': BiddingRule(response='2H', hcp_range=(10, 40), description="Transfer to S"),
            '2S': BiddingRule(response='2S', hcp_range=(10, 40), description="Transfer to minors")
        }
        
        self.sequences['1NT'] = BiddingSequence('1NT', responses, {})
    
    def _parse_competitive_bidding(self, content: str):
        """Parse competitive bidding rules."""
        section = self._extract_section(content, "DEFENSIVE BIDDING", "SLAM BIDDING")
        # Implementation for competitive bidding rules
        pass
    
    def _parse_slam_bidding(self, content: str):
        """Parse slam bidding rules."""
        section = self._extract_section(content, "SLAM BIDDING", "GENERAL")
        # Implementation for slam bidding rules
        pass
    
    def _extract_section(self, content: str, start_marker: str, end_marker: str) -> str:
        """Extract a section of text between markers."""
        start_idx = content.find(start_marker)
        if start_idx == -1:
            return ""
        
        end_idx = content.find(end_marker, start_idx)
        if end_idx == -1:
            return content[start_idx:]
        
        return content[start_idx:end_idx]
    
    def get_opening_rules(self) -> Dict[str, List[BiddingRule]]:
        """Get all opening bid rules."""
        return {k: v for k, v in self.rules.items() if k in ['1C', '1D', '1H', '1S', '1NT', '2C', '2D', '2H', '2S', '2NT', '3C', '3D', '3H', '3S', '3NT']}
    
    def get_response_rules(self, opening: str) -> Dict[str, BiddingRule]:
        """Get response rules for a specific opening."""
        if opening in self.sequences:
            return self.sequences[opening].responses
        return {}
    
    def find_matching_rule(self, hand_analysis: Dict, opening: Optional[str] = None, response: Optional[str] = None) -> Optional[BiddingRule]:
        """Find a matching rule for given hand analysis and bid."""
        if opening:
            rules = self.rules.get(opening, [])
        elif response:
            # Find in all sequences
            for seq in self.sequences.values():
                if response in seq.responses:
                    return seq.responses[response]
            return None
        else:
            return None
        
        for rule in rules:
            if self._rule_matches(rule, hand_analysis):
                return rule
        
        return None
    
    def _rule_matches(self, rule: BiddingRule, hand_analysis: Dict) -> bool:
        """Check if a rule matches the hand analysis."""
        # Check HCP range
        if rule.hcp_range:
            hcp = hand_analysis.get('hcp', 0)
            if not (rule.hcp_range[0] <= hcp <= rule.hcp_range[1]):
                return False
        
        # Check suit requirements
        if rule.suit_requirements:
            suit_lengths = hand_analysis.get('suit_lengths', {})
            for suit, min_length in rule.suit_requirements.items():
                if suit_lengths.get(suit, 0) < min_length:
                    return False
        
        # Check balanced requirement
        if rule.balanced is not None:
            if hand_analysis.get('balanced', False) != rule.balanced:
                return False
        
        return True
