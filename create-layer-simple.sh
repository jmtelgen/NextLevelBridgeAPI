#!/bin/bash

# Create Lambda Layer for Pydantic (simplified version)
# This uses a pre-built approach for Lambda compatibility

set -e

echo "Creating Lambda Layer for Pydantic..."

# Create layer directory structure
LAYER_DIR="pydantic-layer"
rm -rf $LAYER_DIR
mkdir -p $LAYER_DIR/python

# Install Pydantic and dependencies directly
cd $LAYER_DIR/python

# Install Pydantic with specific version known to work with Lambda
pip install pydantic==2.4.2 typing_extensions -t .

# Remove unnecessary files to reduce size
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.pyc" -delete 2>/dev/null || true

cd ../..

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
echo "3. Deploy your functions using ./deploy.sh"

# Clean up
rm -rf $LAYER_DIR 