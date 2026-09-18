import asyncio
import logging
from config import settings
from app.database import init_db, get_db_session
from app.models import LeetCodeUser
from app.crawler import crawler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def run_test():
    print("=== Step 1: Initializing DB & Seeds ===")
    init_db()
    crawler.initialize_seeds()

    status = crawler.get_status()
    print("Initial status:", status)
    assert status["discovered"] >= 12, "Seed users should be pre-populated"

    print("\n=== Step 2: Starting Crawler to reach ~20 users ===")
    await crawler.start()

    # Poll status until target (20) is reached or crawler finishes
    for i in range(45):  # Max 45 iterations (~45s)
        await asyncio.sleep(2)
        s = crawler.get_status()
        print(f"[{i*2}s] Running={s['is_running']} | Discovered={s['discovered']} | Processed={s['processed']} | Successful={s['successful']} | Failed={s['failed']} | MNNIT={s['mnnit_count']}")
        if not s["is_running"] and s["processed"] >= 20:
            break
        if s["discovered"] >= 20 and s["pending"] == 0:
            break

    # If still running after target reached, stop gracefully
    if crawler.is_running:
        crawler.stop()
        await asyncio.sleep(2)

    final_status = crawler.get_status()
    print("\n=== Step 3: Final Crawl Status ===")
    print("Final Status:", final_status)

    with get_db_session() as session:
        users = session.query(LeetCodeUser).all()
        print(f"\nTotal users in DB: {len(users)}")
        print("Sample users:")
        for u in users[:10]:
            print(f" - {u.username}: Rating={u.rating} | Solved={u.total_questions} (E:{u.easy_questions}, M:{u.medium_questions}, H:{u.hard_questions}) | College={u.college_relevance} | Via={u.discovered_via} of {u.source_user}")

    print("\nE2E Crawl Test Completed Successfully!")

if __name__ == "__main__":
    asyncio.run(run_test())
