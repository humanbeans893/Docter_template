# データ台帳(data dictionary)

> **鉄則**: `data/raw/` は不変(手で編集しない・上書きしない)。大きなデータは Git にコミットされない設定なので、**このファイルに「再入手の方法」を必ず書き残すこと**。ここが空のままだと、他のマシンや将来の自分がデータを復元できません。

## データセット一覧

| データセット名 | 層 (raw / interim / processed) | 生成元(入手先 or 生成スクリプト) |
|---|---|---|
| (例) sst_monthly | raw | NOAA OISST v2.1 からダウンロード |
| (例) sst_anomaly | processed | `scripts/build_sst_anomaly.py` |

---

## 各データセットの記録テンプレート

データセットを追加するたびに、以下のブロックをコピーして記入する。

### <データセット名>

- **層**: raw / interim / processed
- **入手先 / Source**: URL・DOI・提供者の連絡先など
- **取得日**: YYYY-MM-DD
- **ライセンス・利用条件**:
- **バージョン**:
- **サイズ**: (`du -sh data/raw/<name>` の結果)
- **チェックサム**: (`sha256sum data/raw/<file>` の結果)
- **スキーマ / データ辞書**:

  | 列名 / 変数名 | 単位 | 型 | 欠損値の表現 | 説明 |
  |---|---|---|---|---|
  |  |  |  |  |  |

- **既知の注意点**: (欠測期間、センサー交換、座標系のクセなど)
- **再生成 / 再入手コマンド**:

  ```bash
  # raw: ダウンロード手順やリクエスト方法を具体的に
  # interim / processed: 生成スクリプトの実行コマンド
  docker compose exec research-template uv run python projects/<study>/scripts/<script>.py
  ```
