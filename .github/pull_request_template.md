## 概要

-

## 検証

- [ ] `make test`
- [ ] `make lint`
- [ ] 原稿を変えた場合: `make pdf && make check`
- [ ] 公開・安全に関わる変更: `make security`

## 実験と結果

- [ ] 実験を追加・変更した場合、その `summary.md` と、スタディの `experiments/EXP_SUMMARY.md` の行(状態・論文・由来)を同じ語で更新した
- [ ] 過去の結果を取り込んだ場合、取り込み実験の README に由来を、`data/README.md` に台帳の項目を記録し、入力のマニフェスト(`inputs.sha256`)を照合した
- [ ] 論文に使う図表・数値はコードで生成し、由来ファイル(`*.provenance.json`)がある
- [ ] 本文中の数値は手で書かず、生成した値(`\val{...}`)で参照している

## データと書誌

- [ ] 生データ、資格情報、個人情報、Zotero などのデータベース、文献PDFを含めていない
- [ ] 追加した書誌エントリは DOI などで原典と照合し、`verified` フィールドを付けた
- [ ] 方法論に関わる判断は、必要に応じて記録した(`docs/research-log.md`、`docs/decisions/`)
