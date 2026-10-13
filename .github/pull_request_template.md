## 概要

-

## 検証

- [ ] `make test`
- [ ] `make lint`
- [ ] 原稿を変えた場合: `make pdf && make check`
- [ ] 公開・安全に関わる変更: `make security`

## 研究の取り込み

- [ ] 研究を取り込んだ・更新した場合、`research.json` の行(`source` = `<repo>@<sha>`、`status`)と `projects/<id>/README.md` を更新した
- [ ] 図・表・数値はそのコミットから写し、`values.tex` の各行の上に元(`<repo>@<sha>:<path>` や論文の表・ページ)を書いた
- [ ] 本文中の数値は手で書かず、`\val{...}` で参照している

## データと書誌

- [ ] 生データ、資格情報、個人情報、Zotero などのデータベース、文献PDFを含めていない
- [ ] 追加した書誌エントリは DOI などで原典と照合し、`verified` フィールドを付けた
- [ ] 方法論に関わる判断は、必要に応じて記録した(`docs/research-log.md`、`docs/decisions/`)
