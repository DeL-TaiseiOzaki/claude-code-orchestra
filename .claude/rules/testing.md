# Testing Rules

Guidelines for writing tests.

## Core Principles

- **TDD recommended**: Write tests first
- **Coverage target**: 80% or higher
- **Execution speed**: Unit tests should be fast (< 100ms per test)

## Test Structure

### AAA Pattern

```php
public function testUserCreation(): void
{
    // Arrange
    $userData = ['name' => 'Alice', 'email' => 'alice@example.com'];

    // Act
    $user = createUser($userData);

    // Assert
    $this->assertSame('Alice', $user->getName());
    $this->assertSame('alice@example.com', $user->getEmail());
}
```

### Naming Convention

```php
// test_{target}_{condition}_{expected_result}
public function testCreateUserWithValidDataReturnsUser(): void
{
    // ...
}

public function testCreateUserWithInvalidEmailThrowsException(): void
{
    // ...
}
```

## Test Case Coverage

For each feature, consider:

1. **Happy path**: Basic functionality
2. **Boundary values**: Min, max, empty
3. **Error cases**: Invalid input, error conditions
4. **Edge cases**: Null, empty string, special characters

## Mocking

Mock external dependencies:

```php
use PHPUnit\Framework\TestCase;

class ServiceTest extends TestCase
{
    public function testWithMockedApi(): void
    {
        $mockApi = $this->createMock(ExternalApi::class);
        $mockApi->method('call')
            ->willReturn(['status' => 'ok']);

        $service = new Service($mockApi);
        $result = $service->process();

        $this->assertSame($expected, $result);
    }
}
```

## Data Providers

Common test data patterns using data providers:

```php
use PHPUnit\Framework\Attributes\DataProvider;

class ValidationTest extends TestCase
{
    public static function validEmailProvider(): array
    {
        return [
            'simple' => ['test@example.com'],
            'with subdomain' => ['user@sub.example.com'],
        ];
    }

    #[DataProvider('validEmailProvider')]
    public function testValidEmail(string $email): void
    {
        $this->assertTrue(isValidEmail($email));
    }
}
```

## Fixtures / setUp

Common setup goes in setUp method:

```php
class UserTest extends TestCase
{
    private User $sampleUser;
    private PDO $dbConnection;

    protected function setUp(): void
    {
        $this->sampleUser = new User('Test', 'test@example.com');
        $this->dbConnection = createTestConnection();
    }

    protected function tearDown(): void
    {
        // Clean up resources
    }
}
```

## Commands

```bash
# All tests
./vendor/bin/phpunit

# Specific file
./vendor/bin/phpunit tests/UserTest.php

# Specific test method
./vendor/bin/phpunit --filter testCreateUser

# With coverage
./vendor/bin/phpunit --coverage-text

# Stop on first failure
./vendor/bin/phpunit --stop-on-failure
```

## Checklist

- [ ] Happy path is tested
- [ ] Error cases are tested
- [ ] Boundary values are tested
- [ ] Tests are independent (no order dependency)
- [ ] External dependencies are mocked
- [ ] Tests run fast
