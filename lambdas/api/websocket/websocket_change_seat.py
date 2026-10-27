from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game.runtime import connection_user, GameRequestError
from lambdas.core.game.runtime import personalized
from lambdas.core.rooms.lifecycle import change_seat
from lambdas.core.rooms.responses import deliver_reply, publish_update
import copy

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
        try:
            user_id = connection_user(db_utils, event, user_id)
        except GameRequestError as exc:
            return self.error_response(exc.status, str(exc))
        
        # Validate seat is valid
        if new_seat not in SEATS:
            return self.error_response(400, f'Invalid seat. Must be one of: {", ".join(SEATS)}')
        
        # Get room table reference
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Find room using database utilities
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        room_item = copy.deepcopy(room_item)
        try:
            current_seat = change_seat(room_table, room_item, user_id, new_seat)
        except GameRequestError as exc:
            return self.error_response(exc.status, str(exc))
        except Exception as e:
            return self.error_response(500, f"Unexpected error: {str(e)}")
        
        publish_update(db_utils, broadcast_to_connection, room_item, 'Player changed seat',
                       updateType='seatChanged', userId=user_id,
                       oldSeat=current_seat, newSeat=new_seat)
        payload = personalized(room_item, user_id, 'roomUpdated', 'Player changed seat')
        payload.update(success=True, updateType='seatChanged', userId=user_id,
                       oldSeat=current_seat, newSeat=new_seat)
        return self.success_response(self._convert_for_json(payload))

# Create handler instance
handler = WebSocketChangeSeatHandler()

# Lambda handler function
def lambda_handler(event, context):
    try:
        return deliver_reply(event, handler.handle_websocket_request(event, context),
                             broadcast_to_connection)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'WebSocket error: {str(e)}'
        }
