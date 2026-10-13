---
name: import-results
description: これまでの実験結果(別のリポジトリ・フォルダ・論文)を、由来と再現性(R1/R2/R3)を記録しながらスタディの取り込み実験として取り込み、照合してから章へつなぐ。ユーザーが「過去の結果を入れたい」「前のリポジトリの図を使いたい」と言ったときに使う
---

# 過去の結果を取り込む

手順の正本は `docs/importing-past-results.md` です。最初に全文を読み、ケース別の手順(A〜E)と
「既発表・投稿中の論文を章にする」を確かめてから進めます。このスキルは、その手順をエージェントが
どの順で進め、どこでユーザーに確かめるかを決めます。

## 守ること

- **`data/raw/` にはエージェントは書き込まない。** 過去のファイルのコピーは、ユーザーが自分の端末で実行する
  コマンドとして示すだけにする。ユーザーに「実行して」と頼まれても実行しない(生データの置き場に書くのは本人
  だけ。Claude Code ではフックが止めるが、Codex をホストで使うときは何も止めないので自分で守る)。止められても
  回避しない。
- ハッシュを手で打たない。マニフェストは生成する。
- README・台帳・`params.py` に書く由来の内容は、ユーザーに確かめてから書く。推測で埋めない。
- ホストの絶対パスを追跡するファイルに書かない。場所は `<repo>@<sha>:<path>` で書く。
- 撤回・中止された過去の結果、合成・デモの出力は、結果として取り込まない(撤回・中止のものは、ユーザーが
  決めたときだけ、その判断を README に書いて取り込む)。
- 取り込み実験が「完了」になるまで、取り込んだ結果を本文で使わない。
- Python はコンテナ内で実行する。

## 手順

1. **聞く。** ユーザーに次を尋ねる。答えはこの後の手順でファイルに書く。
   - 過去の結果はどこにあるか(ホストのパス。Git のリポジトリならその名前)
   - 何が残っているか: 入力データ / コード / 数値の出力(CSV・JSON など)/ 画像だけ / 論文の数値だけ
   - どの主張・章の根拠にするか(`docs/thesis-plan.md` の RQ・章ラベル)
   - どの実行が正式か。既に発表したか(どの論文・表か)。共同研究者の同意やライセンスの制約はあるか

2. **読むだけの操作で調べる。** `ls`・`find <path> -type f | head`・`du -sh`、`git -C <repo> log -1`・
   `git -C <repo> status --porcelain`、`run_meta.json` や `config.yaml` などの記録を読む。
   research-template 形式なら、先に旧リポジトリの `STATE.md`・実験の索引(`experiments/EXP_SUMMARY.md`、古い版では
   `exp/EXP_SUMMARY.md`)・`docs/guardrails.md`・`docs/ideas.md` と候補の実験の `summary.md`(あれば)を読み、
   候補の実験の状態(撤回・訂正・中止・置き換え)を確かめる。置き換えられた実験は取り込まず、置き換えた実験を
   取り込む。候補の実験の `out/params_used.json`(あれば。`status` が `completed` で `smoke` でない記録だけを
   実行の記録とする)も読む。
   正式な実行、外す実行(古い版・試し・合成・デモ)、1 MB を超える画像、アニメーションなどを洗い出す。

3. **案を出して確かめる。** 取り込む単位(1つの主張を支える1組の結果ごとに1実験)、スタディ(既存か
   `TITLE='…' make study NAME=<study>`)、slug、`<source>` の名前、成果物ごとの再現性(R1/R2/R3)と
   その理由を表にしてユーザーに示し、了承を得る。

4. **取り込み実験を作る。**

   ```bash
   make experiment-import STUDY=<study> SLUG=<slug> SOURCE=<source> FROM=<path> [LEGACY_ID=<repo>@<sha>:experiments/NNN_x]
   ```

   直接なら `python3 tools/new_experiment.py <study> <slug> --import --source <source> --from <path>`。
   索引に `(実行前) | 進行中 | — | 取り込み` の行ができ、`summary.md` に「残りの手順」、README に
   「取り込み元とコマンド」が入る。

5. **すぐに書き残す。** 手順1〜3の答えのうち、ユーザーが確かめたものを `summary.md` の問い・判定の規則と
   README の「目的」「由来」に書く。`STATE.md` の待ちの行(または次の作業)に「ユーザーが `<source>` をコピー →
   マニフェスト生成」と書く。ここでセッションが切れても、`summary.md`・README と STATE.md から再開できる状態にする。

6. **コピーのコマンドを示す(実行しない)。** 表示されたコマンドを、正式な実行だけを写すように直して示す。

   ```bash
   mkdir -p projects/<study>/data/raw/legacy/<source>
   rsync -a --copy-unsafe-links --exclude .git --exclude .venv --exclude __pycache__ \
     --exclude .DS_Store --exclude '._*' <PATH>/ projects/<study>/data/raw/legacy/<source>/
   ```

   R1 の入力データは `projects/<study>/data/raw/<dataset>/` へ、非公開の旧コードは
   `mkdir -p projects/<study>/data/raw/legacy/<source>/code && git -C <repo> archive <sha> | tar -x -C projects/<study>/data/raw/legacy/<source>/code/`
   で写すよう示す(マニフェストはコードを写した後に作る)。
   「リポジトリのルートで、ご自分の端末で実行してください」と添え、終わったら知らせてもらう。

7. **マニフェストを作る(エージェントが実行してよい)。** raw を読み、raw の外へ書くだけの操作。

   ```bash
   (cd projects/<study>/data/raw/legacy/<source> && find . -type f ! -name .gitkeep -print0 \
     | LC_ALL=C sort -z | xargs -0 sha256sum) > projects/<study>/experiments/NNN_<slug>/inputs.sha256
   ```

   `SOURCE_DIR` が `/external` の下にあるときは、`/external` がコンテナの中にしか無いので、ホストのリポジトリの
   ルートで次を実行する(ホストで `cd /external/...` すると失敗し、空のマニフェストだけが残る)。

   ```bash
   docker compose exec -T research-template bash -c '(cd /external/<source> && find . -type f ! -name .gitkeep -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) > projects/<study>/experiments/NNN_<slug>/inputs.sha256'
   ```

   元と同じに写せたかを `m="$PWD/projects/<study>/experiments/NNN_<slug>/inputs.sha256"; (cd <PATH> && sha256sum --quiet -c "$m")`
   で確かめる(何も出なければ一致)。コミットの前に、ファイル数と `inputs.sha256` のファイル名をユーザーに示し、
   次を確かめる。
   - 外したはずのもの(サンプル・デモ)が入っていないか。入っていれば、ユーザーに写し直してもらう。
   - ファイル名に人名・参加者 ID・施設名など公開できない情報が無いか。ファイル名はマニフェストと由来記録に
     そのまま入り、コミットすると公開される。あれば `inputs.sha256` をコミットせず、ユーザーに名前を付け替えて
     写し直してもらい(元の名前との対応表は Git の外に保管する)、マニフェストを作り直す。

8. **由来・台帳・パラメータを埋める(確かめてから)。** 下書きを示して了承を得てから書く。
   - README の「由来」「成果物ごとの再現性」の表
   - `projects/<study>/data/README.md` の台帳の一覧の行と「過去の結果(legacy)の記録」のブロック(元の場所、実施時期、
     実施者、生成コードとコミット、再現性、取り込み実験、ライセンス・公開可否、バックアップ先、マニフェスト)
   - `params.py`: `SOURCE_DIR`、`RECORDED_SHA256`(旧ツールの記録のうち `SOURCE_DIR` の中のファイルの分だけ。
     入力データのハッシュは `data/raw/<dataset>/` の台帳のチェックサムと照合する)、`REFERENCE_VALUES`(既報の
     数値と出典。bib キーと表・頁)、論文の数値しか無ければ `TRANSCRIBED`・`TRANSCRIBED_SOURCE`・
     `TRANSCRIBED_FORMATS`

9. **作り直しを実装して実行する。** `run.py` の TODO を、決めたレベルに合わせて実装する(R1 は旧コードを別の
   プロセスで(import せず)出力先を `run.out_dir` に向けて動かすか `src/` へ移植、R2 は残った数値から作り直す、
   R3 は `import_figure`)。
   `run.py` は `experiment.start()` の中で段階(`run.stage()`)ごとに進める: 入力の照合(`verify_inputs`)→
   メモリ上か `out/` での作り直し → 既報の数値との照合(`crosscheck`。照合の表は `run.promote()` で
   `result/tables/` の `<study>-<slug>-crosscheck.csv` へ)→ ヘルパー(`save_figure`・`write_latex_table`・
   `write_latex_values`。R3 の書き写した数値も)。照合が通らなければ実行は `failed` になり `result/` は変わらない。
   再利用するロジックは `src/` にテストとともに置く。まず `--smoke` で最後まで通し(何も公開しない)、
   `run.py`・`params.py`・`inputs.sha256` と変えたコードをコミットしてから本実行する(コミットを任されていなければ
   ユーザーに頼む。未コミットのコードや、実行中に変わったコードで書いた生成物は W15 になる)。実行は:

   ```bash
   docker compose exec research-template uv run python projects/<study>/experiments/NNN_<slug>/run.py --smoke
   docker compose exec research-template uv run python projects/<study>/experiments/NNN_<slug>/run.py
   ```

   実行後に `git status` を見て、そのスタディの `result/` と実験の `out/` の他に変更が無いことを確かめる。
   照合(`crosscheck`)が合わなければ許容差を黙って広げず、原因を調べてユーザーに報告する。

10. **照合を書く。** 照合の数値は `result/tables/` の `…-crosscheck.csv` から `summary.md` の「照合」へ写し、
    経緯(最大の差、許容幅、日付、出所)を README の「照合」に書く。発表済みの値と違えば、論文はここで
    作り直した値を使うこと、差と理由を書き、意思決定記録を提案する。

11. **記録を閉じる。** `summary.md` の答え・言えないこと・本実行・関連を書き(`out/params_used.json` から)、
    状態を「完了」にし「残りの手順」を消す。索引の状態を「完了」、「一行で」に答えの要点、論文に章のラベル、
    由来に「取り込み(R2)」などを書く。ここまでを同じコミットにする。research-template 形式なら、関係する旧
    guardrails・ideas の行を「スタディ」と `<repo>@<sha>` 付きで `docs/guardrails.md`・`docs/ideas.md` に写す。

12. **章につなぐ。** 図は `\includegraphics{<name>}`、表は `\input{../projects/<study>/result/tables/<name>}`。
    値のファイルは `draft/values.tex` の終わりの目印より上に `\ThesisValues{../projects/<study>/result/tables/<name>}`
    を足し、本文では `\val{<name>-<key>}`。`make pdf` の後に `make check` を実行し、W11・W14・W15 が出ないこと、
    R3 が I3 に挙がることを確かめる(W14 は取り込み実験が「進行中」の間も出る)。W15 が出たら、コードを
    コミットして `run.py --overwrite` で実行し直す。`docs/thesis-plan.md` の主要な根拠・基になる論文を更新し、
    `STATE.md` の待ちの行を消す(`write-handoff` スキル)。

## 報告

取り込んだ実験(`projects/<study>/experiments/NNN_<slug>`)、成果物ごとの再現性、照合の結果、R3 の一覧、
章で使った名前、ユーザーに残っている作業(コピー、ライセンスの確認など)を短くまとめる。
