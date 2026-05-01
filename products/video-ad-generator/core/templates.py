"""テンプレート CRUD ロジック。"""

from __future__ import annotations

from database import Template, get_session
from core.safety import is_blocked


def create_template(
    *,
    name: str,
    category: str,
    image_prompt: str,
    video_prompt: str,
    default_provider: str,
    default_aspect: str,
    default_duration: int,
    default_camera_preset: str | None,
) -> Template:
    if is_blocked(image_prompt) or is_blocked(video_prompt):
        raise ValueError("プロンプトにブロックワード（block word）が含まれています")
    with get_session() as session:
        t = Template(
            name=name,
            category=category,
            image_prompt=image_prompt,
            video_prompt=video_prompt,
            default_provider=default_provider,
            default_aspect=default_aspect,
            default_duration=default_duration,
            default_camera_preset=default_camera_preset,
            is_archived=False,
        )
        session.add(t)
        session.commit()
        session.refresh(t)
        return t


def get_template(template_id: int) -> Template | None:
    with get_session() as session:
        return session.get(Template, template_id)


def list_templates(
    *, category: str | None = None, include_archived: bool = False
) -> list[Template]:
    with get_session() as session:
        q = session.query(Template)
        if not include_archived:
            q = q.filter(Template.is_archived == False)  # noqa: E712
        if category:
            q = q.filter(Template.category == category)
        return q.order_by(Template.created_at.desc()).all()


def update_template(template_id: int, **fields) -> Template | None:
    allowed = {
        "name",
        "category",
        "image_prompt",
        "video_prompt",
        "default_provider",
        "default_aspect",
        "default_duration",
        "default_camera_preset",
        "is_archived",
    }
    sanitized = {k: v for k, v in fields.items() if k in allowed and v is not None}

    if "image_prompt" in sanitized and is_blocked(sanitized["image_prompt"]):
        raise ValueError("image_prompt にブロックワードが含まれています")
    if "video_prompt" in sanitized and is_blocked(sanitized["video_prompt"]):
        raise ValueError("video_prompt にブロックワードが含まれています")

    with get_session() as session:
        t = session.get(Template, template_id)
        if not t:
            return None
        for k, v in sanitized.items():
            setattr(t, k, v)
        session.commit()
        session.refresh(t)
        return t


def archive_template(template_id: int) -> bool:
    with get_session() as session:
        t = session.get(Template, template_id)
        if not t:
            return False
        t.is_archived = True
        session.commit()
        return True
