// ==UserScript==
// @name         AIppocampus Claude Local Memory Search MVP
// @namespace    https://github.com/Sapientropic/AIppocampus
// @version      0.1.0
// @description  Local-first Claude.ai memory_search prototype with explicit capture and visible result handoff.
// @match        https://claude.ai/*
// @grant        none
// ==/UserScript==

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }
  root.AIppocampusBrowserMemory = api;
  if (typeof document !== "undefined") {
    api.installBrowserPrototype({ document, window: root });
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const STORE_KEY = "aippocampus.browserMemoryCompanion.v1";
  const ENABLED_KEY = "aippocampus.browserMemoryCompanion.enabled";
  const MAX_QUERY_RESULTS = 5;
  const MAX_RESULT_CHARS = 720;
  const MAX_HANDOFF_CHARS = 2400;
  const MAX_STORAGE_TEXT_CHARS = 12000;
  const MAX_EXPORT_TEXT_CHARS = 12000;
  const STORAGE_MODE = "redacted_local_storage_v1";

  const REDACTION_PATTERNS = [
    {
      type: "api-key",
      pattern: /\bsk-[A-Za-z0-9_-]{20,}\b/gi,
      replacement: "<redacted:api-key>",
    },
    {
      type: "bearer-token",
      pattern: /\bBearer\s+[A-Za-z0-9._~+/=-]{20,}/gi,
      replacement: "Bearer <redacted:bearer-token>",
    },
    {
      type: "credential-url",
      pattern: /\b([A-Za-z][A-Za-z0-9+.-]*:\/\/)[^@\s:/]+:[^@\s]+@/g,
      replacement: "$1<redacted:credentials>@",
    },
    {
      type: "secret-assignment",
      pattern:
        /\b(api[_-]?key|secret|token|password|passwd|cookie|authorization)\b\s*[:=]\s*("[^"]*"|'[^']*'|[^\s,;&]+)/gi,
      replacement: "$1=<redacted:secret>",
    },
    {
      type: "windows-local-path",
      pattern: /(?<![\w])(?:[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n\t ]+\\?)+[^\\/:*?"<>|\r\n\t ]*)/g,
      replacement: "<redacted:local-path>",
    },
    {
      type: "json-escaped-windows-local-path",
      pattern: /(?<![\w])(?:[A-Za-z]:\\\\[^"'\s<>]+)/g,
      replacement: "<redacted:local-path>",
    },
    {
      type: "posix-local-path",
      pattern: /(?<![\w:/])\/(?:Users|home|root|tmp|var|mnt|Volumes|private)\/(?:[^\s"'<>]+)/g,
      replacement: "<redacted:local-path>",
    },
  ];

  const INJECTION_PATTERNS = [
    /ignore (?:all )?(?:previous|prior) instructions/gi,
    /disregard (?:all )?(?:previous|prior) instructions/gi,
    /system prompt/gi,
    /developer message/gi,
    /<\s*(?:system|developer|tool)[^>]*>/gi,
  ];

  function createMemoryStore(records) {
    return { records: Array.isArray(records) ? records.slice() : [] };
  }

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function tokenize(value) {
    const text = normalizeText(value).toLowerCase();
    const terms = [];
    for (const part of text.split(/[\s,/|+，。；：！？、.!?()[\]{}<>《》"'`]+/)) {
      if (part.length >= 2) {
        terms.push(part);
      }
    }
    const latin = text.match(/[a-z][a-z0-9_.-]{1,}/g) || [];
    terms.push(...latin);
    const cjk = text.replace(/[a-z0-9_.-]+/g, " ");
    const cjkRuns = cjk.match(/[\u3400-\u9fff]{2,}/g) || [];
    for (const run of cjkRuns) {
      terms.push(run);
      for (let index = 0; index < run.length - 1; index += 1) {
        terms.push(run.slice(index, index + 2));
      }
    }
    return Array.from(new Set(terms.filter(Boolean)));
  }

  function sanitizeText(value) {
    let text = String(value || "");
    const redactionTypes = [];
    let redactionCount = 0;
    for (const item of REDACTION_PATTERNS) {
      text = text.replace(item.pattern, function () {
        redactionTypes.push(item.type);
        redactionCount += 1;
        return item.replacement;
      });
    }
    for (const pattern of INJECTION_PATTERNS) {
      text = text.replace(pattern, function () {
        redactionTypes.push("prompt-injection");
        redactionCount += 1;
        return "<redacted:prompt-injection>";
      });
    }
    return {
      text: normalizeText(text),
      redacted: redactionCount > 0,
      redactionCount,
      redactionTypes: Array.from(new Set(redactionTypes)),
    };
  }

  function sanitizeForLocalStorage(value, maxChars) {
    const sanitized = sanitizeText(value);
    const bounded = truncateMiddle(sanitized.text, maxChars || MAX_STORAGE_TEXT_CHARS);
    return {
      text: bounded.text,
      redacted: sanitized.redacted,
      redactionCount: sanitized.redactionCount,
      redactionTypes: sanitized.redactionTypes,
      truncated: bounded.truncated,
    };
  }

  function truncateMiddle(value, maxChars) {
    const text = normalizeText(value);
    if (text.length <= maxChars) {
      return { text, truncated: false };
    }
    const marker = " ...[truncated]... ";
    const keep = Math.max(8, Math.floor((maxChars - marker.length) / 2));
    return {
      text: `${text.slice(0, keep).trimEnd()}${marker}${text.slice(-keep).trimStart()}`,
      truncated: true,
    };
  }

  function stableSlug(value, fallback) {
    const text = normalizeText(value)
      .toLowerCase()
      .replace(/^https?:\/\//, "")
      .replace(/[^a-z0-9_.-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 120);
    return text || fallback || "local";
  }

  function hostFrom(value) {
    const text = normalizeText(value);
    if (!text) {
      return "";
    }
    try {
      return stableSlug(new URL(text).host, "");
    } catch (_) {
      return stableSlug(text.split(/[/:#?]/)[0], "");
    }
  }

  function exportHost(records, options) {
    return (
      hostFrom(options && options.host) ||
      hostFrom(options && options.locationHref) ||
      hostFrom(records[0] && records[0].source) ||
      "browser-local"
    );
  }

  function exportSessionId(records, options) {
    const explicit = stableSlug(options && options.sessionId, "");
    if (explicit) {
      return explicit;
    }
    const locationText = normalizeText(options && options.locationHref);
    if (locationText) {
      try {
        const url = new URL(locationText);
        const lastPath = url.pathname.split("/").filter(Boolean).pop();
        if (lastPath) {
          return stableSlug(`${url.host}-${lastPath}`, "browser-local-session");
        }
        return stableSlug(url.host, "browser-local-session");
      } catch (_) {
        return stableSlug(locationText, "browser-local-session");
      }
    }
    const first = records[0] || {};
    return stableSlug(`${exportHost(records, options)}-${first.source || "manual-capture"}`, "browser-local-session");
  }

  function rowForExport(record, role, text, context) {
    const sanitized = sanitizeText(text);
    const bounded = truncateMiddle(sanitized.text, context.maxTextChars);
    const source = sanitizeText(record.source || "browser-local").text || "browser-local";
    const row = {
      session_id: context.sessionId,
      timestamp: normalizeText(record.capturedAt),
      role,
      text: bounded.text,
      turn_id: context.turnId,
      source_ref: `browser:${context.host}:conversation:${context.sessionId}#turn:${context.turnId}:${role}`,
      provider_metadata: {
        provider: "browser-memory-companion",
        host: context.host,
        source,
        export_version: "generic-jsonl-v1",
        source_boundary: "browser-local-visible-capture",
        redacted: sanitized.redacted,
        redaction_types: sanitized.redactionTypes,
        truncated: bounded.truncated,
      },
    };
    return row;
  }

  function exportGenericJsonlRows(store, options) {
    const records = Array.isArray(store && store.records) ? store.records : [];
    const host = exportHost(records, options || {});
    const sessionId = exportSessionId(records, options || {});
    const maxTextChars = Number(options && options.maxTextChars) || MAX_EXPORT_TEXT_CHARS;
    const rows = [];
    const skipped = [];
    records.forEach((record, index) => {
      const userText = normalizeText(record && record.userText);
      const assistantText = normalizeText(record && record.assistantText);
      if (!userText && !assistantText) {
        skipped.push({ id: record && record.id, index, reason: "empty_turn" });
        return;
      }
      if (!userText && assistantText) {
        skipped.push({ id: record && record.id, index, reason: "missing_user_text" });
        return;
      }
      const turnId = stableSlug((record && record.id) || `turn-${index + 1}`, `turn-${index + 1}`);
      const context = {
        host,
        maxTextChars,
        sessionId,
        turnId,
      };
      rows.push(rowForExport(record, "user", userText, context));
      if (assistantText) {
        rows.push(rowForExport(record, "assistant", assistantText, context));
      }
    });
    return { rows, sessionId, skipped };
  }

  function exportGenericJsonl(store, options) {
    if (!options || !options.enabled) {
      return {
        exported: false,
        reason: "export_disabled",
        jsonl: "",
        rowCount: 0,
        sessionId: "",
        skipped: [],
      };
    }
    const result = exportGenericJsonlRows(store, options);
    const jsonl = result.rows.length
      ? `${result.rows.map((row) => JSON.stringify(row)).join("\n")}\n`
      : "";
    return {
      exported: result.rows.length > 0,
      reason: result.rows.length > 0 ? "" : "no_exportable_rows",
      jsonl,
      rowCount: result.rows.length,
      sessionId: result.sessionId,
      skipped: result.skipped,
    };
  }

  function captureTurn(store, options) {
    if (!options || !options.enabled) {
      return { captured: false, reason: "capture_disabled" };
    }
    const rawUserText = normalizeText(options.userText);
    const rawAssistantText = normalizeText(options.assistantText);
    if (!rawUserText && !rawAssistantText) {
      return { captured: false, reason: "empty_turn" };
    }
    const now = options.now || new Date().toISOString();
    const storedUser = sanitizeForLocalStorage(rawUserText, MAX_STORAGE_TEXT_CHARS);
    const storedAssistant = sanitizeForLocalStorage(rawAssistantText, MAX_STORAGE_TEXT_CHARS);
    const source = sanitizeText(options.source || "claude.ai:local").text || "claude.ai:local";
    const record = {
      id: `turn-${now}-${store.records.length + 1}`,
      source,
      capturedAt: now,
      userText: storedUser.text,
      assistantText: storedAssistant.text,
      text: normalizeText(`${storedUser.text}\n${storedAssistant.text}`),
      storage_mode: STORAGE_MODE,
      raw_capture_at_rest: false,
      storage_redaction_count: storedUser.redactionCount + storedAssistant.redactionCount,
      storage_redaction_types: Array.from(
        new Set([...storedUser.redactionTypes, ...storedAssistant.redactionTypes])
      ),
      storage_truncated: storedUser.truncated || storedAssistant.truncated,
    };
    record.terms = tokenize(record.text);
    store.records.push(record);
    return { captured: true, record };
  }

  function storageDiagnostics(store) {
    const records = Array.isArray(store && store.records) ? store.records : [];
    let redactedCount = 0;
    let legacyOrRawCount = 0;
    let redactionCount = 0;
    let truncatedCount = 0;
    for (const record of records) {
      if (record && record.storage_mode === STORAGE_MODE && record.raw_capture_at_rest === false) {
        redactedCount += 1;
      } else {
        legacyOrRawCount += 1;
      }
      redactionCount += Number(record && record.storage_redaction_count) || 0;
      if (record && record.storage_truncated) {
        truncatedCount += 1;
      }
    }
    return {
      storage_mode: legacyOrRawCount ? "mixed_or_legacy_local_storage" : STORAGE_MODE,
      raw_capture_at_rest: legacyOrRawCount > 0,
      record_count: records.length,
      redacted_record_count: redactedCount,
      legacy_or_raw_record_count: legacyOrRawCount,
      storage_redaction_count: redactionCount,
      storage_truncated_count: truncatedCount,
      boundary: "browser-local storage contains redacted/bounded visible text only for v1 records",
    };
  }

  function decodeEntities(value) {
    return String(value || "")
      .replace(/&quot;/g, '"')
      .replace(/&apos;/g, "'")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&");
  }

  function parseAttributes(value) {
    const attrs = {};
    const pattern = /([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)')/g;
    let match = pattern.exec(value);
    while (match) {
      attrs[match[1]] = decodeEntities(match[3] !== undefined ? match[3] : match[4]);
      match = pattern.exec(value);
    }
    return attrs;
  }

  function parseMemorySearchRequest(value) {
    const text = String(value || "");
    const match = text.match(/<\s*memory_search\b([^>]*)\/?\s*>/i);
    if (!match) {
      return null;
    }
    const attrs = parseAttributes(match[1]);
    const query = normalizeText(attrs.query || attrs.q || "");
    const max = Number.parseInt(attrs.max || attrs.limit || "", 10);
    return {
      tool: "memory_search",
      query,
      max: Number.isFinite(max) && max > 0 ? max : MAX_QUERY_RESULTS,
    };
  }

  function scoreRecord(record, queryTerms) {
    const recordTerms = new Set(record.terms || tokenize(record.text));
    let score = 0;
    for (const term of queryTerms) {
      if (recordTerms.has(term)) {
        score += term.length >= 4 ? 3 : 2;
      } else if (record.text.toLowerCase().includes(term)) {
        score += 1;
      }
    }
    return score;
  }

  function searchMemory(store, request, options) {
    if (!request || !request.query) {
      return [];
    }
    const maxResults = Math.min(
      Number(options && options.maxResults) || MAX_QUERY_RESULTS,
      Number(request.max) || MAX_QUERY_RESULTS,
      MAX_QUERY_RESULTS
    );
    const maxResultChars = Number(options && options.maxResultChars) || MAX_RESULT_CHARS;
    const queryTerms = tokenize(request.query);
    return store.records
      .map((record) => ({ record, score: scoreRecord(record, queryTerms) }))
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score)
      .slice(0, maxResults)
      .map((item) => {
        const sanitized = sanitizeText(item.record.text);
        const bounded = truncateMiddle(sanitized.text, maxResultChars);
        return {
          id: item.record.id,
          source: item.record.source,
          capturedAt: item.record.capturedAt,
          score: item.score,
          text: bounded.text,
          redacted: sanitized.redacted,
          redactionTypes: sanitized.redactionTypes,
          truncated: bounded.truncated,
          sourceBoundary: "browser-local-captured-turn",
        };
      });
  }

  function buildVisibleHandoff(results, options) {
    const query = normalizeText(options && options.query);
    const lines = [
      "[AIppocampus memory_search results]",
      `query: ${query || "(empty)"}`,
      "source-boundary: browser-local captured turns; generated summaries are not truth",
      "privacy: redacted, bounded, visible handoff; review before sending back to the model",
    ];
    if (!results.length) {
      lines.push("- no local results");
    }
    results.forEach((result, index) => {
      const flags = [];
      if (result.redacted) {
        flags.push(`redacted=${result.redactionTypes.join(",") || "yes"}`);
      }
      if (result.truncated) {
        flags.push("truncated");
      }
      lines.push(
        `- ${index + 1}. source=${result.source}; score=${result.score}; ${flags.join("; ")}`
      );
      lines.push(`  ${result.text}`);
    });
    const handoff = lines.join("\n");
    return truncateMiddle(handoff, MAX_HANDOFF_CHARS).text;
  }

  function loadStore(storage) {
    try {
      const raw = storage.getItem(STORE_KEY);
      return createMemoryStore(raw ? JSON.parse(raw) : []);
    } catch (_) {
      return createMemoryStore();
    }
  }

  function saveStore(storage, store) {
    storage.setItem(STORE_KEY, JSON.stringify(store.records.slice(-500)));
  }

  function installBrowserPrototype(env) {
    const doc = env.document;
    const win = env.window || window;
    if (!doc.body || doc.getElementById("aippocampus-memory-search-mvp")) {
      return;
    }
    const storage = win.localStorage;
    const store = loadStore(storage);
    const panel = doc.createElement("section");
    panel.id = "aippocampus-memory-search-mvp";
    panel.style.cssText =
      "position:fixed;right:16px;bottom:16px;z-index:2147483647;max-width:360px;" +
      "font:12px/1.4 system-ui,sans-serif;background:#111;color:#f8f8f2;border:1px solid #555;" +
      "padding:10px;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.35)";
    panel.innerHTML =
      '<label style="display:flex;gap:6px;align-items:center;margin-bottom:8px">' +
      '<input type="checkbox" data-aippocampus-enable /> AIppocampus capture/search</label>' +
      '<textarea data-aippocampus-user rows="2" style="width:100%;box-sizing:border-box" ' +
      'placeholder="User turn to capture after explicit consent"></textarea>' +
      '<textarea data-aippocampus-assistant rows="3" style="width:100%;box-sizing:border-box;margin-top:4px" ' +
      'placeholder="Assistant turn to capture after explicit consent"></textarea>' +
      '<button type="button" data-aippocampus-capture style="margin-top:6px">Capture local turn</button>' +
      '<button type="button" data-aippocampus-export style="margin-top:6px;margin-left:6px">Export generic JSONL</button>' +
      '<textarea data-aippocampus-query rows="2" style="width:100%;box-sizing:border-box" ' +
      'placeholder=\'<memory_search query="..." />\'></textarea>' +
      '<button type="button" data-aippocampus-run style="margin-top:6px">Run visible search</button>' +
      '<pre data-aippocampus-output style="white-space:pre-wrap;max-height:220px;overflow:auto"></pre>';
    doc.body.appendChild(panel);

    const checkbox = panel.querySelector("[data-aippocampus-enable]");
    const userBox = panel.querySelector("[data-aippocampus-user]");
    const assistantBox = panel.querySelector("[data-aippocampus-assistant]");
    const queryBox = panel.querySelector("[data-aippocampus-query]");
    const output = panel.querySelector("[data-aippocampus-output]");
    checkbox.checked = storage.getItem(ENABLED_KEY) === "true";
    checkbox.addEventListener("change", () => {
      storage.setItem(ENABLED_KEY, checkbox.checked ? "true" : "false");
    });
    panel.querySelector("[data-aippocampus-capture]").addEventListener("click", () => {
      const result = win.AIppocampusBrowserMemoryCapture({
        userText: userBox.value,
        assistantText: assistantBox.value,
      });
      output.textContent = result.captured
        ? "Captured local turn. Redacted/bounded text remains in browser localStorage on this device."
        : `Capture skipped: ${result.reason}`;
    });
    panel.querySelector("[data-aippocampus-export]").addEventListener("click", () => {
      const result = exportGenericJsonl(store, {
        enabled: checkbox.checked,
        host: win.location && win.location.host,
        locationHref: win.location && win.location.href,
      });
      if (!result.exported) {
        output.textContent = `Export skipped: ${result.reason}`;
        return;
      }
      if (!win.Blob || !win.URL || !win.URL.createObjectURL) {
        output.textContent = result.jsonl;
        return;
      }
      const blob = new win.Blob([result.jsonl], { type: "application/x-ndjson;charset=utf-8" });
      const url = win.URL.createObjectURL(blob);
      const anchor = doc.createElement("a");
      anchor.href = url;
      anchor.download = `aippocampus-browser-memory-${result.sessionId}.jsonl`;
      anchor.style.display = "none";
      doc.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      win.setTimeout(() => win.URL.revokeObjectURL(url), 0);
      output.textContent =
        `Exported ${result.rowCount} generic JSONL rows. ` +
        "Import with aippocampus import conversation --format generic-jsonl.";
    });
    panel.querySelector("[data-aippocampus-run]").addEventListener("click", () => {
      const request = parseMemorySearchRequest(queryBox.value);
      const results = searchMemory(store, request);
      output.textContent = buildVisibleHandoff(results, { query: request && request.query });
    });

    win.AIppocampusBrowserMemoryCapture = function (turn) {
      const result = captureTurn(store, {
        userText: turn && turn.userText,
        assistantText: turn && turn.assistantText,
        enabled: checkbox.checked,
        source: "claude.ai:manual-capture",
      });
      if (result.captured) {
        saveStore(storage, store);
      }
      return result;
    };
  }

  return {
    buildVisibleHandoff,
    captureTurn,
    createMemoryStore,
    exportGenericJsonl,
    exportGenericJsonlRows,
    installBrowserPrototype,
    parseMemorySearchRequest,
    sanitizeText,
    searchMemory,
    storageDiagnostics,
    tokenize,
    truncateMiddle,
  };
});
