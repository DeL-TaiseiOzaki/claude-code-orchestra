#!/usr/bin/env php
<?php
/**
 * PostToolUse hook: Log Codex/Gemini CLI input/output to JSONL file.
 *
 * Triggers after Bash tool calls containing 'codex' or 'gemini' commands.
 * Logs are stored in .claude/logs/cli-tools.jsonl
 *
 * All agents (Claude Code, subagents, Codex, Gemini) can read this log.
 */

define('LOG_DIR', dirname(__FILE__) . '/../logs');
define('LOG_FILE', LOG_DIR . '/cli-tools.jsonl');

function extractCodexPrompt(string $command): ?string
{
    // Pattern: codex exec ... "prompt" or codex exec ... 'prompt'
    $patterns = [
        '/codex\s+exec\s+.*?--full-auto\s+"([^"]+)"/s',
        "/codex\s+exec\s+.*?--full-auto\s+'([^']+)'/s",
        '/codex\s+exec\s+.*?"([^"]+)"\s*2>\/dev\/null/s',
        "/codex\s+exec\s+.*?'([^']+)'\s*2>\/dev\/null/s",
    ];
    foreach ($patterns as $pattern) {
        if (preg_match($pattern, $command, $matches)) {
            return trim($matches[1]);
        }
    }
    return null;
}

function extractGeminiPrompt(string $command): ?string
{
    // Pattern: gemini -p "prompt" or gemini -p 'prompt'
    $patterns = [
        '/gemini\s+-p\s+"([^"]+)"/s',
        "/gemini\s+-p\s+'([^']+)'/s",
    ];
    foreach ($patterns as $pattern) {
        if (preg_match($pattern, $command, $matches)) {
            return trim($matches[1]);
        }
    }
    return null;
}

function extractModel(string $command): ?string
{
    if (preg_match('/--model\s+(\S+)/', $command, $matches)) {
        return $matches[1];
    }
    return null;
}

function truncateText(string $text, int $maxLength = 2000): string
{
    if (mb_strlen($text) <= $maxLength) {
        return $text;
    }
    $totalChars = mb_strlen($text);
    return mb_substr($text, 0, $maxLength) . "... [truncated, {$totalChars} total chars]";
}

function logEntry(array $entry): void
{
    if (!is_dir(LOG_DIR)) {
        mkdir(LOG_DIR, 0755, true);
    }
    file_put_contents(
        LOG_FILE,
        json_encode($entry, JSON_UNESCAPED_UNICODE) . "\n",
        FILE_APPEND | LOCK_EX
    );
}

function main(): void
{
    // Read hook input from stdin
    $rawInput = file_get_contents('php://stdin');
    $hookInput = json_decode($rawInput, true);
    if ($hookInput === null) {
        return;
    }

    // Only process Bash tool calls
    $toolName = $hookInput['tool_name'] ?? '';
    if ($toolName !== 'Bash') {
        return;
    }

    // Get command and output
    $toolInput = $hookInput['tool_input'] ?? [];
    $toolResponse = $hookInput['tool_response'] ?? [];

    $command = $toolInput['command'] ?? '';
    $output = $toolResponse['stdout'] ?? $toolResponse['content'] ?? '';

    // Check if this is a codex or gemini command
    $commandLower = strtolower($command);
    $isCodex = str_contains($commandLower, 'codex');
    $isGemini = str_contains($commandLower, 'gemini') && !str_contains($commandLower, 'codex');

    if (!$isCodex && !$isGemini) {
        return;
    }

    // Extract prompt based on tool type
    if ($isCodex) {
        $tool = 'codex';
        $prompt = extractCodexPrompt($command);
        $model = extractModel($command) ?? 'gpt-5.2-codex';
    } else {
        $tool = 'gemini';
        $prompt = extractGeminiPrompt($command);
        $model = 'gemini-3-pro-preview';
    }

    if ($prompt === null) {
        // Could not extract prompt, skip logging
        return;
    }

    // Determine success
    $exitCode = $toolResponse['exit_code'] ?? 0;
    $success = $exitCode === 0 && !empty($output);

    // Create log entry
    $entry = [
        'timestamp' => gmdate('c'),
        'tool' => $tool,
        'model' => $model,
        'prompt' => truncateText($prompt),
        'response' => $output ? truncateText($output) : '',
        'success' => $success,
        'exit_code' => $exitCode,
    ];

    logEntry($entry);

    // Output notification (shown to user via hook output)
    echo json_encode([
        'result' => 'continue',
        'message' => "[LOG] " . ucfirst($tool) . " call logged to .claude/logs/cli-tools.jsonl",
    ]) . "\n";
}

main();
