# docs/ — 人間向けの文書

このディレクトリは、**人が読むための研究と論文の文書**を蓄積する場所です。エージェント向けの運用規則(`AGENTS.md`)とは役割を分けています。

目安: **「なぜそうしたか」と「何を決めたか」は docs/、「どうやるか」は README・AGENTS.md**。パス・コマンド・環境構築などの事実は `README.md`・`AGENTS.md` へ、コードで表せることはコードとテストへ書きます。各情報の正本の一覧は `AGENTS.md` の「単一の正本」にあります。

## セッションの引き継ぎに使う文書

新しいセッションは次の順で読みます。

1. `../STATE.md` — 運用状態の単一ページ(段階、現在の焦点、実行中のジョブ、次の作業)
2. `thesis-plan.md` — 論文の骨格(主張・研究課題・貢献・章と根拠の対応・執筆状況)
3. `../projects/<study>/experiments/EXP_SUMMARY.md` — 現在の焦点のスタディの実験の索引と状態(撤回を含む)
4. `guardrails.md` — 撤回した主張と、繰り返さない失敗

この4つには文字数の上限があります(上限は `AGENTS.md` の「セッション状態と引き継ぎ」。`tests/test_repo_structure.py` が検査します)。

必要なときに開く文書:

- `../projects/<study>/experiments/JOBS.md` — 長時間ジョブの台帳(投入直後と完了時に記録)
- `launch-checklist.md` — 高コストな実行の投入前チェックリスト
- `ideas.md` — 有望な案と、却下した方向
- `importing-past-results.md` — これまでの実験結果を取り込む手引き
- `integrations.md` — 外部の同期フォルダと書誌の扱い

## 記録の置き場所

| 置き場所 | 書くもの | 書き方 |
|---|---|---|
| `research-log.md` | 研究ログ: 何を試し、何が分かり、なぜそう判断し、何が行き止まりだったか | 1ファイルに、新しいものほど上(`<!-- newest entry below -->` の直下へ)。`research-log` スキルで書ける |
| `decisions/NNNN-<slug>.md` | 意思決定記録: 方法・データの除外基準・構成など、後から理由を振り返る判断 | `decisions/_adr-template.md` を写す。`NNNN` は 0001 からの連番 |
| `reviews/YYYY-MM-DD-<chapter>.md`、`reviews/YYYY-MM-DD-thesis.md` | 章ごとの査読と、論文全体の一貫性の査読 | `/review-chapter`・`/review-thesis` が書く。原稿は直さない |
| `feedback/YYYY-MM-DD-<reviewer>.md` | 指導教員・審査員の指摘と、その対応 | `feedback/_template.md` を写す(`feedback/README.md`) |

- 実験の結果は、ここではなく各実験の `summary.md`(今の結論)と `README.md`(経緯)に書き(`projects/<study>/experiments/NNN_<slug>/`)、研究ログからリンクします。
- 繰り返さない失敗は、研究ログに加えて `guardrails.md` にも1行で書きます。撤回は、実験の `summary.md` と索引に加えて `guardrails.md` にも1行書きます。訂正・置き換えも、古い主張がすでに外に出ている(送った版・投稿・発表)なら同じです(手順は `AGENTS.md` の「実験」)。
- 研究ログと意思決定記録は、他の文書と同じく日本語で書きます。古いリポジトリの記録は写さず、`<repo>@<sha>:<path>` でリンクします。
- サブディレクトリは、ファイルが増えてから切ります(雛形は最小の構成を保ちます)。
