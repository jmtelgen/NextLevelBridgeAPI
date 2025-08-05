import json
import os
import random
import boto3
from botocore.exceptions import ClientError

SEATS = ['N', 'E', 'S', 'W']

def get_room_connections(user_ids, room_id):
    """
    Get active WebSocket connections for users in a specific room
    """
    try:
        connections_table_name = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE')
        if not connections_table_name:
            return []
        
        dynamodb = boto3.resource('dynamodb')
        connections_table = dynamodb.Table(connections_table_name)
        
        # Get connections for all users in the room
        connection_ids = []
        for user_id in user_ids:
            if user_id and not user_id.startswith('robot-'):  # Skip robot players
                response = connections_table.scan(
                    FilterExpression='#status = :status AND #userId = :userId',
                    ExpressionAttributeNames={'#status': 'status', '#userId': 'userId'},
                    ExpressionAttributeValues={':status': 'connected', ':userId': user_id}
                )
                connection_ids.extend([item['connectionId'] for item in response.get('Items', [])])
        
        return list(set(connection_ids))  # Remove duplicates
        
    except Exception as e:
        print(f"Error getting room connections: {str(e)}")
        return []

def broadcast_to_connections(connection_ids, message):
    """
    Send a message to multiple WebSocket connections
    """
    try:
        endpoint_url = os.environ.get('WEBSOCKET_ENDPOINT')
        if not endpoint_url:
            print("WEBSOCKET_ENDPOINT environment variable not set")
            return
        
        apigateway = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
        
        for connection_id in connection_ids:
            try:
                apigateway.post_to_connection(
                    ConnectionId=connection_id,
                    Data=json.dumps(message)
                )
                print(f"Message sent to connection {connection_id}")
            except Exception as e:
                print(f"Failed to send message to {connection_id}: {str(e)}")
                
    except Exception as e:
        print(f"Error broadcasting message: {str(e)}")

def update_user_room(user_id, room_id):
    """
    Update the user's current room in the connections table
    """
    try:
        connections_table_name = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE')
        if not connections_table_name:
            return
        
        dynamodb = boto3.resource('dynamodb')
        connections_table = dynamodb.Table(connections_table_name)
        
        # Find the user's connection and update their current room
        print(f"Attempting to scan connections table for user {user_id}")
        try:
            response = connections_table.scan(
                FilterExpression='#userId = :userId AND #status = :status',
                ExpressionAttributeNames={
                    '#userId': 'userId',
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':userId': user_id,
                    ':status': 'connected'
                }
            )
            print(f"Scan completed successfully")
        except ClientError as e:
            print(f"Scan failed with ClientError: {e.response['Error']['Message']}")
            return
        except Exception as e:
            print(f"Scan failed with unexpected error: {str(e)}")
            return
        
        print(f"Found {response.get('Count', 0)} connections for user {user_id}")
        if response.get('Items'):
            print(f"Connection items: {response.get('Items')}")
        
        for item in response.get('Items', []):
            connection_id = item.get('connectionId')
            if not connection_id:
                print(f"Warning: connectionId is missing or empty for user {user_id}")
                continue
            
            # Ensure connectionId is a string and not empty
            if not isinstance(connection_id, str) or not connection_id.strip():
                print(f"Warning: connectionId is not a valid string for user {user_id}: {connection_id}")
                continue
                
            try:
                key = {'connectionId': connection_id}
                print(f"Attempting to update connection with key: {key}")
                connections_table.update_item(
                    Key=key,
                    UpdateExpression='SET currentRoomId = :roomId',
                    ExpressionAttributeValues={':roomId': room_id}
                )
                print(f"Updated user {user_id} current room to {room_id}")
            except ClientError as e:
                print(f"Error updating connection {connection_id}: {e.response['Error']['Message']}")
                # Continue with other connections even if one fails
                continue
            
    except Exception as e:
        print(f"Error updating user room: {str(e)}")

def lambda_handler(event, context):
    """
    WebSocket handler for joining a room
    Expected event structure:
    {
        "requestContext": {
            "connectionId": "connection-id",
            "routeKey": "$connect" | "$disconnect" | "joinRoom"
        },
        "body": "{\"roomId\": \"room-id\", \"userId\": \"user-id\", \"seat\": \"N\"}"
    }
    """
    print(event)
    try:
        # Extract connection ID for potential future use
        connection_id = event.get('requestContext', {}).get('connectionId')
        route_key = event.get('requestContext', {}).get('routeKey')
        
        # Handle different route keys
        if route_key == '$connect':
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Connected'})
            }
        elif route_key == '$disconnect':
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Disconnected'})
            }
        elif route_key != 'joinRoom':
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid route key'})
            }
        
        # Parse the message body
        body = event.get('body')
        if not body:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing request body'})
            }
        
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract data from the nested data object, with fallback to top-level fields
        data = body.get('data', {})
        
        # Extract parameters with fallback to top-level fields
        user_id = data.get('userId') or body.get('userId')
        room_id = data.get('roomId') or body.get('roomId')
        requested_seat = data.get('seat') or body.get('seat')
        
        if not user_id or not room_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'userId and roomId required'})
            }
        
        # Fetch room
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})
            }
        
        dynamodb = boto3.resource('dynamodb')
        room_table = dynamodb.Table(room_table_name)
        
        # Use get_item with both partition key and sort key
        # First, we need to scan to find the room since we only have roomId
        room_result = room_table.scan(
            FilterExpression='roomId = :roomId',
            ExpressionAttributeValues={':roomId': room_id}
        )
        
        if room_result['Count'] == 0:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Room does not exist'})
            }
        
        room_item = room_result['Items'][0]
        
        # Check if user is already in the room
        if user_id in room_item['seats'].values():
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'User already in room'})
            }
        
        # Determine seat
        available_seats = [seat for seat, occupant in room_item['seats'].items() if not occupant]
        
        if requested_seat:
            if requested_seat not in SEATS:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Invalid seat'})
                }
            if room_item['seats'][requested_seat]:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Seat not available'})
                }
            seat_to_assign = requested_seat
        else:
            if not available_seats:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'No seats available'})
                }
            seat_to_assign = random.choice(available_seats)
        
        # Assign user to seat
        room_item['seats'][seat_to_assign] = user_id
        
        # Update user's current room in connections table
        update_user_room(user_id, room_id)
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Get all active connections for users in this room
        active_connections = get_room_connections(room_item['seats'].values(), room_id)
        
        # Broadcast the update to all users in the room
        broadcast_message = {
            'action': 'roomUpdated',
            'room': room_item,
            'updateType': 'userJoined',
            'newUser': user_id,
            'assignedSeat': seat_to_assign
        }
        
        broadcast_to_connections(active_connections, broadcast_message)
        
        # Return success response to the joining user with current game state
        response_data = {
            'action': 'joinRoom',
            'success': True,
            'room': room_item,
            'assignedSeat': seat_to_assign,
            'gameState': room_item.get('gameData', {})
        }
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_data)
        }
        
    except ClientError as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': e.response['Error']['Message']})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        } 