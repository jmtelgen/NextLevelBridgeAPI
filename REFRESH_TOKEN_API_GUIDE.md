# Refresh Token API Guide

## Overview

The refresh token API (`POST /api/auth/refresh-token`) is designed to work **WITHOUT** requiring an Authorization header. This is intentional and follows security best practices.

## Why No Authentication Header?

### 1. **Circular Dependency Prevention**
- Access tokens expire after 15 minutes
- When expired, users can't make authenticated requests
- If refresh endpoint required auth, users couldn't refresh expired tokens
- This would create a deadlock situation

### 2. **Security Best Practice**
- Refresh tokens are long-lived (7 days) and stored in HttpOnly cookies
- They should be independent of access tokens
- Refresh endpoints should be accessible even when access tokens are expired

### 3. **Proper Authentication Flow**
```
Login → Get Access Token (15min) + Refresh Token (7 days)
  ↓
Use Access Token for API calls
  ↓
Access Token Expires (15 min)
  ↓
Use Refresh Token to get new Access Token (no auth header needed)
  ↓
Continue using new Access Token
```

## How It Works

### **Primary Method: Cookies (Recommended)**
```javascript
// The refresh token is automatically sent in cookies
const response = await fetch('/api/auth/refresh-token', {
    method: 'POST',
    credentials: 'include', // Important: include cookies
    headers: {
        'Content-Type': 'application/json'
    }
    // No Authorization header needed!
});
```

### **Fallback Method: Request Body**
```javascript
// Alternative: send refresh token in request body
const response = await fetch('/api/auth/refresh-token', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        refresh_token: 'your_refresh_token_here'
    })
    // No Authorization header needed!
});
```

## API Response

### **Success (200)**
```json
{
    "message": "Token refreshed successfully",
    "accessToken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "expiresIn": 900,
    "tokenType": "Bearer",
    "request_id": "abc123"
}
```

### **Missing Token (400)**
```json
{
    "error": "Missing refresh token",
    "message": "Refresh token not found in cookies or request body. Please log in again.",
    "request_id": "abc123"
}
```

### **Invalid Token (401)**
```json
{
    "error": "Token refresh failed",
    "message": "Your refresh token has expired. Please log in again.",
    "request_id": "abc123"
}
```

## Frontend Implementation

### **1. Automatic Token Refresh**
```javascript
class AuthService {
    async refreshToken() {
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
            console.error('Token refresh failed:', error);
            return false;
        }
    }
    
    async makeAuthenticatedRequest(url, options = {}) {
        const accessToken = localStorage.getItem('accessToken');
        
        if (!accessToken) {
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
            const refreshed = await this.refreshToken();
            if (refreshed) {
                // Retry the request with new token
                return this.makeAuthenticatedRequest(url, options);
            } else {
                // Redirect to login
                window.location.href = '/login';
                return;
            }
        }
        
        return response;
    }
}
```

### **2. Interceptor Pattern**
```javascript
// Add response interceptor to automatically refresh tokens
const originalFetch = window.fetch;
window.fetch = async function(url, options = {}) {
    const response = await originalFetch(url, options);
    
    if (response.status === 401 && url !== '/api/auth/refresh-token') {
        // Try to refresh token
        const refreshed = await refreshToken();
        if (refreshed) {
            // Retry original request
            return originalFetch(url, options);
        }
    }
    
    return response;
};
```

## Testing

### **Test Without Authentication (Should Work)**
```bash
# Test with cookies
curl -X POST https://your-api.com/api/auth/refresh-token \
  -H "Content-Type: application/json" \
  -H "Cookie: refresh_token=your_token_here"

# Test with request body
curl -X POST https://your-api.com/api/auth/refresh-token \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your_token_here"}'
```

### **Test With Authentication (Optional)**
```bash
# This should also work but is not required
curl -X POST https://your-api.com/api/auth/refresh-token \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -H "Cookie: refresh_token=your_refresh_token"
```

## Common Issues

### **Issue: "Missing Authorization header" Error**
**Cause**: The refresh token API is protected by `@require_auth` decorator
**Solution**: Remove the decorator from the refresh token endpoint

### **Issue: Refresh Token Not Found**
**Cause**: Cookie not being sent or parsed correctly
**Solution**: 
1. Ensure `credentials: 'include'` is set
2. Check cookie name matches exactly: `refresh_token`
3. Verify cookie is HttpOnly and Secure

### **Issue: CORS Errors**
**Cause**: Frontend and API on different domains
**Solution**: Ensure CORS headers are properly configured

## Security Notes

1. **Refresh tokens are stored in HttpOnly cookies** - protected from XSS
2. **Cookies are marked Secure** - only sent over HTTPS
3. **Cookies use SameSite=Strict** - protected from CSRF
4. **Refresh tokens expire after 7 days** - limited lifetime
5. **No sensitive data in access tokens** - minimal exposure window

## Summary

The refresh token API is intentionally designed to work **without** authentication headers. This allows users to refresh expired access tokens and maintain their session seamlessly. The security is handled through the refresh token itself, not through access token validation.
