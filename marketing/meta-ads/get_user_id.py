"""
LINE ユーザーID取得 — Webhookサーバー

手順:
1. このスクリプトを実行
2. 別ターミナルで ngrok http 8765 を実行（ngrokが無ければ brew install ngrok）
3. ngrokのURLをコピー（例: https://xxxx.ngrok-free.app）
4. LINE Developers → Messaging API設定 → Webhook URL に貼り付け → 更新
5. Webhookの利用をON
6. LINEからTrustLinkに何かメッセージを送る
7. ターミナルにユーザーIDが表示される
"""
import http.server
import json

PORT = 8765

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        for event in body.get("events", []):
            uid = event.get("source", {}).get("userId", "")
            if uid:
                print(f"\n{'='*50}")
                print(f"あなたのユーザーID: {uid}")
                print(f"{'='*50}")
                print(f"\n.envのLINE_USER_IDにこの値を設定してください\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, fmt, *args):
        pass

print(f"Webhookサーバー起動: http://localhost:{PORT}")
print("ngrok等でトンネルを張ってWebhook URLに設定してください")
http.server.HTTPServer(("", PORT), Handler).serve_forever()
