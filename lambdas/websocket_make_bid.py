import json
import os
import boto3
import time
from botocore.exceptions import ClientError
from base_handler import WebSocketBaseHandler
from db_utils import db_utils
from websocket_utils import broadcast_to_connections

VALID_BIDS = ['pass', '1C', '1D', '1H', '1S', '1NT', '2C', '2D', '2H', '2S', '2NT', 
              '3C', '3D', '3H', '3S', '3NT', '4C', '4D', '4H', '4S', '4NT', 
              '5C', '5D', '5H', '5S', '5NT', '6C', '6D', '6H', '6S', '6NT', 
              '7C', '7D', '7H', '7S', '7NT', 'double', 'redouble']

class WebSocketMakeBidHandler(WebSocketBaseHandler):
    """
    WebSocket handler for making a bid
    """
    
    def _determine_declarer_and_leader(self, bids):
        """
        Determine the declarer and opening leader based on bidding history.
        
        The declarer is the person (on the same team as the one who bid last) 
        who first bid the final contract suit. The opening leader is the player
        to the left of the declarer.
        
        Args:
            bids: List of bid dictionaries with 'seat', 'bid', 'timestamp' keys
            
        Returns:
            tuple: (declarer_seat, opening_leader_seat)
        """
        if not bids:
            return None, None
            
        # Find the final contract (last non-pass bid)
        final_contract = None
        for bid in reversed(bids):
            if bid['bid'] not in ['pass', 'double', 'redouble']:
                final_contract = bid
                break
                
        if not final_contract:
            return None, None
            
        # Extract suit and level from final contract
        contract_bid = final_contract['bid']
        if contract_bid == '1NT' or contract_bid.endswith('NT'):
            suit = 'NT'
        else:
            suit = contract_bid[1:]  # Extract suit (C, D, H, S)
            
        # Find who first bid this suit
        first_suit_bidder = None
        for bid in bids:
            if bid['bid'] not in ['pass', 'double', 'redouble']:
                bid_suit = bid['bid'][1:] if not bid['bid'].endswith('NT') else 'NT'
                if bid_suit == suit:
                    first_suit_bidder = bid['seat']
                    break
                    
        if not first_suit_bidder:
            # This shouldn't happen in normal bidding, but handle gracefully
            return None, None
            
        # Determine if the first suit bidder is on the same team as the final bidder
        final_bidder = final_contract['seat']
        if self._are_partners(first_suit_bidder, final_bidder):
            declarer = first_suit_bidder
        else:
            # If not partners, the declarer is the final bidder
            declarer = final_bidder
            
        # Calculate opening leader (player to the left of declarer)
        seats = ['N', 'E', 'S', 'W']
        declarer_index = seats.index(declarer)
        opening_leader_index = (declarer_index + 1) % 4  # Next clockwise position
        opening_leader = seats[opening_leader_index]
        
        return declarer, opening_leader
    
    def _are_partners(self, seat1, seat2):
        """
        Check if two seats are partners (N/S or E/W).
        
        Args:
            seat1: First seat ('N', 'E', 'S', 'W')
            seat2: Second seat ('N', 'E', 'S', 'W')
            
        Returns:
            bool: True if partners, False otherwise
        """
        return (seat1 in ['N', 'S'] and seat2 in ['N', 'S']) or (seat1 in ['E', 'W'] and seat2 in ['E', 'W'])
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket make bid request
        """
        # Validate route key
        self.validate_route_key(event, 'makeBid')
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Extract and validate parameters
        user_id = data.get('userId')
        room_id = data.get('roomId')
        bid = data.get('bid')
        
        error = self.validate_required_fields(data, ['userId', 'roomId', 'bid'])
        if error:
            return self.error_response(400, error)
        
        # Validate bid
        if bid not in VALID_BIDS:
            return self.error_response(400, f'Invalid bid. Valid bids: {", ".join(VALID_BIDS)}')
        
        # Get room table reference once
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Fetch room using db_utils (pass table reference to avoid duplicate logging)
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        
        # Check if room is in bidding phase
        if room_item['state'] != 'bidding':
            return self.error_response(400, 'Room is not in bidding phase')
        
        # Check if it's the user's turn
        game_data = room_item.get('gameData', {})
        current_turn = game_data.get('turn')
        
        if current_turn != user_id:
            return self.error_response(400, 'Not your turn to bid')
        
        # Find user's seat
        user_seat = None
        for seat, occupant in room_item['seats'].items():
            if occupant == user_id:
                user_seat = seat
                break
        
        if not user_seat:
            return self.error_response(400, 'User not found in room')
        
        # Add bid to game data
        if 'bids' not in game_data:
            game_data['bids'] = []
        
        bid_entry = {
            'seat': user_seat,
            'bid': bid,
            'timestamp': int(time.time() * 1000)  # Unix timestamp in milliseconds
        }
        
        game_data['bids'].append(bid_entry)
        
        # Determine next turn (simple round-robin)
        seats = ['N', 'E', 'S', 'W']
        current_seat_index = seats.index(user_seat)
        next_seat_index = (current_seat_index + 1) % 4
        next_seat = seats[next_seat_index]
        next_player = room_item['seats'][next_seat]
        
        game_data['turn'] = next_player
        
        # Check if bidding should end (4 passes in a row or valid contract)
        recent_bids = game_data['bids'][-4:] if len(game_data['bids']) >= 4 else game_data['bids']
        if len(recent_bids) >= 4:
            last_four_bids = [b['bid'] for b in recent_bids]
            if last_four_bids == ['pass', 'pass', 'pass', 'pass']:
                # Bidding ended with all passes - game ends with no winner
                game_data['currentPhase'] = 'completed'
                game_data['gameResult'] = 'noWinner'
                game_data['gameEndReason'] = 'allPass'
                game_data['winner'] = None
                # Set next_player to None since game is over
                next_player = None
            elif len([b for b in last_four_bids if b != 'pass']) >= 1:
                # Check if we have a valid contract (3 passes after a non-pass bid)
                non_pass_bids = [b for b in last_four_bids if b != 'pass']
                if len(non_pass_bids) >= 1 and recent_bids[-1]['bid'] == 'pass':
                    # Check if we have 3 consecutive passes after a contract
                    pass_count = 0
                    for bid in reversed(recent_bids):
                        if bid['bid'] == 'pass':
                            pass_count += 1
                        else:
                            break
                    if pass_count >= 3:
                        game_data['currentPhase'] = 'playing'
                        # Find the declarer and set opening leader
                        declarer_seat, opening_leader_seat = self._determine_declarer_and_leader(game_data['bids'])
                        
                        if declarer_seat and opening_leader_seat:
                            game_data['turn'] = room_item['seats'][opening_leader_seat]
                            # Update next_player to the opening leader for frontend
                            next_player = room_item['seats'][opening_leader_seat]
                            # Store declarer and contract information
                            game_data['declarer'] = declarer_seat
                            # Get the final contract bid
                            final_contract_bid = None
                            for bid in reversed(recent_bids):
                                if bid['bid'] not in ['pass', 'double', 'redouble']:
                                    final_contract_bid = bid['bid']
                                    break
                            game_data['contract'] = final_contract_bid
                            game_data['openingLeader'] = opening_leader_seat
                        else:
                            # Fallback to North if something goes wrong
                            game_data['turn'] = room_item['seats']['N']
                            next_player = room_item['seats']['N']
        
        # Update room state if phase changed
        if game_data['currentPhase'] == 'playing':
            room_item['state'] = 'playing'
        elif game_data['currentPhase'] == 'completed':
            room_item['state'] = 'completed'
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Convert objects to JSON-serializable format
        game_data_serializable = self._convert_for_json(game_data)
        
        # Get active connections and broadcast update (excluding the user who made the bid)
        active_connections = db_utils.get_room_connections_excluding_user(room_item['seats'].values(), room_id, user_id)
        
        broadcast_message = {
            'action': 'bidMade',
            'bid': bid_entry,
            'nextTurn': next_player,
            'gameData': game_data_serializable,
            'roomState': room_item['state'],
            'updateType': 'bidUpdate'
        }
        
        # If bidding phase ended, include additional information
        if game_data.get('currentPhase') == 'playing' and 'declarer' in game_data:
            if game_data['declarer'] is None:
                broadcast_message['biddingResult'] = 'allPass'
                broadcast_message['message'] = 'Bidding ended with all passes'
            else:
                broadcast_message['biddingResult'] = 'contract'
                broadcast_message['declarer'] = game_data['declarer']
                broadcast_message['contract'] = game_data['contract']
                broadcast_message['openingLeader'] = game_data['openingLeader']
                broadcast_message['message'] = f'Contract: {game_data["contract"]} by {game_data["declarer"]}'
        elif game_data.get('currentPhase') == 'completed':
            broadcast_message['biddingResult'] = 'allPass'
            broadcast_message['gameResult'] = 'noWinner'
            broadcast_message['gameEndReason'] = 'allPass'
            broadcast_message['message'] = 'Game ended - all players passed'
            # When game is completed, nextTurn should be None
            broadcast_message['nextTurn'] = None
        
        broadcast_to_connections(active_connections, broadcast_message)
        
        # Return success response (same as broadcast to avoid duplication)
        response_data = {
            'action': 'bidMade',
            'success': True,
            'bid': bid_entry,
            'nextTurn': next_player,
            'gameData': game_data_serializable,
            'roomState': room_item['state'],
            'updateType': 'bidUpdate',
            'message': f'Bid {bid} recorded successfully'
        }
        
        # If bidding phase ended, include additional information
        if game_data.get('currentPhase') == 'playing' and 'declarer' in game_data:
            if game_data['declarer'] is None:
                response_data['biddingResult'] = 'allPass'
                response_data['message'] = 'Bidding ended with all passes'
            else:
                response_data['biddingResult'] = 'contract'
                response_data['declarer'] = game_data['declarer']
                response_data['contract'] = game_data['contract']
                response_data['openingLeader'] = game_data['openingLeader']
                response_data['message'] = f'Contract: {game_data["contract"]} by {game_data["declarer"]}'
        elif game_data.get('currentPhase') == 'completed':
            response_data['biddingResult'] = 'allPass'
            response_data['gameResult'] = 'noWinner'
            response_data['gameEndReason'] = 'allPass'
            response_data['message'] = 'Game ended - all players passed'
            # When game is completed, nextTurn should be None
            response_data['nextTurn'] = None
        
        return self.success_response(response_data)

# Create handler instance
handler = WebSocketMakeBidHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context) 