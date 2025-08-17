# Bridge Login API with JWT Tokens and bcrypt Password Hashing

This document describes the login API implementation with JWT token authentication and bcrypt password hashing with salt.

## Overview

The login API provides secure authentication using:
- **JWT Tokens**: For stateless authentication
- **bcrypt**: For password hashing with enhanced salt
- **DynamoDB**: For user storage

## Architecture

```
Client → Login API → bcrypt Verification → JWT Generation
```

## Environment Variables Required

```bash
# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key-here
JWT_ACCESS_TOKEN_EXPIRY=3600  # 1 hour in seconds
JWT_REFRESH_TOKEN_EXPIRY=604800  # 7 days in seconds

# Database
USER_TABLE=your-users-table-name
```

## API Endpoints

### 1. Login API (`/login`)

**Method:** POST  
**Content-Type:** application/json

**Request Body:**
```json
{
  "username": "user@example.com",
  "password": "plaintext_password"
}
```

**Response (Success - 200):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "userId": "user-123",
    "username": "user@example.com",
    "createdAt": "2024-01-01T00:00:00Z"
  },
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

**Response (Error - 401):**
```json
{
  "error": "Invalid username or password"
}
```

### 2. Account Creation API (`/create`)

**Method:** POST  
**Content-Type:** application/json

**Request Body:**
```json
{
  "username": "user@example.com",
  "password": "plaintext_password"
}
```

**Response (Success - 201):**
```json
{
  "user": {
    "userId": "user-123",
    "username": "user@example.com",
    "createdAt": "2024-01-01T00:00:00Z"
  },
  "message": "Account created successfully"
}
```

### 3. Token Refresh API (`/refresh`)

**Method:** POST  
**Content-Type:** application/json

**Request Body:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response (Success - 200):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

## Client-Side Implementation

### Simple Login (Frontend)

```javascript
async function login(username, password) {
  const response = await fetch('/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      username: username,
      password: password
    })
  });
  
  return response.json();
}

// Usage
const result = await login('user@example.com', 'MySecurePassword123!');
if (result.access_token) {
  localStorage.setItem('access_token', result.access_token);
  localStorage.setItem('refresh_token', result.refresh_token);
}
```

### Using JWT Tokens

```javascript
// Store tokens securely
localStorage.setItem('access_token', response.access_token);
localStorage.setItem('refresh_token', response.refresh_token);

// Add to API requests
function makeAuthenticatedRequest(url, options = {}) {
  const token = localStorage.getItem('access_token');
  
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`
    }
  });
}

// Handle token refresh
async function refreshToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  
  const response = await fetch('/refresh', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      refresh_token: refreshToken
    })
  });
  
  if (response.ok) {
    const data = await response.json();
    localStorage.setItem('access_token', data.access_token);
    return data.access_token;
  } else {
    // Redirect to login
    window.location.href = '/login';
  }
}
```

## Protected API Usage

### Using the Authentication Middleware

```python
from utils.auth_middleware import require_auth, get_user_from_event

@require_auth
def protected_handler(event, context):
    # This function is now protected
    user = get_user_from_event(event)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Hello {user["username"]}!',
            'user_id': user['user_id']
        })
    }
```

### Manual Token Validation

```python
from utils.auth_middleware import validate_token

def some_handler(event, context):
    auth_header = event.get('headers', {}).get('Authorization', '')
    token = auth_header.replace('Bearer ', '')
    
    payload = validate_token(token)
    if payload:
        user_id = payload['user_id']
        # Process request
    else:
        return {'statusCode': 401, 'body': 'Unauthorized'}
```

## Security Features

### 1. Password Security
- **Enhanced bcrypt Hashing**: Passwords hashed with bcrypt plus custom salt
- **Unique Salt Per User**: Each user gets a unique salt for maximum security
- **Strength Validation**: Password strength requirements enforced
- **No Plaintext Storage**: Passwords never stored in plaintext

### 2. Token Security
- **JWT Tokens**: Stateless authentication tokens
- **Access/Refresh Pattern**: Short-lived access tokens with refresh capability
- **Secure Headers**: CORS and security headers included

### 3. Error Handling
- **Generic Error Messages**: No information leakage in error responses
- **Rate Limiting**: Can be added via API Gateway
- **Input Validation**: All inputs validated and sanitized

## Database Schema

### Users Table (DynamoDB)

```json
{
  "userId": "string (partition key)",
  "username": "string (unique)",
  "passwordHash": "string (bcrypt hash with enhanced salt)",
  "salt": "string (required enhanced salt)",
  "createdAt": "string (ISO timestamp)"
}
```

## Password Security Details

### bcrypt Hashing with Enhanced Salt
- **Enhanced Salt**: Custom salt generated and combined with password before bcrypt hashing
- **Double Protection**: bcrypt adds its own salt automatically, plus our custom salt
- **Work Factor**: Configurable cost factor for hash computation
- **One-way**: Passwords cannot be reversed from hashes
- **Unique Per User**: Each user gets a unique salt for maximum security

## Deployment

### 1. AWS Lambda Functions
- Deploy each API as separate Lambda functions
- Set environment variables
- Configure API Gateway triggers

### 2. IAM Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:region:account:table/users-table"
    }
  ]
}
```

### 3. API Gateway Configuration
- Enable CORS
- Set up authentication headers
- Configure rate limiting
- Set up custom domain (optional)

## Testing

### Test Login Flow
```bash
# Call login API directly
curl -X POST https://your-api-gateway-url/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test@example.com",
    "password": "MySecurePassword123!"
  }'
```

### Test Account Creation
```bash
# Create new account
curl -X POST https://your-api-gateway-url/create \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser@example.com",
    "password": "MySecurePassword123!"
  }'
```

## Troubleshooting

### Common Issues

1. **JWT Secret Not Set**
   - Verify JWT_SECRET_KEY environment variable
   - Ensure secret is at least 32 characters long

2. **Database Connection Issues**
   - Verify USER_TABLE environment variable
   - Check IAM permissions for DynamoDB access

3. **CORS Issues**
   - Ensure API Gateway CORS is configured
   - Check Access-Control-Allow-* headers

4. **Password Validation**
   - Check password meets strength requirements
   - Ensure password is sent as plaintext (not encrypted)

## Best Practices

1. **Token Storage**: Store tokens in httpOnly cookies or secure storage
2. **Token Rotation**: Implement automatic token refresh
3. **Error Logging**: Log authentication failures for monitoring
4. **Rate Limiting**: Implement rate limiting on login endpoints
5. **Monitoring**: Set up CloudWatch alarms for authentication failures
6. **HTTPS**: Always use HTTPS in production
7. **Password Policy**: Enforce strong password requirements
