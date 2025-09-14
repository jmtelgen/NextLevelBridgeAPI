# Robot Bridge Bidding System

This directory contains an intelligent robot bridge bidding system that implements the SAYC (Standard American Yellow Card) bidding system as the primary method, with fallback to the Fantoni-Nunes bidding system. The system is designed to provide realistic and competitive bidding for robot players in bridge games.

## Architecture

The system is organized into several utility classes:

### 1. HandEvaluator (`utils/hand_evaluator.py`)
- **Purpose**: Analyzes bridge hands for bidding purposes
- **Key Features**:
  - High Card Points (HCP) calculation
  - Distribution points calculation
  - Suit length analysis
  - Balanced hand detection
  - Stopper analysis
  - Control counting

### 2. SAYCBidding (`utils/sayc_bidding.py`)
- **Purpose**: Implements the SAYC (Standard American Yellow Card) bidding system
- **Key Features**:
  - Complete SAYC opening bid logic (1C, 1D, 1H, 1S, 1NT, 2-level, 3-level)
  - SAYC response bidding with Jacoby transfers, Stayman, etc.
  - Position-aware bidding with seat tracking
  - Vulnerability considerations
  - Competitive bidding and overcalls

### 3. BiddingSystem (`utils/bidding_system.py`)
- **Purpose**: Implements the Fantoni-Nunes bidding system (fallback)
- **Key Features**:
  - Opening bid logic (1C, 1D, 1H, 1S, 1NT, 2-level, 3-level)
  - Response bidding
  - Position-aware bidding
  - Vulnerability considerations

### 4. RobotBidder (`utils/robot_bidder.py`)
- **Purpose**: Main robot bidding logic that coordinates hand evaluation and bidding systems
- **Key Features**:
  - Primary SAYC bidding system integration
  - Fallback to Fantoni-Nunes system
  - Intelligent bid selection
  - Bidding context analysis
  - Competitive bidding
  - Doubling/redoubling decisions

### 5. RobotBridgeBidding Lambda (`robot_bridge_bidding.py`)
- **Purpose**: AWS Lambda function for robot bidding
- **Key Features**:
  - WebSocket integration
  - Real-time bidding
  - Game state management
  - Broadcasting updates

## SAYC System Overview

The system now primarily implements the SAYC (Standard American Yellow Card) bidding system with the following key principles:

### Opening Bids
- **1C**: 12+ HCP, longest suit is clubs, or 3-3 in minors
- **1D**: 12+ HCP, longest suit is diamonds, or 4-4 in minors  
- **1H**: 12+ HCP, 5+ hearts
- **1S**: 12+ HCP, 5+ spades
- **1NT**: 15-17 HCP, balanced (4333, 4432, or 5332 with 5-card minor)
- **2C**: 22+ HCP or 9+ tricks (strong artificial opening)
- **2D/2H/2S**: 5-11 HCP, 6-card suit (weak two)
- **2NT**: 20-21 HCP, balanced
- **3NT**: 25-27 HCP, balanced
- **3-level**: Preempts with 7+ cards

### Response Bidding
- **Jacoby Transfers**: 2D→H, 2H→S after 1NT
- **Stayman**: 2C asking for major suits after 1NT
- **Jacoby 2NT**: 13+ points, 3+ cards in opener's suit
- **Limit Raises**: 3-level raises showing 10-12 points
- **New Suit Responses**: 6+ points, 4+ cards

## Fantoni-Nunes System Overview (Fallback)

The system also includes the Fantoni-Nunes bidding system as a fallback:

### Opening Bids
- **1C**: 15+ balanced (4333/4432/5m332) or 14+ with 5+C or 444-1red
- **1D**: 14+ with 5+D or 444-1black
- **1H**: 14+ with 5+H (12+ if 4S)
- **1S**: 14+ with 5+S (12+ if 4H)
- **1NT**: 12-14 balanced (11+ NV)
- **2C**: 10-13 with 5C-4other or 6+C
- **2D**: 10-13 with 5D-4M/4+m or 6+D
- **2H/2S**: 10-13 with 5M-4+m or 6+M
- **2NT**: 21-22 balanced
- **3-level**: Preempts with 7+ cards

### Response Bidding
- **1C Responses**:
  - 1D: 4+H, 0-9
  - 1H: 4+S, 0-9
  - 1S: 4+H, 14-20/GF
  - 1NT: 15-18, denies 4H
  - 2C: 14-17, 6+C or 4D-5C

- **1D Responses**:
  - 1H: 4+H, 0-9
  - 1S: 4+S, 0-9
  - 1NT: 18+ unbalanced

- **1H/1S Responses**:
  - 1NT: 0-9 no 4M
  - 2C: 10+ balanced or suit raise

## Usage

### Basic Robot Bidding
```python
from utils.robot_bidder import RobotBidder

robot_bidder = RobotBidder()
bid = robot_bidder.make_bid(room_data, robot_seat)  # robot_seat: 'N', 'E', 'S', or 'W'
```

### Hand Analysis
```python
from utils.hand_evaluator import HandEvaluator

evaluator = HandEvaluator()
analysis = evaluator.evaluate_hand(hand)
print(f"HCP: {analysis.hcp}, Total: {analysis.total_points}")
```

### Custom Bidding Context
```python
from utils.bidding_system import BiddingSystem, BiddingContext

context = BiddingContext(
    seat='N',  # Use N/S/E/W instead of full names
    vulnerability='None',
    position=1,
    previous_bids=[],
    partner_bids=[],
    opponents_bids=[]
)

bidding_system = BiddingSystem()
bid = bidding_system.get_opening_bid(hand, context)
```

## Testing

Run the test script to see the system in action:

```bash
cd lambdas
python test_robot_bidding.py
```

This will demonstrate:
- Hand evaluation capabilities
- Opening bid decisions
- Response bidding
- Complete robot bidding scenarios

## Integration

The system integrates with the existing bridge game infrastructure:

1. **WebSocket Integration**: Real-time bidding updates
2. **Database Integration**: Game state persistence
3. **Robot Utils**: Seamless integration with existing robot system
4. **Error Handling**: Graceful fallbacks to simple bidding

## Configuration

The system can be configured through the `BiddingContext` class:

- **Vulnerability**: Affects bidding aggressiveness
- **Position**: 1st, 2nd, 3rd, 4th seat considerations
- **Previous Bids**: Context for competitive bidding
- **Partner Bids**: Information for response bidding

## Future Enhancements

Potential improvements to the system:

1. **Advanced Conventions**: More sophisticated bidding agreements
2. **Slam Bidding**: Key card asking and slam investigation
3. **Competitive Bidding**: Advanced competitive strategies
4. **Partnership Bidding**: More sophisticated partnership agreements
5. **Learning System**: Adaptive bidding based on results

## Error Handling

The system includes comprehensive error handling:

- **Fallback Bidding**: Falls back to 'pass' if intelligent bidding fails
- **Input Validation**: Validates hand formats and bidding contexts
- **Exception Handling**: Catches and logs errors gracefully
- **Debugging Support**: Detailed logging for troubleshooting

## Performance

The system is optimized for:

- **Fast Bidding**: Quick decision making for real-time games
- **Memory Efficiency**: Minimal memory footprint
- **Scalability**: Handles multiple concurrent games
- **Reliability**: Robust error handling and fallbacks
