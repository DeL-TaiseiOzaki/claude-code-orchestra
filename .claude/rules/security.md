# Security Rules

Security checklist to always verify when writing code.

## Secrets Management

### Never Do

- Hardcode API keys or passwords
- Log sensitive information
- Commit `.env` files

### Required

```php
// Good: Get from environment variables
$apiKey = getenv('API_KEY');

// Good: With existence check
$apiKey = getenv('API_KEY');
if ($apiKey === false) {
    throw new RuntimeException('API_KEY environment variable is required');
}
```

## Input Validation

Always validate external input:

```php
// Using strict type declarations and validation
function createUser(string $email, int $age, string $name): User
{
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
        throw new InvalidArgumentException('Invalid email');
    }
    if ($age < 0 || $age > 150) {
        throw new InvalidArgumentException('Age must be between 0 and 150');
    }
    if (strlen($name) < 1 || strlen($name) > 100) {
        throw new InvalidArgumentException('Name must be between 1 and 100 characters');
    }
    return new User($email, $age, $name);
}
```

## SQL Injection Prevention

```php
// Bad: String concatenation
$stmt = $pdo->query("SELECT * FROM users WHERE id = {$userId}");

// Good: Prepared statement
$stmt = $pdo->prepare('SELECT * FROM users WHERE id = :id');
$stmt->execute(['id' => $userId]);
```

## XSS Prevention

- Escape user input before embedding in HTML
- Use `htmlspecialchars()` with `ENT_QUOTES` flag
- Enable template engine auto-escaping (Twig, Blade)

```php
// Always escape output
echo htmlspecialchars($userInput, ENT_QUOTES, 'UTF-8');
```

## Error Messages

```php
// Bad: Too detailed (gives attackers information)
throw new Exception("Database connection failed: {$connectionString}");

// Good: Minimal information
throw new Exception('Database connection failed');
// Details go to logs (logs are private)
error_log("Database connection failed: {$connectionString}");
```

## Dependencies

- Regular vulnerability checks: `composer audit`
- Remove unused dependencies
- Pin versions in `composer.lock`

## Code Review Checklist

- [ ] No hardcoded secrets
- [ ] External input is validated
- [ ] SQL queries use prepared statements
- [ ] Error messages are not too detailed
- [ ] Logs don't contain sensitive information
