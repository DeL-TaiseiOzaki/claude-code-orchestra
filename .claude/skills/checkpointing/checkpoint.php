#!/usr/bin/env php
<?php
/**
 * Checkpoint script: Read CLI logs and update agent context files.
 *
 * Usage:
 *     php checkpoint.php [--since YYYY-MM-DD]           # Session history mode
 *     php checkpoint.php --full [--since YYYY-MM-DD]    # Full checkpoint mode
 *     php checkpoint.php --full --analyze               # Full checkpoint + skill analysis
 *
 * Session History Mode (default):
 *     Updates CLAUDE.md, .codex/AGENTS.md, .gemini/GEMINI.md with CLI consultation history.
 *
 * Full Checkpoint Mode (--full):
 *     Creates comprehensive checkpoint file in .claude/checkpoints/ including:
 *     - Git commits and file changes
 *     - CLI tool consultations (Codex/Gemini)
 *     - Design decisions changes
 *     - Session summary
 *
 * Analyze Mode (--full --analyze):
 *     After creating checkpoint, outputs a prompt for AI analysis to extract
 *     reusable skill patterns. Use with subagent to analyze and suggest new skills.
 */

define('PROJECT_ROOT', dirname(__FILE__, 4));
define('LOG_FILE_PATH', PROJECT_ROOT . '/.claude/logs/cli-tools.jsonl');
define('CHECKPOINTS_DIR', PROJECT_ROOT . '/.claude/checkpoints');
define('DESIGN_FILE', PROJECT_ROOT . '/.claude/docs/DESIGN.md');

$contextFiles = [
    'claude' => PROJECT_ROOT . '/CLAUDE.md',
    'codex' => PROJECT_ROOT . '/.codex/AGENTS.md',
    'gemini' => PROJECT_ROOT . '/.gemini/GEMINI.md',
];

const SESSION_HISTORY_HEADER = '## Session History';

function parseLogs(?string $since = null): array
{
    if (!file_exists(LOG_FILE_PATH)) {
        return [];
    }

    $entries = [];
    $sinceDt = null;
    if ($since !== null) {
        $sinceDt = new DateTimeImmutable($since, new DateTimeZone('UTC'));
    }

    $handle = fopen(LOG_FILE_PATH, 'r');
    if ($handle === false) {
        return [];
    }

    while (($line = fgets($handle)) !== false) {
        $line = trim($line);
        if (empty($line)) {
            continue;
        }
        $entry = json_decode($line, true);
        if ($entry === null) {
            continue;
        }
        if ($sinceDt !== null) {
            $timestamp = $entry['timestamp'] ?? '';
            if (empty($timestamp)) {
                continue;
            }
            $entryDt = new DateTimeImmutable(str_replace('Z', '+00:00', $timestamp));
            if ($entryDt < $sinceDt) {
                continue;
            }
        }
        $entries[] = $entry;
    }
    fclose($handle);

    return $entries;
}

function runGitCommand(array $args): ?string
{
    $cmd = array_merge(['git'], $args);
    $process = proc_open(
        $cmd,
        [
            1 => ['pipe', 'w'],
            2 => ['pipe', 'w'],
        ],
        $pipes,
        PROJECT_ROOT
    );

    if (!is_resource($process)) {
        return null;
    }

    $stdout = stream_get_contents($pipes[1]);
    fclose($pipes[1]);
    fclose($pipes[2]);

    $returnCode = proc_close($process);
    if ($returnCode === 0) {
        return trim($stdout);
    }
    return null;
}

function getGitCommits(?string $since = null): array
{
    $args = ['log', '--pretty=format:%H|%ai|%s', '-n', '100'];
    if ($since !== null) {
        $args[] = '--since';
        $args[] = $since;
    }

    $output = runGitCommand($args);
    if ($output === null || $output === '') {
        return [];
    }

    $commits = [];
    foreach (explode("\n", $output) as $line) {
        if (empty($line)) {
            continue;
        }
        $parts = explode('|', $line, 3);
        if (count($parts) === 3) {
            $commits[] = [
                'hash' => substr($parts[0], 0, 7),
                'date' => $parts[1],
                'message' => $parts[2],
            ];
        }
    }
    return $commits;
}

/**
 * @return array{created: string[], modified: string[], deleted: string[]}
 */
function getFileChanges(?string $since = null): array
{
    $changes = ['created' => [], 'modified' => [], 'deleted' => []];

    if ($since !== null) {
        $args = ['log', '--since', $since, '--name-status', '--pretty=format:'];
    } else {
        $args = ['diff', '--name-status', 'HEAD~10', 'HEAD'];
    }

    $output = runGitCommand($args);
    if ($output === null || $output === '') {
        return $changes;
    }

    $seen = [];
    foreach (explode("\n", $output) as $line) {
        $line = trim($line);
        if (empty($line) || !str_contains($line, "\t")) {
            continue;
        }

        $parts = explode("\t", $line, 2);
        if (count($parts) !== 2) {
            continue;
        }

        [$status, $filepath] = $parts;
        if (isset($seen[$filepath])) {
            continue;
        }
        $seen[$filepath] = true;

        if (str_starts_with($status, 'A')) {
            $changes['created'][] = $filepath;
        } elseif (str_starts_with($status, 'M')) {
            $changes['modified'][] = $filepath;
        } elseif (str_starts_with($status, 'D')) {
            $changes['deleted'][] = $filepath;
        }
    }

    return $changes;
}

/**
 * @return array<string, array{int, int}>
 */
function getFileStats(?string $since = null): array
{
    if ($since !== null) {
        $args = ['log', '--since', $since, '--numstat', '--pretty=format:'];
    } else {
        $args = ['diff', '--numstat', 'HEAD~10', 'HEAD'];
    }

    $output = runGitCommand($args);
    if ($output === null || $output === '') {
        return [];
    }

    $stats = [];
    foreach (explode("\n", $output) as $line) {
        $line = trim($line);
        if (empty($line)) {
            continue;
        }

        $parts = explode("\t", $line);
        if (count($parts) !== 3) {
            continue;
        }

        [$added, $deleted, $filepath] = $parts;
        $addCount = $added === '-' ? 0 : (int) $added;
        $delCount = $deleted === '-' ? 0 : (int) $deleted;

        if (isset($stats[$filepath])) {
            $prev = $stats[$filepath];
            $stats[$filepath] = [$prev[0] + $addCount, $prev[1] + $delCount];
        } else {
            $stats[$filepath] = [$addCount, $delCount];
        }
    }

    return $stats;
}

/**
 * @return array<string, array<string, array>>
 */
function summarizeEntries(array $entries): array
{
    $byDate = [];

    foreach ($entries as $entry) {
        $ts = $entry['timestamp'] ?? '';
        $date = $ts ? substr($ts, 0, 10) : 'unknown';
        $tool = $entry['tool'] ?? 'unknown';

        if (!isset($byDate[$date])) {
            $byDate[$date] = ['codex' => [], 'gemini' => []];
        }

        if (isset($byDate[$date][$tool])) {
            $byDate[$date][$tool][] = [
                'prompt' => mb_substr($entry['prompt'] ?? '', 0, 200),
                'response_preview' => mb_substr($entry['response'] ?? '', 0, 300),
                'success' => $entry['success'] ?? false,
            ];
        }
    }

    return $byDate;
}

function generateSessionHistory(array $byDate): string
{
    if (empty($byDate)) {
        return '';
    }

    $lines = [SESSION_HISTORY_HEADER, ''];

    $dates = array_keys($byDate);
    rsort($dates);

    foreach ($dates as $date) {
        $lines[] = "### {$date}";
        $lines[] = '';

        $data = $byDate[$date];

        if (!empty($data['codex'])) {
            $lines[] = '**Codex相談:**';
            foreach (array_slice($data['codex'], 0, 5) as $item) {
                $promptSummary = str_replace("\n", ' ', mb_substr($item['prompt'], 0, 100));
                $status = $item['success'] ? '✓' : '✗';
                $lines[] = "- {$status} {$promptSummary}...";
            }
            $lines[] = '';
        }

        if (!empty($data['gemini'])) {
            $lines[] = '**Gemini調査:**';
            foreach (array_slice($data['gemini'], 0, 5) as $item) {
                $promptSummary = str_replace("\n", ' ', mb_substr($item['prompt'], 0, 100));
                $status = $item['success'] ? '✓' : '✗';
                $lines[] = "- {$status} {$promptSummary}...";
            }
            $lines[] = '';
        }
    }

    return implode("\n", $lines);
}

function updateContextFile(string $filePath, string $sessionHistory): bool
{
    if (!file_exists($filePath)) {
        echo "Warning: {$filePath} does not exist, skipping\n";
        return false;
    }

    $content = file_get_contents($filePath);

    // Remove existing session history section
    $pattern = '/' . preg_quote(SESSION_HISTORY_HEADER, '/') . '.*/s';
    $content = preg_replace($pattern, '', $content);
    $content = rtrim($content) . "\n\n";

    // Append new session history
    $content .= $sessionHistory;

    file_put_contents($filePath, $content);
    return true;
}

function generateFullCheckpoint(?string $since = null): ?string
{
    $timestamp = gmdate('Y-m-d-His');
    $checkpointFile = CHECKPOINTS_DIR . "/{$timestamp}.md";

    // Ensure checkpoints directory exists
    if (!is_dir(CHECKPOINTS_DIR)) {
        mkdir(CHECKPOINTS_DIR, 0755, true);
    }

    // Gather data
    $entries = parseLogs($since);
    $commits = getGitCommits($since);
    $fileChanges = getFileChanges($since);
    $fileStats = getFileStats($since);

    // Count CLI consultations
    $codexCount = count(array_filter($entries, fn($e) => ($e['tool'] ?? '') === 'codex'));
    $geminiCount = count(array_filter($entries, fn($e) => ($e['tool'] ?? '') === 'gemini'));

    // Build checkpoint content
    $lines = [];

    // Header
    $lines[] = '# Checkpoint: ' . gmdate('Y-m-d H:i:s') . ' UTC';
    $lines[] = '';

    // Summary
    $lines[] = '## Summary';
    $lines[] = '';
    $totalFiles = count($fileChanges['created']) + count($fileChanges['modified']) + count($fileChanges['deleted']);
    $lines[] = '- **Commits**: ' . count($commits);
    $lines[] = "- **Files changed**: {$totalFiles} "
        . '(' . count($fileChanges['modified']) . ' modified, '
        . count($fileChanges['created']) . ' created, '
        . count($fileChanges['deleted']) . ' deleted)';
    $lines[] = "- **Codex consultations**: {$codexCount}";
    $lines[] = "- **Gemini researches**: {$geminiCount}";
    if ($since !== null) {
        $lines[] = "- **Since**: {$since}";
    }
    $lines[] = '';

    // Git History
    $lines[] = '## Git History';
    $lines[] = '';

    if (!empty($commits)) {
        $lines[] = '### Commits';
        $lines[] = '';
        foreach (array_slice($commits, 0, 20) as $commit) {
            $lines[] = "- `{$commit['hash']}` {$commit['message']}";
        }
        if (count($commits) > 20) {
            $remaining = count($commits) - 20;
            $lines[] = "- ... and {$remaining} more commits";
        }
        $lines[] = '';
    }

    // File Changes
    $lines[] = '### File Changes';
    $lines[] = '';

    if (!empty($fileChanges['created'])) {
        $lines[] = '**Created:**';
        foreach (array_slice($fileChanges['created'], 0, 15) as $f) {
            $stat = $fileStats[$f] ?? [0, 0];
            $lines[] = "- `{$f}` (+{$stat[0]})";
        }
        if (count($fileChanges['created']) > 15) {
            $remaining = count($fileChanges['created']) - 15;
            $lines[] = "- ... and {$remaining} more files";
        }
        $lines[] = '';
    }

    if (!empty($fileChanges['modified'])) {
        $lines[] = '**Modified:**';
        foreach (array_slice($fileChanges['modified'], 0, 15) as $f) {
            $stat = $fileStats[$f] ?? [0, 0];
            $lines[] = "- `{$f}` (+{$stat[0]}, -{$stat[1]})";
        }
        if (count($fileChanges['modified']) > 15) {
            $remaining = count($fileChanges['modified']) - 15;
            $lines[] = "- ... and {$remaining} more files";
        }
        $lines[] = '';
    }

    if (!empty($fileChanges['deleted'])) {
        $lines[] = '**Deleted:**';
        foreach (array_slice($fileChanges['deleted'], 0, 15) as $f) {
            $lines[] = "- `{$f}`";
        }
        if (count($fileChanges['deleted']) > 15) {
            $remaining = count($fileChanges['deleted']) - 15;
            $lines[] = "- ... and {$remaining} more files";
        }
        $lines[] = '';
    }

    if (empty($fileChanges['created']) && empty($fileChanges['modified']) && empty($fileChanges['deleted'])) {
        $lines[] = 'No file changes detected.';
        $lines[] = '';
    }

    // CLI Tool Consultations
    $lines[] = '## CLI Tool Consultations';
    $lines[] = '';

    $codexEntries = array_filter($entries, fn($e) => ($e['tool'] ?? '') === 'codex');
    $geminiEntries = array_filter($entries, fn($e) => ($e['tool'] ?? '') === 'gemini');

    if (!empty($codexEntries)) {
        $count = count($codexEntries);
        $lines[] = "### Codex ({$count} consultations)";
        $lines[] = '';
        foreach (array_slice(array_values($codexEntries), 0, 10) as $entry) {
            $status = ($entry['success'] ?? false) ? '✓' : '✗';
            $prompt = str_replace("\n", ' ', mb_substr($entry['prompt'] ?? '', 0, 80));
            $lines[] = "- {$status} {$prompt}...";
        }
        if ($count > 10) {
            $remaining = $count - 10;
            $lines[] = "- ... and {$remaining} more consultations";
        }
        $lines[] = '';
    }

    if (!empty($geminiEntries)) {
        $count = count($geminiEntries);
        $lines[] = "### Gemini ({$count} researches)";
        $lines[] = '';
        foreach (array_slice(array_values($geminiEntries), 0, 10) as $entry) {
            $status = ($entry['success'] ?? false) ? '✓' : '✗';
            $prompt = str_replace("\n", ' ', mb_substr($entry['prompt'] ?? '', 0, 80));
            $lines[] = "- {$status} {$prompt}...";
        }
        if ($count > 10) {
            $remaining = $count - 10;
            $lines[] = "- ... and {$remaining} more researches";
        }
        $lines[] = '';
    }

    if (empty($entries)) {
        $lines[] = 'No CLI tool consultations recorded.';
        $lines[] = '';
    }

    // Footer
    $lines[] = '---';
    $lines[] = "*Generated by checkpointing skill at {$timestamp}*";

    // Write checkpoint file
    file_put_contents($checkpointFile, implode("\n", $lines));

    return $checkpointFile;
}

function generateSkillAnalysisPrompt(string $checkpointContent): string
{
    return <<<PROMPT
Analyze the following checkpoint and identify reusable work patterns that could become skills.

A "skill" is a repeatable workflow pattern that can be triggered by specific phrases and executed consistently.

## Checkpoint Content

{$checkpointContent}

## Analysis Instructions

1. **Identify Patterns**: Look for regularities in:
   - Sequences of commits that form a logical workflow
   - File change patterns (e.g., test + implementation together)
   - CLI consultation patterns (design → implementation → review)
   - Multi-step operations that could be templated

2. **For each potential skill, provide**:
   - **Name**: Short, descriptive name (e.g., "tdd-feature", "research-implement")
   - **Description**: What this skill accomplishes
   - **Trigger phrases**: When should this skill be invoked (Japanese + English)
   - **Workflow steps**: Ordered list of actions
   - **Files typically involved**: Patterns like `tests/**/*.php`, `src/**/*.php`
   - **Confidence**: How confident are you this is a reusable pattern (0.0-1.0)
   - **Evidence**: What in the checkpoint suggests this pattern

3. **Output format**:

```markdown
## Skill Suggestions

### Skill 1: {{name}}
**Confidence:** {{0.0-1.0}}
**Description:** {{description}}

**Trigger phrases:**
- "{{Japanese phrase}}"
- "{{English phrase}}"

**Workflow:**
1. {{step 1}}
2. {{step 2}}
3. {{step 3}}

**Files involved:**
- `{{pattern 1}}`
- `{{pattern 2}}`

**Evidence:**
- {{evidence from checkpoint}}
```

4. **Quality criteria**:
   - Only suggest skills with confidence >= 0.6
   - Skip trivial patterns (single file edits, simple commits)
   - Focus on multi-step workflows that save time when repeated
   - Consider what would be valuable to automate in future sessions

Provide your analysis:
PROMPT;
}

function main(): void
{
    global $contextFiles;

    // Parse arguments
    $options = getopt('', ['since:', 'full', 'analyze']);
    $since = $options['since'] ?? null;
    $isFull = isset($options['full']);
    $isAnalyze = isset($options['analyze']);

    if ($isFull) {
        // Full checkpoint mode
        echo "Creating full checkpoint...\n";
        $checkpointFile = generateFullCheckpoint($since);
        if ($checkpointFile !== null) {
            echo "\nCheckpoint created: {$checkpointFile}\n";
            echo "\nCheckpoint includes:\n";
            echo "  - Git commits and file changes\n";
            echo "  - CLI tool consultations (Codex/Gemini)\n";
            echo "  - Session summary\n";

            if ($isAnalyze) {
                // Generate skill analysis prompt
                $checkpointContent = file_get_contents($checkpointFile);
                $prompt = generateSkillAnalysisPrompt($checkpointContent);

                // Save prompt to file
                $promptFile = preg_replace('/\.md$/', '.analyze-prompt.md', $checkpointFile);
                file_put_contents($promptFile, $prompt);

                echo "\n" . str_repeat('=', 60) . "\n";
                echo "SKILL ANALYSIS MODE\n";
                echo str_repeat('=', 60) . "\n";
                echo "\nAnalysis prompt saved to: {$promptFile}\n";
                echo "\nNext step: Use a subagent to analyze and suggest skills:\n";
                echo "  Read the prompt file and pass it to a subagent for analysis.\n";
                echo "\nThe subagent will identify reusable patterns and suggest new skills.\n";
            }
        } else {
            echo "Failed to create checkpoint.\n";
        }
        return;
    }

    // Session history mode (default)
    $entries = parseLogs($since);
    if (empty($entries)) {
        echo "No log entries found.\n";
        echo "Log file: " . LOG_FILE_PATH . "\n";
        return;
    }

    echo "Found " . count($entries) . " log entries\n";

    // Summarize
    $byDate = summarizeEntries($entries);

    // Generate session history
    $sessionHistory = generateSessionHistory($byDate);
    if (empty($sessionHistory)) {
        echo "No session history to write\n";
        return;
    }

    // Update each context file
    foreach ($contextFiles as $name => $filePath) {
        if (updateContextFile($filePath, $sessionHistory)) {
            echo "Updated: {$filePath}\n";
        } else {
            echo "Skipped: {$filePath}\n";
        }
    }

    echo "\nSession history has been written to all context files.\n";
    echo "All agents (Claude, Codex, Gemini) can now see the session history.\n";
}

main();
