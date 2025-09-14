# BridgeLambdas Project Structure

This document describes the reorganized project structure for better maintainability and clarity.

## Directory Overview

```
lambdas/
├── api/                          # API handlers organized by functionality
│   ├── auth/                     # Authentication APIs
│   │   ├── account_create.py
│   │   ├── account_login.py
│   │   └── account_refresh_token.py
│   ├── game/                     # Game management APIs
│   │   ├── connection_count.py
│   │   └── example_protected_api.py
│   ├── websocket/                # WebSocket APIs
│   │   ├── websocket_connect.py
│   │   ├── websocket_create_room.py
│   │   ├── websocket_join_room.py
│   │   ├── websocket_start_room.py
│   │   ├── websocket_make_bid.py
│   │   ├── websocket_play_card.py
│   │   ├── websocket_change_seat.py
│   │   └── websocket_disconnect.py
│   └── ai/                       # AI and automation APIs
│       ├── robot_bridge_bidding.py
│       ├── ai_double_dummy.py
│       ├── web-crawler.py
│       └── crawler-trigger.py
├── core/                         # Core business logic
│   ├── bidding/                  # Bidding system implementations
│   │   ├── sayc_bidding.py       # SAYC (Standard American Yellow Card)
│   │   ├── advanced_bidding_engine.py
│   │   ├── bidding_system.py     # Fantoni-Nunes system
│   │   ├── bidding_parser.py
│   │   └── fantoni_nunes_bidding.py
│   ├── hand_evaluation/          # Hand analysis and evaluation
│   │   └── hand_evaluator.py
│   └── robot/                    # Robot player logic
│       ├── robot_bidder.py
│       └── robot_utils.py
├── shared/                       # Shared utilities and services
│   ├── database/                 # Database utilities
│   │   └── db_utils.py
│   ├── security/                 # Security and authentication
│   │   ├── auth_utils.py
│   │   ├── auth_middleware.py
│   │   ├── jwt_utils.py
│   │   ├── password_utils.py
│   │   └── aws_secrets.py
│   └── utils/                    # General utilities
│       ├── base_handler.py
│       ├── websocket_utils.py
│       ├── seat_filtering.py
│       └── crawler_utils.py
├── tests/                        # Test suites
│   ├── unit/                     # Unit tests
│   │   ├── test_*.py
│   │   └── test_sayc_*.py
│   └── integration/              # Integration tests
└── dds/                          # Double Dummy Solver (unchanged)
```

## Key Improvements

### 1. **API Organization**
- **`api/auth/`**: All authentication-related endpoints
- **`api/game/`**: Game management and state APIs
- **`api/websocket/`**: Real-time WebSocket handlers
- **`api/ai/`**: AI and automation features

### 2. **Core Business Logic**
- **`core/bidding/`**: All bidding system implementations
  - SAYC (primary system)
  - Fantoni-Nunes (fallback)
  - Advanced bidding engine
- **`core/hand_evaluation/`**: Hand analysis and evaluation
- **`core/robot/`**: Robot player intelligence

### 3. **Shared Services**
- **`shared/database/`**: Database utilities and connections
- **`shared/security/`**: Authentication, JWT, password handling
- **`shared/utils/`**: Common utilities used across modules

### 4. **Testing Structure**
- **`tests/unit/`**: Unit tests for individual components
- **`tests/integration/`**: Integration tests for API endpoints

## Import Patterns

### For API Handlers
```python
import sys
import os

# Add the lambdas directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from shared.database.db_utils import db_utils
from shared.security.password_utils import PasswordUtils
from core.robot.robot_bidder import RobotBidder
```

### For Core Modules
```python
from core.hand_evaluation.hand_evaluator import HandEvaluator, HandAnalysis
from core.bidding.sayc_bidding import SAYCBidding
from shared.database.db_utils import db_utils
```

### For Shared Utilities
```python
from shared.utils.websocket_utils import broadcast_to_connection
from shared.security.jwt_utils import generate_jwt_token
```

## Benefits of New Structure

1. **Clear Separation of Concerns**: Each directory has a specific purpose
2. **Easier Navigation**: Developers can quickly find relevant code
3. **Better Maintainability**: Related functionality is grouped together
4. **Scalability**: Easy to add new features in appropriate directories
5. **Testing**: Clear separation between unit and integration tests
6. **Import Clarity**: Import paths clearly indicate module purpose

## Migration Notes

- All import statements have been updated to reflect the new structure
- Existing functionality remains unchanged
- Deployment scripts may need updates to reflect new file locations
- Test files have been moved to appropriate test directories

## Future Enhancements

- Add `api/analytics/` for game analytics and statistics
- Add `core/contract/` for contract evaluation and scoring
- Add `shared/caching/` for Redis or other caching utilities
- Add `shared/monitoring/` for logging and metrics
