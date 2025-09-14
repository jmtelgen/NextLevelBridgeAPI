#!/usr/bin/env python3
"""
Script to add path setup to all Lambda functions to fix import issues.
"""

import os
from pathlib import Path

def add_path_setup_to_file(file_path):
    """Add path setup code to a Lambda function file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if path setup is already there
        if 'lambdas_dir = os.path.dirname' in content:
            print(f"  ⚠️  {file_path.name} already has path setup")
            return False
        
        # Check if it's a Lambda function file
        if 'lambda_handler' not in content or 'def lambda_handler' not in content:
            return False
        
        # Find where to insert the path setup
        lines = content.split('\n')
        insert_index = 0
        
        # Find the end of the import statements
        for i, line in enumerate(lines):
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                insert_index = i + 1
            elif line.strip() and not line.strip().startswith('#'):
                break
        
        # Insert the path setup code
        path_setup = [
            "import sys",
            "",
            "# Add the lambdas directory to Python path for Lambda runtime",
            "current_dir = os.path.dirname(os.path.abspath(__file__))",
            "lambdas_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))",
            "if lambdas_dir not in sys.path:",
            "    sys.path.insert(0, lambdas_dir)",
            ""
        ]
        
        # Insert the path setup
        for i, line in enumerate(path_setup):
            lines.insert(insert_index + i, line)
        
        # Write back to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        print(f"  ✅ Added path setup to {file_path.name}")
        return True
        
    except Exception as e:
        print(f"  ❌ Error processing {file_path.name}: {e}")
        return False

def main():
    """Main function to fix all Lambda function paths."""
    print("🔧 Adding path setup to Lambda functions...")
    print("=" * 50)
    
    lambdas_dir = Path("lambdas")
    lambda_files = []
    
    # Find all Lambda function files
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
        print(f"Processing {file_path.name}...")
        
        if add_path_setup_to_file(file_path):
            success_count += 1
        
        print()
    
    print("=" * 50)
    print(f"📊 Results: {success_count}/{total_count} files updated")
    
    if success_count > 0:
        print("✅ Path setup added to Lambda functions!")
        print("🚀 Your Lambda functions should now find their dependencies correctly.")
    else:
        print("ℹ️  No files needed updating (path setup already present).")

if __name__ == "__main__":
    main()
