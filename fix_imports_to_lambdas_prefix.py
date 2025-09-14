#!/usr/bin/env python3
"""
Script to update all imports to use lambdas. prefix.
This reverts the imports back to what was working before.
"""

import os
from pathlib import Path

def update_imports_in_file(file_path):
    """Update imports in a single file to use lambdas. prefix."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Define the import mappings
        import_mappings = {
            'from shared.database.db_utils import': 'from lambdas.shared.database.db_utils import',
            'from shared.utils.base_handler import': 'from lambdas.shared.utils.base_handler import',
            'from shared.utils.websocket_utils import': 'from lambdas.shared.utils.websocket_utils import',
            'from shared.utils.seat_filtering import': 'from lambdas.shared.utils.seat_filtering import',
            'from shared.security.auth_middleware import': 'from lambdas.shared.security.auth_middleware import',
            'from shared.security.jwt_utils import': 'from lambdas.shared.security.jwt_utils import',
            'from shared.security.password_utils import': 'from lambdas.shared.security.password_utils import',
            'from core.robot.robot_utils import': 'from lambdas.core.robot.robot_utils import',
            'from core.bidding.sayc_bidding import': 'from lambdas.core.bidding.sayc_bidding import',
            'from core.bidding.advanced_bidding_engine import': 'from lambdas.core.bidding.advanced_bidding_engine import',
            'from core.bidding.bidding_system import': 'from lambdas.core.bidding.bidding_system import',
            'from core.bidding.fantoni_nunes_bidding import': 'from lambdas.core.bidding.fantoni_nunes_bidding import',
            'from core.hand_evaluation.hand_evaluator import': 'from lambdas.core.hand_evaluation.hand_evaluator import',
            'from models.game_state import': 'from lambdas.models.game_state import',
            'from models.crawler_models import': 'from lambdas.models.crawler_models import',
            'from models.user import': 'from lambdas.models.user import',
            'from dds.working_dds_wrapper import': 'from lambdas.dds.working_dds_wrapper import',
        }
        
        # Apply the mappings
        for old_import, new_import in import_mappings.items():
            content = content.replace(old_import, new_import)
        
        # Check if any changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  ✅ Updated imports in {file_path.name}")
            return True
        else:
            print(f"  ℹ️  No changes needed in {file_path.name}")
            return False
        
    except Exception as e:
        print(f"  ❌ Error processing {file_path.name}: {e}")
        return False

def main():
    """Main function to update all imports."""
    print("🔧 Updating all imports to use lambdas. prefix...")
    print("=" * 60)
    
    lambdas_dir = Path("lambdas")
    python_files = []
    
    # Find all Python files in lambdas directory
    for py_file in lambdas_dir.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            python_files.append(py_file)
    
    print(f"Found {len(python_files)} Python files to check")
    print()
    
    updated_count = 0
    total_count = len(python_files)
    
    for file_path in python_files:
        print(f"Processing {file_path.name}...")
        
        if update_imports_in_file(file_path):
            updated_count += 1
        
        print()
    
    print("=" * 60)
    print(f"📊 Results: {updated_count}/{total_count} files updated")
    
    if updated_count > 0:
        print("✅ All imports updated to use lambdas. prefix!")
        print("🚀 Your Lambda functions should now work as they did before.")
    else:
        print("ℹ️  No files needed updating (imports already correct).")

if __name__ == "__main__":
    main()
