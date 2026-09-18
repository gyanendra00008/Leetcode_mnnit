from pathlib import Path
from typing import List, Optional
from app.utils import normalize_username, extract_usernames_from_text

SEED_USERS = [
    "prabhat_05",
    "Prateek816",
    "Shrey_Gayakvad",
    "UditSaha",
    "RevanthReddyMNNIT",
    "adarneey_sajal",
    "gyanendra1729",
    "ralon_1",
    "adityapratapsinghnegi",
    "Kunal_K008",
    "Endr_",
    "Aryanifie",
]

def load_seed_users(csv_path: Optional[str] = None) -> List[str]:
    """
    Loads, normalizes, and deduplicates seed users from SEED_USERS and any existing users.csv.
    Supports both raw usernames and full profile URLs.
    """
    seen = set()
    cleaned_seeds = []

    # 1. Process SEED_USERS list
    for user in SEED_USERS:
        norm = normalize_username(user)
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            cleaned_seeds.append(norm)

    # 2. Check for users.csv
    file_path = Path(csv_path) if csv_path else Path(__file__).resolve().parent / "users.csv"
    if file_path.is_file():
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            csv_users = extract_usernames_from_text(content)
            for u in csv_users:
                if u.lower() not in seen:
                    seen.add(u.lower())
                    cleaned_seeds.append(u)
        except Exception:
            pass

    return cleaned_seeds
