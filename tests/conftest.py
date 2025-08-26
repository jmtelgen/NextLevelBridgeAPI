import pytest
import os
import sys
import boto3
from unittest.mock import MagicMock, patch

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Common test fixtures and configuration
@pytest.fixture(scope="session")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

@pytest.fixture(scope="session")
def dynamodb(aws_credentials):
    """Mocked DynamoDB resource."""
    with patch('boto3.resource') as mock_resource:
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        yield mock_dynamodb

@pytest.fixture(scope="session")
def apigateway(aws_credentials):
    """Mocked API Gateway client."""
    with patch('boto3.client') as mock_client:
        mock_apigateway = MagicMock()
        mock_client.return_value = mock_apigateway
        yield mock_apigateway

@pytest.fixture(scope="function")
def mock_environment():
    """Set up common environment variables for testing."""
    env_vars = {
        'ROOM_TABLE': 'test-rooms-table',
        'WEBSOCKET_CONNECTIONS_TABLE': 'test-connections-table',
        'USER_TABLE': 'test-users-table',
        'JWT_SECRET': 'test-jwt-secret-key',
        'AWS_REGION': 'us-east-1'
    }
    
    # Store original values
    original_env = {}
    for key in env_vars:
        if key in os.environ:
            original_env[key] = os.environ[key]
    
    # Set test values
    for key, value in env_vars.items():
        os.environ[key] = value
    
    yield env_vars
    
    # Restore original values
    for key in env_vars:
        if key in original_env:
            os.environ[key] = original_env[key]
        else:
            del os.environ[key]

@pytest.fixture(scope="function")
def sample_room_data():
    """Sample room data for testing."""
    return {
        'roomId': 'test-room-123',
        'ownerId': 'test-user-123',
        'roomName': 'Test Room',
        'state': 'waiting',
        'seats': {
            'North': 'test-user-123',
            'East': 'robot-E',
            'South': 'robot-S',
            'West': 'robot-W'
        },
        'gameData': {
            'currentPhase': 'waiting',
            'turn': 'N',  # North's turn (position, not userId)
            'bids': [],
            'hands': {'N': [], 'E': [], 'S': [], 'W': []},
            'tricks': []
        },
        'createdAt': '2023-01-01T00:00:00Z',
        'updatedAt': '2023-01-01T00:00:00Z'
    }

@pytest.fixture(scope="function")
def sample_user_data():
    """Sample user data for testing."""
    return {
        'userId': 'test-user-123',
        'email': 'test@example.com',
        'username': 'testuser',
        'hashedPassword': 'hashed_password_123',
        'createdAt': '2023-01-01T00:00:00Z',
        'lastLogin': '2023-01-01T00:00:00Z',
        'isActive': True
    }

@pytest.fixture(scope="function")
def sample_websocket_event():
    """Sample WebSocket event for testing."""
    return {
        'requestContext': {
            'routeKey': 'testRoute',
            'connectionId': 'test-connection-123',
            'domainName': 'test.execute-api.us-east-1.amazonaws.com',
            'stage': 'test'
        },
        'body': '{"test": "data"}',
        'isBase64Encoded': False
    }

@pytest.fixture(scope="function")
def sample_lambda_context():
    """Sample Lambda context for testing."""
    context = MagicMock()
    context.function_name = 'test-function'
    context.function_version = '$LATEST'
    context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test-function'
    context.memory_limit_in_mb = 128
    context.remaining_time_in_millis = 30000
    context.aws_request_id = 'test-request-id'
    return context

@pytest.fixture(scope="function")
def mock_dynamodb_table():
    """Mock DynamoDB table for testing."""
    table = MagicMock()
    
    # Mock common table operations
    table.get_item.return_value = {}
    table.put_item.return_value = {}
    table.update_item.return_value = {}
    table.delete_item.return_value = {}
    table.scan.return_value = {'Items': []}
    table.query.return_value = {'Items': []}
    
    return table

@pytest.fixture(scope="function")
def mock_boto3_resource():
    """Mock boto3 resource for testing."""
    with patch('lambdas.utils.db_utils.boto3.resource') as mock_resource:
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        yield mock_resource

@pytest.fixture(scope="function")
def mock_boto3_client():
    """Mock boto3 client for testing."""
    with patch('lambdas.utils.db_utils.boto3.client') as mock_client:
        yield mock_client

@pytest.fixture(scope="function")
def mock_boto3_client_websocket():
    """Mock boto3 client for websocket utils testing."""
    with patch('lambdas.utils.websocket_utils.boto3.client') as mock_client:
        yield mock_client

@pytest.fixture(scope="function")
def mock_boto3_resource_websocket():
    """Mock boto3 resource for websocket utils testing."""
    with patch('lambdas.utils.websocket_utils.boto3.resource') as mock_resource:
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        yield mock_resource

@pytest.fixture(scope="function")
def sample_jwt_payload():
    """Sample JWT payload for testing."""
    return {
        'user_id': 'test-user-123',
        'email': 'test@example.com',
        'exp': 1735689600,  # Future timestamp
        'iat': 1735603200,  # Past timestamp
        'iss': 'bridge-game-api'
    }

@pytest.fixture(scope="function")
def sample_password():
    """Sample password for testing."""
    return 'TestPassword123!'

@pytest.fixture(scope="function")
def sample_hashed_password():
    """Sample hashed password for testing."""
    return '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/vYzqKqK'

@pytest.fixture(scope="function")
def mock_websocket_connections():
    """Mock WebSocket connections data."""
    return [
        {
            'connectionId': 'conn-1',
            'userId': 'user-1',
            'currentRoomId': 'room-1',
            'status': 'connected',
            'connectedAt': '2023-01-01T00:00:00Z'
        },
        {
            'connectionId': 'conn-2',
            'userId': 'user-2',
            'currentRoomId': 'room-1',
            'status': 'connected',
            'connectedAt': '2023-01-01T00:00:00Z'
        },
        {
            'connectionId': 'conn-3',
            'userId': 'user-3',
            'currentRoomId': 'room-2',
            'status': 'connected',
            'connectedAt': '2023-01-01T00:00:00Z'
        }
    ]

# Test markers for different test categories
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "websocket: mark test as websocket related"
    )
    config.addinivalue_line(
        "markers", "database: mark test as database related"
    )
    config.addinivalue_line(
        "markers", "auth: mark test as authentication related"
    )

# Test collection and execution configuration
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add default markers."""
    for item in items:
        # Add unit marker to all tests by default
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unit)
        
        # Add specific markers based on test file names
        if 'websocket' in item.nodeid:
            item.add_marker(pytest.mark.websocket)
        if 'db_utils' in item.nodeid or 'database' in item.nodeid:
            item.add_marker(pytest.mark.database)
        if 'auth' in item.nodeid:
            item.add_marker(pytest.mark.auth)
