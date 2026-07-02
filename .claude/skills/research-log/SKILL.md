---
name: research-log
description: Record session findings, decisions with rationale, and dead ends into docs/research-log.md; significant decisions also become ADRs under docs/decisions/. Always confirm with the user before writing.
---

# /research-log

セッションの研究内容(結果・判断・行き止まり)を `docs/research-log.md` に記録する。影響の大きい意思決定は `docs/decisions/` の ADR にも残す。

## When to use

- 解析や執筆の節目(結果が出た・方針を決めた・行き詰まった)
- ユーザーが「ログに残して」「今日の記録をして」と言ったとき
- コード変更の記録が目的なら `/session-save` の方が適切。こちらは**研究内容**(何を試し、何が分かり、なぜそう判断したか)の記録

## Steps

### 1. 情報収集

```bash
git log --oneline -5
git status
```

会話を振り返り、次の形式で下書きを作る:

```markdown
## YYYY-MM-DD — <短いタイトル>

- **Goal**: 何をしようとしたか
- **Done**: 実際にやったこと(実行したスクリプト・生成した図表・関連コミット)
- **Decisions**: 下した判断とその理由
- **Dead ends**: うまくいかなかったことと原因
- **Next**: 次にやること
```

### 2. ユーザー確認(必須)

下書きを提示して確認を取る。**確認なしに書き込まない**(誤った記録は将来のセッションを汚染する)。

### 3. 書き込み

`docs/research-log.md` の `<!-- newest entry below -->` マーカーの**直下**にエントリを挿入する(新しい順)。

### 4. 重要な決定は ADR に

方法論の選択・データの除外基準・リポジトリ構成の変更など影響の大きい決定は、`docs/decisions/_adr-template.md` をコピーして `docs/decisions/NNNN-<slug>.md`(NNNN は次の連番)を作成し、ログエントリからリンクする。

### 5. 完了報告

書き込んだファイルのパスを表示する。
