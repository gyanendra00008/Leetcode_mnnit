import asyncio
import httpx
import time
from app.database import get_db_session
from app.models import LeetCodeUser
from app.leetcode_client import leetcode_client

async def test_50_stats():
    with get_db_session() as s:
        # Get users from ID 30 to 80
        users = s.query(LeetCodeUser).filter(LeetCodeUser.id >= 30, LeetCodeUser.id <= 80).all()
        usernames = [u.username for u in users]

    print(f"Testing stats for {len(usernames)} users: {usernames[:5]}...")

    success_count = 0
    rated_count = 0
    fail_count = 0

    for i, u in enumerate(usernames):
        t0 = time.time()
        res = await leetcode_client.fetch_user_stats(u)
        elapsed = time.time() - t0
        if res.get("success"):
            success_count += 1
            r = res.get("rating")
            if r is not None:
                rated_count += 1
            print(f"[{i+1}/{len(usernames)}] {u} -> Solved={res.get('total_questions')}, Rating={r}, RealName={res.get('school')} ({elapsed:.2f}s)")
        else:
            fail_count += 1
            print(f"[{i+1}/{len(usernames)}] {u} -> FAILED: {res.get('error')} ({elapsed:.2f}s)")

    print(f"\nResults: Total={len(usernames)}, Success={success_count}, Rated={rated_count}, Failed={fail_count}")

if __name__ == "__main__":
    asyncio.run(test_50_stats())
