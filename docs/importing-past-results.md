# これまでの実験結果を取り込む

別のリポジトリ・フォルダ・論文に残っているこれまでの実験結果を、由来と再現性を記録したままスタディに取り込み、論文の章の根拠にする手順です。エージェントは `import-results` スキルでこの手順を進めます。規約の要点は `AGENTS.md` の「過去の結果の取り込み」にあります。

## 原則

- **過去のファイルは生データとして扱う。** コピーした後は編集・削除・追加しない。コピーするのはユーザーで、エージェントはコマンドを示すだけ(頼まれても実行しない)。
- **1つの主張を支える1組の結果ごとに、取り込み実験を1つ作る。** 図1枚ごとにも、古いリポジトリ丸ごとにも作らない。
- **再現性は生成物ごとに決める**(下の R1/R2/R3)。決めた理由は実験の README に、レベルは生成物の由来記録に残る。
- **取り込み実験が「完了」になるまで本文で使わない。** `run.py` は `experiment.start()` の中で、入力のマニフェストとの照合(`verify_inputs`)と既に報告した数値との照合(`crosscheck`)が通ってから生成物を書き、照合に失敗した実行は `result/` を変えない(`make check` の W14 は「進行中」の取り込み実験の生成物も知らせる)。
- **由来はファイルに書く。** チャットにだけ残った情報は、次のセッションでは失われる。

## 再現性のレベル

レベルは生成物(図・表・数値のファイル)ごとに、由来記録 `<name>.provenance.json` の `reproducibility` に入ります。

| レベル | 意味 | 典型例 |
|---|---|---|
| R1 再計算可能 | 入力とコードからここで計算し直し、元の出力と一致を確かめた(`crosscheck`) | 旧リポジトリのスクリプトを移植して再実行 |
| R2 再描画可能 | 残っている数値の出力(CSV・JSON など)から、図表をここでコードから作り直した。計算は再実行していない | 旧 `results/*.csv` から図を作り直す |
| R3 再生成不可 | 画像をそのまま載せた、または論文などから数値を書き写した | 装置が出力した画像、元データが失われた図、論文の表にしか無い数値 |

- 原理的には計算し直せても、ここで再実行していなければ R2 です(理由を README に書く)。
- R3 は意識して残す例外です。`make check` の I3 が R3 の生成物を一覧にするので、指導教員と確かめ、作り直すか、そのまま載せるかを決めます。

## 置き場所

```text
projects/<study>/
├── data/raw/legacy/<source>/                    # 過去の出力(ユーザーがコピー。不変・Git 管理外)
│   └── code/                                    # 非公開の旧コードのスナップショット(任意)
├── data/raw/<dataset>/                          # 過去・新規の入力データ(台帳に通常の行)
├── data/interim/acquired/<dataset>/             # コードがダウンロードしたもの(ユーザーが raw へ移す)
├── data/interim/NNN_<slug>/inputs_verified.json # 照合の記録(作り直せる)
├── data/README.md                               # データ台帳(「過去の結果」の層)
└── experiments/NNN_<slug>/                      # 取り込み実験(make experiment-import)
    ├── summary.md                               # 今の結論・照合・残りの手順
    ├── README.md                                # 由来・成果物ごとの再現性・照合の経緯・取り込み元とコマンド
    ├── params.py                                # SOURCE_DIR・MANIFEST・RECORDED_SHA256・REFERENCE_VALUES・TRANSCRIBED(PARAMS にまとめる)
    ├── inputs.sha256                            # 入力のマニフェスト(生成してコミットする)
    ├── run.py                                   # 入力の照合 → 作り直し → 既報の数値との照合 → 生成物
    └── out/                                     # params_used.json など(Git 管理外)
```

- `<source>` は出どころが分かる名前にします(例: `logger-drift_runs_2026-07`)。省略すると slug の `_` を `-` にした名前になります。
- `legacy/` には過去の**出力**だけを置きます。計算し直すための**入力**データは `data/raw/<dataset>/` に置き、他の実験からも使える通常のデータとして台帳に書きます。
- 共有する生データは1つのスタディが持ち、他のスタディは台帳にパスと sha256 で参照します。
- リポジトリに置けないデータ(大きすぎる、外へ出せない)は、ホストのフォルダをコンテナの `/external` に読み取り専用で付け、`SOURCE_DIR = Path("/external/<source>")` のようにそこへ向けます(`docs/integrations.md`)。付け方は、利用者が `.env` に `EXTERNAL_FILES_DIR=<ホストの絶対パス>` と `COMPOSE_FILE=docker-compose.yml:docker-compose.files.yml`(GPU も使うなら `docker-compose.yml:docker-compose.gpu.yml:docker-compose.files.yml`)を一度書き、実行中のジョブが無いことを確かめて `make up` します。`.env` に書いておけば、後の `make up` やコンテナの自動起動でも外れません。`/external` はコンテナの中にしか無いので、マニフェストはコンテナの中で作ります(手順 4)。マニフェストは同じく `experiments/NNN_<slug>/inputs.sha256` に置き、台帳に保管場所(バックアップ)を書きます。

## 手順

### 0. 何が残っているかを調べる

読むだけの操作で、次を確かめます(エージェントが行ってよい)。

- どこにあるか。Git のリポジトリなら、そのコミット(`git -C <repo> rev-parse HEAD`)と未コミットの変更の有無(`git -C <repo> status --porcelain`)。
- 何が残っているか: 入力データ / コード / 数値の出力 / 画像 / 論文中の数値だけ。
- どの実行が正式か。実行が複数あるなら、報告・発表に使った1回はどれか。サンプル・デモ・合成データの出力はどれか。
- 大きさとファイル数(`du -sh`、`find <path> -type f | wc -l`)。1 MB を超える図があるか。
- 既に発表したか(論文・学会)、ライセンスや共同研究者の同意が要るか。
- research-template 形式のリポジトリなら、先に `STATE.md`・実験の索引(`experiments/EXP_SUMMARY.md`、古いリポジトリでは `exp/EXP_SUMMARY.md`)・`docs/guardrails.md` を読む(下の「ケース A」)。

### 1. スタディを決める

既存のスタディに入れるか、新しく作ります(`TITLE='…' make study NAME=<study>`)。どの研究課題・章の根拠にするかを `docs/thesis-plan.md` で確かめます。

### 2. 取り込み実験を作る

```bash
make experiment-import STUDY=<study> SLUG=<slug> SOURCE=<source> FROM=<過去の結果のパス>
# 旧リポジトリの番号付き実験なら LEGACY_ID=<repo>@<sha>:experiments/NNN_<old_slug> も付ける
# (古いリポジトリでは <repo>@<sha>:exp/NNN_<old_slug>)
# 直接呼ぶ場合: python3 tools/new_experiment.py <study> <slug> --import --source <source> --from <path> [--legacy-id …] [--summary …]
```

- `projects/<study>/experiments/_import_template/` から `experiments/NNN_<slug>/` を作り、索引に `| NNN | slug | (実行前) | 進行中 | — | 取り込み |` の行を足します。`summary.md` には「残りの手順」が、README には「取り込み元とコマンド」が入ります。
- 「残りの手順」は状態が `進行中` の間だけ置くチェックリストです。セッションが途中で切れても、`summary.md` から再開できます。
- `--legacy-id` を付けると、旧実験の ID が README の「元の実験」と `summary.md` の「元の実験」に入ります(索引には入りません)。
- コピーのコマンド、マニフェストを作るコマンド、README と台帳に書くことが表示されます。

### 3. ユーザーが過去のファイルをコピーする

リポジトリのルートで、**ユーザーが自分の端末で**実行します。

```bash
mkdir -p projects/<study>/data/raw/legacy/<source>
rsync -a --copy-unsafe-links --exclude .git --exclude .venv --exclude __pycache__ \
  --exclude .DS_Store --exclude '._*' <PATH>/ projects/<study>/data/raw/legacy/<source>/
```

- エージェントはこのコマンドを実行しません。生データの置き場に書くのは本人だけです。Claude Code ではフックと拒否設定が止め、コンテナの中では読み取り専用ですが、ホストで動く Codex などは仕組みでは止まらないので、エージェントが自分で避けます。
- 正式な実行の出力だけを写します(例: `<PATH>` を `results/runs/<日時>` にする)。サンプル・デモの出力は写さないか、`--exclude` で外します。写したファイルはすべてマニフェストに入り、照合の対象になります。
- `--copy-unsafe-links` は、外を指すシンボリックリンクを実体として写します。
- 写し間違えたときは、ユーザーがそのディレクトリを消して写し直し、マニフェストを作り直します。

### 4. マニフェストを作る

```bash
(cd projects/<study>/data/raw/legacy/<source> && find . -type f ! -name .gitkeep -print0 \
  | LC_ALL=C sort -z | xargs -0 sha256sum) > projects/<study>/experiments/NNN_<slug>/inputs.sha256
```

- raw を読むだけで、書くのは raw の外なので、エージェントが実行してよい。ハッシュを手で打たない。マニフェストはコミットします。マニフェストが無いまま `run.py` を実行すると、このコマンドを表示して止まります。
- `SOURCE_DIR` が `/external` の下にあるときは、`/external` がコンテナの中にしか無いので、同じコマンドをコンテナの中で動かします。ホストのリポジトリのルートで次を実行します(`run.py` もこの形を表示します。書き出し先の `projects/...` はコンテナの作業場所 `/workspace` からの相対パスで、ホストの同じファイルになります)。ホストでは、そのフォルダは `.env` の `EXTERNAL_FILES_DIR` が指すフォルダの下にあります。

  ```bash
  docker compose exec -T research-template bash -c '(cd /external/<source> && find . -type f ! -name .gitkeep -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) > projects/<study>/experiments/NNN_<slug>/inputs.sha256'
  ```

  ホストで `cd /external/...` を実行すると、ディレクトリが無いので失敗し、空のマニフェストだけが残ります。
- **マニフェストに入るファイル名は公開されます。** マニフェスト(と、後で由来記録の `sources`)には、写したファイルの相対パスがそのまま入り、コミットすると公開リポジトリに載ります。コミットの前に `inputs.sha256` のファイル名を確かめ、人名・参加者 ID・施設名など公開できない情報があれば、コミットせずにユーザーに伝えます。ユーザーがそのディレクトリを消し、名前を付け替えて写し直し(元の名前との対応表は Git の外に保管する)、マニフェストを作り直します。
- 写した内容が元と同じかは、元の場所で確かめられます。

  ```bash
  m="$PWD/projects/<study>/experiments/NNN_<slug>/inputs.sha256"; (cd <PATH> && sha256sum --quiet -c "$m")
  ```

  何も表示されなければ一致しています。
- 古いツールが自分でハッシュを記録していた場合(`run_meta.json` など)は、**`SOURCE_DIR` の中に写したファイルのハッシュだけ**を `params.py` の `RECORDED_SHA256` に写します(キーはマニフェストと同じ相対パス)。`verify_inputs` がマニフェストと突き合わせ、マニフェストに無い名前があると止まります。入力データのハッシュ(例: `run_meta.json` に記録された、計算に使った入力ファイルのハッシュ)は `RECORDED_SHA256` に入れません。その入力を置いた `data/raw/<dataset>/` の台帳(`data/README.md`)の「チェックサム」と照らし合わせ、結果を README の「由来」に書きます。

### 5. 由来を書く

実験の `README.md` の「由来」に次を書きます(ユーザーに確かめてから)。

- **元のリポジトリ・コミット**: `<repo>@<sha>`。**元の場所**: `<repo>@<sha>:<リポジトリ内のパス>`(ホストの絶対パスは書かない。Git でなければ保管場所の説明と、その中の相対パス)。**元の実験**(旧リポジトリの実験 ID。あれば)。
- **実施時期**とその決め方、**実施者**、**実行環境**(OS・言語とライブラリの版・計算機)。
- **元のコードの状態**: clean | dirty | 不明。**コミットの特定方法**: run_meta(旧ツールの実行記録) | 更新日時と git log の照合 | 不明(確かさも)。
- **取り込んだ範囲**: 正式な実行。置き換えられた実行・合成データの出力は、外した理由と一緒に挙げる(合成・デモの出力は結果ではない)。
- **入力マニフェスト**: `inputs.sha256`。**公開可否・ライセンス**、**バックアップ先**(原本の保管先。`data/raw/` は Git に入らない)。
- 「成果物ごとの再現性」の表(`| 成果物名 | 種類 | 再現性 | 根拠 |`)と、「照合」の経緯(比較した日付、参照した出所、食い違いの調査。数値そのものは `summary.md` の「照合」と `result/tables/` の `…-crosscheck.csv`)。

状態は索引と `summary.md` に同じ語で書き(テストが一致を検査します)、README には書きません。問いと判定の規則も `summary.md` に書きます。あわせて `projects/<study>/data/README.md` の台帳に、一覧の行と「過去の結果(legacy)の記録」のブロックを足します(元の場所、実施時期、実施者、生成コードとコミット、再現性、取り込み実験 `experiments/NNN_<slug>`、ライセンス・公開可否、バックアップ先、マニフェストとその sha256)。

### 6. `params.py` を埋める

| 名前 | 中身 |
|---|---|
| `SOURCE_DIR` | 過去の出力の場所(既定は `config.RAW_DATA_DIR / "legacy" / "<source>"`) |
| `MANIFEST` | `inputs.sha256`(この実験のディレクトリ) |
| `RECORDED_SHA256` | 古いツールが記録した、`SOURCE_DIR` の中のファイルのハッシュ(マニフェストと同じ相対パス → 16進)。入力データのハッシュは入れない(手順 4) |
| `REFERENCE_VALUES` | 既に報告した数値。`{"<key>": {"value": 0.42, "rtol": 0, "atol": 0.005, "source": "smith2024ocean, Table 2"}}`。キーは run.py が作る値の名前 |
| `TRANSCRIBED` | 論文にしか残っていない数値(ケース D) |
| `TRANSCRIBED_SOURCE`・`TRANSCRIBED_FORMATS` | その出典(`"<bibキー>, Table 2"` など)と、実数ごとの書式(`{"rmse": "{:.2f}"}`) |

これらは `params.py` の末尾の `PARAMS` にまとまり、`run.py` は `run.params` から読みます(`SEED` と一緒に `out/params_used.json` に残ります)。`SMOKE` は空のままで構いません。`--smoke` も同じファイルで全段階を通し、何も公開しません。

### 7. `run.py` を実装して実行する

`run.py` は `with experiment.start(__file__, params) as run:` の中で、次の段階を順に進みます。照合(1 と 3)で止まれば実行は `failed` になり、`result/` は変わりません。

1. **入力の照合**: `verify_inputs` で入力をマニフェストと照合する。ファイルの過不足、ハッシュの不一致、`RECORDED_SHA256` との食い違いで止まる。照合の記録は `data/interim/NNN_<slug>/inputs_verified.json` に残り(作り直せる)、次の実行は変わっていないファイルを読み直さない。
2. **作り直し**: レベルに応じて、図・表・数値をメモリの中か `run.out()` で `out/` に作り、照合する値を `actual` に入れる。
   - **R1**: 旧コードの計算を `src/` に移して呼ぶか(ケース A)、旧コードのスナップショットを別のプロセスで、出力先をすべて `run.out_dir` に向けて実行し(ケース B)、計算し直した数値を `actual` に入れる。
   - **R2**: 残っている数値(CSV・JSON など)を読んで図表と値を作り、読んだ値を `actual` に入れる。
   - **R3**: 取り込む画像を選ぶ(ケース C)。論文中の数値は `TRANSCRIBED`(ケース D)。
3. **既報の数値との照合**: `REFERENCE_VALUES` があれば `crosscheck` で `actual` と照合する。合わなければここで止まる。照合の表は `run.out()` で `<study>-<slug>-crosscheck.csv` に書き、`run.promote()` で出す(本実行が通ると `result/tables/` に入る)。
4. **生成物を書く**: `save_figure`・`write_latex_table`・`write_latex_values` を `provenance={"reproducibility": "R1", "sources": sources}`(R2 なら `"R2"`)付きで呼び、R3 の画像は `import_figure` で、`TRANSCRIBED` は値のファイルとして書く。`sources` は読んだ過去のファイルの一覧で、`src.utils.provenance.source_entry(params.SOURCE_DIR / name, config, sha256=verified[name])` で作る。照合表を付録に載せるなら、ここで `write_latex_table` で書く(名前は `…-crosscheck` とは別にする。1回の実行で同じ名前は1度しか書けない)。

- 生成物の名前は `<study>-<slug>-<内容>`(slug は実験名の `_` を `-` にしたもの。`run.py` の `PREFIX`)。
- ヘルパーと `run.promote()` が書いたものは実行中は `out/staged/` に置かれ、本実行が最後まで通ったときだけ `result/` にまとめて入ります(`projects/<study>/experiments/README.md`)。実装の途中は `--smoke` で通します。照合に失敗した実行と `--smoke` は `result/` を変えないので、前に出した生成物はそのまま残ります。

**論文に使う実行の前にコミットします。** 由来記録には実行を始めた時点のコミットが入り、未コミットのコードや実行中に変わったコードで書いた生成物は `git_dirty` になり、`make check` の W15 が出ます。ここでのコードは、このスタディの `src/`・`scripts/`・`config.py`・`experiments/` の `.py` と、リポジトリのルートの `config.py`・`pyproject.toml`・`uv.lock` です(README・`summary.md`・台帳・原稿・`result/` の未コミットの変更は数えません)。まず `--smoke` で通し、`run.py`・`params.py`・`inputs.sha256` と変えたコードをコミットして、`git status` でコードに未コミットの変更が無いことを確かめてから本実行します。照合が通らなければ実行は失敗し、`result/` は変わりません。完了した本実行をやり直すときは `--overwrite` を付けます。実行は Docker で:

```bash
docker compose exec research-template uv run python projects/<study>/experiments/NNN_<slug>/run.py --smoke
docker compose exec research-template uv run python projects/<study>/experiments/NNN_<slug>/run.py
```

照合が合わないときは、許容差を黙って広げません。原因(乱数の種、ライブラリの版、入力の違い)を調べ、分かったことを README に書きます。解決しなければ R2 に下げ、理由を書きます。

### 8. 記録を閉じる

照合が通った本実行の後に、次を**同じコミットで**行います。本文で使えるのは、この後です。

- `summary.md` に答え・言えないこと・照合・本実行・関連を書き(本実行は `out/params_used.json` の `started`・`git.short`・`elapsed_s`・`code_state` から、昇格した生成物は `promoted` から写す)、状態を `完了` にして「残りの手順」を消す。
- 索引の行の状態を `完了` に、「一行で」に答えの要点を、「論文」に使う章のラベル(`ch:<study>`)を、「由来」に `取り込み(R2+R3)` などを書く。
- README の「結果」と「照合」に経緯を日付つきで足す。
- `result/` の生成物(1 MB 以下)と、これらの記録の更新をコミットする(コードとマニフェストは手順 7 でコミット済み)。

### 9. 章につなぐ

- 図: `\includegraphics{<study>-<slug>}`。表: `\input{../projects/<study>/result/tables/<name>}`。
- 数値: 値のファイルを `draft/values.tex` の終わりの目印より上に `\ThesisValues{../projects/<study>/result/tables/<name>}` で登録し、本文では `\val{<name>-<key>}`。
- `make pdf` の後に `make check` を実行し、W11(由来なし・不一致)、W14(撤回・中止・置き換え・進行中の実験の生成物)、W15(未コミットのコード)が出ないこと、R3 が I3 に挙がることを確かめます。
- W15 が出たら、コードをコミットしてから `run.py --overwrite` で実行し直し、もう一度 `make check` を実行します(手順 7)。
- `docs/thesis-plan.md` の「主要な根拠」(図表・値の名前)と「基になる論文」を更新し、`STATE.md` の待ちの行を消す。

## 取り込む単位と選び方

- 1つの主張を支える1組の結果を、1つの取り込み実験にします。同じ解析の複数の図は1つの実験から作ります。
- 使うのは正式な1回の実行です。置き換えた実行・失敗した実行・設定を試した実行は、写さずに README の「取り込んだ範囲」で理由と一緒に挙げます。
- 合成データ・サンプル・デモの出力は、形が本物に似ていても結果として扱いません。
- 古い記録で撤回・中止になっている結果は、ユーザーが決めない限り取り込みません。取り込むと決めたら、その判断と理由を README に書きます。
- ここで作り直した値が発表済みの値と違うときは、論文はここで作り直した値を使います。差とその理由を README の照合と章の冒頭のコメントに書き、意思決定記録(`docs/decisions/`)を残します。

## ケース別の手順

### A. research-template 形式のリポジトリ

番号付きの実験のディレクトリ、`STATE.md`、実験の索引 `EXP_SUMMARY.md`、`docs/guardrails.md` があるリポジトリです。版によって置き場所が違います。

| 版 | 実験 | 索引 | config の名前 |
|---|---|---|---|
| 今の research-template | `experiments/NNN_<slug>/`(各実験に今の結論と状態を書いた `summary.md` がある) | `experiments/EXP_SUMMARY.md` | `config.EXPERIMENTS_DIR` |
| 古い research-template | `exp/NNN_<slug>/` | `exp/EXP_SUMMARY.md` | `config.EXP_DIR` |

`docs/guardrails.md`・`docs/ideas.md` は、リポジトリによっては `docs/GUARDRAILS.md`・`docs/IDEAS.md` のように大文字の名前です。

1. 先に旧リポジトリの `STATE.md`・実験の索引・`docs/guardrails.md`・`docs/ideas.md` と、候補の実験の `summary.md`(あれば)を読み、取り込む候補の実験の状態(撤回・訂正・中止・置き換え)を確かめる。
2. 撤回・中止の実験は黙って取り込まない(上の「選び方」)。旧状態が `置き換え` の実験は取り込まず、置き換えた実験を取り込む。
3. 候補ごとに `make experiment-import … LEGACY_ID=<repo>@<sha>:experiments/NNN_<old_slug>`(古い版では `…:exp/NNN_<old_slug>`)。旧番号はそのまま新しい番号にせず、README の「元の実験」と `summary.md` の「元の実験」で対応を残す。
4. 旧実験の `out/` は旧リポジトリでも Git 管理外なので、残っている作業コピーから写す(ユーザー)。旧 `result/` のコミット済みの図表も同様。旧実験に `out/params_used.json` があれば実行の記録として読む(`status` が `completed` で `smoke` が false のものだけ。`git.commit` と `git.dirty` は「元のコードの状態」、`seed` と `params` は再現の条件)。
5. コード: 旧コードの `import config` と `config.PROJECT_ROOT`・`EXPERIMENTS_DIR`・`EXP_DIR`・`DATA_ROOT`・`RAW_DATA_DIR`・`FIGURE_DIR` はスタディの `config.py` でもそのまま動く(下の「スタディの config との違い」)。再利用するロジックは `projects/<study>/src/` にテストとともに移し、新しい `run.py` から呼ぶ。旧実験の `run.py` は、自分のディレクトリの `out/` に書くので、そのままでは動かない(取り込んだコピーは読み取り専用)。ロジックを `src/` へ移す。新しい `run.py` は `experiment.start()` の中で動き、ヘルパーと `run.promote()` が書いたものは本実行が通ったときだけ `result/` に入る(`projects/<study>/experiments/README.md`)。
6. 旧 `docs/guardrails.md`・`docs/ideas.md` の関係する行を、このリポジトリの `docs/guardrails.md`・`docs/ideas.md` に写す。「スタディ」の列を埋め、根拠の列に `<repo>@<sha>` を書く。
7. 旧リポジトリの意思決定記録・研究ログは写さず、`<repo>@<sha>:<path>` でリンクする。
8. 旧リポジトリのコミット済みの CSV にある数値を `REFERENCE_VALUES` にし、計算し直して照合できれば R1。旧 `summary.md` の主な数値の出所を `REFERENCE_VALUES` の候補にし、旧「言えないこと」を新しい `summary.md` に引き継ぐ。

### B. スクリプトと `results/` フォルダがあるリポジトリ

よくある形: `scripts/`・`src/` と、`results/runs/<日時>/{*.csv, summary.json, *.png, config.yaml, run_meta.json}`、デモ用の `results/sample/`。

- **コミットを特定する。** `run_meta.json` などに記録があればそれを使う。無ければファイルの更新時刻と `git log` を照らし合わせ、方法と確かさを書く。`git status --porcelain` に変更が出るなら、そのコミットのコードが実際に動いたとは限らない(元のコードの状態 dirty・不明)。
- **R2(多くの場合はこちら)**: 正式な実行の数値の出力を写し、`run.py` が CSV・JSON を読んで図表と値を作り直す。`summary.json` などに記録された値を `REFERENCE_VALUES` にして、読んだ値が報告と同じかを照合する。古い PNG は、作り直せない場合だけ R3 で取り込む。
- **R1**: 入力・コード・実行環境が揃うときだけ。
  - 入力は `data/raw/<dataset>/` に置く(ユーザー)。R1 の再実行のために入力を取り直さない。保管したコピーを使う。
  - 旧コードの扱いは次のどれか。
    1. 公開されたパッケージ: `docker compose exec research-template uv add 'pkg @ git+https://…@<40桁のコミット>'`、続けて `make lock && make build`(実行中のジョブが無いことを確かめて `make up`)。
    2. 非公開のコード: ユーザーがスナップショットを作る。`mkdir -p projects/<study>/data/raw/legacy/<source>/code && git -C <repo> archive <sha> | tar -x -C projects/<study>/data/raw/legacy/<source>/code/`。`run.py` は旧い入口を**別のプロセスで**、そのまま動かす。`sys.path` に入れて import しない。`run.py` は既にこのスタディの `config`・`params`・`src` を読み込んでいるので、旧コードの同じ名前のモジュール(research-template 形式なら `config.py`・`src/`・`params.py`)がこのスタディのものにすり替わり、import が失敗するか、黙って違う値で動く。

       ```python
       import os
       import subprocess

       CODE = config.RAW_DATA_DIR / "legacy" / "<source>" / "code"
       subprocess.run(
           [sys.executable, str(CODE / "scripts" / "<入口>.py"), "--out", str(run.out_dir)],
           cwd=run.out_dir,  # 取り込んだコピーは読み取り専用なので、作業場所は out/
           env={**os.environ, "PYTHONPATH": str(CODE)},
           check=True,
       )
       ```

       出力先は引数か設定で `run.out_dir` に向ける(`--out` は例。旧い入口の引数に合わせる)。自分のディレクトリの隣に書く入口(research-template の実験の `run.py` など)は、そのままでは動かないので、ロジックを `src/` へ移す(ケース A の 5)。再現性の根拠に「R1(非公開コード)」と書く。マニフェストはコードを写した後に作る(コードも照合の対象になる)。
    3. 許諾を得て取り込む: `projects/<study>/src/vendor/<pkg>/` に変更せずに置き、`VENDORED.md` に出どころ・コミット・ライセンスを書く(ruff の対象外)。整理は再現が一致してから。
  - 足りない外部ライブラリは `uv add`(Docker 内)の後に `make lock && make build` でイメージに入れ、実行中のジョブが無いことを確かめて `make up`。
  - 旧コードに自分のディレクトリや raw へ書かせない。出力先の引数や設定で `run.out_dir` に向ける。実行後に `git status` を見て、`out/` と意図した `result/` の生成物の他に変更が無いことを確かめる。
  - `crosscheck` で元の出力と一致したら R1。一致しない理由が分からなければ R2 に下げる。

### C. 画像しか残っていない

```python
from src.utils.figures import import_figure

import_figure(
    params.SOURCE_DIR / "fig3.png", "<study>-<slug>", cfg,
    note="装置の解析ソフトが出力した図。元の数値は残っていない",
    license="自作(未発表)",
)
```

- 再現性は常に R3。`note` に何を示す図か、なぜ作り直せないかを、`license` に権利(自作、出版社、第三者)を書く。既発表の図は出版社の規程を確かめ、転載の許諾を記録する。
- `.png`・`.pdf`・`.jpg`・`.jpeg` はそのまま。`.tif`・`.gif`・`.bmp`・`.webp` は `convert_to_png=True` で PNG にする(最初の1枚。変換元は由来記録に残る)。
- 取り込める大きさは 1 MB まで(追跡するファイルは 1 MB までに制限している)。大きい画像は `run.py` の中で縮小・圧縮した版を `out/` に作って渡し、方法を `note` に書く。`out/` に作った版を渡すときは、照合済みの元のファイルを `sources=[source_entry(params.SOURCE_DIR / "fig3.tif", cfg, sha256=verified["fig3.tif"])]` で一緒に渡す(`source_entry` は `src.utils.provenance`)。由来記録の `sources` には元のファイルが、`copied` には実際に写した `out/` のファイルが入る。図はできればベクトルの PDF にする。

### D. 数値が論文にしか残っていない

```python
TRANSCRIBED = {"rmse": 0.42, "n": 120}
TRANSCRIBED_SOURCE = "smith2024ocean, Table 2"
TRANSCRIBED_FORMATS = {"rmse": "{:.2f}"}
```

- 論文の数値しか残っていなければ、`SOURCE_DIR = None` にする(コピーとマニフェストは要らない)。
- `run.py` が `<study>-<slug>-transcribed` という値のファイルを R3(`transcribed_from` 付き)で書く(slug は `_` を `-` にしたもの)。`draft/values.tex` に登録し、本文では `\val{<study>-<slug>-transcribed-rmse}` と書く。
- 書き写すのは一度だけ、原典の PDF から。可能なら別の人が確かめる。出典の書誌は DOI で照合し、`verified` の欄を付ける。
- 本文では、その数値が発表済みの論文からのものであることを引用で示す。

### E. アニメーション・HTML・3次元モデル

- 元のファイルは `data/raw/legacy/<source>/` に置いたままにする(論文は静的な PDF)。`result/animations/` は Git 管理外。
- 論文に載せる静止画はコードで作る。元の数値(軌跡の CSV など)が残っていれば、そこから図を作り直す(R2)。画像しか無ければ、`run.py` で選んだコマを `out/` に書き出して `import_figure` に渡す(R3)。元の動画を `sources=[source_entry(...)]` で渡す(ケース C と同じ)。
- 動画そのものを審査員に見せる必要があるなら、補足資料かデータの公開先(DOI)に置き、本文から参照する。

## 既発表・投稿中の論文を章にする

上から順に進めます。

1. **原稿のソース**: LaTeX なら、`make study` が作った `chapters/NN-<study>.tex` へ本文を移す。Word の原稿は手で移すか、pandoc を入れてから変換する(この環境に pandoc は入っていない)。
2. **書誌**: 論文の `.bib` を `draft/reference.bib` に統合し、キーを `authYYYYfirstword` にそろえる。各項目を DOI で原典と照合して `verified` の欄を付け、本文の引用キーも直す(DOI の重複は W13 が挙げる)。
3. **ラベル**: `ch:<study>`・`sec:<study>-…`・`fig:`・`tab:`・`eq:` に付け替え、参照を `\cref` にする。
4. **図表と数値**: 図は `<study>-<slug>` の名前で、スタディのコードで作り直すか(R1・R2)、`import_figure`(R3)で取り込む。本文の数値は `\val` にする。
5. **論文に固有の部分**: 論文の要旨は、必要なら章の冒頭の `\section*{Chapter Abstract}` に。謝辞(研究費など)は論文全体の謝辞へ、データの利用可能性の記述は章か付録へ移す。
6. **重複を削る**: 序論・方法の繰り返しは、総合序論や背景章へまとめ、`\cref` で参照する。
7. **発表版との違い**: 論文はここで作り直した値を使う。違いとその理由を、章の冒頭の `% Differences from the published version:` のコメントと README の照合に書き、意思決定記録を残す。
8. **再利用と著作権**: 章の冒頭(章の雛形のコメント)に、出版の状況、完全な引用(`\cite`)、著者の貢献、転載の許諾を書く。出版社の規程で学位論文への再利用が認められているかを確かめる。`frontmatter/publications.tex` と一致させる。
9. **論文計画**: `docs/thesis-plan.md` の「基になる論文」に bib キーを書く。

## スタディの config との違い

research-template 形式のコードを移すときの注意です。

- `import config` で読むのはスタディの `config.py`。`PROJECT_ROOT` はスタディのルート(`projects/<study>/`)で、リポジトリのルートではない。`EXPERIMENTS_DIR`(今の research-template の名前)と `EXP_DIR`(古い名前)はどちらもスタディの `experiments/` を指し、`RAW_DATA_DIR`・`FIGURE_DIR`・`TABLE_DIR` もスタディの中を指す。
- `DRAFT_DIR` は無い。原稿へ書き出していたコードは、`write_latex_values`・`write_latex_table` で `result/tables/` に書くように直す。
- `config.RANDOM` は無い。シードを含め、結果を変えうる値はすべて実験の `params.py` に固定する(例: `SEED = 42`)。`config.py` にあるのは場所と、論文全体で図の見た目をそろえる `VISUALIZATION`、物理定数の `GEO` だけ。
- `/data` のマウントは無く、`DATA_ROOT` は `RAW_DATA_DIR` と同じ。環境変数 `DATA_ROOT` は使わない。
- 書き込みは `*_DIR` の下だけ。図表の名前には `<study>-` を付ける(W16)。`FIGURE_DIR` へファイルをコピーしていた昇格は、由来記録が付くよう `save_figure`・`import_figure` に置き換える(W11)。
- 実験の `run.py` は冒頭で `STUDY_ROOT = Path(__file__).resolve().parents[2]` を `sys.path` に入れる(`experiments/NNN_<slug>/run.py` からスタディのルート)。

## してはいけないこと

- 過去の図を `draft/figures/` に置いて、由来の記録と照合を飛ばす(`draft/figures/` は手作りの図だけ)。
- 古い数値を本文に打ち込む(`\val` を使う)。
- `data/raw/legacy/` の中のファイルを編集・削除・追加する。写し直すときはユーザーが行い、マニフェストを作り直す。
- ハッシュを手で書く。照合を外して `run.py` を通す。照合が済む前に生成物を書く。取り込み実験が `完了` になる前に本文で使う。
- 人名・参加者 ID・施設名などを含むファイル名のまま、マニフェストや由来記録をコミットする(公開リポジトリに載る)。
- 撤回・中止された過去の実験を黙って取り込む。合成・デモの出力を結果として使う。
- エージェントが raw へのコピーを実行する(頼まれても)。
- ホストの絶対パスを README・台帳・コードに書く。1 MB を超えるファイルをコミットする。
