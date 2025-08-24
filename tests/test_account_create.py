import pytest
import json
import os
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
import sys

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.account_create import lambda_handler


class TestAccountCreate:
    """Test cases for account creation API."""
    
    @pytest.fixture
    def sample_account_data(self):
        """Sample account creation data."""
        return {
            'username': 'testuser@example.com',
            'email': 'testuser@example.com',
            'password': 'StrongPassword123!'
        }
    
    @pytest.fixture
    def mock_environment(self):
        """Set up test environment variables."""
        env_vars = {
            'USER_TABLE': 'test-users-table'
        }
        
        # Store original values
        original_env = {}
        for key in env_vars:
            if key in os.environ:
                original_env[key] = os.environ[key]
        
        # Set test values
        for key, value in env_vars.items():
            os.environ[key] = value
        
        yield env_vars
        
        # Restore original values
        for key in env_vars:
            if key in original_env:
                os.environ[key] = original_env[key]
            else:
                del os.environ[key]
    
    def test_lambda_handler_success_direct_data(self, sample_account_data, mock_environment):
        """Test successful account creation with direct event data."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            # Mock password hashing
            mock_password_utils.hash_password.return_value = ('hashed_password_123', 'salt_123')
            
            # Mock GSI scan - no existing users
            mock_table.scan.return_value = {'Count': 0, 'Items': []}
            
            # Mock successful user creation
            mock_table.put_item.return_value = {}
            
            result = lambda_handler(sample_account_data, {})
            
            assert result['statusCode'] == 201
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Account created successfully'
            assert 'user' in response_body
            assert response_body['user']['username'] == 'testuser@example.com'
            assert response_body['user']['email'] == 'testuser@example.com'
            assert 'userId' in response_body['user']
            assert 'createdAt' in response_body['user']
            
            # Verify user was saved to DynamoDB
            mock_table.put_item.assert_called_once()
            saved_user = mock_table.put_item.call_args[1]['Item']
            assert saved_user['username'] == 'testuser@example.com'
            assert saved_user['email'] == 'testuser@example.com'
            assert 'passwordHash' in saved_user
            assert saved_user['passwordHash'] != 'StrongPassword123!'  # Should be hashed
    
    def test_lambda_handler_success_body_wrapped_data(self, sample_account_data, mock_environment):
        """Test successful account creation with body-wrapped data."""
        event = {'body': json.dumps(sample_account_data)}
        
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            # Mock password hashing
            mock_password_utils.hash_password.return_value = ('hashed_password_123', 'salt_123')
            
            # Mock GSI scan - no existing users
            mock_table.scan.return_value = {'Count': 0, 'Items': []}
            
            # Mock successful user creation
            mock_table.put_item.return_value = {}
            
            result = lambda_handler(event, {})
            
            assert result['statusCode'] == 201
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Account created successfully'
    
    def test_lambda_handler_missing_required_fields(self, mock_environment):
        """Test account creation with missing required fields."""
        event = {
            'username': 'testuser@example.com',
            # Missing email and password
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Missing required fields'
        assert 'email' in response_body['message']
        assert 'password' in response_body['message']
    
    def test_lambda_handler_empty_fields(self, mock_environment):
        """Test account creation with empty required fields."""
        event = {
            'username': '',
            'email': '',
            'password': ''
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Missing required fields'
    
    def test_lambda_handler_invalid_json_body(self, mock_environment):
        """Test account creation with invalid JSON in body."""
        event = {'body': 'invalid json'}
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Invalid JSON'
    
    def test_lambda_handler_empty_body(self, mock_environment):
        """Test account creation with empty body."""
        event = {'body': ''}
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Missing required fields'
    
    def test_lambda_handler_weak_password(self, sample_account_data, mock_environment):
        """Test account creation with weak password."""
        weak_password_data = sample_account_data.copy()
        weak_password_data['password'] = 'weak'
        
        with patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            # Mock password validation failure
            mock_password_utils.validate_password_strength.return_value = (False, 'Password too weak')
            
            result = lambda_handler(weak_password_data, {})
            
            assert result['statusCode'] == 400
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Invalid password'
            # The actual message may vary, so just check that it contains error info
            assert 'password' in response_body['message'].lower()
    
    def test_lambda_handler_username_already_exists(self, sample_account_data, mock_environment):
        """Test account creation when username already exists."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            
            # Mock GSI scan - username exists
            mock_table.scan.return_value = {
                'Count': 1,
                'Items': [{'username': 'testuser@example.com', 'email': 'other@example.com'}]
            }
            
            result = lambda_handler(sample_account_data, {})
            
            assert result['statusCode'] == 409
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Username already exists'
            assert 'username already exists' in response_body['message'].lower()
    
    def test_lambda_handler_email_already_exists(self, sample_account_data, mock_environment):
        """Test account creation when email already exists."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            
            # Mock GSI scan - email exists
            mock_table.scan.return_value = {
                'Count': 1,
                'Items': [{'username': 'otheruser', 'email': 'testuser@example.com'}]
            }
            
            result = lambda_handler(sample_account_data, {})
            
            assert result['statusCode'] == 409
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Email already exists'
            assert 'email already exists' in response_body['message'].lower()
    
    def test_lambda_handler_gsi_scan_failure_fallback(self, sample_account_data, mock_environment):
        """Test account creation when GSI scan fails and falls back to table scan."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            # Mock password hashing
            mock_password_utils.hash_password.return_value = ('hashed_password_123', 'salt_123')
            
            # Mock GSI scan failure
            mock_table.scan.side_effect = [
                ClientError(
                    {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Index not found'}},
                    'Scan'
                ),
                {'Count': 0, 'Items': []}  # Fallback scan result
            ]
            
            # Mock successful user creation
            mock_table.put_item.return_value = {}
            
            result = lambda_handler(sample_account_data, {})
            
            # The function should handle the GSI failure gracefully and still succeed
            assert result['statusCode'] == 201
            assert mock_table.scan.call_count == 2  # GSI scan + fallback scan
    
    def test_lambda_handler_dynamodb_put_error(self, sample_account_data, mock_environment):
        """Test account creation when DynamoDB put operation fails."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            
            # Mock GSI scan - no existing users
            mock_table.scan.return_value = {'Count': 0, 'Items': []}
            
            # Mock DynamoDB put failure
            mock_table.put_item.side_effect = ClientError(
                {'Error': {'Code': 'ValidationException', 'Message': 'Invalid item'}},
                'PutItem'
            )
            
            result = lambda_handler(sample_account_data, {})
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'error' in response_body
    
    def test_lambda_handler_missing_table_env_var(self):
        """Test account creation with missing USER_TABLE environment variable."""
        # Ensure the environment variable is not set
        if 'USER_TABLE' in os.environ:
            del os.environ['USER_TABLE']
        
        result = lambda_handler({'username': 'test', 'email': 'test@test.com', 'password': 'Test123!'}, {})
        
        assert result['statusCode'] == 500
        response_body = json.loads(result['body'])
        assert 'error' in response_body
    
    def test_lambda_handler_cors_headers(self, sample_account_data, mock_environment):
        """Test that CORS headers are properly set."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            # Mock password hashing
            mock_password_utils.hash_password.return_value = ('hashed_password_123', 'salt_123')
            
            # Mock GSI scan - no existing users
            mock_table.scan.return_value = {'Count': 0, 'Items': []}
            
            # Mock successful user creation
            mock_table.put_item.return_value = {}
            
            result = lambda_handler(sample_account_data, {})
            
            assert result['statusCode'] == 201
            headers = result['headers']
            assert headers['Access-Control-Allow-Origin'] == '*'
            assert 'Content-Type' in headers
            assert 'Access-Control-Allow-Methods' in headers
    
    def test_lambda_handler_debug_logging(self, sample_account_data, mock_environment, capsys):
        """Test that debug logging is working."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_create.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock password validation
            mock_password_utils.validate_password_strength.return_value = (True, None)
            # Mock password hashing
            mock_password_utils.hash_password.return_value = ('hashed_password_123', 'salt_123')
            
            # Mock GSI scan - no existing users
            mock_table.scan.return_value = {'Count': 0, 'Items': []}
            
            # Mock successful user creation
            mock_table.put_item.return_value = {}
            
            lambda_handler(sample_account_data, {})
            
            captured = capsys.readouterr()
            assert 'DEBUG: Full event:' in captured.out
            assert 'DEBUG: Event body type:' in captured.out
            assert 'DEBUG: Parsed body:' in captured.out
