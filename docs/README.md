# docs/ — 論文の計画と記録

人が読むための計画と記録の置き場所です。「なぜそうしたか」「何を決めたか」はここに、パス・コマンド・手順は `README.md` と `AGENTS.md` に書きます。各情報の正本の一覧は `AGENTS.md` の「単一の正本」にあります。

## 毎回読む文書

新しいセッションは `../STATE.md` → 実行記録(下記) → `../research.json` → `thesis-plan.md` → `guardrails.md` の順に読みます。`thesis-plan.md` と `guardrails.md` は8000字以内に保ちます(テストが検査します)。

両エージェント共通の実行記録も、[`AGENTS.md` の「動的ワークフロー」](../AGENTS.md#動的ワークフロー)に従って開始時・引き継ぎ時に読みます。運用手順の正本は [`DYNAMIC_WORKFLOW.md`](../DYNAMIC_WORKFLOW.md) です。

- `thesis-plan.md` — 論文の主張・研究課題・貢献・マイルストーン・一貫性の確認項目。研究と章の一覧は `../research.json`
- `guardrails.md` — 撤回した主張と、繰り返さない失敗
- `ideas.md` — 有望な案と、却下した案

## 記録の置き場所

| 置き場所 | 書くもの | 書き方 |
|---|---|---|
| `research-log.md` | 何を試し、何が分かり、なぜそう判断し、何が行き止まりだったか | 新しいものほど上(`<!-- newest entry below -->` の直下)。`research-log` スキルで書ける |
| `decisions/NNNN-<slug>.md` | 後から理由を振り返る判断(章の構成、根拠にする研究、発表版と違う値を使うことなど) | `decisions/_adr-template.md` を写す。`NNNN` は 0001 からの連番 |
| `reviews/YYYY-MM-DD-<chapter>.md`・`reviews/YYYY-MM-DD-thesis.md` | 章ごとの査読と、論文全体の一貫性の査読 | `review-chapter`・`review-thesis` スキルが書く。原稿は直さない |
| `feedback/YYYY-MM-DD-<reviewer>.md` | 指導教員・審査員の指摘と対応 | `feedback/_template.md` を写す(`feedback/README.md`) |
| `../.agent-runs/` | Claude Code・Codex のセッション一覧・実行記録・続きの地点(Git 管理外) | [台帳の案内](../.agent-runs/README.md)に従う |

- 実験の結果と判断は研究リポジトリの記録が正本です。ここには写さず、`<repo>@<sha>:<path>` でリンクします。
- 繰り返さない失敗と撤回した主張は、研究ログに加えて `guardrails.md` にも1行で書きます。
- サブディレクトリは、ファイルが増えてから切ります。
