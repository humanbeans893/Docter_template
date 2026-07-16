# projects/ — 研究スタディ置き場

ここの各サブディレクトリが博士論文の **1つの研究(スタディ)** です。スタディは自前のデータ・コード・結果を持つ自己完結な単位で、他のスタディに依存しません。論文原稿はリポジトリルートの `draft/` にあり、通常 1スタディ=1章になります。

## スタディの構成

```text
projects/<study>/
├── data/
│   ├── raw/                 # 生データ(不変・Git対象外)
│   ├── interim/             # 中間データ(スクリプトが生成)
│   ├── processed/           # 解析用データ(スクリプトが生成)
│   └── README.md            # データ台帳(入手元・取得日・再入手方法を必ず記入)
├── src/{utils,models,methods,analysis}/   # 再利用コード
│   └── utils/figures.py, tables.py        # 図表ヘルパー(来歴記録付き)
├── scripts/                 # 実行入口(薄く保つ)
├── result/{figures,tables,animations}/    # 生成物(手で編集しない)
├── tests/                   # スタディ携行テスト(コピー直後から通る)
├── config.py                # スタディ内パス + 共有定数
└── README.md
```

## 新しいスタディの作り方

```bash
cp -r projects/_template projects/<スタディ名>
docker compose exec research-template uv run pytest projects/<スタディ名>
```

テストが通れば複製は健全です。あとは:

1. `data/raw/` にデータを置き、`data/README.md` に台帳を記入
2. 解析コードを `src/` + `scripts/` に実装し、再現手順と依存関係を各スタディの README に記録
3. 図表は `save_figure` / `write_latex_table` で生成。**ファイル名は `<スタディ名>-<内容>`**
4. 章にする段階になったら `draft/preamble.tex` の `\graphicspath` と `draft/main.tex` の `\include` に登録(手順の詳細は `draft/README.md`)

## なぜ monorepo(git submodule にしない)か

1人の学位論文では、リポジトリ分割(submodule/subtree)は detached HEAD・二段コミットなどの運用コストばかりが先に立ちます。全スタディを1リポジトリで管理し、後で単独公開が必要になったスタディだけ履歴ごと切り出します:

```bash
git subtree split --prefix=projects/<study> -b <study>-export
# 完全な書き換えが要るなら: git filter-repo --path projects/<study>/
```
