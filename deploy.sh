#!/bin/bash

# BridgeLambdas Deployment Script
# Usage: ./deploy.sh <function-name>
# Example: ./deploy.sh room-create

set -e

FUNCTION_NAME=$1

if [ -z "$FUNCTION_NAME" ]; then
    echo "Usage: ./deploy.sh <function-name>"
    echo "Available functions:"
    echo ""
    echo "Authentication functions:"
    echo "  account-create"
    echo "  account-login"
    echo "  account-refresh-token"
    echo ""
    echo "Game functions:"
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
    echo "  websocket-change-seat"
    echo ""
    echo "AI functions:"
    echo "  robot-bridge-bidding"
    echo "  ai-double-dummy"
    echo "  WebCrawler"
    echo "  CrawlerTrigger"
    exit 1
fi

echo "Building deployment package for $FUNCTION_NAME..."

# Create temporary build directory
BUILD_DIR="build_$FUNCTION_NAME"
rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

# Copy shared dependencies
# Note: models directory is actually inside lambdas/models, so we only need to copy lambdas
cp -r lambdas $BUILD_DIR/

# Special handling for WebSocket functions that need the DDS library
if [[ $FUNCTION_NAME == websocket-make-bid ]] || [[ $FUNCTION_NAME == websocket-play-card ]]; then
    echo "WebSocket function with DDS requirements detected - ensuring DDS library is included..."
    # Make sure the DDS library files are executable in source
    chmod +x lambdas/dds/libdds.so.2.9.0
    chmod +x lambdas/dds/libdds.so.2
    chmod +x lambdas/dds/libdds.so
    # Verify DDS library files exist in source
    if [ ! -f "lambdas/dds/libdds.so.2" ]; then
        echo "Warning: DDS library file not found at lambdas/dds/libdds.so.2"
        echo "This may cause the WebSocket function to fail at runtime"
    else
        echo "✓ DDS library files found in source directory"
    fi
    
    # Verify files were copied to build directory
    echo "Verifying DDS library files were copied to build directory..."
    if [ -f "$BUILD_DIR/lambdas/dds/libdds.so.2" ]; then
        echo "✓ DDS library files successfully copied to build directory"
        # Set permissions in build directory
        chmod +x $BUILD_DIR/lambdas/dds/libdds.so.2.9.0
        chmod +x $BUILD_DIR/lambdas/dds/libdds.so.2
        chmod +x $BUILD_DIR/lambdas/dds/libdds.so
    else
        echo "❌ DDS library files failed to copy to build directory!"
        echo "This will cause the WebSocket function to fail at runtime"
        exit 1
    fi
fi

# Copy specific handler and rename function to lambda_handler
if [[ $FUNCTION_NAME == WebCrawler ]]; then
    cp lambdas/api/ai/web-crawler.py $BUILD_DIR/lambda_function.py
elif [[ $FUNCTION_NAME == CrawlerTrigger ]]; then
    cp lambdas/api/ai/crawler-trigger.py $BUILD_DIR/lambda_function.py
elif [[ $FUNCTION_NAME == robot-bridge-bidding ]]; then
    cp lambdas/api/ai/robot_bridge_bidding.py $BUILD_DIR/lambda_function.py
elif [[ $FUNCTION_NAME == ai-double-dummy ]]; then
    cp lambdas/api/ai/ai_double_dummy.py $BUILD_DIR/lambda_function.py
elif [[ $FUNCTION_NAME == account-* ]]; then
    cp lambdas/api/auth/${FUNCTION_NAME//-/_}.py $BUILD_DIR/lambda_function.py
elif [[ $FUNCTION_NAME == websocket-* ]]; then
    cp lambdas/api/websocket/${FUNCTION_NAME//-/_}.py $BUILD_DIR/lambda_function.py
elif [[ $FUNCTION_NAME == connection-count ]]; then
    cp lambdas/api/game/connection_count.py $BUILD_DIR/lambda_function.py
else
    # Try to find the file in the new structure
    if [ -f "lambdas/api/auth/${FUNCTION_NAME//-/_}.py" ]; then
        cp lambdas/api/auth/${FUNCTION_NAME//-/_}.py $BUILD_DIR/lambda_function.py
    elif [ -f "lambdas/api/game/${FUNCTION_NAME//-/_}.py" ]; then
        cp lambdas/api/game/${FUNCTION_NAME//-/_}.py $BUILD_DIR/lambda_function.py
    elif [ -f "lambdas/api/websocket/${FUNCTION_NAME//-/_}.py" ]; then
        cp lambdas/api/websocket/${FUNCTION_NAME//-/_}.py $BUILD_DIR/lambda_function.py
    elif [ -f "lambdas/api/ai/${FUNCTION_NAME//-/_}.py" ]; then
        cp lambdas/api/ai/${FUNCTION_NAME//-/_}.py $BUILD_DIR/lambda_function.py
    else
        echo "❌ Function file not found: ${FUNCTION_NAME//-/_}.py"
        echo "Searched in:"
        echo "  - lambdas/api/auth/"
        echo "  - lambdas/api/game/"
        echo "  - lambdas/api/websocket/"
        echo "  - lambdas/api/ai/"
        exit 1
    fi
fi
# Rename the handler function to lambda_handler (only if it exists)
if grep -q "def handler(" $BUILD_DIR/lambda_function.py; then
    sed -i 's/def handler(/def lambda_handler(/g' $BUILD_DIR/lambda_function.py
fi

# Fix imports for refactored files that use base classes or shared utilities
if grep -q "from shared\.\|from core\.\|from api\.\|from models\.\|from \." $BUILD_DIR/lambda_function.py; then
    # Update imports to work in the build directory structure
    sed -i 's/from shared\./from lambdas.shared./g' $BUILD_DIR/lambda_function.py
    sed -i 's/from core\./from lambdas.core./g' $BUILD_DIR/lambda_function.py
    sed -i 's/from api\./from lambdas.api./g' $BUILD_DIR/lambda_function.py
    sed -i 's/from models\./from lambdas.models./g' $BUILD_DIR/lambda_function.py
    # Fix relative imports
    sed -i 's/from \.shared\./from lambdas.shared./g' $BUILD_DIR/lambda_function.py
    sed -i 's/from \.core\./from lambdas.core./g' $BUILD_DIR/lambda_function.py
    sed -i 's/from \.api\./from lambdas.api./g' $BUILD_DIR/lambda_function.py
    sed -i 's/from \.models\./from lambdas.models./g' $BUILD_DIR/lambda_function.py
fi

# Copy function-specific requirements
cp requirements-function.txt $BUILD_DIR/requirements.txt

# Special handling for web crawler functions that need additional dependencies
if [[ $FUNCTION_NAME == WebCrawler ]] || [[ $FUNCTION_NAME == CrawlerTrigger ]]; then
    echo "Web crawler function detected - ensuring all dependencies are included..."
    # Web crawler needs requests and beautifulsoup4
    echo "" >> $BUILD_DIR/requirements.txt
    echo "requests" >> $BUILD_DIR/requirements.txt
    echo "beautifulsoup4" >> $BUILD_DIR/requirements.txt
    echo "✓ Additional dependencies added for web crawler"
    echo "Requirements file contents:"
    cat $BUILD_DIR/requirements.txt
fi

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
echo "   - BUCKET_NAME, TABLE_NAME, QUEUE_URL, TARGET_DOMAIN, MAX_DEPTH (for WebCrawler function)"
echo ""
echo "Or use AWS CLI:"
echo "aws lambda update-function-code --function-name $FUNCTION_NAME --zip-file fileb://${FUNCTION_NAME}-deployment.zip"

# Clean up
rm -rf $BUILD_DIR 