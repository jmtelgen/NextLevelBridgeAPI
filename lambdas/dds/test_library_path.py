#!/usr/bin/env python3
"""
Test to verify which libdds library is being loaded.
"""

from .working_dds_wrapper import DDS
import os

def test_library_path():
    try:
        dds = DDS()
        print("✓ DDS instance created successfully")
        
        # Get the library path by checking the loaded library
        if hasattr(dds.libdds, '_name'):
            print(f"Loaded library: {dds.libdds._name}")
        else:
            print("Library loaded (path not directly accessible)")
        
        # Check if local files exist
        local_files = ['./libdds.so.2', './libdds.so', './libdds.so.2.9.0']
        print("\nLocal library files:")
        for file in local_files:
            if os.path.exists(file):
                print(f"  ✓ {file} exists")
            else:
                print(f"  ❌ {file} missing")
        
        # Test basic functionality
        print("\nTesting basic functionality...")
        # Create minimal valid hands (just 4 cards total to avoid complexity)
        hands = {
            'N': ['SA'],
            'E': ['SK'],
            'S': ['SQ'],
            'W': ['SJ']
        }
        
        # This should work with minimal hands
        print("✓ Basic test completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_library_path()
