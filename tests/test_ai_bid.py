import pytest
from lambdas import ai_bid

def test_ai_bid_stub():
    event = {}
    context = None
    response = ai_bid.handler(event, context)
    assert response['statusCode'] == 200
    assert 'AI bid suggestion' in response['body'] 