#!/usr/bin/env python3
"""
Test script for the DDS wrapper with realistic bridge scenarios.
"""

from working_dds_wrapper import DDS, DDSError

def test_realistic_bridge_scenario():
    """Test with a realistic bridge scenario."""
    
    # Create a realistic bridge deal
    hands = {
        'N': ['SA', 'SK', 'SQ', 'SJ', 'HA', 'HK', 'HQ', 'DA', 'DK', 'DQ', 'CA', 'CK', 'CQ'],
        'E': ['S2', 'S3', 'S4', 'S5', 'H2', 'H3', 'H4', 'H5', 'D2', 'D3', 'D4', 'D5', 'C2'],
        'S': ['S6', 'S7', 'S8', 'S9', 'H6', 'H7', 'H8', 'H9', 'D6', 'D7', 'D8', 'D9', 'C3'],
        'W': ['ST', 'SJ', 'S2', 'S3', 'HT', 'HJ', 'H2', 'H3', 'DT', 'DJ', 'D2', 'D3', 'C4']
    }
    
    try:
        dds = DDS()
        print("✓ DDS instance created successfully")
        
        # Test DD table calculation
        dd_table = dds.calc_dd_table(hands)
        print("✓ DD table calculated successfully")
        
        # Print some results
        print("\nDouble Dummy Results:")
        for strain in ['N', 'S', 'H', 'D', 'C']:
            print(f"{strain}: N={dd_table[strain]['N']}, E={dd_table[strain]['E']}, S={dd_table[strain]['S']}, W={dd_table[strain]['W']}")
        
        # Test solving a specific board
        print("\nTesting specific board solution...")
        current_trick = []  # No cards played yet
        result = dds.solve_board(
            trump='N',  # No trump
            first='N',  # North leads
            current_trick=current_trick,
            hands=hands,
            target=-1,  # Find all solutions
            solutions=3
        )
        
        print("✓ Board solved successfully")
        print(f"Best plays: {result[:5]}")  # Show first 5 results
        
        return True
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_error_handling():
    """Test error handling with invalid inputs."""
    
    try:
        dds = DDS()
        
        # Test with invalid trump
        try:
            dds.solve_board('X', 'N', [], {'N': ['SA'], 'E': ['SK'], 'S': ['SQ'], 'W': ['SJ']})
            print("❌ Should have raised error for invalid trump")
            return False
        except ValueError:
            print("✓ Correctly caught invalid trump error")
        
        # Test with invalid first player
        try:
            dds.solve_board('N', 'X', [], {'N': ['SA'], 'E': ['SK'], 'S': ['SQ'], 'W': ['SJ']})
            print("❌ Should have raised error for invalid first player")
            return False
        except ValueError:
            print("✓ Correctly caught invalid first player error")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in error handling test: {e}")
        return False

if __name__ == "__main__":
    print("Testing DDS wrapper with realistic scenarios...\n")
    
    success1 = test_realistic_bridge_scenario()
    print()
    success2 = test_error_handling()
    
    if success1 and success2:
        print("\n🎉 All tests passed! The DDS wrapper is working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the output above.")
        import sys
        sys.exit(1)
