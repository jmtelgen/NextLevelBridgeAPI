import json

def handler(event, context):
    # TODO: Implement room state fetch logic
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Room state (stub)'})
    } 