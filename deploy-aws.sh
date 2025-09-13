#!/bin/bash

# AWS CLI Deployment Script for BridgeLambdas
# Usage: ./deploy-aws.sh <function-name> [create|update]
# Example: ./deploy-aws.sh room-create create
#
# NOTE: When adding new Lambda functions, update this script to include:
# 1. Add function to the help text (lines 14-35)
# 2. Add case mapping (lines 44-104)
# 3. Add environment variables (lines 105-132)
# 4. Add timeout/memory settings if needed (lines 138-147)
# 5. Add next steps guidance (lines 179-193)

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
    echo "  account-refresh-token → RefreshTokenAPILambda"
    echo "  connection-count → ConnectionCountAPILambda"
    echo ""
    echo "WebSocket functions:"
    echo "  websocket-connect → WebSocketConnectLambda"
    echo "  websocket-disconnect → WebSocketDisconnectLambda"
    echo "  websocket-create-room → WebSocketCreateRoomLambda"
    echo "  websocket-join-room → WebSocketJoinRoomLambda"
    echo "  websocket-start-room → WebSocketStartRoomLambda"
    echo "  websocket-change-seat → WebSocketChangeSeatLambda"
    echo "  websocket-make-bid → WebSocketMakeBidLambda"
    echo "  websocket-play-card → WebSocketPlayCardLambda"
    echo ""
    echo "Web Crawler functions:"
    echo "  WebCrawler → WebCrawler"
    echo "  CrawlerTrigger → CrawlerTrigger"
    exit 1
fi

# Configuration
REGION="us-west-2"  # Change to your region
RUNTIME="python3.12"
# Update this with your account ID and role name
ROLE_ARN="arn:aws:iam::851725597758:role/lambda-execution-role"
TIMEOUT=30
MEMORY_SIZE=512

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
    "account-refresh-token")
        LAMBDA_FUNCTION_NAME="RefreshTokenAPILambda"
        ;;

    "connection-count")
        LAMBDA_FUNCTION_NAME="ConnectionCountAPILambda"
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
    "websocket-change-seat")
        LAMBDA_FUNCTION_NAME="WebSocketChangeSeatLambda"
        ;;
    "websocket-make-bid")
        LAMBDA_FUNCTION_NAME="WebSocketMakeBidLambda"
        ;;
    "websocket-play-card")
        LAMBDA_FUNCTION_NAME="WebSocketPlayCardLambda"
        ;;
    "WebCrawler")
        LAMBDA_FUNCTION_NAME="WebCrawler"
        ;;
    "CrawlerTrigger")
        LAMBDA_FUNCTION_NAME="CrawlerTrigger"
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
        ENV_VARS="Variables={USER_TABLE=UsersTable,JWT_SECRET_ID=Bridge/JWT}"
    elif [[ $FUNCTION_NAME == room-* ]] || [[ $FUNCTION_NAME == websocket-* ]]; then
        # WebSocket functions need different tables based on their purpose
        if [[ $FUNCTION_NAME == websocket-connect ]] || [[ $FUNCTION_NAME == websocket-disconnect ]]; then
            ENV_VARS="Variables={WEBSOCKET_CONNECTIONS_TABLE=WebSocketConnections}"
        elif [[ $FUNCTION_NAME == websocket-start-room ]]; then
            ENV_VARS="Variables={USER_TABLE=UsersTable,ROOM_TABLE=GameRooms}"
        else
            ENV_VARS="Variables={ROOM_TABLE=GameRooms}"
        fi
    elif [[ $FUNCTION_NAME == connection-count ]]; then
        ENV_VARS="Variables={WEBSOCKET_CONNECTIONS_TABLE=WebSocketConnections}"
    elif [[ $FUNCTION_NAME == WebCrawler ]]; then
        ENV_VARS="Variables={BUCKET_NAME=bridge-lambdas-crawler-html-2024,TABLE_NAME=crawler-metadata,QUEUE_URL=REPLACE_WITH_YOUR_QUEUE_URL,TARGET_DOMAIN=kwbridge.com,MAX_DEPTH=2}"
    elif [[ $FUNCTION_NAME == CrawlerTrigger ]]; then
        ENV_VARS="Variables={QUEUE_URL=REPLACE_WITH_YOUR_QUEUE_URL,TABLE_NAME=crawler-metadata}"
    fi
    
    # Set timeout and memory based on function type
    FUNCTION_TIMEOUT=$TIMEOUT
    FUNCTION_MEMORY=$MEMORY_SIZE
    
    if [[ $FUNCTION_NAME == account-* ]]; then
        FUNCTION_TIMEOUT=15  # 15 seconds for account functions
        FUNCTION_MEMORY=512  # 512 MB for account functions
    elif [[ $FUNCTION_NAME == WebCrawler ]]; then
        FUNCTION_TIMEOUT=300  # 5 minutes for web crawler (needs time to process)
        FUNCTION_MEMORY=1024  # 1 GB for web crawler (needs memory for HTML processing)
    elif [[ $FUNCTION_NAME == CrawlerTrigger ]]; then
        FUNCTION_TIMEOUT=30   # 30 seconds for trigger function
        FUNCTION_MEMORY=512   # 512 MB for trigger function
    fi
    
    aws lambda create-function \
        --function-name $LAMBDA_FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://${FUNCTION_NAME}-deployment.zip \
        --timeout $FUNCTION_TIMEOUT \
        --memory-size $FUNCTION_MEMORY \
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
elif [[ $FUNCTION_NAME == WebCrawler ]] || [[ $FUNCTION_NAME == CrawlerTrigger ]]; then
    echo "1. Update QUEUE_URL environment variable with actual SQS queue URL"
    echo "2. Set up proper IAM roles and permissions (DynamoDB, SQS, S3)"
    echo "3. Create SQS trigger for WebCrawler function"
    echo "4. Test the crawler with: aws lambda invoke --function-name CrawlerTrigger --payload '{\"action\":\"start_crawl\",\"start_url\":\"https://kwbridge.com/\"}' response.json"
else
    echo "1. Configure API Gateway REST API to route to this Lambda"
    echo "2. Test the function"
    echo "3. Set up proper IAM roles and permissions"
fi 