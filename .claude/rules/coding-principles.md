# Coding Principles

Core coding rules to always follow.

## Simplicity First

- Choose readable code over complex code
- Avoid over-abstraction
- Prioritize "understandable" over "working"

## Single Responsibility

- One function does one thing only
- One class has one responsibility only
- Target 200-400 lines per file (max 800)

## Early Return

```php
// Bad: Deep nesting
function process(?int $value): ?Result
{
    if ($value !== null) {
        if ($value > 0) {
            return doSomething($value);
        }
    }
    return null;
}

// Good: Early return
function process(?int $value): ?Result
{
    if ($value === null) {
        return null;
    }
    if ($value <= 0) {
        return null;
    }
    return doSomething($value);
}
```

## Type Declarations Required

All functions must have parameter and return type declarations:

```php
function callLlm(
    string $prompt,
    string $model = 'gpt-4',
    int $maxTokens = 1000
): string {
    // ...
}
```

## Immutability

Create new data instead of mutating existing objects:

```php
// Bad: Mutating existing array
$data['new_key'] = $value;

// Good: Creating new array
$newData = [...$data, 'new_key' => $value];
```

## Naming Conventions

- **Variables/Functions**: camelCase (English)
- **Classes**: PascalCase (English)
- **Constants**: UPPER_SNAKE_CASE (English)
- **Meaningful names**: `$userCount` over `$x`

## No Magic Numbers

```php
// Bad
if ($retryCount > 3) {
    // ...
}

// Good
const MAX_RETRIES = 3;
if ($retryCount > MAX_RETRIES) {
    // ...
}
```
