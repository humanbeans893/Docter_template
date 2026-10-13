# 外部の同期フォルダと書誌

外部アプリのデータ本体と資格情報は Git 管理外に置き、このリポジトリからは必要最小限の読み取りだけを許します。

## Google Drive・Dropbox・OneDrive・Nextcloud

各デスクトップアプリが同期したローカルのフォルダを、Docker のコンテナへ読み取り専用で見せられます。

1. `.env.example` を参考に、Git 管理外の `.env` に絶対パスと、`docker-compose.files.yml` を加えた `COMPOSE_FILE` を書きます。GPU も使うマシンでは `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml:docker-compose.files.yml` にします。

   ```dotenv
   EXTERNAL_FILES_DIR=/absolute/path/to/synced/research-files
   COMPOSE_FILE=docker-compose.yml:docker-compose.files.yml
   ```

   `COMPOSE_FILE` に `docker-compose.files.yml` があるあいだは `EXTERNAL_FILES_DIR` が必須で、無いとすべての `docker compose` コマンドが止まります。

2. 起動します(コンテナが作り直されるので、実行中のジョブが無いことを先に確かめます)。

   ```bash
   make up
   ```

   以後の `make up`・`make test`・`docker compose` も `.env` の `COMPOSE_FILE` を使うので、`/external` は外れません。`-f docker-compose.files.yml` を1回のコマンドに付けるだけでは、次の `make up`(`make study` や `uv add` の後など)でエラーなしに外れます。

3. コンテナ内では `/external` として読めます。

このマウントは読み取り専用です。解析に要る派生データは、スクリプトからスタディの `data/interim/` か `data/processed/` に作ります。同期フォルダをリポジトリの中へコピーしたり、シンボリックリンクをコミットしたりしないでください。

リポジトリに置けない過去の結果(大きすぎる、外へ出せない)は、取り込み実験の `params.py` で `SOURCE_DIR` を `/external/…` に向けて使えます。マニフェスト(`inputs.sha256`)はリポジトリ側の実験に置き、保管場所を台帳に書きます(`importing-past-results.md`)。

## 書誌

- 書誌の正本は `draft/reference.bib` だけです。文献管理ソフトとは同期しません。
- エージェントは Zotero などの文献管理ソフトに接続しません。自分のライブラリの書誌を使いたいときは、どの文献管理ソフトからでも BibTeX で書き出して渡します。
- 書誌を足すときは、エージェントが見つけたものも渡されたものも、DOI から原典(出版社のページ、Crossref、PMC、保存版)と照合してから入れます。引用する数値も原文で確かめます。
- 照合したら、その日付と照合の手がかりを `verified` の欄に書きます。DOI が無ければ `isbn:` か、公式ページの `url:` を使います。

  ```bibtex
  @article{<auth><YYYY><firstword>,
    author   = {<著者>},
    title    = {<題名>},
    journal  = {<誌名>},
    year     = {<YYYY>},
    doi      = {<DOI>},
    verified = {<照合した日 YYYY-MM-DD>, doi:<DOI>},
  }
  ```

  `make check` は `verified` の無い項目を I4 として挙げ、提出の検査(`make check-final`)では誤りにします。同じ DOI の項目が2つあれば W13 で挙げます。
- 引用キーは `authYYYYfirstword`(例: `smith2024ocean`)にそろえます。
- `file`・`local-url`・`annote`・`annotation` など、手元のパスや私的なメモの欄は消してから入れます。
- 引用を捏造しません。原典を確かめられない文献は入れず、「出典が必要な箇所」として残します。
- `reference.bib` は書誌の情報だけを追跡します。文献管理ソフトのデータベースや文献の PDF はコミットしません。

## 秘密情報

API キーなどの資格情報は `.env` か、利用するクライアントの秘密設定に置きます。`.env` は Git の追跡対象外で、エージェントは読みません。
