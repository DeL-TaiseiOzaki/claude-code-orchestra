#!/usr/bin/env php
<?php
/**
 * Post-tool hook: Run formatter and static analysis on PHP files after Edit/Write.
 *
 * Triggered after Edit or Write tools modify files.
 * Runs PHP-CS-Fixer (format) and PHPStan (static analysis) on PHP files.
 */

// Input validation constants
const MAX_PATH_LENGTH = 4096;

function validatePath(string $filePath): bool
{
    if (empty($filePath) || strlen($filePath) > MAX_PATH_LENGTH) {
        return false;
    }
    // Check for path traversal
    if (str_contains($filePath, '..')) {
        return false;
    }
    return true;
}

function getFilePath(): ?string
{
    $toolInput = getenv('CLAUDE_TOOL_INPUT');
    if (empty($toolInput)) {
        return null;
    }

    $data = json_decode($toolInput, true);
    if ($data === null) {
        return null;
    }
    return $data['file_path'] ?? null;
}

function isPhpFile(string $path): bool
{
    return str_ends_with($path, '.php');
}

/**
 * Run a command and return [returnCode, stdout, stderr].
 *
 * @return array{int, string, string}
 */
function runCommand(array $cmd, string $cwd): array
{
    $process = proc_open(
        $cmd,
        [
            1 => ['pipe', 'w'],
            2 => ['pipe', 'w'],
        ],
        $pipes,
        $cwd
    );

    if (!is_resource($process)) {
        return [1, '', "Failed to execute: " . implode(' ', $cmd)];
    }

    $stdout = stream_get_contents($pipes[1]);
    fclose($pipes[1]);
    $stderr = stream_get_contents($pipes[2]);
    fclose($pipes[2]);

    $returnCode = proc_close($process);

    return [$returnCode, $stdout, $stderr];
}

function main(): void
{
    $filePath = getFilePath();
    if ($filePath === null) {
        return;
    }

    // Validate input
    if (!validatePath($filePath)) {
        return;
    }

    if (!isPhpFile($filePath)) {
        return;
    }

    $projectDir = getenv('CLAUDE_PROJECT_DIR') ?: getcwd();

    // Determine relative path for display
    if (str_starts_with($filePath, $projectDir)) {
        $relPath = ltrim(substr($filePath, strlen($projectDir)), '/');
    } else {
        $relPath = $filePath;
    }

    $issues = [];

    // Run PHP-CS-Fixer
    [$ret, $stdout, $stderr] = runCommand(
        ['./vendor/bin/php-cs-fixer', 'fix', $filePath, '--dry-run', '--diff'],
        $projectDir
    );
    if ($ret !== 0) {
        $output = $stdout ?: $stderr;
        if (trim($output) !== '') {
            $issues[] = "php-cs-fixer issues:\n{$output}";
        }
    }

    // Run PHPStan
    [$ret, $stdout, $stderr] = runCommand(
        ['./vendor/bin/phpstan', 'analyse', $filePath, '--no-progress'],
        $projectDir
    );
    if ($ret !== 0) {
        $output = $stdout ?: $stderr;
        if (trim($output) !== '') {
            $issues[] = "phpstan issues:\n{$output}";
        }
    }

    // Report results
    if (!empty($issues)) {
        fwrite(STDERR, "[lint-on-save] Issues found in {$relPath}:\n");
        foreach ($issues as $issue) {
            fwrite(STDERR, $issue . "\n");
        }
        fwrite(STDERR, "\nPlease review and fix these issues.\n");
    } else {
        echo "[lint-on-save] OK: {$relPath} passed all checks\n";
    }
}

main();
