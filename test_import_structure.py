#!/usr/bin/env python3
"""
Import structure test for BridgeLambdas project.
This script checks if all import statements are syntactically correct and use proper paths.
"""

import ast
import re
from pathlib import Path

def extract_imports(file_path):
    """Extract all import statements from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(('import', alias.name, None))
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                for alias in node.names:
                    imports.append(('from', module, alias.name))
        
        return imports
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return []

def check_import_path(import_type, module, name):
    """Check if an import path is correct based on our project structure."""
    issues = []
    
    # Skip standard library and third-party imports
    if not module or module.startswith(('typing', 'json', 'os', 'sys', 'time', 'random', 'uuid', 'logging', 'datetime', 're', 'dataclasses', 'abc', 'functools', 'decimal', 'base64', 'secrets', 'string', 'urllib', 'platform', 'ctypes', 'collections', 'itertools', 'math', 'statistics', 'hashlib', 'hmac', 'boto3', 'botocore', 'jwt', 'bcrypt', 'requests', 'bs4')):
        return issues
    
    # Check internal imports
    if module:
        if module.startswith('shared.'):
            # Check if the path is correct
            if module == 'shared.db_utils':
                issues.append(f"❌ INCORRECT: '{module}' should be 'shared.database.db_utils'")
            elif module == 'shared.websocket_utils':
                issues.append(f"❌ INCORRECT: '{module}' should be 'shared.utils.websocket_utils'")
            elif module == 'shared.robot_utils':
                issues.append(f"❌ INCORRECT: '{module}' should be 'core.robot.robot_utils'")
            elif module == 'shared.seat_filtering':
                issues.append(f"❌ INCORRECT: '{module}' should be 'shared.utils.seat_filtering'")
            elif module == 'shared.auth_middleware':
                issues.append(f"❌ INCORRECT: '{module}' should be 'shared.security.auth_middleware'")
            elif module == 'shared.base_handler':
                issues.append(f"❌ INCORRECT: '{module}' should be 'shared.utils.base_handler'")
        
        elif module.startswith('lambdas.'):
            issues.append(f"❌ INCORRECT: '{module}' should not start with 'lambdas.'")
        
        elif module.startswith('core.'):
            # These are correct
            pass
        
        elif module.startswith('models.'):
            # These are correct
            pass
        
        elif module.startswith('dds.'):
            # These are correct
            pass
        
        else:
            # Check for direct imports that should be relative
            if module in ['sayc_bidding', 'hand_evaluator', 'working_dds_wrapper']:
                issues.append(f"❌ INCORRECT: '{module}' should use proper module path")
    
    return issues

def test_file_imports(file_path):
    """Test imports for a single file."""
    imports = extract_imports(file_path)
    issues = []
    
    for import_type, module, name in imports:
        file_issues = check_import_path(import_type, module, name)
        issues.extend(file_issues)
    
    return issues

def find_all_python_files():
    """Find all Python files in the lambdas directory."""
    lambdas_dir = Path("lambdas")
    python_files = []
    
    for py_file in lambdas_dir.rglob("*.py"):
        # Skip __pycache__ directories
        if "__pycache__" not in str(py_file):
            python_files.append(py_file)
    
    return python_files

def main():
    """Main test function."""
    print("🔍 BridgeLambdas Import Structure Test")
    print("=" * 60)
    
    python_files = find_all_python_files()
    
    total_issues = 0
    files_with_issues = 0
    
    for file_path in python_files:
        issues = test_file_imports(file_path)
        
        if issues:
            print(f"\n📁 {file_path}")
            for issue in issues:
                print(f"  {issue}")
            total_issues += len(issues)
            files_with_issues += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results:")
    print(f"  Files checked: {len(python_files)}")
    print(f"  Files with issues: {files_with_issues}")
    print(f"  Total issues found: {total_issues}")
    
    if total_issues == 0:
        print("🎉 All import statements are correctly structured!")
        return True
    else:
        print(f"⚠️  Found {total_issues} import issues that need to be fixed.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
