import csv
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("leetcode_collector")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_FILE = DATA_DIR / "leetcode_users.csv"
TMP_CSV_FILE = DATA_DIR / "leetcode_users.tmp.csv"

CSV_COLUMNS = [
    "username",
    "actual_name",
    "profile_url",
    "rating",
    "total_questions",
    "easy_questions",
    "medium_questions",
    "hard_questions",
    "college_relevance",
    "source_user",
    "discovered_via",
    "stats_status",
    "last_updated",
]

class CSVManager:
    def __init__(self, csv_path: Path = CSV_FILE):
        self.csv_path = csv_path
        self.tmp_path = csv_path.parent / (csv_path.name + ".tmp")
        self._ensure_dir()

    def _ensure_dir(self):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def load_users(self) -> Dict[str, Dict[str, Any]]:
        """
        Loads all users from the persistent CSV cache.
        Returns a dictionary keyed by lowercase username for O(1) case-insensitive lookup.
        """
        self._ensure_dir()
        if not self.csv_path.is_file():
            return {}

        users = {}
        try:
            with open(self.csv_path, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    u = row.get("username", "").strip()
                    if not u:
                        continue
                    
                    # Parse numerical fields safely
                    def to_int(val, default=0):
                        try:
                            return int(val) if val not in (None, "", "null", "None") else default
                        except (ValueError, TypeError):
                            return default

                    def to_float(val, default=None):
                        try:
                            return float(val) if val not in (None, "", "null", "None", "N/A") else default
                        except (ValueError, TypeError):
                            return default

                    user_data = {
                        "username": u,
                        "actual_name": row.get("actual_name") or "N/A",
                        "profile_url": row.get("profile_url") or f"https://leetcode.com/u/{u}/",
                        "rating": to_float(row.get("rating")),
                        "total_questions": to_int(row.get("total_questions")),
                        "easy_questions": to_int(row.get("easy_questions")),
                        "medium_questions": to_int(row.get("medium_questions")),
                        "hard_questions": to_int(row.get("hard_questions")),
                        "college_relevance": row.get("college_relevance") or "unknown",
                        "source_user": row.get("source_user") if row.get("source_user") not in ("", "None", "null") else None,
                        "discovered_via": row.get("discovered_via") or "seed",
                        "stats_status": row.get("stats_status") or "pending",
                        "last_updated": row.get("last_updated") or datetime.now(timezone.utc).isoformat(),
                    }
                    users[u.lower()] = user_data
        except Exception as e:
            logger.error(f"[CSV] Error reading {self.csv_path}: {e}")

        return users

    def save_all(self, users_dict: Dict[str, Dict[str, Any]]) -> bool:
        """
        Atomically saves all user records to CSV using a temporary file.
        Prevents corrupting CSV on unexpected power loss or crashes.
        """
        self._ensure_dir()
        try:
            with open(self.tmp_path, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                for user in users_dict.values():
                    row = {
                        "username": user.get("username", ""),
                        "actual_name": user.get("actual_name") or "N/A",
                        "profile_url": user.get("profile_url", ""),
                        "rating": round(user["rating"], 1) if user.get("rating") is not None else "",
                        "total_questions": user.get("total_questions", 0),
                        "easy_questions": user.get("easy_questions", 0),
                        "medium_questions": user.get("medium_questions", 0),
                        "hard_questions": user.get("hard_questions", 0),
                        "college_relevance": user.get("college_relevance", "unknown"),
                        "source_user": user.get("source_user") or "",
                        "discovered_via": user.get("discovered_via", "seed"),
                        "stats_status": user.get("stats_status", "pending"),
                        "last_updated": user.get("last_updated") or datetime.now(timezone.utc).isoformat(),
                    }
                    writer.writerow(row)

            # Atomic replace
            os.replace(self.tmp_path, self.csv_path)
            return True
        except Exception as e:
            logger.error(f"[CSV] Failed to atomically save CSV: {e}")
            if self.tmp_path.is_file():
                try:
                    self.tmp_path.unlink()
                except Exception:
                    pass
            return False

    def upsert_user(self, user_dict: Dict[str, Any]) -> bool:
        """
        Upserts a single user into the CSV cache atomically.
        """
        users = self.load_users()
        u_key = user_dict["username"].lower()
        users[u_key] = user_dict
        return self.save_all(users)

csv_manager = CSVManager()
