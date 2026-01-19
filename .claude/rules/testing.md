# Testing Rules

Guidelines for writing tests.

## Core Principles

- **TDD recommended**: Write tests first
- **Coverage target**: 80% or higher
- **Execution speed**: Unit tests should be fast (< 100ms per test)

## Test Structure

### AAA Pattern

```python
def test_user_creation():
    # Arrange
    user_data = {"name": "Alice", "email": "alice@example.com"}

    # Act
    user = create_user(user_data)

    # Assert
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
```

### Naming Convention

```python
# test_{target}_{condition}_{expected_result}
def test_create_user_with_valid_data_returns_user():
    ...

def test_create_user_with_invalid_email_raises_error():
    ...
```

## Test Case Coverage

For each feature, consider:

1. **Happy path**: Basic functionality
2. **Boundary values**: Min, max, empty
3. **Error cases**: Invalid input, error conditions
4. **Edge cases**: None, empty string, special characters

## Mocking

Mock external dependencies:

```python
from unittest.mock import Mock, patch

@patch("module.external_api_call")
def test_with_mocked_api(mock_api):
    mock_api.return_value = {"status": "ok"}
    result = function_under_test()
    assert result == expected
```

## Fixtures

Common setup goes in `conftest.py`:

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_user():
    return User(name="Test", email="test@example.com")

@pytest.fixture
def db_session():
    session = create_session()
    yield session
    session.rollback()
```

## Commands

```bash
# All tests
uv run pytest -v

# Specific file
uv run pytest tests/test_user.py -v

# Specific test
uv run pytest tests/test_user.py::test_create_user -v

# With coverage
uv run pytest --cov=src --cov-report=term-missing

# Stop on first failure
uv run pytest -x
```

## Checklist

- [ ] Happy path is tested
- [ ] Error cases are tested
- [ ] Boundary values are tested
- [ ] Tests are independent (no order dependency)
- [ ] External dependencies are mocked
- [ ] Tests run fast
