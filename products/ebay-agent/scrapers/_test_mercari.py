"""メルカリスクレイパーのテスト"""
import asyncio
from playwright.async_api import async_playwright
from mercari import _load_cookies, scrape_mercari_purchases

async def test_extract():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            locale="ja-JP",
        )
        await _load_cookies(context)
        page = await context.new_page()

        await page.goto("https://jp.mercari.com/mypage/purchases", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # container構造を確認
        debug = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/transaction/"]');
            const results = [];

            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const idMatch = href.match(/\\/transaction\\/(m\\d+)/);
                if (!idMatch) continue;

                // 親要素の構造を確認
                let el = link;
                const parents = [];
                for (let i = 0; i < 5; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    parents.push(el.tagName + (el.className ? '.' + el.className.split(' ')[0] : ''));
                }

                const container = link.closest('li') || link.parentElement;
                const text = container ? container.innerText : 'NO_CONTAINER';
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                results.push({
                    id: idMatch[1],
                    parents: parents,
                    lines: lines.slice(0, 8),
                    container_tag: container ? container.tagName : 'NONE',
                });
                if (results.length >= 3) break;
            }
            return results;
        }""")

        for item in debug:
            print(f"=== {item['id']} ===")
            print(f"  container: {item['container_tag']}")
            print(f"  parents: {item['parents']}")
            print(f"  lines: {item['lines']}")
            print()

        await browser.close()


async def test_full():
    def progress(msg, cur, total):
        print(f"[{cur}/{total}] {msg}")

    results = await scrape_mercari_purchases(on_progress=progress, headless=True)
    print(f"\n=== {len(results)} items ===")
    for r in results[:5]:
        print(f"  {r['title'][:50]}  ¥{r.get('price', '?')}  {r['date']}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        asyncio.run(test_full())
    else:
        asyncio.run(test_extract())
