import json
import os
import boto3
from botocore.exceptions import ClientError
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.robot.robot_utils import fill_empty_seats_with_robots, can_start_game_with_robots
from typing import Dict, List

SEATS = ['North', 'East', 'South', 'West']

class WebSocketStartRoomHandler(WebSocketBaseHandler):
    """
    WebSocket handler for starting a room/game
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket start room request
        """
        # Validate route key
        try:
            self.validate_route_key(event, 'startRoom')
        except ValueError as e:
            return self.error_response(400, str(e))
        
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
        
        # Fill empty seats with robots and check if game can be started
        room_item['seats'] = fill_empty_seats_with_robots(room_item['seats'])
        
        if not can_start_game_with_robots(room_item['seats']):
            return self.error_response(400, 'At least one human player is required to start the game')
        
        # Update room state to bidding
        room_item['state'] = 'bidding'
        
        # Find the owner's seat position
        owner_seat = None
        for seat, occupant in room_item['seats'].items():
            if occupant == room_item['ownerId']:
                owner_seat = seat
                break
        
        # Initialize game data if not present
        if 'gameData' not in room_item:
            room_item['gameData'] = {
                'currentPhase': 'waiting',
                'turn': owner_seat,  # Use position (North/South/East/West) instead of userId
                'bids': [],
                'hands': {seat: [] for seat in SEATS},
                'tricks': []
            }
        
        # Update game phase to bidding, reset turn to owner's position, and deal cards
        room_item['gameData']['currentPhase'] = 'bidding'
        room_item['gameData']['turn'] = owner_seat  # Always ensure turn is a position, not userId
        room_item['gameData']['hands'] = self._deal_cards()
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Convert objects to JSON-serializable format
        room_item_serializable = self._convert_for_json(room_item)
        # Convert seats from userIds to usernames for privacy
        room_item_serializable['seats'] = self._convert_seats_to_usernames(room_item['seats'])
        game_data_serializable = self._convert_for_json(room_item['gameData'])
        
         # Get active connections and broadcast update (excluding the user who joined the room)
        active_connections = []
        for _, user_id in room_item['seats'].items():
            connection = db_utils.get_room_connection(user_id)
            if connection:
                active_connections.append(connection)
        active_connections = list(set(active_connections))
        
        broadcast_message = {
            'action': 'roomStarted',
            'room': room_item_serializable,
            'gameData': game_data_serializable,
            'updateType': 'gameStart',
            'message': 'Game started successfully',
            'hands': game_data_serializable['hands']
        }
        
        for connection in active_connections:
            broadcast_to_connection(connection, broadcast_message)
        
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
            'North': deck[0:13],    # North gets cards 0-12
            'East': deck[13:26],    # East gets cards 13-25
            'South': deck[26:39],   # South gets cards 26-38
            'West': deck[39:52]     # West gets cards 39-51
        }
        
        return hands

# Create handler instance
handler = WebSocketStartRoomHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context) 