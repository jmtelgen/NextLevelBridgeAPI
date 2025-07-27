import json

def handler(event, context):
    # TODO: Implement move logic
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Move processed (stub)'})
    } 