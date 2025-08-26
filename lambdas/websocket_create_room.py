import json
import uuid
import os
import random
import logging
import time
from base_handler import WebSocketBaseHandler
from lambdas.utils.db_utils import db_utils

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class WebSocketCreateRoomHandler(WebSocketBaseHandler):
    """
    WebSocket handler for creating a room
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket create room request
        """
        start_time = time.time()
        request_id = self._log_request_info(event, context)
        
        try:
            # Validate route key
            try:
                self.validate_route_key(event, 'createRoom')
            except ValueError as e:
                return self.error_response(400, str(e))
            
            # Parse request body
            body = self.parse_body(event)
            data = self.extract_data_from_body(body)
            
            logger.debug(f"[{request_id}] Extracted data object", extra={
                'request_id': request_id,
                'data_keys': list(data.keys()) if data else [],
                'has_data': bool(data)
            })
            
            # Extract and validate parameters
            owner_id = data.get('ownerId')
            player_name = data.get('playerName')
            room_name = data.get('roomName')
            is_private = data.get('isPrivate', False)
            
            logger.info(f"[{request_id}] Validating required fields", extra={
                'request_id': request_id,
                'owner_id_present': bool(owner_id),
                'player_name_present': bool(player_name),
                'room_name_present': bool(room_name),
                'is_private': is_private
            })
            
            # Validate required fields
            error = self.validate_required_fields(data, ['ownerId', 'playerName', 'roomName'])
            if error:
                logger.error(f"[{request_id}] Missing required field: {error}", extra={
                    'request_id': request_id,
                    'data': data
                })
                return self.error_response(400, f"Missing required field: {error}")
            
            # Generate room ID
            room_id = str(uuid.uuid4())
            logger.info(f"[{request_id}] Generated room ID: {room_id}", extra={
                'request_id': request_id,
                'room_id': room_id
            })
            
            # Initialize seats
            seats = {seat: '' for seat in ['North', 'East', 'South', 'West']}
            owner_seat = random.choice(['North', 'East', 'South', 'West'])
            seats[owner_seat] = owner_id
            
            logger.info(f"[{request_id}] Assigned owner to seat {owner_seat}", extra={
                'request_id': request_id,
                'owner_id': owner_id,
                'owner_seat': owner_seat,
                'seats': seats
            })
            
            # Set initial state
            state = 'waiting'
            
            # Initialize game data
            game_data = {
                'currentPhase': 'waiting',
                'turn': owner_seat,  # Use position (North/South/East/West) instead of userId
                'bids': [],
                'hands': {seat: [] for seat in ['North', 'East', 'South', 'West']},
                'tricks': []
            }
            
            # Create room object
            room = {
                'roomId': room_id,
                'ownerId': owner_id,
                'playerName': player_name,
                'roomName': room_name,
                'isPrivate': is_private,
                'seats': seats,
                'state': state,
                'gameData': game_data
            }
            
            logger.info(f"[{request_id}] Created room object", extra={
                'request_id': request_id,
                'room_id': room_id,
                'room_name': room_name,
                'owner_id': owner_id,
                'is_private': is_private
            })
            
            # Save to DynamoDB
            room_table = self.get_table('ROOM_TABLE')
            
            logger.info(f"[{request_id}] Saving room to DynamoDB", extra={
                'request_id': request_id,
                'room_id': room_id,
                'table_name': os.environ.get('ROOM_TABLE')
            })
            
            room_table.put_item(Item=room)
            
            logger.info(f"[{request_id}] Successfully saved room to DynamoDB", extra={
                'request_id': request_id,
                'room_id': room_id
            })
            
            # Update the user's connection record to reflect they're now in the room
            logger.info(f"[{request_id}] Updating user's current room", extra={
                'request_id': request_id,
                'user_id': owner_id,
                'room_id': room_id
            })
            
            self._update_user_room(owner_id, room_id, request_id)
            
            # Return success response with game state
            response_data = {
                'action': 'createRoom',
                'success': True,
                'room': room,
                'assignedSeat': owner_seat,
                'gameState': game_data,
                'message': 'Room created successfully'
            }
            
            duration = time.time() - start_time
            logger.info(f"[{request_id}] Room creation completed successfully", extra={
                'request_id': request_id,
                'room_id': room_id,
                'owner_id': owner_id,
                'duration_seconds': round(duration, 3)
            })
            
            return self.success_response(response_data, 201)
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{request_id}] Unexpected error in process_websocket_request", extra={
                'request_id': request_id,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'duration_seconds': round(duration, 3),
                'traceback': str(e.__traceback__) if hasattr(e, '__traceback__') else 'No traceback'
            })
            return self.error_response(500, f"Unexpected error: {str(e)}")
    
    def _log_request_info(self, event, context, request_id=None):
        """Log request information for debugging"""
        if not request_id:
            request_id = str(uuid.uuid4())
        
        logger.info(f"[{request_id}] WebSocket Create Room Request", extra={
            'request_id': request_id,
            'connection_id': event.get('requestContext', {}).get('connectionId'),
            'route_key': event.get('requestContext', {}).get('routeKey'),
            'request_time': event.get('requestContext', {}).get('requestTime'),
            'function_name': context.function_name if context else 'unknown',
            'function_version': context.function_version if context else 'unknown',
            'memory_limit': context.memory_limit_in_mb if context else 'unknown',
            'remaining_time': context.get_remaining_time_in_millis() if context else 'unknown'
        })
        return request_id
    
    def _update_user_room(self, user_id, room_id, request_id=None):
        """
        Update the user's current room in the connections table using db_utils
        """
        start_time = time.time()
        logger.info(f"[{request_id}] Starting update_user_room using db_utils", extra={
            'request_id': request_id,
            'user_id': user_id,
            'room_id': room_id,
            'operation': 'update_user_room'
        })
        
        try:
            # Use the existing db_utils method which is more robust
            success = db_utils.update_user_room(user_id, room_id)
            
            duration = time.time() - start_time
            logger.info(f"[{request_id}] update_user_room completed", extra={
                'request_id': request_id,
                'user_id': user_id,
                'room_id': room_id,
                'success': success,
                'duration_seconds': round(duration, 3)
            })
            
            if not success:
                logger.warning(f"[{request_id}] Failed to update user room using db_utils", extra={
                    'request_id': request_id,
                    'user_id': user_id,
                    'room_id': room_id
                })
                return False
            
            return success
                
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{request_id}] Error updating user room", extra={
                'request_id': request_id,
                'user_id': user_id,
                'room_id': room_id,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'duration_seconds': round(duration, 3),
                'traceback': str(e.__traceback__) if hasattr(e, '__traceback__') else 'No traceback'
            })
            
            # Don't let connection update failures break room creation
            logger.info(f"[{request_id}] Continuing with room creation despite connection update failure", extra={
                'request_id': request_id,
                'user_id': user_id,
                'room_id': room_id
            })
            return False

# Create handler instance
handler = WebSocketCreateRoomHandler()

# Lambda handler function
def lambda_handler(event, context):
    """
    Lambda handler function that delegates to the WebSocket handler
    """
    logger.info(f"LAMBDA HANDLER CALLED with event: {event}")
    logger.info(f"Event type: {type(event)}")
    logger.info(f"Event keys: {list(event.keys()) if isinstance(event, dict) else 'Not a dict'}")
    
    try:
        result = handler.handle_websocket_request(event, context)
        logger.info(f"Handler result: {result}")
        return result
    except Exception as e:
        logger.error(f"Exception in lambda_handler: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': f'Internal server error: {str(e)}'
        } 