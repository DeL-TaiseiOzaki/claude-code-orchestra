#!/usr/bin/env php
<?php
/**
 * PreToolUse hook: Suggest Gemini for research tasks.
 *
 * Analyzes web search/fetch operations and suggests using Gemini CLI
 * for comprehensive research with its larger context window.
 */

// Keywords that suggest deep research would benefit from Gemini
const RESEARCH_INDICATORS = [
    'documentation',
    'best practice',
    'comparison',
    'library',
    'framework',
    'tutorial',
    'guide',
    'example',
    'pattern',
    'architecture',
    'migration',
    'upgrade',
    'breaking change',
    'api reference',
    'specification',
];

// Simple lookups that don't need Gemini
const SIMPLE_LOOKUP_PATTERNS = [
    'error message',
    'stack trace',
    'version',
    'release notes',
    'changelog',
];

/**
 * Determine if Gemini should be suggested for this research.
 *
 * @return array{bool, string}
 */
function shouldSuggestGemini(string $query, string $url = ''): array
{
    $combined = strtolower($query) . ' ' . strtolower($url);

    // Skip simple lookups
    foreach (SIMPLE_LOOKUP_PATTERNS as $pattern) {
        if (str_contains($combined, $pattern)) {
            return [false, ''];
        }
    }

    // Check for research indicators
    foreach (RESEARCH_INDICATORS as $indicator) {
        if (str_contains($combined, $indicator)) {
            return [true, "Research involves '{$indicator}'"];
        }
    }

    // Long queries suggest complex research
    if (mb_strlen($query) > 100) {
        return [true, 'Complex research query detected'];
    }

    return [false, ''];
}

function main(): void
{
    try {
        $input = file_get_contents('php://stdin');
        $data = json_decode($input, true);
        $toolName = $data['tool_name'] ?? '';
        $toolInput = $data['tool_input'] ?? [];

        // Get query/url based on tool type
        $query = '';
        $url = '';
        if ($toolName === 'WebSearch') {
            $query = $toolInput['query'] ?? '';
        } elseif ($toolName === 'WebFetch') {
            $url = $toolInput['url'] ?? '';
            $query = $toolInput['prompt'] ?? '';
        }

        [$shouldSuggest, $reason] = shouldSuggestGemini($query, $url);

        if ($shouldSuggest) {
            $output = [
                'hookSpecificOutput' => [
                    'hookEventName' => 'PreToolUse',
                    'additionalContext' =>
                        "[Gemini Research Suggestion] {$reason}. "
                        . 'For comprehensive research, consider using Gemini CLI (1M token context). '
                        . "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        . 'to consult Gemini and save results to .claude/docs/research/. '
                        . "(Direct call OK for quick questions: `gemini -p '...' 2>/dev/null`)",
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
