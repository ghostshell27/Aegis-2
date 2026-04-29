// Single place where we talk to the local FastAPI backend.
// All endpoints are relative to the same origin the browser loaded,
// so this works identically in `vite dev` (via the proxy) and the bundled
// portable app.

async function request(path, { method = "GET", body, signal } = {}) {
  const headers = {};
  let payload;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const r = await fetch(path, { method, headers, body: payload, signal });
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch (e) {
    data = { raw: text };
  }
  if (!r.ok) {
    const detail = data?.detail || data?.error || `HTTP ${r.status}`;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = r.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  // config
  getConfig: () => request("/api/config"),
  saveConfig: (payload) => request("/api/config", { method: "POST", body: payload }),
  testConfig: () => request("/api/config/test", { method: "POST" }),
  clearConfig: () => request("/api/config", { method: "DELETE" }),
  exportProgressUrl: () => "/api/config/export",
  importProgress: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/config/import", { method: "POST", body: fd });
    const text = await r.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { raw: text }; }
    if (!r.ok) {
      const detail = data?.detail || data?.error || `HTTP ${r.status}`;
      const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = r.status;
      throw err;
    }
    return data;
  },

  // curriculum
  getCurriculum: () => request("/api/curriculum"),
  getTopic: (id) => request(`/api/curriculum/topic/${encodeURIComponent(id)}`),
  getDomains: () => request("/api/curriculum/domains"),

  // progress
  getProgressMap: () => request("/api/progress/map"),
  getSummary: () => request("/api/progress/summary"),
  getTopicDetail: (id) => request(`/api/progress/topic/${encodeURIComponent(id)}`),
  setPreferredDomain: (domain) =>
    request("/api/progress/preferred_domain", { method: "POST", body: { domain } }),
  getCapstone: (trackId) =>
    request(`/api/progress/capstone/${encodeURIComponent(trackId)}`),
  saveCapstone: (payload) =>
    request("/api/progress/capstone", { method: "POST", body: payload }),

  // sessions
  startSession: (payload) =>
    request("/api/session/start", { method: "POST", body: payload }),
  sendTurn: (payload) =>
    request("/api/session/turn", { method: "POST", body: payload }),
  endSession: (payload) =>
    request("/api/session/end", { method: "POST", body: payload }),
  getSessionHistory: (id) =>
    request(`/api/session/history/${encodeURIComponent(id)}`),
  getActiveSession: (topicId) =>
    request(`/api/session/active/${encodeURIComponent(topicId)}`),

  // generic
  ask: (prompt, system) =>
    request("/api/ai/ask", { method: "POST", body: { prompt, system } })
};
