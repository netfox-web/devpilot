import crypto from "node:crypto";

function cleanBaseUrl(value) {
  const baseUrl = String(value || "").trim().replace(/\/+$/, "");
  if (!baseUrl) throw new Error("DEVPILOT_API_BASE_URL is required");
  return baseUrl;
}

function requireValue(name, value) {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function jsonHeaders(settings, idempotencyKey) {
  return {
    "Content-Type": "application/json",
    "X-DevPilot-Source-System": requireValue("DEVPILOT_SOURCE_SYSTEM", settings.sourceSystem),
    "X-DevPilot-Api-Key": requireValue("DEVPILOT_API_KEY", settings.apiKey),
    "X-DevPilot-Request-Id": crypto.randomUUID(),
    "X-DevPilot-Idempotency-Key": idempotencyKey
  };
}

async function requestJson(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs || 10000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(`DevPilot request failed: ${response.status} ${payload.error || "unknown_error"}`);
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}

export async function testDevPilotConnection(settings) {
  const baseUrl = cleanBaseUrl(settings.baseUrl);
  return requestJson(`${baseUrl}/api/external/projects`, {
    method: "GET",
    headers: {
      "X-DevPilot-Source-System": requireValue("DEVPILOT_SOURCE_SYSTEM", settings.sourceSystem),
      "X-DevPilot-Api-Key": requireValue("DEVPILOT_API_KEY", settings.apiKey)
    }
  });
}

export async function registerDevPilotProject(settings, project) {
  const baseUrl = cleanBaseUrl(settings.baseUrl);
  const sourceSystem = requireValue("DEVPILOT_SOURCE_SYSTEM", settings.sourceSystem);
  const externalProjectId = requireValue("external_project_id", project.external_project_id);
  return requestJson(`${baseUrl}/api/external/projects/register`, {
    method: "POST",
    headers: jsonHeaders(settings, `register:${sourceSystem}:${externalProjectId}`),
    body: JSON.stringify(project)
  });
}

export async function sendDevPilotProjectEvent(settings, externalProjectId, event) {
  const baseUrl = cleanBaseUrl(settings.baseUrl);
  const sourceSystem = requireValue("DEVPILOT_SOURCE_SYSTEM", settings.sourceSystem);
  const projectId = encodeURIComponent(requireValue("external_project_id", externalProjectId));
  const eventType = requireValue("event_type", event.event_type);
  const keySeed = event.idempotencyKey || `${eventType}:${event.commit_sha || event.message || crypto.randomUUID()}`;
  return requestJson(`${baseUrl}/api/external/projects/${projectId}/events`, {
    method: "POST",
    headers: jsonHeaders(settings, `event:${sourceSystem}:${externalProjectId}:${keySeed}`),
    body: JSON.stringify(event)
  });
}

export async function createDevPilotHandoff(settings, taskId, handoff) {
  const baseUrl = cleanBaseUrl(settings.baseUrl);
  const sourceSystem = requireValue("DEVPILOT_SOURCE_SYSTEM", settings.sourceSystem);
  const idempotencySeed = handoff.external_ref || handoff.reason || crypto.randomUUID();
  return requestJson(`${baseUrl}/api/external/tasks/${encodeURIComponent(taskId)}/handoffs`, {
    method: "POST",
    headers: jsonHeaders(settings, `handoff:${sourceSystem}:${taskId}:${idempotencySeed}`),
    body: JSON.stringify(handoff)
  });
}

// Never log settings.apiKey or full request headers.
