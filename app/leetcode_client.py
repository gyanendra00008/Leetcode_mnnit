import asyncio
import logging
import random
from typing import Optional, Dict, Any, List
import httpx
from config import settings
from app.utils import check_mnnit_affiliation

logger = logging.getLogger("leetcode_collector")

USER_STATS_QUERY = """
query getUserStats($username: String!) {
  matchedUser(username: $username) {
    username
    profile {
      realName
      aboutMe
      school
      company
    }
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
  }
  userContestRanking(username: $username) {
    rating
    attendedContestsCount
  }
}
"""

SOCIAL_CONNECTIONS_QUERY = """
query getSocialConnections($userSlug: String!) {
  followers(userSlug: $userSlug) {
    allNum
    users {
      userSlug
    }
  }
  following(userSlug: $userSlug) {
    allNum
    users {
      userSlug
    }
  }
}
"""

class LeetCodeClient:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": settings.USER_AGENT,
            "Referer": "https://leetcode.com",
            "Accept": "application/json",
        }

    async def _post_graphql(self, query: str, variables: dict) -> Dict[str, Any]:
        """
        Executes a GraphQL POST request with rate limiting, retries, and exponential backoff.
        """
        async with self.semaphore:
            # Respect configured request delay
            if settings.REQUEST_DELAY > 0:
                await asyncio.sleep(settings.REQUEST_DELAY)

            url = settings.LEETCODE_URL
            payload = {"query": query, "variables": variables}

            for attempt in range(1, settings.MAX_RETRIES + 1):
                try:
                    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
                        response = await client.post(url, json=payload, headers=self.headers)

                    # Handle Rate Limiting (429)
                    if response.status_code == 429:
                        backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
                        target_user = variables.get("username") or variables.get("userSlug") or "unknown"
                        logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus=429\nmessage=Rate limited (Too Many Requests)\nretry={attempt}/{settings.MAX_RETRIES}")
                        await asyncio.sleep(backoff)
                        continue

                    # Handle 404
                    if response.status_code == 404:
                        target_user = variables.get("username") or variables.get("userSlug") or "unknown"
                        logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus=404\nmessage=Profile not found (HTTP 404)\nretry={attempt}/{settings.MAX_RETRIES}")
                        return {"_error": "HTTP 404 Not Found", "_status": 404}

                    # Handle Server Errors
                    if response.status_code >= 500:
                        backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                        target_user = variables.get("username") or variables.get("userSlug") or "unknown"
                        logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus={response.status_code}\nmessage=Server error\nretry={attempt}/{settings.MAX_RETRIES}")
                        await asyncio.sleep(backoff)
                        continue

                    if response.status_code != 200:
                        target_user = variables.get("username") or variables.get("userSlug") or "unknown"
                        logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus={response.status_code}\nmessage=Unexpected status code\nretry={attempt}/{settings.MAX_RETRIES}")
                        return {"_error": f"HTTP {response.status_code}", "_status": response.status_code}

                    data = response.json()

                    # Handle GraphQL level errors
                    if "errors" in data:
                        errors = data["errors"]
                        err_msgs = [e.get("message", "") for e in errors if isinstance(e, dict)]
                        err_text = "; ".join(err_msgs) if err_msgs else str(errors)
                        target_user = variables.get("username") or variables.get("userSlug") or "unknown"

                        if any("does not exist" in m.lower() or "user not found" in m.lower() for m in err_msgs):
                            logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus=404\nmessage=User does not exist in GraphQL\nretry=0/0")
                            return {"_error": "User does not exist", "_status": 404}

                        # Check if query was rejected or unavailable
                        if "Query unavailable" in err_text:
                            logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus=403\nmessage=Query unavailable in GraphQL\nretry=0/0")
                            return {"_error": "Query unavailable", "_status": 403}

                        # If partial data is present, return data with warnings
                        if data.get("data"):
                            data["data"]["_graphql_error"] = err_text
                            return data.get("data", {})

                        logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus=400\nmessage=GraphQL error: {err_text}\nretry=0/0")
                        return {"_error": err_text, "_status": 400}

                    return data.get("data", {})

                except httpx.TimeoutException:
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                    target_user = variables.get("username") or variables.get("userSlug") or "unknown"
                    logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus=TIMEOUT\nmessage=Request timed out\nretry={attempt}/{settings.MAX_RETRIES}")
                    if attempt == settings.MAX_RETRIES:
                        return {"_error": "Request timed out after max retries", "_status": 504}
                    await asyncio.sleep(backoff)

                except httpx.RequestError as e:
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                    target_user = variables.get("username") or variables.get("userSlug") or "unknown"
                    logger.error(f"[ERROR][STATS]\nusername={target_user}\nstatus=NETWORK_ERR\nmessage={str(e)}\nretry={attempt}/{settings.MAX_RETRIES}")
                    if attempt == settings.MAX_RETRIES:
                        return {"_error": f"Network error: {str(e)}", "_status": 502}
                    await asyncio.sleep(backoff)

            return {"_error": "Max retries exceeded", "_status": 500}

    async def fetch_user_stats(self, username: str) -> Dict[str, Any]:
        """
        Fetches user profile stats: solved questions breakdown, contest rating, and college affiliation.
        """
        data = await self._post_graphql(USER_STATS_QUERY, {"username": username})

        if "_error" in data:
            return {
                "success": False,
                "error": data["_error"],
                "status_code": data.get("_status", 500),
            }

        matched_user = data.get("matchedUser")
        if not matched_user:
            logger.error(f"[ERROR][STATS]\nusername={username}\nstatus=404\nmessage=User not found or profile is private\nretry=0/0")
            return {
                "success": False,
                "error": "User not found or profile is private",
                "status_code": 404,
            }

        # Parse profile details for MNNIT identification & actual name
        profile = matched_user.get("profile") or {}
        real_name = profile.get("realName")
        actual_name = real_name.strip() if real_name and isinstance(real_name, str) and real_name.strip() else "N/A"
        school = profile.get("school")
        company = profile.get("company")
        about_me = profile.get("aboutMe")
        college_relevance = check_mnnit_affiliation(school=school, company=company, about_me=about_me)

        # Parse contest rating
        contest = data.get("userContestRanking")
        rating = None
        if contest and contest.get("rating") is not None:
            rating = float(contest["rating"])

        # Parse solved counts
        total_questions = 0
        easy_questions = 0
        medium_questions = 0
        hard_questions = 0

        submit_stats = matched_user.get("submitStatsGlobal") or {}
        ac_submissions = submit_stats.get("acSubmissionNum") or []

        for item in ac_submissions:
            diff = str(item.get("difficulty", "")).lower()
            count = int(item.get("count", 0))
            if diff == "all":
                total_questions = count
            elif diff == "easy":
                easy_questions = count
            elif diff == "medium":
                medium_questions = count
            elif diff == "hard":
                hard_questions = count

        # If "All" was missing, sum individual difficulties
        if total_questions == 0 and (easy_questions + medium_questions + hard_questions) > 0:
            total_questions = easy_questions + medium_questions + hard_questions

        rating_str = f"{round(rating)}" if rating is not None else "N/A"
        logger.info(f"[STATS] {username}")
        logger.info(f"[STATS] Name: {actual_name} | Rating: {rating_str} | Solved: {total_questions} | College: {college_relevance}")

        return {
            "success": True,
            "username": username,
            "actual_name": actual_name,
            "rating": rating,
            "total_questions": total_questions,
            "easy_questions": easy_questions,
            "medium_questions": medium_questions,
            "hard_questions": hard_questions,
            "college_relevance": college_relevance,
            "school": school,
            "about_me": about_me,
            "company": company,
        }

    async def fetch_user_connections(self, user_slug: str) -> Dict[str, Any]:
        """
        Fetches publicly accessible followers and following for a user.
        """
        logger.info(f"[DISCOVERY] Crawling connections for: {user_slug}")
        data = await self._post_graphql(SOCIAL_CONNECTIONS_QUERY, {"userSlug": user_slug})

        followers_list = []
        following_list = []

        if "_error" in data:
            logger.warning(f"[DISCOVERY] Connections failed for: {user_slug} | {data['_error']}")
            return {
                "success": False,
                "error": data["_error"],
                "followers": [],
                "following": []
            }

        followers_node = data.get("followers") or {}
        for u in followers_node.get("users", []) or []:
            slug = u.get("userSlug")
            if slug:
                followers_list.append(slug)

        following_node = data.get("following") or {}
        for u in following_node.get("users", []) or []:
            slug = u.get("userSlug")
            if slug:
                following_list.append(slug)

        logger.info(f"[DISCOVERY] Found {len(followers_list)} followers, {len(following_list)} following for {user_slug}")

        return {
            "success": True,
            "followers": followers_list,
            "following": following_list
        }

leetcode_client = LeetCodeClient()
