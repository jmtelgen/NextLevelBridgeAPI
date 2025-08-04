#!/bin/bash

# Create Lambda Layer for Pydantic and dependencies
# This builds the layer in a Lambda-compatible environment

set -e

echo "Creating Lambda Layer for Pydantic..."

# Create layer directory structure
LAYER_DIR="pydantic-layer"
rm -rf $LAYER_DIR
mkdir -p $LAYER_DIR/python

# Copy requirements
cp requirements.txt $LAYER_DIR/

# Use Docker to build in Lambda-compatible environment
echo "Building Pydantic layer in Lambda-compatible environment..."
docker run --rm -v "$(pwd)/$LAYER_DIR:/var/task" public.ecr.aws/lambda/python:3.12 \
    pip install -r /var/task/requirements.txt -t /var/task/python

# Create layer package
cd $LAYER_DIR
zip -r ../pydantic-layer.zip python/
cd ..

echo "Lambda Layer created: pydantic-layer.zip"
echo ""
echo "Next steps:"
echo "1. Create Lambda Layer in AWS Console or CLI:"
echo "   aws lambda publish-layer-version \\"
echo "     --layer-name pydantic-layer \\"
echo "     --description 'Pydantic and dependencies for BridgeLambdas' \\"
echo "     --zip-file fileb://pydantic-layer.zip \\"
echo "     --compatible-runtimes python3.12"
echo ""
echo "2. Attach the layer to your Lambda functions"
echo "3. Update deployment scripts to exclude Pydantic from function packages"

# Clean up
rm -rf $LAYER_DIR 