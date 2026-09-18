from fastapi.testclient import TestClient
from main import app
from app.database import init_db

init_db()
client = TestClient(app)

def test_api():
    print("=== Testing FastAPI Endpoints ===")

    # 1. Root dashboard HTML
    r_root = client.get("/")
    assert r_root.status_code == 200, f"Dashboard failed: {r_root.status_code}"
    assert "LeetCode Profile Collector" in r_root.text
    print("[PASS] GET / (Dashboard HTML rendered)")

    # 2. Collector status
    r_status = client.get("/collector/status")
    assert r_status.status_code == 200
    status = r_status.json()
    assert status["discovered"] >= 20
    assert status["successful"] >= 20
    assert status["mnnit_count"] >= 3
    print(f"[PASS] GET /collector/status: {status}")

    # 3. User listing (Rating DESC)
    r_users = client.get("/users?page=1&limit=10&sort=rating&order=desc")
    assert r_users.status_code == 200
    data = r_users.json()
    assert data["total"] >= 20
    assert len(data["users"]) == 10
    top_user = data["users"][0]
    print(f"[PASS] GET /users (Top Rated): {top_user['username']} | Rating={top_user['rating']}")

    # 4. MNNIT Filter
    r_mnnit = client.get("/users?mnnit=true")
    assert r_mnnit.status_code == 200
    mnnit_data = r_mnnit.json()
    assert mnnit_data["total"] >= 3
    for u in mnnit_data["users"]:
        assert u["college_relevance"] == "MNNIT"
    print(f"[PASS] GET /users?mnnit=true returned {mnnit_data['total']} MNNIT students:")
    for u in mnnit_data["users"]:
        print(f"       - {u['username']} (Rating: {u['rating']}, Solved: {u['total_questions']})")

    # 5. Search
    r_search = client.get("/users?search=Prateek")
    assert r_search.status_code == 200
    search_data = r_search.json()
    assert len(search_data["users"]) >= 1
    assert any("prateek" in u["username"].lower() for u in search_data["users"])
    print(f"[PASS] GET /users?search=Prateek found: {[u['username'] for u in search_data['users']]}")

    # 6. User detail by username
    r_user = client.get("/users/prabhat_05")
    assert r_user.status_code == 200
    user_obj = r_user.json()
    assert user_obj["username"] == "prabhat_05"
    assert user_obj["college_relevance"] == "MNNIT"
    assert user_obj["rating"] is not None
    print(f"[PASS] GET /users/prabhat_05: Rating={user_obj['rating']} | Solved={user_obj['total_questions']}")

    # 7. Sorting by total_questions DESC
    r_solved = client.get("/users?sort=total_questions&order=desc")
    assert r_solved.status_code == 200
    solved_data = r_solved.json()
    most_solved = solved_data["users"][0]
    print(f"[PASS] GET /users?sort=total_questions&order=desc: Top solved is {most_solved['username']} with {most_solved['total_questions']} problems")

    print("\nALL FASTAPI ENDPOINTS VERIFIED AND PASSING!")

if __name__ == "__main__":
    test_api()
