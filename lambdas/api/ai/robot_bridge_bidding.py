"""
Robot Bridge Bidding Lambda

This lambda provides intelligent bridge bidding for robot players using the
SAYC (Standard American Yellow Card) bidding system. It analyzes hands and 
makes appropriate bids based on high card points, distribution, and bidding 
context with fallback to Fantoni-Nunes system.
"""

import json
import os
import boto3
import time
from typing import Dict, List, Optional
import sys
import os

# Add the lambdas directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.shared.utils.seat_filtering import create_seat_based_response, broadcast_game_update
from lambdas.core.robot.robot_utils import is_robot_seat, get_robot_turns_sequence, get_next_seat
from core.robot.robot_bidder import RobotBidder


class RobotBridgeBiddingHandler(WebSocketBaseHandler):
    """
    WebSocket handler for robot bridge bidding using SAYC system
    """
    
    def __init__(self):
        super().__init__()
        self.robot_bidder = RobotBidder()
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket robot bidding request
        """
        # Validate route key
        try:
            self.validate_route_key(event, 'robotBid')
        except ValueError as e:
            return self.error_response(400, str(e))
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Extract and validate parameters
        room_id = data.get('roomId')
        robot_seat = data.get('robotSeat')
        
        error = self.validate_required_fields(data, ['roomId', 'robotSeat'])
        if error:
            return self.error_response(400, error)
        
        # Validate robot seat
        if robot_seat not in ['North', 'East', 'South', 'West']:
            return self.error_response(400, 'Invalid robot seat')
        
        # Get room table reference
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Fetch room
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        
        # Check if room is in bidding phase
        if room_item['state'] != 'bidding':
            return self.error_response(400, 'Room is not in bidding phase')
        
        # Check if it's the robot's turn
        game_data = room_item.get('gameData', {})
        current_turn = game_data.get('turn')
        
        if current_turn != robot_seat:
            return self.error_response(400, 'Not the robot\'s turn to bid')
        
        # Verify this is actually a robot seat
        robot_occupant = room_item['seats'].get(robot_seat)
        if not is_robot_seat(robot_occupant):
            return self.error_response(400, 'Seat is not occupied by a robot')
        
        # Make intelligent bid
        try:
            robot_bid = self.robot_bidder.make_bid(room_item, robot_seat)
        except Exception as e:
            print(f"Robot bidding error: {e}")
            robot_bid = 'pass'  # Fallback to pass
        
        # Add bid to game data
        if 'bids' not in game_data:
            game_data['bids'] = []
        
        bid_entry = {
            'seat': robot_seat,
            'bid': robot_bid,
            'timestamp': int(time.time() * 1000)
        }
        
        game_data['bids'].append(bid_entry)
        
        # Determine next turn
        seats = ['North', 'East', 'South', 'West']
        current_seat_index = seats.index(robot_seat)
        next_seat_index = (current_seat_index + 1) % 4
        next_seat = seats[next_seat_index]
        
        game_data['turn'] = next_seat
        
        # Check if bidding should end
        self._check_bidding_end(game_data)
        
        # Update room state if phase changed
        if game_data.get('currentPhase') == 'playing':
            room_item['state'] = 'playing'
        elif game_data.get('currentPhase') == 'completed':
            room_item['state'] = 'completed'
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Broadcast robot bid
        self._broadcast_robot_bid(
            room_id=room_id,
            room_item=room_item,
            robot_seat=robot_seat,
            robot_bid=robot_bid,
            game_data=game_data
        )
        
        # Execute additional robot turns if needed
        self._execute_additional_robot_turns(room_item, robot_seat)
        
        # Create response
        response_data = {
            'action': 'robotBidMade',
            'robotSeat': robot_seat,
            'bid': robot_bid,
            'nextTurn': game_data['turn'],
            'biddingPhase': game_data.get('currentPhase', 'bidding')
        }
        
        # Add bidding result information if phase changed
        if game_data.get('currentPhase') == 'playing' and 'declarer' in game_data:
            response_data['biddingResult'] = 'contract'
            response_data['declarer'] = game_data['declarer']
            response_data['contract'] = game_data['contract']
            response_data['openingLeader'] = game_data['openingLeader']
        elif game_data.get('currentPhase') == 'completed':
            response_data['biddingResult'] = 'allPass'
            response_data['gameResult'] = 'noWinner'
            response_data['gameEndReason'] = 'allPass'
        
        return self.success_response(response_data)
    
    def _check_bidding_end(self, game_data: Dict):
        """Check if bidding should end and update game phase accordingly."""
        bids = game_data.get('bids', [])
        
        if len(bids) < 4:
            return
        
        # Check last 4 bids
        recent_bids = bids[-4:]
        last_four_bids = [b['bid'] for b in recent_bids]
        
        # All passes
        if last_four_bids == ['pass', 'pass', 'pass', 'pass']:
            game_data['currentPhase'] = 'completed'
            game_data['gameResult'] = 'noWinner'
            game_data['gameEndReason'] = 'allPass'
            game_data['winner'] = None
            return
        
        # Check for 3 passes after a contract
        non_pass_bids = [b for b in last_four_bids if b != 'pass']
        if len(non_pass_bids) >= 1 and recent_bids[-1]['bid'] == 'pass':
            pass_count = 0
            for bid in reversed(recent_bids):
                if bid['bid'] == 'pass':
                    pass_count += 1
                else:
                    break
            
            if pass_count >= 3:
                game_data['currentPhase'] = 'playing'
                self._set_contract_info(game_data, recent_bids)
    
    def _set_contract_info(self, game_data: Dict, recent_bids: List[Dict]):
        """Set contract information when bidding ends."""
        # Find the final contract
        final_contract = None
        for bid in reversed(recent_bids):
            if bid['bid'] not in ['pass', 'double', 'redouble']:
                final_contract = bid
                break
        
        if not final_contract:
            return
        
        # Find declarer (first person to bid the final suit)
        contract_suit = final_contract['bid'][1:] if not final_contract['bid'].endswith('NT') else 'NT'
        declarer = None
        
        for bid in game_data['bids']:
            if bid['bid'] not in ['pass', 'double', 'redouble']:
                bid_suit = bid['bid'][1:] if not bid['bid'].endswith('NT') else 'NT'
                if bid_suit == contract_suit:
                    declarer = bid['seat']
                    break
        
        if declarer:
            game_data['declarer'] = declarer
            game_data['contract'] = final_contract['bid']
            
            # Set opening leader (player to the left of declarer)
            seats = ['North', 'East', 'South', 'West']
            declarer_index = seats.index(declarer)
            opening_leader_index = (declarer_index + 1) % 4
            game_data['openingLeader'] = seats[opening_leader_index]
            game_data['turn'] = seats[opening_leader_index]
    
    def _execute_additional_robot_turns(self, room_item: Dict, current_seat: str):
        """Execute additional robot turns if needed."""
        robot_turns = get_robot_turns_sequence(room_item, current_seat)
        game_data = room_item.get('gameData', {})
        
        for robot_seat, action_type in robot_turns:
            if action_type == 'bid':
                try:
                    robot_bid = self.robot_bidder.make_bid(room_item, robot_seat)
                except Exception as e:
                    print(f"Additional robot bidding error: {e}")
                    robot_bid = 'pass'
                
                if robot_bid:
                    # Add robot bid to game data
                    robot_bid_entry = {
                        'seat': robot_seat,
                        'bid': robot_bid,
                        'timestamp': int(time.time() * 1000)
                    }
                    game_data['bids'].append(robot_bid_entry)
                    
                    # Update turn
                    game_data['turn'] = get_next_seat(robot_seat)
                    
                    # Broadcast this robot bid
                    self._broadcast_robot_bid(
                        room_id=room_item['roomId'],
                        room_item=room_item,
                        robot_seat=robot_seat,
                        robot_bid=robot_bid,
                        game_data=game_data
                    )
                    
                    # Check if bidding should end after this bid
                    self._check_bidding_end(game_data)
                    
                    # Update room state if phase changed
                    if game_data.get('currentPhase') == 'playing':
                        room_item['state'] = 'playing'
                    elif game_data.get('currentPhase') == 'completed':
                        room_item['state'] = 'completed'
    
    def _broadcast_robot_bid(self, room_id: str, room_item: Dict, robot_seat: str, 
                            robot_bid: str, game_data: Dict):
        """Broadcast robot bid to all players."""
        def broadcast_to_user(target_user_id, response):
            connection = db_utils.get_room_connection(target_user_id)
            if connection:
                broadcast_to_connection(connection, response.dict())
        
        # Broadcast robot bid to all players
        broadcast_game_update(
            room_id=room_id,
            game_data=game_data,
            room_seats=room_item['seats'],
            action='robotBidMade',
            message=f'Robot {robot_seat} bid {robot_bid}',
            broadcast_function=broadcast_to_user
        )
    
    def get_hand_analysis(self, hand: List[str]) -> Dict:
        """Get detailed hand analysis for debugging purposes."""
        try:
            analysis = self.robot_bidder.hand_evaluator.evaluate_hand(hand)
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
                'description': self.robot_bidder.get_hand_strength_description(hand)
            }
        except Exception as e:
            return {'error': str(e)}


# Create handler instance
handler = RobotBridgeBiddingHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
