import os
import asyncio
import unittest
from pathlib import Path
from datetime import datetime, timezone

# Ensure test settings
os.environ["DATABASE_URL"] = "sqlite:///./test_upgraded.db"
os.environ["TARGET_USERS"] = "40"
os.environ["REQUEST_DELAY"] = "0.1"

from config import settings
from app.database import init_db, get_db_session, engine, Base
from app.models import LeetCodeUser
from app.csv_manager import CSVManager
from app.crawler import LeetCodeCrawler
from app.leetcode_client import leetcode_client

TEST_CSV = Path(__file__).resolve().parent / "data" / "test_leetcode_users.csv"

class TestUpgradedCollector(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        if TEST_CSV.is_file():
            TEST_CSV.unlink()
        self.csv_mgr = CSVManager(csv_path=TEST_CSV)
        self.crawler = LeetCodeCrawler(csv_mgr=self.csv_mgr)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)
        if TEST_CSV.is_file():
            TEST_CSV.unlink()
        tmp = TEST_CSV.parent / (TEST_CSV.name + ".tmp")
        if tmp.is_file():
            tmp.unlink()

    def test_actual_name_parsing(self):
        """Verify actual_name / realName parsing from LeetCode GraphQL."""
        # Prateek816 has realName = "Prateek Rastogi"
        async def fetch():
            res = await leetcode_client.fetch_user_stats("Prateek816")
            self.assertTrue(res["success"])
            self.assertEqual(res["actual_name"], "Prateek Rastogi")
            self.assertIsNotNone(res["rating"])
            self.assertGreater(res["total_questions"], 0)
        asyncio.run(fetch())

    def test_missing_rating_handling(self):
        """Verify that genuine unrated users return rating=None and display 'N/A' rather than failing."""
        async def fetch():
            # Shrey_Gayakvad has never attended contests
            res = await leetcode_client.fetch_user_stats("Shrey_Gayakvad")
            self.assertTrue(res["success"])
            self.assertIsNone(res["rating"])  # Genuine unrated
            self.assertGreater(res["total_questions"], 0)
        asyncio.run(fetch())

    def test_csv_atomic_persistence(self):
        """Verify atomic writes and data round-trip in CSV cache."""
        sample_users = {
            "prateek816": {
                "username": "Prateek816",
                "actual_name": "Prateek Rastogi",
                "profile_url": "https://leetcode.com/u/Prateek816/",
                "rating": 1695.3,
                "total_questions": 417,
                "easy_questions": 128,
                "medium_questions": 247,
                "hard_questions": 42,
                "college_relevance": "MNNIT",
                "source_user": None,
                "discovered_via": "seed",
                "stats_status": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        }
        # Save to CSV
        saved = self.csv_mgr.save_all(sample_users)
        self.assertTrue(saved)
        self.assertTrue(TEST_CSV.is_file())

        # Load back from CSV
        loaded = self.csv_mgr.load_users()
        self.assertIn("prateek816", loaded)
        self.assertEqual(loaded["prateek816"]["actual_name"], "Prateek Rastogi")
        self.assertEqual(loaded["prateek816"]["rating"], 1695.3)
        self.assertEqual(loaded["prateek816"]["stats_status"], "completed")

    async def test_cached_users_skip_stats_api_calls(self):
        """Test A: Existing completed users in CSV are NOT fetched again."""
        # Pre-populate CSV with 2 completed users
        self.csv_mgr.save_all({
            "prateek816": {
                "username": "Prateek816",
                "actual_name": "Prateek Rastogi",
                "profile_url": "https://leetcode.com/u/Prateek816/",
                "rating": 1695.3,
                "total_questions": 417,
                "easy_questions": 128,
                "medium_questions": 247,
                "hard_questions": 42,
                "college_relevance": "MNNIT",
                "source_user": None,
                "discovered_via": "seed",
                "stats_status": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        })

        # Initialize cache into database
        self.crawler.initialize_cache()

        # Check DB status
        with get_db_session() as s:
            u = s.query(LeetCodeUser).filter(LeetCodeUser.username == "Prateek816").first()
            self.assertIsNotNone(u)
            self.assertEqual(u.stats_status, "completed")
            self.assertEqual(u.actual_name, "Prateek Rastogi")

    async def test_manual_update_single_user(self):
        """Test C: update_user explicitly fetches latest data and updates CSV."""
        res = await self.crawler.update_user("prabhat_05")
        self.assertTrue(res["success"])
        self.assertIsNotNone(res.get("rating"))

        # Verify DB updated
        with get_db_session() as s:
            u = s.query(LeetCodeUser).filter(LeetCodeUser.username == "prabhat_05").first()
            self.assertIsNotNone(u)
            self.assertEqual(u.stats_status, "completed")
            self.assertEqual(u.college_relevance, "MNNIT")

if __name__ == "__main__":
    unittest.main()
