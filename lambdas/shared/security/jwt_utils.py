import jwt
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from .aws_secrets import get_jwt_secret


class JWTUtils:
    """Utility class for JWT token operations"""
    
    def __init__(self, secret_id: str = None, region_name: Optional[str] = None):
        """
        Initialize JWT utilities
        
        Args:
            secret_id: The AWS Secrets Manager secret ID for the JWT secret
                      If None, uses JWT_SECRET_ID environment variable or defaults to "Bridge/JWT"
            region_name: AWS region name. If None, uses default region from environment
        """
        self.secret_id = secret_id or os.environ.get('JWT_SECRET_ID', 'Bridge/JWT')
        self.region_name = region_name
        self._secret_key = None
    
    @property
    def secret_key(self) -> str:
        """Get the JWT secret key from AWS Secrets Manager"""
        if self._secret_key is None:
            try:
                self._secret_key = get_jwt_secret(self.secret_id, self.region_name)
                if not self._secret_key:
                    raise ValueError(f"JWT secret key is empty from secret {self.secret_id}")
            except Exception as e:
                raise Exception(f"Failed to retrieve JWT secret key: {str(e)}")
        return self._secret_key
    
    def generate_access_token(self, user_data: Dict[str, Any], expires_in_minutes: int = 15) -> str:
        """
        Generate a JWT access token
        
        Args:
            user_data: User data to include in the token payload
            expires_in_minutes: Token expiration time in minutes (default: 15)
            
        Returns:
            JWT access token string
        """
        payload = {
            'userId': user_data.get('userId'),
            'username': user_data.get('username'),
            'email': user_data.get('email'),
            'exp': datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            'iat': datetime.now(timezone.utc),
            'type': 'access'
        }
        
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    def generate_refresh_token(self, user_data: Dict[str, Any], expires_in_days: int = 7) -> str:
        """
        Generate a JWT refresh token
        
        Args:
            user_data: User data to include in the token payload
            expires_in_days: Token expiration time in days (default: 7)
            
        Returns:
            JWT refresh token string
        """
        payload = {
            'userId': user_data.get('userId'),
            'username': user_data.get('username'),
            'email': user_data.get('email'),
            'exp': datetime.now(timezone.utc) + timedelta(days=expires_in_days),
            'iat': datetime.now(timezone.utc),
            'type': 'refresh'
        }
        
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode a JWT token
        
        Args:
            token: JWT token string to verify
            
        Returns:
            Decoded token payload
            
        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            raise jwt.InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise jwt.InvalidTokenError(f"Invalid token: {str(e)}")
    
    def refresh_access_token(self, refresh_token: str, expires_in_minutes: int = 15) -> str:
        """
        Generate a new access token using a valid refresh token
        
        Args:
            refresh_token: Valid refresh token
            expires_in_minutes: New access token expiration time in minutes
            
        Returns:
            New JWT access token string
            
        Raises:
            jwt.InvalidTokenError: If refresh token is invalid
        """
        try:
            # Verify the refresh token
            payload = self.verify_token(refresh_token)
            
            # Check if it's actually a refresh token
            if payload.get('type') != 'refresh':
                raise jwt.InvalidTokenError("Token is not a refresh token")
            
            # Generate new access token with same user data
            user_data = {
                'userId': payload.get('userId'),
                'username': payload.get('username'),
                'email': payload.get('email')
            }
            
            return self.generate_access_token(user_data, expires_in_minutes)
            
        except jwt.InvalidTokenError as e:
            raise jwt.InvalidTokenError(f"Invalid refresh token: {str(e)}")
    
    def is_token_expired(self, token: str) -> bool:
        """
        Check if a JWT token is expired
        
        Args:
            token: JWT token string to check
            
        Returns:
            True if token is expired, False otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'], options={'verify_exp': False})
            exp_timestamp = payload.get('exp')
            
            if exp_timestamp is None:
                return True
            
            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            return datetime.now(timezone.utc) > exp_datetime
            
        except jwt.InvalidTokenError:
            return True
    
    def get_token_expiration(self, token: str) -> Optional[datetime]:
        """
        Get the expiration time of a JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Token expiration datetime or None if invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'], options={'verify_exp': False})
            exp_timestamp = payload.get('exp')
            
            if exp_timestamp is None:
                return None
            
            return datetime.fromtimestamp(exp_timestamp)
            
        except jwt.InvalidTokenError:
            return None


# Convenience functions for backward compatibility
def generate_access_token(user_data: Dict[str, Any], expires_in_minutes: int = 15, 
                         secret_id: str = None, region_name: Optional[str] = None) -> str:
    """Generate a JWT access token"""
    jwt_utils = JWTUtils(secret_id, region_name)
    return jwt_utils.generate_access_token(user_data, expires_in_minutes)


def generate_refresh_token(user_data: Dict[str, Any], expires_in_days: int = 7,
                          secret_id: str = None, region_name: Optional[str] = None) -> str:
    """Generate a JWT refresh token"""
    jwt_utils = JWTUtils(secret_id, region_name)
    return jwt_utils.generate_refresh_token(user_data, expires_in_days)


def verify_token(token: str, secret_id: str = None, region_name: Optional[str] = None) -> Dict[str, Any]:
    """Verify and decode a JWT token"""
    jwt_utils = JWTUtils(secret_id, region_name)
    return jwt_utils.verify_token(token)


def refresh_access_token(refresh_token: str, expires_in_minutes: int = 15,
                        secret_id: str = None, region_name: Optional[str] = None) -> str:
    """Generate a new access token using a valid refresh token"""
    jwt_utils = JWTUtils(secret_id, region_name)
    return jwt_utils.refresh_access_token(refresh_token, expires_in_minutes)
