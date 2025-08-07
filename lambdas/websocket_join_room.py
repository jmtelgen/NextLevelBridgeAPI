import random
from base_handler import WebSocketBaseHandler
from db_utils import db_utils
from websocket_utils import broadcast_to_connections

SEATS = ['N', 'E', 'S', 'W']

class WebSocketJoinRoomHandler(WebSocketBaseHandler):
    """
    WebSocket handler for joining a room
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket join room request
        """
        # Validate route key
        self.validate_route_key(event, 'joinRoom')
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Extract and validate parameters
        user_id = data.get('userId')
        room_id = data.get('roomId')
        requested_seat = data.get('seat')
        
        error = self.validate_required_fields(data, ['userId', 'roomId'])
        if error:
            return self.error_response(400, error)
        
        # Find room using database utilities
        room_item = db_utils.find_room_by_id(room_id)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        
        # Check if user is already in the room
        if user_id in room_item['seats'].values():
            return self.error_response(400, 'User already in room')
        
        # Determine seat assignment
        seat_to_assign = self._determine_seat(room_item, requested_seat)
        if not seat_to_assign:
            return self.error_response(400, 'No seats available')
        
        # Assign user to seat
        room_item['seats'][seat_to_assign] = user_id
        
        # Update room in database
        room_table = db_utils.get_table('ROOM_TABLE')
        room_table.put_item(Item=room_item)
        
        # Update user's connection record
        db_utils.update_user_room(user_id, room_id)
        
        # Get active connections and broadcast update
        active_connections = db_utils.get_room_connections(room_item['seats'].values(), room_id)
        
        broadcast_message = {
            'action': 'roomUpdated',
            'room': room_item,
            'updateType': 'userJoined',
            'newUser': user_id,
            'assignedSeat': seat_to_assign
        }
        
        broadcast_to_connections(active_connections, broadcast_message)
        
        # Return success response
        return self.success_response({
            'action': 'joinRoom',
            'success': True,
            'room': room_item,
            'assignedSeat': seat_to_assign,
            'gameState': room_item.get('gameData', {})
        })
    
    def _determine_seat(self, room_item, requested_seat):
        """
        Determine which seat to assign to the user
        """
        available_seats = [seat for seat, occupant in room_item['seats'].items() if not occupant]
        
        if requested_seat:
            if requested_seat not in SEATS:
                return None
            if room_item['seats'][requested_seat]:
                return None
            return requested_seat
        else:
            if not available_seats:
                return None
            return random.choice(available_seats)

# Create handler instance
handler = WebSocketJoinRoomHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context) 