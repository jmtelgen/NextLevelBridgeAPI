import pytest
import json
import os
from unittest.mock import patch, MagicMock
import sys

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.account_refresh_token import lambda_handler


class TestAccountRefreshToken:
    """Test cases for account refresh token API."""
    
    @pytest.fixture
    def sample_refresh_token(self):
        """Sample refresh token."""
        return 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJ0ZXN0LXVzZXItMTIzIiwidXNlcm5hbWUiOiJ0ZXN0dXNlckBleGFtcGxlLmNvbSIsImVtYWlsIjoidGVzdHVzZXJAZXhhbXBsZS5jb20iLCJ0eXBlIjoicmVmcmVzaCIsImlhdCI6MTY0MDk5NTIwMCwiZXhwIjoxNjQxNjAwODAwfQ.example_signature'
    
    @pytest.fixture
    def sample_event_with_cookies(self, sample_refresh_token):
        """Sample event with refresh token in cookies."""
        return {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'headers': {
                'Cookie': f'refresh_token={sample_refresh_token}; other_cookie=value'
            }
        }
    
    @pytest.fixture
    def sample_event_with_body(self, sample_refresh_token):
        """Sample event with refresh token in request body."""
        return {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'body': json.dumps({
                'refresh_token': sample_refresh_token
            })
        }
    
    @pytest.fixture
    def sample_event_direct_data(self, sample_refresh_token):
        """Sample event with refresh token as direct data."""
        return {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'refresh_token': sample_refresh_token
        }
    
    def test_lambda_handler_success_cookies(self, sample_event_with_cookies, sample_refresh_token):
        """Test successful token refresh using cookies."""
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(sample_event_with_cookies, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
            assert response_body['accessToken'] == 'new-access-token'
            assert response_body['expiresIn'] == 900
            assert response_body['tokenType'] == 'Bearer'
            assert response_body['request_id'] == 'test-request-123'
            
            # Verify JWT utilities was called correctly
            mock_jwt_utils.assert_called_once()
            mock_jwt_instance.refresh_access_token.assert_called_once_with(sample_refresh_token, expires_in_minutes=15)
            
            # Verify Set-Cookie header
            headers = result['headers']
            assert 'Set-Cookie' in headers
            set_cookie = headers['Set-Cookie']
            assert f'refresh_token={sample_refresh_token}' in set_cookie
            assert 'HttpOnly' in set_cookie
            assert 'Secure' in set_cookie
            assert 'SameSite=Strict' in set_cookie
            assert 'Path=/' in set_cookie
            assert 'Max-Age=604800' in set_cookie
    
    def test_lambda_handler_success_body(self, sample_event_with_body, sample_refresh_token):
        """Test successful token refresh using request body."""
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(sample_event_with_body, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
            assert response_body['accessToken'] == 'new-access-token'
    
    def test_lambda_handler_success_direct_data(self, sample_event_direct_data, sample_refresh_token):
        """Test successful token refresh using direct event data."""
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(sample_event_direct_data, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
            assert response_body['accessToken'] == 'new-access-token'
    
    def test_lambda_handler_missing_refresh_token(self):
        """Test token refresh with missing refresh token."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            }
            # No refresh token in cookies or body
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Missing refresh token'
        assert 'Refresh token not found' in response_body['message']
        assert response_body['request_id'] == 'test-request-123'
    
    def test_lambda_handler_empty_refresh_token(self):
        """Test token refresh with empty refresh token."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'headers': {
                'Cookie': 'refresh_token=; other_cookie=value'
            }
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Missing refresh token'
    
    def test_lambda_handler_invalid_json_body(self):
        """Test token refresh with invalid JSON in body."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'body': 'invalid json'
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Invalid JSON'
        assert 'Request body must be valid JSON' in response_body['message']
    
    def test_lambda_handler_jwt_utils_init_failure(self, sample_event_with_cookies):
        """Test token refresh when JWT utilities initialization fails."""
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_utils.side_effect = Exception("JWT secret not found")
            
            result = lambda_handler(sample_event_with_cookies, {})
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Configuration error'
            assert 'Failed to initialize JWT utilities' in response_body['message']
            assert response_body['request_id'] == 'test-request-123'
    
    def test_lambda_handler_token_refresh_failure(self, sample_event_with_cookies, sample_refresh_token):
        """Test token refresh when JWT token refresh fails."""
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.side_effect = Exception("Invalid refresh token")
            
            result = lambda_handler(sample_event_with_cookies, {})
            
            assert result['statusCode'] == 401
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Token refresh failed'
            assert response_body['message'] == 'Invalid refresh token'
            assert response_body['request_id'] == 'test-request-123'
    
    def test_lambda_handler_case_insensitive_cookie_header(self, sample_refresh_token):
        """Test that cookie header is case insensitive."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'headers': {
                'cookie': f'refresh_token={sample_refresh_token}; other_cookie=value'  # lowercase 'cookie'
            }
        }
        
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(event, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
    
    def test_lambda_handler_multiple_cookies(self, sample_refresh_token):
        """Test token refresh with multiple cookies."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'headers': {
                'Cookie': f'first_cookie=value; refresh_token={sample_refresh_token}; last_cookie=value'
            }
        }
        
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(event, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
    
    def test_lambda_handler_cookie_with_spaces(self, sample_refresh_token):
        """Test token refresh with cookies containing spaces."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'headers': {
                'Cookie': f'  refresh_token={sample_refresh_token}  ; other_cookie=value  '
            }
        }
        
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(event, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
    
    def test_lambda_handler_fallback_to_body_when_cookies_empty(self, sample_refresh_token):
        """Test that function falls back to body when cookies are empty."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'headers': {
                'Cookie': ''  # Empty cookies
            },
            'body': json.dumps({
                'refresh_token': sample_refresh_token
            })
        }
        
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(event, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
    
    def test_lambda_handler_fallback_to_body_when_cookies_none(self, sample_refresh_token):
        """Test that function falls back to body when cookies are None."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            },
            'headers': {
                'Cookie': None  # None cookies
            },
            'body': json.dumps({
                'refresh_token': sample_refresh_token
            })
        }
        
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(event, {})
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['message'] == 'Token refreshed successfully'
    
    def test_lambda_handler_cors_headers(self, sample_event_with_cookies, sample_refresh_token):
        """Test that CORS headers are properly set."""
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(sample_event_with_cookies, {})
            
            assert result['statusCode'] == 200
            headers = result['headers']
            assert 'Content-Type' in headers
            assert 'Access-Control-Allow-Origin' in headers
            assert 'Access-Control-Allow-Headers' in headers
            assert 'Access-Control-Allow-Methods' in headers
    
    def test_lambda_handler_missing_request_context(self, sample_refresh_token):
        """Test token refresh with missing request context."""
        event = {
            'headers': {
                'Cookie': f'refresh_token={sample_refresh_token}'
            }
        }
        
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(event, {})
            
            # Should still work, just with default values
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['request_id'] == 'unknown'
    
    def test_lambda_handler_missing_identity(self, sample_refresh_token):
        """Test token refresh with missing identity in request context."""
        event = {
            'requestContext': {
                'requestId': 'test-request-123'
                # Missing identity
            },
            'headers': {
                'Cookie': f'refresh_token={sample_refresh_token}'
            }
        }
        
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.return_value = 'new-access-token'
            
            result = lambda_handler(event, {})
            
            # Should still work, just with default values
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['request_id'] == 'test-request-123'
    
    def test_lambda_handler_unexpected_exception(self, sample_event_with_cookies):
        """Test token refresh with unexpected exception."""
        with patch('lambdas.account_refresh_token.JWTUtils') as mock_jwt_utils:
            # Mock JWT utilities to work, but cause an unexpected error later
            mock_jwt_instance = MagicMock()
            mock_jwt_utils.return_value = mock_jwt_instance
            mock_jwt_instance.refresh_access_token.side_effect = Exception("Unexpected database error")
            
            result = lambda_handler(sample_event_with_cookies, {})
            
            assert result['statusCode'] == 401
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Token refresh failed'
            assert response_body['message'] == 'Unexpected database error'
