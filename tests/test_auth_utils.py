import pytest
import json
import os
from unittest.mock import patch, MagicMock, Mock
from lambdas.utils.auth_utils import (
    protect_api,
    validate_and_extract_user,
    validate_jwt_token,
    create_redirect_response,
    create_unauthorized_response,
    get_user_id_from_event,
    get_user_info_from_event,
    is_authenticated
)


class TestAuthUtils:
    """Test suite for authentication utility functions"""
    
    @pytest.fixture
    def mock_event(self):
        """Sample Lambda event with headers"""
        return {
            'headers': {
                'Authorization': 'Bearer test.jwt.token.here',
                'Content-Type': 'application/json'
            },
            'body': '{"test": "data"}'
        }
    
    @pytest.fixture
    def mock_context(self):
        """Sample Lambda context"""
        return MagicMock()
    
    def test_protect_api_decorator_success(self, mock_event, mock_context):
        """Test successful API protection with decorator"""
        with patch('lambdas.utils.auth_utils.validate_and_extract_user') as mock_validate:
            mock_validate.return_value = {'userId': 'user-123', 'username': 'testuser'}
            
            @protect_api()
            def test_handler(event, context):
                return {'statusCode': 200, 'body': 'success'}
            
            response = test_handler(mock_event, mock_context)
            
            assert response['statusCode'] == 200
            assert response['body'] == 'success'
            assert mock_event['user'] == {'userId': 'user-123', 'username': 'testuser'}
    
    def test_protect_api_decorator_redirect_on_failure(self, mock_event, mock_context):
        """Test API protection with redirect on failure"""
        with patch('lambdas.utils.auth_utils.validate_and_extract_user') as mock_validate:
            mock_validate.side_effect = Exception("Authentication failed")
            
            @protect_api(redirect_on_failure=True, login_url="/login")
            def test_handler(event, context):
                return {'statusCode': 200, 'body': 'success'}
            
            response = test_handler(mock_event, mock_context)
            
            assert response['statusCode'] == 302
            assert 'Location' in response['headers']
            assert response['headers']['Location'] == '/login'
    
    def test_protect_api_decorator_error_on_failure(self, mock_event, mock_context):
        """Test API protection with error on failure"""
        with patch('lambdas.utils.auth_utils.validate_and_extract_user') as mock_validate:
            mock_validate.side_effect = Exception("Authentication failed")
            
            @protect_api()
            def test_handler(event, context):
                return {'statusCode': 200, 'body': 'success'}
            
            response = test_handler(mock_event, mock_context)
            
            assert response['statusCode'] == 401
            assert 'error' in json.loads(response['body'])
    
    def test_validate_and_extract_user_success(self, mock_event):
        """Test successful user validation and extraction"""
        with patch('lambdas.utils.auth_utils.validate_jwt_token') as mock_validate:
            mock_validate.return_value = {'userId': 'user-123', 'username': 'testuser'}
            
            user = validate_and_extract_user(mock_event)
            
            assert user['userId'] == 'user-123'
            assert user['username'] == 'testuser'
            mock_validate.assert_called_once_with('test.jwt.token.here', None, None)
    
    def test_validate_and_extract_user_missing_auth_header(self):
        """Test user validation with missing authorization header"""
        event = {'headers': {}, 'body': '{"test": "data"}'}
        
        with pytest.raises(Exception, match="Authorization header is required"):
            validate_and_extract_user(event)
    
    def test_validate_and_extract_user_invalid_auth_format(self):
        """Test user validation with invalid authorization header format"""
        event = {'headers': {'Authorization': 'InvalidFormat'}, 'body': '{"test": "data"}'}
        
        with pytest.raises(Exception, match="Authorization header must start with 'Bearer '"):
            validate_and_extract_user(event)
    
    def test_validate_and_extract_user_empty_token(self):
        """Test user validation with empty token"""
        event = {'headers': {'Authorization': 'Bearer '}, 'body': '{"test": "data"}'}
        
        with pytest.raises(Exception, match="JWT token is required"):
            validate_and_extract_user(event)
    
    def test_validate_jwt_token_success(self):
        """Test successful JWT token validation"""
        with patch('lambdas.utils.auth_utils.get_jwt_secret') as mock_get_secret:
            mock_get_secret.return_value = 'test-secret-key'
            
            with patch('jwt.decode') as mock_decode:
                mock_decode.return_value = {
                    'type': 'access',
                    'userId': 'user-123',
                    'username': 'testuser',
                    'email': 'test@example.com'
                }
                
                user = validate_jwt_token('test.jwt.token', 'secret-id', 'us-east-1')
                
                assert user['userId'] == 'user-123'
                assert user['username'] == 'testuser'
                assert user['email'] == 'test@example.com'
    
    def test_validate_jwt_token_missing_secret(self):
        """Test JWT token validation with missing secret"""
        with patch('lambdas.utils.auth_utils.get_jwt_secret') as mock_get_secret:
            mock_get_secret.return_value = None
            
            with pytest.raises(Exception, match="JWT secret key not found"):
                validate_jwt_token('test.jwt.token')
    
    def test_validate_jwt_token_invalid_type(self):
        """Test JWT token validation with invalid token type"""
        with patch('lambdas.utils.auth_utils.get_jwt_secret') as mock_get_secret:
            mock_get_secret.return_value = 'test-secret-key'
            
            with patch('jwt.decode') as mock_decode:
                mock_decode.return_value = {
                    'type': 'refresh',  # Wrong type
                    'userId': 'user-123'
                }
                
                with pytest.raises(Exception, match="Invalid token type. Access token required."):
                    validate_jwt_token('test.jwt.token')
    
    def test_validate_jwt_token_missing_user_id(self):
        """Test JWT token validation with missing userId"""
        with patch('lambdas.utils.auth_utils.get_jwt_secret') as mock_get_secret:
            mock_get_secret.return_value = 'test-secret-key'
            
            with patch('jwt.decode') as mock_decode:
                mock_decode.return_value = {
                    'type': 'access',
                    # Missing userId
                    'username': 'testuser'
                }
                
                with pytest.raises(Exception, match="Token missing required userId field"):
                    validate_jwt_token('test.jwt.token')
    
    def test_create_redirect_response(self):
        """Test redirect response creation"""
        response = create_redirect_response('/login', 302)
        
        assert response['statusCode'] == 302
        assert response['headers']['Location'] == '/login'
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert body['error'] == 'Authentication required'
        assert body['redirect_url'] == '/login'
    
    def test_create_unauthorized_response(self):
        """Test unauthorized response creation"""
        response = create_unauthorized_response('Invalid token', 401)
        
        assert response['statusCode'] == 401
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert body['error'] == 'Unauthorized'
        assert body['message'] == 'Invalid token'
    
    def test_get_user_id_from_event(self, mock_event):
        """Test getting user ID from event"""
        mock_event['user'] = {'userId': 'user-123', 'username': 'testuser'}
        
        user_id = get_user_id_from_event(mock_event)
        assert user_id == 'user-123'
    
    def test_get_user_id_from_event_missing_user(self):
        """Test getting user ID from event without user"""
        event = {'headers': {}, 'body': '{}'}
        
        with pytest.raises(Exception, match="User information not available. Ensure @protect_api decorator is used."):
            get_user_id_from_event(event)
    
    def test_get_user_info_from_event(self, mock_event):
        """Test getting user info from event"""
        mock_event['user'] = {'userId': 'user-123', 'username': 'testuser', 'email': 'test@example.com'}
        
        user_info = get_user_info_from_event(mock_event)
        assert user_info['userId'] == 'user-123'
        assert user_info['username'] == 'testuser'
        assert user_info['email'] == 'test@example.com'
    
    def test_get_user_info_from_event_missing_user(self):
        """Test getting user info from event without user"""
        event = {'headers': {}, 'body': '{}'}
        
        with pytest.raises(Exception, match="User information not available. Ensure @protect_api decorator is used."):
            get_user_info_from_event(event)
    
    def test_is_authenticated_true(self, mock_event):
        """Test authentication check when user is authenticated"""
        with patch('lambdas.utils.auth_utils.validate_and_extract_user') as mock_validate:
            mock_validate.return_value = {'userId': 'user-123'}
            
            result = is_authenticated(mock_event)
            assert result is True
    
    def test_is_authenticated_false(self):
        """Test authentication check when user is not authenticated"""
        event = {'headers': {}, 'body': '{}'}
        
        result = is_authenticated(event)
        assert result is False
    
    def test_protect_api_with_custom_secret_id(self, mock_event, mock_context):
        """Test API protection with custom secret ID"""
        with patch('lambdas.utils.auth_utils.validate_and_extract_user') as mock_validate:
            mock_validate.return_value = {'userId': 'user-123'}
            
            @protect_api(secret_id='CustomSecret')
            def test_handler(event, context):
                return {'statusCode': 200, 'body': 'success'}
            
            response = test_handler(mock_event, mock_context)
            
            assert response['statusCode'] == 200
            # Verify the secret_id was passed through
            mock_validate.assert_called_once()
    
    def test_protect_api_with_custom_region(self, mock_event, mock_context):
        """Test API protection with custom region"""
        with patch('lambdas.utils.auth_utils.validate_and_extract_user') as mock_validate:
            mock_validate.return_value = {'userId': 'user-123'}
            
            @protect_api(region_name='eu-west-1')
            def test_handler(event, context):
                return {'statusCode': 200, 'body': 'success'}
            
            response = test_handler(mock_event, mock_context)
            
            assert response['statusCode'] == 200
            # Verify the region was passed through
            mock_validate.assert_called_once()
