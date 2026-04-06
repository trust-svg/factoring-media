# App Store Assets Generator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 毎日すこやか診断所のアプリストア素材7点（アイコン・通知アイコン・フィーチャーグラフィック・スクショ3枚・スプラッシュ）をFlux Pro API + Figma MCPで自動生成するワークフローを構築する。

**Architecture:** PythonスクリプトがFlux Pro API（fal.ai）を呼び出して人物素材3点を生成・保存。その後Claude CodeがFigma MCP経由でFigmaファイルを構築し、全7フレームをレイアウト・書き出しする。

**Tech Stack:** Python 3.11+, fal-client (Flux Pro API), python-dotenv, Figma MCP (Claude Code tool)

**Spec:** `docs/superpowers/specs/2026-04-06-app-store-assets-design.md`

---

## File Structure

```
products/sukoyaka-assets/
├── .env                    # FAL_KEY（Flux Pro APIキー）
├── requirements.txt        # 依存パッケージ
├── generate_assets.py      # メインスクリプト（Flux Pro画像生成）
├── prompts.py              # Flux Proプロンプト定義
├── config.py               # カラー・サイズ定数
└── output/                 # 生成された素材の保存先
    ├── flux/               # Flux Pro生成画像（woman_a, woman_b, couple）
    └── final/              # Figma書き出し完成素材
```

---

## Task 1: プロジェクトセットアップ

**Files:**
- Create: `products/sukoyaka-assets/requirements.txt`
- Create: `products/sukoyaka-assets/.env`
- Create: `products/sukoyaka-assets/config.py`

- [ ] **Step 1: ディレクトリ作成**

```bash
mkdir -p products/sukoyaka-assets/output/flux
mkdir -p products/sukoyaka-assets/output/final
```

- [ ] **Step 2: requirements.txt を作成**

```
fal-client==0.5.6
python-dotenv==1.0.1
requests==2.31.0
Pillow==10.3.0
```

- [ ] **Step 3: .env を作成（APIキーはあとで入力）**

```
FAL_KEY=your_fal_api_key_here
```

> fal.aiのAPIキー取得: https://fal.ai → Sign up → API Keys → Create key

- [ ] **Step 4: config.py を作成**

```python
# config.py — カラー・サイズ・パス定数

COLORS = {
    "main": "#F28C63",       # やさしい昭和オレンジ
    "sub": "#FFF4E6",        # 落ち着いたクリームベージュ
    "accent": "#8B5E3C",     # 深みのある昭和ブラウン
}

OUTPUT_SIZES = {
    "app_icon": (512, 512),
    "notification_icon": (128, 128),
    "feature_graphic": (1024, 500),
    "screenshot": (1080, 1920),
    "splash": (2048, 2048),
}

OUTPUT_DIR = "output"
FLUX_DIR = "output/flux"
FINAL_DIR = "output/final"

APP_NAME = "毎日すこやか診断所"
```

- [ ] **Step 5: 依存パッケージをインストール**

```bash
cd products/sukoyaka-assets
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: Successfully installed fal-client, python-dotenv, requests, Pillow

- [ ] **Step 6: コミット**

```bash
git add products/sukoyaka-assets/requirements.txt products/sukoyaka-assets/config.py
git commit -m "feat: sukoyaka-assets プロジェクト初期セットアップ"
```

---

## Task 2: Flux Proプロンプト定義

**Files:**
- Create: `products/sukoyaka-assets/prompts.py`

- [ ] **Step 1: prompts.py を作成**

```python
# prompts.py — Flux Pro画像生成プロンプト定義

WOMAN_A = """
Portrait photo of an elegant Japanese woman in her 40s,
naturally feminine figure, soft curves,
warm genuine smile, casual-elegant clothing in cream and orange tones,
soft warm bokeh background, vintage warm film filter,
vignette effect, photorealistic, upper body shot,
high quality, no text
""".strip()

WOMAN_B = """
Portrait photo of an elegant Japanese woman in her 40s,
naturally feminine figure, soft curves,
slightly different angle from previous, cheerful expression,
casual-elegant clothing in warm earth tones,
soft warm bokeh background, vintage warm film filter,
vignette effect, photorealistic, upper body shot,
high quality, no text
""".strip()

COUPLE = """
Two Japanese people, man in his 50s and woman in her 40s,
natural warm expressions, casual-elegant clothing,
soft warm lighting, vintage film filter,
photorealistic, upper body shot, friendly atmosphere,
standing side by side, both smiling naturally,
no text, high quality
""".strip()

# モデル指定（Flux Pro）
FLUX_MODEL = "fal-ai/flux-pro"

# 生成パラメータ
GENERATION_PARAMS = {
    "width": 1024,
    "height": 1024,
    "num_inference_steps": 28,
    "guidance_scale": 3.5,
    "num_images": 1,
    "output_format": "png",
}
```

- [ ] **Step 2: コミット**

```bash
git add products/sukoyaka-assets/prompts.py
git commit -m "feat: Flux Proプロンプト定義を追加"
```

---

## Task 3: Flux Pro画像生成スクリプト

**Files:**
- Create: `products/sukoyaka-assets/generate_assets.py`

- [ ] **Step 1: generate_assets.py を作成**

```python
#!/usr/bin/env python3
"""
generate_assets.py — Flux Pro APIで人物素材3点を生成するスクリプト
"""

import os
import fal_client
from dotenv import load_dotenv
from pathlib import Path
from prompts import WOMAN_A, WOMAN_B, COUPLE, FLUX_MODEL, GENERATION_PARAMS
from config import FLUX_DIR

load_dotenv()


def generate_image(prompt: str, output_filename: str) -> str:
    """
    Flux Pro APIで画像を生成してローカルに保存する。
    Returns: 保存されたファイルパス
    """
    print(f"生成中: {output_filename} ...")

    result = fal_client.subscribe(
        FLUX_MODEL,
        arguments={
            "prompt": prompt,
            **GENERATION_PARAMS,
        },
        with_logs=True,
    )

    image_url = result["images"][0]["url"]

    # ダウンロードして保存
    import requests
    response = requests.get(image_url)
    response.raise_for_status()

    output_path = Path(FLUX_DIR) / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)

    print(f"  保存完了: {output_path}")
    return str(output_path)


def main():
    api_key = os.getenv("FAL_KEY")
    if not api_key or api_key == "your_fal_api_key_here":
        print("エラー: .env に FAL_KEY を設定してください")
        print("  取得先: https://fal.ai → API Keys")
        return

    os.environ["FAL_KEY"] = api_key

    assets = [
        (WOMAN_A, "woman_a.png"),
        (WOMAN_B, "woman_b.png"),
        (COUPLE, "couple.png"),
    ]

    results = {}
    for prompt, filename in assets:
        path = generate_image(prompt, filename)
        results[filename] = path

    print("\n=== 生成完了 ===")
    for filename, path in results.items():
        print(f"  {filename}: {path}")
    print("\n次のステップ: Figma MCPでレイアウトを組み立ててください")
    print("  参照: docs/superpowers/specs/2026-04-06-app-store-assets-design.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: スクリプトの動作確認（ドライラン）**

```bash
cd products/sukoyaka-assets
source venv/bin/activate
python generate_assets.py
```

Expected: `エラー: .env に FAL_KEY を設定してください` と表示される（APIキー未設定のため正常）

- [ ] **Step 3: コミット**

```bash
git add products/sukoyaka-assets/generate_assets.py
git commit -m "feat: Flux Pro画像生成スクリプトを追加"
```

---

## Task 4: APIキー設定 & 画像生成実行

**Files:**
- Modify: `products/sukoyaka-assets/.env`

- [ ] **Step 1: fal.aiでAPIキーを取得**

1. https://fal.ai にアクセス
2. Sign up / Log in
3. 右上のアバター → API Keys → Create new key
4. 生成されたキーをコピー

- [ ] **Step 2: .env にAPIキーを設定**

```
FAL_KEY=fal_xxxxxxxxxxxxxxxxxxxxxxxxxx
```

- [ ] **Step 3: 画像生成を実行**

```bash
cd products/sukoyaka-assets
source venv/bin/activate
python generate_assets.py
```

Expected（正常時）:
```
生成中: woman_a.png ...
  保存完了: output/flux/woman_a.png
生成中: woman_b.png ...
  保存完了: output/flux/woman_b.png
生成中: couple.png ...
  保存完了: output/flux/couple.png

=== 生成完了 ===
  woman_a.png: output/flux/woman_a.png
  ...
次のステップ: Figma MCPでレイアウトを組み立ててください
```

> コスト目安: 3枚 × $0.05 = 約$0.15（約23円）

- [ ] **Step 4: 生成画像を確認**

```bash
open products/sukoyaka-assets/output/flux/
```

人物が正しく生成されているか目視確認。不満があればプロンプトを微調整して再実行。

---

## Task 5: Figma MCPセットアップ確認

> FigmaのMCPは `@figma/mcp` パッケージで提供されています。Claude Codeのsettings.jsonに設定が必要です。

- [ ] **Step 1: Figma MCP が設定済みか確認**

Claude Codeの設定ファイルを確認:
```bash
cat ~/.claude/settings.json | grep -A5 figma
```

設定がない場合は以下を追加:
```json
{
  "mcpServers": {
    "figma": {
      "command": "npx",
      "args": ["-y", "@figma/mcp"],
      "env": {
        "FIGMA_ACCESS_TOKEN": "your_figma_token_here"
      }
    }
  }
}
```

- [ ] **Step 2: Figmaアクセストークン取得**

1. https://figma.com → 左上メニュー → Account settings
2. Access tokens → Generate new token
3. 名前: `claude-mcp` / 有効期限: 30日
4. 生成されたトークンをsettings.jsonに設定

- [ ] **Step 3: Claude Codeを再起動してMCP接続確認**

Claude Codeを再起動後、チャットで確認:
```
Figma MCPが使えますか？
```

Figmaのツール（create_file, create_frame等）がリストされれば接続成功。

---

## Task 6: FigmaファイルとデザイントークンをMCPで作成

> このタスク以降はClaude Code（Figma MCP）を使って対話的に実行してください。
> 以下の指示をClaudeへの指示として使用します。

- [ ] **Step 1: Figmaに新規ファイル作成**

Claude Codeへの指示:
```
Figma MCPで新しいFigmaファイルを作成してください。
ファイル名: 「毎日すこやか診断所_ストア素材」
```

- [ ] **Step 2: カラースタイルを定義**

Claude Codeへの指示:
```
作成したFigmaファイルに以下のカラースタイルを追加してください:
- Main Orange: #F28C63
- Sub Beige: #FFF4E6
- Accent Brown: #8B5E3C
```

- [ ] **Step 3: コミット（ファイルIDを記録）**

FigmaのURLからファイルIDを取得して記録:
```bash
# Figmaファイルを開いてURLをコピー
# 例: https://www.figma.com/file/XXXXXX/毎日すこやか診断所...
# XXXXXXの部分がファイルID
echo "FIGMA_FILE_ID=XXXXXX" >> products/sukoyaka-assets/.env
```

---

## Task 7: アプリアイコン・通知アイコン作成（Figma MCP）

- [ ] **Step 1: アプリアイコンフレーム作成**

Claude Codeへの指示:
```
Figma MCPで以下のフレームを作成してください:
- フレーム名: app-icon
- サイズ: 512×512px
- 背景色: #F28C63
- 中央に聴診器＋ハートのシンプルなベクターアイコンを配置（白色）
- アイコンサイズ: 256×256px（フレームの50%）
```

- [ ] **Step 2: 通知アイコンフレーム作成**

Claude Codeへの指示:
```
Figma MCPで以下のフレームを作成してください:
- フレーム名: notification-icon
- サイズ: 128×128px
- 背景: 透明
- アプリアイコンのシルエットを白単色で配置（128×128px全体に）
```

- [ ] **Step 3: アイコン2点を書き出し**

Claude Codeへの指示:
```
Figma MCPで以下を書き出してください:
- app-icon: PNG 32bit, 512×512px → products/sukoyaka-assets/output/final/app_icon.png
- notification-icon: PNG, 128×128px, 背景透過 → products/sukoyaka-assets/output/final/notification_icon.png
```

---

## Task 8: フィーチャーグラフィック作成（Figma MCP）

- [ ] **Step 1: Flux生成画像をFigmaにアップロード**

Claude Codeへの指示:
```
Figma MCPで以下の画像をFigmaファイルにインポートしてください:
- products/sukoyaka-assets/output/flux/woman_a.png → Assets/woman_a
- products/sukoyaka-assets/output/flux/woman_b.png → Assets/woman_b
- products/sukoyaka-assets/output/flux/couple.png → Assets/couple
```

- [ ] **Step 2: フィーチャーグラフィックフレーム作成**

Claude Codeへの指示:
```
Figma MCPで以下のフレームを作成してください:
- フレーム名: feature-graphic
- サイズ: 1024×500px
- 背景: #FFF4E6 から #F28C63 への左→右グラデーション + グレインテクスチャオーバーレイ(opacity 15%)

レイアウト（左半分・右半分の2カラム）:
[左半分 512×500px]
- アプリ名「毎日すこやか診断所」: 明朝体, 36px, #8B5E3C, top:80px, left:48px
- テキスト「性格診断をきっかけに、同世代と気軽につながる。」: ゴシック, 18px, #8B5E3C, top:160px, left:48px, 最大幅420px
- テキスト「50代以上向け交流アプリ」: ゴシック, 16px, #F28C63, top:240px, left:48px

[右半分 512×500px]
- Assets/woman_a を配置: width:480px, height:500px, object-fit:cover, ビネット加工
```

- [ ] **Step 3: フィーチャーグラフィックを書き出し**

Claude Codeへの指示:
```
フレーム feature-graphic を PNG 24bit で書き出してください:
→ products/sukoyaka-assets/output/final/feature_graphic.png
```

---

## Task 9: スクリーンショット3枚作成（Figma MCP）

- [ ] **Step 1: スクショ①（メインビジュアル）作成**

Claude Codeへの指示:
```
Figma MCPで以下のフレームを作成してください:
- フレーム名: screenshot-01
- サイズ: 1080×1920px
- 背景: #FFF4E6 + グレインテクスチャ(opacity 12%)

レイアウト:
[左半分 540×1920px]
- Assets/woman_a: width:540px, height:1920px, object-fit:cover

[右半分 540×1920px]
- スマホモック枠（iPhone 14 Pro風の黒いフレーム）: width:360px, height:720px, top:400px, left:570px
- モック内は空（プレースホルダー #E8E8E8）

[テキストブロック, bottom:200px, left:40px, 最大幅:1000px]
- 「毎日すこやか診断所」: 明朝体, 52px, #8B5E3C
- 「50代からの性格診断＆交流アプリ」: ゴシック, 28px, #8B5E3C, top offset:70px
- 「気軽に自分を知って、共感を楽しもう」: ゴシック, 24px, #F28C63, top offset:120px
```

- [ ] **Step 2: スクショ②（ターゲット訴求）作成**

Claude Codeへの指示:
```
Figma MCPで以下のフレームを作成してください:
- フレーム名: screenshot-02
- サイズ: 1080×1920px
- 背景: #F28C63 + グレインテクスチャ(opacity 12%)

レイアウト:
[ヘッダーテキスト, top:120px, left:0, 幅:1080px, 中央寄せ]
- 「こんな方におすすめ」: 明朝体, 52px, #FFF4E6

[左半分 540×1200px, top:300px]
- Assets/couple: width:540px, height:800px, object-fit:cover, ビネット加工

[右半分チェックリスト, top:400px, left:580px]
- 「✓ 診断や心理テストが好き」: ゴシック, 26px, #FFF4E6
- 「✓ 同世代とつながりたい」: ゴシック, 26px, #FFF4E6, top offset:80px
- 「✓ 気軽に交流したい」: ゴシック, 26px, #FFF4E6, top offset:160px
- 「✓ 共感できる話題がほしい」: ゴシック, 26px, #FFF4E6, top offset:240px
各行の✓マーク: #8B5E3C（ブラウン）
```

- [ ] **Step 3: スクショ③（安心訴求）作成**

Claude Codeへの指示:
```
Figma MCPで以下のフレームを作成してください:
- フレーム名: screenshot-03
- サイズ: 1080×1920px
- 背景: #FFF4E6 + グレインテクスチャ(opacity 12%)

レイアウト:
[左半分 540×1920px]
- Assets/woman_b: width:540px, height:1920px, object-fit:cover

[右半分 540×1920px]
- スマホモック枠（screenshot-01と同じ仕様）: top:200px, left:570px

[テキストブロック, bottom:350px, left:40px, 最大幅:1000px]
- 「診断 × 共感 × 交流」: 明朝体, 48px, #8B5E3C
- 「毎日を少し明るく」: ゴシック, 32px, #F28C63, top offset:70px

[安心カード, bottom:100px, left:40px, 幅:1000px, 高さ:220px]
- カード背景: #8B5E3C, 角丸:16px
- 「安心・安全設計」: 明朝体, 28px, #FFF4E6
- 「・サポート体制充実」「・通報・ブロック機能」「・24時間監視」: ゴシック, 22px, #FFF4E6
```

- [ ] **Step 4: スクショ3枚を書き出し**

Claude Codeへの指示:
```
以下の3フレームをPNG形式で書き出してください（各1080×1920px）:
- screenshot-01 → products/sukoyaka-assets/output/final/screenshot_01.png
- screenshot-02 → products/sukoyaka-assets/output/final/screenshot_02.png
- screenshot-03 → products/sukoyaka-assets/output/final/screenshot_03.png
```

---

## Task 10: スプラッシュスクリーン作成（Figma MCP）

- [ ] **Step 1: スプラッシュフレーム作成**

Claude Codeへの指示:
```
Figma MCPで以下のフレームを作成してください:
- フレーム名: splash
- サイズ: 2048×2048px
- 背景: #FFF4E6 全面

レイアウト（全要素を垂直中央揃え, 水平中央揃え）:
- アプリアイコン（app-iconフレームのコンポーネント）: 256×256px, top:700px, 水平中央
- アプリ名「毎日すこやか診断所」: 明朝体, 72px, #8B5E3C, top:1000px, 水平中央
- キャッチコピー「今日の自分を、少し知ってみよう。」: ゴシック, 40px, #F28C63, top:1120px, 水平中央
```

- [ ] **Step 2: スプラッシュを書き出し**

Claude Codeへの指示:
```
フレーム splash をPNG形式で書き出してください:
→ products/sukoyaka-assets/output/final/splash.png (2048×2048px)
```

---

## Task 11: 最終確認 & 納品

- [ ] **Step 1: 全成果物を確認**

```bash
ls -la products/sukoyaka-assets/output/final/
```

Expected（7ファイル）:
```
app_icon.png          （512×512, ≤1024KB）
notification_icon.png （128×128, 透過PNG）
feature_graphic.png   （1024×500）
screenshot_01.png     （1080×1920）
screenshot_02.png     （1080×1920）
screenshot_03.png     （1080×1920）
splash.png            （2048×2048）
```

- [ ] **Step 2: ファイルサイズ確認**

```bash
python3 -c "
from PIL import Image
import os

files = {
    'app_icon.png': (512, 512),
    'notification_icon.png': (128, 128),
    'feature_graphic.png': (1024, 500),
    'screenshot_01.png': (1080, 1920),
    'screenshot_02.png': (1080, 1920),
    'screenshot_03.png': (1080, 1920),
    'splash.png': (2048, 2048),
}

for fname, expected_size in files.items():
    path = f'products/sukoyaka-assets/output/final/{fname}'
    img = Image.open(path)
    size_kb = os.path.getsize(path) / 1024
    status = '✓' if img.size == expected_size else f'✗ (expected {expected_size}, got {img.size})'
    print(f'{status} {fname}: {img.size}, {size_kb:.1f}KB')
"
```

Expected: 全ファイルに ✓ が表示される。app_icon.pngは1024KB以下であること。

- [ ] **Step 3: 最終コミット**

```bash
git add products/sukoyaka-assets/
git commit -m "feat: 毎日すこやか診断所 ストア素材生成ワークフロー完成"
```

---

## チェックリスト（スペック対照）

| 仕様 | タスク | 確認 |
|---|---|---|
| アプリアイコン 512×512 PNG | Task 7 | - |
| 通知アイコン 128×128 白抜き透過PNG | Task 7 | - |
| フィーチャーグラフィック 1024×500 | Task 8 | - |
| スクショ① メインビジュアル 1080×1920 | Task 9 | - |
| スクショ② ターゲット訴求 1080×1920 | Task 9 | - |
| スクショ③ 安心訴求 1080×1920 | Task 9 | - |
| スプラッシュスクリーン 2048×2048 | Task 10 | - |
| 人物素材: woman_a, woman_b, couple | Task 3-4 | - |
| 昭和モダンプレミアムスタイル | Task 6-10 | - |
| グレインテクスチャ + グラデーション | Task 6-10 | - |
