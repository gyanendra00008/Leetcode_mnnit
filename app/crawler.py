import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import func
from config import settings
from seed_users import load_seed_users
from app.database import get_db_session
from app.models import LeetCodeUser
from app.leetcode_client import leetcode_client
from app.csv_manager import csv_manager

logger = logging.getLogger("leetcode_collector")

class LeetCodeCrawler:
    def __init__(self, csv_mgr=None):
        self.csv_mgr = csv_mgr or csv_manager
        self.is_running = False
        self.current_action = "idle"
        self.current_user: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self._stop_requested = False
        self._task: Optional[asyncio.Task] = None
        self.initial_cached_count = 0

    def initialize_cache(self):
        """
        Loads cached users from CSV into SQLite DB.
        Adds seed users if not already present.
        Recovers stuck 'processing' statuses from previous crashes.
        """
        # 1. Load CSV cache
        csv_users = self.csv_mgr.load_users()
        completed_in_csv = sum(1 for u in csv_users.values() if u.get("stats_status") == "completed")
        self.initial_cached_count = completed_in_csv
        logger.info(f"[CACHE] Loaded {len(csv_users)} users from CSV cache ({completed_in_csv} with completed stats).")

        seeds = load_seed_users()

        with get_db_session() as session:
            # Recover stuck states
            stuck_crawls = session.query(LeetCodeUser).filter(LeetCodeUser.crawl_status == "processing").all()
            for u in stuck_crawls:
                u.crawl_status = "pending"

            stuck_stats = session.query(LeetCodeUser).filter(LeetCodeUser.stats_status == "processing").all()
            for u in stuck_stats:
                u.stats_status = "pending"

            # Sync CSV users to SQLite
            for u_lower, data in csv_users.items():
                db_user = session.query(LeetCodeUser).filter(func.lower(LeetCodeUser.username) == u_lower).first()
                if not db_user:
                    db_user = LeetCodeUser(
                        username=data["username"],
                        actual_name=data.get("actual_name") or "N/A",
                        profile_url=data.get("profile_url") or f"https://leetcode.com/u/{data['username']}/",
                        rating=data.get("rating"),
                        total_questions=data.get("total_questions", 0),
                        easy_questions=data.get("easy_questions", 0),
                        medium_questions=data.get("medium_questions", 0),
                        hard_questions=data.get("hard_questions", 0),
                        college_relevance=data.get("college_relevance", "unknown"),
                        source_user=data.get("source_user"),
                        discovered_via=data.get("discovered_via", "seed"),
                        crawl_status=data.get("crawl_status", "pending"),
                        stats_status=data.get("stats_status", "pending"),
                    )
                    session.add(db_user)
                else:
                    # Update fields from CSV if CSV has completed stats
                    if data.get("stats_status") == "completed":
                        db_user.actual_name = data.get("actual_name") or "N/A"
                        db_user.rating = data.get("rating")
                        db_user.total_questions = data.get("total_questions", 0)
                        db_user.easy_questions = data.get("easy_questions", 0)
                        db_user.medium_questions = data.get("medium_questions", 0)
                        db_user.hard_questions = data.get("hard_questions", 0)
                        db_user.college_relevance = data.get("college_relevance", "unknown")
                        db_user.stats_status = "completed"

            session.flush()

            # Sync Seed Users only if CSV was empty (initial first run)
            if not csv_users:
                for username in seeds:
                    existing = session.query(LeetCodeUser).filter(func.lower(LeetCodeUser.username) == username.lower()).first()
                    if not existing:
                        user_entry = LeetCodeUser(
                            username=username,
                            actual_name="N/A",
                            profile_url=f"https://leetcode.com/u/{username}/",
                            source_user=None,
                            discovered_via="seed",
                            crawl_status="pending",
                            stats_status="pending",
                            college_relevance="unknown",
                        )
                        session.add(user_entry)
                        logger.info(f"[DISCOVERY] Seed: {username}")

                session.flush()

                # Ensure CSV has initial seed users
                all_db_users = session.query(LeetCodeUser).all()
                all_dict = {}
                for u in all_db_users:
                    all_dict[u.username.lower()] = {
                        "username": u.username,
                        "actual_name": u.actual_name or "N/A",
                        "profile_url": u.profile_url,
                        "rating": u.rating,
                        "total_questions": u.total_questions,
                        "easy_questions": u.easy_questions,
                        "medium_questions": u.medium_questions,
                        "hard_questions": u.hard_questions,
                        "college_relevance": u.college_relevance,
                        "source_user": u.source_user,
                        "discovered_via": u.discovered_via,
                        "stats_status": u.stats_status,
                        "last_updated": u.updated_at.isoformat() if u.updated_at else datetime.now(timezone.utc).isoformat(),
                    }
                self.csv_mgr.save_all(all_dict)

    def initialize_seeds(self):
        """Backward compatible initialization alias."""
        self.initialize_cache()

    def get_status(self) -> Dict[str, Any]:
        """
        Calculates live status metrics from the database and persistent cache.
        """
        with get_db_session() as session:
            total_discovered = session.query(func.count(LeetCodeUser.id)).scalar() or 0
            successful = session.query(func.count(LeetCodeUser.id)).filter(LeetCodeUser.stats_status == "completed").scalar() or 0
            failed = session.query(func.count(LeetCodeUser.id)).filter(LeetCodeUser.stats_status == "failed").scalar() or 0
            pending = session.query(func.count(LeetCodeUser.id)).filter(LeetCodeUser.stats_status.in_(["pending", "processing"])).scalar() or 0
            mnnit_count = session.query(func.count(LeetCodeUser.id)).filter(LeetCodeUser.college_relevance == "MNNIT").scalar() or 0

            new_users = max(0, total_discovered - self.initial_cached_count)
            elapsed_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds() if self.start_time and self.is_running else 0

            return {
                "is_running": self.is_running,
                "current_action": self.current_action,
                "current_user": self.current_user,
                "elapsed_seconds": round(elapsed_seconds, 1),
                "target": settings.TARGET_USERS,
                "discovered": total_discovered,
                "cached": self.initial_cached_count,
                "new_users": new_users,
                "processed": successful + failed,
                "successful": successful,
                "stats_completed": successful,
                "failed": failed,
                "pending": pending,
                "mnnit_count": mnnit_count,
            }

    async def start(self, target: Optional[int] = None) -> bool:
        """
        Starts the background discovery and stats collection loop.
        Only fetches stats for NEW or PENDING users.
        """
        if self.is_running:
            return False

        if target and target > 0:
            settings.TARGET_USERS = target

        self.initialize_cache()
        self.is_running = True
        self.current_action = "discovering"
        self.start_time = datetime.now(timezone.utc)
        self._stop_requested = False
        self._task = asyncio.create_task(self._crawl_loop())
        return True

    def stop(self):
        """Requests the crawler to gracefully stop."""
        if self.is_running:
            self._stop_requested = True
            logger.info("[CRAWLER] Stop requested by user.")

    async def update_user(self, username: str) -> Dict[str, Any]:
        """
        Explicitly updates statistics for a single user and writes to CSV.
        """
        logger.info(f"[UPDATE] Manually updating statistics for: {username}")
        stats_res = await leetcode_client.fetch_user_stats(username)
        if not stats_res.get("success"):
            return stats_res

        with get_db_session() as session:
            user = session.query(LeetCodeUser).filter(func.lower(LeetCodeUser.username) == username.lower()).first()
            if not user:
                user = LeetCodeUser(
                    username=username,
                    profile_url=f"https://leetcode.com/u/{username}/",
                    discovered_via="manual_update",
                )
                session.add(user)

            user.actual_name = stats_res.get("actual_name") or "N/A"
            user.rating = stats_res.get("rating")
            user.total_questions = stats_res.get("total_questions", 0)
            user.easy_questions = stats_res.get("easy_questions", 0)
            user.medium_questions = stats_res.get("medium_questions", 0)
            user.hard_questions = stats_res.get("hard_questions", 0)
            user.college_relevance = stats_res.get("college_relevance", "unknown")
            user.stats_status = "completed"
            user.error_message = None
            user.updated_at = datetime.now(timezone.utc)
            session.flush()

            # Update CSV atomically
            self.csv_mgr.upsert_user({
                "username": user.username,
                "actual_name": user.actual_name,
                "profile_url": user.profile_url,
                "rating": user.rating,
                "total_questions": user.total_questions,
                "easy_questions": user.easy_questions,
                "medium_questions": user.medium_questions,
                "hard_questions": user.hard_questions,
                "college_relevance": user.college_relevance,
                "source_user": user.source_user,
                "discovered_via": user.discovered_via,
                "stats_status": user.stats_status,
                "last_updated": user.updated_at.isoformat(),
            })

            stats_res["is_new"] = is_new
            stats_res["rating_display"] = str(round(user.rating)) if user.rating is not None else "N/A"
            stats_res["unrated_reason"] = "User has no rated contest ranking" if user.rating is None else None
            stats_res["last_updated"] = user.updated_at.isoformat()

        logger.info(f"[UPDATE] Successfully updated {username} (is_new={is_new})")
        return stats_res

    async def update_all(self, stale_days: Optional[int] = None) -> bool:
        """
        Refreshes statistics for existing users (optionally only stale ones).
        """
        if self.is_running:
            return False

        with get_db_session() as session:
            query = session.query(LeetCodeUser)
            if stale_days is not None:
                threshold = datetime.now(timezone.utc) - timedelta(days=stale_days)
                query = query.filter((LeetCodeUser.updated_at < threshold) | (LeetCodeUser.updated_at.is_(None)))
            
            users = query.all()
            for u in users:
                u.stats_status = "pending"

        self.is_running = True
        self.current_action = "updating"
        self.start_time = datetime.now(timezone.utc)
        self._stop_requested = False
        self._task = asyncio.create_task(self._stats_collection_loop())
        return True

    async def refresh_stats(self) -> bool:
        """Backward compatible refresh alias."""
        return await self.update_all()

    async def _crawl_loop(self):
        """
        Orchestrates graph discovery followed by statistics collection.
        """
        logger.info(f"[CRAWLER] Started crawling loop with TARGET_USERS={settings.TARGET_USERS}")
        try:
            # 1. DISCOVERY PHASE: Crawl connections if target not yet reached
            while self.is_running and not self._stop_requested:
                with get_db_session() as session:
                    total_discovered = session.query(func.count(LeetCodeUser.id)).scalar() or 0

                if total_discovered >= settings.TARGET_USERS:
                    logger.info(f"[DISCOVERY] Discovery target met: {total_discovered}/{settings.TARGET_USERS}")
                    break

                user_to_crawl = None
                with get_db_session() as session:
                    user_to_crawl = (
                        session.query(LeetCodeUser)
                        .filter(LeetCodeUser.crawl_status == "pending")
                        .order_by(LeetCodeUser.id.asc())
                        .first()
                    )
                    if user_to_crawl:
                        user_to_crawl.crawl_status = "processing"
                        target_username = user_to_crawl.username
                        user_id = user_to_crawl.id

                if not user_to_crawl:
                    logger.info("[DISCOVERY] No more users to crawl for connections.")
                    break

                self.current_action = f"discovering (via {target_username})"
                self.current_user = target_username

                try:
                    connections = await leetcode_client.fetch_user_connections(target_username)

                    with get_db_session() as session:
                        user = session.query(LeetCodeUser).filter(LeetCodeUser.id == user_id).first()
                        if not connections.get("success"):
                            if user:
                                user.crawl_status = "failed"
                                user.retry_count += 1
                                user.error_message = connections.get("error", "Connections fetch failed")
                        else:
                            if user:
                                user.crawl_status = "completed"

                            current_total = session.query(func.count(LeetCodeUser.id)).scalar() or 0

                            # Deduplicate candidate connections across followers and following
                            seen_candidates = set()
                            candidate_connections = []
                            for f in connections.get("followers", []):
                                if not f:
                                    continue
                                f_norm = f.strip()
                                if f_norm and f_norm.lower() not in seen_candidates:
                                    seen_candidates.add(f_norm.lower())
                                    candidate_connections.append((f_norm, "followers"))

                            for f in connections.get("following", []):
                                if not f:
                                    continue
                                f_norm = f.strip()
                                if f_norm and f_norm.lower() not in seen_candidates:
                                    seen_candidates.add(f_norm.lower())
                                    candidate_connections.append((f_norm, "following"))

                            # Fast in-memory check against existing DB users
                            existing_db_users = {
                                row[0].lower() for row in session.query(LeetCodeUser.username).all()
                            }

                            new_discovered_users = []
                            for candidate_username, source_type in candidate_connections:
                                if current_total >= settings.TARGET_USERS:
                                    break
                                if candidate_username.lower() in existing_db_users:
                                    continue

                                existing_db_users.add(candidate_username.lower())
                                new_user = LeetCodeUser(
                                    username=candidate_username,
                                    actual_name="N/A",
                                    profile_url=f"https://leetcode.com/u/{candidate_username}/",
                                    source_user=target_username,
                                    discovered_via=source_type,
                                    crawl_status="pending",
                                    stats_status="pending",
                                    college_relevance="unknown",
                                )
                                session.add(new_user)
                                new_discovered_users.append(new_user)
                                current_total += 1
                                logger.info(f"[DISCOVERY] Found: {candidate_username} (via {source_type} of {target_username})")

                            session.flush()

                            # Append newly discovered users to CSV immediately
                            for nu in new_discovered_users:
                                self.csv_mgr.upsert_user({
                                    "username": nu.username,
                                    "actual_name": nu.actual_name or "N/A",
                                    "profile_url": nu.profile_url,
                                    "rating": None,
                                    "total_questions": 0,
                                    "easy_questions": 0,
                                    "medium_questions": 0,
                                    "hard_questions": 0,
                                    "college_relevance": "unknown",
                                    "source_user": nu.source_user,
                                    "discovered_via": nu.discovered_via,
                                    "stats_status": "pending",
                                    "last_updated": datetime.now(timezone.utc).isoformat(),
                                })

                            logger.info(f"[DISCOVERY] Total discovered: {current_total}/{settings.TARGET_USERS}")

                except Exception as user_err:
                    logger.error(f"[DISCOVERY] Error crawling connections for {target_username}: {user_err}", exc_info=True)
                    with get_db_session() as session:
                        user = session.query(LeetCodeUser).filter(LeetCodeUser.id == user_id).first()
                        if user:
                            user.crawl_status = "failed"
                            user.error_message = str(user_err)

                await asyncio.sleep(settings.REQUEST_DELAY)

            # 2. STATS COLLECTION PHASE: Process stats for all pending users
            if not self._stop_requested:
                await self._stats_collection_loop()

        except asyncio.CancelledError:
            logger.info("[CRAWLER] Crawl loop cancelled.")
        except Exception as e:
            logger.error(f"[CRAWLER] Error in crawl loop: {e}", exc_info=True)
        finally:
            self.is_running = False
            self.current_action = "idle"
            self.current_user = None
            self.start_time = None
            self._stop_requested = False
            logger.info("[CRAWLER] Crawl loop finished.")

    async def _stats_collection_loop(self):
        """
        Fetches statistics for users whose stats_status is pending.
        Updates DB and CSV cache on every user.
        """
        logger.info("[CRAWLER] Entering statistics collection phase.")
        try:
            while self.is_running and not self._stop_requested:
                user_for_stats = None
                with get_db_session() as session:
                    user_for_stats = (
                        session.query(LeetCodeUser)
                        .filter(LeetCodeUser.stats_status == "pending")
                        .order_by(LeetCodeUser.id.asc())
                        .first()
                    )
                    if user_for_stats:
                        user_for_stats.stats_status = "processing"
                        stats_username = user_for_stats.username
                        stats_id = user_for_stats.id

                if not user_for_stats:
                    logger.info("[CRAWLER] All pending statistics collected successfully.")
                    break

                self.current_action = f"fetching stats for {stats_username}"
                self.current_user = stats_username

                try:
                    stats_res = await leetcode_client.fetch_user_stats(stats_username)

                    with get_db_session() as session:
                        user = session.query(LeetCodeUser).filter(LeetCodeUser.id == stats_id).first()
                        if user:
                            user.updated_at = datetime.now(timezone.utc)
                            if stats_res.get("success"):
                                user.actual_name = stats_res.get("actual_name") or "N/A"
                                user.rating = stats_res.get("rating")
                                user.total_questions = stats_res.get("total_questions", 0)
                                user.easy_questions = stats_res.get("easy_questions", 0)
                                user.medium_questions = stats_res.get("medium_questions", 0)
                                user.hard_questions = stats_res.get("hard_questions", 0)
                                user.college_relevance = stats_res.get("college_relevance", "unknown")
                                user.stats_status = "completed"
                                user.error_message = None
                            else:
                                user.stats_status = "failed"
                                user.retry_count += 1
                                user.error_message = stats_res.get("error", "Stats fetch failed")

                            session.flush()

                            # Save to persistent CSV atomically
                            self.csv_mgr.upsert_user({
                                "username": user.username,
                                "actual_name": user.actual_name or "N/A",
                                "profile_url": user.profile_url,
                                "rating": user.rating,
                                "total_questions": user.total_questions,
                                "easy_questions": user.easy_questions,
                                "medium_questions": user.medium_questions,
                                "hard_questions": user.hard_questions,
                                "college_relevance": user.college_relevance,
                                "source_user": user.source_user,
                                "discovered_via": user.discovered_via,
                                "stats_status": user.stats_status,
                                "last_updated": user.updated_at.isoformat(),
                            })

                            completed = session.query(func.count(LeetCodeUser.id)).filter(LeetCodeUser.stats_status.in_(["completed", "failed"])).scalar() or 0
                            total = session.query(func.count(LeetCodeUser.id)).scalar() or 0
                            logger.info(f"[CRAWLER] Stats Progress: {completed}/{total} users processed")

                except Exception as s_err:
                    logger.error(f"[CRAWLER] Error processing stats for {stats_username}: {s_err}", exc_info=True)
                    with get_db_session() as session:
                        user = session.query(LeetCodeUser).filter(LeetCodeUser.id == stats_id).first()
                        if user:
                            user.stats_status = "failed"
                            user.error_message = str(s_err)

                await asyncio.sleep(settings.REQUEST_DELAY)

        except asyncio.CancelledError:
            logger.info("[CRAWLER] Stats collection loop cancelled.")
        except Exception as e:
            logger.error(f"[CRAWLER] Error in stats collection loop: {e}", exc_info=True)
        finally:
            self.is_running = False
            self.current_action = "idle"
            self.current_user = None
            self.start_time = None
            self._stop_requested = False

crawler = LeetCodeCrawler()
