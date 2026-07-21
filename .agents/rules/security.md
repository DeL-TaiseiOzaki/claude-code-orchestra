# Security Rules

Security checklist to always verify when writing code.

## Secrets Management

### Never Do

- Hardcode API keys or passwords
- Log sensitive information
- Commit `.env` files

### Required

```python
# Good: Get from environment variables
import os
API_KEY = os.environ["API_KEY"]

# Good: With existence check
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable is required")
```

## Input Validation

Always validate external input:

```python
from pydantic import BaseModel, EmailStr, Field

class UserInput(BaseModel):
    email: EmailStr
    age: int = Field(ge=0, le=150)
    name: str = Field(min_length=1, max_length=100)
```

## SQL Injection Prevention

```python
# Bad: String concatenation
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# Good: Parameterized query
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

## XSS Prevention

- Escape user input before embedding in HTML
- Enable template engine auto-escaping

## Error Messages

```python
# Bad: Too detailed (gives attackers information)
raise Exception(f"Database connection failed: {connection_string}")

# Good: Minimal information
raise Exception("Database connection failed")
# Details go to logs (logs are private)
logger.error(f"Database connection failed: {connection_string}")
```

## Dependencies

- Regular vulnerability checks: `pip-audit`, `safety`
- Remove unused dependencies
- Pin versions (`==` over `>=`)

## Code Review Checklist

- [ ] No hardcoded secrets
- [ ] External input is validated
- [ ] SQL queries are parameterized
- [ ] Error messages are not too detailed
- [ ] Logs don't contain sensitive information
