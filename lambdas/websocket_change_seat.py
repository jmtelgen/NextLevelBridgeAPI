from base_handler import WebSocketBaseHandler
from lambdas.utils.db_utils import db_utils
from lambdas.utils.websocket_utils import broadcast_to_connection

SEATS = ['North', 'East', 'South', 'West']

class WebSocketChangeSeatHandler(WebSocketBaseHandler):
    """
    WebSocket handler for changing seat assignments
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket change seat request
        """
        # Validate route key
        try:
            self.validate_route_key(event, 'changeSeat')
        except ValueError as e:
            return self.error_response(400, str(e))
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Extract and validate parameters
        user_id = data.get('userId')
        room_id = data.get('roomId')
        new_seat = data.get('newSeat')
        
        error = self.validate_required_fields(data, ['userId', 'roomId', 'newSeat'])
        if error:
            return self.error_response(400, error)
        
        # Validate seat is valid
        if new_seat not in SEATS:
            return self.error_response(400, f'Invalid seat. Must be one of: {", ".join(SEATS)}')
        
        # Get room table reference
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Find room using database utilities
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        
        # Check if user is in the room
        if user_id not in room_item['seats'].values():
            return self.error_response(400, 'User is not in this room')
        
        # Check if the new seat is available
        if room_item['seats'][new_seat] is not None:
            return self.error_response(400, f'Seat {new_seat} is already occupied')
        
        # Find user's current seat
        current_seat = None
        for seat, occupant in room_item['seats'].items():
            if occupant == user_id:
                current_seat = seat
                break
        
        if not current_seat:
            return self.error_response(400, 'User seat not found')
        
        # Update seat assignment
        room_item['seats'][current_seat] = None  # Clear current seat
        room_item['seats'][new_seat] = user_id    # Assign to new seat
        
        # Update room in database
        try:
            room_table.put_item(Item=room_item)
        except Exception as e:
            return self.error_response(500, f"Unexpected error: {str(e)}")
        
        # Convert objects to JSON-serializable format
        room_item_serializable = self._convert_for_json(room_item)
        # Convert seats from userIds to usernames for privacy
        room_item_serializable['seats'] = self._convert_seats_to_usernames(room_item['seats'])
        game_data_serializable = self._convert_for_json(room_item.get('gameData', {}))
        
        # Get active connections and broadcast update
        active_connections = []
        for _, seat_user_id in room_item['seats'].items():
            if seat_user_id:  # Only process occupied seats
                connection = db_utils.get_room_connection(seat_user_id)
                if connection:
                    active_connections.append(connection)
        active_connections = list(set(active_connections))
        
        broadcast_message = {
            'action': 'roomUpdated',
            'success': True,
            'room': room_item_serializable,
            'updateType': 'seatChanged',
            'userId': user_id,
            'oldSeat': current_seat,
            'newSeat': new_seat,
            'gameData': game_data_serializable
        }
        
        for connection in active_connections:
            broadcast_to_connection(connection, broadcast_message)
        
        # Return success response
        return self.success_response({
            'action': 'roomUpdated',
            'success': True,
            'room': room_item_serializable,
            'updateType': 'seatChanged',
            'userId': user_id,
            'oldSeat': current_seat,
            'newSeat': new_seat,
            'gameData': game_data_serializable
        })

# Create handler instance
handler = WebSocketChangeSeatHandler()

# Lambda handler function
def lambda_handler(event, context):
    try:
        return handler.handle_websocket_request(event, context)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'WebSocket error: {str(e)}'
        }
