# BridgeLambdas

Serverless backend for an online Bridge platform using AWS Lambda, API Gateway, and DynamoDB.

## Project Structure

- `lambdas/`: Lambda handler code for each API endpoint
- `models/`: Data models for users, rooms, and game state
- `tests/`: Unit tests for Lambda functions

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Add your AWS credentials for local testing (if needed).
3. Run tests:
   ```bash
   pytest
   ```

## APIs Implemented
- Authentication: `/account/create`, `/account/login`
- Room Management: `/room/create`, `/room/join`, `/room/start`, `/room/:id/state`
- Game Actions: `/room/:id/move`
- AI/Robot: `/ai/bid`, `/ai/play`, `/ai/double-dummy` 