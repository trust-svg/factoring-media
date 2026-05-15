def _register_and_token(client, username="taro", pin="1234", grade="pre2"):
    res = client.post(
        "/auth/register", json={"username": username, "pin": pin, "grade": grade}
    )
    return res.json()["access_token"]


def test_start_session(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/sessions/start", json={"skill": "reading"}, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["skill"] == "reading"
    assert data["questions_attempted"] == 0
    assert "id" in data


def test_end_session_calculates_accuracy(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    start = client.post("/sessions/start", json={"skill": "reading"}, headers=headers)
    session_id = start.json()["id"]
    res = client.post(
        f"/sessions/{session_id}/end",
        json={
            "duration_seconds": 600,
            "questions_attempted": 10,
            "correct_count": 7,
            "pomodoro_completed": False,
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert abs(data["accuracy_rate"] - 0.7) < 0.001
    assert data["duration_seconds"] == 600


def test_end_session_zero_questions(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    start = client.post("/sessions/start", json={"skill": "listening"}, headers=headers)
    session_id = start.json()["id"]
    res = client.post(
        f"/sessions/{session_id}/end",
        json={
            "duration_seconds": 0,
            "questions_attempted": 0,
            "correct_count": 0,
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["accuracy_rate"] is None


def test_record_attempt(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    start = client.post("/sessions/start", json={"skill": "reading"}, headers=headers)
    session_id = start.json()["id"]
    res = client.post(
        f"/sessions/{session_id}/attempt",
        json={
            "question_id": "fake-question-id",
            "skill": "reading",
            "user_answer": "B",
            "is_correct": True,
            "time_spent_seconds": 30,
        },
        headers=headers,
    )
    assert res.status_code == 201
    assert "id" in res.json()
