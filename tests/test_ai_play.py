import pytest
from lambdas import ai_play

def test_ai_play_stub():
    event = {}
    context = None
    response = ai_play.handler(event, context)
    assert response['statusCode'] == 200
    assert 'AI play suggestion' in response['body'] 