import pytest
from lambdas import account_create
import json
import os
from unittest.mock import patch, MagicMock

@patch('lambdas.account_create.boto3')
def test_account_create_success(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table
    mock_table.scan.return_value = {'Count': 0}
    mock_table.put_item.return_value = {}
    event = {
        'body': json.dumps({'username': 'jacob', 'password': 'testpass'})
    }
    context = None
    response = account_create.handler(event, context)
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    assert 'user' in body
    user = body['user']
    assert user['username'] == 'jacob'
    assert 'userId' in user
    assert 'createdAt' in user
    assert 'passwordHash' not in user

@patch('lambdas.account_create.boto3')
def test_account_create_duplicate_username(mock_boto3):
    os.environ['USER_TABLE'] = 'users-table'
    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table
    mock_table.scan.return_value = {'Count': 1}
    event = {
        'body': json.dumps({'username': 'jacob', 'password': 'testpass'})
    }
    response = account_create.handler(event, None)
    assert response['statusCode'] == 409
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'exists' in body['error']

@patch('lambdas.account_create.boto3')
def test_account_create_missing_user_table_env(mock_boto3):
    if 'USER_TABLE' in os.environ:
        del os.environ['USER_TABLE']
    event = {
        'body': json.dumps({'username': 'jacob', 'password': 'testpass'})
    }
    response = account_create.handler(event, None)
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'USER_TABLE' in body['error']

def test_account_create_missing_fields():
    os.environ['USER_TABLE'] = 'users-table'
    event = {'body': json.dumps({'username': 'jacob'})}
    response = account_create.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body

    event = {'body': json.dumps({'password': 'testpass'})}
    response = account_create.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body

    event = {'body': None}
    response = account_create.handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body 