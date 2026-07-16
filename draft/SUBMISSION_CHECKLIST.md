# Dissertation submission checklist

大学・研究科の最新版提出要項を正とし、次を確認してください。

## Institutional format

- [ ] 正式な学位名、題目、著者名、所属、指導教員名、提出日
- [ ] 表紙・背表紙・審査用表紙の指定様式
- [ ] A4、余白、行間、片面／両面、フォント、ページ番号
- [ ] 和文・英文要旨の字数、キーワード数、提出順
- [ ] 宣誓文、署名、関連論文・著者貢献の要否
- [ ] 電子提出のファイル名、容量、PDF/A、暗号化禁止などの要件

## Research integrity

- [ ] 研究倫理承認番号、同意、データ利用許諾
- [ ] 利益相反、資金提供、謝辞、grant番号
- [ ] 共著論文を含む章の著者貢献と転載許諾
- [ ] データ・コード公開先、DOI、embargo、ライセンス
- [ ] 本文、図表、補足資料の数値と解析出力の一致

## Technical validation

- [ ] `make test && make lint`
- [ ] `make submission`
- [ ] `make security-history`
- [ ] PDFを別端末で開き、目次リンク、フォント、図表、ページ順を確認
- [ ] TODO、変更履歴、注釈、非表示レイヤーが残っていない
- [ ] 未定義参照・引用、Overfull box、重複アンカーがない

## Archive

- [ ] 最終 commit/tag と提出PDFのチェックサムを記録
- [ ] データ台帳から全データを再取得できる
- [ ] 解析環境を `uv.lock` と Dockerfile から再構築できる
- [ ] Zoteroコレクションと `reference.bib` の最終同期を確認
