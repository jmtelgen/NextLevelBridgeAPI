# BridgeLambdas Deployment Guide

## Overview
This project uses separate Lambda functions for each API endpoint. Each function is deployed independently with its own deployment package.

## Prerequisites

1. **AWS CLI configured** with appropriate permissions
2. **IAM Role** with Lambda execution permissions
3. **DynamoDB tables** created:
   - `users-table` (for account functions)
   - `rooms-table` (for room functions)

## Deployment Steps

### 1. **Update Configuration**
Edit `deploy-aws.sh` and update:
- `REGION`: Your AWS region
- `ROLE_ARN`: Your Lambda execution role ARN

### 2. **Build and Deploy Individual Functions**

#### **Room Create Function:**
```bash
# Build deployment package
./deploy.sh room-create

# Create new function
./deploy-aws.sh room-create create

# Update existing function
./deploy-aws.sh room-create update
```

#### **Room Join Function:**
```bash
./deploy.sh room-join
./deploy-aws.sh room-join create
```

#### **Room Start Function:**
```bash
./deploy.sh room-start
./deploy-aws.sh room-start create
```

#### **Account Functions:**
```bash
./deploy.sh account-create
./deploy-aws.sh account-create create

./deploy.sh account-login
./deploy-aws.sh account-login create
```

### 3. **Manual Deployment (Alternative)**

If you prefer manual deployment:

1. **Build package:**
   ```bash
   ./deploy.sh room-create
   ```

2. **Upload to AWS Lambda console:**
   - Go to AWS Lambda console
   - Create new function or update existing
   - Upload `room-create-deployment.zip`
   - Set handler to: `lambda_function.handler`
   - Set environment variables:
     - `ROOM_TABLE=rooms-table` (for room functions)
     - `USER_TABLE=users-table` (for account functions)

### 4. **API Gateway Configuration**

For each Lambda function, create an API Gateway endpoint:

#### **Room Create API:**
- **Method:** POST
- **Resource:** `/room/create`
- **Integration:** Lambda function `room-create`

#### **Room Join API:**
- **Method:** POST
- **Resource:** `/room/join`
- **Integration:** Lambda function `room-join`

#### **Room Start API:**
- **Method:** POST
- **Resource:** `/room/start`
- **Integration:** Lambda function `room-start`

## Function List

| Function Name | Handler File | Environment Variables | API Endpoint |
|---------------|--------------|----------------------|--------------|
| `account-create` | `lambdas/account_create.py` | `USER_TABLE` | `POST /account/create` |
| `account-login` | `lambdas/account_login.py` | `USER_TABLE` | `POST /account/login` |
| `room-create` | `lambdas/room_create.py` | `ROOM_TABLE` | `POST /room/create` |
| `room-join` | `lambdas/room_join.py` | `ROOM_TABLE` | `POST /room/join` |
| `room-start` | `lambdas/room_start.py` | `ROOM_TABLE` | `POST /room/start` |
| `room-state` | `lambdas/room_state.py` | `ROOM_TABLE` | `GET /room/{id}/state` |
| `room-move` | `lambdas/room_move.py` | `ROOM_TABLE` | `POST /room/{id}/move` |
| `ai-bid` | `lambdas/ai_bid.py` | None | `POST /ai/bid` |
| `ai-play` | `lambdas/ai_play.py` | None | `POST /ai/play` |
| `ai-double-dummy` | `lambdas/ai_double_dummy.py` | None | `GET /ai/double-dummy` |

## Testing

After deployment, test each function:

```bash
# Test room create
aws lambda invoke \
  --function-name room-create \
  --payload '{"body": "{\"ownerId\": \"user-123\"}"}' \
  response.json

# Test room join
aws lambda invoke \
  --function-name room-join \
  --payload '{"body": "{\"userId\": \"user-456\", \"roomId\": \"room-abc\"}"}' \
  response.json
```

## Troubleshooting

### Common Issues:

1. **Import errors:** Make sure all dependencies are included in the deployment package
2. **Environment variables:** Verify they're set correctly for each function
3. **IAM permissions:** Ensure Lambda execution role has DynamoDB access
4. **Handler configuration:** Must be set to `lambda_function.handler`

### Debugging:

1. Check CloudWatch logs for each function
2. Test functions directly with AWS CLI before API Gateway
3. Verify DynamoDB table names and permissions 