# 貢献の手引き

## 作業の流れ

1. `main` から作業用のブランチを作成します。
2. 変更範囲に応じたテストを追加します。
3. `make test lint` を実行します。原稿を変えたときは `make pdf check`、公開に関わる変更では `make security` も実行します。
4. pull request を作成し、CI が通り、未解決のコメントが残っていないことを確認します。

`main` への直接の push、force push、生成物の手編集は行いません。

## データとプライバシー

- 生データ、個人情報、資格情報、文献管理ソフトのデータベース(Zotero など)、文献PDFをコミットしないでください。
- 再現に必要なデータの情報は各スタディの `data/README.md` に記録します。過去の結果は `make experiment-import` で取り込み実験を作り、由来と再現性を記録してから使います([docs/importing-past-results.md](docs/importing-past-results.md))。
- 研究結果の図表と本文中の数値は、スクリプトから再生成できる状態にしてください。図表はコードで `result/` に書き出し、本文の数値は生成した値(`\val{...}`)で参照します。

## フック(`.claude/hooks/protect_raw_data.py`)を変えるとき

このフックはすべての Bash・Edit・Write の前に動き、失敗すると止める側に倒れるので、書きかけのフックはセッションのすべてのツール呼び出しを止めます。新しい版は別の場所に全体を書き、import できることと `tests/test_protect_raw_data_hook.py` が通ることを確かめてから、1回の `cp` で置き換えます。何回かに分けて直接編集しません。

## 書誌

書誌は `draft/reference.bib` だけで管理します。文献管理ソフトから書き出した BibTeX を受け取り、各エントリは DOI などで原典と照合してから追加し、`verified` フィールドを付けます。詳しくは [docs/integrations.md](docs/integrations.md) を参照してください。

## pull request

本文には目的、主な変更、利用者への影響、実行した検証を書きます。方法論やリポジトリの設計に影響する判断は、意思決定記録(`docs/decisions/`)にも残します。
