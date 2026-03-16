"""Remove irrelevant listings from DB where keyword words don't all appear in title."""
import asyncio
import aiosqlite
import config

DB = config.DATABASE_PATH


async def main():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row

        # Get all listings with their keyword
        cur = await db.execute("""
            SELECT l.id, l.title, k.name as keyword
            FROM listings l JOIN keywords k ON l.keyword_id = k.id
        """)
        rows = await cur.fetchall()

        to_delete = []
        for row in rows:
            kw_words = row["keyword"].lower().split()
            title_lower = row["title"].lower()
            if not all(w in title_lower for w in kw_words):
                to_delete.append(row["id"])

        if not to_delete:
            print("No irrelevant listings found.")
            return

        print(f"Found {len(to_delete)} irrelevant listings out of {len(rows)} total.")
        print(f"Deleting...")

        await db.execute(
            f"DELETE FROM listings WHERE id IN ({','.join('?' * len(to_delete))})",
            to_delete,
        )
        await db.commit()
        print(f"Deleted {len(to_delete)} irrelevant listings.")


if __name__ == "__main__":
    asyncio.run(main())
