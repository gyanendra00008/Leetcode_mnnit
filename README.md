# LeetCode Profile Collector & MNNIT Graph Intelligence

A high-performance, standalone Python/FastAPI application designed to discover publicly accessible LeetCode profiles through social graph traversal (followers/following), collect verified profile statistics (ratings, problem difficulties, submission counts), identify explicit college affiliations (e.g. MNNIT Allahabad), and present the data in a responsive web dashboard.

---

## Architecture Overview

```
                   +-----------------------+
                   |  Initial Seed Users   |
                   |  (MNNIT Seed Cohort)  |
                   +-----------+-----------+
                               |
                               v
               +---------------+---------------+
               |    Queue-based BFS Crawler    |
               |  (Resumable SQLite State DB)  |
               +-------+---------------+-------+
                       |               |
       Followers /     |               | Profile Stats
       Following Query |               | & Contest Info
                       v               v
               +---------------+---------------+
               |    LeetCode GraphQL Client    |
               | (Rate-Limited, Backoff Retry) |
               +---------------+---------------+
                               |
                               v
               +---------------+---------------+
               |  SQLite Database Initialization|
               |       (leetcode_users)        |
               +---------------+---------------+
                               |
                               v
               +---------------+---------------+
               |      FastAPI REST Router      |
               |    (/users, /collector/*)     |
               +---------------+---------------+
                               |
                               v
               +---------------+---------------+
               |   Modern Interactive Web UI   |
               | (Tailwind CSS, Search/Filter) |
               +-------------------------------+
```

### Directory Structure

```text
Aukaat/
├── main.py                 # FastAPI application, lifespan startup, UI mount
├── config.py               # Pydantic Settings & environment variables
├── seed_users.py           # Seed normalization, deduplication & URL cleaning
├── requirements.txt        # Production dependencies
├── .env                    # Active environment configuration (TARGET_USERS=1000)
├── .env.example            # Environment configuration template
│
├── app/
│   ├── __init__.py
│   ├── database.py         # SQLAlchemy engine, session management & SQLite init
│   ├── models.py           # LeetCodeUser model schema & constraints
│   ├── schemas.py          # Pydantic request/response validation schemas
│   ├── routes.py           # API endpoints (/collector/*, /users)
│   ├── leetcode_client.py  # Async GraphQL client with retry/backoff & concurrency
│   ├── crawler.py          # Resumable BFS graph discovery & stats collection engine
│   └── utils.py            # Username normalization & strict MNNIT pattern matching
│
├── templates/
│   └── users.html          # Responsive Tailwind CSS dashboard with live polling
│
├── test_collector.py       # Unit tests (normalization, MNNIT matching, DB, client)
├── test_e2e_crawl.py       # End-to-end integration test
├── test_api_endpoints.py   # FastAPI endpoint test suite
└── README.md               # Complete documentation
```

---

## Features

- **Automated Social Graph Discovery**: Discovers peer profiles via LeetCode's public GraphQL `followers(userSlug: $userSlug)` and `following(userSlug: $userSlug)` queries.
- **Strict MNNIT Identification**: Adheres strictly to verified evidence. Only labels users who explicitly list `MNNIT`, `Motilal Nehru National Institute of Technology`, `MNNIT Allahabad`, or `MNNIT Prayagraj` in their public profile fields (`school`, `company`, or `aboutMe`).
- **Resilient & Resumable**: All states (`pending`, `processing`, `completed`, `failed`) are committed immediately to SQLite. If the process is halted or restarted, execution resumes seamlessly from where it left off without duplicate work.
- **Polite Rate Limiting**: Built-in exponential backoff, jitter, configurable delay (`REQUEST_DELAY=1.0`), request timeouts, and maximum concurrency control (`MAX_CONCURRENCY=3`).
- **Rich Dashboard UI**: Modern dark-mode interface with live metrics (Target, Discovered, Processed, Successful, Failed, Pending, MNNIT count), username search, sorting (Rating, Solved, Difficulty), MNNIT-only filter, and pagination.

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.13)
- Windows PowerShell or command prompt

### 2. Create and Activate Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

---

## Environment Variables (`.env`)

Configuration settings are loaded automatically via `.env` (or system environment variables):

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TARGET_USERS` | `1000` | Target number of unique users to discover |
| `DATABASE_URL` | `sqlite:///./leetcode_data.db` | SQLite database file location |
| `REQUEST_DELAY` | `1.0` | Delay in seconds between requests |
| `MAX_RETRIES` | `3` | Maximum retry attempts for transient errors / 429 |
| `MAX_CONCURRENCY` | `3` | Asyncio semaphore limit for concurrent requests |
| `REQUEST_TIMEOUT` | `15.0` | HTTP request timeout in seconds |
| `LEETCODE_URL` | `https://leetcode.com/graphql/` | LeetCode GraphQL endpoint |
| `HOST` | `127.0.0.1` | Host for FastAPI Uvicorn server |
| `PORT` | `8000` | Port for FastAPI Uvicorn server |

---

## Running the Application

Start the FastAPI server with Uvicorn:

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Once started:
- **Interactive Dashboard**: Open your browser at [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Swagger API Docs**: Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Operating the Collector

### Starting the Crawler
You can start discovery through either:
1. **Web UI**: Click the **Start Discovery** button in the header.
2. **API**: Send a `POST` request to `/collector/start`:
   ```bash
   curl -X POST http://127.0.0.1:8000/collector/start
   ```

### Stopping the Crawler
1. **Web UI**: Click the **Stop** button in the header.
2. **API**:
   ```bash
   curl -X POST http://127.0.0.1:8000/collector/stop
   ```

### Checking Progress
Progress is automatically polled and displayed on the web dashboard every 2.5 seconds.
Or query via API:
```bash
curl http://127.0.0.1:8000/collector/status
```
Example JSON response:
```json
{
  "is_running": true,
  "current_action": "crawling",
  "target": 1000,
  "discovered": 742,
  "processed": 521,
  "successful": 507,
  "failed": 14,
  "pending": 221,
  "mnnit_count": 48
}
```

### Refreshing Existing User Statistics
To update ratings, submission counts, and profiles for users already stored in the database without rediscovering new graph connections:
1. **Web UI**: Click **Update All Stats** or the **Update** button on any individual user row.
2. **API**:
   ```bash
   # Update all users (optionally ?stale_days=7)
   curl -X POST http://127.0.0.1:8000/collector/update-all

   # Update single user
   curl -X POST http://127.0.0.1:8000/collector/update/Prateek816
   ```
3. **CLI**:
   ```bash
   # Update all users
   python collector.py update

   # Update single user
   python collector.py update-user Prateek816

   # Check live status & metrics
   python collector.py status

   # Run discovery via CLI
   python collector.py discover --target 1000
   ```

---

## API Reference

### `GET /users`
Query and filter collected users:
- `page` (int, default: 1): Page number
- `limit` (int, default: 50): Results per page (max: 100)
- `sort` (str, default: "rating"): `rating`, `total_questions`, `easy_questions`, `medium_questions`, `hard_questions`, `username`, `name`
- `order` (str, default: "desc"): `asc` or `desc`
- `search` (str): Search username or actual name by substring
- `mnnit` (bool, default: false): Filter only users with explicit MNNIT evidence

Example:
```bash
curl "http://127.0.0.1:8000/users?page=1&limit=25&sort=rating&order=desc&mnnit=true"
```

### `GET /users/{username}`
Retrieve details for a specific user:
```bash
curl http://127.0.0.1:8000/users/Prateek816
```

### `POST /collector/update-all`
Trigger manual update of all stored users or users stale after N days (`?stale_days=7`).

### `POST /collector/update/{username}`
Trigger manual update for a specific username and persist changes immediately to CSV cache and SQLite.

---

## Verifying and Running Tests

All unit tests and integration suites:

```powershell
# Run Comprehensive Acceptance Test Suite (Tests A to G)
python -m unittest test_suite_a_to_g.py

# Run Feature Upgrade Tests (Atomic CSV, Actual Name parsing, Rating handling)
python -m unittest test_upgraded_features.py

# Run unit tests (Normalization, Affiliation, DB init, Client)
python -m unittest test_collector.py

# Run FastAPI API endpoint tests
python test_api_endpoints.py
```

---

## Limitations of Public LeetCode Data

1. **Private Profiles**: Some users configure their profile settings to private, which causes LeetCode's GraphQL `matchedUser` query to return `null`. The crawler gracefully catches this and records `stats_status = 'failed'` with `error_message = 'User not found or profile is private'`.
2. **Connection Limits**: The public GraphQL endpoint returns the most recent followers/following nodes. When traversing deep graphs, the crawler naturally branches out into active users.
3. **MNNIT Affiliation Coverage**: Many college students do not fill out their school or company name on LeetCode. Under strict guidelines, only users with explicit textual evidence (`MNNIT`, `Motilal Nehru National Institute of Technology`, `MNNIT Allahabad`, `MNNIT Prayagraj`) are tagged as `"MNNIT"`; all others remain `"unknown"` to prevent false assumptions.
4. **Cloudflare & Rate Limits**: Aggressive scraping without delays triggers HTTP 429 rate limits or Cloudflare blocks. The configured 1.0-second delay and exponential backoff retry system ensure stable, continuous data collection.
