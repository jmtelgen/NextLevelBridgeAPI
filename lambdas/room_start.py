import json
import os
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
        if not user_id or not room_id:
            return {'statusCode': 400, 'body': json.dumps({'error': 'userId and roomId required'})}
        # Check user existence
        user_table_name = os.environ.get('USER_TABLE')
        if not user_table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'USER_TABLE environment variable not set'})}
        dynamodb = boto3.resource('dynamodb')
        user_table = dynamodb.Table(user_table_name)
        user_result = user_table.scan(
            FilterExpression='userId = :u',
            ExpressionAttributeValues={':u': user_id}
        )
        if user_result['Count'] == 0:
            return {'statusCode': 401, 'body': json.dumps({'error': 'User is not logged in or does not exist'})}
        # Fetch room
        room_table_name = os.environ.get('ROOM_TABLE')
        if not room_table_name:
            return {'statusCode': 500, 'body': json.dumps({'error': 'ROOM_TABLE environment variable not set'})}
        room_table = dynamodb.Table(room_table_name)
        room_result = room_table.scan(
            FilterExpression='roomId = :r',
            ExpressionAttributeValues={':r': room_id}
        )
        if room_result['Count'] == 0:
            return {'statusCode': 404, 'body': json.dumps({'error': 'Room does not exist'})}
        room_item = room_result['Items'][0]
        # Check owner
        if room_item['ownerId'] != user_id:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Only the room owner can start the game'})}
        # Check state
        if room_item['state'] != 'waiting':
            return {'statusCode': 400, 'body': json.dumps({'error': 'Room is not in waiting state'})}
        # Fill empty seats with robots
        for seat in SEATS:
            if not room_item['seats'][seat]:
                room_item['seats'][seat] = f'robot-{seat}'
        room_item['state'] = 'bidding'
        room_table.put_item(Item=room_item)
        return {'statusCode': 200, 'body': json.dumps({'room': room_item})}
    except ClientError as e:
        return {'statusCode': 500, 'body': json.dumps({'error': e.response['Error']['Message']})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})} 