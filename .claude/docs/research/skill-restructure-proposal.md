# Skill システム再構築 提案書

_基盤: `.claude/docs/research/skill-independence-audit.md`（独立性監査）。本書は READ-ONLY 分析であり、既存ファイルは一切変更していない。_
_Codex CLI はこの環境では未インストール（`codex` バイナリ不在 / exit 127）のため未相談。以下は自己分析に基づく。_

---

## 1. 提案サマリ

低独立度8スキルの密結合を **3つの統合** で解消し、**17 → 14** に削減する。削除（丸ごと廃止）は行わず、全て「統合＝別スキルのフェーズ/モードへ吸収」で内容を保存する。

### Before / After カタログ

| # | Before (17) | After (14) | 変更 |
|---|---|---|---|
| 1 | plan | plan | 据置（高独立） |
| 2 | tdd | tdd | 据置（高独立） |
| 3 | simplify | simplify | 据置（高独立） |
| 4 | research-lib | research-lib | 据置（高独立）※代替案でlib-docsへ統合 |
| 5 | update-lib-docs | update-lib-docs | 据置（高独立）※同上 |
| 6 | catchup | catchup | 据置＋`collect_repo_state.py`同梱 |
| 7 | codex-system | codex-system | 据置＋重複排除の単一情報源へ昇格 |
| 8 | design-tracker | design-tracker | 据置（DESIGN.md単一オーナー・中独立） |
| 9 | init | init | 据置＋`detect_stack.py`同梱 |
| 10 | add-feature ┐ | **feature** | **統合①**（モード分岐＋複雑度ルーティング） |
| 11 | start-feature ┘ | | |
| 12 | team-implement ┐ | **team-execute** | **統合②**（Phase1実装＋Phase2レビュー）＋`gather_diff.sh` |
| 13 | team-review ┘ | | |
| 14 | troubleshoot | troubleshoot | 据置（別意図の診断WF）＋`repro.sh`同梱 |
| 15 | spike | spike | 据置（意思決定文書・別成果物） |
| 16 | checkpointing ┐ | **checkpointing** | **統合③**（context-refreshを最終compactフェーズとして吸収） |
| 17 | context-refresh ┘ | | ＋`refresh_guard.py`同梱 |

低独立8スキル → 統合後は `feature` / `team-execute` / `troubleshoot` / `spike` / `checkpointing` の **5スキル**（8→5）。

---

## 2. 統合・削除プラン（推奨1案）

### 統合① add-feature + start-feature → `feature`

- **What**: 2つの「計画スキル」を1つに。冒頭で MODE を判定する。
  - `MODE=existing`（旧 add-feature）: 既存コードベース、規約確立済み → **Codex直** で scope→design→plan。
  - `MODE=greenfield`（旧 start-feature）: 大規模・要外部調査 → **Agent Teams**（Researcher＋Architect）で research→design。
  - Phase3 の複雑度ルーティング（SIMPLE=Codex直 / MODERATE=+review / COMPLEX=team-execute）は共通化して残す。
- **Why**: 両者は「Phase1 理解 → Phase2 設計 → Phase3 計画/実装ルート」の3フェーズ構造が同型（add-feature:60-402 / start-feature:46-343）。差分は「研究フェーズの有無」の1軸のみで、`/add-feature` 自身が「lighter than /start-feature」と明記（add-feature:21,452）しており、実体は同一スキルの2モード。
- **Migration**: `feature/SKILL.md` に MODE 分岐節を新設。Opusサブエージェント走査・Codex必須consult・DESIGN.md/CLAUDE.md Zone C更新は共通節に集約。`start-feature/references/task-patterns.md` は `feature/references/` へ移設。旧 `/add-feature` `/start-feature` はエイリアスとして1シーズン残置し警告出力。
- **Risk**: 中。トリガー文言（新機能 vs 既存追加）の誤判定 → MODE を最初に `AskUserQuestion` で明示確認して回避。

### 統合② team-implement + team-review → `team-execute`

- **What**: 常に逐次実行される「並列実装 → 並列レビュー」を1スキルの2フェーズに。
  - Phase1 IMPLEMENT（旧 team-implement）: モジュール別Teammate、file-ownership分離。
  - Phase2 REVIEW（旧 team-review）: security/quality/test レビュアを並列起動。
  - `--review-only` で Phase1 をスキップ（手動実装後のレビュー単独利用を維持）。
- **Why**: team-implement 完了時の唯一の Next Step が `/team-review`（team-implement:259）、team-review の前提が team-implement 出力（team-review:19,31）。両者は Agent Teams ランタイム・work-logフォーマット・`{feature}`/`{team-name}`命名継続・DESIGN/PROGRESS読取を完全共有し、ハブノードとして常にペアで呼ばれる。
- **Migration**: `team-execute/SKILL.md` を2フェーズ構成に。work-logテンプレは統合③の共有情報源（§3参照）へ外出し。`gather_diff.sh`（§4-3）を同梱し Phase2 冒頭で実行。旧 `/team-review` は `--review-only` エイリアスへ。
- **Risk**: 低。`--review-only` により独立レビュー用途は保全。

### 統合③ checkpointing が context-refresh を吸収

- **What**: context-refresh を checkpointing の **最終 compact フェーズ**（Phase5相当）として内部化。単独起動用に `checkpointing --compact-only`（旧 `/context-refresh` 相当）を提供。
- **Why**: context-refresh は `disable-model-invocation: true`（context-refresh:14）で自動起動不可、実質 checkpointing 専用サブルーチン。checkpointing が「最終ステップで必ず呼ぶ」（checkpointing:48,308,358）唯一の呼出元。**スキル間の必須ハード呼び出し**という最大の結合要因が、統合により内部フェーズ呼び出しへ降格する（＝独立度改善の本丸）。
- **Migration**: context-refresh SKILL.md 本文（Phase1-5, Invariants, Safety Checklist）を `checkpointing/SKILL.md` の「## Phase 5: Compact」節へ移動。`refresh_guard.py`（§4-1）を `checkpointing/` に同梱し破壊的検証を機械保証。`checkpoint.py` は変更不要（既に Zone-Cリンク挿入を担当）。
- **Risk**: 中。「CLAUDE.md > 400行で単独compact」用途 → `--compact-only` モードで完全保全。destructive prune の承認ゲート（AskUserQuestion）は必ず維持。

> **据置の判断（troubleshoot / spike）**: 両者は feature と同型の3フェーズCodex-first+Agent Teams構造だが、**意図と成果物が異なる**ため統合しない。troubleshoot は「根本原因診断」（Bug Report・hypothesis評価・regression risk）で成果は fix plan、spike は「go/no-go意思決定文書」で実装計画を敢えて作らない（spike:9,22）。feature へ mode として畳むとプロンプト本質部（診断/評価ロジック）が肥大化し、逆に可読性が落ちる。両者は team-execute へのハンドオフ側に残す。

### 近接判断（briefly-noted alternatives）

- **Alt-A: team-execute を feature に畳む** — 承認ゲート（計画→承認→実装→レビュー）が1スキルに埋没し、独立レビュー用途も失う。**非推奨**。
- **Alt-B: research-lib + update-lib-docs → `lib-docs`（research/update モード）** — 両者とも `.claude/docs/libraries/` を対象とし統合可能（14→13）。高独立スキルで緊急度は低いが、カタログ簡潔化に有効。**任意採用可**。
- **Alt-C: troubleshoot を feature の diagnose モードへ** — 上記理由で**非推奨**。

---

## 3. CLAUDE.md 重複排除マップ

各トピックに **単一情報源（SSOT）** を1つ割当て、他は削除 or 1行ポインタ化する。行番号は現状の実ファイル。

| トピック | 現在の重複箇所 (file:line) | 指定SSOT | 各他箇所の処置 |
|---|---|---|---|
| **Codex delegation ポリシー（いつ委譲するか・トリガー表）** | CLAUDE.md §3,§4 / `rules/codex-delegation.md`「Delegation Decision」/ `codex-system/SKILL.md:37-55` | `rules/codex-delegation.md` | CLAUDE.md §3/§4 は要旨1行＋ルールへのポインタに縮約。codex-system:37-55 を「詳細は codex-delegation.md」ポインタ化 |
| **Codex 呼出し方法（exec構文・Subagent/Direct・テンプレ）** | `codex-system/SKILL.md:57-144` / `rules/codex-delegation.md`「How to Consult」 | `codex-system/SKILL.md` | codex-delegation.md の exec例を削除しcodex-systemへポインタ（ルールは"when"に専念） |
| **Sandbox modes 表（read-only / workspace-write）** | `codex-system:91-96` / `rules/codex-delegation.md`「Sandbox Modes」 | `codex-system:91-96` | codex-delegation.md 側を削除しポインタ |
| **codex-plugin-cc スラッシュコマンド群** | `codex-system:153-209` / `rules/codex-delegation.md`「Codex Plugin」 | `codex-system:153-209` | codex-delegation.md 側を1行ポインタ化 |
| **Preflight「CLI更新」文言** | add-feature:17 / start-feature:17 / spike:18 / team-review:15 / troubleshoot:18 / codex-system:18 / codex-delegation.md冒頭 | `codex-system:18` | 各featureスキルから削除し「see codex-system Preflight」1行に。ルールも同ポインタ |
| **Language Protocol（思考=英/応答=日/コード=英）** | CLAUDE.md §8 / `rules/language.md`（全文）/ `codex-system:146-151` | `rules/language.md` | CLAUDE.md §8 と codex-system:146-151 をポインタ化（context-refresh:263 は既にポインタ＝手本） |
| **Agent Teams Work Log テンプレ**（`# Work Log:` 5節） | start-feature:167-187,213-233 / spike:217-239,349-374 / team-implement:132-152,169-189 / team-review:108-124,152-174,198-221 / troubleshoot:287-313,398-426 | 新設 `.claude/skills/_shared/work-log-format.md`（or `rules/agent-teams.md`） | 各スキルのインライン定義を削除し「per shared Work Log format (`_shared/work-log-format.md`)」参照へ。**最大の重複源**（約12箇所） |
| **CLAUDE.md 3-zone / 境界マーカー / update.sh 手順** | init:21-35,93-97 / context-refresh:59,236-239 / start-feature:287-289 / checkpointing:273-285 | 新設 `rules/claude-md-zones.md`（ゾーン契約の正典） | 各スキルは不変条件を1行参照＋「マーカー欠如時 update.sh」だけ残す |
| **品質ゲートコマンド列（ruff/ruff format/ty/pytest）** | `rules/dev-environment.md`「Common Commands/Pre-commit」/ team-implement:231-240 / add-feature:368-377 / team-review:180 | `verify.sh`（poe all 相当・§4補足）＋ dev-environment.md | 各スキルはコマンド列を削除し `verify.sh` 実行へ置換 |
| **スキル・ルーティング表（どの状況でどのスキル）** | CLAUDE.md §3 / add-feature:35-41 / spike:34-51 / context-refresh:43-55 / catchup:209-213 | CLAUDE.md §3 Routing Policy | 各スキルの比較表は自スキルの「When NOT to use」最小限に絞り、全体routingはCLAUDE.md参照 |

**付随クリーンアップ**（重複ではないが同時修正推奨）:
- `codex-system:217` の `context-loader` skill 断リンク（実在せず）を削除。
- `codex-system/references/*.md`（5本）が SKILL.md から未リンク → 導線追加 or 削除。
- `checkpoint.py:736-739` のハードコード17スキル列挙を統合後14スキルへ更新（統合後の必須作業）。

---

## 4. スクリプト同梱設計（checkpoint.py 方式・ROI Top5）

方針: 決定的・機械的手順を各スキルディレクトリ内スクリプトへ封じ込め、SKILL.md は「このスクリプトを実行し出力(JSON)を解釈する」に縮約。全て **JSON を stdout** に出力し、大きな本文（diff/ログ）はファイルへ書きパスをJSONで返す。`PROJECT_ROOT` は checkpoint.py:25 と同じ4階層規約。

### 4-1. `refresh_guard.py` （配置: `checkpointing/`）

- **役割**: context-refresh の機械部分＝境界マーカー検証・行数計測・Zone Cブロック棚卸・archive移動プラン算出（破壊操作なし=dry-run）。
- **Inputs**: `--project-root`（既定4階層上）, `--mode {check,plan,verify}`。読取: CLAUDE.md, `.claude/docs/research/*.md`。
- **Outputs (stdout JSON)**:
  ```json
  {"markers":{"template_boundary":1,"repo_boundary":1,"ok":true},
   "claude_md":{"total_lines":512,"zone_c_start":300,"zone_c_lines":210},
   "progress_tracker_present":true,
   "zone_c_blocks":[{"heading":"## Current Feature: X","line":305,"date":"2026-02-01","keep":true}],
   "legacy_sections":["## Work Evolution"],
   "research_notes":[{"file":"feat-x.md","mtime":"2026-01-10","active":false}],
   "move_plan":[{"src":".../research/feat-x.md","dst":".../research/archive/feat-x.md","mode":"create"}]}
  ```
- **Exit codes**: `0` 正常 / `2` マーカー欠如（=abort、update.sh要求） / `3` パース不能・異常。
- **置換対象**: context-refresh SKILL.md Phase1スキャン(97-151)の機械部・Phase2プラン算出(155-186)・Phase5検証grep(247-263)。実際の書換えは承認後にEdit/Writeで実施（本スクリプトは非書込）。
- **規模**: 約180行 (Python)。

### 4-2. `collect_repo_state.py` （配置: `catchup/`）

- **役割**: catchup Phase1 の全収集（git＋identity＋rules/skills/agents frontmatter＋docs＋checkpoints/logs）を1本のJSONに集約。
- **Inputs**: `--project-root`, `--since`（既定 "30 days ago"）, `--max-commits`（既定100）。
- **Outputs (stdout JSON)**: `git`(log/branches/status/stash/diff --stat), `identity`(README/CLAUDE/AGENTS/pyproject の有無＋先頭行), `rules`(ファイル名＋1行), `skills`(name＋short-description), `agents`(name＋specialization), `docs`(DESIGN有無, research/libraries 一覧＋1行), `checkpoints`(newest5＋summary), `cli_tools`(最新50・Codexトピック抽出)。存在しないパスは `null`/`"not present"`。
- **Exit codes**: `0` 常時（欠損は優雅劣化） / `1` git非リポジトリ（`git:null`で継続も可）。
- **置換対象**: catchup SKILL.md のサブエージェント・スキャン仕様(58-131)。SKILL.md は「本スクリプト実行→JSONをサブエージェント/synthesisへ」に縮約。
- **規模**: 約220行 (Python)。

### 4-3. `gather_diff.sh` （配置: `team-execute/`、旧 team-review）

- **役割**: レビュー対象スコープ収集＝diff・変更ファイル・commit log・coverage・lint。
- **Inputs**: `$1`=base ref（既定 `main`）。
- **Outputs (stdout JSON)**: `{"base":"main","head":"<sha>","changed_files":[...],"diffstat":"...","commits":[...],"coverage":{...}|null,"ruff":{"ok":true,"issues":0},"diff_file":".claude/logs/review-diff.patch"}`。diff本体は肥大するためファイルへ書き、stdoutは軽量に保つ。
- **Exit codes**: `0` 正常 / `1` git非リポジトリ or base ref不在。coverage/ruff失敗は**スクリプトを落とさず**JSONに記録。
- **置換対象**: team-review SKILL.md Step1(52-65)＋テスト実行(180)。`feature`/`troubleshoot` からも再利用可（横断共通化）。
- **規模**: 約60行 (bash)。

### 4-4. `detect_stack.py` （配置: `init/`）

- **役割**: tech stack・コマンド・境界マーカーを機械検出。
- **Inputs**: `--project-root`。走査: package.json / pyproject.toml / setup.py / requirements.txt / Cargo.toml / go.mod / Makefile / Dockerfile / .github/workflows、poe tasks・npm scripts。
- **Outputs (stdout JSON)**: `{"languages":["python"],"package_managers":["uv"],"manifests":{"pyproject.toml":true},"commands":{"lint":"uv run ruff check .","test":"uv run pytest"},"libraries":[...],"ci":["github-actions"],"claude_md_markers":{"template_boundary":true,"repo_boundary":true}}`。
- **Exit codes**: `0` 正常 / `2` CLAUDE.md マーカー欠如（init に update.sh 要求を促す）。
- **置換対象**: init SKILL.md Step1 検出手順(41-53)＋マーカーgrep(93-97)。`feature`(旧start-feature前提チェック)からも再利用可。
- **規模**: 約130行 (Python)。

### 4-5. `repro.sh` （配置: `troubleshoot/`）

- **役割**: エラー再現＋スタックトレース捕捉＋関連git履歴収集（log/blame）。
- **Inputs**: `$1`=再現コマンド（例 `"uv run pytest tests/test_x.py"`）, `--file`（blame対象・任意）, `--bisect-good`（任意）。
- **Outputs (stdout JSON)**: `{"repro_command":"...","exit_code":1,"stdout_tail":"...","stderr_tail":"...","traceback":"...","recent_commits":[...],"blame":null,"log_file":".claude/logs/troubleshoot-repro.log"}`。全出力はログファイルへ、パスをJSONで返す。
- **Exit codes**: スクリプト自体は捕捉モードのため `0`（再現コマンドの終了コードはJSON内 `exit_code`） / `1` 引数誤り。
- **置換対象**: troubleshoot SKILL.md Phase1サブエージェントの機械部(79-96: 失敗コマンド実行・git log -20・blame)＋Phase3 regression実行(505-506)。根本原因判断はLLM+Codexに残す。
- **規模**: 約70行 (bash)。

> **共通スクリプト補足**: `verify.sh`（ruff/ruff format/ty/pytest 一括、`poe all` 相当）は team-execute / feature / troubleshoot で重複するため、独立配布優先なら各スキル同梱、DRY優先なら共有 `scripts/` を選択（監査6.3のトレードオフ）。本提案は独立度優先で **各スキル同梱** を推奨。

---

## 5. 実装ロードマップ（安全順）

原則: **加算的で単独検証可能なものから → テキスト重複排除 → 構造的マージは最後**。スクリプトと重複排除は独立で並行可、マージは厳密に最後。

### Step 1: スクリプト同梱（加算的・最小リスク）

- **内容**: §4の5スクリプトを現行スキルディレクトリに追加（checkpoint.py が実証済みの手本）。SKILL.md は当該機械手順節を「スクリプト実行＋JSON解釈」に置換。
- **Blast radius**: 新規ファイル＋各SKILL.md 1節。既存挙動は非破壊。
- **検証**: 各スクリプト単体実行 →
  ```bash
  uv run python .claude/skills/checkpointing/refresh_guard.py --mode check | python -m json.tool
  uv run python .claude/skills/catchup/collect_repo_state.py | python -m json.tool
  bash .claude/skills/team-review/gather_diff.sh main | python -m json.tool
  uv run python .claude/skills/init/detect_stack.py | python -m json.tool
  ```
  各 exit code とJSON妥当性を確認。

### Step 2: 重複排除（テキスト単一情報源化・可逆）

- **内容**: §3マップに従い SSOT を確定し、他箇所を削除/ポインタ化。特に Work Log テンプレの共有ファイル外出しと codex 3重複（CLAUDE.md/rules/codex-system）の整理。付随して codex-system:217 断リンク削除。
- **Blast radius**: CLAUDE.md・`rules/*.md`・SKILL.md本文（テキストのみ、構造不変）。新規 `_shared/work-log-format.md` と `rules/claude-md-zones.md` を追加。
- **検証**:
  ```bash
  rg -n "npm install -g @openai/codex" .claude CLAUDE.md   # Preflight が1箇所へ収束
  rg -n "# Work Log:" .claude/skills                        # インライン定義が消えたことを確認
  rg -n "context-loader" .claude/skills                     # 断リンク除去を確認（0件）
  ```

### Step 3: 構造マージ（最高Blast radius・最後）

- **内容**: 統合①②③を実施。`git mv` でディレクトリ統合、Step1のスクリプトを最終ディレクトリへ移設、cross-reference（`/add-feature` `/start-feature` `/team-implement` `/team-review` `/context-refresh`）をエイリアス/新名へ更新。`checkpoint.py:736-739` のスキル列挙を14スキルへ更新。catchup/checkpointing の interaction 表を更新。
- **Blast radius**: スキルディレクトリ構成・checkpoint.py・全skill間参照・PROGRESS/GUIDE 生成ロジック。
- **検証**:
  ```bash
  ls .claude/skills | wc -l                                  # = 14
  rg -n "/add-feature|/start-feature|/team-implement|/team-review|/context-refresh" .claude \
     | rg -v "alias|旧"                                       # 未解決の旧参照が無いこと
  uv run python .claude/skills/checkpointing/checkpoint.py --since 2026-01-01  # 統合後も走る
  ```

### 順序の根拠

スクリプトは checkpoint.py で実証済みの加算パターンで単独検証でき、I/O契約を先に固める価値が高い（→最初）。重複排除は純テキストで可逆・低リスクかつマージ対象本文を予めスリム化する（→中間）。マージはディレクトリ改名・多数の相互参照・checkpoint.py更新を伴い最高Blast radiusのため、本文がリーンでスクリプトが揃った後に一度だけ実施する（→最後）。
