import boto3
import json
import os
from typing import Optional
from botocore.exceptions import ClientError, NoCredentialsError


class SecretsManager:
    """Utility class for interacting with AWS Secrets Manager"""
    
    def __init__(self, region_name: Optional[str] = None):
        """
        Initialize the Secrets Manager client
        
        Args:
            region_name: AWS region name. If None, uses default region from environment
        """
        try:
            self.client = boto3.client(
                'secretsmanager',
                region_name=region_name or os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
            )
        except NoCredentialsError:
            raise Exception("AWS credentials not found. Please configure your AWS credentials.")
    
    def get_secret(self, secret_id: str) -> str:
        """
        Retrieve a secret from AWS Secrets Manager
        
        Args:
            secret_id: The identifier for the secret
            
        Returns:
            The secret value as a string
            
        Raises:
            Exception: If the secret cannot be retrieved
        """
        try:
            response = self.client.get_secret_value(SecretId=secret_id)
            
            # Handle different types of secrets
            if 'SecretString' in response:
                return response['SecretString']
            elif 'SecretBinary' in response:
                # Convert binary secret to string
                return response['SecretBinary'].decode('utf-8')
            else:
                raise Exception("Secret value not found in response")
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'DecryptionFailureException':
                raise Exception(f"Failed to decrypt secret {secret_id}: {str(e)}")
            elif error_code == 'InternalServiceErrorException':
                raise Exception(f"Internal AWS service error for secret {secret_id}: {str(e)}")
            elif error_code == 'InvalidParameterException':
                raise Exception(f"Invalid parameter for secret {secret_id}: {str(e)}")
            elif error_code == 'InvalidRequestException':
                raise Exception(f"Invalid request for secret {secret_id}: {str(e)}")
            elif error_code == 'ResourceNotFoundException':
                raise Exception(f"Secret {secret_id} not found: {str(e)}")
            else:
                raise Exception(f"Failed to retrieve secret {secret_id}: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error retrieving secret {secret_id}: {str(e)}")
    
    def get_jwt_secret(self, secret_id: str = "Bridge/JWT") -> str:
        """
        Retrieve the JWT secret from AWS Secrets Manager
        
        Args:
            secret_id: The secret ID for the JWT secret (defaults to "Bridge/JWT")
            
        Returns:
            The JWT secret as a string
        """
        try:
            secret_value = self.get_secret(secret_id)
            
            # If the secret is stored as JSON, try to parse it
            try:
                secret_data = json.loads(secret_value)
                # Look for common JWT secret field names
                if 'jwt_secret' in secret_data:
                    return secret_data['jwt_secret']
                elif 'secret' in secret_data:
                    return secret_data['secret']
                elif 'key' in secret_data:
                    return secret_data['key']
                elif 'value' in secret_data:
                    return secret_data['value']
                else:
                    # Return the entire JSON string if no specific field found
                    return secret_value
            except json.JSONDecodeError:
                # If not JSON, return as-is
                return secret_value
                
        except Exception as e:
            raise Exception(f"Failed to retrieve JWT secret from {secret_id}: {str(e)}")


def get_jwt_secret(secret_id: str = None, region_name: Optional[str] = None) -> str:
    """
    Convenience function to get JWT secret
    
    Args:
        secret_id: The secret ID for the JWT secret
                  If None, uses JWT_SECRET_ID environment variable or defaults to "Bridge/JWT"
        region_name: AWS region name. If None, uses default region from environment
        
    Returns:
        The JWT secret as a string
    """
    if secret_id is None:
        secret_id = os.environ.get('JWT_SECRET_ID', 'Bridge/JWT')
    
    secrets_manager = SecretsManager(region_name=region_name)
    return secrets_manager.get_jwt_secret(secret_id)
