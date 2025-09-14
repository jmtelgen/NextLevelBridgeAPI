#!/usr/bin/env python3
"""
Comprehensive import test script for BridgeLambdas project.
This script tests all Lambda functions to ensure they can import their dependencies correctly.
"""

import sys
import os
import importlib.util
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_import(module_path, module_name):
    """Test if a module can be imported successfully."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None:
            return False, f"Could not load spec for {module_path}"
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # Test if lambda_handler function exists and is callable
        if hasattr(module, 'lambda_handler'):
            if callable(module.lambda_handler):
                return True, "SUCCESS: Module imported and lambda_handler is callable"
            else:
                return False, "ERROR: lambda_handler exists but is not callable"
        else:
            return False, "ERROR: lambda_handler function not found"
            
    except Exception as e:
        return False, f"ERROR: {str(e)}"

def find_lambda_files():
    """Find all Python files that contain lambda_handler function."""
    lambda_files = []
    lambdas_dir = project_root / "lambdas"
    
    for py_file in lambdas_dir.rglob("*.py"):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'lambda_handler' in content and 'def lambda_handler' in content:
                    lambda_files.append(py_file)
        except Exception as e:
            print(f"Warning: Could not read {py_file}: {e}")
    
    return lambda_files

def main():
    """Main test function."""
    print("🔍 BridgeLambdas Import Test")
    print("=" * 50)
    
    # Find all Lambda function files
    lambda_files = find_lambda_files()
    
    if not lambda_files:
        print("❌ No Lambda function files found!")
        return False
    
    print(f"Found {len(lambda_files)} Lambda function files:")
    for file_path in lambda_files:
        print(f"  - {file_path.relative_to(project_root)}")
    print()
    
    # Test each Lambda function
    success_count = 0
    total_count = len(lambda_files)
    
    for file_path in lambda_files:
        module_name = file_path.stem
        relative_path = file_path.relative_to(project_root)
        
        print(f"Testing {relative_path}...")
        success, message = test_import(file_path, module_name)
        
        if success:
            print(f"  ✅ {message}")
            success_count += 1
        else:
            print(f"  ❌ {message}")
        
        print()
    
    # Summary
    print("=" * 50)
    print(f"📊 Test Results: {success_count}/{total_count} Lambda functions passed")
    
    if success_count == total_count:
        print("🎉 All Lambda functions can import their dependencies correctly!")
        return True
    else:
        print(f"⚠️  {total_count - success_count} Lambda functions have import issues.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
