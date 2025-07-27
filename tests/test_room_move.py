import pytest
from lambdas import room_move

def test_room_move_stub():
    event = {}
    context = None
    response = room_move.handler(event, context)
    assert response['statusCode'] == 200
    assert 'Move processed' in response['body'] 