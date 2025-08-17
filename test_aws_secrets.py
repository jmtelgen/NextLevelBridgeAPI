#!/usr/bin/env python3
"""
Test script to demonstrate AWS Secrets Manager integration for JWT secrets

This script shows how to:
1. Retrieve the JWT secret from AWS Secrets Manager
2. Use it with JWT utilities
3. Handle different secret formats and error cases

Prerequisites:
- AWS credentials configured (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- AWS region set (AWS_DEFAULT_REGION)
- Secret "Bridge/JWT" exists in AWS Secrets Manager
"""

import os
import sys
import json
from datetime import datetime

# Add the lambdas directory to the Python path
sys.path.append('lambdas')

try:
    from utils.aws_secrets import SecretsManager, get_jwt_secret
    from utils.jwt_utils import JWTUtils
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def test_secrets_manager():
    """Test the SecretsManager class"""
    print("🔐 Testing SecretsManager class...")
    
    try:
        # Initialize with default region
        secrets_manager = SecretsManager()
        print("✅ SecretsManager initialized successfully")
        
        # Test getting the JWT secret
        jwt_secret = secrets_manager.get_jwt_secret("Bridge/JWT")
        print(f"✅ JWT secret retrieved successfully (length: {len(jwt_secret)})")
        print(f"   Secret preview: {jwt_secret[:20]}...")
        
        return jwt_secret
        
    except Exception as e:
        print(f"❌ SecretsManager test failed: {e}")
        return None


def test_convenience_function():
    """Test the convenience function"""
    print("\n🚀 Testing convenience function...")
    
    try:
        jwt_secret = get_jwt_secret("Bridge/JWT")
        print(f"✅ Convenience function worked (length: {len(jwt_secret)})")
        return jwt_secret
        
    except Exception as e:
        print(f"❌ Convenience function test failed: {e}")
        return None


def test_jwt_utils():
    """Test JWT utilities with the retrieved secret"""
    print("\n🎫 Testing JWT utilities...")
    
    try:
        # Initialize JWT utilities (will automatically fetch secret from AWS)
        jwt_utils = JWTUtils()
        print("✅ JWTUtils initialized successfully")
        
        # Test token generation
        user_data = {
            'user_id': 'test_user_123',
            'username': 'test@example.com',
            'email': 'test@example.com'
        }
        
        access_token = jwt_utils.generate_access_token(user_data, expires_in_hours=1)
        refresh_token = jwt_utils.generate_refresh_token(user_data, expires_in_days=7)
        
        print(f"✅ Access token generated (length: {len(access_token)})")
        print(f"✅ Refresh token generated (length: {len(refresh_token)})")
        
        # Test token verification
        payload = jwt_utils.verify_token(access_token)
        print(f"✅ Access token verified successfully")
        print(f"   User ID: {payload.get('user_id')}")
        print(f"   Username: {payload.get('username')}")
        print(f"   Token type: {payload.get('type')}")
        
        # Test token refresh
        new_access_token = jwt_utils.refresh_access_token(refresh_token, expires_in_hours=2)
        print(f"✅ Access token refreshed successfully (length: {len(new_access_token)})")
        
        return True
        
    except Exception as e:
        print(f"❌ JWT utilities test failed: {e}")
        return False


def test_error_handling():
    """Test error handling for invalid secrets"""
    print("\n⚠️  Testing error handling...")
    
    try:
        # Try to get a non-existent secret
        jwt_utils = JWTUtils("NonExistent/Secret")
        jwt_utils.secret_key  # This should trigger an error
        print("❌ Expected error not raised")
        return False
        
    except Exception as e:
        print(f"✅ Error handling worked correctly: {e}")
        return True


def main():
    """Main test function"""
    print("🔑 AWS Secrets Manager JWT Integration Test")
    print("=" * 50)
    
    # Check AWS credentials
    if not (os.environ.get('AWS_ACCESS_KEY_ID') or os.environ.get('AWS_PROFILE')):
        print("⚠️  AWS credentials not found. Please configure:")
        print("   - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or")
        print("   - AWS_PROFILE, or")
        print("   - AWS credentials file (~/.aws/credentials)")
        print("\nYou can also run: aws configure")
        return
    
    # Check AWS region
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    print(f"🌍 Using AWS region: {region}")
    
    # Run tests
    tests_passed = 0
    total_tests = 4
    
    # Test 1: SecretsManager class
    if test_secrets_manager():
        tests_passed += 1
    
    # Test 2: Convenience function
    if test_convenience_function():
        tests_passed += 1
    
    # Test 3: JWT utilities
    if test_jwt_utils():
        tests_passed += 1
    
    # Test 4: Error handling
    if test_error_handling():
        tests_passed += 1
    
    # Summary
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! AWS Secrets Manager integration is working correctly.")
        print("\nNext steps:")
        print("1. Deploy your Lambda functions")
        print("2. Ensure the 'Bridge/JWT' secret exists in AWS Secrets Manager")
        print("3. Configure appropriate IAM permissions for your Lambda execution role")
    else:
        print("❌ Some tests failed. Please check the error messages above.")
        print("\nCommon issues:")
        print("1. AWS credentials not configured correctly")
        print("2. Secret 'Bridge/JWT' doesn't exist in AWS Secrets Manager")
        print("3. Insufficient IAM permissions to access Secrets Manager")
        print("4. Network connectivity issues")


if __name__ == "__main__":
    main()
