# データ台帳(study1)

> **鉄則**: `data/raw/` は不変です(手で編集しない・上書きしない。Docker の中では読み取り専用)。raw に置くのは利用者で、ホストでコピーします。大きなデータは Git に入らないので、**このファイルに「どこから来たか」と「どう取り戻すか」を必ず書き残します**。ここが空のままだと、別のマシンや将来の自分がデータを復元できず、論文の数値の出所も示せません。

## 置き場所

| 層 | 場所 | 中身 | 置くのは |
|---|---|---|---|
| raw | `data/raw/<dataset>/` | 入力データ(観測・取得・提供されたデータ。過去に集めたものも含む) | 利用者(ホストでコピー) |
| legacy | `data/raw/legacy/<source>/` | 過去の結果(旧リポジトリや旧 PC の出力・図・ログ)。取り込み実験が検証してから使う | 利用者(ホストでコピー) |
| acquired | `data/interim/acquired/<dataset>/` | コードがダウンロードしたもの(マニフェスト付き)。確かめた後、利用者が `data/raw/<dataset>/` へ移す | コード |
| interim | `data/interim/` | 中間データ | スクリプト |
| processed | `data/processed/` | 解析用データ。実験の大きな出力は `data/processed/NNN_<slug>/` | スクリプト |
| 外部 | `/external/...`(`.env` に `EXTERNAL_FILES_DIR` と、`docker-compose.files.yml` を含む `COMPOSE_FILE` を書いて `make up` すると、コンテナの中で読み取り専用に見える。手順は `docs/integrations.md`) | リポジトリに置けないデータ | 利用者 |

- `<dataset>` と `<source>` は小文字・数字・`-`・`_` の短い名前にする。legacy の `<source>` は由来が分かる名前にする(例: `logger-drift_runs_2026-07`)。
- コードがダウンロードしたデータを raw に移すコマンドは、ダウンロードしたスクリプトが表示する。利用者がホストで実行する(例):

  ```bash
  mkdir -p projects/study1/data/raw/<dataset>
  rsync -a projects/study1/data/interim/acquired/<dataset>/ projects/study1/data/raw/<dataset>/
  ```

- 過去の結果を計算し直す(R1)ときは、入力を再ダウンロードしない。保存しておいた写しを使う(配布元の版が変わっていることがある)。

## データセット一覧

| データセット名 | 層 | 場所 | 生成元(入手先・生成スクリプト・取り込み実験) |
|---|---|---|---|
| (例) sst_monthly | raw | `data/raw/sst_monthly/` | NOAA OISST v2.1 からダウンロード |
| (例) sst_anomaly | processed | `data/processed/sst_anomaly/` | `scripts/build_sst_anomaly.py` |
| (例) logger-drift_runs_2026-07 | legacy | `data/raw/legacy/logger-drift_runs_2026-07/` | 旧リポジトリの出力。`experiments/003_logger_drift` で取り込み |

---

## 入力データの記録

データセットを追加するたびに、次のブロックをコピーして記入する。

### <データセット名>

- **層**: raw / acquired / interim / processed
- **場所**: `data/raw/<dataset>/`
- **入手先**: URL・DOI・提供者の連絡先など
- **取得日**: YYYY-MM-DD
- **ライセンス・利用条件**:
- **公開可否**: (このデータや、そこから作った図表を公開リポジトリと論文に載せてよいか)
- **バージョン**:
- **サイズ**: (`du -sh projects/study1/data/raw/<dataset>` の結果)
- **チェックサム**: (1ファイルなら `sha256sum` の結果。多数なら下のマニフェスト生成コマンドの出力を `data/manifests/<dataset>.sha256` に保存してコミットし、そのパスを書く。マニフェストのファイル名は公開リポジトリに載るので、コミットの前に人名・参加者 ID・施設名などが無いことを確かめる)
- **バックアップ先**: (原本の保管先。raw は Git に入らない)
- **スキーマ / データ辞書**:

  | 列名 / 変数名 | 単位 | 型 | 欠損値の表現 | 説明 |
  |---|---|---|---|---|
  |  |  |  |  |  |

- **既知の注意点**: (欠測期間、センサー交換、座標系のクセなど)
- **再生成 / 再入手コマンド**:

  ```bash
  # raw: ダウンロード手順やリクエスト方法を具体的に
  # interim / processed: 生成スクリプトの実行コマンド
  docker compose exec research-template uv run python projects/study1/scripts/<script>.py
  ```

マニフェストの生成(raw を読むだけで、書き込まない):

```bash
(cd projects/study1/data/raw/<dataset> && find . -type f ! -name .gitkeep -print0 | LC_ALL=C sort -z | xargs -0 sha256sum)
```

`/external` の下のデータは、`/external` がコンテナの中にしか無いので、同じコマンドをコンテナの中で動かす。ホストのリポジトリのルートで実行する(書き出し先はコンテナの作業場所 `/workspace` からの相対パスで、ホストの同じファイルになる):

```bash
docker compose exec -T research-template bash -c 'mkdir -p projects/study1/data/manifests && (cd /external/<dataset> && find . -type f ! -name .gitkeep -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) > projects/study1/data/manifests/<dataset>.sha256'
```

## 過去の結果(legacy)の記録

過去の結果を取り込むたびに、次のブロックをコピーして記入する。成果物ごとの再現性や照合の詳細は取り込み実験の README(照合の数値は `summary.md`)に書き、ここには由来の要点と、その README への参照を書く(手順の全体は `docs/importing-past-results.md`)。場所は `<repo>@<sha>:<リポジトリ内のパス>` の形で書き、ホストの絶対パスは書かない。

### <取り込み元の名前>

- **層**: legacy
- **場所**: `data/raw/legacy/<source>/`
- **元の場所**: `<repo>@<sha>:<リポジトリ内のパス>`(リポジトリでなければ、どの機器・フォルダにあったか)
- **実施時期**: (いつ計算・測定したか。どう特定したか)
- **実施者**:
- **生成コード/コミット**: `<repo>@<sha>`(コードの状態: clean / dirty / 不明)
- **再現性**: (R1 / R2 / R3。成果物ごとの内訳は取り込み実験の README)
- **取り込み実験**: `experiments/NNN_<slug>`
- **ライセンス・利用条件**:
- **公開可否**: (公開リポジトリと論文に載せてよいか。第三者の図なら転載許諾)
- **バックアップ先**: (原本の保管先)
- **元の記録のハッシュ**: マニフェスト `experiments/NNN_<slug>/inputs.sha256` とその sha256(`sha256sum projects/study1/experiments/NNN_<slug>/inputs.sha256` の結果)。マニフェストのファイル名は公開リポジトリに載るので、コミットの前に公開できない情報が無いことを確かめる。旧ツールが自分で記録したハッシュ(例: `run_meta.json`)があれば、その場所。`SOURCE_DIR` の中のファイルの分は `params.py` の `RECORDED_SHA256` で照合し、入力データのハッシュは、その入力を置いた `data/raw/<dataset>/` の記録の「チェックサム」と照らし合わせる

## 他のスタディのデータを使うとき

同じデータを複数のスタディで使うときは、1つのスタディ(持ち主)の `data/raw/` にだけ置き、他のスタディの台帳には持ち主のパスとチェックサムを書く。コードは他のスタディから import せず、ファイルとして読む。

### <データセット名>(他のスタディから)

- **持ち主**: `projects/<他のスタディ>/data/raw/<dataset>/`(台帳はそのスタディの `data/README.md`)
- **チェックサム**: (持ち主の台帳と同じ値。読む前に照合する)
