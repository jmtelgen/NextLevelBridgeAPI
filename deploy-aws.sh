#!/bin/bash

# AWS CLI Deployment Script for BridgeLambdas
# Usage: ./deploy-aws.sh <function-name> [create|update]
# Example: ./deploy-aws.sh room-create create

set -e

FUNCTION_NAME=$1
ACTION=$2

if [ -z "$FUNCTION_NAME" ] || [ -z "$ACTION" ]; then
    echo "Usage: ./deploy-aws.sh <function-name> [create|update]"
    echo "Available functions:"
    echo "  room-create → CreateRoomAPILambda"
    echo "  room-join → JoinRoomAPILambda"
    echo "  room-start → StartRoomAPILambda"
    echo "  account-create → CreateAccountAPILambda"
    echo "  account-login → LoginAPILambda"
    echo "  ai-double-dummy → GetDoubleDummyLambda"
    echo ""
    echo "WebSocket functions:"
    echo "  websocket-connect → WebSocketConnectLambda"
    echo "  websocket-disconnect → WebSocketDisconnectLambda"
    echo "  websocket-create-room → WebSocketCreateRoomLambda"
    echo "  websocket-join-room → WebSocketJoinRoomLambda"
    echo "  websocket-start-room → WebSocketStartRoomLambda"
    echo "  websocket-make-bid → WebSocketMakeBidLambda"
    echo "  websocket-play-card → WebSocketPlayCardLambda"
    exit 1
fi

# Configuration
REGION="us-west-2"  # Change to your region
RUNTIME="python3.12"
# Update this with your account ID and role name
ROLE_ARN="arn:aws:iam::851725597758:role/lambda-execution-role"
TIMEOUT=30
MEMORY_SIZE=256

# Map function names to actual Lambda function names
case $FUNCTION_NAME in
    "room-create")
        LAMBDA_FUNCTION_NAME="CreateRoomAPILambda"
        ;;
    "room-join")
        LAMBDA_FUNCTION_NAME="JoinRoomAPILambda"
        ;;
    "room-start")
        LAMBDA_FUNCTION_NAME="StartRoomAPILambda"
        ;;
    "account-create")
        LAMBDA_FUNCTION_NAME="CreateAccountAPILambda"
        ;;
    "account-login")
        LAMBDA_FUNCTION_NAME="LoginAPILambda"
        ;;
    "ai-double-dummy")
        LAMBDA_FUNCTION_NAME="GetDoubleDummyLambda"
        ;;
    "websocket-connect")
        LAMBDA_FUNCTION_NAME="WebSocketConnectLambda"
        ;;
    "websocket-disconnect")
        LAMBDA_FUNCTION_NAME="WebSocketDisconnectLambda"
        ;;
    "websocket-create-room")
        LAMBDA_FUNCTION_NAME="WebSocketCreateRoomLambda"
        ;;
    "websocket-join-room")
        LAMBDA_FUNCTION_NAME="WebSocketJoinRoomLambda"
        ;;
    "websocket-start-room")
        LAMBDA_FUNCTION_NAME="WebSocketStartRoomLambda"
        ;;
    "websocket-make-bid")
        LAMBDA_FUNCTION_NAME="WebSocketMakeBidLambda"
        ;;
    "websocket-play-card")
        LAMBDA_FUNCTION_NAME="WebSocketPlayCardLambda"
        ;;
    *)
        echo "Unknown function: $FUNCTION_NAME"
        exit 1
        ;;
esac

# Build the deployment package first
./deploy.sh $FUNCTION_NAME

if [ "$ACTION" = "create" ]; then
    echo "Creating Lambda function: $LAMBDA_FUNCTION_NAME"
    
    # Set environment variables based on function type
    ENV_VARS=""
    if [[ $FUNCTION_NAME == account-* ]]; then
        ENV_VARS="Variables={USER_TABLE=UsersTable}"
    elif [[ $FUNCTION_NAME == room-* ]] || [[ $FUNCTION_NAME == websocket-* ]]; then
        # WebSocket functions need different tables based on their purpose
        if [[ $FUNCTION_NAME == websocket-connect ]] || [[ $FUNCTION_NAME == websocket-disconnect ]]; then
            ENV_VARS="Variables={WEBSOCKET_CONNECTIONS_TABLE=WebSocketConnections}"
        elif [[ $FUNCTION_NAME == websocket-start-room ]]; then
            ENV_VARS="Variables={USER_TABLE=UsersTable,ROOM_TABLE=GameRooms}"
        else
            ENV_VARS="Variables={ROOM_TABLE=GameRooms}"
        fi
    fi
    
    aws lambda create-function \
        --function-name $LAMBDA_FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler lambda_function.handler \
        --zip-file fileb://${FUNCTION_NAME}-deployment.zip \
        --timeout $TIMEOUT \
        --memory-size $MEMORY_SIZE \
        --environment $ENV_VARS \
        --region $REGION
        
    echo "Function $LAMBDA_FUNCTION_NAME created successfully!"
    
elif [ "$ACTION" = "update" ]; then
    echo "Updating Lambda function: $LAMBDA_FUNCTION_NAME"
    
    aws lambda update-function-code \
        --function-name $LAMBDA_FUNCTION_NAME \
        --zip-file fileb://${FUNCTION_NAME}-deployment.zip \
        --region $REGION
        
    echo "Function $LAMBDA_FUNCTION_NAME updated successfully!"
    
else
    echo "Invalid action. Use 'create' or 'update'"
    exit 1
fi

echo ""
echo "Next steps:"
if [[ $FUNCTION_NAME == websocket-* ]]; then
    echo "1. Configure API Gateway WebSocket API to route to this Lambda"
    echo "2. Set up route key mapping (e.g., 'createRoom' → WebSocketCreateRoomLambda)"
    echo "3. Test the WebSocket function"
    echo "4. Set up proper IAM roles and permissions"
else
    echo "1. Configure API Gateway REST API to route to this Lambda"
    echo "2. Test the function"
    echo "3. Set up proper IAM roles and permissions"
fi 