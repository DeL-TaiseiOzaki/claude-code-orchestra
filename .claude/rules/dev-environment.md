# Development Environment

Project development environment and toolchain.

## Package Management: Composer

**All dependency management must go through Composer.**

```bash
# Add packages
composer require <package>
composer require --dev <package>    # Dev dependency

# Install dependencies
composer install

# Update dependencies
composer update

# Run scripts
composer <script-name>
```

### composer.json

Manage dependencies in `composer.json`:

```json
{
    "require": {
        "php": ">=8.2"
    },
    "require-dev": {
        "phpunit/phpunit": "^11.0",
        "phpstan/phpstan": "^2.0",
        "friendsofphp/php-cs-fixer": "^3.0"
    }
}
```

## Code Formatting: PHP-CS-Fixer

```bash
# Check (dry run)
./vendor/bin/php-cs-fixer fix --dry-run --diff

# Auto-fix
./vendor/bin/php-cs-fixer fix
```

### PHP-CS-Fixer Configuration (.php-cs-fixer.dist.php)

```php
<?php

$finder = (new PhpCsFixer\Finder())
    ->in(__DIR__ . '/src')
    ->in(__DIR__ . '/tests');

return (new PhpCsFixer\Config())
    ->setRules([
        '@PER-CS' => true,
        'strict_types' => true,
        'array_syntax' => ['syntax' => 'short'],
        'no_unused_imports' => true,
        'ordered_imports' => ['sort_algorithm' => 'alpha'],
    ])
    ->setFinder($finder)
    ->setRiskyAllowed(true);
```

## Static Analysis: PHPStan

```bash
# Run analysis
./vendor/bin/phpstan analyse src/

# With specific level (0-9, max is strictest)
./vendor/bin/phpstan analyse src/ --level=max
```

### PHPStan Configuration (phpstan.neon)

```neon
parameters:
    level: max
    paths:
        - src
    tmpDir: .phpstan-cache
```

## Testing: PHPUnit

```bash
# Run all tests
./vendor/bin/phpunit

# Run specific test file
./vendor/bin/phpunit tests/UserTest.php

# Run with coverage
./vendor/bin/phpunit --coverage-text
```

### PHPUnit Configuration (phpunit.xml)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<phpunit xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:noNamespaceSchemaLocation="vendor/phpunit/phpunit/phpunit.xsd"
         bootstrap="vendor/autoload.php"
         colors="true">
    <testsuites>
        <testsuite name="Unit">
            <directory>tests</directory>
        </testsuite>
    </testsuites>
    <source>
        <include>
            <directory>src</directory>
        </include>
    </source>
</phpunit>
```

## Composer Scripts

Manage task execution in `composer.json` scripts:

```json
{
    "scripts": {
        "lint": ["@cs-check", "@phpstan"],
        "cs-check": "php-cs-fixer fix --dry-run --diff",
        "cs-fix": "php-cs-fixer fix",
        "phpstan": "phpstan analyse src/ --no-progress",
        "test": "phpunit",
        "all": ["@lint", "@test"]
    }
}
```

## Common Commands

```bash
# Initialize
composer init
composer install

# Quality check (all)
./vendor/bin/php-cs-fixer fix --dry-run --diff && ./vendor/bin/phpstan analyse src/ && ./vendor/bin/phpunit

# Or via composer scripts
composer all
```

## Pre-commit Checklist

- [ ] `composer cs-check` passes
- [ ] `composer phpstan` passes
- [ ] `composer test` passes
