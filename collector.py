import sys
import argparse
import asyncio
import logging
from app.database import init_db
from app.crawler import crawler
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("leetcode_collector")

async def cmd_discover(target: int = None):
    if target:
        settings.TARGET_USERS = target
    init_db()
    crawler.initialize_cache()
    print(f"Starting discovery with TARGET_USERS={settings.TARGET_USERS}...")
    await crawler.start()
    while crawler.is_running:
        await asyncio.sleep(2)
        s = crawler.get_status()
        print(f"[PROGRESS] Action: {s['current_action']} | Discovered: {s['discovered']} | Cached: {s['cached']} | Stats Done: {s['stats_completed']}/{s['discovered']}")

    print("\nDiscovery & Stats Collection Complete!")
    print(crawler.get_status())

async def cmd_update(stale_days: int = None):
    init_db()
    crawler.initialize_cache()
    if stale_days:
        print(f"Updating users older than {stale_days} days...")
    else:
        print("Updating all users from LeetCode API...")
    await crawler.update_all(stale_days=stale_days)
    while crawler.is_running:
        await asyncio.sleep(2)
        s = crawler.get_status()
        print(f"[PROGRESS] Action: {s['current_action']} | Processed: {s['processed']}/{s['discovered']}")

    print("\nUpdate Complete!")
    print(crawler.get_status())

async def cmd_update_user(username: str):
    init_db()
    crawler.initialize_cache()
    print(f"Updating single user: {username}...")
    res = await crawler.update_user(username)
    if res.get("success"):
        print(f"Successfully updated '{username}':")
        print(f"  Name:    {res.get('actual_name')}")
        print(f"  Rating:  {res.get('rating')}")
        print(f"  Solved:  {res.get('total_questions')} (E: {res.get('easy_questions')}, M: {res.get('medium_questions')}, H: {res.get('hard_questions')})")
        print(f"  College: {res.get('college_relevance')}")
    else:
        print(f"Failed to update '{username}': {res.get('error')}")

def cmd_status():
    init_db()
    crawler.initialize_cache()
    s = crawler.get_status()
    print("========================================")
    print("      LeetCode Collector Status         ")
    print("========================================")
    print(f"Target Users:      {s['target']}")
    print(f"Discovered:        {s['discovered']}")
    print(f"Cached in CSV:     {s['cached']}")
    print(f"New Users:         {s['new_users']}")
    print(f"Stats Completed:   {s['stats_completed']}")
    print(f"Failed:            {s['failed']}")
    print(f"Pending:           {s['pending']}")
    print(f"MNNIT Verified:    {s['mnnit_count']}")
    print(f"Crawler Active:    {s['is_running']} ({s['current_action']})")
    print("========================================")

def main():
    parser = argparse.ArgumentParser(description="LeetCode Profile Collector CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # discover
    p_disc = subparsers.add_parser("discover", help="Discover new users and collect stats")
    p_disc.add_argument("--target", type=int, default=None, help="Override target user count")

    # update
    p_upd = subparsers.add_parser("update", help="Update statistics for existing users")
    p_upd.add_argument("--stale-days", type=int, default=None, help="Only update users older than N days")

    # update-user
    p_usr = subparsers.add_parser("update-user", help="Update statistics for a single user")
    p_usr.add_argument("username", type=str, help="Username to update")

    # status
    subparsers.add_parser("status", help="Show current collector status and metrics")

    args = parser.parse_args()

    if args.command == "discover":
        asyncio.run(cmd_discover(args.target))
    elif args.command == "update":
        asyncio.run(cmd_update(args.stale_days))
    elif args.command == "update-user":
        asyncio.run(cmd_update_user(args.username))
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
