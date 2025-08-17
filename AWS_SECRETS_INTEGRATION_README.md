# AWS Secrets Manager Integration for JWT Secrets

This document explains how to integrate AWS Secrets Manager with your Bridge application for secure JWT secret management.

## Overview

Instead of storing JWT secrets in environment variables, this integration uses AWS Secrets Manager to:
- **Securely store** JWT secrets
- **Automatically retrieve** secrets when needed
- **Support multiple environments** with different secrets
- **Follow security best practices** for secret management

## Architecture

```
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│   Lambda       │    │   AWS Secrets       │    │   JWT Utils    │
│   Function     │───▶│   Manager           │───▶│   & Auth       │
│                │    │   (Bridge/JWT)      │    │   Middleware   │
└─────────────────┘    └─────────────────────┘    └─────────────────┘
```

## Prerequisites

### 1. AWS Credentials
Ensure your Lambda execution role or local environment has access to AWS Secrets Manager:

```bash
# Option 1: Environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# Option 2: AWS CLI configuration
aws configure

# Option 3: IAM role (for Lambda)
# Attach appropriate policies to your Lambda execution role
```

### 2. IAM Permissions
Your Lambda execution role needs these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "arn:aws:secretsmanager:region:account:secret:Bridge/JWT*"
            ]
        }
    ]
}
```

### 3. AWS Secrets Manager Secret
Create a secret named `Bridge/JWT` in AWS Secrets Manager:

```bash
# Using AWS CLI
aws secretsmanager create-secret \
    --name "Bridge/JWT" \
    --description "JWT secret key for Bridge application" \
    --secret-string "your-super-secret-jwt-key-here"

# Or using AWS Console
# 1. Go to AWS Secrets Manager
# 2. Click "Store a new secret"
# 3. Choose "Other type of secret"
# 4. Enter your JWT secret
# 5. Name it "Bridge/JWT"
```

## Secret Format Options

AWS Secrets Manager supports multiple secret formats. The integration handles all of these:

### 1. Plain Text Secret
```json
"your-super-secret-jwt-key-here"
```

### 2. JSON Object Secret
```json
{
    "jwt_secret": "your-super-secret-jwt-key-here"
}
```

### 3. Alternative JSON Fields
The integration automatically detects these field names:
- `jwt_secret`
- `secret`
- `key`
- `value`

### 4. Binary Secret
Binary secrets are automatically converted to UTF-8 strings.

## Usage Examples

### 1. Basic Usage (Default Secret ID)

```python
from utils.jwt_utils import JWTUtils

# Automatically uses "Bridge/JWT" secret
jwt_utils = JWTUtils()

# Generate tokens
access_token = jwt_utils.generate_access_token(user_data)
refresh_token = jwt_utils.generate_refresh_token(user_data)
```

### 2. Custom Secret ID

```python
from utils.jwt_utils import JWTUtils

# Use a different secret
jwt_utils = JWTUtils(secret_id="Custom/JWT")

# Or with custom region
jwt_utils = JWTUtils(
    secret_id="Custom/JWT", 
    region_name="us-west-2"
)
```

### 3. Authentication Middleware

```python
from utils.auth_middleware import require_auth

@require_auth()  # Uses default "Bridge/JWT"
def protected_function(event, context):
    # Your protected code here
    pass

@require_auth(secret_id="Custom/JWT")
def custom_protected_function(event, context):
    # Uses custom secret
    pass
```

### 4. Direct Secret Retrieval

```python
from utils.aws_secrets import get_jwt_secret

# Get secret directly
secret = get_jwt_secret("Bridge/JWT")

# With custom region
secret = get_jwt_secret("Bridge/JWT", region_name="us-west-2")
```

## Environment Configuration

### Lambda Environment Variables

```bash
# Required
USER_TABLE=Users

# Optional (defaults to "Bridge/JWT")
JWT_SECRET_ID=Bridge/JWT

# Optional (defaults to AWS_DEFAULT_REGION)
AWS_REGION=us-east-1
```

### Local Development

```bash
# .env file
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
USER_TABLE=Users
JWT_SECRET_ID=Bridge/JWT  # Optional, defaults to "Bridge/JWT"
```

### Local Development

```bash
# .env file
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
USER_TABLE=Users
```

## Error Handling

The integration provides comprehensive error handling:

### 1. Secret Not Found
```python
try:
    jwt_utils = JWTUtils("NonExistent/Secret")
    secret = jwt_utils.secret_key
except Exception as e:
    print(f"Secret not found: {e}")
```

### 2. Invalid Secret Format
```python
try:
    secret = get_jwt_secret("Bridge/JWT")
except Exception as e:
    print(f"Invalid secret format: {e}")
```

### 3. AWS Permissions
```python
try:
    secret = get_jwt_secret("Bridge/JWT")
except Exception as e:
    print(f"Permission denied: {e}")
```

## Testing

### 1. Run the Test Script

```bash
# Make sure you have AWS credentials configured
python test_aws_secrets.py
```

### 2. Test Output Example

```
🔑 AWS Secrets Manager JWT Integration Test
==================================================
🌍 Using AWS region: us-west-2

🔐 Testing SecretsManager class...
✅ SecretsManager initialized successfully
✅ JWT secret retrieved successfully (length: 64)
   Secret preview: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

🚀 Testing convenience function...
✅ Convenience function worked (length: 64)

🎫 Testing JWT utilities...
✅ JWTUtils initialized successfully
✅ Access token generated (length: 234)
✅ Refresh token generated (length: 245)
✅ Access token verified successfully
   User ID: test_user_123
   Username: test@example.com
   Token type: access
✅ Access token refreshed successfully (length: 234)

⚠️  Testing error handling...
✅ Error handling worked correctly: Failed to retrieve JWT secret key: Secret NonExistent/Secret not found

==================================================
📊 Test Results: 4/4 tests passed
🎉 All tests passed! AWS Secrets Manager integration is working correctly.
```

## Security Best Practices

### 1. Secret Rotation
- **Rotate secrets regularly** (every 6-12 months)
- **Use different secrets** for different environments
- **Monitor secret access** through CloudTrail

### 2. Access Control
- **Principle of least privilege** for IAM roles
- **Restrict secret access** to only necessary services
- **Use resource-based policies** when possible

### 3. Monitoring
- **Enable CloudTrail** for API calls
- **Set up CloudWatch alarms** for secret access
- **Monitor for unusual access patterns**

## Troubleshooting

### Common Issues

#### 1. "AWS credentials not found"
```bash
# Solution: Configure AWS credentials
aws configure
# or
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

#### 2. "Secret Bridge/JWT not found"
```bash
# Solution: Create the secret
aws secretsmanager create-secret \
    --name "Bridge/JWT" \
    --secret-string "your-jwt-secret"
```

#### 3. "Access denied"
```bash
# Solution: Check IAM permissions
# Ensure your role has secretsmanager:GetSecretValue permission
```

#### 4. "Invalid secret format"
```bash
# Solution: Check secret value in AWS Console
# Ensure it's a valid string or JSON
```

### Debug Mode

Enable debug logging by setting environment variables:

```bash
export AWS_SECRETS_DEBUG=true
export JWT_DEBUG=true
```

## Migration from Environment Variables

### Before (Environment Variables)
```python
import os

class JWTUtils:
    def __init__(self):
        self.secret_key = os.environ.get('JWT_SECRET_KEY')
        if not self.secret_key:
            raise ValueError("JWT_SECRET_KEY environment variable is required")
```

### After (AWS Secrets Manager)
```python
from utils.aws_secrets import get_jwt_secret

class JWTUtils:
    def __init__(self, secret_id: str = "Bridge/JWT"):
        self.secret_id = secret_id
        self._secret_key = None
    
    @property
    def secret_key(self):
        if self._secret_key is None:
            self._secret_key = get_jwt_secret(self.secret_id)
        return self._secret_key
```

## Cost Considerations

### AWS Secrets Manager Pricing
- **$0.40 per secret per month**
- **$0.05 per 10,000 API calls**
- **Free tier**: 1 secret, 1,000 API calls/month

### Optimization Tips
- **Cache secrets** in Lambda execution context
- **Use appropriate TTL** for your use case
- **Monitor API call frequency**

## Next Steps

1. **Create the secret** in AWS Secrets Manager
2. **Configure IAM permissions** for your Lambda role
3. **Test the integration** using the test script
4. **Deploy your Lambda functions**
5. **Monitor secret access** through CloudTrail

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify AWS credentials and permissions
3. Test with the provided test script
4. Check CloudWatch logs for detailed error messages

## Related Documentation

- [AWS Secrets Manager User Guide](https://docs.aws.amazon.com/secretsmanager/)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [JWT.io](https://jwt.io/) - JWT token information
- [bcrypt](https://pypi.org/project/bcrypt/) - Password hashing library
