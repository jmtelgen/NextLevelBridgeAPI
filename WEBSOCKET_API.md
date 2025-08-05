# WebSocket API Documentation

This document describes the WebSocket API implementation for the Bridge application using AWS API Gateway WebSocket APIs.

## Overview

The WebSocket API provides real-time communication for the Bridge game, allowing players to:
- Join rooms
- Start games
- Make bids
- Play cards

All WebSocket functions are compatible with AWS API Gateway WebSocket APIs and follow the standard event structure.

## WebSocket Functions

### 1. Connect (`websocket-connect`)

**Route Key**: `$connect`

**Purpose**: Handles WebSocket connection establishment and stores connection information in DynamoDB.

**Event Structure** (automatically triggered by API Gateway):
```json
{
  "requestContext": {
    "connectionId": "connection-uuid",
    "routeKey": "$connect",
    "requestTimeEpoch": 1234567890,
    "identity": {
      "sourceIp": "192.168.1.1",
      "userAgent": "Mozilla/5.0..."
    }
  }
}
```

**Response Format**:
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Connected successfully\", \"connectionId\": \"connection-uuid\"}"
}
```

**DynamoDB Record Created**:
```json
{
  "connectionId": "connection-uuid",
  "connectedAt": 1234567890,
  "sourceIp": "192.168.1.1",
  "userAgent": "Mozilla/5.0...",
  "status": "connected",
  "lastActivity": 1234567890
}
```

### 2. Disconnect (`websocket-disconnect`)

**Route Key**: `$disconnect`

**Purpose**: Handles WebSocket connection termination and removes connection information from DynamoDB.

**Event Structure** (automatically triggered by API Gateway):
```json
{
  "requestContext": {
    "connectionId": "connection-uuid",
    "routeKey": "$disconnect",
    "requestTimeEpoch": 1234567890
  }
}
```

**Response Format**:
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Disconnected successfully\", \"connectionId\": \"connection-uuid\"}"
}
```

### 3. Create Room (`websocket-create-room`)

**Route Key**: `createRoom`

**Purpose**: Allows a player to create a new room and become the owner.

**Request Format**:
```json
{
  "ownerId": "user-id",
  "playerName": "Player Name",
  "roomName": "Room Name",
  "isPrivate": false
}
```

**Response Format**:
```json
{
  "action": "createRoom",
  "success": true,
  "room": {
    "roomId": "room-uuid",
    "ownerId": "user-id",
    "playerName": "Player Name",
    "roomName": "Room Name",
    "isPrivate": false,
    "seats": {
      "N": "user-id",
      "E": "",
      "S": "",
      "W": ""
    },
    "state": "waiting",
    "gameData": {
      "currentPhase": "waiting",
      "turn": "user-id",
      "bids": [],
      "hands": {
        "N": [],
        "E": [],
        "S": [],
        "W": []
      },
      "tricks": []
    }
  },
  "assignedSeat": "N",
  "message": "Room created successfully"
}
```

### 2. Join Room (`websocket-join-room`)

**Route Key**: `joinRoom`

**Purpose**: Allows a player to join an existing room and be assigned a seat.

**Request Format**:
```json
{
  "roomId": "room-uuid",
  "userId": "user-id",
  "seat": "N"  // Optional: specific seat request
}
```

**Response Format**:
```json
{
  "action": "joinRoom",
  "success": true,
  "room": {
    "roomId": "room-uuid",
    "ownerId": "owner-id",
    "playerName": "Player Name",
    "roomName": "Room Name",
    "isPrivate": false,
    "seats": {
      "N": "user-id",
      "E": "",
      "S": "",
      "W": ""
    },
    "state": "waiting",
    "gameData": {}
  },
  "assignedSeat": "N"
}
```

### 4. Start Room (`websocket-start-room`)

**Route Key**: `startRoom`

**Purpose**: Allows the room owner to start the game, filling empty seats with robots.

**Request Format**:
```json
{
  "roomId": "room-uuid",
  "userId": "user-id"
}
```

**Response Format**:
```json
{
  "action": "startRoom",
  "success": true,
  "room": {
    "roomId": "room-uuid",
    "ownerId": "owner-id",
    "playerName": "Player Name",
    "roomName": "Room Name",
    "isPrivate": false,
    "seats": {
      "N": "user-id",
      "E": "robot-E",
      "S": "robot-S",
      "W": "robot-W"
    },
    "state": "bidding",
    "gameData": {
      "currentPhase": "bidding",
      "turn": "user-id",
      "bids": [],
      "hands": {
        "N": [],
        "E": [],
        "S": [],
        "W": []
      },
      "tricks": []
    }
  },
  "message": "Game started successfully"
}
```

### 5. Make Bid (`websocket-make-bid`)

**Route Key**: `makeBid`

**Purpose**: Allows a player to make a bid during the bidding phase.

**Request Format**:
```json
{
  "roomId": "room-uuid",
  "userId": "user-id",
  "bid": "1H"
}
```

**Valid Bids**:
- `pass`, `double`, `redouble`
- `1C`, `1D`, `1H`, `1S`, `1NT`
- `2C`, `2D`, `2H`, `2S`, `2NT`
- `3C`, `3D`, `3H`, `3S`, `3NT`
- `4C`, `4D`, `4H`, `4S`, `4NT`
- `5C`, `5D`, `5H`, `5S`, `5NT`
- `6C`, `6D`, `6H`, `6S`, `6NT`
- `7C`, `7D`, `7H`, `7S`, `7NT`

**Response Format**:
```json
{
  "action": "makeBid",
  "success": true,
  "bid": {
    "seat": "N",
    "bid": "1H",
    "timestamp": 1234567890
  },
  "nextTurn": "user-id-2",
  "gameData": {
    "currentPhase": "bidding",
    "turn": "user-id-2",
    "bids": [
      {
        "seat": "N",
        "bid": "1H",
        "timestamp": 1234567890
      }
    ],
    "hands": {},
    "tricks": []
  },
  "message": "Bid 1H recorded successfully"
}
```

### 6. Play Card (`websocket-play-card`)

**Route Key**: `playCard`

**Purpose**: Allows a player to play a card during the playing phase.

**Request Format**:
```json
{
  "roomId": "room-uuid",
  "userId": "user-id",
  "card": "AH"
}
```

**Card Format**: Two-character string where:
- First character: Rank (`2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `10`, `J`, `Q`, `K`, `A`)
- Second character: Suit (`C`, `D`, `H`, `S`)

**Response Format**:
```json
{
  "action": "playCard",
  "success": true,
  "play": {
    "seat": "N",
    "card": "AH",
    "timestamp": 1234567890
  },
  "nextTurn": "user-id-2",
  "gameData": {
    "currentPhase": "playing",
    "turn": "user-id-2",
    "bids": [...],
    "hands": {
      "N": ["KD", "QS", ...],
      "E": [...],
      "S": [...],
      "W": [...]
    },
    "currentTrick": [
      {
        "seat": "N",
        "card": "AH",
        "timestamp": 1234567890
      }
    ],
    "tricks": [...]
  },
  "message": "Card AH played successfully"
}
```

## WebSocket Event Structure

All WebSocket functions expect the following event structure from API Gateway:

```json
{
  "requestContext": {
    "connectionId": "connection-uuid",
    "routeKey": "route-key",
    "messageId": "message-uuid",
    "eventType": "MESSAGE",
    "extendedRequestId": "request-uuid",
    "requestTime": "12/Mar/2024:19:03:58 +0000",
    "messageDirection": "IN",
    "stage": "prod",
    "connectedAt": 1647123456789,
    "requestTimeEpoch": 1647123456789,
    "identity": {
      "cognitoIdentityPoolId": null,
      "accountId": null,
      "cognitoIdentityId": null,
      "caller": null,
      "sourceIp": "192.168.1.1",
      "principalOrgId": null,
      "accessKey": null,
      "cognitoAuthenticationType": null,
      "cognitoAuthenticationProvider": null,
      "userArn": null,
      "userAgent": "Mozilla/5.0...",
      "user": null
    },
    "authorizer": null,
    "apiId": "api-id"
  },
  "body": "{\"roomId\": \"room-uuid\", \"userId\": \"user-id\"}",
  "isBase64Encoded": false
}
```

## Deployment

### Deploy WebSocket Functions

```bash
# Deploy individual WebSocket functions
./deploy.sh websocket-connect
./deploy.sh websocket-disconnect
./deploy.sh websocket-create-room
./deploy.sh websocket-join-room
./deploy.sh websocket-start-room
./deploy.sh websocket-make-bid
./deploy.sh websocket-play-card
```

### API Gateway Configuration

1. **Create WebSocket API**:
   - Go to API Gateway console
   - Create API → WebSocket API
   - Name: `BridgeWebSocketAPI`

2. **Configure Routes**:
   - `$connect` → `websocket-connect` Lambda
   - `$disconnect` → `websocket-disconnect` Lambda
   - `createRoom` → `websocket-create-room` Lambda
   - `joinRoom` → `websocket-join-room` Lambda
   - `startRoom` → `websocket-start-room` Lambda
   - `makeBid` → `websocket-make-bid` Lambda
   - `playCard` → `websocket-play-card` Lambda

3. **Deploy API**:
   - Create deployment stage (e.g., `prod`)
   - Note the WebSocket URL: `wss://api-id.execute-api.region.amazonaws.com/prod`

## Environment Variables

WebSocket functions require different environment variables based on their purpose:

- `WEBSOCKET_CONNECTIONS_TABLE`: DynamoDB table for WebSocket connections (connect/disconnect functions)
- `USER_TABLE`: DynamoDB table for user accounts (start-room function)
- `ROOM_TABLE`: DynamoDB table for rooms and game state (most functions)

## Error Handling

All WebSocket functions return consistent error responses:

```json
{
  "error": "Error message description"
}
```

Common error scenarios:
- `400`: Invalid request parameters
- `401`: User not authenticated
- `404`: Room not found
- `500`: Server error

## Frontend Integration

### WebSocket Connection

```javascript
const ws = new WebSocket('wss://api-id.execute-api.region.amazonaws.com/prod');

ws.onopen = () => {
  console.log('Connected to WebSocket');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};

ws.onclose = () => {
  console.log('Disconnected from WebSocket');
};
```

### Sending Messages

```javascript
// Create room
ws.send(JSON.stringify({
  action: 'createRoom',
  ownerId: 'user-id',
  playerName: 'Player Name',
  roomName: 'Room Name',
  isPrivate: false
}));

// Join room
ws.send(JSON.stringify({
  action: 'joinRoom',
  roomId: 'room-uuid',
  userId: 'user-id',
  seat: 'N'
}));

// Start room
ws.send(JSON.stringify({
  action: 'startRoom',
  roomId: 'room-uuid',
  userId: 'user-id'
}));

// Make bid
ws.send(JSON.stringify({
  action: 'makeBid',
  roomId: 'room-uuid',
  userId: 'user-id',
  bid: '1H'
}));

// Play card
ws.send(JSON.stringify({
  action: 'playCard',
  roomId: 'room-uuid',
  userId: 'user-id',
  card: 'AH'
}));
```

## Security Considerations

1. **Authentication**: Implement proper authentication for WebSocket connections
2. **Authorization**: Verify user permissions for each action
3. **Input Validation**: All inputs are validated server-side
4. **Rate Limiting**: Consider implementing rate limiting for WebSocket messages
5. **Connection Management**: Handle connection cleanup and reconnection logic

## Testing

Test WebSocket functions using tools like:
- AWS Lambda console (with test events)
- WebSocket clients (wscat, Postman)
- Custom WebSocket test client

Example test event for Lambda console:
```json
{
  "requestContext": {
    "connectionId": "test-connection",
    "routeKey": "joinRoom"
  },
  "body": "{\"roomId\": \"test-room\", \"userId\": \"test-user\", \"seat\": \"N\"}"
}
``` 