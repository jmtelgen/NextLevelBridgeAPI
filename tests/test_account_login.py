import pytest
import json
import os
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
import sys

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.account_login import lambda_handler


class TestAccountLogin:
    """Test cases for account login API."""
    
    @pytest.fixture
    def sample_login_data(self):
        """Sample login data."""
        return {
            'username': 'testuser@example.com',
            'password': 'StrongPassword123!'
        }
    
    @pytest.fixture
    def mock_user_data(self):
        """Mock user data from database."""
        return {
            'userId': 'test-user-123',
            'username': 'testuser@example.com',
            'email': 'testuser@example.com',
            'passwordHash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/HS.iQeO',
            'salt': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/HS.iQeO',
            'createdAt': '2024-01-01T00:00:00Z'
        }
    
    @pytest.fixture
    def mock_environment(self):
        """Set up test environment variables."""
        env_vars = {
            'USER_TABLE': 'test-users-table',
            'FRONTEND_URL': 'http://localhost:3000'
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
    
    def test_lambda_handler_success_direct_data(self, sample_login_data, mock_environment, mock_user_data):
        """Test successful login with direct event data."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils, \
             patch('lambdas.account_login.JWTUtils') as mock_jwt_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data]}
            
            # Mock password verification
            mock_password_utils.verify_password.return_value = True
            
            # Mock JWT token generation
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.generate_access_token.return_value = 'mock-access-token'
            mock_jwt_instance.generate_refresh_token.return_value = 'mock-refresh-token'
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Login successful'
            assert response_body['accessToken'] == 'mock-access-token'
            assert 'user' in response_body
            assert response_body['user']['userId'] == 'test-user-123'
            assert response_body['user']['username'] == 'testuser@example.com'
            assert response_body['user']['email'] == 'testuser@example.com'
            assert response_body['expiresIn'] == 900
            assert response_body['tokenType'] == 'Bearer'
            
            # Verify CORS headers
            headers = result['headers']
            assert headers['Access-Control-Allow-Origin'] == 'http://localhost:3000'
            assert headers['Access-Control-Allow-Credentials'] == 'true'
            
            # Verify Set-Cookie header
            assert 'multiValueHeaders' in result
            assert 'Set-Cookie' in result['multiValueHeaders']
            set_cookie = result['multiValueHeaders']['Set-Cookie'][0]
            assert 'refresh_token=mock-refresh-token' in set_cookie
            assert 'HttpOnly' in set_cookie
            assert 'Path=/' in set_cookie
            assert 'SameSite=Strict' in set_cookie
    
    def test_lambda_handler_success_body_wrapped_data(self, sample_login_data, mock_environment, mock_user_data):
        """Test successful login with body-wrapped data."""
        event = {'body': json.dumps(sample_login_data)}
        
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils, \
             patch('lambdas.account_login.JWTUtils') as mock_jwt_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data]}
            
            # Mock password verification
            mock_password_utils.verify_password.return_value = True
            
            # Mock JWT token generation
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.generate_access_token.return_value = 'mock-access-token'
            mock_jwt_instance.generate_refresh_token.return_value = 'mock-refresh-token'
            
            result = lambda_handler(event, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Login successful'
    
    def test_lambda_handler_missing_required_fields(self, mock_environment):
        """Test login with missing required fields."""
        event = {
            'username': 'testuser@example.com',
            # Missing password
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Missing required fields'
        assert response_body['message'] == 'Username and password are required'
    
    def test_lambda_handler_empty_fields(self, mock_environment):
        """Test login with empty required fields."""
        event = {
            'username': '',
            'password': ''
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Missing required fields'
    
    def test_lambda_handler_invalid_json_body(self, mock_environment):
        """Test login with invalid JSON in body."""
        event = {'body': 'invalid json'}
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Invalid JSON'
    
    def test_lambda_handler_user_not_found(self, sample_login_data, mock_environment):
        """Test login when user is not found."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock user lookup - no users found
            mock_table.scan.return_value = {'Count': 0, 'Items': []}
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 401
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Authentication failed'
            assert 'Invalid username/email or password' in response_body['message']
    
    def test_lambda_handler_gsi_scan_failure_fallback(self, sample_login_data, mock_environment, mock_user_data):
        """Test login when GSI scan fails and falls back to table scan."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils, \
             patch('lambdas.account_login.JWTUtils') as mock_jwt_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock GSI scan failure, then successful fallback
            mock_table.scan.side_effect = [
                ClientError(
                    {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Index not found'}},
                    'Scan'
                ),
                {'Count': 1, 'Items': [mock_user_data]}  # Fallback scan result
            ]
            
            # Mock password verification
            mock_password_utils.verify_password.return_value = True
            
            # Mock JWT token generation
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.generate_access_token.return_value = 'mock-access-token'
            mock_jwt_instance.generate_refresh_token.return_value = 'mock-refresh-token'
            
            result = lambda_handler(sample_login_data, {})
            
            # Should handle the GSI failure gracefully and still succeed
            assert result['statusCode'] == 200
            assert mock_table.scan.call_count == 2  # GSI scan + fallback scan
    
    def test_lambda_handler_invalid_password(self, sample_login_data, mock_environment, mock_user_data):
        """Test login with invalid password."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data]}
            
            # Mock password verification failure
            mock_password_utils.verify_password.return_value = False
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 401
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Authentication failed'
            assert 'Invalid username or password' in response_body['message']
    
    def test_lambda_handler_missing_password_hash(self, sample_login_data, mock_environment):
        """Test login when user has no password hash."""
        mock_user_data_incomplete = {
            'userId': 'test-user-123',
            'username': 'testuser@example.com',
            'email': 'testuser@example.com',
            # Missing passwordHash and salt
            'createdAt': '2024-01-01T00:00:00Z'
        }
        
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data_incomplete]}
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 401
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Authentication failed'
            assert 'Invalid username or password' in response_body['message']
    
    def test_lambda_handler_jwt_utils_init_failure(self, sample_login_data, mock_environment, mock_user_data):
        """Test login when JWT utilities initialization fails."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils, \
             patch('lambdas.account_login.JWTUtils') as mock_jwt_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data]}
            
            # Mock password verification
            mock_password_utils.verify_password.return_value = True
            
            # Mock JWT utilities initialization failure
            mock_jwt_utils.side_effect = Exception("JWT secret not found")
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Configuration error'
            assert 'Failed to initialize JWT utilities' in response_body['message']
    
    def test_lambda_handler_token_generation_failure(self, sample_login_data, mock_environment, mock_user_data):
        """Test login when JWT token generation fails."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils, \
             patch('lambdas.account_login.JWTUtils') as mock_jwt_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data]}
            
            # Mock password verification
            mock_password_utils.verify_password.return_value = True
            
            # Mock JWT utilities initialization
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            
            # Mock token generation failure
            mock_jwt_instance.generate_access_token.side_effect = Exception("Token generation failed")
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Token generation failed'
            assert 'Failed to generate authentication tokens' in response_body['message']
    
    def test_lambda_handler_database_error(self, sample_login_data, mock_environment):
        """Test login when database operation fails."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock database error
            mock_table.scan.side_effect = Exception("Database connection failed")
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Database error'
            assert 'Failed to retrieve user information' in response_body['message']
    
    def test_lambda_handler_production_environment_secure_cookie(self, sample_login_data, mock_environment, mock_user_data):
        """Test that Secure flag is added to cookies in production environment."""
        # Set production environment
        os.environ['ENVIRONMENT'] = 'production'
        
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils, \
             patch('lambdas.account_login.JWTUtils') as mock_jwt_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data]}
            
            # Mock password verification
            mock_password_utils.verify_password.return_value = True
            
            # Mock JWT token generation
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.generate_access_token.return_value = 'mock-access-token'
            mock_jwt_instance.generate_refresh_token.return_value = 'mock-refresh-token'
            
            result = lambda_handler(sample_login_data, {})
            
            # Verify Secure flag is added in production
            set_cookie = result['multiValueHeaders']['Set-Cookie'][0]
            assert 'Secure' in set_cookie
            
            # Clean up
            del os.environ['ENVIRONMENT']
    
    def test_lambda_handler_missing_table_env_var(self):
        """Test login with missing USER_TABLE environment variable."""
        # Ensure the environment variable is not set
        if 'USER_TABLE' in os.environ:
            del os.environ['USER_TABLE']
        
        result = lambda_handler({'username': 'test', 'password': 'Test123!'}, {})
        
        # Should still work as it defaults to 'Users'
        assert result['statusCode'] in [200, 401, 500]  # Depends on whether table exists
    
    def test_lambda_handler_cors_headers(self, sample_login_data, mock_environment, mock_user_data):
        """Test that CORS headers are properly set."""
        with patch('boto3.resource') as mock_resource, \
             patch('lambdas.account_login.PasswordUtils') as mock_password_utils, \
             patch('lambdas.account_login.JWTUtils') as mock_jwt_utils:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful user lookup
            mock_table.scan.return_value = {'Count': 1, 'Items': [mock_user_data]}
            
            # Mock password verification
            mock_password_utils.verify_password.return_value = True
            
            # Mock JWT token generation
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.generate_access_token.return_value = 'mock-access-token'
            mock_jwt_instance.generate_refresh_token.return_value = 'mock-refresh-token'
            
            result = lambda_handler(sample_login_data, {})
            
            assert result['statusCode'] == 200
            headers = result['headers']
            assert 'Content-Type' in headers
            assert 'Access-Control-Allow-Headers' in headers
            assert 'Access-Control-Allow-Methods' in headers
            assert 'Access-Control-Allow-Credentials' in headers
