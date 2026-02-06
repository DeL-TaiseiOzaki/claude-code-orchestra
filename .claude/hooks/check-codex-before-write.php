#!/usr/bin/env php
<?php
/**
 * PreToolUse hook: Check if Codex consultation is recommended before Write/Edit.
 *
 * This hook analyzes the file being modified and suggests Codex consultation
 * for design decisions, complex implementations, or architectural changes.
 */

// Input validation constants
const MAX_PATH_LENGTH = 4096;
const MAX_CONTENT_LENGTH = 1_000_000;

function validateInput(string $filePath, string $content): bool
{
    if (empty($filePath) || strlen($filePath) > MAX_PATH_LENGTH) {
        return false;
    }
    if (strlen($content) > MAX_CONTENT_LENGTH) {
        return false;
    }
    // Check for path traversal
    if (str_contains($filePath, '..')) {
        return false;
    }
    return true;
}

// Patterns that suggest design/architecture decisions
const DESIGN_INDICATORS = [
    // File patterns
    'DESIGN.md',
    'ARCHITECTURE.md',
    'architecture',
    'design',
    'schema',
    'model',
    'interface',
    'abstract',
    'base_',
    'core/',
    '/core/',
    'config',
    'settings',

    // Code patterns in content
    'class ',
    'interface ',
    'abstract class',
    '__construct',
    'implements',
    'extends',
    'readonly class',
    'enum ',
];

// Files that are typically simple edits (skip suggestion)
const SIMPLE_EDIT_PATTERNS = [
    '.gitignore',
    'README.md',
    'CHANGELOG.md',
    'composer.json',
    '.env.example',
];

/**
 * Determine if Codex consultation should be suggested.
 *
 * @return array{bool, string}
 */
function shouldSuggestCodex(string $filePath, ?string $content = null): array
{
    $filePathLower = strtolower($filePath);

    // Skip simple edits
    foreach (SIMPLE_EDIT_PATTERNS as $pattern) {
        if (str_contains($filePathLower, strtolower($pattern))) {
            return [false, ''];
        }
    }

    // Check file path for design indicators
    foreach (DESIGN_INDICATORS as $indicator) {
        if (str_contains($filePathLower, strtolower($indicator))) {
            return [true, "File path contains '{$indicator}' - likely a design decision"];
        }
    }

    // Check content if available
    if ($content !== null) {
        // New file with significant content
        if (strlen($content) > 500) {
            return [true, 'Creating new file with significant content'];
        }

        // Check for design patterns in content
        foreach (DESIGN_INDICATORS as $indicator) {
            if (str_contains($content, $indicator)) {
                return [true, "Content contains '{$indicator}' - likely architectural code"];
            }
        }
    }

    // New files in src/ directory
    if (str_contains($filePath, '/src/') || str_starts_with($filePath, 'src/')) {
        if ($content !== null && strlen($content) > 200) {
            return [true, 'New source file - consider design review'];
        }
    }

    return [false, ''];
}

function main(): void
{
    try {
        $input = file_get_contents('php://stdin');
        $data = json_decode($input, true);
        $toolInput = $data['tool_input'] ?? [];
        $filePath = $toolInput['file_path'] ?? '';
        $content = $toolInput['content'] ?? $toolInput['new_string'] ?? '';

        // Validate input
        if (!validateInput($filePath, $content)) {
            exit(0);
        }

        [$shouldSuggest, $reason] = shouldSuggestCodex($filePath, $content);

        if ($shouldSuggest) {
            // Return additional context to Claude
            $output = [
                'hookSpecificOutput' => [
                    'hookEventName' => 'PreToolUse',
                    'additionalContext' =>
                        "[Codex Consultation Reminder] {$reason}. "
                        . 'Consider consulting Codex before making this change. '
                        . "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        . 'to preserve main context. '
                        . '(Direct call OK for quick questions: '
                        . "`codex exec --model gpt-5.2-codex --sandbox read-only --full-auto '...'`)",
                ],
            ];
            echo json_encode($output) . "\n";
        }

        exit(0); // Always allow, just add context

    } catch (\Throwable $e) {
        // Don't block on errors
        fwrite(STDERR, "Hook error: {$e->getMessage()}\n");
        exit(0);
    }
}

main();
