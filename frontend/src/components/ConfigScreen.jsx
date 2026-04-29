import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

const PRESETS = [
  {
    label: "Anthropic (direct)",
    base_url: "https://api.anthropic.com",
    provider_hint: "anthropic",
    model: "claude-opus-4-7",
  },
  {
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    provider_hint: "openai",
    model: "gpt-4o-mini",
  },
  {
    label: "OpenRouter",
    base_url: "https://openrouter.ai/api/v1",
    provider_hint: "openai",
    model: "anthropic/claude-3.5-sonnet",
  },
  {
    label: "Chutes",
    base_url: "https://llm.chutes.ai/v1",
    provider_hint: "openai",
    model: "deepseek-ai/DeepSeek-V3",
  },
  {
    label: "Local (LM Studio / vLLM)",
    base_url: "http://127.0.0.1:1234/v1",
    provider_hint: "openai",
    model: "local-model",
  },
];

export default function ConfigScreen({ firstRun, onSaved }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    api_key: "",
    base_url: "https://api.anthropic.com",
    model_name: "claude-opus-4-7",
    custom_system_prompt:
      "You are a patient, encouraging tutor. Explain clearly. Use examples.",
    provider_hint: "auto",
  });
  const [view, setView] = useState(null);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const importInputRef = React.useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const v = await api.getConfig();
        setView(v);
        setForm((f) => ({
          ...f,
          base_url: v.base_url || f.base_url,
          model_name: v.model_name || f.model_name,
          custom_system_prompt: v.custom_system_prompt ?? f.custom_system_prompt,
          provider_hint: v.provider_hint || "auto",
        }));
      } catch (e) {
        setErr(e.message);
      }
    })();
  }, []);

  const applyPreset = (preset) => {
    setForm((f) => ({
      ...f,
      base_url: preset.base_url,
      provider_hint: preset.provider_hint,
      model_name: preset.model || f.model_name,
    }));
  };

  const save = async (e) => {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      if (!form.api_key && !view?.configured) {
        throw new Error("API key is required on first setup.");
      }
      const payload = { ...form };
      if (!payload.api_key) {
        // Leave unset so the backend preserves the existing encrypted key.
        delete payload.api_key;
      }
      await api.saveConfig(payload);
      setMsg("Saved.");
      onSaved && (await onSaved());
      if (firstRun) {
        navigate("/");
      }
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      const r = await api.testConfig();
      setMsg(`Connected. Reply: ${r.reply}`);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const resetAll = async () => {
    if (!confirm("Clear saved AI configuration? You will need to enter it again.")) return;
    try {
      await api.clearConfig();
      onSaved && (await onSaved());
      setMsg("Configuration cleared.");
    } catch (e) {
      setErr(e.message);
    }
  };

  const exportProgress = () => {
    setErr(null);
    setMsg(null);
    // Trigger a browser download by navigating to the streaming endpoint.
    // Same-origin, so the auth/header story is trivial.
    const a = document.createElement("a");
    a.href = api.exportProgressUrl();
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setMsg("Backup download started. Save the file somewhere safe.");
  };

  const onImportFileChosen = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) return;
    if (!confirm(
      `Replace your current progress with "${file.name}"?\n\n` +
      `Your existing data will be saved as userdata.db.bak in case you ` +
      `need to recover it. This action cannot be easily undone.`
    )) return;
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      const result = await api.importProgress(file);
      setMsg(
        `Progress imported successfully. ${
          result?.tables_found?.length || 0
        } tables restored. Reload the page to see your data.`
      );
      onSaved && (await onSaved());
    } catch (e) {
      setErr(`Import failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const triggerImport = () => {
    if (importInputRef.current) importInputRef.current.click();
  };

  return (
    <div className="card config-form">
      <h1>{firstRun ? "First-run configuration" : "AI provider settings"}</h1>
      <p className="hero-sub">
        Aegis 2 runs entirely through the AI provider you configure here. Your API
        key is encrypted with a key derived from this machine's hostname and stored
        locally in data/userdata.db. It never leaves the app except as an
        authorization header to your chosen endpoint.
      </p>

      <div style={{ marginBottom: 16 }}>
        <label>Quick presets</label>
        <div className="row">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              className="btn ghost small"
              onClick={() => applyPreset(p)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={save}>
        <div className="form-row">
          <label htmlFor="api_key">API key</label>
          <input
            id="api_key"
            type="password"
            autoComplete="off"
            value={form.api_key}
            placeholder={view?.configured ? `Stored (${view.api_key_preview})` : "sk-..."}
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
          />
          <div className="form-help">
            {view?.configured
              ? "Leave blank to keep the current key. Enter a new value to replace it."
              : "Required on first setup."}
          </div>
        </div>

        <div className="config-row">
          <div className="form-row">
            <label htmlFor="base_url">Base URL</label>
            <input
              id="base_url"
              type="url"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
            <div className="form-help">
              Anthropic uses /v1/messages; any OpenAI-compatible endpoint uses /chat/completions.
            </div>
          </div>

          <div className="form-row">
            <label htmlFor="provider_hint">Protocol</label>
            <select
              id="provider_hint"
              value={form.provider_hint}
              onChange={(e) => setForm({ ...form, provider_hint: e.target.value })}
            >
              <option value="auto">auto-detect</option>
              <option value="anthropic">anthropic</option>
              <option value="openai">openai-compatible</option>
            </select>
          </div>
        </div>

        <div className="form-row">
          <label htmlFor="model_name">Model name</label>
          <input
            id="model_name"
            type="text"
            value={form.model_name}
            onChange={(e) => setForm({ ...form, model_name: e.target.value })}
          />
        </div>

        <div className="form-row">
          <label htmlFor="custom_system_prompt">Custom system prompt (optional)</label>
          <textarea
            id="custom_system_prompt"
            value={form.custom_system_prompt}
            onChange={(e) => setForm({ ...form, custom_system_prompt: e.target.value })}
            placeholder='e.g. "Respond like a strict professor" or "Use only Spanish"'
          />
          <div className="form-help">
            Prepended to every AI interaction. Use it to shape tone, language, or teaching style.
          </div>
        </div>

        {err ? <div className="error" style={{ marginBottom: 12 }}>{err}</div> : null}
        {msg ? <div className="notice" style={{ marginBottom: 12 }}>{msg}</div> : null}

        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="row">
            <button className="btn primary" disabled={busy}>Save</button>
            <button type="button" className="btn" onClick={testConnection} disabled={busy}>
              Test connection
            </button>
          </div>
          {view?.configured ? (
            <button type="button" className="btn danger" onClick={resetAll}>
              Clear configuration
            </button>
          ) : null}
        </div>
      </form>

      <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "28px 0 20px" }} />

      <div>
        <h2 style={{ marginBottom: 6 }}>Backup &amp; restore</h2>
        <p className="hero-sub" style={{ fontSize: 14, marginBottom: 16 }}>
          Export your full progress (sessions, mastery, error patterns, encrypted
          API key, capstone state) to a single <code>.db</code> file. Keep it
          somewhere safe before updating Aegis 2 or moving to a new machine.
          Importing replaces your current data; the previous file is preserved
          as <code>userdata.db.bak</code> in case you need to roll back.
        </p>
        <div className="row">
          <button type="button" className="btn" onClick={exportProgress} disabled={busy}>
            Export progress
          </button>
          <button type="button" className="btn ghost" onClick={triggerImport} disabled={busy}>
            Import progress...
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".db,.sqlite,.sqlite3,application/octet-stream"
            style={{ display: "none" }}
            onChange={onImportFileChosen}
          />
        </div>
      </div>
    </div>
  );
}
