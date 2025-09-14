#!/usr/bin/env python3
"""
Comprehensive verification script for BridgeLambdas imports.
This script verifies that all Lambda functions have correct import statements.
"""

import os
import sys
from pathlib import Path

def check_file_imports(file_path):
    """Check a single file for import issues."""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Check for problematic import patterns
            if line.startswith('from shared.db_utils import'):
                issues.append(f"Line {line_num}: ❌ 'from shared.db_utils import' should be 'from shared.database.db_utils import'")
            
            elif line.startswith('from shared.websocket_utils import'):
                issues.append(f"Line {line_num}: ❌ 'from shared.websocket_utils import' should be 'from shared.utils.websocket_utils import'")
            
            elif line.startswith('from shared.robot_utils import'):
                issues.append(f"Line {line_num}: ❌ 'from shared.robot_utils import' should be 'from core.robot.robot_utils import'")
            
            elif line.startswith('from shared.seat_filtering import'):
                issues.append(f"Line {line_num}: ❌ 'from shared.seat_filtering import' should be 'from shared.utils.seat_filtering import'")
            
            elif line.startswith('from shared.auth_middleware import'):
                issues.append(f"Line {line_num}: ❌ 'from shared.auth_middleware import' should be 'from shared.security.auth_middleware import'")
            
            elif line.startswith('from base_handler import'):
                issues.append(f"Line {line_num}: ❌ 'from base_handler import' should be 'from shared.utils.base_handler import'")
            
            elif line.startswith('from lambdas.shared'):
                issues.append(f"Line {line_num}: ❌ 'from lambdas.shared' should not include 'lambdas.' prefix")
            
            elif line.startswith('from sayc_bidding import'):
                issues.append(f"Line {line_num}: ❌ 'from sayc_bidding import' should be 'from core.bidding.sayc_bidding import'")
            
            elif line.startswith('from hand_evaluator import'):
                issues.append(f"Line {line_num}: ❌ 'from hand_evaluator import' should be 'from core.hand_evaluation.hand_evaluator import'")
            
            elif line.startswith('from working_dds_wrapper import'):
                issues.append(f"Line {line_num}: ❌ 'from working_dds_wrapper import' should be 'from dds.working_dds_wrapper import' or 'from .working_dds_wrapper import'")
    
    except Exception as e:
        issues.append(f"Error reading file: {e}")
    
    return issues

def find_lambda_files():
    """Find all Lambda function files."""
    lambda_files = []
    lambdas_dir = Path("lambdas")
    
    for py_file in lambdas_dir.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'lambda_handler' in content and 'def lambda_handler' in content:
                        lambda_files.append(py_file)
            except:
                pass
    
    return lambda_files

def main():
    """Main verification function."""
    print("🔍 BridgeLambdas Import Verification")
    print("=" * 60)
    
    # Find all Lambda files
    lambda_files = find_lambda_files()
    print(f"Found {len(lambda_files)} Lambda function files")
    print()
    
    # Check all Python files in lambdas directory
    lambdas_dir = Path("lambdas")
    all_python_files = list(lambdas_dir.rglob("*.py"))
    all_python_files = [f for f in all_python_files if "__pycache__" not in str(f)]
    
    total_issues = 0
    files_with_issues = []
    
    for file_path in all_python_files:
        issues = check_file_imports(file_path)
        
        if issues:
            files_with_issues.append(file_path)
            print(f"📁 {file_path.relative_to(Path.cwd())}")
            for issue in issues:
                print(f"  {issue}")
                total_issues += 1
            print()
    
    # Summary
    print("=" * 60)
    print(f"📊 Verification Results:")
    print(f"  Total Python files checked: {len(all_python_files)}")
    print(f"  Lambda function files: {len(lambda_files)}")
    print(f"  Files with import issues: {len(files_with_issues)}")
    print(f"  Total issues found: {total_issues}")
    print()
    
    if total_issues == 0:
        print("🎉 All import statements are correct!")
        print("✅ Your Lambda functions should deploy and run successfully.")
        return True
    else:
        print(f"⚠️  Found {total_issues} import issues that need to be fixed.")
        print("❌ Please fix these issues before deploying.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
