def _register_and_token(client, username="taro", pin="1234", grade="pre2"):
    res = client.post(
        "/auth/register", json={"username": username, "pin": pin, "grade": grade}
    )
    return res.json()["access_token"]


def test_get_due_cards_empty(client):
    token = _register_and_token(client)
    res = client.get("/flashcards/due", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == []


def test_create_and_get_due(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/flashcards/", json={"front": "apple", "back": "りんご"}, headers=headers
    )
    res = client.get("/flashcards/due", headers=headers)
    assert len(res.json()) == 1
    assert res.json()[0]["front"] == "apple"


def test_review_updates_sm2(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    card_res = client.post(
        "/flashcards/", json={"front": "apple", "back": "りんご"}, headers=headers
    )
    card_id = card_res.json()["id"]
    res = client.post(
        f"/flashcards/{card_id}/review", json={"quality": 5}, headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["repetitions"] == 1
    assert data["interval_days"] == 1  # 初回なので1日


def test_review_quality_1_resets(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    card_res = client.post(
        "/flashcards/", json={"front": "apple", "back": "りんご"}, headers=headers
    )
    card_id = card_res.json()["id"]
    client.post(f"/flashcards/{card_id}/review", json={"quality": 5}, headers=headers)
    client.post(f"/flashcards/{card_id}/review", json={"quality": 5}, headers=headers)
    res = client.post(
        f"/flashcards/{card_id}/review", json={"quality": 1}, headers=headers
    )
    assert res.json()["repetitions"] == 0
    assert res.json()["interval_days"] == 1


def test_mine_words(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/flashcards/mine",
        json={
            "words": [
                {"front": "apple", "back": "りんご"},
                {"front": "book", "back": "本"},
            ]
        },
        headers=headers,
    )
    assert res.json()["created"] == 2
    due = client.get("/flashcards/due", headers=headers)
    assert len(due.json()) == 2


def test_mine_skips_duplicates(client):
    token = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/flashcards/mine",
        json={"words": [{"front": "apple", "back": "りんご"}]},
        headers=headers,
    )
    res = client.post(
        "/flashcards/mine",
        json={"words": [{"front": "apple", "back": "りんご"}]},
        headers=headers,
    )
    assert res.json()["created"] == 0
