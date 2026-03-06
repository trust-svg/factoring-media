"""eBay API diagnostic test"""
import logging
logging.basicConfig(level=logging.INFO)

from ebay_core.client import get_active_listings

print("=== get_active_listings (with Trading API fallback) ===")
try:
    items = get_active_listings()
    print(f"Total items: {len(items)}")
    print(f"Out of stock: {sum(1 for i in items if i.is_out_of_stock)}")
    print(f"In stock: {sum(1 for i in items if not i.is_out_of_stock)}")
    print()
    for i, item in enumerate(items[:10], 1):
        status = "OUT OF STOCK" if item.is_out_of_stock else f"qty={item.quantity}"
        print(f"  {i}. [{item.sku[:20]}] {item.title[:50]} | ${item.price_usd:.2f} | {status}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
