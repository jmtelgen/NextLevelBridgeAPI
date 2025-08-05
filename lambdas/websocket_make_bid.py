import json
import os
import boto3
from botocore.exceptions import ClientError

VALID_BIDS = ['pass', '1C', '1D', '1H', '1S', '1NT', '2C', '2D', '2H', '2S', '2NT', 
              '3C', '3D', '3H', '3S', '3NT', '4C', '4D', '4H', '4S', '4NT', 
              '5C', '5D', '5H', '5S', '5NT', '6C', '6D', '6H', '6S', '6NT', 
              '7C', '7D', '7H', '7S', '7NT', 'double', 'redouble']

def lambda_handler(event, context):
    """
    WebSocket handler for making a bid
    Expected event structure:
    {
        "requestContext": {
            "connectionId": "connection-id",
            "routeKey": "$connect" | "$disconnect" | "makeBid"
        },
        "body": "{\"roomId\": \"room-id\", \"userId\": \"user-id\", \"bid\": \"1H\"}"
    }
    """
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
        elif route_key != 'makeBid':
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
        
        # Extract parameters
        user_id = body.get('userId')
        room_id = body.get('roomId')
        bid = body.get('bid')
        
        if not user_id or not room_id or not bid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'userId, roomId, and bid required'})
            }
        
        # Validate bid
        if bid not in VALID_BIDS:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Invalid bid. Valid bids: {", ".join(VALID_BIDS)}'})
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
        room_result = room_table.get_item(Key={'roomId': room_id})
        
        if 'Item' not in room_result:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Room does not exist'})
            }
        
        room_item = room_result['Item']
        
        # Check if room is in bidding phase
        if room_item['state'] != 'bidding':
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Room is not in bidding phase'})
            }
        
        # Check if it's the user's turn
        game_data = room_item.get('gameData', {})
        current_turn = game_data.get('turn')
        
        if current_turn != user_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Not your turn to bid'})
            }
        
        # Find user's seat
        user_seat = None
        for seat, occupant in room_item['seats'].items():
            if occupant == user_id:
                user_seat = seat
                break
        
        if not user_seat:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'User not found in room'})
            }
        
        # Add bid to game data
        if 'bids' not in game_data:
            game_data['bids'] = []
        
        bid_entry = {
            'seat': user_seat,
            'bid': bid,
            'timestamp': int(boto3.client('sts').get_caller_identity()['Account'])  # Simple timestamp
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
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'action': 'makeBid',
                'success': True,
                'bid': bid_entry,
                'nextTurn': next_player,
                'gameData': game_data,
                'message': f'Bid {bid} recorded successfully'
            })
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