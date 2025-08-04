import json
import os
import random
from models.room import Room
import boto3
from botocore.exceptions import ClientError

SEATS = ['N', 'E', 'S', 'W']

def handler(event, context):
    try:
        body = event.get('body')
        if body is None:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Missing request body'})}
        if isinstance(body, str):
            body = json.loads(body)
        user_id = body.get('userId')
        room_id = body.get('roomId')
        requested_seat = body.get('seat')
        if not user_id or not room_id:
            return {'statusCode': 400, 'body': json.dumps({'error': 'userId and roomId required'})}
        # Fetch room
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})}
        dynamodb = boto3.resource('dynamodb')
        room_table = dynamodb.Table(room_table_name)
        room_result = room_table.scan(
            FilterExpression='roomId = :r',
            ExpressionAttributeValues={':r': room_id}
        )
        if room_result['Count'] == 0:
            return {'statusCode': 404, 'body': json.dumps({'error': 'Room does not exist'})}
        room_item = room_result['Items'][0]
        # Check if user is already in the room
        if user_id in room_item['seats'].values():
            return {'statusCode': 400, 'body': json.dumps({'error': 'User already in room'})}
        # Determine seat
        available_seats = [seat for seat, occupant in room_item['seats'].items() if not occupant]
        if requested_seat:
            if requested_seat not in SEATS:
                return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid seat'})}
            if room_item['seats'][requested_seat]:
                return {'statusCode': 400, 'body': json.dumps({'error': 'Seat not available'})}
            seat_to_assign = requested_seat
        else:
            if not available_seats:
                return {'statusCode': 400, 'body': json.dumps({'error': 'No seats available'})}
            seat_to_assign = random.choice(available_seats)
        # Assign user to seat
        room_item['seats'][seat_to_assign] = user_id
        # Save updated room
        room_table.put_item(Item=room_item)
        return {'statusCode': 200, 'body': json.dumps({'room': room_item})}
    except ClientError as e:
        return {'statusCode': 500, 'body': json.dumps({'error': e.response['Error']['Message']})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})} 