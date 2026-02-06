#!/usr/bin/env php
<?php
/**
 * UserPromptSubmit hook: Route to appropriate agent based on user intent.
 *
 * Analyzes user prompts and suggests the most appropriate agent
 * (Codex for design/debug, Gemini for research/multimodal).
 */

// Triggers for Codex (design, debugging, deep reasoning)
$codexTriggers = [
    'ja' => [
        '設計', 'どう設計', 'アーキテクチャ',
        'なぜ動かない', 'エラー', 'バグ', 'デバッグ',
        'どちらがいい', '比較して', 'トレードオフ',
        '実装方法', 'どう実装',
        'リファクタリング', 'リファクタ',
        'レビュー', '見て',
        '考えて', '分析して', '深く',
    ],
    'en' => [
        'design', 'architecture', 'architect',
        'debug', 'error', 'bug', 'not working', 'fails',
        'compare', 'trade-off', 'tradeoff', 'which is better',
        'how to implement', 'implementation',
        'refactor', 'simplify',
        'review', 'check this',
        'think', 'analyze', 'deeply',
    ],
];

// Triggers for Gemini (research, multimodal, large context)
$geminiTriggers = [
    'ja' => [
        '調べて', 'リサーチ', '調査',
        'PDF', '動画', '音声', '画像',
        'コードベース全体', 'リポジトリ全体',
        '最新', 'ドキュメント',
        'ライブラリ', 'パッケージ',
    ],
    'en' => [
        'research', 'investigate', 'look up', 'find out',
        'pdf', 'video', 'audio', 'image',
        'entire codebase', 'whole repository',
        'latest', 'documentation', 'docs',
        'library', 'package', 'framework',
    ],
];

/**
 * Detect which agent should handle this prompt.
 *
 * @return array{?string, string}
 */
function detectAgent(string $prompt, array $codexTriggers, array $geminiTriggers): array
{
    $promptLower = mb_strtolower($prompt);

    // Check Codex triggers
    foreach ($codexTriggers as $triggers) {
        foreach ($triggers as $trigger) {
            if (mb_strpos($promptLower, mb_strtolower($trigger)) !== false) {
                return ['codex', $trigger];
            }
        }
    }

    // Check Gemini triggers
    foreach ($geminiTriggers as $triggers) {
        foreach ($triggers as $trigger) {
            if (mb_strpos($promptLower, mb_strtolower($trigger)) !== false) {
                return ['gemini', $trigger];
            }
        }
    }

    return [null, ''];
}

function main(): void
{
    global $codexTriggers, $geminiTriggers;

    try {
        $input = file_get_contents('php://stdin');
        $data = json_decode($input, true);
        $prompt = $data['prompt'] ?? '';

        // Skip short prompts
        if (mb_strlen($prompt) < 10) {
            exit(0);
        }

        [$agent, $trigger] = detectAgent($prompt, $codexTriggers, $geminiTriggers);

        if ($agent === 'codex') {
            $output = [
                'hookSpecificOutput' => [
                    'hookEventName' => 'UserPromptSubmit',
                    'additionalContext' =>
                        "[Agent Routing] Detected '{$trigger}' - this task may benefit from "
                        . "Codex CLI's deep reasoning capabilities. Consider: "
                        . '`codex exec --model gpt-5.2-codex --sandbox read-only --full-auto '
                        . '"{task description}"` for design decisions, debugging, or complex analysis.',
                ],
            ];
            echo json_encode($output) . "\n";
        } elseif ($agent === 'gemini') {
            $output = [
                'hookSpecificOutput' => [
                    'hookEventName' => 'UserPromptSubmit',
                    'additionalContext' =>
                        "[Agent Routing] Detected '{$trigger}' - this task may benefit from "
                        . "Gemini CLI's research capabilities. Consider: "
                        . '`gemini -p "Research: {topic}" 2>/dev/null` '
                        . 'for documentation, library research, or multimodal content.',
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
