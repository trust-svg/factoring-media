"""統一抽出スキーマ — 全サイト共通の仕入れ候補データ構造

仕入れ検索の3原則「各サイトで読む情報を絞る」を実現するスキーマ。
各スクレイパーはこのスキーマに合わせてデータを返す。
不要な情報（商品説明文全文、出品者プロフィール等）は取得しない。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SourceCandidate:
    """全サイト共通の仕入れ候補スキーマ

    各スクレイパーが返すべきデータ構造。
    これ以外の情報は取得しない = コンテキストにノイズが入らない。
    """
    # 必須フィールド
    title: str                          # 商品タイトル
    price_jpy: int                      # 価格（円）
    platform: str                       # プラットフォーム名
    url: str                            # 商品ページURL

    # 準必須（取得できるサイトは必ず取得）
    image_url: str = ""                 # 商品画像URL（画像比較に必須）
    condition: str = "中古品"            # コンディション文字列
    shipping_jpy: int = 0               # 送料（円）。不明なら0

    # 任意フィールド
    seller_id: str = ""                 # 出品者ID
    is_junk: bool = False               # ジャンク品フラグ
    raw_condition_text: str = ""        # 元のコンディション文字列（正規化前）
    model_numbers: list[str] = field(default_factory=list)  # 抽出済み型番リスト

    def __post_init__(self):
        """初期化後に型番を自動抽出"""
        if not self.model_numbers:
            self.model_numbers = self._extract_model_numbers()
        if not self.raw_condition_text:
            self.raw_condition_text = self.condition

    def _extract_model_numbers(self) -> list[str]:
        """タイトルから型番トークンを抽出"""
        tokens = []
        for word in self.title.split():
            if not re.search(r"\d", word):
                continue
            if re.match(r"^\d+$", word):
                continue
            if len(word) >= 2:
                tokens.append(word.upper())
        return tokens

    @property
    def total_price_jpy(self) -> int:
        """合計価格（本体 + 送料）"""
        return self.price_jpy + self.shipping_jpy

    @property
    def has_image(self) -> bool:
        """画像URLがあるか"""
        return bool(self.image_url)

    def to_dict(self) -> dict:
        """辞書変換（API応答・DB保存用）"""
        return {
            "title": self.title,
            "price_jpy": self.price_jpy,
            "shipping_jpy": self.shipping_jpy,
            "total_price_jpy": self.total_price_jpy,
            "condition": self.condition,
            "platform": self.platform,
            "url": self.url,
            "image_url": self.image_url,
            "is_junk": self.is_junk,
            "seller_id": self.seller_id,
            "model_numbers": self.model_numbers,
        }


@dataclass
class ScoredCandidate:
    """スコアリング後の候補（スコア内訳付き）"""
    candidate: SourceCandidate
    total_score: float                  # 合計スコア（0〜100）
    price_score: float = 0.0           # 価格スコア（0〜30）
    condition_score: float = 0.0       # コンディションスコア（0〜25）
    relevance_score: float = 0.0       # タイトル関連度（0〜15）
    image_match_score: float = 0.0     # 画像一致度（0〜30）
    image_match_result: str = "pending" # "yes" | "maybe" | "no" | "skip" | "pending"
    reliability_bonus: float = 0.0      # サイト信頼度ボーナス

    def to_dict(self) -> dict:
        """辞書変換（スコア内訳付き）"""
        d = self.candidate.to_dict()
        d.update({
            "score": round(self.total_score, 1),
            "score_breakdown": {
                "price": round(self.price_score, 1),
                "condition": round(self.condition_score, 1),
                "relevance": round(self.relevance_score, 1),
                "image_match": round(self.image_match_score, 1),
                "image_match_result": self.image_match_result,
                "reliability_bonus": round(self.reliability_bonus, 1),
            },
        })
        return d
