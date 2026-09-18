import os
import asyncio
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

# Configure test environment
os.environ["DATABASE_URL"] = "sqlite:///./test_a_to_g.db"
os.environ["TARGET_USERS"] = "50"
os.environ["REQUEST_DELAY"] = "0.05"

from config import settings
from app.database import init_db, get_db_session, engine, Base
from app.models import LeetCodeUser
from app.csv_manager import CSVManager
from app.crawler import LeetCodeCrawler
from app.leetcode_client import leetcode_client

TEST_CSV = Path(__file__).resolve().parent / "data" / "test_a_to_g_users.csv"

class TestSuiteAToG(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        if TEST_CSV.is_file():
            TEST_CSV.unlink()
        tmp = TEST_CSV.parent / (TEST_CSV.name + ".tmp")
        if tmp.is_file():
            tmp.unlink()
        self.csv_mgr = CSVManager(csv_path=TEST_CSV)
        self.crawler = LeetCodeCrawler(csv_mgr=self.csv_mgr)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)
        if TEST_CSV.is_file():
            TEST_CSV.unlink()
        tmp = TEST_CSV.parent / (TEST_CSV.name + ".tmp")
        if tmp.is_file():
            tmp.unlink()

    async def test_A_existing_csv_zero_unnecessary_api_requests(self):
        """
        Test A: Put 35 users in CSV with stats_status='completed'.
        Initialize cache into DB and verify NO stats requests are made for them.
        """
        cached_users = {}
        for i in range(1, 36):
            uname = f"cached_user_{i}"
            cached_users[uname.lower()] = {
                "username": uname,
                "actual_name": f"User {i}",
                "profile_url": f"https://leetcode.com/u/{uname}/",
                "rating": 1500.0 + i,
                "total_questions": 100 + i,
                "easy_questions": 50,
                "medium_questions": 40,
                "hard_questions": 10 + i,
                "college_relevance": "MNNIT" if i % 2 == 0 else "unknown",
                "source_user": None,
                "discovered_via": "seed",
                "stats_status": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        self.csv_mgr.save_all(cached_users)

        # Initialize cache
        self.crawler.initialize_cache()

        # Verify DB has 35 completed users
        with get_db_session() as session:
            count_completed = session.query(LeetCodeUser).filter(LeetCodeUser.stats_status == "completed").count()
            self.assertEqual(count_completed, 35)

        # Mock fetch_user_stats and run _stats_collection_loop
        with patch.object(leetcode_client, "fetch_user_stats", new_callable=AsyncMock) as mock_fetch:
            self.crawler.is_running = True
            await self.crawler._stats_collection_loop()
            # Since all 35 users are 'completed', none are 'pending'
            # fetch_user_stats must be called 0 times for cached users!
            mock_fetch.assert_not_called()

        print("\n[PASS] Test A: 35 completed CSV users loaded into DB with ZERO API calls made.")

    async def test_B_new_user_only_fetched(self):
        """
        Test B: Pre-populate CSV with 2 completed users, add 1 new pending user.
        Verify ONLY the new pending user has stats fetched.
        """
        self.csv_mgr.save_all({
            "existing1": {
                "username": "existing1",
                "actual_name": "Existing One",
                "profile_url": "https://leetcode.com/u/existing1/",
                "rating": 1600.0,
                "total_questions": 200,
                "easy_questions": 100,
                "medium_questions": 80,
                "hard_questions": 20,
                "college_relevance": "MNNIT",
                "stats_status": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        })
        self.crawler.initialize_cache()

        # Add 1 new pending user
        with get_db_session() as session:
            session.add(LeetCodeUser(
                username="new_user_xyz",
                actual_name="N/A",
                profile_url="https://leetcode.com/u/new_user_xyz/",
                stats_status="pending"
            ))

        with patch.object(leetcode_client, "fetch_user_stats", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "success": True,
                "actual_name": "New User XYZ",
                "rating": 1750.5,
                "total_questions": 350,
                "easy_questions": 150,
                "medium_questions": 150,
                "hard_questions": 50,
                "college_relevance": "unknown",
            }
            self.crawler.is_running = True
            await self.crawler._stats_collection_loop()

            # Verify fetch_user_stats was called exactly ONCE, specifically for new_user_xyz
            self.assertEqual(mock_fetch.call_count, 1)
            mock_fetch.assert_called_once_with("new_user_xyz")

        # Verify CSV was updated with new_user_xyz
        loaded = self.csv_mgr.load_users()
        self.assertIn("new_user_xyz", loaded)
        self.assertEqual(loaded["new_user_xyz"]["actual_name"], "New User XYZ")
        self.assertEqual(loaded["new_user_xyz"]["rating"], 1750.5)
        print("\n[PASS] Test B: Only newly added pending user was fetched and updated in CSV.")

    async def test_C_update_user_single(self):
        """
        Test C: Update single user explicitly.
        Verify only that user's data is fetched and updated in DB and CSV.
        """
        # Seed Prateek816 with older fake rating
        self.csv_mgr.save_all({
            "prateek816": {
                "username": "Prateek816",
                "actual_name": "Prateek Fake",
                "profile_url": "https://leetcode.com/u/Prateek816/",
                "rating": 1000.0,
                "total_questions": 50,
                "easy_questions": 20,
                "medium_questions": 20,
                "hard_questions": 10,
                "college_relevance": "unknown",
                "stats_status": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
            "other_user": {
                "username": "other_user",
                "actual_name": "Other Person",
                "profile_url": "https://leetcode.com/u/other_user/",
                "rating": 1200.0,
                "total_questions": 100,
                "easy_questions": 50,
                "medium_questions": 40,
                "hard_questions": 10,
                "college_relevance": "unknown",
                "stats_status": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        })
        self.crawler.initialize_cache()

        # Manually update Prateek816 against live API
        res = await self.crawler.update_user("Prateek816")
        self.assertTrue(res["success"])
        self.assertEqual(res["actual_name"], "Prateek Rastogi")
        self.assertGreater(res["rating"], 1600.0)

        # Check that other_user remained untouched
        loaded = self.csv_mgr.load_users()
        self.assertEqual(loaded["other_user"]["actual_name"], "Other Person")
        self.assertEqual(loaded["other_user"]["rating"], 1200.0)
        self.assertEqual(loaded["prateek816"]["actual_name"], "Prateek Rastogi")
        print("\n[PASS] Test C: update_user updated Prateek816 without affecting other users.")

    async def test_D_update_all_refreshes_users(self):
        """
        Test D: update_all transitions users to pending and refreshes them.
        """
        self.csv_mgr.save_all({
            "user_a": {
                "username": "user_a",
                "actual_name": "User A",
                "profile_url": "https://leetcode.com/u/user_a/",
                "rating": 1500.0,
                "total_questions": 100,
                "easy_questions": 50,
                "medium_questions": 40,
                "hard_questions": 10,
                "college_relevance": "unknown",
                "stats_status": "completed",
                "last_updated": "2026-01-01T00:00:00Z",
            }
        })
        self.crawler.initialize_cache()

        with patch.object(leetcode_client, "fetch_user_stats", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "success": True,
                "actual_name": "User A Refreshed",
                "rating": 1550.0,
                "total_questions": 110,
                "easy_questions": 55,
                "medium_questions": 45,
                "hard_questions": 10,
                "college_relevance": "MNNIT",
            }
            # Run update_all
            await self.crawler.update_all()
            while self.crawler.is_running:
                await asyncio.sleep(0.05)

            mock_fetch.assert_called_once_with("user_a")

        loaded = self.csv_mgr.load_users()
        self.assertEqual(loaded["user_a"]["actual_name"], "User A Refreshed")
        self.assertEqual(loaded["user_a"]["rating"], 1550.0)
        print("\n[PASS] Test D: update_all successfully triggered refresh of existing users.")

    async def test_E_rating_bug_beyond_32_users(self):
        """
        Test E: Verify that 40 users processed through stats collection
        correctly retain their ratings beyond user #32 (e.g., users 33-40).
        """
        # Create 40 pending users
        with get_db_session() as session:
            for i in range(1, 41):
                session.add(LeetCodeUser(
                    username=f"student_{i}",
                    actual_name="N/A",
                    profile_url=f"https://leetcode.com/u/student_{i}/",
                    stats_status="pending"
                ))

        with patch.object(leetcode_client, "fetch_user_stats", new_callable=AsyncMock) as mock_fetch:
            async def fake_stats(uname):
                idx = int(uname.split("_")[1])
                return {
                    "success": True,
                    "actual_name": f"Student {idx}",
                    "rating": 1400.0 + (idx * 10),
                    "total_questions": 100 + idx,
                    "easy_questions": 50,
                    "medium_questions": 40,
                    "hard_questions": 10 + idx,
                    "college_relevance": "MNNIT" if idx % 2 == 0 else "unknown"
                }
            mock_fetch.side_effect = fake_stats

            self.crawler.is_running = True
            await self.crawler._stats_collection_loop()

        # Verify DB and CSV
        loaded = self.csv_mgr.load_users()
        self.assertEqual(len(loaded), 40)

        # Check users past #32: specifically 33, 34, 35, ..., 40
        for i in range(33, 41):
            key = f"student_{i}"
            self.assertIn(key, loaded)
            self.assertEqual(loaded[key]["stats_status"], "completed")
            expected_rating = 1400.0 + (i * 10)
            self.assertEqual(loaded[key]["rating"], expected_rating, f"User {key} missing expected rating")

        with get_db_session() as session:
            users_past_32 = session.query(LeetCodeUser).filter(LeetCodeUser.id >= 33, LeetCodeUser.id <= 40).all()
            for u in users_past_32:
                self.assertEqual(u.stats_status, "completed")
                self.assertIsNotNone(u.rating, f"User {u.username} has null rating!")

        print("\n[PASS] Test E: Ratings correctly populated beyond user #32 (tested up to #40).")

    async def test_F_missing_rating_genuine_unrated_displays_na(self):
        """
        Test F: If LeetCode returns no contest ranking (unrated),
        stats_status is completed, rating is None, and error_message is None (not an API failure).
        """
        res = await leetcode_client.fetch_user_stats("Shrey_Gayakvad")
        self.assertTrue(res["success"])
        self.assertIsNone(res["rating"])  # Genuine unrated user
        self.assertGreater(res["total_questions"], 0)
        self.assertIsNone(res.get("error"))

        # In CSV and DB, unrated user is saved cleanly as completed with rating=None
        with get_db_session() as session:
            u = LeetCodeUser(
                username="Shrey_Gayakvad",
                actual_name=res.get("actual_name") or "N/A",
                profile_url="https://leetcode.com/u/Shrey_Gayakvad/",
                rating=res.get("rating"),
                total_questions=res.get("total_questions", 0),
                stats_status="completed"
            )
            session.add(u)
            session.flush()
            user_dict = u.to_dict()

        self.assertEqual(user_dict["stats_status"], "completed")
        self.assertIsNone(user_dict["rating"])
        print("\n[PASS] Test F: Genuine unrated user marked completed with rating=None, distinct from failure.")

    async def test_G_crash_recovery_stuck_processing_reset(self):
        """
        Test G: Simulate crawler interruption mid-processing.
        Verify that stuck 'processing' status resets to 'pending',
        while already completed records in CSV and DB are preserved.
        """
        # Save 1 completed user in CSV
        self.csv_mgr.save_all({
            "completed_user": {
                "username": "completed_user",
                "actual_name": "Completed Person",
                "profile_url": "https://leetcode.com/u/completed_user/",
                "rating": 1800.0,
                "total_questions": 400,
                "easy_questions": 150,
                "medium_questions": 200,
                "hard_questions": 50,
                "college_relevance": "MNNIT",
                "stats_status": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        })
        self.crawler.initialize_cache()

        # Simulate a crash leaving user2 in 'processing'
        with get_db_session() as session:
            session.add(LeetCodeUser(
                username="crashed_mid_crawl",
                actual_name="N/A",
                profile_url="https://leetcode.com/u/crashed_mid_crawl/",
                stats_status="processing",
                crawl_status="processing"
            ))

        # Restart / re-initialize cache
        self.crawler.initialize_cache()

        with get_db_session() as session:
            crashed = session.query(LeetCodeUser).filter(LeetCodeUser.username == "crashed_mid_crawl").first()
            self.assertEqual(crashed.stats_status, "pending")
            self.assertEqual(crashed.crawl_status, "pending")

            comp = session.query(LeetCodeUser).filter(LeetCodeUser.username == "completed_user").first()
            self.assertEqual(comp.stats_status, "completed")
            self.assertEqual(comp.rating, 1800.0)

        print("\n[PASS] Test G: Interrupted 'processing' states safely recovered to 'pending' on restart.")

if __name__ == "__main__":
    unittest.main()
