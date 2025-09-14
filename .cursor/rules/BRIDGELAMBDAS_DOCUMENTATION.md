# BridgeLambdas Documentation Index

This directory contains all documentation for the BridgeLambdas project. The project has been restructured for better organization and maintainability.

## Documentation Files

### 1. PROJECT_STRUCTURE.md
- **Purpose**: Complete overview of the restructured project directory layout
- **Contents**: 
  - Directory organization (api/, core/, shared/, tests/)
  - Import patterns and examples
  - Migration notes and benefits
  - Future enhancement suggestions

### 2. ROBOT_BIDDING_README.md
- **Purpose**: Documentation for the robot bidding system
- **Contents**:
  - SAYC (Standard American Yellow Card) system implementation
  - Fantoni-Nunes system as fallback
  - Architecture overview
  - Usage examples and testing

### 3. deployment-memory.md
- **Purpose**: Deployment configuration and memory
- **Contents**: AWS deployment settings and configurations

### 4. memory.mdc & rules.mdc
- **Purpose**: Cursor IDE rules and memory files
- **Contents**: IDE-specific configurations and rules

## Key Project Structure

```
lambdas/
├── api/                    # API handlers by functionality
│   ├── auth/              # Authentication APIs
│   ├── game/              # Game management APIs
│   ├── websocket/         # WebSocket APIs
│   └── ai/                # AI and automation APIs
├── core/                  # Core business logic
│   ├── bidding/           # All bidding systems (SAYC, Fantoni-Nunes)
│   ├── hand_evaluation/   # Hand analysis
│   └── robot/             # Robot player logic
├── shared/                # Shared utilities
│   ├── database/          # Database utilities
│   ├── security/          # Auth, JWT, passwords
│   └── utils/             # General utilities
└── tests/                 # Test suites
    ├── unit/              # Unit tests
    └── integration/       # Integration tests
```

## Recent Changes

- **SAYC Integration**: Primary bidding system for robot players
- **Project Restructuring**: Organized code into logical directories
- **Deployment Updates**: Updated deploy.sh and deploy-aws.sh for new structure
- **Import Updates**: All import statements updated for new structure

## Usage

When working on this project, refer to:
- `PROJECT_STRUCTURE.md` for understanding the codebase organization
- `ROBOT_BIDDING_README.md` for bidding system implementation details
- `deployment-memory.md` for deployment configurations

All documentation is maintained in this `.cursor/rules` directory for easy access and reference.
