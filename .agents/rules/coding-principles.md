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

```python
# Bad: Deep nesting
def process(value):
    if value is not None:
        if value > 0:
            return do_something(value)
    return None

# Good: Early return
def process(value):
    if value is None:
        return None
    if value <= 0:
        return None
    return do_something(value)
```

## Type Hints Required

All functions must have type annotations:

```python
def call_llm(
    prompt: str,
    model: str = "gpt-4",
    max_tokens: int = 1000
) -> str:
    ...
```

## Immutability

Create new objects instead of mutating existing ones:

```python
# Bad: Mutating existing object
data["new_key"] = value

# Good: Creating new object
new_data = {**data, "new_key": value}
```

## Naming Conventions

- **Variables/Functions**: snake_case (English)
- **Classes**: PascalCase (English)
- **Constants**: UPPER_SNAKE_CASE (English)
- **Meaningful names**: `user_count` over `x`

## No Magic Numbers

```python
# Bad
if retry_count > 3:
    ...

# Good
MAX_RETRIES = 3
if retry_count > MAX_RETRIES:
    ...
```
