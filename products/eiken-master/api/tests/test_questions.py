def _register_and_token(client, username="taro", pin="1234", grade="pre2"):
    res = client.post(
        "/auth/register", json={"username": username, "pin": pin, "grade": grade}
    )
    return res.json()["access_token"]


def test_get_questions_empty_without_seed(client):
    token = _register_and_token(client)
    res = client.get(
        "/questions/?skill=reading", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    assert res.json() == []


def test_seed_endpoint_returns_count(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/questions/seed", headers=headers)
    assert res.status_code == 201
    assert res.json()["seeded"] == 20


def test_get_questions_after_seed(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/questions/seed", headers=headers)
    res = client.get("/questions/?skill=reading&count=2", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) <= 2
    for q in data:
        assert q["grade"] == "pre2"
        assert q["skill"] == "reading"
