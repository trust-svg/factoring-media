"""Extract search keywords from eBay listing titles and register them.

Strategy: Extract Brand + Model Number only. Deduplicate across languages.
"""
import asyncio
import os
import re
import sqlite3

import database as db

EBAY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ebay_agent.db")
# Fallback to relative path for dev
if not os.path.exists(EBAY_DB):
    EBAY_DB = "../ebay-agent/agent.db"

# Brand -> normalized brand name
BRANDS = {
    "akai": "AKAI", "accuphase": "Accuphase", "allen & heath": "Allen & Heath",
    "ampeg": "Ampeg", "avalon": "Avalon", "behringer": "BEHRINGER",
    "bose": "BOSE", "boss": "BOSS",
    "bandai": "Bandai", "babolat": "Babolat", "bronica": "Bronica",
    "canon": "Canon", "casio": "Casio", "contax": "Contax",
    "dbx": "DBX", "denon": "Denon", "drt": "DRT",
    "e-mu": "E-MU", "emu": "E-MU",
    "fostex": "Fostex", "fractal audio": "Fractal Audio",
    "helix": "HELIX", "jbl": "JBL", "korg": "KORG", "kowa": "KOWA",
    "lexicon": "Lexicon", "line 6": "Line 6", "line6": "Line 6",
    "digitech": "DigiTech", "digiTech": "DigiTech",
    "kenwood": "Kenwood",
    "marantz": "Marantz", "masamoto": "Masamoto",
    "medicom": "Medicom", "micro seiki": "Micro Seiki",
    "nakamichi": "Nakamichi",
    "nikon": "Nikon", "nux": "NUX",
    "onkyo": "Onkyo", "olympus": "Olympus",
    "rme": "RME", "roger mayer": "Roger Mayer",
    "pentax": "Pentax", "pilot": "Pilot", "pioneer": "Pioneer",
    "roland": "Roland", "sansui": "Sansui", "sony": "Sony",
    "shure": "Shure", "sme": "SME",
    "stax": "Stax", "taito": "TAITO", "tascam": "TASCAM",
    "teac": "TEAC", "tamiya": "Tamiya", "technics": "Technics",
    "teenage engineering": "Teenage Engineering",
    "universal audio": "Universal Audio",
    "vermicular": "Vermicular", "vertex": "Vertex", "victor": "Victor",
    "vox": "VOX", "wallhack": "WALLHACK", "xotic": "Xotic",
    "xiaomi": "Xiaomi", "yamaha": "Yamaha",
    "zoom": "ZOOM", "zuiki": "ZUIKI", "zeiss": "Zeiss",
    "smc pentax": "SMC Pentax",
}

# Model number pattern: alphanumeric with dashes/dots
MODEL_RE = re.compile(
    r"""
    ([A-Z]{1,3}[\-]?[A-Z0-9][\w\-\.\/]*   # e.g. MPC1000, SL-1200MK5, JP-8080
    (?:\s+MK\s*[IVX\d]+)?)                  # optional MK suffix
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Special product patterns (non-electronics)
SPECIAL_PRODUCTS = {
    r"(?:G-SHOCK|G-Shock)\s+([\w\-]+)": "Casio G-SHOCK {}",
    r"Samurai\s+(?:Armor|Kabuto|Yoroi|Rüstung|Armadura|Armatura)": "Samurai Armor",
    r"Edo\s+(?:Period|Periode|Tsuba).*?(?:Menpo|Kabuto|Tsuba|Kozuka|Fuchi)": "Edo Samurai",
    r"Kiritsuke\s+Yanagiba": "Kiritsuke Yanagiba",
    r"Shakuhachi": "Shakuhachi",
    r"Star\s+Wars\s+Skywalker": "Star Wars Skywalker Saga",
    r"Super\s+Sonico": "Super Sonico",
    r"Super\s+Pochaco": "Super Pochaco",
    r"Gloomy\s+Bear": "Gloomy Bear Super Sonico",
    r"Hatsune\s+Miku": "Hatsune Miku",
    r"King\s*[\-]?Ohger": "King Ohger",
    r"Kamen\s+Rider\s+W": "Kamen Rider W Double Driver",
    r"One\s+Piece\s+Going\s+Merry": "One Piece Going Merry",
    r"Bleach\s+Tensa\s+Zangetsu": "Bleach Tensa Zangetsu",
    r"Yu-Gi-Oh": "Yu-Gi-Oh Seiko Watch",
    r"Pure\s+Drive": "Babolat Pure Drive",
    r"Vanishing\s+Point.*Anna\s+Sui": "Pilot Vanishing Point Anna Sui",
    r"Vermicular\s+Frying": "Vermicular Frying Pan",
    r"Snail\s+Shell.*Shikura": "Snail Shell Shikura",
    r"Ado\s+Kyogen": "Ado Kyogen LP",
    r"Voltage\s+Converter.*(\d+)W": "{}W Voltage Converter",
    r"Edo\s+Tsuba": "Edo Tsuba",
    r"(?:Netsuke|Sagemono).*(?:Edo|Iron|Gun)": "Edo Netsuke",
    r"Kozuka\s+Edo": "Edo Kozuka",
    r"Tsuba\s+(?:Sword|Guard)": "Tsuba Sword Guard",
    r"(?:Armadura|Armatura|Armure|Rüstung).*(?:[Ss]amurai|Edo)": "Samurai Armor",
    r"(?:Samouraï|Samurai)\s+Kabuto": "Samurai Kabuto",
    r"Fullmetal\s+Alchemist": "Fullmetal Alchemist",
    r"(?:laqué|Makie|Inro).*Edo": "Edo Makie Inro",
    r"Death\s+Note.*(?:Watch|Montre)": "Death Note Watch",
    r"My\s+Hero\s+Academia.*Toga": "My Hero Academia Toga Himiko",
    r"Skypad.*SP-004": "WALLHACK Skypad SP-004",
}


def extract_keyword(title: str):
    """Extract core Brand + Model from title."""
    # Strip condition prefixes
    title = re.sub(
        r"^\[?\s*(?:Box\]?|Read\s)?\s*\[?\s*(?:Top\s+|Near\s+|N\s+)?(?:MINT|Exc[\+]*\d*|SIC)\s*(?:\d+x+)?\s*(?:w/[^\]]*)?(?:\]|\s)+",
        "", title,
    ).strip()
    title = re.sub(r"^\[\s*[^\]]*\]\s*", "", title).strip()
    title = re.sub(r"^(?:SIC\s+)?\d{5,}x*\s*", "", title).strip()

    # Check special products first
    for pattern, template in SPECIAL_PRODUCTS.items():
        m = re.search(pattern, title, re.IGNORECASE)
        if m:
            if "{}" in template and m.groups():
                return template.format(m.group(1))
            return template

    # Find brand in title
    title_lower = title.lower()
    found_brand = None
    brand_pos = len(title)

    for brand_key, brand_name in BRANDS.items():
        idx = title_lower.find(brand_key)
        if idx >= 0 and idx < brand_pos:
            brand_pos = idx
            found_brand = brand_name

    if not found_brand:
        return None

    # Extract model after brand
    after_brand = title[brand_pos + len(found_brand):]
    after_brand = after_brand.strip()

    # Find model number
    model_match = MODEL_RE.search(after_brand)
    if model_match:
        model = model_match.group(1).strip()
        # Clean trailing noise
        model = re.sub(r"\s+(Stereo|Digital|Guitar|Bass|Vintage|Integrated|Portable|Professional|Compact|Black|Silver|White|Red|Nero|Noir|Schwarz|Negro).*$", "", model, flags=re.IGNORECASE)
        keyword = f"{found_brand} {model}"
        # Normalize MK variants
        keyword = re.sub(r"\s+MK\s*", " MK", keyword)
        return keyword

    # For brands without clear model numbers, get first significant word
    words = after_brand.split()
    if words:
        first_word = words[0]
        if len(first_word) >= 2 and not first_word.lower() in {"de", "di", "du", "des", "der", "per", "für", "pour", "da", "dal"}:
            return f"{found_brand} {first_word}"

    return found_brand


def get_ebay_titles() -> list:
    conn = sqlite3.connect(EBAY_DB)
    cur = conn.execute("SELECT title FROM listings ORDER BY title")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


async def main():
    await db.init_db()
    titles = get_ebay_titles()
    print(f"eBay active listings: {len(titles)}")

    # Extract and deduplicate
    keywords = {}
    for title in titles:
        kw = extract_keyword(title)
        if kw and len(kw) >= 3:
            # Normalize key for dedup
            key = re.sub(r"\s+", " ", kw.upper().strip())
            if key not in keywords:
                keywords[key] = kw

    # Sort and register
    sorted_kws = sorted(keywords.values(), key=str.upper)
    print(f"Unique keywords: {len(sorted_kws)}")
    print()

    for kw in sorted_kws:
        await db.add_keyword(kw)
        print(f"  + {kw}")

    print(f"\nDone! {len(sorted_kws)} keywords registered.")


if __name__ == "__main__":
    asyncio.run(main())
