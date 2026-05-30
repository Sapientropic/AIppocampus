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

  function captureTurn(store, options) {
    if (!options || !options.enabled) {
      return { captured: false, reason: "capture_disabled" };
    }
    const userText = normalizeText(options.userText);
    const assistantText = normalizeText(options.assistantText);
    if (!userText && !assistantText) {
      return { captured: false, reason: "empty_turn" };
    }
    const now = options.now || new Date().toISOString();
    const record = {
      id: `turn-${now}-${store.records.length + 1}`,
      source: options.source || "claude.ai:local",
      capturedAt: now,
      userText,
      assistantText,
      text: normalizeText(`${userText}\n${assistantText}`),
    };
    record.terms = tokenize(record.text);
    store.records.push(record);
    return { captured: true, record };
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
        ? "Captured local turn. It remains in browser localStorage on this device."
        : `Capture skipped: ${result.reason}`;
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
    installBrowserPrototype,
    parseMemorySearchRequest,
    sanitizeText,
    searchMemory,
    tokenize,
    truncateMiddle,
  };
});
