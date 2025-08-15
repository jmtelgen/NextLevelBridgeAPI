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
                # Bidding ended with all passes
                game_data['currentPhase'] = 'playing'
                game_data['turn'] = room_item['seats']['N']  # North leads
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
                        game_data['turn'] = room_item['seats']['N']  # North leads
        
        # Update room state if phase changed
        if game_data['currentPhase'] == 'playing':
            room_item['state'] = 'playing'
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Get active connections and broadcast update (excluding the user who made the bid)
        active_connections = db_utils.get_room_connections_excluding_user(room_item['seats'].values(), room_id, user_id)
        
        broadcast_message = {
            'action': 'bidMade',
            'bid': bid_entry,
            'nextTurn': next_player,
            'gameData': game_data,
            'roomState': room_item['state'],
            'updateType': 'bidUpdate'
        }
        
        broadcast_to_connections(active_connections, broadcast_message)
        
        # Return success response (same as broadcast to avoid duplication)
        return self.success_response({
            'action': 'bidMade',
            'success': True,
            'bid': bid_entry,
            'nextTurn': next_player,
            'gameData': game_data,
            'roomState': room_item['state'],
            'updateType': 'bidUpdate',
            'message': f'Bid {bid} recorded successfully'
        })

# Create handler instance
handler = WebSocketMakeBidHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context) 