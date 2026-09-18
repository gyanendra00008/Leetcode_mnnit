import asyncio
import os
import unittest
from pathlib import Path

# Ensure test env
os.environ["TARGET_USERS"] = "20"
os.environ["DATABASE_URL"] = "sqlite:///./test_leetcode.db"
os.environ["REQUEST_DELAY"] = "0.2"

from config import settings
from app.utils import normalize_username, extract_usernames_from_text, check_mnnit_affiliation
from app.database import init_db, get_db_session, engine, Base
from app.models import LeetCodeUser
from seed_users import load_seed_users
from app.leetcode_client import leetcode_client
from app.crawler import crawler

class TestLeetCodeCollector(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Fresh database for test
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def test_seed_normalization(self):
        # 1. Plain username
        self.assertEqual(normalize_username("prabhat_05"), "prabhat_05")
        # 2. Profile URL
        self.assertEqual(normalize_username("https://leetcode.com/u/Prateek816/"), "Prateek816")
        # 3. Concatenated duplicate URLs
        triple_url = "https://leetcode.com/u/Aryanifie/https://leetcode.com/u/Aryanifie/https://leetcode.com/u/Aryanifie/"
        self.assertEqual(normalize_username(triple_url), "Aryanifie")

        # 4. Extract usernames from text
        sample_text = """
        prabhat_05
        https://leetcode.com/u/Prateek816/
        https://leetcode.com/u/Aryanifie/https://leetcode.com/u/Aryanifie/https://leetcode.com/u/Aryanifie/
        """
        extracted = extract_usernames_from_text(sample_text)
        self.assertEqual(len(extracted), 3)
        self.assertIn("prabhat_05", extracted)
        self.assertIn("Prateek816", extracted)
        self.assertIn("Aryanifie", extracted)

    def test_mnnit_affiliation_check(self):
        # Explicit MNNIT variations
        self.assertEqual(check_mnnit_affiliation(school="Motilal Nehru National Institute of Technology"), "MNNIT")
        self.assertEqual(check_mnnit_affiliation(school="MNNIT Allahabad"), "MNNIT")
        self.assertEqual(check_mnnit_affiliation(about_me="Student at MNNIT Prayagraj"), "MNNIT")
        self.assertEqual(check_mnnit_affiliation(school="mnnit"), "MNNIT")

        # Non-MNNIT / Unknown
        self.assertEqual(check_mnnit_affiliation(school="IIT Bombay"), "unknown")
        self.assertEqual(check_mnnit_affiliation(school=None, about_me=None), "unknown")
        self.assertEqual(check_mnnit_affiliation(school="nit allahbad"), "unknown")

    def test_database_initialization_and_seeds(self):
        crawler.initialize_seeds()
        with get_db_session() as session:
            count = session.query(LeetCodeUser).count()
            self.assertGreaterEqual(count, 12)
            prateek = session.query(LeetCodeUser).filter(LeetCodeUser.username == "Prateek816").first()
            self.assertIsNotNone(prateek)
            self.assertEqual(prateek.discovered_via, "seed")
            self.assertIn(prateek.stats_status, ["pending", "completed"])

    async def test_leetcode_client_fetch(self):
        # Test stats query on known user
        stats = await leetcode_client.fetch_user_stats("Prateek816")
        self.assertTrue(stats["success"])
        self.assertGreater(stats["total_questions"], 0)
        self.assertEqual(stats["college_relevance"], "MNNIT")
        self.assertIsNotNone(stats["rating"])

        # Test connections query
        connections = await leetcode_client.fetch_user_connections("Prateek816")
        self.assertTrue(connections["success"])
        self.assertIsInstance(connections["followers"], list)
        self.assertIsInstance(connections["following"], list)

    async def test_crawler_resumption(self):
        # Insert a user and mark completed
        with get_db_session() as session:
            u1 = LeetCodeUser(
                username="test_user_1",
                profile_url="https://leetcode.com/u/test_user_1/",
                stats_status="completed",
                crawl_status="completed",
                total_questions=100
            )
            u2 = LeetCodeUser(
                username="test_user_2",
                profile_url="https://leetcode.com/u/test_user_2/",
                stats_status="processing",
                crawl_status="processing",
            )
            session.add_all([u1, u2])

        # Initializing seeds should recover stuck 'processing' states to 'pending'
        crawler.initialize_seeds()

        with get_db_session() as session:
            db_u1 = session.query(LeetCodeUser).filter(LeetCodeUser.username == "test_user_1").first()
            self.assertEqual(db_u1.stats_status, "completed")
            db_u2 = session.query(LeetCodeUser).filter(LeetCodeUser.username == "test_user_2").first()
            self.assertEqual(db_u2.stats_status, "pending")
            self.assertEqual(db_u2.crawl_status, "pending")

if __name__ == "__main__":
    unittest.main()
