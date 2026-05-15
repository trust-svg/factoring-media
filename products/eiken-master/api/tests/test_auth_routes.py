# products/eiken-master/api/tests/test_auth_routes.py
def test_register_success(client):
    res = client.post(
        "/auth/register", json={"username": "taro", "pin": "1234", "grade": "pre2"}
    )
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["grade"] == "pre2"


def test_register_duplicate_username(client):
    client.post(
        "/auth/register", json={"username": "taro", "pin": "1234", "grade": "pre2"}
    )
    res = client.post(
        "/auth/register", json={"username": "taro", "pin": "5678", "grade": "2"}
    )
    assert res.status_code == 400


def test_login_success(client):
    client.post(
        "/auth/register", json={"username": "taro", "pin": "1234", "grade": "pre2"}
    )
    res = client.post("/auth/login", json={"username": "taro", "pin": "1234"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_pin(client):
    client.post(
        "/auth/register", json={"username": "taro", "pin": "1234", "grade": "pre2"}
    )
    res = client.post("/auth/login", json={"username": "taro", "pin": "0000"})
    assert res.status_code == 401


def test_me_requires_auth(client):
    res = client.get("/auth/me")
    assert (
        res.status_code == 401
    )  # FastAPI 0.136+ HTTPBearer returns 401 (was 403 in older versions)


def test_me_with_token(client):
    reg = client.post(
        "/auth/register", json={"username": "taro", "pin": "1234", "grade": "pre2"}
    )
    token = reg.json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["username"] == "taro"
