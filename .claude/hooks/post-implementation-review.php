#!/usr/bin/env php
<?php
/**
 * PostToolUse hook: Suggest Codex review after significant implementations.
 *
 * Tracks file changes and suggests code review when substantial
 * code has been written.
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

// State file to track changes in this session
const STATE_FILE = '/tmp/claude-code-implementation-state.json';

// Thresholds for suggesting review
const MIN_FILES_FOR_REVIEW = 3;
const MIN_LINES_FOR_REVIEW = 100;

function loadState(): array
{
    if (file_exists(STATE_FILE)) {
        $data = json_decode(file_get_contents(STATE_FILE), true);
        if (is_array($data)) {
            return $data;
        }
    }
    return ['files_changed' => [], 'total_lines' => 0, 'review_suggested' => false];
}

function saveState(array $state): void
{
    file_put_contents(STATE_FILE, json_encode($state), LOCK_EX);
}

function countLines(string $content): int
{
    $lines = explode("\n", $content);
    // Count non-empty, non-comment lines
    $meaningful = array_filter($lines, function (string $line): bool {
        $trimmed = trim($line);
        return $trimmed !== '' && !str_starts_with($trimmed, '//') && !str_starts_with($trimmed, '#');
    });
    return count($meaningful);
}

/**
 * Check if we should suggest a code review.
 *
 * @return array{bool, string}
 */
function shouldSuggestReview(array $state): array
{
    if ($state['review_suggested'] ?? false) {
        return [false, ''];
    }

    $filesCount = count($state['files_changed'] ?? []);
    $totalLines = $state['total_lines'] ?? 0;

    if ($filesCount >= MIN_FILES_FOR_REVIEW) {
        return [true, "{$filesCount} files modified"];
    }

    if ($totalLines >= MIN_LINES_FOR_REVIEW) {
        return [true, "{$totalLines}+ lines written"];
    }

    return [false, ''];
}

function main(): void
{
    try {
        $input = file_get_contents('php://stdin');
        $data = json_decode($input, true);
        $toolName = $data['tool_name'] ?? '';

        // Only process Write/Edit tools
        if (!in_array($toolName, ['Write', 'Edit'], true)) {
            exit(0);
        }

        $toolInput = $data['tool_input'] ?? [];
        $filePath = $toolInput['file_path'] ?? '';
        $content = $toolInput['content'] ?? $toolInput['new_string'] ?? '';

        // Validate input
        if (!validateInput($filePath, $content)) {
            exit(0);
        }

        // Skip non-source files
        $sourceExtensions = ['.php', '.ts', '.js', '.tsx', '.jsx', '.go', '.rs'];
        $isSourceFile = false;
        foreach ($sourceExtensions as $ext) {
            if (str_ends_with($filePath, $ext)) {
                $isSourceFile = true;
                break;
            }
        }
        if (!$isSourceFile) {
            exit(0);
        }

        // Load and update state
        $state = loadState();
        if (!in_array($filePath, $state['files_changed'], true)) {
            $state['files_changed'][] = $filePath;
        }
        $state['total_lines'] += countLines($content);
        saveState($state);

        // Check if review should be suggested
        [$shouldReview, $reason] = shouldSuggestReview($state);

        if ($shouldReview) {
            $state['review_suggested'] = true;
            saveState($state);

            $output = [
                'hookSpecificOutput' => [
                    'hookEventName' => 'PostToolUse',
                    'additionalContext' =>
                        "[Code Review Suggestion] {$reason} in this session. "
                        . 'Consider having Codex review the implementation. '
                        . "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        . 'to consult Codex with git diff and preserve main context.',
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
