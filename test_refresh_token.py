#!/usr/bin/env python3
"""
Test script to verify the refresh token API works without authentication headers.
This simulates how a frontend would call the refresh endpoint.
"""

import requests
import json

def test_refresh_token_without_auth():
    """
    Test that the refresh token API can be called without Authorization header
    """
    print("🧪 Testing Refresh Token API without Authentication Header")
    print("=" * 60)
    
    # Test 1: Call without any headers (should fail with missing token message)
    print("\n1️⃣ Testing with no cookies or body:")
    try:
        response = requests.post(
            'https://your-api-gateway-url/api/auth/refresh-token',
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 400:
            print("   ✅ Expected: API correctly rejected request without refresh token")
        else:
            print("   ❌ Unexpected: API should return 400 for missing token")
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    # Test 2: Call with refresh token in body (fallback method)
    print("\n2️⃣ Testing with refresh token in request body:")
    try:
        # This would be a valid refresh token from a previous login
        test_refresh_token = "your_test_refresh_token_here"
        
        response = requests.post(
            'https://your-api-gateway-url/api/auth/refresh-token',
            headers={'Content-Type': 'application/json'},
            json={'refresh_token': test_refresh_token},
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("   ✅ Success: API returned new access token")
        elif response.status_code == 401:
            print("   ⚠️  Expected: API rejected invalid refresh token")
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    # Test 3: Call with refresh token in cookies (primary method)
    print("\n3️⃣ Testing with refresh token in cookies:")
    try:
        # This would be a valid refresh token from a previous login
        test_refresh_token = "your_test_refresh_token_here"
        
        cookies = {'refresh_token': test_refresh_token}
        
        response = requests.post(
            'https://your-api-gateway-url/api/auth/refresh-token',
            headers={'Content-Type': 'application/json'},
            cookies=cookies,
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("   ✅ Success: API returned new access token from cookie")
        elif response.status_code == 401:
            print("   ⚠️  Expected: API rejected invalid refresh token")
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")

def test_refresh_token_with_auth_header():
    """
    Test that the refresh token API can be called WITH Authorization header
    (This should work but is not required)
    """
    print("\n🔐 Testing Refresh Token API WITH Authorization Header (optional):")
    print("=" * 60)
    
    try:
        # This would be a valid access token
        test_access_token = "your_test_access_token_here"
        
        response = requests.post(
            'https://your-api-gateway-url/api/auth/refresh-token',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {test_access_token}'
            },
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 400:
            print("   ✅ Expected: API still requires refresh token (ignores access token)")
        elif response.status_code == 200:
            print("   ✅ Success: API worked with both tokens")
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")

def main():
    """
    Main test function
    """
    print("🚀 Refresh Token API Test Suite")
    print("This tests that the refresh token API works WITHOUT requiring authentication")
    print()
    
    # Update this URL to match your actual API Gateway endpoint
    print("⚠️  IMPORTANT: Update the API URL in this script before running!")
    print("   Current URL: https://your-api-gateway-url/api/auth/refresh-token")
    print()
    
    # Test without auth (this should work)
    test_refresh_token_without_auth()
    
    # Test with auth (this should also work but is not required)
    test_refresh_token_with_auth_header()
    
    print("\n" + "=" * 60)
    print("📋 Test Summary:")
    print("   ✅ The refresh token API should work WITHOUT Authorization header")
    print("   ✅ It should accept refresh tokens from cookies (primary method)")
    print("   ✅ It should accept refresh tokens from request body (fallback)")
    print("   ✅ It should NOT require a valid access token to function")
    print()
    print("🔧 To use this script:")
    print("   1. Update the API URL above")
    print("   2. Get a valid refresh token from logging in")
    print("   3. Replace 'your_test_refresh_token_here' with the actual token")
    print("   4. Run: python test_refresh_token.py")

if __name__ == "__main__":
    main()
