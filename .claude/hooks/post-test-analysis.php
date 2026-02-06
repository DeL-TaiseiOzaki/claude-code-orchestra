#!/usr/bin/env php
<?php
/**
 * PostToolUse hook: Suggest Codex analysis after test/build failures.
 *
 * Analyzes test and build output and suggests Codex consultation
 * for debugging complex failures.
 */

// Commands that run tests or builds
const TEST_BUILD_COMMANDS = [
    'phpunit',
    'pest',
    'composer test',
    'npm test',
    'npm run test',
    'npm run build',
    'phpstan',
    'php-cs-fixer',
    'psalm',
    'tsc',
    'cargo test',
    'go test',
    'make test',
    'make build',
];

// Patterns indicating failures that need debugging
const FAILURE_PATTERNS = [
    '/FAILED/',
    '/ERROR/',
    '/error\\[/',
    '/Error:/',
    '/failed/',
    '/error:/',
    '/Fatal error/',
    '/TypeError/',
    '/ValueError/',
    '/Exception/',
    '/Stack trace/',
    '/PHPUnit\\\\Framework\\\\/',
    '/FAILURES!/',
    '/Tests:.*failures/',
    '/panic:/',
    '/FAIL:/',
];

// Simple errors that don't need Codex
const SIMPLE_ERRORS = [
    'Class not found',
    'command not found',
    'No such file or directory',
];

function isTestOrBuildCommand(string $command): bool
{
    $commandLower = strtolower($command);
    foreach (TEST_BUILD_COMMANDS as $cmd) {
        if (str_contains($commandLower, $cmd)) {
            return true;
        }
    }
    return false;
}

/**
 * Check if output contains complex failures that need debugging.
 *
 * @return array{bool, string}
 */
function hasComplexFailure(string $output): array
{
    // Skip if it's a simple error
    foreach (SIMPLE_ERRORS as $simple) {
        if (str_contains($output, $simple)) {
            return [false, ''];
        }
    }

    // Count failure patterns
    $failureCount = 0;
    foreach (FAILURE_PATTERNS as $pattern) {
        $matches = [];
        if (preg_match_all($pattern . 'i', $output, $matches)) {
            $failureCount += count($matches[0]);
        }
    }

    // Multiple failures or complex errors suggest need for Codex
    if ($failureCount >= 3) {
        return [true, "Multiple failures detected ({$failureCount} issues)"];
    }

    // Single failure in test output
    $outputLower = strtolower($output);
    if ($failureCount >= 1 && (str_contains($outputLower, 'stack trace') || str_contains($outputLower, 'assertion'))) {
        return [true, 'Test failure with stack trace'];
    }

    return [false, ''];
}

function main(): void
{
    try {
        $input = file_get_contents('php://stdin');
        $data = json_decode($input, true);
        $toolName = $data['tool_name'] ?? '';

        // Only process Bash tool
        if ($toolName !== 'Bash') {
            exit(0);
        }

        $toolInput = $data['tool_input'] ?? [];
        $toolOutput = $data['tool_output'] ?? '';
        $command = $toolInput['command'] ?? '';

        // Check if it's a test/build command
        if (!isTestOrBuildCommand($command)) {
            exit(0);
        }

        // Check for complex failures
        [$hasFailure, $reason] = hasComplexFailure($toolOutput);

        if ($hasFailure) {
            $output = [
                'hookSpecificOutput' => [
                    'hookEventName' => 'PostToolUse',
                    'additionalContext' =>
                        "[Codex Debug Suggestion] {$reason}. "
                        . 'Consider consulting Codex for debugging analysis. '
                        . "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        . 'to consult Codex with full error context and preserve main context.',
                ],
            ];
            echo json_encode($output) . "\n";
        }

        exit(0);

    } catch (\Throwable $e) {
        fwrite(STDERR, "Hook error: {$e->getMessage()}\n");
        exit(0);
    }
}

main();
