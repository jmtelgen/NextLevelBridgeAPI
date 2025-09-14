#!/usr/bin/env python3
"""
Deployment test script for BridgeLambdas.
This script simulates the Lambda runtime environment to test imports.
"""

import sys
import os
from pathlib import Path

def setup_lambda_environment():
    """Set up the Lambda runtime environment."""
    # Add lambdas directory to Python path (like Lambda does)
    lambdas_dir = Path(__file__).parent / "lambdas"
    sys.path.insert(0, str(lambdas_dir))
    
    # Set up environment variables that Lambda would have
    os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
    os.environ.setdefault('USER_TABLE', 'test-user-table')
    os.environ.setdefault('ROOM_TABLE', 'test-room-table')
    os.environ.setdefault('CONNECTION_TABLE', 'test-connection-table')

def test_specific_lambda(lambda_file_path):
    """Test a specific Lambda function."""
    try:
        # Import the module
        module_name = lambda_file_path.stem
        
        # Load the module
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_name, lambda_file_path)
        if spec is None:
            return False, f"Could not load spec for {lambda_file_path}"
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # Check if lambda_handler exists
        if not hasattr(module, 'lambda_handler'):
            return False, "lambda_handler function not found"
        
        if not callable(module.lambda_handler):
            return False, "lambda_handler is not callable"
        
        return True, "SUCCESS: Module imported successfully"
        
    except ImportError as e:
        return False, f"IMPORT ERROR: {str(e)}"
    except Exception as e:
        return False, f"ERROR: {str(e)}"

def test_all_lambda_functions():
    """Test all Lambda functions."""
    print("🚀 BridgeLambdas Deployment Test")
    print("=" * 60)
    
    setup_lambda_environment()
    
    # Find all Lambda function files
    lambdas_dir = Path("lambdas")
    lambda_files = []
    
    for py_file in lambdas_dir.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'lambda_handler' in content and 'def lambda_handler' in content:
                        lambda_files.append(py_file)
            except:
                pass
    
    print(f"Found {len(lambda_files)} Lambda function files")
    print()
    
    success_count = 0
    total_count = len(lambda_files)
    
    for file_path in lambda_files:
        relative_path = file_path.relative_to(Path.cwd())
        print(f"Testing {relative_path}...")
        
        success, message = test_specific_lambda(file_path)
        
        if success:
            print(f"  ✅ {message}")
            success_count += 1
        else:
            print(f"  ❌ {message}")
        
        print()
    
    # Summary
    print("=" * 60)
    print(f"📊 Test Results: {success_count}/{total_count} Lambda functions passed")
    
    if success_count == total_count:
        print("🎉 All Lambda functions are ready for deployment!")
        print("✅ No import errors detected.")
        return True
    else:
        print(f"⚠️  {total_count - success_count} Lambda functions have issues.")
        print("❌ Please fix the issues before deploying.")
        return False

def test_websocket_start_room_specifically():
    """Test the websocket_start_room function specifically."""
    print("🎯 Testing websocket_start_room specifically...")
    print("=" * 60)
    
    setup_lambda_environment()
    
    start_room_file = Path("lambdas/api/websocket/websocket_start_room.py")
    
    if not start_room_file.exists():
        print("❌ websocket_start_room.py not found!")
        return False
    
    success, message = test_specific_lambda(start_room_file)
    
    if success:
        print(f"✅ {message}")
        print("🎉 websocket_start_room is ready for deployment!")
        return True
    else:
        print(f"❌ {message}")
        print("🔧 Please check the import statements in websocket_start_room.py")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test BridgeLambdas deployment")
    parser.add_argument("--start-room-only", action="store_true", 
                       help="Test only the websocket_start_room function")
    
    args = parser.parse_args()
    
    if args.start_room_only:
        success = test_websocket_start_room_specifically()
    else:
        success = test_all_lambda_functions()
    
    sys.exit(0 if success else 1)
