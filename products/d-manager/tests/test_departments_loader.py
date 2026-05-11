from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def fake_company(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "COMPANY_DIR", tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# company rules", encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()
    # フラット形式
    (skills / "flat.md").write_text("FLAT-SKILL-BODY", encoding="utf-8")
    # 新形式（SKILL.md + references/）
    d = skills / "fancy"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "FANCY-SKILL-BODY 詳細は references/long.md を参照", encoding="utf-8"
    )
    refs = d / "references"
    refs.mkdir()
    (refs / "long.md").write_text(
        "REFERENCE-DETAIL-SHOULD-NOT-BE-CONCATENATED", encoding="utf-8"
    )
    # .archive は無視されるべき
    arch = skills / ".archive"
    arch.mkdir()
    (arch / "old.md").write_text("ARCHIVED-SHOULD-NOT-APPEAR", encoding="utf-8")
    return tmp_path


def test_loader_includes_flat_and_skillmd_body_not_references(fake_company):
    import departments

    importlib.reload(departments)
    prompt = departments.load_department_prompt("operations")
    assert "FLAT-SKILL-BODY" in prompt
    assert "FANCY-SKILL-BODY" in prompt
    assert "REFERENCE-DETAIL-SHOULD-NOT-BE-CONCATENATED" not in prompt
    assert "ARCHIVED-SHOULD-NOT-APPEAR" not in prompt


def test_skills_concat_size(fake_company):
    import departments

    importlib.reload(departments)
    m = departments.skills_concat_size()
    assert m["count"] == 2
    # FLAT-SKILL-BODY + FANCY-SKILL-BODY ... の文字数（references は含めない）
    assert m["concat_chars"] == len("FLAT-SKILL-BODY") + len(
        "FANCY-SKILL-BODY 詳細は references/long.md を参照"
    )


def test_skillmd_takes_priority_over_flat(fake_company):
    # skills/dup.md と skills/dup/SKILL.md が両方ある → SKILL.md 側を使う
    skills = fake_company / "skills"
    (skills / "dup.md").write_text("DUP-FLAT", encoding="utf-8")
    d = skills / "dup"
    d.mkdir()
    (d / "SKILL.md").write_text("DUP-NEW", encoding="utf-8")
    import departments

    importlib.reload(departments)
    prompt = departments.load_department_prompt("operations")
    assert "DUP-NEW" in prompt
    assert "DUP-FLAT" not in prompt
