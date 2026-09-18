import re
from typing import Optional, List

MNNIT_KEYWORDS = [
    "mnnit",
    "motilal nehru national institute of technology",
    "mnnit allahabad",
    "mnnit prayagraj",
]

def normalize_username(raw: str) -> Optional[str]:
    """
    Extracts a clean LeetCode username from a raw string.
    Supports:
      - 'username'
      - 'https://leetcode.com/u/username/'
      - 'https://leetcode.com/username/'
      - Multiple concatenated URLs (e.g. 'https://leetcode.com/u/Aryanifie/https://leetcode.com/u/Aryanifie/')
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.strip()
    if not raw:
        return None

    # Find matches of usernames in URL patterns
    # LeetCode usernames typically contain alphanumeric characters, underscores, and hyphens.
    url_pattern = re.compile(r"leetcode\.com/(?:u/)?([a-zA-Z0-9_-]+)", re.IGNORECASE)
    matches = url_pattern.findall(raw)
    if matches:
        # Return the first matched username
        candidate = matches[0].strip("/ ")
        if candidate:
            return candidate

    # If it's a plain string, clean any leading/trailing slashes or punctuation
    cleaned = raw.strip("/ \t\n\r")
    # Discard non-username URL parts if any
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = re.sub(r"^www\.", "", cleaned)
    parts = [p for p in cleaned.split("/") if p]
    if parts:
        candidate = parts[-1]
        # Validate candidate character set
        if re.match(r"^[a-zA-Z0-9_-]+$", candidate):
            return candidate

    return None


def extract_usernames_from_text(text: str) -> List[str]:
    """
    Extracts and deduplicates all valid usernames found across lines or concatenated strings.
    """
    if not text:
        return []

    lines = text.strip().splitlines()
    seen = set()
    result = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Look for URL matches first
        url_matches = re.findall(r"leetcode\.com/(?:u/)?([a-zA-Z0-9_-]+)", line, re.IGNORECASE)
        if url_matches:
            for u in url_matches:
                u_clean = u.strip("/ ")
                if u_clean and u_clean.lower() not in seen:
                    seen.add(u_clean.lower())
                    result.append(u_clean)
            continue

        # Plain username
        user = normalize_username(line)
        if user and user.lower() not in seen:
            seen.add(user.lower())
            result.append(user)

    return result


def check_mnnit_affiliation(
    school: Optional[str] = None,
    company: Optional[str] = None,
    about_me: Optional[str] = None,
) -> str:
    """
    Determines if a profile explicitly identifies MNNIT affiliation.
    Strictly follows rule:
    If publicly available profile information explicitly identifies:
      - MNNIT
      - Motilal Nehru National Institute of Technology
      - MNNIT Allahabad
      - MNNIT Prayagraj
    Then mark college_relevance = 'MNNIT'.
    Otherwise college_relevance = 'unknown'.
    Never infer college affiliation from username alone, mutual followers, etc.
    """
    combined_texts = []
    if school:
        combined_texts.append(school)
    if company:
        combined_texts.append(company)
    if about_me:
        combined_texts.append(about_me)

    full_text = " ".join(combined_texts).lower()

    for keyword in MNNIT_KEYWORDS:
        # Check whole word / substring boundary match
        if re.search(r"\b" + re.escape(keyword) + r"\b", full_text, re.IGNORECASE):
            return "MNNIT"

    return "unknown"
