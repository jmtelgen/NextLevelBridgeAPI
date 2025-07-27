import pytest
from lambdas import room_state

def test_room_state_stub():
    event = {}
    context = None
    response = room_state.handler(event, context)
    assert response['statusCode'] == 200
    assert 'Room state' in response['body'] 