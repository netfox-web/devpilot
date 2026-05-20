import os
import uuid

import requests


class DevPilotClient:
    def __init__(self, base_url=None, source_system=None, api_key=None, timeout=10):
        self.base_url = (base_url or os.getenv("DEVPILOT_API_BASE_URL", "")).rstrip("/")
        self.source_system = (source_system or os.getenv("DEVPILOT_SOURCE_SYSTEM", "")).strip()
        self.api_key = (api_key or os.getenv("DEVPILOT_API_KEY", "")).strip()
        self.timeout = timeout
        if not self.base_url:
            raise ValueError("DEVPILOT_API_BASE_URL is required")
        if not self.source_system:
            raise ValueError("DEVPILOT_SOURCE_SYSTEM is required")
        if not self.api_key:
            raise ValueError("DEVPILOT_API_KEY is required")

    def _headers(self, idempotency_key=None, json_body=False):
        headers = {
            "X-DevPilot-Source-System": self.source_system,
            "X-DevPilot-Api-Key": self.api_key,
            "X-DevPilot-Request-Id": str(uuid.uuid4()),
        }
        if idempotency_key:
            headers["X-DevPilot-Idempotency-Key"] = idempotency_key
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(self, method, path, **kwargs):
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            error = payload.get("error", "unknown_error")
            raise RuntimeError(f"DevPilot request failed: {response.status_code} {error}")
        return payload

    def test_connection(self):
        return self._request("GET", "/api/external/projects", headers=self._headers())

    def register_project(self, project):
        external_project_id = str(project.get("external_project_id") or "").strip()
        if not external_project_id:
            raise ValueError("external_project_id is required")
        idempotency_key = f"register:{self.source_system}:{external_project_id}"
        return self._request(
            "POST",
            "/api/external/projects/register",
            headers=self._headers(idempotency_key=idempotency_key, json_body=True),
            json=project,
        )

    def send_project_event(self, external_project_id, event):
        external_project_id = str(external_project_id or "").strip()
        event_type = str(event.get("event_type") or "").strip()
        if not external_project_id:
            raise ValueError("external_project_id is required")
        if not event_type:
            raise ValueError("event_type is required")
        seed = event.get("idempotency_key") or event.get("commit_sha") or event.get("message") or str(uuid.uuid4())
        idempotency_key = f"event:{self.source_system}:{external_project_id}:{event_type}:{seed}"
        return self._request(
            "POST",
            f"/api/external/projects/{external_project_id}/events",
            headers=self._headers(idempotency_key=idempotency_key, json_body=True),
            json=event,
        )

    def create_handoff(self, task_id, handoff):
        task_id = str(task_id or "").strip()
        if not task_id:
            raise ValueError("task_id is required")
        seed = handoff.get("external_ref") or handoff.get("reason") or str(uuid.uuid4())
        idempotency_key = f"handoff:{self.source_system}:{task_id}:{seed}"
        return self._request(
            "POST",
            f"/api/external/tasks/{task_id}/handoffs",
            headers=self._headers(idempotency_key=idempotency_key, json_body=True),
            json=handoff,
        )

    def generate_ai_text(self, prompt, provider="openai", model="gpt-4.1-mini", capability="generate", external_ref=None, metadata=None):
        prompt = str(prompt or "")
        if not prompt.strip():
            raise ValueError("prompt is required")
        stable_ref = external_ref or str(uuid.uuid4())
        idempotency_key = f"ai-generate:{self.source_system}:{stable_ref}"
        return self._request(
            "POST",
            "/api/external/ai/generate",
            headers=self._headers(idempotency_key=idempotency_key, json_body=True),
            json={
                "provider": provider,
                "model": model,
                "capability": capability,
                "prompt": prompt,
                "external_ref": stable_ref,
                "metadata": metadata or {},
            },
        )


# Never log client.api_key or full request headers.
