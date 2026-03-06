"""
TrustLink — Meta広告 下書き作成スクリプト
広告マネージャーに PAUSED 状態で広告を作成します。
3サイト対応: Olive / Travis / Massive
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adimage import AdImage

load_dotenv()

# --- 設定 ---
ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
PAGE_ID = os.getenv("META_PAGE_ID")
OLIVE_ADSET_ID = os.getenv("OLIVE_ADSET_ID")
TRAVIS_ADSET_ID = os.getenv("TRAVIS_ADSET_ID")
MASSIVE_ADSET_ID = os.getenv("MASSIVE_ADSET_ID")
OLIVE_LP_URL = os.getenv("OLIVE_LP_URL", "https://4528n.com")
TRAVIS_LP_URL = os.getenv("TRAVIS_LP_URL", "https://example.com")
MASSIVE_LP_URL = os.getenv("MASSIVE_LP_URL", "https://example.com")

ADSET_LABELS = {
    OLIVE_ADSET_ID: "Olive",
    TRAVIS_ADSET_ID: "Travis",
    MASSIVE_ADSET_ID: "Massive",
}

# --- 広告クリエイティブ定義 ---
AD_CREATIVES = [
    # === Olive 用 (4528n.com) ===
    {
        "name": "Olive-A1-成功体験",
        "adset_id": OLIVE_ADSET_ID,
        "link": OLIVE_LP_URL,
        "primary_text": (
            "54歳、離婚して3年。\n"
            "正直、もう無理だと思ってました。\n\n"
            "でも始めて2週間で4人とマッチ。\n"
            "先月は2人と実際に会えました。\n\n"
            "50代の男って、意外とモテるんです。\n"
            "嘘だと思うなら、まず無料で覗いてみてください。"
        ),
        "headline": "50代が一番モテる場所がここにある",
        "description": "LINE登録30秒・無料で始められます",
    },
    {
        "name": "Olive-B1-休日の寂しさ",
        "adset_id": OLIVE_ADSET_ID,
        "link": OLIVE_LP_URL,
        "primary_text": (
            "日曜の朝。\n"
            "コンビニ弁当を一人で食べて、テレビをつけて…\n\n"
            "こんな週末が、あと何年続くんだろう。\n\n"
            "そう思ったのが始めたきっかけです。\n"
            "今は週末が来るのが楽しみになりました。"
        ),
        "headline": "一人の日曜日、もう終わりにしませんか",
        "description": "50代専門のマッチング・LINE登録無料",
    },
    {
        "name": "Olive-C2-安心感",
        "adset_id": OLIVE_ADSET_ID,
        "link": OLIVE_LP_URL,
        "primary_text": (
            "マッチングアプリって怪しくない？\n"
            "最初は僕もそう思ってました。\n\n"
            "でもここは50代専門。\n"
            "年齢確認済みの、同年代の女性だけ。\n\n"
            "若い子に混じって恥ずかしい思いをする必要、ありません。"
        ),
        "headline": "50代専門だから、気まずくない",
        "description": "年齢確認済み・同年代の女性だけ",
    },
    {
        "name": "Olive-C3-無料強調",
        "adset_id": OLIVE_ADSET_ID,
        "link": OLIVE_LP_URL,
        "primary_text": (
            "まず無料でできること：\n"
            "✅ 女性のプロフィールを見る\n"
            "✅ マッチング相手を探す\n"
            "✅ いいねを送る\n\n"
            "「お金かかるんでしょ？」\n"
            "いいえ、最初は完全無料です。"
        ),
        "headline": "完全無料で始める50代のマッチング",
        "description": "LINE登録30秒・今すぐ無料で相手を探す",
    },
    # === Travis 用 (gotrust系) ===
    {
        "name": "Travis-A2-数字で証明",
        "adset_id": TRAVIS_ADSET_ID,
        "link": TRAVIS_LP_URL,
        "primary_text": (
            "50代男性の平均マッチ数：月7.2人\n\n"
            "「若い子しかいないアプリ」で消耗するのは、もうやめませんか？\n\n"
            "ここは50代が\"主役\"の場所。\n"
            "同年代の女性が、あなたとの出会いを探しています。"
        ),
        "headline": "50代男性の平均マッチ数、月7.2人",
        "description": "今すぐ無料で登録する",
    },
    {
        "name": "Travis-B2-既読の喜び",
        "adset_id": TRAVIS_ADSET_ID,
        "link": TRAVIS_LP_URL,
        "primary_text": (
            "スマホに通知が来るだけで、こんなに嬉しいとは。\n\n"
            "50歳を過ぎて、誰かに「会いたい」と思われる。\n"
            "忘れてたこの感覚、戻ってきました。"
        ),
        "headline": "「会いたい」のメッセージ、届いてますか？",
        "description": "今日から始められる50代のマッチング",
    },
    {
        "name": "Travis-C1-30秒訴求",
        "adset_id": TRAVIS_ADSET_ID,
        "link": TRAVIS_LP_URL,
        "primary_text": (
            "LINE登録たった30秒。\n"
            "顔出しなし、本名不要。\n\n"
            "まずは「どんな女性がいるか」見るだけでOK。\n"
            "気になる人がいたら、その時に登録すればいい。"
        ),
        "headline": "まず見るだけ。30秒で始められます",
        "description": "LINE登録無料・顔出し不要",
    },
    {
        "name": "Travis-D1-アプリ疲れ",
        "adset_id": TRAVIS_ADSET_ID,
        "link": TRAVIS_LP_URL,
        "primary_text": (
            "Pairs、with、Tinder…\n"
            "全部やって、全部ダメでした。\n\n"
            "理由はシンプル。\n"
            "20代30代向けのアプリで、50代が戦っても勝てない。\n\n"
            "ここに変えた途端、状況が変わりました。"
        ),
        "headline": "マッチングアプリで消耗した50代へ",
        "description": "50代が選ばれる場所に、来ませんか",
    },
    # === Massive 用 ===
    {
        "name": "Massive-A1-成功体験",
        "adset_id": MASSIVE_ADSET_ID,
        "link": MASSIVE_LP_URL,
        "primary_text": (
            "54歳、離婚して3年。\n"
            "正直、もう無理だと思ってました。\n\n"
            "でも始めて2週間で4人とマッチ。\n"
            "先月は2人と実際に会えました。\n\n"
            "50代の男って、意外とモテるんです。\n"
            "嘘だと思うなら、まず無料で覗いてみてください。"
        ),
        "headline": "50代が一番モテる場所がここにある",
        "description": "LINE登録30秒・無料で始められます",
    },
    {
        "name": "Massive-A3-ギャップ訴求",
        "adset_id": MASSIVE_ADSET_ID,
        "link": MASSIVE_LP_URL,
        "primary_text": (
            "妻に捨てられて、自信なんてゼロでした。\n"
            "髪も薄いし、腹も出てる。\n\n"
            "それでも始めて1ヶ月。\n"
            "「年上の男性が好きなんです」って言われて、目が覚めました。\n\n"
            "50代の魅力に気づいてない男性が多すぎます。"
        ),
        "headline": "あなたの魅力、まだ気づいてないだけ",
        "description": "無料・匿名で始められるマッチング",
    },
    {
        "name": "Massive-B3-定年前の焦り",
        "adset_id": MASSIVE_ADSET_ID,
        "link": MASSIVE_LP_URL,
        "primary_text": (
            "定年まであと5年。\n\n"
            "仕事は終わる。\n"
            "でもその後の人生は、まだ30年ある。\n\n"
            "一人で過ごすのか。\n"
            "誰かと一緒に過ごすのか。\n\n"
            "決めるなら、今です。"
        ),
        "headline": "仕事の次に大事なこと、忘れていませんか",
        "description": "50代からの出会い・無料で始める",
    },
    {
        "name": "Massive-C1-30秒訴求",
        "adset_id": MASSIVE_ADSET_ID,
        "link": MASSIVE_LP_URL,
        "primary_text": (
            "LINE登録たった30秒。\n"
            "顔出しなし、本名不要。\n\n"
            "まずは「どんな女性がいるか」見るだけでOK。\n"
            "気になる人がいたら、その時に登録すればいい。"
        ),
        "headline": "まず見るだけ。30秒で始められます",
        "description": "LINE登録無料・顔出し不要",
    },
    {
        "name": "Massive-D1-アプリ疲れ",
        "adset_id": MASSIVE_ADSET_ID,
        "link": MASSIVE_LP_URL,
        "primary_text": (
            "Pairs、with、Tinder…\n"
            "全部やって、全部ダメでした。\n\n"
            "理由はシンプル。\n"
            "20代30代向けのアプリで、50代が戦っても勝てない。\n\n"
            "ここに変えた途端、状況が変わりました。"
        ),
        "headline": "マッチングアプリで消耗した50代へ",
        "description": "50代が選ばれる場所に、来ませんか",
    },
]


def check_config():
    """必須設定の確認"""
    missing = []
    for key in ["META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID"]:
        if not os.getenv(key):
            missing.append(key)
    if missing:
        print(f"❌ .env に以下の設定が必要です: {', '.join(missing)}")
        print("   .env.example を参考に .env を作成してください")
        sys.exit(1)


def init_api():
    """Facebook Ads API 初期化"""
    FacebookAdsApi.init(access_token=ACCESS_TOKEN)
    return AdAccount(AD_ACCOUNT_ID)


def upload_image(account: AdAccount, image_path: str) -> str:
    """画像をアップロードしてハッシュを返す"""
    image = AdImage(parent_id=account.get_id_assured())
    image[AdImage.Field.filename] = image_path
    image.remote_create()
    return image[AdImage.Field.hash]


def create_draft_ad(account: AdAccount, creative_data: dict, image_hash=None):
    """PAUSED状態の広告を作成（= 下書き相当）"""

    object_story_spec = {
        "page_id": PAGE_ID,
        "link_data": {
            "link": creative_data["link"],
            "message": creative_data["primary_text"],
            "name": creative_data["headline"],
            "description": creative_data["description"],
            "call_to_action": {"type": "SIGN_UP"},
        },
    }

    if image_hash:
        object_story_spec["link_data"]["image_hash"] = image_hash

    creative = account.create_ad_creative(
        params={
            AdCreative.Field.name: f"creative-{creative_data['name']}",
            AdCreative.Field.object_story_spec: object_story_spec,
        }
    )

    ad = account.create_ad(
        params={
            Ad.Field.name: creative_data["name"],
            Ad.Field.adset_id: creative_data["adset_id"],
            Ad.Field.creative: {"creative_id": creative["id"]},
            Ad.Field.status: Ad.Status.paused,
        }
    )

    return ad["id"]


def list_creatives(creatives=None):
    """作成予定の広告一覧を表示"""
    items = creatives or AD_CREATIVES
    print(f"\n📋 作成予定の広告（{len(items)}本）\n")
    print(f"{'#':<3} {'名前':<30} {'サイト':<10} {'見出し'}")
    print("-" * 80)
    for i, c in enumerate(items, 1):
        label = ADSET_LABELS.get(c["adset_id"], "???")
        print(f"{i:<3} {c['name']:<30} {label:<10} {c['headline']}")


def filter_by_site(site: str) -> list:
    """サイト名でフィルタ"""
    id_map = {"olive": OLIVE_ADSET_ID, "travis": TRAVIS_ADSET_ID, "massive": MASSIVE_ADSET_ID}
    adset_id = id_map.get(site.lower())
    if not adset_id:
        return AD_CREATIVES
    return [c for c in AD_CREATIVES if c["adset_id"] == adset_id]


def main():
    check_config()
    account = init_api()

    image_dir = Path(__file__).parent / "images"
    image_hash = None

    # サイト選択
    print("\n🌐 サイト選択:")
    print("  all     → 全サイト（13本）")
    print("  olive   → Olive のみ（4本）")
    print("  travis  → Travis のみ（4本）")
    print("  massive → Massive のみ（5本）")

    site_choice = input("\nサイト> ").strip().lower()

    if site_choice in ("olive", "travis", "massive"):
        filtered = filter_by_site(site_choice)
    else:
        filtered = AD_CREATIVES

    list_creatives(filtered)

    print("\n" + "=" * 80)
    print("⚠️  全広告は PAUSED（一時停止）状態で作成されます")
    print("   広告マネージャーで確認してからONにしてください")
    print("=" * 80)

    # 広告選択
    print("\n作成する広告を選択:")
    print(f"  all   → 全{len(filtered)}本を作成")
    print("  1,3,5 → 番号をカンマ区切りで指定")
    print("  q     → キャンセル")

    choice = input("\n> ").strip().lower()

    if choice == "q":
        print("キャンセルしました")
        return

    if choice == "all":
        selected = filtered
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(",")]
            selected = [filtered[i] for i in indices]
        except (ValueError, IndexError):
            print("❌ 無効な入力です")
            return

    # 画像アップロード
    if image_dir.exists():
        images = list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.jpeg")) + list(image_dir.glob("*.png"))
        if images:
            print(f"\n📸 画像アップロード中: {images[0].name}")
            image_hash = upload_image(account, str(images[0]))

    # 広告作成
    print(f"\n🚀 {len(selected)}本の広告を作成中...\n")
    created = []
    errors = []

    for creative_data in selected:
        try:
            if not creative_data["adset_id"]:
                raise ValueError("adset_id が未設定です。.env を確認してください")
            ad_id = create_draft_ad(account, creative_data, image_hash)
            created.append((creative_data["name"], ad_id))
            print(f"  ✅ {creative_data['name']} → Ad ID: {ad_id}")
        except Exception as e:
            errors.append((creative_data["name"], str(e)))
            print(f"  ❌ {creative_data['name']} → エラー: {e}")

    # 結果表示
    print(f"\n{'=' * 80}")
    print(f"✅ 成功: {len(created)}本  ❌ エラー: {len(errors)}本")

    if created:
        print("\n📌 次のステップ:")
        print("  1. 広告マネージャーを開く")
        print("  2. 作成された広告のクリエイティブ画像を設定")
        print("  3. プレビューで確認")
        print("  4. 問題なければステータスをONに変更")


if __name__ == "__main__":
    main()
