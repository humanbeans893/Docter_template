# External application integrations

外部アプリのデータ本体と資格情報は Git 管理外に置き、このリポジトリからは必要最小限の読み取りアクセスだけを与えます。

## Zotero bibliography workflow

推奨構成は Zotero 7 + Better BibTeX です。

1. Zotero で論文用コレクションを作成します。
2. Better BibTeX の自動エクスポート先を `draft/reference.bib` に設定します。
3. citation key は `authYYYYfirstword` 形式に固定します。
4. エクスポート項目から `file`, `local-url`, `annotation` などローカルパスや私的情報を除外します。

`reference.bib` は文献メタデータだけを追跡します。Zotero の `zotero.sqlite`、storage、PDF添付ファイルは追跡しません。

## Zotero local API and MCP

Zotero の Settings → Advanced でローカルAPIを有効にします。WSL2 から Windows Zotero へ接続する場合:

```bash
make zotero-forward
make zotero-check
```

MCP を利用する場合は、信頼できる環境で `zotero-mcp-server` をインストールし、`.mcp.json.example` をクライアントのローカル設定へコピーします。設定はローカルAPIを使用し、Web API キーをリポジトリへ保存しません。

Zotero MCP はコミュニティ実装です。既定は読み取り用途とし、タグ変更やアイテム削除などの書き込み操作は実行前に確認してください。

## Google Drive, Dropbox, OneDrive, Nextcloud

各デスクトップアプリが同期したローカルフォルダを、Dockerへ読み取り専用で公開できます。

1. `.env.example` を参考に、Git管理外の `.env` に絶対パスを設定します。

   ```dotenv
   EXTERNAL_FILES_DIR=/absolute/path/to/synced/research-files
   ```

2. 外部ファイル対応で起動します。

   ```bash
   make up-files
   ```

3. コンテナ内では `/external` として読み取れます。

このマウントは `read_only` です。解析で必要な派生データは、スクリプトから study の `data/interim/` または `data/processed/` に生成してください。クラウド同期フォルダをリポジトリ配下へコピーしたり、シンボリックリンクを commit したりしないでください。

## Secrets

Web API を選択する場合、`ZOTERO_API_KEY`、`ZOTERO_LIBRARY_ID` などは `.env` または利用するMCPクライアントの秘密設定に置きます。`.env` はエージェントの読み取り対象外かつ Git ignore 対象です。
