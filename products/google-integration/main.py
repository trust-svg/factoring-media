"""
Google連携 AIエージェント
────────────────────────
Gmail・Googleカレンダー・GoogleドライブをAIで操作するCLIエージェント。

使い方:
    python main.py

終了:
    「終了」「quit」「exit」と入力
"""

from agent import chat

BANNER = """
╔════════════════════════════════════════╗
║   Google連携 AIエージェント            ║
║   Gmail / カレンダー / ドライブ        ║
╚════════════════════════════════════════╝

使い方の例:
  「最新のメールを5件見せて」
  「このメールに返信して」
  「〇〇のミーティングをカレンダーに登録して」
  「今週の予定を教えて」
  「議事録.docxを探して内容を教えて」

終了するには「終了」と入力してください。
"""


def main():
    print(BANNER)
    messages = []

    while True:
        try:
            user_input = input("あなた: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n終了します。")
            break

        if not user_input:
            continue

        if user_input.lower() in {"終了", "quit", "exit", "q"}:
            print("終了します。")
            break

        messages.append({"role": "user", "content": user_input})

        print("AI: 考え中...", end="\r")
        try:
            response, messages = chat(messages)
            print(f"AI: {response}")
        except Exception as e:
            print(f"AI: エラーが発生しました: {e}")
            # エラー時は最後のユーザーメッセージを除去してリセット
            if messages and messages[-1]["role"] == "user":
                messages.pop()

        print()  # 空行で区切り


if __name__ == "__main__":
    main()
