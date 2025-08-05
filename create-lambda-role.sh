#!/bin/bash

# Create IAM Role for Lambda Execution
# This script creates the necessary IAM role and policies for Lambda functions

set -e

echo "Creating IAM role for Lambda execution..."

# Create the trust policy document
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the execution role
aws iam create-role \
    --role-name lambda-execution-role \
    --assume-role-policy-document file://trust-policy.json \
    --description "Role for Bridge Lambda functions"

echo "Role created successfully!"

# Create the execution policy
cat > execution-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/UsersTable",
        "arn:aws:dynamodb:*:*:table/GameRooms",
        "arn:aws:dynamodb:*:*:table/WebSocketConnections"
      ]
    }
  ]
}
EOF

# Attach the execution policy
aws iam put-role-policy \
    --role-name lambda-execution-role \
    --policy-name lambda-execution-policy \
    --policy-document file://execution-policy.json

echo "Execution policy attached successfully!"

# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name lambda-execution-role --query 'Role.Arn' --output text)

echo ""
echo "✅ Lambda execution role created successfully!"
echo "Role ARN: $ROLE_ARN"
echo ""
echo "Update your deploy-aws.sh script with this ARN:"
echo "ROLE_ARN=\"$ROLE_ARN\""
echo ""

# Clean up temporary files
rm -f trust-policy.json execution-policy.json

echo "Temporary files cleaned up." 