"""Small request helpers shared by the template, consent, audit and error tests."""

from __future__ import annotations

from typing import Any

from httpx import Response

from tests.fixtures.doubles import VALID_VIDEO, pdf_bytes, word
from tests.integration.api.conftest import Env
from vidgen.domain.values import Word

ORIGINAL_NAME = "Krishan"


def upload_template(
    env: Env,
    *,
    content: bytes = VALID_VIDEO,
    filename: str = "template.mp4",
    original_name: str | None = ORIGINAL_NAME,
) -> Response:
    """POST /templates (multipart) with CSRF; ``original_name=None`` omits the field."""
    data = {} if original_name is None else {"original_name": original_name}
    return env.client.post(
        "/templates",
        files={"video": (filename, content, "video/mp4")},
        data=data,
        headers=env.csrf,
    )


def new_template(env: Env, **kwargs: Any) -> str:
    """Upload a valid template and return its id."""
    response = upload_template(env, **kwargs)
    assert response.status_code == 201, response.text
    template_id: str = response.json()["id"]
    return template_id


def upload_consent(
    env: Env,
    template_id: str,
    *,
    content: bytes | None = None,
    filename: str = "consent.pdf",
    confirmed: str | None = "true",
) -> Response:
    """POST /templates/{id}/consent; ``content=None`` sends only the tick."""
    files = None if content is None else {"file": (filename, content, "application/octet-stream")}
    data = {} if confirmed is None else {"confirmed": confirmed}
    return env.client.post(
        f"/templates/{template_id}/consent", files=files, data=data, headers=env.csrf
    )


def give_consent(env: Env, template_id: str) -> None:
    """Attach a valid PDF consent with the tick."""
    assert upload_consent(env, template_id, content=pdf_bytes()).status_code == 200


def analyse(env: Env, template_id: str, *, force: bool = False) -> Response:
    """POST /templates/{id}/analyse."""
    suffix = "?force=true" if force else ""
    return env.client.post(f"/templates/{template_id}/analyse{suffix}", headers=env.csrf)


def set_slot(env: Env, template_id: str, start_s: float, end_s: float) -> Response:
    """PUT /templates/{id}/slot (manual slot)."""
    return env.client.put(
        f"/templates/{template_id}/slot",
        json={"start_s": start_s, "end_s": end_s},
        headers=env.csrf,
    )


def confirm_slot(env: Env, template_id: str) -> Response:
    """POST /templates/{id}/slot/confirm."""
    return env.client.post(f"/templates/{template_id}/slot/confirm", headers=env.csrf)


def get_template(env: Env, template_id: str) -> dict[str, Any]:
    """GET /templates/{id} as JSON."""
    response = env.client.get(f"/templates/{template_id}")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def transcript(*words: Word) -> list[Word]:
    """Convenience for setting the fake STT transcript."""
    return list(words)


def krishan_at(start: float, confidence: float = 0.95) -> Word:
    """The spoken voter name at ``start`` seconds."""
    return word(ORIGINAL_NAME, start, confidence)


def audit_actions(env: Env) -> list[str]:
    """Actions in the audit log, oldest first."""
    response = env.client.get("/audit")
    assert response.status_code == 200
    return [entry["action"] for entry in response.json()["entries"]]
