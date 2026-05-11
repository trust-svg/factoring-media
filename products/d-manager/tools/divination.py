"""
占術エンジン: 九星気学 + 四柱推命
オーナー生年月日: 1981年12月29日（出生時刻不明のため時柱なし）

【アンカー】
  日干支: 2000年1月1日 = 甲子(index 0)
  日九星: 2000年1月1日 = 一白水星
  ※実際の運勢サイトと1〜2日ずれる場合は ANCHOR_OFFSET で調整
"""

import math
from datetime import date, datetime
from typing import Optional

# ── 定数 ─────────────────────────────────────────────

JIKKAN  = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
JUNISHI = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]

JIKKAN_GOGYO  = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土",
                 "己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
JUNISHI_GOGYO = {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火",
                 "午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"}

KYUSEI_NAME = ["","一白水星","二黒土星","三碧木星","四緑木星","五黄土星",
               "六白金星","七赤金星","八白土星","九紫火星"]
KYUSEI_ELEMENT = {1:"水",2:"土",3:"木",4:"木",5:"土",6:"金",7:"金",8:"土",9:"火"}
KYUSEI_KEYWORDS = {
    1: "流動・知恵・内省・人脈",
    2: "勤勉・育成・忍耐・蓄積",
    3: "発展・活動・創造・新スタート",
    4: "信頼・交流・調和・旅",
    5: "変革・中心・破壊と再生",
    6: "リーダーシップ・決断・権威・天",
    7: "喜悦・交渉・収穫・弁舌",
    8: "変化・継承・蓄財・山",
    9: "名誉・直感・美・情熱・顕現",
}

# 五行: 相生(生む) / 相克(制す)
GOGYO_GENERATES = {"木":"火","火":"土","土":"金","金":"水","水":"木"}
GOGYO_CONTROLS  = {"木":"土","火":"金","土":"水","金":"木","水":"火"}

# 日盤アンカー: 2000年1月1日 = 甲子(index 0) = 一白水星
_ANCHOR       = date(2000, 1, 1)
ANCHOR_OFFSET = 0  # ←ずれが生じたらここで ±1 調整

# 節入り概算日 (month → sekki開始日)
_SEKKI_DAY = {1:6, 2:4, 3:6, 4:5, 5:6, 6:6, 7:7, 8:7, 9:8, 10:8, 11:7, 12:7}

# ── 生年月日 ─────────────────────────────────────────
BIRTH_DATE = date(1981, 12, 29)

# ── 月齢アンカー（既知の新月日時 UTC）─────────────────────
# 2000-01-06 18:14 UTC = 既知の新月
_NEW_MOON_ANCHOR_JD = 2451550.259  # ユリウス日
_SYNODIC_MONTH = 29.530588853      # 朔望月(日)


# ── 九年運サイクル ────────────────────────────────────
# 本命星9(九紫火星)の九年運: 9が「顕現年」= 基点
# 立春基準の年九星をそのまま使い、本命星との関係で解釈
_NINE_YEAR_THEME = {
    "比和":     ("顕現・実りの年", "これまでの努力が形になる年。積極的な発信と行動を。"),
    "相生(生)": ("貢献・与える年",  "力を注ぐことで大きな成果が生まれる。消耗に注意。"),
    "相生(受)": ("充電・飛躍前年",  "サポートを受けやすい。学びと準備に最適。"),
    "相克(制)": ("主導・拡大年",    "自分が流れを作れる年。強引にならずリードを。"),
    "相克(被)": ("忍耐・蓄積年",    "表に出るより内を固める年。焦らず土台を作ろう。"),
}

# ── 基本計算 ─────────────────────────────────────────

def _digit_reduce(n: int) -> int:
    """桁和を1桁になるまで繰り返す"""
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def _year_star_num(year: int) -> int:
    """暦年から九星番号を返す (1〜9)"""
    s = _digit_reduce(year)
    r = 10 - s
    return 9 if r in (0, 10) else r


def _kyusei_year(d: date) -> int:
    """立春(2/4)基準の年九星"""
    y = d.year if (d.month > 2 or (d.month == 2 and d.day >= 4)) else d.year - 1
    return _year_star_num(y)


def _month_index(d: date) -> int:
    """
    節入り基準の月インデックス
    1=寅月(立春後) 〜 12=丑月(小寒〜立春前)
    """
    m, day = d.month, d.day
    after = day >= _SEKKI_DAY[m]
    if after:
        return 12 if m == 1 else m - 1
    else:
        if m == 1: return 11   # 子月
        if m == 2: return 12   # 丑月
        return m - 2           # 一つ前の月


def _kyusei_month(year_star: int, month_idx: int) -> int:
    """月九星: 年九星グループ別の基準から月ごとに逆順で下がる"""
    if year_star in (1, 4, 7):
        base = 8
    elif year_star in (2, 5, 8):
        base = 5
    else:
        base = 2
    return ((base - 1 - (month_idx - 1)) % 9) + 1


def _day_kanshi_index(d: date) -> int:
    """日の干支インデックス 0=甲子 … 59=癸亥"""
    return ((d - _ANCHOR).days + ANCHOR_OFFSET) % 60


def _kyusei_day(d: date) -> int:
    """日九星 (1〜9)"""
    return (((d - _ANCHOR).days + ANCHOR_OFFSET) % 9) + 1


def _kanshi_str(idx: int) -> str:
    return JIKKAN[idx % 10] + JUNISHI[idx % 12]


# ── 月齢計算 ─────────────────────────────────────────

def _date_to_jd(d: date) -> float:
    """日付 → ユリウス日 (正午基準)"""
    dt = datetime(d.year, d.month, d.day, 12, 0, 0)
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = (dt.day + (153 * m + 2) // 5 + 365 * y
           + y // 4 - y // 100 + y // 400 - 32045)
    return jdn - 0.5  # 正午→深夜0時基準に補正


def moon_age(d: Optional[date] = None) -> float:
    """月齢 (0=新月, ~14.7=満月, ~29.5で次の新月)"""
    if d is None:
        d = date.today()
    jd = _date_to_jd(d)
    cycles = (jd - _NEW_MOON_ANCHOR_JD) / _SYNODIC_MONTH
    return (cycles % 1) * _SYNODIC_MONTH


def moon_phase_info(d: Optional[date] = None) -> dict:
    """月相の名前・アイコン・行動指針を返す"""
    age = moon_age(d)
    if age < 1.85:
        phase, icon = "新月",   "🌑"
        action = "新しい意図を立てる。種まき・計画・始動に最適。"
        avoid  = "無理な強行・散財。エネルギーが低い時期。"
    elif age < 7.38:
        phase, icon = "三日月〜上弦前", "🌒"
        action = "行動開始・仕込み。意図したことを動かし始める。"
        avoid  = "方向転換・撤退。始めたことを信じて進もう。"
    elif age < 9.22:
        phase, icon = "上弦",   "🌓"
        action = "軌道修正・決断。半分まで来た。見直して加速。"
        avoid  = "迷い・先延ばし。判断の時。"
    elif age < 14.77:
        phase, icon = "十三夜〜満月前", "🌔"
        action = "加速・最大展開。エネルギーが高まっている。"
        avoid  = "引きこもり・消極性。今こそ外に出よう。"
    elif age < 16.61:
        phase, icon = "満月",   "🌕"
        action = "収穫・感謝・発信。成果を受け取り人と分かち合う。"
        avoid  = "新規スタート。収穫の時、刈り入れに集中。"
    elif age < 22.15:
        phase, icon = "十六夜〜下弦前", "🌖"
        action = "手放し・整理。不要なものを手放し、内省を深める。"
        avoid  = "新しい約束・大きな投資。"
    elif age < 24.0:
        phase, icon = "下弦",   "🌗"
        action = "断捨離・完結。プロジェクトのまとめ・締め切り作業。"
        avoid  = "感情的な対立。冷静に整理する時期。"
    else:
        phase, icon = "晦日〜新月前", "🌘"
        action = "静養・回復・内省。次のサイクルへの準備期間。"
        avoid  = "無理な行動・重要な決断。休息を優先。"
    return {"phase": phase, "icon": icon, "age": age,
            "action": action, "avoid": avoid}


# ── バイオリズム計算 ─────────────────────────────────────

_BIO_CYCLES = {"身体": 23, "感情": 28, "知性": 33}

def biorhythm(d: Optional[date] = None) -> dict:
    """
    バイオリズム: 各サイクルの値(-100〜+100)とフェーズ説明を返す
    ゼロ交差日は「注意日」
    """
    if d is None:
        d = date.today()
    days = (d - BIRTH_DATE).days
    result = {}
    for name, period in _BIO_CYCLES.items():
        val = math.sin(2 * math.pi * days / period) * 100
        # 明日との差分でゼロ交差チェック
        val_next = math.sin(2 * math.pi * (days + 1) / period) * 100
        crossing = (val * val_next < 0)  # 符号が変わる = ゼロ交差

        if crossing:
            phase = "転換点(注意)"
        elif val > 50:
            phase = "高調"
        elif val > 0:
            phase = "上昇中"
        elif val > -50:
            phase = "下降中"
        else:
            phase = "低調"

        result[name] = {"value": round(val, 1), "phase": phase, "crossing": crossing}
    return result


def _bio_bar(val: float) -> str:
    """値を視覚的なバーで表示 (-100〜+100)"""
    filled = round((val + 100) / 200 * 10)
    return "█" * filled + "░" * (10 - filled)


# ── 九年運サイクル ────────────────────────────────────

def nine_year_cycle(d: Optional[date] = None) -> dict:
    """今年の九年運（本命星との関係で解釈）"""
    if d is None:
        d = date.today()
    year_s   = _kyusei_year(d)
    honmei   = honmei_star()
    honmei_el = KYUSEI_ELEMENT[honmei]
    year_el   = KYUSEI_ELEMENT[year_s]
    relation  = _gogyo_relation(honmei_el, year_el)
    theme, advice = _NINE_YEAR_THEME.get(relation, ("", ""))
    return {
        "year_star": year_s,
        "year_star_name": KYUSEI_NAME[year_s],
        "relation": relation,
        "theme": theme,
        "advice": advice,
    }


# ── 本命星・月命星・誕生日柱 ─────────────────────────────

def honmei_star() -> int:
    """本命星: 九紫火星(9)"""
    return _year_star_num(1981)   # 1981/12/29 は立春以降 → 1981年適用


def tsuki_meisei() -> int:
    """月命星: 子月(index 11) → 一白水星(1)"""
    ys = _year_star_num(1981)
    return _kyusei_month(ys, _month_index(BIRTH_DATE))


def birth_pillars() -> dict:
    """誕生日の四柱(時柱なし)"""
    idx = _day_kanshi_index(BIRTH_DATE)
    return {
        "year":  "辛酉",          # 1981年
        "month": "庚子",          # 子月(12月節入り後)
        "day":   _kanshi_str(idx),
        "hour":  "不明",
    }


# ── 五行の関係 ──────────────────────────────────────────

def _gogyo_relation(from_el: str, to_el: str) -> str:
    if from_el == to_el:
        return "比和"
    if GOGYO_GENERATES[from_el] == to_el:
        return "相生(生)"    # from が to を生む → 消耗するが成果を出す
    if GOGYO_GENERATES[to_el] == from_el:
        return "相生(受)"    # to が from を生む → エネルギーをもらえる
    if GOGYO_CONTROLS[from_el] == to_el:
        return "相克(制)"    # from が to を制す → 主導権を持てる
    return "相克(被)"        # to が from を制す → 消耗・慎重モード


# ── 指針テキスト ─────────────────────────────────────

_RELATION_TEXT = {
    "比和":     ("本命星と同気。自分の本質が発揮しやすい日",
                 "直感を信じ、自分らしく動こう。独りよがりに注意。"),
    "相生(生)": ("自分のエネルギーを注ぐことで成果が出る日",
                 "与えることで流れが生まれる。疲れ過ぎには気をつけて。"),
    "相生(受)": ("流れが味方し、サポートを受けやすい日",
                 "人の言葉に耳を傾けて。良いチャンスを見逃さない。"),
    "相克(制)": ("物事を動かしやすく、主導権を持てる日",
                 "強引になりすぎず、相手への配慮も忘れずに。"),
    "相克(被)": ("エネルギーが削がれやすく、消耗しやすい日",
                 "新規チャレンジより現状を守る。大事な決断は翌日に。"),
}

_DAY_STAR_DO = {
    1: ["情報収集・リサーチ・学習", "人脈・ネットワーク活動", "計画の見直し・内省・書くこと"],
    2: ["地道な実務・タスク処理", "育成・サポート・フォロー業務", "整理整頓・蓄積作業"],
    3: ["新規アクション・スタートを切る", "プレゼン・発信・SNS更新", "行動量を増やすこと"],
    4: ["交渉・コミュニケーション", "信頼関係の構築・メール返信", "外出・出会い・旅行"],
    5: ["重要な決断・大きな変革", "不要なものの断捨離・リセット", "中心軸・ビジョンの再確認"],
    6: ["リーダーシップの発揮・指示出し", "重要な判断・規律の整備", "長期計画・方向性の確定"],
    7: ["交渉・営業・商談・クロージング", "お礼・感謝を伝える", "楽しむ・喜びを感じる活動"],
    8: ["変化への準備・移行作業", "蓄財・節約・投資見直し", "継承・引き継ぎ・仕組み整備"],
    9: ["アピール・発信・PR・露出", "クリエイティブな活動", "直感に従って動くこと"],
}

_DAY_STAR_AVOID = {
    1: ["曖昧な態度・優柔不断", "孤立・殻に閉じこもる"],
    2: ["強い自己主張", "変化を急ぐ・焦り"],
    3: ["軽率な発言・根拠なき行動", "計画なしの突撃"],
    4: ["約束破り・先延ばし", "優柔不断な態度"],
    5: ["感情的な判断・衝動買い", "現状への無意味な執着"],
    6: ["独断・独善・強引な押し付け", "細部への過度なこだわり"],
    7: ["散財・衝動的な支出", "軽い口約束"],
    8: ["頑固さ・変化の拒絶", "ため込み・情報独占"],
    9: ["見栄・虚飾・盛りすぎ", "感情的な爆発・激しい言動"],
}

_MONTH_THEME = {
    1: "内省と準備の月。静かに力を蓄え、水のように柔軟に動く",
    2: "地道な積み重ねの月。焦らず一歩ずつ、土台を固める",
    3: "行動と発展の月。積極的に動き、新しいことを始める",
    4: "交流と信頼の月。人との縁を深め、調和を育む",
    5: "変革と決断の月。大きな変化と向き合い、恐れず選択する",
    6: "決断とリーダーシップの月。天の流れに乗り、方向を定める",
    7: "収穫と喜びの月。成果を受け取り、人と分かち合う",
    8: "転換と蓄積の月。変化を受け入れ、次のステージへ準備する",
    9: "表現と顕現の月。これまでの努力が形になり始める",
}

_MONTH_DO = {
    1: ["深い思考・戦略立案", "人脈の棚卸しと再構築", "内側に向かう活動・学習"],
    2: ["実務・作業の積み上げ", "サポート・育成業務", "節約・資産の見直し"],
    3: ["新規事業・新しいチャレンジ", "発信・マーケティング強化", "行動量を大幅に増やす"],
    4: ["パートナーシップの強化", "対外コミュニケーション・商談", "長期的な信頼の構築"],
    5: ["重要な意思決定・大改革", "不要なものを手放す", "自分の中心軸の見直し"],
    6: ["組織・仕組みづくり", "重要な判断・長期計画の確定", "ビジョンと価値観の整理"],
    7: ["交渉・営業・セールス活動", "成果の棚卸しと振り返り", "モチベーション管理・楽しむ"],
    8: ["蓄財・投資・節約", "変化への適応準備", "継承・仕組みの整備"],
    9: ["アウトプット・発信・PR", "ブランディング強化", "ビジョンの可視化と共有"],
}


def _build_biorhythm_text(d: date) -> str:
    bio = biorhythm(d)
    lines = ["【バイオリズム】"]
    warnings = []
    for name, info in bio.items():
        bar = _bio_bar(info["value"])
        warn = " ⚠️転換点" if info["crossing"] else ""
        lines.append(f"  {name}: [{bar}] {info['phase']}{warn}")
        if info["crossing"]:
            warnings.append(name)
    if warnings:
        lines.append(f"  → {'/'.join(warnings)}が転換点。判断・行動は慎重に。")
    # 総合コメント
    vals = [v["value"] for v in bio.values()]
    avg = sum(vals) / len(vals)
    if avg > 40:
        lines.append("  総合: エネルギー高め。積極的に動ける日。")
    elif avg < -40:
        lines.append("  総合: エネルギー低め。無理せず回復優先。")
    return "\n".join(lines)


def _build_moon_text(d: date) -> str:
    m = moon_phase_info(d)
    return (f"【月相】{m['icon']} {m['phase']}（月齢 {m['age']:.1f}）\n"
            f"  やること: {m['action']}\n"
            f"  避けること: {m['avoid']}")


def _build_nine_year_text(d: date) -> str:
    cy = nine_year_cycle(d)
    return (f"【今年の運気】年盤: {cy['year_star_name']} / {cy['relation']} → {cy['theme']}\n"
            f"  {cy['advice']}")


def _build_daily_text(honmei: int, day_s: int, month_s: int,
                      relation: str, kanshi: str) -> str:
    rel_desc, rel_advice = _RELATION_TEXT.get(relation, ("", ""))
    lines = [
        f"【九星】日盤: {KYUSEI_NAME[day_s]}　月盤: {KYUSEI_NAME[month_s]}",
        f"【日柱】{kanshi}　【今日のキーワード】{KYUSEI_KEYWORDS[day_s]}",
        "",
        f"【本命星({KYUSEI_NAME[honmei]})との関係】{relation}",
        f"　{rel_desc}",
        f"　→ {rel_advice}",
        "",
        "【今日すべきこと】",
    ]
    for a in _DAY_STAR_DO[day_s]:
        lines.append(f"  ✓ {a}")
    lines += ["", "【今日避けること】"]
    for av in _DAY_STAR_AVOID[day_s]:
        lines.append(f"  ✗ {av}")
    return "\n".join(lines)


def _build_monthly_text(honmei: int, month_s: int, relation: str) -> str:
    rel_desc, rel_advice = _RELATION_TEXT.get(relation, ("", ""))
    lines = [
        f"【今月の九星】{KYUSEI_NAME[month_s]}",
        f"【今月のテーマ】{_MONTH_THEME[month_s]}",
        "",
        f"【本命星({KYUSEI_NAME[honmei]})との関係】{relation}",
        f"　{rel_desc}",
        f"　→ {rel_advice}",
        "",
        "【今月の重点アクション】",
    ]
    for f in _MONTH_DO[month_s]:
        lines.append(f"  ✓ {f}")
    return "\n".join(lines)


# ── 公開 API ─────────────────────────────────────────

def get_daily_summary(d: Optional[date] = None) -> str:
    """朝ブリーフィング用の日次占術サマリー"""
    if d is None:
        d = date.today()

    ys = _kyusei_year(d)
    mi = _month_index(d)
    ms = _kyusei_month(ys, mi)
    ds = _kyusei_day(d)
    kanshi = _kanshi_str(_day_kanshi_index(d))

    honmei = honmei_star()
    honmei_el = KYUSEI_ELEMENT[honmei]
    day_el    = KYUSEI_ELEMENT[ds]
    relation  = _gogyo_relation(honmei_el, day_el)

    body = _build_daily_text(honmei, ds, ms, relation, kanshi)
    moon = _build_moon_text(d)
    bio  = _build_biorhythm_text(d)
    year_text = _build_nine_year_text(d)
    return "\n\n".join([
        "━━ 今日の占術指針（九星気学・四柱推命）━━",
        body,
        moon,
        bio,
        year_text,
    ])


def get_monthly_summary(d: Optional[date] = None) -> str:
    """月初ブリーフィング用の月次占術サマリー"""
    if d is None:
        d = date.today()

    ys = _kyusei_year(d)
    mi = _month_index(d)
    ms = _kyusei_month(ys, mi)

    honmei    = honmei_star()
    honmei_el = KYUSEI_ELEMENT[honmei]
    month_el  = KYUSEI_ELEMENT[ms]
    relation  = _gogyo_relation(honmei_el, month_el)

    body = _build_monthly_text(honmei, ms, relation)
    return f"━━ 今月の占術指針（九星気学）━━\n{body}"
