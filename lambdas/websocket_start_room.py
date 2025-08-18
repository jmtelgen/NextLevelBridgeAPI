import json
import os
import boto3
from botocore.exceptions import ClientError
from base_handler import WebSocketBaseHandler
from lambdas.utils.db_utils import db_utils
from lambdas.utils.websocket_utils import broadcast_to_connections
from typing import Dict, List

SEATS = ['N', 'E', 'S', 'W']

class WebSocketStartRoomHandler(WebSocketBaseHandler):
    """
    WebSocket handler for starting a room/game
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket start room request
        """
        # Validate route key
        self.validate_route_key(event, 'startRoom')
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Extract and validate parameters
        user_id = data.get('userId')
        room_id = data.get('roomId')
        
        error = self.validate_required_fields(data, ['userId', 'roomId'])
        if error:
            return self.error_response(400, error)
        
        # Get room table reference once
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Fetch room using db_utils (pass table reference to avoid duplicate logging)
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        
        # Check owner
        if room_item['ownerId'] != user_id:
            return self.error_response(400, 'Only the room owner can start the game')
        
        # Check state
        if room_item['state'] != 'waiting':
            return self.error_response(400, 'Room is not in waiting state')
        
        # All seats should already be filled (either with humans or robots)
        # Update room state to bidding
        room_item['state'] = 'bidding'
        
        # Initialize game data if not present
        if 'gameData' not in room_item:
            room_item['gameData'] = {
                'currentPhase': 'waiting',
                'turn': room_item['ownerId'],
                'bids': [],
                'hands': {seat: [] for seat in SEATS},
                'tricks': []
            }
        
        # Update game phase to bidding and deal cards
        room_item['gameData']['currentPhase'] = 'bidding'
        room_item['gameData']['hands'] = self._deal_cards()
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Convert objects to JSON-serializable format
        room_item_serializable = self._convert_for_json(room_item)
        game_data_serializable = self._convert_for_json(room_item['gameData'])
        
        # Get active connections and broadcast update (excluding the user who started the room)
        active_connections = db_utils.get_room_connections_excluding_user(room_item['seats'].values(), room_id, user_id)
        
        broadcast_message = {
            'action': 'roomStarted',
            'room': room_item_serializable,
            'gameData': game_data_serializable,
            'updateType': 'gameStart',
            'message': 'Game started successfully',
            'hands': game_data_serializable['hands']
        }
        
        broadcast_to_connections(active_connections, broadcast_message)
        
        # Return success response (same as broadcast to avoid duplication)
        return self.success_response({
            'action': 'roomStarted',
            'success': True,
            'room': room_item_serializable,
            'gameData': game_data_serializable,
            'updateType': 'gameStart',
            'message': 'Game started successfully',
            'hands': game_data_serializable['hands']
        })
    
    def _deal_cards(self) -> Dict[str, List[str]]:
        """
        Deal 13 cards to each of the 4 players from a shuffled 52-card deck
        Returns a dictionary mapping seat positions to lists of cards
        """
        import random
        
        # Standard 52-card deck
        suits = ['C', 'D', 'H', 'S']  # Clubs, Diamonds, Hearts, Spades
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']  # T = 10
        
        # Create the deck
        deck = []
        for suit in suits:
            for rank in ranks:
                deck.append(f"{rank}{suit}")  # e.g., "AS" for Ace of Spades
        
        # Shuffle the deck
        random.shuffle(deck)
        
        # Deal 13 cards to each player
        hands = {
            'N': deck[0:13],    # North gets cards 0-12
            'E': deck[13:26],   # East gets cards 13-25
            'S': deck[26:39],   # South gets cards 26-38
            'W': deck[39:52]    # West gets cards 39-51
        }
        
        return hands

# Create handler instance
handler = WebSocketStartRoomHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context) 