# Authentication System Implementation

This document describes the implementation of the authentication system based on the Auth.md design specification.

## Overview

The authentication system implements JWT-based authentication with the following features:

- **Access Tokens**: JWT tokens that expire in 15 minutes
- **Refresh Tokens**: JWT tokens that expire in 7 days, stored in HttpOnly cookies
- **Automatic Redirects**: Unauthenticated users can be redirected to a login page
- **Flexible Protection**: APIs can be protected with standard error responses or redirects

## Token Configuration

### Access Token
- **Type**: JWT
- **Expiration**: 15 minutes
- **Usage**: Sent in Authorization header as `Bearer <token>`

### Refresh Token
- **Type**: JWT
- **Expiration**: 7 days
- **Storage**: HttpOnly, Secure, SameSite=Strict cookie
- **Usage**: Automatically sent by browser for token refresh

## API Endpoints

### 1. Login API (`POST /api/account/login`)

**Request Body:**
```json
{
  "username": "user@example.com",
  "password": "userpassword"
}
```

**Response:**
```json
{
  "statusCode": 200,
  "headers": {
    "Set-Cookie": "refresh_token=<token>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=604800"
  },
  "body": {
    "message": "Login successful",
    "accessToken": "<jwt_token>",
    "user": {
      "userId": "user123",
      "username": "username",
      "email": "user@example.com",
      "createdAt": "2024-01-01T00:00:00Z"
    },
    "expiresIn": 900,
    "tokenType": "Bearer"
  }
}
```

### 2. Refresh Token API (`POST /api/auth/refresh-token`)

**Request:** Automatically sends refresh token from cookie

**Response:**
```json
{
  "statusCode": 200,
  "headers": {
    "Set-Cookie": "refresh_token=<new_token>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=604800"
  },
  "body": {
    "message": "Token refreshed successfully",
    "accessToken": "<new_jwt_token>",
    "expiresIn": 900,
    "tokenType": "Bearer"
  }
}
```

## Protecting APIs

### Method 1: Using the `@protect_api` decorator (Recommended)

```python
from utils.auth_utils import protect_api, get_user_id_from_event, get_user_info_from_event

@protect_api()
def lambda_handler(event, context):
    """Standard protected API - returns 401 for unauthenticated users"""
    user_id = get_user_id_from_event(event)
    user_info = get_user_info_from_event(event)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Access granted',
            'user_id': user_id,
            'user_info': user_info
        })
    }
```

### Method 2: Using the `@protect_api` decorator with redirects

```python
@protect_api(redirect_on_failure=True, login_url="/login")
def lambda_handler(event, context):
    """Protected API with redirect - redirects unauthenticated users to login"""
    user_id = get_user_id_from_event(event)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Access granted',
            'user_id': user_id
        })
    }
```

### Method 3: Using the legacy `@require_auth` decorator

```python
from utils.auth_middleware import require_auth, get_user_id_from_event

@require_auth()
def lambda_handler(event, context):
    """Legacy protected API - returns 401 for unauthenticated users"""
    user_id = get_user_id_from_event(event)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Access granted',
            'user_id': user_id
        })
    }
```

### Method 4: Using the legacy decorator with redirects

```python
@require_auth(redirect_on_failure=True, login_url="/login")
def lambda_handler(event, context):
    """Legacy protected API with redirect support"""
    user_id = get_user_id_from_event(event)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Access granted',
            'user_id': user_id
        })
    }
```

## Base Handler Authentication Methods

The `BaseLambdaHandler` class provides additional authentication utilities:

```python
from base_handler import BaseLambdaHandler

class MyProtectedAPI(BaseLambdaHandler):
    def process_request(self, event, context):
        # Check if user is authenticated
        if not self.is_authenticated(event):
            return self.redirect_response("/login")
        
        # Or use the convenience method
        redirect_response = self.require_auth_or_redirect(event, "/login")
        if redirect_response:
            return redirect_response
        
        # Continue with protected logic
        return self.success_response({"message": "Protected data"})
```

## Environment Variables

Configure the following environment variables:

```bash
# JWT Secret (stored in AWS Secrets Manager)
JWT_SECRET_ID=Bridge/JWT

# Login URL for redirects (optional, defaults to /login)
LOGIN_URL=/login

# User table name
USER_TABLE=Users
```

## Client-Side Implementation

### 1. Login Flow

```javascript
async function login(username, password) {
    const response = await fetch('/api/account/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    });
    
    if (response.ok) {
        const data = await response.json();
        
        // Store access token in memory (not localStorage for security)
        localStorage.setItem('accessToken', data.accessToken);
        
        // Refresh token is automatically stored in HttpOnly cookie
        return data.user;
    }
    
    throw new Error('Login failed');
}
```

### 2. Making Authenticated Requests

```javascript
async function makeAuthenticatedRequest(url, options = {}) {
    const accessToken = localStorage.getItem('accessToken');
    
    if (!accessToken) {
        // Redirect to login
        window.location.href = '/login';
        return;
    }
    
    const response = await fetch(url, {
        ...options,
        headers: {
            ...options.headers,
            'Authorization': `Bearer ${accessToken}`
        }
    });
    
    if (response.status === 401) {
        // Token expired, try to refresh
        const refreshed = await refreshToken();
        if (refreshed) {
            // Retry the request
            return makeAuthenticatedRequest(url, options);
        } else {
            // Redirect to login
            window.location.href = '/login';
            return;
        }
    }
    
    return response;
}
```

### 3. Token Refresh

```javascript
async function refreshToken() {
    try {
        const response = await fetch('/api/auth/refresh-token', {
            method: 'POST',
            credentials: 'include' // Include cookies
        });
        
        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('accessToken', data.accessToken);
            return true;
        }
        
        return false;
    } catch (error) {
        return false;
    }
}
```

## Security Features

1. **HttpOnly Cookies**: Refresh tokens are stored in HttpOnly cookies to prevent XSS attacks
2. **Secure Cookies**: Cookies are marked as Secure for HTTPS-only transmission
3. **SameSite=Strict**: Prevents CSRF attacks
4. **Short-lived Access Tokens**: 15-minute expiration minimizes exposure window
5. **Automatic Token Refresh**: Seamless user experience with automatic token renewal

## Error Handling

### Authentication Errors

- **401 Unauthorized**: Invalid or missing token
- **302 Found**: Redirect to login page (when redirect_on_failure=True)

### Token Expiration

- Access tokens expire after 15 minutes
- Refresh tokens expire after 7 days
- Automatic refresh attempts when access token expires
- Graceful fallback to login page if refresh fails

## Migration Guide

### From Legacy Authentication

1. **Replace `@require_auth` with `@protect_api`**:
   ```python
   # Old
   @require_auth()
   
   # New
   @protect_api()
   ```

2. **Update imports**:
   ```python
   # Old
   from utils.auth_middleware import require_auth, get_user_id_from_event
   
   # New
   from utils.auth_utils import protect_api, get_user_id_from_event
   ```

3. **Add redirect support** (optional):
   ```python
   @protect_api(redirect_on_failure=True, login_url="/login")
   ```

### Environment Setup

1. Ensure `JWT_SECRET_ID` is set in AWS Secrets Manager
2. Set `LOGIN_URL` environment variable if using redirects
3. Verify `USER_TABLE` environment variable is configured

## Testing

### Test Protected Endpoints

```bash
# Test without authentication (should return 401 or redirect)
curl -X GET https://your-api.com/protected-endpoint

# Test with valid token
curl -X GET https://your-api.com/protected-endpoint \
  -H "Authorization: Bearer <your_jwt_token>"
```

### Test Token Refresh

```bash
# Test refresh with cookie
curl -X POST https://your-api.com/api/auth/refresh-token \
  -H "Cookie: refresh_token=<your_refresh_token>"
```

## Troubleshooting

### Common Issues

1. **"JWT secret key not found"**: Check `JWT_SECRET_ID` environment variable and AWS Secrets Manager
2. **"Token has expired"**: Access token expired, client should refresh
3. **"Invalid token type"**: Ensure you're using access tokens, not refresh tokens
4. **Cookie not set**: Verify HTTPS is enabled (required for Secure cookies)

### Debug Mode

Enable debug logging by setting environment variable:
```bash
DEBUG_AUTH=true
```

## Best Practices

1. **Always use HTTPS** in production (required for Secure cookies)
2. **Implement proper error handling** for authentication failures
3. **Use short-lived access tokens** (15 minutes is recommended)
4. **Implement automatic token refresh** on the client side
5. **Handle token expiration gracefully** with user-friendly messages
6. **Log authentication events** for security monitoring
7. **Regularly rotate JWT secrets** in production environments
