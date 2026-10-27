import copy
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.core.game.runtime import connection_user, GameRequestError
from lambdas.core.game.runtime import personalized
from lambdas.core.rooms.lifecycle import join_room
from lambdas.core.rooms.responses import deliver_reply, publish_update

SEATS = ['North', 'East', 'South', 'West']

class WebSocketJoinRoomHandler(WebSocketBaseHandler):
    """
    WebSocket handler for joining a room
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket join room request
        """
        # Validate route key
        try:
            self.validate_route_key(event, 'joinRoom')
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
        try:
            user_id = connection_user(db_utils, event, user_id)
        except GameRequestError as exc:
            return self.error_response(exc.status, str(exc))
        
        # Get room table reference once
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Find room using database utilities (pass table reference to avoid duplicate logging)
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        try:
            room_item, seat_to_assign, reconnected = join_room(
                db_utils, room_table, copy.deepcopy(room_item), user_id,
                data.get('invitationToken'))
        except GameRequestError as exc:
            return self.error_response(exc.status, str(exc))
        except Exception as e:
            return self.error_response(500, f"Unexpected error: {str(e)}")
        
        # Update user's connection record
        db_utils.update_user_room(user_id, room_id)
        
        message = 'Player reconnected' if reconnected else 'Player joined room'
        publish_update(db_utils, broadcast_to_connection, room_item, message,
                       updateType='userReconnected' if reconnected else 'userJoined',
                       newUser=user_id, assignedSeat=seat_to_assign)
        payload = personalized(room_item, user_id, 'roomUpdated', message)
        payload.update(success=True, updateType='userReconnected' if reconnected else 'userJoined',
                       newUser=user_id, assignedSeat=seat_to_assign)
        return self.success_response(self._convert_for_json(payload))
    
# Create handler instance
handler = WebSocketJoinRoomHandler()

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