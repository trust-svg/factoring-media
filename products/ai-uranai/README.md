# AI占い事業

X（Twitter）でユーザーを獲得し、LINE公式アカウントでAI占いを提供・課金するビジネス。
**月利100万円目標**。

## ディレクトリ

| フォルダ | 内容 |
|---|---|
| `docs/` | 事業計画・マネタイズ設計 |
| `x-strategy/` | X投稿戦略・テンプレート |
| `line-official/` | LINEファネル・メッセージフロー設計 |
| `ai-fortune/` | LINE Botコード（FastAPI + Claude API） |
| `operations/` | 日次運用・KPI管理 |

## クイックスタート

```bash
cd ai-fortune
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .envにAPIキーを設定
python main.py
```

## 技術スタック

- **AI**: Anthropic Claude API
- **Bot**: LINE Messaging API v3
- **Server**: FastAPI + Uvicorn
- **Deploy**: Railway or Render
