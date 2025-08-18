#!/usr/bin/env python3
"""
Test script to verify the login API is properly setting the Set-Cookie header
"""

import requests
import json

def test_login_api():
    """
    Test the login API to see if it sets the Set-Cookie header
    """
    print("🧪 Testing Login API Set-Cookie Header")
    print("=" * 60)
    
    # Test credentials (update these with real test credentials)
    test_credentials = {
        "username": "test@example.com",  # Update with real test username
        "password": "testpassword"       # Update with real test password
    }
    
    # Test login endpoint (update with your actual URL)
    login_url = "https://your-api-gateway-url.com/api/account/login"
    
    print(f"Testing login endpoint: {login_url}")
    print(f"Test credentials: {test_credentials['username']}")
    print()
    
    try:
        # Make login request
        print("🚀 Making login request...")
        response = requests.post(
            login_url,
            json=test_credentials,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        print(f"✅ Response received!")
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Headers: {dict(response.headers)}")
        
        # Check for Set-Cookie header
        set_cookie_header = response.headers.get('Set-Cookie')
        if set_cookie_header:
            print(f"   ✅ Set-Cookie header found: {set_cookie_header}")
            
            # Check if it contains refresh_token
            if 'refresh_token=' in set_cookie_header:
                print("   ✅ Set-Cookie contains refresh_token")
            else:
                print("   ❌ Set-Cookie does not contain refresh_token")
        else:
            print("   ❌ Set-Cookie header NOT found!")
            print("   This is the problem - the cookie won't be set in the browser")
        
        # Check response body
        try:
            response_data = response.json()
            print(f"   Response Body: {json.dumps(response_data, indent=2)}")
            
            # Check if accessToken is present
            if 'accessToken' in response_data:
                print("   ✅ Access token received")
            else:
                print("   ❌ Access token missing")
                
        except json.JSONDecodeError:
            print(f"   Response body is not JSON: {response.text}")
        
        # Check CORS headers
        cors_origin = response.headers.get('Access-Control-Allow-Origin')
        cors_credentials = response.headers.get('Access-Control-Allow-Credentials')
        
        print(f"   CORS Origin: {cors_origin}")
        print(f"   CORS Credentials: {cors_credentials}")
        
        if cors_credentials == 'true':
            print("   ✅ CORS credentials enabled (good for cookies)")
        else:
            print("   ❌ CORS credentials not enabled (cookies won't work)")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {str(e)}")
        print()
        print("🔧 Troubleshooting tips:")
        print("   1. Check if the login URL is correct")
        print("   2. Verify the API Gateway is accessible")
        print("   3. Check if the Lambda function is deployed")
        print("   4. Verify the test credentials are valid")

def test_cookie_parsing():
    """
    Test parsing the Set-Cookie header to extract the refresh token
    """
    print("\n🍪 Testing Cookie Parsing")
    print("=" * 60)
    
    # Example Set-Cookie header (this would come from your actual response)
    example_set_cookie = "refresh_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...; HttpOnly; Path=/; Max-Age=604800; SameSite=Strict"
    
    print(f"Example Set-Cookie header: {example_set_cookie}")
    print()
    
    # Parse the cookie
    if 'refresh_token=' in example_set_cookie:
        # Extract the token value
        token_start = example_set_cookie.find('refresh_token=') + len('refresh_token=')
        token_end = example_set_cookie.find(';', token_start)
        
        if token_end == -1:
            token_end = len(example_set_cookie)
        
        refresh_token = example_set_cookie[token_start:token_end]
        print(f"✅ Parsed refresh token: {refresh_token[:50]}...")
        print(f"   Token length: {len(refresh_token)} characters")
        
        # Check if it looks like a JWT
        if refresh_token.count('.') == 2:
            print("   ✅ Token format looks like JWT (header.payload.signature)")
        else:
            print("   ❌ Token format doesn't look like JWT")
    else:
        print("❌ Could not find refresh_token in Set-Cookie header")

def main():
    """
    Main test function
    """
    print("🚀 Login API Test Suite")
    print("This tests if the login API is properly setting cookies")
    print()
    
    print("⚠️  IMPORTANT: Update the following before running:")
    print("   1. Update login_url with your actual API Gateway URL")
    print("   2. Update test_credentials with valid test credentials")
    print()
    
    # Test the login API
    test_login_api()
    
    # Test cookie parsing
    test_cookie_parsing()
    
    print("\n" + "=" * 60)
    print("📋 Test Results:")
    print("   ✅ If Set-Cookie header is present: Login API is working")
    print("   ❌ If Set-Cookie header is missing: There's a configuration issue")
    print()
    print("🔧 Common issues:")
    print("   1. API Gateway not forwarding Set-Cookie headers")
    print("   2. CORS configuration blocking cookies")
    print("   3. Lambda function not setting headers correctly")
    print("   4. Environment variables not configured")

if __name__ == "__main__":
    main()
