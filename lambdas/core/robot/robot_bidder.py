"""
Robot Bidder utility class for intelligent bridge bidding.

This class uses the AdvancedBiddingEngine to make intelligent
bidding decisions for robot players in bridge games using the full
Fantoni-Nunes system with DDS integration.
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

# Add the lambdas directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator, HandAnalysis
from lambdas.core.bidding.bidding_system import BiddingSystem, BiddingContext
from lambdas.core.bidding.advanced_bidding_engine import AdvancedBiddingEngine, BiddingDecision
from lambdas.core.bidding.sayc_bidding import SAYCBidding, BiddingContext as SAYCBiddingContext, Bid


class RobotBidder:
    """Intelligent robot bidder using SAYC bidding system with fallback to Fantoni-Nunes."""
    
    def __init__(self):
        self.hand_evaluator = HandEvaluator()
        self.bidding_system = BiddingSystem()
        
        # Initialize SAYC bidding system as primary method
        self.sayc_bidding = SAYCBidding()
        self.use_sayc = True
        
        # Initialize advanced engine with algorithm file as fallback
        algorithm_file = os.path.join(os.path.dirname(__file__), '..', 'dds', 'bridge_bidding_alg.txt')
        try:
            self.advanced_engine = AdvancedBiddingEngine(algorithm_file)
            self.use_advanced = True
        except Exception as e:
            print(f"Advanced bidding engine initialization failed: {e}")
            self.advanced_engine = None
            self.use_advanced = False
    
    def make_bid(self, room_data: Dict, robot_seat: str) -> str:
        """
        Make an intelligent bid for a robot player using SAYC bidding system.
        
        Args:
            room_data: Current room data
            robot_seat: The robot's seat position
            
        Returns:
            The bid to make
        """
        try:
            # Get robot's hand
            game_data = room_data.get('gameData', {})
            hands = game_data.get('hands', {})
            robot_hand = hands.get(robot_seat, [])
            
            if not robot_hand:
                return 'pass'
            
            # Use SAYC bidding system as primary method
            if self.use_sayc and self.sayc_bidding:
                return self._make_sayc_bid(robot_hand, room_data, robot_seat)
            elif self.use_advanced and self.advanced_engine:
                return self._make_advanced_bid(robot_hand, room_data, robot_seat)
            else:
                # Fallback to basic system
                return self._make_basic_bid(robot_hand, room_data, robot_seat)
                
        except Exception as e:
            print(f"Robot bidding error: {e}")
            return 'pass'
    
    def _make_advanced_bid(self, hand: List[str], room_data: Dict, robot_seat: str) -> str:
        """Make bid using the advanced Fantoni-Nunes engine."""
        try:
            # Create comprehensive bidding context
            context = self._create_advanced_bidding_context(room_data, robot_seat)
            
            # Get intelligent bid decision
            decision = self.advanced_engine.make_bid(hand, context)
            
            # Log the decision for debugging
            print(f"Robot {robot_seat} bid: {decision.bid} (confidence: {decision.confidence:.2f}) - {decision.reasoning}")
            
            return decision.bid
            
        except Exception as e:
            print(f"Advanced bidding failed: {e}")
            return self._make_basic_bid(hand, room_data, robot_seat)
    
    def _make_sayc_bid(self, hand: List[str], room_data: Dict, robot_seat: str) -> str:
        """Make bid using the SAYC bidding system."""
        try:
            # Create SAYC bidding context
            context = self._create_sayc_bidding_context(room_data, robot_seat)
            
            # Get intelligent bid using SAYC system
            bid = self.sayc_bidding.make_bid(hand, context)
            
            # Log the decision for debugging
            print(f"Robot {robot_seat} SAYC bid: {bid}")
            
            return bid
            
        except Exception as e:
            print(f"SAYC bidding failed: {e}")
            return self._make_basic_bid(hand, room_data, robot_seat)
    
    def _make_basic_bid(self, hand: List[str], room_data: Dict, robot_seat: str) -> str:
        """Fallback to basic bidding system."""
        try:
            # Create basic bidding context
            context = self._create_bidding_context(room_data, robot_seat)
            
            # Determine if this is an opening bid or response
            if self._is_opening_bid(context):
                return self._make_opening_bid(hand, context)
            else:
                return self._make_response_bid(hand, context)
                
        except Exception as e:
            print(f"Basic bidding error: {e}")
            return 'pass'
    
    def _create_bidding_context(self, room_data: Dict, robot_seat: str) -> BiddingContext:
        """Create bidding context from room data."""
        game_data = room_data.get('gameData', {})
        bids = game_data.get('bids', [])
        
        # Determine position (1st, 2nd, 3rd, 4th seat)
        position = self._get_position(robot_seat, game_data.get('dealer', 'North'))
        
        # Separate partner and opponent bids
        partner_bids, opponent_bids = self._separate_bids(bids, robot_seat)
        
        # Get vulnerability
        vulnerability = room_data.get('vulnerability', 'None')
        
        return BiddingContext(
            seat=robot_seat,
            vulnerability=vulnerability,
            position=position,
            previous_bids=bids,
            partner_bids=partner_bids,
            opponents_bids=opponent_bids
        )
    
    def _is_opening_bid(self, context: BiddingContext) -> bool:
        """Check if this should be an opening bid."""
        # If no bids have been made, this is an opening bid
        if not context.previous_bids:
            return True
        
        # If only passes have been made, this could be an opening bid
        non_pass_bids = [bid for bid in context.previous_bids if bid['bid'] != 'pass']
        return len(non_pass_bids) == 0
    
    def _make_opening_bid(self, hand: List[str], context: BiddingContext) -> str:
        """Make an opening bid."""
        bid = self.bidding_system.get_opening_bid(hand, context)
        return bid if bid else 'pass'
    
    def _make_response_bid(self, hand: List[str], context: BiddingContext) -> str:
        """Make a response bid."""
        # Find partner's last bid
        partner_last_bid = self._get_partner_last_bid(context)
        
        if not partner_last_bid:
            return 'pass'
        
        # Get response to partner's bid
        bid = self.bidding_system.get_response(hand, partner_last_bid, context)
        return bid if bid else 'pass'
    
    def _get_position(self, seat: str, dealer: str) -> int:
        """Get position (1st, 2nd, 3rd, 4th seat) relative to dealer."""
        seat_order = ['North', 'East', 'South', 'West']
        dealer_index = seat_order.index(dealer)
        seat_index = seat_order.index(seat)
        
        # Calculate position (1-based)
        position = ((seat_index - dealer_index) % 4) + 1
        return position
    
    def _separate_bids(self, bids: List[Dict], robot_seat: str) -> Tuple[List[Dict], List[Dict]]:
        """Separate bids into partner and opponent bids."""
        partner_bids = []
        opponent_bids = []
        
        for bid in bids:
            bidder_seat = bid['seat']
            if self._are_partners(robot_seat, bidder_seat):
                partner_bids.append(bid)
            else:
                opponent_bids.append(bid)
        
        return partner_bids, opponent_bids
    
    def _create_advanced_bidding_context(self, room_data: Dict, robot_seat: str) -> Dict:
        """Create comprehensive bidding context for advanced engine."""
        game_data = room_data.get('gameData', {})
        bids = game_data.get('bids', [])
        
        # Determine position (1st, 2nd, 3rd, 4th seat)
        position = self._get_position(robot_seat, game_data.get('dealer', 'North'))
        
        # Separate partner and opponent bids
        partner_bids, opponent_bids = self._separate_bids(bids, robot_seat)
        
        # Get vulnerability
        vulnerability = room_data.get('vulnerability', 'None')
        
        # Create comprehensive context
        context = {
            'seat': robot_seat,
            'vulnerability': vulnerability,
            'position': position,
            'previous_bids': bids,
            'partner_bids': partner_bids,
            'opponents_bids': opponent_bids,
            'dealer': game_data.get('dealer', 'North'),
            'game_phase': game_data.get('currentPhase', 'bidding'),
            'room_id': room_data.get('roomId', ''),
            'timestamp': game_data.get('timestamp', 0)
        }
        
        return context
    
    def _create_sayc_bidding_context(self, room_data: Dict, robot_seat: str) -> SAYCBiddingContext:
        """Create SAYC bidding context from room data."""
        game_data = room_data.get('gameData', {})
        bids = game_data.get('bids', [])
        
        # Convert bids to SAYC Bid format
        sayc_bids = []
        for i, bid_data in enumerate(bids):
            sayc_bid = Bid(
                seat=bid_data['seat'],
                bid=bid_data['bid'],
                position=self._get_position(bid_data['seat'], game_data.get('dealer', 'North')),
                timestamp=bid_data.get('timestamp', 0)
            )
            sayc_bids.append(sayc_bid)
        
        # Get vulnerability
        vulnerability = room_data.get('vulnerability', 'None')
        
        # Get dealer
        dealer = game_data.get('dealer', 'N')
        
        # Create hand analysis (will be set by SAYC system)
        hand_analysis = None  # Will be set by the SAYC system
        
        return SAYCBiddingContext(
            current_seat=robot_seat,
            dealer=dealer,
            vulnerability=vulnerability,
            bidding_sequence=sayc_bids,
            hand_analysis=hand_analysis,
            room_id=room_data.get('roomId', ''),
            game_phase=game_data.get('currentPhase', 'bidding')
        )
    
    def _are_partners(self, seat1: str, seat2: str) -> bool:
        """Check if two seats are partners."""
        return ((seat1 in ['North', 'South'] and seat2 in ['North', 'South']) or
                (seat1 in ['East', 'West'] and seat2 in ['East', 'West']))
    
    def _get_partner_last_bid(self, context: BiddingContext) -> Optional[str]:
        """Get partner's last non-pass bid."""
        for bid in reversed(context.partner_bids):
            if bid['bid'] != 'pass':
                return bid['bid']
        return None
    
    def get_hand_strength_description(self, hand: List[str]) -> str:
        """Get a description of the hand strength for debugging."""
        if self.use_advanced and self.advanced_engine:
            return self.advanced_engine.get_hand_evaluation(hand)['description']
        else:
            analysis = self.hand_evaluator.evaluate_hand(hand)
            return self.hand_evaluator.get_hand_description(hand)
    
    def get_advanced_hand_analysis(self, hand: List[str]) -> Dict:
        """Get comprehensive hand analysis using advanced engine."""
        if self.use_advanced and self.advanced_engine:
            return self.advanced_engine.get_hand_evaluation(hand)
        else:
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
    
    def get_available_bids(self, hand: List[str], room_data: Dict, robot_seat: str) -> List[Dict]:
        """Get all available bids with confidence scores."""
        if self.use_advanced and self.advanced_engine:
            context = self._create_advanced_bidding_context(room_data, robot_seat)
            decisions = self.advanced_engine.get_available_bids(hand, context)
            return [
                {
                    'bid': decision.bid,
                    'confidence': decision.confidence,
                    'reasoning': decision.reasoning,
                    'rule_used': decision.rule_used.description if decision.rule_used else None
                }
                for decision in decisions
            ]
        else:
            # Fallback to basic analysis
            return [{'bid': 'pass', 'confidence': 0.5, 'reasoning': 'Basic fallback'}]
    
    def should_double(self, hand: List[str], context: BiddingContext) -> bool:
        """Check if robot should double opponent's bid."""
        analysis = self.hand_evaluator.evaluate_hand(hand)
        
        # Basic doubling criteria
        if analysis.hcp >= 12:
            return True
        
        # Distributional doubles
        if analysis.total_points >= 15:
            return True
        
        return False
    
    def should_redouble(self, hand: List[str], context: BiddingContext) -> bool:
        """Check if robot should redouble."""
        analysis = self.hand_evaluator.evaluate_hand(hand)
        
        # Redouble with good hand
        if analysis.hcp >= 10:
            return True
        
        return False
    
    def get_competitive_bid(self, hand: List[str], context: BiddingContext) -> Optional[str]:
        """Get competitive bid when opponents are bidding."""
        analysis = self.hand_evaluator.evaluate_hand(hand)
        
        # If we have a good hand, compete
        if analysis.total_points >= 8:
            # Try to find a suit to bid
            if analysis.longest_suit_length >= 5:
                suit = analysis.longest_suit
                level = self._get_competitive_level(analysis, context)
                return f"{level}{suit}"
        
        return None
    
    def _get_competitive_level(self, analysis: HandAnalysis, context: BiddingContext) -> int:
        """Get appropriate level for competitive bidding."""
        # Simple level selection based on hand strength
        if analysis.total_points >= 15:
            return 2
        elif analysis.total_points >= 10:
            return 1
        else:
            return 1
