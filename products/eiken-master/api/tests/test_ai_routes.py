import base64
import json
from unittest.mock import MagicMock, patch

from app.schemas.ai import (
    CriterionScore,
    WritingScoreResponse,
    AudioResponse,
    SpeakingScoreResponse,
)


def _register(client, username="ai_user", pin="5678", grade="pre2"):
    res = client.post(
        "/auth/register", json={"username": username, "pin": pin, "grade": grade}
    )
    return res.json()["access_token"]


def _fake_writing_score(passing=True) -> WritingScoreResponse:
    return WritingScoreResponse(
        score=7.0 if passing else 4.0,
        max_score=10.0,
        feedback="テストフィードバック",
        criteria={
            "content": CriterionScore(score=3, max=4, comment="ok"),
            "grammar": CriterionScore(score=2, max=3, comment="ok"),
            "vocabulary": CriterionScore(score=2, max=3, comment="ok"),
        },
        is_passing=passing,
    )


def _start_session(client, headers, skill="writing"):
    return client.post(
        "/sessions/start", json={"skill": skill}, headers=headers
    ).json()["id"]


def test_score_writing_returns_feedback(client):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    session_id = _start_session(client, headers)

    with patch(
        "app.routers.ai.ai_service.score_writing",
        return_value=_fake_writing_score(True),
    ):
        res = client.post(
            "/ai/score-writing",
            json={
                "session_id": session_id,
                "question_id": "fake-q-id",
                "answer_text": "I think pets are good for people.",
            },
            headers=headers,
        )
    assert res.status_code == 200
    data = res.json()
    assert data["score"] == 7.0
    assert data["is_passing"] is True
    assert "content" in data["criteria"]


def test_score_writing_rejects_empty_answer(client):
    token = _register(client, username="ai2")
    headers = {"Authorization": f"Bearer {token}"}
    session_id = _start_session(client, headers)
    res = client.post(
        "/ai/score-writing",
        json={"session_id": session_id, "question_id": "q", "answer_text": ""},
        headers=headers,
    )
    assert res.status_code == 422


def test_generate_audio_returns_base64(client):
    token = _register(client, username="ai3")
    headers = {"Authorization": f"Bearer {token}"}
    fake_resp = AudioResponse(audio_base64=base64.b64encode(b"fake-mp3").decode())

    with patch("app.routers.ai.ai_service.generate_audio", return_value=fake_resp):
        res = client.post(
            "/ai/generate-audio", json={"text": "Hello world"}, headers=headers
        )
    assert res.status_code == 200
    assert res.json()["audio_base64"] == base64.b64encode(b"fake-mp3").decode()


def test_score_speaking_returns_transcript(client):
    token = _register(client, username="ai4")
    headers = {"Authorization": f"Bearer {token}"}
    session_id = _start_session(client, headers, skill="speaking")
    fake_resp = SpeakingScoreResponse(
        score=6.5,
        max_score=10.0,
        feedback="まあまあです",
        criteria={
            "content": CriterionScore(score=3, max=4, comment="ok"),
            "fluency": CriterionScore(score=2, max=3, comment="ok"),
            "grammar": CriterionScore(score=1, max=3, comment="ok"),
        },
        is_passing=True,
        transcript="I think smartphones are useful.",
    )

    with patch("app.routers.ai.ai_service.score_speaking", return_value=fake_resp):
        res = client.post(
            "/ai/score-speaking",
            data={
                "session_id": session_id,
                "question_id": "fake-q",
                "topic": "smartphones",
                "speaking_points": "learning",
            },
            files={"audio": ("rec.webm", b"fake-audio", "audio/webm")},
            headers=headers,
        )
    assert res.status_code == 200
    data = res.json()
    assert data["transcript"] == "I think smartphones are useful."
    assert data["is_passing"] is True
