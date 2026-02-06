#!/usr/bin/env php
<?php
/**
 * PostToolUse hook: Suggest Codex review after Plan tasks.
 *
 * This hook runs after Task tool execution and suggests Codex consultation
 * for reviewing plans and implementation strategies.
 */

// Task descriptions that suggest planning/design work
const PLAN_INDICATORS = [
    'plan',
    'design',
    'architect',
    'structure',
    'implement',
    'strategy',
    'approach',
    'solution',
    'refactor',
    'migrate',
    'optimize',
];

/**
 * Determine if Codex review should be suggested after task completion.
 *
 * @return array{bool, string}
 */
function shouldSuggestCodexReview(array $toolInput, ?string $toolOutput = null): array
{
    $subagentType = strtolower($toolInput['subagent_type'] ?? '');
    $description = strtolower($toolInput['description'] ?? '');
    $prompt = strtolower($toolInput['prompt'] ?? '');

    // Check if this is a Plan agent
    if ($subagentType === 'plan') {
        return [true, 'Plan task completed'];
    }

    // Check description/prompt for planning keywords
    $combinedText = "{$description} {$prompt}";
    foreach (PLAN_INDICATORS as $indicator) {
        if (str_contains($combinedText, $indicator)) {
            return [true, "Task involves '{$indicator}'"];
        }
    }

    return [false, ''];
}

function main(): void
{
    try {
        $input = file_get_contents('php://stdin');
        $data = json_decode($input, true);
        $toolName = $data['tool_name'] ?? '';

        // Only process Task tool
        if ($toolName !== 'Task') {
            exit(0);
        }

        $toolInput = $data['tool_input'] ?? [];
        $toolOutput = $data['tool_output'] ?? '';

        [$shouldSuggest, $reason] = shouldSuggestCodexReview($toolInput, $toolOutput);

        if ($shouldSuggest) {
            $output = [
                'hookSpecificOutput' => [
                    'hookEventName' => 'PostToolUse',
                    'additionalContext' =>
                        "[Codex Review Suggestion] {$reason}. "
                        . 'Consider having Codex review this plan for potential improvements. '
                        . "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        . 'to consult Codex and preserve main context.',
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
