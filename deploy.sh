#!/bin/bash

# BridgeLambdas Deployment Script
# Usage: ./deploy.sh <function-name>
# Example: ./deploy.sh room-create

set -e

FUNCTION_NAME=$1

if [ -z "$FUNCTION_NAME" ]; then
    echo "Usage: ./deploy.sh <function-name>"
    echo "Available functions:"
    echo "  account-create"
    echo "  account-login"
    echo "  room-create"
    echo "  room-join"
    echo "  room-start"
    echo "  room-state"
    echo "  room-move"
    echo "  ai-bid"
    echo "  ai-play"
    echo "  ai-double-dummy"
    echo "  connection-count"
    echo ""
    echo "WebSocket functions:"
    echo "  websocket-connect"
    echo "  websocket-disconnect"
    echo "  websocket-create-room"
    echo "  websocket-join-room"
    echo "  websocket-start-room"
    echo "  websocket-make-bid"
    echo "  websocket-play-card"
    exit 1
fi

echo "Building deployment package for $FUNCTION_NAME..."

# Create temporary build directory
BUILD_DIR="build_$FUNCTION_NAME"
rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

# Copy shared dependencies
cp -r models $BUILD_DIR/
cp -r lambdas $BUILD_DIR/

# Copy specific handler and rename function to lambda_handler
cp lambdas/${FUNCTION_NAME//-/_}.py $BUILD_DIR/lambda_function.py
# Rename the handler function to lambda_handler (only if it exists)
if grep -q "def handler(" $BUILD_DIR/lambda_function.py; then
    sed -i 's/def handler(/def lambda_handler(/g' $BUILD_DIR/lambda_function.py
fi

# Fix imports for refactored files that use base classes
if grep -q "from base_handler import" $BUILD_DIR/lambda_function.py; then
    # Update imports to work in the build directory structure
    sed -i 's/from base_handler import/from lambdas.base_handler import/g' $BUILD_DIR/lambda_function.py
    sed -i 's/from db_utils import/from lambdas.db_utils import/g' $BUILD_DIR/lambda_function.py
    sed -i 's/from websocket_utils import/from lambdas.websocket_utils import/g' $BUILD_DIR/lambda_function.py
fi

# Copy function-specific requirements
cp requirements-function.txt $BUILD_DIR/requirements.txt
cd $BUILD_DIR

# Install dependencies to the package
pip install -r requirements.txt -t .

# Create deployment package
zip -r ../${FUNCTION_NAME}-deployment.zip . -x "*.pyc" -x "__pycache__/*" -x "tests/*" -x ".git/*"

cd ..

echo "Deployment package created: ${FUNCTION_NAME}-deployment.zip"
echo ""
echo "Next steps:"
echo "1. Upload ${FUNCTION_NAME}-deployment.zip to AWS Lambda"
echo "2. Set handler to: lambda_function.lambda_handler"
echo "3. Set environment variables:"
echo "   - USER_TABLE (for account functions)"
echo "   - ROOM_TABLE (for room functions)"
echo ""
echo "Or use AWS CLI:"
echo "aws lambda update-function-code --function-name $FUNCTION_NAME --zip-file fileb://${FUNCTION_NAME}-deployment.zip"

# Clean up
rm -rf $BUILD_DIR 