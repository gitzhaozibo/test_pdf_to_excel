# 契約書スキャンPDF抽出アプリ

Streamlit + Azure Document Intelligence + Azure OpenAI + PostgreSQL で契約書PDFの項目抽出を行うアプリです。

## 機能

- PDFアップロード後に「データ抽出」ボタンで OCR → AI抽出 → ハイライト表示
- 抽出値を画面で修正して PostgreSQL に保存
- 保存済みデータを一覧表示し、Excelでダウンロード
- 座標マッチングは正規化 + 文字単位逆引き + 曖昧一致フォールバック

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` に Azure / PostgreSQL の接続情報を設定してください。

## PostgreSQL準備例（Docker）

```bash
docker run --name contract-db -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=contracts -p 5432:5432 -d postgres:16
```

## 起動

```bash
streamlit run app.py
```

## テスト

```bash
pytest -q
```
