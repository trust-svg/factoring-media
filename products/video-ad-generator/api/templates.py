"""テンプレート CRUD API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core import templates as tmpl

router = APIRouter(prefix="/api/templates")


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field("custom", max_length=50)
    image_prompt: str = Field(..., min_length=1, max_length=2000)
    video_prompt: str = Field(..., min_length=1, max_length=2000)
    default_provider: str = "seedance"
    default_aspect: str = "9:16"
    default_duration: int = 10
    default_camera_preset: str | None = None


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    image_prompt: str | None = None
    video_prompt: str | None = None
    default_provider: str | None = None
    default_aspect: str | None = None
    default_duration: int | None = None
    default_camera_preset: str | None = None


def _to_dict(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "category": t.category,
        "image_prompt": t.image_prompt,
        "video_prompt": t.video_prompt,
        "default_provider": t.default_provider,
        "default_aspect": t.default_aspect,
        "default_duration": t.default_duration,
        "default_camera_preset": t.default_camera_preset,
        "is_archived": t.is_archived,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template(req: TemplateCreateRequest):
    try:
        t = tmpl.create_template(**req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_dict(t)


@router.get("")
def list_templates(category: str | None = None, include_archived: bool = False):
    items = tmpl.list_templates(category=category, include_archived=include_archived)
    return [_to_dict(t) for t in items]


@router.get("/{template_id}")
def get_template(template_id: int):
    t = tmpl.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_dict(t)


@router.patch("/{template_id}")
def update_template(template_id: int, req: TemplateUpdateRequest):
    try:
        t = tmpl.update_template(template_id, **req.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_dict(t)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int):
    if not tmpl.archive_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return None
