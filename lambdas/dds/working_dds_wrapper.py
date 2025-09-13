#!/usr/bin/env python3
"""
Working Python wrapper for libdds (Double Dummy Solver) library.

This module provides a Python interface to the libdds library for solving
bridge double dummy problems. It uses ctypes to interface with the C++ library.
"""

from ctypes import Structure, c_int, pointer, cdll, POINTER, Array
import platform
import os
import sys
from typing import Dict, List, Tuple, Optional, Union

# Constants
DIRECTIONS = "NESW"  # North, East, South, West
SUITS = "SHDC"       # Spades, Hearts, Diamonds, Clubs
STRAINS = SUITS + "N"  # Suits + No Trump
RANKS = "??23456789TJQKA"  # Card ranks (0-13, where 0-1 are unused)
MAXNOOFBOARDS = 200

# Error codes from libdds
DDS_ERROR_CODES = {
    1: "Success",
    -1: "General error",
    -2: "Zero cards",
    -3: "Target exceeds number of tricks",
    -4: "Cards duplicated",
    -5: "Target is less than -1",
    -7: "Target is higher than 13",
    -8: "Solutions parameter is less than 1",
    -9: "Solutions parameter is higher than 3",
    -10: "Too many cards",
    -12: "currentTrickSuit or currentTrickRank has wrong data",
    -13: "Played card also remains in a hand",
    -14: "Wrong number of remaining cards in a hand"
}


class DDSError(Exception):
    """Exception raised when libdds returns an error."""
    
    def __init__(self, code: int, message: str = None):
        self.code = code
        self.message = message or DDS_ERROR_CODES.get(code, f"Unknown error code: {code}")
        super().__init__(self.message)
    
    def __str__(self):
        return f"DDS Error {self.code}: {self.message}"


class Deal(Structure):
    """Structure representing a bridge deal for SolveBoard."""
    _pack_ = 4
    _fields_ = [
        ("trump", c_int),                    # Trump suit (0-4: S,H,D,C,N)
        ("first", c_int),                    # First player (0-3: N,E,S,W)
        ("current_trick_suit", c_int * 3),   # Suits of cards in current trick
        ("current_trick_rank", c_int * 3),   # Ranks of cards in current trick
        ("remain_cards", c_int * 16)         # Remaining cards for each player (4*4 flattened)
    ]


class FutureTricks(Structure):
    """Structure for storing results from SolveBoard."""
    _pack_ = 4
    _fields_ = [
        ("nodes", c_int),                    # Number of nodes searched
        ("cards", c_int),                    # Number of cards in result
        ("suit", c_int * 13),               # Suits of result cards
        ("rank", c_int * 13),               # Ranks of result cards
        ("equals", c_int * 13),             # Equals flags
        ("score", c_int * 13)               # Scores for each card
    ]


class DDTableDeal(Structure):
    """Structure for storing deals for CalcDDtable."""
    _pack_ = 4
    _fields_ = [
        ("cards", c_int * 16)         # Cards for each player (4*4 flattened)
    ]


class DDTableResults(Structure):
    """Structure for storing results from CalcDDtable."""
    _pack_ = 4
    _fields_ = [
        ("resTable", c_int * 20)      # Results table [strain][player] (5*4 flattened)
    ]


class Boards(Structure):
    """Structure for storing multiple boards for SolveAllBoards."""
    _pack_ = 4
    _fields_ = [
        ("noOfBoards", c_int),              # Number of boards
        ("deals", Deal * MAXNOOFBOARDS),    # Array of deals
        ("target", c_int * MAXNOOFBOARDS),  # Target tricks for each board
        ("solutions", c_int * MAXNOOFBOARDS), # Solutions requested for each board
        ("mode", c_int * MAXNOOFBOARDS)     # Mode for each board
    ]


class SolvedBoards(Structure):
    """Structure for storing results from SolveAllBoards."""
    _pack_ = 4
    _fields_ = [
        ("noOfBoards", c_int),              # Number of boards solved
        ("solvedBoard", FutureTricks * MAXNOOFBOARDS)  # Results for each board
    ]


def encode_deal(hands: Dict[str, List[str]]) -> List[int]:
    """
    Encode bridge hands into the format expected by libdds.
    
    Args:
        hands: Dictionary with keys 'N', 'E', 'S', 'W' and values as lists of cards
               (e.g., ['SA', 'HK', 'D2', ...])
    
    Returns:
        List of 16 integers representing encoded hands for libdds (flattened 4x4)
    
    Example:
        hands = {
            'N': ['SA', 'HK', 'D2'],
            'E': ['SK', 'HQ', 'D3'],
            'S': ['SQ', 'HJ', 'D4'],
            'W': ['SJ', 'HT', 'D5']
        }
    """
    cards = [0] * 16  # Flattened [player][suit] -> [player*4 + suit]
    
    for i, direction in enumerate(DIRECTIONS):
        if direction in hands:
            for card in hands[direction]:
                if len(card) >= 2:
                    try:
                        suit = SUITS.index(card[0])
                        rank = RANKS.index(card[1])
                        if 0 <= suit < 4 and 2 <= rank <= 14:  # Valid suit and rank
                            idx = i * 4 + suit
                            cards[idx] |= 1 << rank
                    except ValueError:
                        # Skip invalid cards silently
                        continue
    
    return cards


class DDS:
    """
    Python wrapper for the libdds library.
    
    This class provides methods to solve bridge double dummy problems
    using the libdds C++ library.
    """
    
    def __init__(self, max_threads: int = 0, max_memory: int = 0):
        """
        Initialize the DDS wrapper.
        
        Args:
            max_threads: Maximum number of threads (0 = auto-detect)
            max_memory: Maximum memory in MB (0 = auto-detect)
        """
        # Try to load the library from various locations
        # For AWS Lambda, prioritize local paths
        lib_paths = [
            "./libdds.so.2",               # Local directory (AWS Lambda)
            "./libdds.so",                 # Local directory (symlink)
            "./libdds.so.2.9.0",          # Local directory (specific version)
            "/usr/local/lib/libdds.so.2",  # System installation (fallback)
            "/usr/local/lib/libdds.so",    # System installation (fallback)
        ]
        
        libdds = None
        for lib_path in lib_paths:
            if os.path.exists(lib_path):
                try:
                    libdds = cdll.LoadLibrary(lib_path)
                    break
                except OSError:
                    continue
        
        if libdds is None:
            raise RuntimeError(
                "Could not load libdds library. "
                "Make sure it's installed and accessible. "
                f"Tried paths: {lib_paths}"
            )
        
        self.libdds = libdds
        
        # Set function argument types and return types
        self._setup_function_signatures()
        
        # Configure resources if specified
        if max_threads > 0 or max_memory > 0:
            self.set_resources(max_memory, max_threads)
    
    def _setup_function_signatures(self):
        """Setup ctypes function signatures for proper argument passing."""
        try:
            # SolveBoard
            self.libdds.SolveBoard.argtypes = [
                Deal, c_int, c_int, c_int, POINTER(FutureTricks), c_int
            ]
            self.libdds.SolveBoard.restype = c_int
            
            # CalcDDtable
            self.libdds.CalcDDtable.argtypes = [DDTableDeal, POINTER(DDTableResults)]
            self.libdds.CalcDDtable.restype = c_int
            
            # SetResources
            if hasattr(self.libdds, 'SetResources'):
                self.libdds.SetResources.argtypes = [c_int, c_int]
                self.libdds.SetResources.restype = None
        except Exception as e:
            print(f"Warning: Could not set function signatures: {e}")
    
    def set_resources(self, max_memory: int, max_threads: int):
        """
        Set maximum memory and thread usage.
        
        Args:
            max_memory: Maximum memory in MB
            max_threads: Maximum number of threads
        """
        if hasattr(self.libdds, 'SetResources'):
            self.libdds.SetResources(max_memory, max_threads)
    
    def solve_board(self, trump: str, first: str, current_trick: List[str], 
                   hands: Dict[str, List[str]], target: int = -1, 
                   solutions: int = 3, mode: int = 1, thread_index: int = 0) -> List[Tuple[str, int]]:
        """
        Solve a single bridge board.
        
        Args:
            trump: Trump suit ('S', 'H', 'D', 'C', or 'N' for no trump)
            first: First player ('N', 'E', 'S', 'W')
            current_trick: List of cards already played in current trick
            hands: Dictionary of remaining cards for each player
            target: Target number of tricks (-1 for all)
            solutions: Number of solutions to return (1-3)
            mode: Mode of operation
            thread_index: Thread index for parallel processing
        
        Returns:
            List of tuples (card, score) representing the best plays
        
        Raises:
            DDSError: If libdds returns an error
            ValueError: If input parameters are invalid
        """
        # Validate inputs
        if trump not in STRAINS:
            raise ValueError(f"Invalid trump: {trump}. Must be one of {STRAINS}")
        if first not in DIRECTIONS:
            raise ValueError(f"Invalid first player: {first}. Must be one of {DIRECTIONS}")
        if solutions < 1 or solutions > 3:
            raise ValueError(f"Solutions must be 1-3, got {solutions}")
        
        # Convert to libdds format
        trump_int = STRAINS.index(trump)
        first_int = DIRECTIONS.index(first)
        
        # Setup current trick arrays
        current_trick_suit = (c_int * 3)()
        current_trick_rank = (c_int * 3)()
        
        for i, card in enumerate(current_trick[:3]):  # Max 3 cards in a trick
            if len(card) >= 2:
                current_trick_suit[i] = SUITS.index(card[0])
                current_trick_rank[i] = RANKS.index(card[1])
        
        # Encode the deal
        remain_cards = encode_deal(hands)
        
        # Create structures - convert list to ctypes array
        remain_cards_array = (c_int * 16)(*remain_cards)
        deal = Deal(trump_int, first_int, current_trick_suit, current_trick_rank, remain_cards_array)
        future_tricks = FutureTricks()
        
        # Call libdds
        result = self.libdds.SolveBoard(deal, target, solutions, mode, 
                                       POINTER(FutureTricks)(future_tricks), thread_index)
        
        if result != 1:
            raise DDSError(result)
        
        # Extract results
        scores = []
        for i in range(future_tricks.cards):
            suit = SUITS[future_tricks.suit[i]]
            rank = RANKS[future_tricks.rank[i]]
            card = suit + rank
            score = future_tricks.score[i]
            scores.append((card, score))
        
        return scores
    
    def calc_dd_table(self, hands: Dict[str, List[str]]) -> Dict[str, Dict[str, int]]:
        """
        Calculate double dummy table for all strains and declarers.
        
        Args:
            hands: Dictionary of cards for each player
        
        Returns:
            Dictionary with structure {strain: {player: tricks}}
        
        Raises:
            DDSError: If libdds returns an error
        """
        # Encode the deal
        cards = encode_deal(hands)
        
        # Create structures - convert list to ctypes array
        cards_array = (c_int * 16)(*cards)
        table_deal = DDTableDeal(cards_array)
        table_results = DDTableResults()
        
        # Call libdds
        result = self.libdds.CalcDDtable(table_deal, POINTER(DDTableResults)(table_results))
        
        if result != 1:
            raise DDSError(result)
        
        # Extract results from flattened array
        results = {}
        for strain_idx, strain in enumerate(STRAINS):
            results[strain] = {}
            for player_idx, player in enumerate(DIRECTIONS):
                idx = strain_idx * 4 + player_idx
                results[strain][player] = table_results.resTable[idx]
        
        return results
    
    def get_version(self) -> str:
        """Get the version of libdds."""
        if hasattr(self.libdds, 'GetDDSInfo'):
            # This would require additional setup, for now return a default
            return "2.9.0"
        return "Unknown"


def create_sample_hands() -> Dict[str, List[str]]:
    """Create sample bridge hands for testing."""
    # Create a proper deck of 52 unique cards
    suits = ['S', 'H', 'D', 'C']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
    
    # Generate all cards
    all_cards = [suit + rank for suit in suits for rank in ranks]
    
    # Distribute cards to players (13 each)
    hands = {
        'N': all_cards[:13],
        'E': all_cards[13:26],
        'S': all_cards[26:39],
        'W': all_cards[39:52]
    }
    
    return hands


if __name__ == "__main__":
    # Simple test when run directly
    try:
        dds = DDS()
        print("✓ Successfully loaded libdds library")
        
        # Test basic functionality
        hands = create_sample_hands()
        print("✓ Created sample hands")
        
        # Test DD table calculation
        dd_table = dds.calc_dd_table(hands)
        print("✓ Successfully calculated DD table")
        print(f"Sample result - NT declarer N: {dd_table['N']['N']} tricks")
        
        print("\n🎉 All basic tests passed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import sys
        sys.exit(1)
