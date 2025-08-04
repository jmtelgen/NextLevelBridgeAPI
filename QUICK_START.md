# Quick Start Guide

## Deploy Your First Lambda Function

### 1. **Build a Deployment Package**
```bash
# For room-create function
./deploy.sh room-create

# For room-join function  
./deploy.sh room-join

# For room-start function
./deploy.sh room-start
```

### 2. **Deploy to AWS (Manual)**
1. Go to AWS Lambda Console
2. Create new function or update existing
3. Upload the generated zip file (e.g., `room-create-deployment.zip`)
4. Set handler to: `lambda_function.handler`
5. Set environment variables:
   - `ROOM_TABLE=rooms-table` (for room functions)
   - `USER_TABLE=users-table` (for account functions)

### 3. **Deploy to AWS (CLI)**
```bash
# Update your AWS region and role ARN in deploy-aws.sh first
./deploy-aws.sh room-create create
```

### 4. **Test Your Function**
```bash
# Test room-create
aws lambda invoke \
  --function-name room-create \
  --payload '{"body": "{\"ownerId\": \"user-123\"}"}' \
  response.json

cat response.json
```

## Available Functions

| Function | Command | Environment Variables |
|----------|---------|----------------------|
| `room-create` | `./deploy.sh room-create` | `ROOM_TABLE` |
| `room-join` | `./deploy.sh room-join` | `ROOM_TABLE` |
| `room-start` | `./deploy.sh room-start` | `ROOM_TABLE` |
| `account-create` | `./deploy.sh account-create` | `USER_TABLE` |
| `account-login` | `./deploy.sh account-login` | `USER_TABLE` |

## Next Steps
1. Set up API Gateway endpoints
2. Configure DynamoDB tables
3. Set up proper IAM roles
4. Test the full API flow

See `DEPLOYMENT.md` for detailed instructions. 