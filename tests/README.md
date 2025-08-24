# Testing Guide for BridgeLambdas

This directory contains the comprehensive test suite for the BridgeLambdas project. The tests are designed to ensure code quality, reliability, and maintainability.

## 🏗️ Test Structure

```
tests/
├── conftest.py                 # Pytest configuration and shared fixtures
├── test_db_utils.py           # Database utilities tests
├── test_websocket_utils.py    # WebSocket utilities tests
├── test_websocket_start_room.py # WebSocket start room lambda tests
├── test_auth_utils.py         # Authentication utilities tests
├── test_room_create.py        # Room creation tests
├── test_room_join.py          # Room joining tests
├── test_room_start.py         # Room starting tests
├── test_seat_filtering.py     # Seat filtering tests
├── test_connection_count.py   # Connection counting tests
├── test_account_login.py      # Account login tests
├── test_account_create.py     # Account creation tests
└── README.md                  # This file
```

## 🚀 Quick Start

### 1. Install Test Dependencies

```bash
# Install testing dependencies
pip install -r requirements-test.txt

# Or use the test runner
python run_tests.py --install
```

### 2. Run All Tests

```bash
# Run all tests
python run_tests.py

# Or use pytest directly
pytest tests/
```

### 3. Run Specific Test Categories

```bash
# Run only unit tests
python run_tests.py --unit

# Run only WebSocket tests
python run_tests.py --websocket

# Run only database tests
python run_tests.py --database

# Run only authentication tests
python run_tests.py --auth
```

## 🧪 Test Categories

### Unit Tests (`--unit`)
- Test individual functions and methods in isolation
- Use mocking to isolate dependencies
- Fast execution, high reliability
- Marked with `@pytest.mark.unit`

### Integration Tests (`--integration`)
- Test interactions between components
- May use real or mocked external services
- Slower execution, tests real workflows
- Marked with `@pytest.mark.integration`

### WebSocket Tests (`--websocket`)
- Test WebSocket-related functionality
- Mock API Gateway and DynamoDB
- Test real-time communication flows
- Marked with `@pytest.mark.websocket`

### Database Tests (`--database`)
- Test database operations and utilities
- Mock DynamoDB responses
- Test data persistence and retrieval
- Marked with `@pytest.mark.database`

### Authentication Tests (`--auth`)
- Test JWT token handling
- Test password hashing and verification
- Test authentication middleware
- Marked with `@pytest.mark.auth`

## 🛠️ Test Runner Options

The `run_tests.py` script provides a convenient way to run different types of tests:

```bash
# Basic usage
python run_tests.py                    # Run all tests
python run_tests.py --verbose         # Verbose output
python run_tests.py --coverage        # With coverage report

# Specific test types
python run_tests.py --unit            # Unit tests only
python run_tests.py --websocket      # WebSocket tests only
python run_tests.py --database       # Database tests only
python run_tests.py --auth           # Authentication tests only

# Specific files
python run_tests.py --file tests/test_db_utils.py

# Code quality
python run_tests.py --lint            # Run flake8
python run_tests.py --format          # Format with black
python run_tests.py --coverage-only   # Show coverage only
```

## 📊 Coverage Reports

Generate coverage reports to see how well your code is tested:

```bash
# Run tests with coverage
python run_tests.py --coverage

# Generate HTML coverage report
pytest --cov=lambdas --cov-report=html tests/
```

Coverage reports will be generated in the `htmlcov/` directory.

## 🔧 Test Configuration

### Pytest Configuration (`pytest.ini`)
- **Strict markers**: Ensures all tests are properly categorized
- **Short tracebacks**: Cleaner test output
- **Warning suppression**: Reduces noise from deprecation warnings
- **Verbose output**: More detailed test information

### Shared Fixtures (`conftest.py`)
- **AWS credentials**: Mocked AWS credentials for testing
- **Environment variables**: Test environment setup
- **Sample data**: Common test data structures
- **Mock objects**: Reusable mocks for external services

## 🎯 Testing Best Practices

### 1. Test Organization
- Group related tests in classes
- Use descriptive test names
- Follow the Arrange-Act-Assert pattern

### 2. Mocking Strategy
- Mock external dependencies (AWS services, databases)
- Use fixtures for common mock setups
- Verify mock interactions when relevant

### 3. Test Data
- Use fixtures for sample data
- Create realistic but minimal test scenarios
- Avoid hardcoded values in tests

### 4. Error Handling
- Test both success and failure scenarios
- Verify error messages and status codes
- Test edge cases and boundary conditions

## 🚨 Common Test Patterns

### Testing Lambda Functions
```python
def test_lambda_handler_success(mock_event, mock_context):
    """Test successful lambda execution."""
    response = lambda_function.handler(mock_event, mock_context)
    
    assert response['statusCode'] == 200
    assert 'body' in response
    
    body = json.loads(response['body'])
    assert body['success'] is True
```

### Testing Database Operations
```python
def test_database_operation(mock_dynamodb_table):
    """Test database operation with mocked table."""
    mock_dynamodb_table.get_item.return_value = {
        'Item': {'id': 'test-123', 'data': 'test-data'}
    }
    
    result = db_utils.get_item('test-123', mock_dynamodb_table)
    
    assert result['id'] == 'test-123'
    mock_dynamodb_table.get_item.assert_called_once()
```

### Testing WebSocket Broadcasting
```python
def test_broadcast_message(mock_apigateway, sample_message):
    """Test WebSocket message broadcasting."""
    connection_ids = ['conn-1', 'conn-2']
    
    result = broadcast_to_connections(connection_ids, sample_message)
    
    assert result['success'] == 2
    assert result['failed'] == 0
    assert mock_apigateway.post_to_connection.call_count == 2
```

## 🔍 Debugging Tests

### Verbose Output
```bash
pytest -v tests/
python run_tests.py --verbose
```

### Debug Specific Test
```bash
# Run with print statements
pytest -s tests/test_specific.py::test_function

# Run with debugger
pytest --pdb tests/test_specific.py::test_function
```

### Test Discovery
```bash
# List all tests without running
pytest --collect-only tests/

# Show test structure
pytest --collect-only --tb=no tests/
```

## 📈 Continuous Integration

The test suite is designed to work with CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Tests
  run: |
    pip install -r requirements-test.txt
    python run_tests.py --coverage

- name: Upload Coverage
  uses: codecov/codecov-action@v3
```

## 🐛 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're running from the project root
2. **Missing Dependencies**: Install requirements with `pip install -r requirements-test.txt`
3. **Mock Issues**: Check that mocks are properly configured in fixtures
4. **Environment Variables**: Verify test environment setup in `conftest.py`

### Getting Help

- Check test output for specific error messages
- Use `--verbose` flag for more detailed information
- Review fixture configurations in `conftest.py`
- Ensure all dependencies are properly installed

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Mock Documentation](https://pytest-mock.readthedocs.io/)
- [AWS Testing with Moto](https://github.com/spulec/moto)
- [Python Testing Best Practices](https://realpython.com/python-testing/)

## 🤝 Contributing

When adding new tests:

1. Follow the existing naming conventions
2. Use appropriate test markers
3. Add comprehensive test coverage
4. Update this README if adding new test categories
5. Ensure tests pass before submitting

---

**Happy Testing! 🎉**
