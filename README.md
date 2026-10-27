# BridgeLambdas

A serverless backend for an online Bridge platform built with AWS Lambda, API Gateway, and DynamoDB. This repository contains the backend services for the [BridgeApp](https://github.com/jmtelgen/BridgeApp) frontend application.

For the current server-authoritative playable bridge lifecycle, personalized
socket payloads, local verification, deployment route additions and remaining
release blockers, see [docs/WEBSOCKET_CONTRACT.md](docs/WEBSOCKET_CONTRACT.md).

For signup policy, cookie-based login/refresh/logout, deployment wiring and
credential-safe logging, see [docs/authentication.md](docs/authentication.md).

## 🏗️ Architecture

This backend is built using a serverless architecture with the following AWS services:

- **AWS Lambda**: Serverless compute for API endpoints
- **API Gateway**: RESTful API management and routing
- **DynamoDB**: NoSQL database for user accounts, rooms, and game state
- **CloudWatch**: Logging and monitoring

## 📁 Project Structure

```
BridgeLambdas/
├── lambdas/                 # Lambda handler functions
│   ├── account_create.py   # User registration
│   ├── account_login.py    # User authentication
│   ├── room_create.py      # Create new game rooms
│   ├── room_join.py        # Join existing rooms
│   ├── room_start.py       # Start game sessions
│   ├── room_state.py       # Get room/game state
│   ├── room_move.py        # Make game moves
│   ├── ai_bid.py           # AI bidding logic
│   ├── ai_play.py          # AI card playing
│   └── ai_double_dummy.py  # AI double dummy analysis
├── models/                  # Pydantic data models
│   ├── room.py             # Room data structure
│   ├── game_state.py       # Game state models
│   └── user.py             # User data structure
├── tests/                   # Unit tests
├── deploy.sh               # Deployment script
├── requirements.txt        # Python dependencies
└── requirements-function.txt # Function-specific dependencies
```

## 🚀 Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.12+
- Docker (for building Lambda layers if needed)

### Local Development Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd BridgeLambdas
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up AWS credentials** (if testing locally):
   ```bash
   aws configure
   ```

4. **Run tests**:
   ```bash
   pytest
   ```

## 📋 API Documentation

### Authentication Endpoints

#### Create Account
- **Endpoint**: `POST /account/create`
- **Body**:
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
- **Response**: `201` with user data (password hash excluded)

#### Login
- **Endpoint**: `POST /account/login`
- **Body**:
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
- **Response**: `200` with user data (password hash excluded)

### Room Management

#### Create Room
- **Endpoint**: `POST /room/create`
- **Body**:
  ```json
  {
    "ownerId": "string",
    "playerName": "string",
    "roomName": "string",
    "isPrivate": boolean
  }
  ```
- **Response**: `201` with room data

#### Join Room
- **Endpoint**: `POST /room/join`
- **Body**:
  ```json
  {
    "roomId": "string",
    "playerId": "string",
    "playerName": "string"
  }
  ```
- **Response**: `200` with updated room data

#### Get Room State
- **Endpoint**: `GET /room/{roomId}/state`
- **Response**: `200` with current room and game state

#### Start Game
- **Endpoint**: `POST /room/start`
- **Body**:
  ```json
  {
    "roomId": "string"
  }
  ```
- **Response**: `200` with initialized game state

### Game Actions

#### Make Move
- **Endpoint**: `POST /room/{roomId}/move`
- **Body**:
  ```json
  {
    "playerId": "string",
    "move": "string" // bid or card
  }
  ```
- **Response**: `200` with updated game state

### AI Endpoints

#### AI Bid
- **Endpoint**: `POST /ai/bid`
- **Body**: Game state and bidding context
- **Response**: `200` with AI bid recommendation

#### AI Play
- **Endpoint**: `POST /ai/play`
- **Body**: Game state and playing context
- **Response**: `200` with AI card recommendation

#### AI Double Dummy
- **Endpoint**: `POST /ai/double-dummy`
- **Body**: Complete game state
- **Response**: `200` with double dummy analysis

## 🚀 Deployment

### Automated Deployment

Use the provided deployment script to build and deploy Lambda functions:

```bash
# Deploy a specific function
./deploy.sh room-create

# Available functions:
# - account-create
# - account-login
# - room-create
# - room-join
# - room-start
# - room-state
# - room-move
# - ai-bid
# - ai-play
# - ai-double-dummy
```

### Manual Deployment

1. **Build deployment package**:
   ```bash
   ./deploy.sh <function-name>
   ```

2. **Upload to AWS Lambda**:
   ```bash
   aws lambda update-function-code \
     --function-name <function-name> \
     --zip-file fileb://<function-name>-deployment.zip
   ```

3. **Set environment variables**:
   - `USER_TABLE`: DynamoDB table for user accounts
   - `ROOM_TABLE`: DynamoDB table for rooms and game state

### Environment Variables

| Variable | Description | Required For |
|----------|-------------|--------------|
| `USER_TABLE` | DynamoDB table for user accounts | Account functions |
| `ROOM_TABLE` | DynamoDB table for rooms and game state | Room and game functions |

## 🔧 Configuration

### DynamoDB Tables

#### User Table
- **Primary Key**: `username` (String)
- **Attributes**: `passwordHash`, `createdAt`

#### Room Table
- **Primary Key**: `roomId` (String)
- **Attributes**: `ownerId`, `playerName`, `roomName`, `isPrivate`, `seats`, `state`, `gameData`

### API Gateway

Configure API Gateway with the following settings:
- **Runtime**: Python 3.12
- **Handler**: `lambda_function.lambda_handler`
- **Timeout**: 30 seconds (for AI functions)
- **Memory**: 512 MB (adjust based on function needs)

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_room_create.py

# Run with coverage
pytest --cov=lambdas --cov=models
```

## 🔗 Frontend Integration

This backend is designed to work with the [BridgeApp](https://github.com/jmtelgen/BridgeApp) frontend application. The frontend repository contains:

- React/TypeScript frontend application
- Real-time game interface
- User authentication UI
- Room management interface

## 📝 Data Models

### Room Model
```python
class Room(BaseModel):
    roomId: str
    ownerId: str
    playerName: str
    roomName: str
    isPrivate: bool
    seats: Dict[str, str]
    state: str
    gameData: Any
```

### Game State Model
```python
class GameState(BaseModel):
    currentPhase: str
    turn: str
    bids: List[Bid]
    hands: Dict[str, List[str]]
    tricks: List[Trick]
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the [BridgeApp](https://github.com/jmtelgen/BridgeApp) repository for frontend-related issues
2. Open an issue in this repository for backend-specific problems
3. Review the API documentation above for endpoint details 