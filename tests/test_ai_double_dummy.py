import pytest
from lambdas import ai_double_dummy

def test_ai_double_dummy_stub():
    event = {}
    context = None
    response = ai_double_dummy.handler(event, context)
    assert response['statusCode'] == 200
    assert 'Double dummy analysis' in response['body'] 