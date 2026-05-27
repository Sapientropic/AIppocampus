
(() => {
  const body = document.body;
  const container = document.querySelector(".published-container");
  const siteHeader = document.querySelector(".site-header");
  const siteBody = document.querySelector(".site-body");
  const leftColumn = document.querySelector(".site-body-left-column");
  const centerColumn = document.querySelector(".site-body-center-column");
  const rightColumn = document.querySelector(".site-body-right-column");
  const mobileToolsButton = document.querySelector("#mobile-tools-btn");
  const sidebarButton = document.querySelector("#codex-mobile-nav-btn");
  const footer = document.querySelector(".site-footer");
  const search = document.querySelector(".search-bar");
  const renderContainer = document.querySelector(".render-container");
  const track = document.querySelector(".render-container-inner");
  const mainRenderer = track?.querySelector(".codex-main-renderer");
  const graphContainer = document.querySelector(".graph-view-container");
  const graphView = graphContainer?.querySelector(".graph-view");
  const graphCanvas = graphContainer?.querySelector(".codex-graph-canvas");
  const hitCanvas = graphContainer?.querySelector(".codex-graph-hit-canvas");
  const desktopGraphExpandIcon = document.querySelector(".graph-icon.graph-expand")?.innerHTML || "";
  const desktopGraphGlobalIcon = document.querySelector(".graph-icon.graph-global")?.innerHTML || "";
  const mobileCurrentGraphIcon = '<svg class="lucide lucide-locate-fixed" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="2" x2="5" y1="12" y2="12"/><line x1="19" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="5"/><line x1="12" x2="12" y1="19" y2="22"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/></svg>';
  const mobileGlobalGraphIcon = '<svg class="lucide lucide-share-2" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/></svg>';
  let graphPlaceholder = null;
  const paneData = JSON.parse(document.getElementById("codex-pane-data")?.textContent || "{}");
  const graphData = JSON.parse(document.getElementById("codex-graph-data")?.textContent || "{\"nodes\":[],\"edges\":[]}");
  const footerHome = { parent: footer?.parentNode || null, next: footer?.nextSibling || null };

  const state = {
    activeNote: "now",
    stackMode: "split",
    graphMode: "local",
    nodes: [],
    edges: [],
    hovered: null,
    dragging: null,
    dragStart: null,
    frame: 0,
    hoverFrame: 0,
    simulation: null,
    pixi: null,
    positions: new Map(),
    scrollAnimation: null,
    stagedOpenTimers: [],
    slidingClassFrame: 0,
    graphSoftRefresh: false
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#039;"
    }[ch]));
  }

  function slug(value) {
    return String(value || "note").trim().replace(/\s+/g, "-").replace(/[^\p{L}\p{N}_-]+/gu, "") || "note";
  }

  function supportsSlidingPanes() {
    return window.matchMedia?.("(min-width: 1279px)")?.matches ?? true;
  }

  function isCompactLayout() {
    return window.matchMedia?.("(max-width: 760px)")?.matches ?? false;
  }

  function publishHeading(level, title) {
    const safeTitle = escapeHtml(title);
    const safeSlug = escapeHtml(slug(title));
    return `
      <div class="el-h${level}">
        <h${level} data-heading="${safeTitle}" dir="auto" class="publish-article-heading" id="${safeSlug}" data-publish-anchor="${safeTitle}" data-publish-anchor-aliases="${safeTitle}">${safeTitle}</h${level}>
      </div>
    `;
  }

  function publishBody(bodyHtml) {
    const template = document.createElement("template");
    template.innerHTML = bodyHtml || "";
    const fragment = document.createElement("div");
    Array.from(template.content.childNodes).forEach((node) => {
      if (node.nodeType !== Node.ELEMENT_NODE) {
        fragment.appendChild(node.cloneNode(true));
        return;
      }
      const element = node.cloneNode(true);
      const tag = element.tagName.toLowerCase();
      if (/^h[1-6]$/.test(tag)) {
        const level = tag.slice(1);
        const title = element.textContent.trim();
        element.classList.add("publish-article-heading");
        element.setAttribute("data-heading", title);
        element.setAttribute("dir", "auto");
        element.id ||= slug(title);
        element.setAttribute("data-publish-anchor", title);
        element.setAttribute("data-publish-anchor-aliases", title);
        const wrapper = document.createElement(`div`);
        wrapper.className = `el-h${level}`;
        wrapper.appendChild(element);
        fragment.appendChild(wrapper);
        return;
      }
      const wrapperMap = { p: "el-p", ul: "el-ul", ol: "el-ol", div: "el-div", blockquote: "el-blockquote", table: "el-table", pre: "el-pre" };
      const wrapperClass = wrapperMap[tag];
      if (wrapperClass) {
        const wrapper = document.createElement("div");
        wrapper.className = wrapperClass;
        wrapper.appendChild(element);
        fragment.appendChild(wrapper);
        return;
      }
      fragment.appendChild(element);
    });
    return fragment.innerHTML;
  }

  function pageMarkup(id) {
    const page = paneData[id] || paneData.now;
    const title = page?.title || id;
    return `
      <div class="markdown-preview-pusher" style="width: 1px; height: 0.1px; margin-bottom: 0px;"></div>
      <div class="mod-header mod-ui">
        <h1 class="page-header" id="${escapeHtml(slug(title))}" data-heading="${escapeHtml(title)}">${escapeHtml(title)}</h1>
      </div>
      ${publishHeading(1, title)}
      ${publishBody(page?.body || "")}
    `;
  }

  function rendererShell(id, classes = "publish-renderer codex-slide-pane") {
    const page = paneData[id] || paneData.now;
    return `
      <article class="${classes}" data-note-id="${escapeHtml(id)}">
        <div class="markdown-preview-view markdown-rendered node-insert-event" tabindex="-1">
          <div class="markdown-preview-sizer markdown-preview-section">${pageMarkup(id)}</div>
        </div>
      </article>
    `;
  }

  function rendererTitle(renderer) {
    return renderer?.querySelector(".publish-article-heading, .page-header, h1")?.textContent?.trim() || "";
  }

  function closeIconMarkup() {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon lucide-x" aria-hidden="true" focusable="false"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>`;
  }

  function linkIconMarkup() {
    return `<svg class="lucide lucide-link" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`;
  }

  function ensureRendererChrome(renderer) {
    if (!renderer) return;
    const title = rendererTitle(renderer) || renderer.dataset.noteId || "";
    const noteId = renderer.dataset.noteId || "";
    let extraTitle = renderer.querySelector(":scope > .extra-title");
    if (!extraTitle) {
      extraTitle = document.createElement("div");
      extraTitle.className = "extra-title";
      extraTitle.innerHTML = `
        <span class="extra-title-text"></span>
        <span class="codex-pane-close" role="button">${closeIconMarkup()}</span>
      `;
      renderer.appendChild(extraTitle);
    }
    if (noteId) extraTitle.dataset.note = noteId;
    const titleText = extraTitle.querySelector(".extra-title-text");
    titleText.textContent = title;
    titleText.setAttribute("role", "link");
    titleText.tabIndex = 0;
    titleText.setAttribute("aria-label", `打开 ${title}`);
    if (titleText && titleText.dataset.boundOpen !== "true") {
      titleText.dataset.boundOpen = "true";
      titleText.addEventListener("click", (event) => {
        event.stopPropagation();
        const targetId = renderer.dataset.noteId;
        if (targetId) openNote(targetId);
      });
      titleText.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        titleText.click();
      });
    }
    const closeButton = extraTitle.querySelector(".codex-pane-close");
    closeButton?.setAttribute("aria-label", `关闭 ${title}`);
    if (closeButton && closeButton.dataset.boundClose !== "true") {
      closeButton.dataset.boundClose = "true";
      closeButton.addEventListener("click", (event) => {
        event.stopPropagation();
        if (renderer.classList.contains("codex-main-renderer")) {
          setMainPage("now", { clearPanes: true });
        } else {
          closePane(renderer);
        }
      });
      closeButton.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        closeButton.click();
      });
    }
  }

  function sourcePaneWidth() {
    return window.matchMedia?.("(min-width: 1800px)")?.matches ? 800 : 700;
  }

  const FOLDED_PANE_STEP = 36;

  function shouldSplitTwoPane(nextCount) {
    // Obsidian Publish only keeps a two-page open as a flat split when the
    // center rail can actually contain two readable panes. Below that width it
    // uses the same overlay drawer mechanics as deeper stacks.
    return nextCount === 2 && (renderContainer?.clientWidth || 0) >= 1400;
  }

  function applyStackLayout(activeId = state.activeNote) {
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    const stacked = supportsSlidingPanes() && renderers.length > 1;
    const mode = stacked ? state.stackMode : "split";
    const paneWidth = sourcePaneWidth();
    renderers.forEach((renderer, index) => {
      ensureRendererChrome(renderer);
      // Obsidian Publish's stack is history-sensitive. Opening the second pane
      // may be a true split on very wide center rails, but it becomes overlay
      // drawer navigation as soon as the rail cannot hold two readable panes.
      // Three or more panes keep old pages as book spines instead of replacing
      // history. The source runtime does not decide overlay/squished from the
      // current note id; it derives those classes from horizontal scroll. That
      // distinction is what makes clicking an existing book spine expand it in
      // place instead of feeling like a fresh page navigation.
      if (stacked) {
        if (mode === "split") {
          renderer.style.flex = "1 1 0px";
          renderer.style.width = "100%";
          renderer.style.minWidth = "0px";
        } else {
          renderer.style.flex = `0 0 ${paneWidth}px`;
          renderer.style.width = `${paneWidth}px`;
          renderer.style.minWidth = "700px";
        }
        renderer.style.left = `${index * 36}px`;
        renderer.style.right = `${-(664 - (renderers.length - 1 - index) * 36)}px`;
      } else {
        renderer.style.flex = "";
        renderer.style.width = "";
        renderer.style.minWidth = "700px";
        renderer.style.left = "0px";
        renderer.style.right = "-664px";
        renderer.classList.remove("mod-overlay", "mod-squished");
      }
    });
    state.activeNote = activeId;
    syncSlidingWindowClasses();
  }

  function rendererIndexForNote(id) {
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    const index = renderers.findIndex((renderer) => renderer.dataset.noteId === id);
    return index >= 0 ? index : Math.max(0, renderers.length - 1);
  }

  function stackScrollTargetForIndex(index) {
    if (!renderContainer) return 0;
    const maxScroll = Math.max(0, renderContainer.scrollWidth - renderContainer.clientWidth);
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    if (renderers.length <= 1 || state.stackMode === "split") return 0;
    const paneWidth = sourcePaneWidth();
    const sourceLikeTarget = Math.max(0, index) * (paneWidth - FOLDED_PANE_STEP);
    return Math.max(0, Math.min(maxScroll, Math.round(sourceLikeTarget)));
  }

  function stackEndScrollTarget() {
    return stackScrollTargetForIndex(rendererIndexForNote(state.activeNote));
  }

  function syncSlidingWindowClasses(scrollLeft = null) {
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    if (!renderContainer || !supportsSlidingPanes() || renderers.length <= 1 || state.stackMode === "split") {
      renderers.forEach((renderer) => renderer.classList.remove("mod-overlay", "mod-squished"));
      return;
    }
    const paneWidth = sourcePaneWidth();
    const spineTravel = paneWidth - FOLDED_PANE_STEP;
    const left = Number.isFinite(scrollLeft) ? scrollLeft : renderContainer.scrollLeft;
    const right = left + renderContainer.clientWidth;
    const count = renderers.length;
    renderers.forEach((renderer, index) => {
      const overlay =
        (index > 0 && left > spineTravel * (index - 1)) ||
        (index * paneWidth + (count - index - 1) * FOLDED_PANE_STEP > right);
      const squished =
        left >= spineTravel * (index + 1) ||
        (index * paneWidth + (count - index) * FOLDED_PANE_STEP >= right);
      renderer.classList.toggle("mod-overlay", overlay);
      renderer.classList.toggle("mod-squished", squished);
    });
  }

  function scheduleSlidingClassSync() {
    if (state.slidingClassFrame) return;
    state.slidingClassFrame = window.requestAnimationFrame(() => {
      state.slidingClassFrame = 0;
      syncSlidingWindowClasses();
    });
  }

  function sourceStackEase(t) {
    const clamped = Math.max(0, Math.min(1, t));
    if (clamped < 0.18) {
      const early = clamped / 0.18;
      return 0.1 * early * early;
    }
    const late = (clamped - 0.18) / 0.82;
    return 0.1 + 0.9 * (1 - Math.pow(1 - late, 4));
  }

  function stopScrollAnimation() {
    if (state.scrollAnimation?.frame) {
      window.cancelAnimationFrame(state.scrollAnimation.frame);
    }
    state.scrollAnimation = null;
  }

  function animateRenderScroll(target, options = {}) {
    if (!renderContainer) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const next = Math.max(0, Math.round(target));
    stopScrollAnimation();
    const explicitStart = Number.isFinite(options.from) ? Math.max(0, Math.round(options.from)) : null;
    if (reduceMotion || options.instant) {
      renderContainer.scrollLeft = next;
      return;
    }
    const start = explicitStart ?? renderContainer.scrollLeft;
    if (explicitStart !== null) {
      renderContainer.scrollLeft = start;
    }
    const delta = next - start;
    if (Math.abs(delta) < 1) {
      renderContainer.scrollLeft = next;
      return;
    }
    if (options.nativeSmooth && typeof renderContainer.scrollTo === "function") {
      // Source Obsidian Publish uses native smooth scrolling when a user clicks
      // an already-open folded pane. Keeping that path native preserves the
      // slow acceleration/deceleration that makes the book-spine feel unfold
      // instead of snapping into the current page slot.
      renderContainer.scrollTo({ left: next, top: 0, behavior: "smooth" });
      syncSlidingWindowClasses(start);
      return;
    }
    const duration = options.duration || 360;
    const startedAt = performance.now();
    const animation = { frame: 0 };
    state.scrollAnimation = animation;
    const step = (now) => {
      if (state.scrollAnimation !== animation) return;
      const progress = Math.min(1, (now - startedAt) / duration);
      const current = start + delta * sourceStackEase(progress);
      renderContainer.scrollLeft = current;
      syncSlidingWindowClasses(current);
      if (progress < 1) {
        animation.frame = window.requestAnimationFrame(step);
      } else {
        renderContainer.scrollLeft = next;
        syncSlidingWindowClasses(next);
        state.scrollAnimation = null;
      }
    };
    animation.frame = window.requestAnimationFrame(step);
  }

  function alignToActivePane(options = {}) {
    if (!renderContainer) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const settleDelay = reduceMotion || options.instant ? 0 : (options.nativeSmooth ? 860 : 560);

    window.requestAnimationFrame(() => {
      const target = stackEndScrollTarget();
      animateRenderScroll(target, options);

      // Publish's sliding stack changes width/class first, then lets the
      // horizontal scroller glide to the active page. Re-landing once after the
      // motion settles protects trimmed stacks and late width changes without
      // turning the drawer open into a hard jump.
      window.setTimeout(() => {
        const finalTarget = stackEndScrollTarget();
        if (Math.abs(renderContainer.scrollLeft - finalTarget) > 2) {
          stopScrollAnimation();
          renderContainer.scrollLeft = finalTarget;
        }
      }, settleDelay);
    });
  }

  function setActiveNav(id) {
    document.querySelectorAll("[data-note]").forEach((item) => {
      item.classList.toggle("mod-active", item.dataset.note === id);
    });
  }

  function renderOutline(id) {
    const outline = document.querySelector(".outline-view");
    const page = paneData[id] || paneData.now;
    if (!outline || !page) return;
    const children = (page.outline || []).map((heading) => `
      <div class="tree-item">
        <a class="tree-item-self is-clickable" href="#${escapeHtml(id)}" data-outline-target="#${escapeHtml(slug(heading))}" data-publish-anchor-target="${escapeHtml(slug(heading))}">
          <span class="tree-item-inner">${escapeHtml(heading)}</span>
        </a>
      </div>
    `).join("");
    outline.innerHTML = `
      <div class="tree-item">
        <a class="tree-item-self is-clickable mod-active" href="#${escapeHtml(id)}" data-outline-target="#${escapeHtml(slug(page.title))}" data-publish-anchor-target="${escapeHtml(slug(page.title))}">
          <span class="tree-item-inner">${escapeHtml(page.title)}</span>
        </a>
        <div class="tree-item-children">${children}</div>
      </div>
    `;
    outline.querySelectorAll(".tree-item-self.is-clickable[href]").forEach((link) => {
      if (link.dataset.boundOutline === "true") return;
      link.dataset.boundOutline = "true";
      link.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        scrollActiveOutlineTo(link.dataset.outlineTarget || link.getAttribute("href"), link);
      });
    });
  }

  function activeRenderer() {
    return (
      track?.querySelector(`:scope > .publish-renderer[data-note-id="${CSS.escape(state.activeNote)}"]`) ||
      mainRenderer ||
      track?.querySelector(":scope > .publish-renderer:last-of-type")
    );
  }

  function normalizeHash(value) {
    try {
      return decodeURIComponent(String(value || "").replace(/^#/, ""));
    } catch {
      return String(value || "").replace(/^#/, "");
    }
  }

  function findHeadingInRenderer(renderer, hash) {
    if (!renderer || !hash) return null;
    const normalized = normalizeHash(hash);
    const byId = renderer.querySelector(`#${CSS.escape(normalized)}`);
    if (byId) return byId;
    return Array.from(renderer.querySelectorAll(":is(h1, h2, h3, h4, h5, h6)[data-heading], .publish-article-heading"))
      .find((element) => slug(element.dataset.heading || element.textContent) === normalized) || null;
  }

  function flashHeading(target) {
    const flashTarget = target?.closest?.(".el-h1, .el-h2, .el-h3, .el-h4, .el-h5, .el-h6") || target;
    if (!flashTarget) return;
    flashTarget.classList.add("is-flashing");
    window.setTimeout(() => flashTarget.classList.remove("is-flashing"), 900);
  }

  function scrollActiveOutlineTo(hash, sourceElement = null) {
    const renderer = activeRenderer();
    const target = findHeadingInRenderer(renderer, hash);
    if (!renderer || !target) return false;
    const scroller = renderer.querySelector(".markdown-preview-view") || renderContainer;
    if (scroller) {
      const targetRect = target.getBoundingClientRect();
      const scrollRect = scroller.getBoundingClientRect();
      const nextTop = scroller.scrollTop + targetRect.top - scrollRect.top - 18;
      scroller.scrollTo({ top: Math.max(0, nextTop), behavior: "smooth" });
    } else {
      target.scrollIntoView({ block: "start", behavior: "smooth" });
    }
    document.querySelectorAll(".outline-view .tree-item-self").forEach((item) => {
      item.classList.toggle("mod-active", item === sourceElement);
    });
    flashHeading(target);
    window.history.replaceState({}, "", `#${state.activeNote}`);
    return true;
  }

  let hoverPreview = null;
  let hoverPreviewTrigger = null;
  let hoverPreviewTimer = 0;
  let hoverPreviewHideTimer = 0;
  const hoverPreviewMarkupCache = new Map();

  function previewTriggerFromEventTarget(target) {
    const trigger = target?.closest?.("a[data-note], .extra-title-text");
    if (!trigger || trigger.closest(".popover.hover-popover")) return null;
    if (trigger.classList?.contains("extra-title-text")) return trigger;
    // Preview only in reading panes. Left nav / right outline links already have
    // their own navigation semantics; previewing every sidebar link makes mouse
    // movement expensive on long generated dashboards.
    if (trigger.closest(".render-container")) return trigger;
    return null;
  }

  function noteIdFromPreviewTrigger(trigger) {
    const noteElement = trigger?.closest?.("[data-note]");
    const explicitNote = noteElement?.dataset?.note;
    if (explicitNote && paneData[explicitNote]) return explicitNote;
    const link = trigger?.closest?.("a[href]");
    const hashNote = normalizeHash(link?.getAttribute("href") || "");
    if (hashNote && paneData[hashNote]) return hashNote;
    const paneNote = trigger?.closest?.(".publish-renderer[data-note-id]")?.dataset?.noteId;
    if (trigger?.closest?.(".extra-title") && paneNote && paneData[paneNote]) return paneNote;
    return "";
  }

  function removeHoverPreview() {
    window.clearTimeout(hoverPreviewTimer);
    window.clearTimeout(hoverPreviewHideTimer);
    hoverPreviewTimer = 0;
    hoverPreviewHideTimer = 0;
    hoverPreview?.remove();
    hoverPreview = null;
    hoverPreviewTrigger = null;
  }

  function positionHoverPreview(trigger, preview) {
    const triggerRect = trigger.getBoundingClientRect();
    const width = Math.min(450, Math.max(320, Math.round(window.innerWidth - 32)));
    preview.style.width = `${width}px`;
    const height = Math.min(400, Math.max(260, Math.round(window.innerHeight - 32)));
    preview.style.height = `${height}px`;
    preview.style.maxWidth = "";
    preview.style.maxHeight = "";
    let left = triggerRect.left;
    left = Math.max(16, Math.min(left, window.innerWidth - width - 16));
    let top = triggerRect.bottom + 10;
    if (top + height > window.innerHeight - 16) {
      top = triggerRect.top - height - 10;
    }
    top = Math.max(16, Math.min(top, window.innerHeight - height - 16));
    preview.style.left = `${Math.round(left)}px`;
    preview.style.top = `${Math.round(top)}px`;
  }

  function hoverPreviewMarkupFor(noteId) {
    if (hoverPreviewMarkupCache.has(noteId)) return hoverPreviewMarkupCache.get(noteId);
    const page = paneData[noteId] || paneData.now;
    const markup = `
      <a class="hover-popover-link" href="#${escapeHtml(noteId)}" data-note="${escapeHtml(noteId)}" aria-label="打开 ${escapeHtml(page.title || noteId)}">${linkIconMarkup()}</a>
      <div class="markdown-embed is-loaded" data-note-id="${escapeHtml(noteId)}">
        <div class="markdown-embed-content">
          <div class="markdown-preview-view markdown-rendered node-insert-event" tabindex="-1">
            <div class="markdown-preview-sizer markdown-preview-section">
              <div class="markdown-preview-pusher" style="width: 1px; height: 0.1px; margin-bottom: 0px;"></div>
              ${pageMarkup(noteId)}
            </div>
          </div>
        </div>
      </div>
    `;
    hoverPreviewMarkupCache.set(noteId, markup);
    return markup;
  }

  function showHoverPreview(trigger) {
    const noteId = noteIdFromPreviewTrigger(trigger);
    if (!noteId || isCompactLayout()) return;
    if (hoverPreview && hoverPreviewTrigger === trigger) {
      positionHoverPreview(trigger, hoverPreview);
      return;
    }
    removeHoverPreview();
    hoverPreviewTrigger = trigger;
    hoverPreview = document.createElement("div");
    hoverPreview.className = "popover hover-popover is-loaded";
    hoverPreview.setAttribute("role", "tooltip");
    hoverPreview.innerHTML = hoverPreviewMarkupFor(noteId);
    hoverPreview.addEventListener("pointerenter", () => {
      window.clearTimeout(hoverPreviewHideTimer);
    });
    hoverPreview.addEventListener("pointerleave", (event) => {
      if (hoverPreviewTrigger?.contains(event.relatedTarget)) return;
      hoverPreviewHideTimer = window.setTimeout(removeHoverPreview, 160);
    });
    document.body.appendChild(hoverPreview);
    positionHoverPreview(trigger, hoverPreview);
  }

  function scheduleHoverPreview(trigger) {
    if (!trigger || trigger.closest(".popover.hover-popover")) return;
    window.clearTimeout(hoverPreviewHideTimer);
    window.clearTimeout(hoverPreviewTimer);
    hoverPreviewTimer = window.setTimeout(() => showHoverPreview(trigger), 400);
  }

  function scheduleHoverPreviewHide(relatedTarget) {
    if (hoverPreview?.contains(relatedTarget) || hoverPreviewTrigger?.contains(relatedTarget)) return;
    window.clearTimeout(hoverPreviewTimer);
    window.clearTimeout(hoverPreviewHideTimer);
    hoverPreviewHideTimer = window.setTimeout(removeHoverPreview, 160);
  }

  function setMainPage(id, options = {}) {
    const sizer = mainRenderer?.querySelector(".markdown-preview-sizer");
    if (!sizer || !paneData[id]) return false;
    clearStagedOpenTimers();
    if (options.clearPanes) {
      track?.querySelectorAll(":scope > .codex-slide-pane").forEach((pane) => pane.remove());
      state.stackMode = "split";
    }
    state.activeNote = id;
    sizer.innerHTML = pageMarkup(id);
    mainRenderer.dataset.noteId = id;
    applyStackLayout(id);
    renderOutline(id);
    setActiveNav(id);
    window.setTimeout(() => renderGraph({ soft: Boolean(options.softGraph) }), 60);
    mainRenderer?.scrollIntoView({ inline: "start", block: "nearest" });
    if (options.clearPanes && renderContainer) {
      stopScrollAnimation();
      renderContainer.scrollLeft = 0;
    }
    window.history.replaceState({}, "", `#${id}`);
    return true;
  }

  function rendererCount() {
    return track?.querySelectorAll(":scope > .publish-renderer")?.length || 0;
  }

  function setStackModeForOpen(nextCount) {
    if (!supportsSlidingPanes() || nextCount <= 1) {
      state.stackMode = "split";
    } else if (shouldSplitTwoPane(nextCount)) {
      state.stackMode = "split";
    } else {
      state.stackMode = "overlay";
    }
  }

  function setStackModeForClose(previousCount, nextCount) {
    if (!supportsSlidingPanes() || nextCount <= 1) {
      state.stackMode = "split";
    } else if (shouldSplitTwoPane(nextCount)) {
      state.stackMode = "split";
    } else {
      state.stackMode = "overlay";
    }
  }

  function clearStagedOpenTimers() {
    state.stagedOpenTimers.forEach((timer) => window.clearTimeout(timer));
    state.stagedOpenTimers = [];
  }

  function scheduleStagedOpenStep(callback, delay) {
    const timer = window.setTimeout(() => {
      state.stagedOpenTimers = state.stagedOpenTimers.filter((item) => item !== timer);
      callback();
    }, delay);
    state.stagedOpenTimers.push(timer);
  }

  function stageNewPaneForSourceOpen(pane, nextCount, activeId) {
    if (!pane) return;
    const paneWidth = sourcePaneWidth();
    const index = Math.max(0, nextCount - 1);
    ensureRendererChrome(pane);
    // Obsidian Publish does not immediately collapse the old foreground page
    // when a deeper card opens. The new renderer is first appended as a normal
    // right-side page, then the scroll motion starts, and only later do the old
    // pages become book spines. Adding final overlay classes up front makes the
    // page feel like it refreshed before sliding.
    pane.classList.remove("mod-overlay", "mod-squished");
    pane.style.flex = `0 0 ${paneWidth}px`;
    pane.style.width = `${paneWidth}px`;
    pane.style.minWidth = "700px";
    pane.style.left = `${index * 36}px`;
    pane.style.right = "-664px";
    state.activeNote = activeId;
  }

  function activatePane(pane) {
    const id = pane?.dataset.noteId;
    if (!pane || !id) return;
    const alreadyInStack = pane.parentElement === track;
    const previousCount = rendererCount();
    const previousScrollLeft = renderContainer?.scrollLeft || 0;
    clearStagedOpenTimers();
    if (alreadyInStack) {
      setStackModeForOpen(previousCount);
      applyStackLayout(id);
      alignToActivePane({ nativeSmooth: true });
      return;
    }
    track?.appendChild(pane);
    trimPaneStack();
    const nextCount = rendererCount();
    const stagedOpen = supportsSlidingPanes() && previousCount >= 2 && nextCount >= 3;
    if (stagedOpen) {
      setStackModeForOpen(nextCount);
      stageNewPaneForSourceOpen(pane, nextCount, id);
      scheduleStagedOpenStep(() => {
        animateRenderScroll(stackEndScrollTarget(), {
          from: previousScrollLeft,
          duration: 430
        });
      }, 33);
      scheduleStagedOpenStep(() => {
        applyStackLayout(id);
      }, 520);
      scheduleStagedOpenStep(() => {
        const finalTarget = stackEndScrollTarget();
        if (renderContainer && Math.abs(renderContainer.scrollLeft - finalTarget) > 2) {
          stopScrollAnimation();
          renderContainer.scrollLeft = finalTarget;
          syncSlidingWindowClasses(finalTarget);
        }
      }, 560);
      return;
    }
    setStackModeForOpen(nextCount);
    applyStackLayout(id);
    alignToActivePane({ from: previousScrollLeft });
  }

  function trimPaneStack() {
    // Source Publish keeps deep navigation history as a row of narrow book
    // spines. Do not trim old panes here: the long stack is the interaction,
    // and collapsing it turns the drawer into a hard page replacement.
  }

  function closePane(pane) {
    clearStagedOpenTimers();
    const previousCount = rendererCount();
    pane?.remove();
    const nextCount = rendererCount();
    setStackModeForClose(previousCount, nextCount);
    const latest = track?.querySelector(":scope > .codex-slide-pane:last-of-type");
    if (latest) {
      const id = latest.dataset.noteId || state.activeNote;
      state.activeNote = id;
      applyStackLayout(id);
      alignToActivePane();
      setActiveNav(id);
      renderOutline(id);
      window.setTimeout(renderGraph, 60);
      window.history.replaceState({}, "", `#${id}`);
    } else {
      const id = mainRenderer?.dataset.noteId || "now";
      state.activeNote = id;
      applyStackLayout(id);
      alignToActivePane();
      setActiveNav(id);
      renderOutline(id);
      window.setTimeout(renderGraph, 60);
      window.history.replaceState({}, "", `#${id}`);
    }
  }

  function openNote(id, options = {}) {
    if (!paneData[id]) return false;
    if (id === "now" || options.replaceMain || !supportsSlidingPanes()) {
      return setMainPage(id, { clearPanes: true });
    }
    let pane = track?.querySelector(`:scope > .codex-slide-pane[data-note-id="${CSS.escape(id)}"]`);
    if (!pane && track) {
      const fragment = document.createElement("template");
      fragment.innerHTML = rendererShell(id);
      pane = fragment.content.firstElementChild;
      ensureRendererChrome(pane);
    }
    if (pane) {
      activatePane(pane);
      setActiveNav(id);
      renderOutline(id);
      window.setTimeout(renderGraph, 60);
      window.history.replaceState({}, "", `#${id}`);
      return true;
    }
    return false;
  }

  function normalizeResponsiveStack() {
    if (supportsSlidingPanes()) return;
    track?.querySelectorAll(":scope > .codex-slide-pane").forEach((pane) => pane.remove());
    applyStackLayout(state.activeNote);
    if (renderContainer) renderContainer.scrollLeft = 0;
  }

  function isPrimaryNavigationOpen() {
    return Boolean(container?.classList.contains("is-left-column-open"));
  }

  function isMobileToolsDrawerOpen() {
    return Boolean(container?.classList.contains("is-mobile-tools-open"));
  }

  function setPrimaryNavigationOpen(open) {
    const nextState = Boolean(open) && isCompactLayout();
    if (nextState) container?.classList.remove("is-mobile-tools-open");
    container?.classList.toggle("is-left-column-open", nextState);
    sidebarButton?.setAttribute("aria-expanded", String(nextState));
    if (!nextState) sidebarButton?.blur?.();
    return nextState;
  }

  function setMobileToolsDrawerOpen(open) {
    const nextState = Boolean(open) && isCompactLayout();
    if (nextState) container?.classList.remove("is-left-column-open");
    container?.classList.toggle("is-mobile-tools-open", nextState);
    mobileToolsButton?.setAttribute("aria-expanded", String(nextState));
    scheduleGraphControlSync();
    if (nextState) window.setTimeout(renderGraph, 80);
    return nextState;
  }

  function syncFooterPlacement() {
    if (!footer || !centerColumn || !rightColumn) return;
    const compact = isCompactLayout();
    if (compact) {
      if (footer.parentNode !== centerColumn) centerColumn.appendChild(footer);
      return;
    }
    if (footerHome.parent && footer.parentNode !== footerHome.parent) {
      footerHome.parent.insertBefore(footer, footerHome.next);
    } else if (!footerHome.parent && footer.parentNode !== rightColumn) {
      rightColumn.appendChild(footer);
    }
  }

  function updateMobileShellMetrics() {
    if (!container) return;
    const headerHeight = siteHeader?.getBoundingClientRect().height || 0;
    const footerHeight = footer?.getBoundingClientRect().height || 0;
    container.style.setProperty("--mobile-shell-header-height", `${Math.round(headerHeight || 50)}px`);
    container.style.setProperty("--mobile-shell-footer-height", `${Math.round(footerHeight || 26)}px`);
  }

  function syncResponsiveShell() {
    const canSlide = supportsSlidingPanes();
    const compact = isCompactLayout();
    body.classList.toggle("sliding-windows", canSlide);
    if (!canSlide) normalizeResponsiveStack();
    rightColumn?.classList.toggle("mobile-tools-drawer", compact);
    if (mobileToolsButton) {
      mobileToolsButton.hidden = !compact;
      mobileToolsButton.setAttribute("aria-hidden", String(!compact));
    }
    if (!compact) {
      container?.classList.remove("is-left-column-open", "is-mobile-tools-open");
      sidebarButton?.setAttribute("aria-expanded", "false");
      mobileToolsButton?.setAttribute("aria-expanded", "false");
    }
    syncFooterPlacement();
    updateMobileShellMetrics();
    scheduleGraphControlSync();
  }

  function restoreFooter() {
    if (!footer) return;
    footer.dataset.customizedFooter = "true";
    footer.dataset.codexFooter = "memory";
    footer.innerHTML = `
      <div class="foot-links"><a href="#now" data-note="now" data-main="true">现在</a> · <a href="#health" data-note="health" data-main="true">Codex Memory</a> · <a href="#heartbeat" data-note="heartbeat" data-main="true">Heartbeat</a></div>
    `;
    syncFooterPlacement();
    updateMobileShellMetrics();
  }

  function setTheme(nextTheme, options = {}) {
    const isLight = nextTheme === "light";
    body.classList.toggle("theme-light", isLight);
    body.classList.toggle("theme-dark", !isLight);
    const toggle = document.querySelector(".site-body-left-column-site-theme-toggle");
    toggle?.classList.toggle("is-light", isLight);
    toggle?.classList.toggle("is-dark", !isLight);
    toggle?.querySelector(".checkbox-container")?.classList.toggle("is-enabled", !isLight);
    if (options.persist !== false) {
      try {
        window.localStorage?.setItem("codex-memory-theme", isLight ? "light" : "dark");
      } catch {
        // Storage can be unavailable in file previews; theme should still switch.
      }
    }
    window.setTimeout(renderGraph, 80);
  }

  function toggleTheme() {
    setTheme(body.classList.contains("theme-dark") ? "light" : "dark");
  }

  document.querySelector(".site-body-left-column-site-theme-toggle")?.addEventListener("click", toggleTheme);
  document.querySelector(".site-body-left-column-site-theme-toggle")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleTheme();
    }
  });

  sidebarButton?.addEventListener("click", () => {
    setPrimaryNavigationOpen(!isPrimaryNavigationOpen());
  });

  mobileToolsButton?.addEventListener("click", () => {
    setMobileToolsDrawerOpen(!isMobileToolsDrawerOpen());
  });

  // Bind on window capture so the private adapter wins before the copied
  // Publish helper's document-level hash navigation. Otherwise outline clicks
  // can be remapped by source heuristics that were built for real Publish DOM.
  window.addEventListener("click", (event) => {
    removeHoverPreview();
    const folder = event.target.closest("[data-folder-toggle]");
    if (folder) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      folder.closest(".tree-item")?.classList.toggle("is-collapsed");
      return;
    }
    const outlineLink = event.target.closest(".outline-view .tree-item-self.is-clickable[href]");
    if (outlineLink) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      scrollActiveOutlineTo(outlineLink.dataset.outlineTarget || outlineLink.getAttribute("href"), outlineLink);
      return;
    }
    const link = event.target.closest("a[data-note]");
    if (!link) return;
    const id = link.dataset.note;
    if (!id) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    const shouldReplaceMain = link.dataset.main === "true" || id === "now" || !supportsSlidingPanes();
    const didOpen = openNote(id, { replaceMain: shouldReplaceMain });
    if (didOpen && isCompactLayout()) {
      setPrimaryNavigationOpen(false);
      setMobileToolsDrawerOpen(false);
    }
  }, true);

  document.addEventListener("pointerover", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreview(trigger);
  }, true);

  document.addEventListener("pointerout", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreviewHide(event.relatedTarget);
  }, true);

  document.addEventListener("mouseover", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreview(trigger);
  }, true);

  document.addEventListener("mouseout", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreviewHide(event.relatedTarget);
  }, true);

  document.addEventListener("focusin", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreview(trigger);
  }, true);

  document.addEventListener("focusout", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreviewHide(event.relatedTarget);
  }, true);

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      search?.focus();
      search?.select();
    }
    if (event.key === "Escape") {
      if (isMobileToolsDrawerOpen()) {
        setMobileToolsDrawerOpen(false);
        return;
      }
      if (isPrimaryNavigationOpen()) {
        setPrimaryNavigationOpen(false);
        return;
      }
      closePane(track?.querySelector(":scope > .codex-slide-pane:last-of-type"));
      if (graphContainer?.classList.contains("mod-expanded")) {
        setGraphExpanded(false);
      }
    }
  });

  search?.addEventListener("input", () => {
    const value = search.value.trim().toLowerCase();
    document.querySelectorAll(".nav-view .tree-item").forEach((item) => {
      const text = item.textContent.toLowerCase();
      item.hidden = Boolean(value && !text.includes(value));
    });
  });

  window.addEventListener("resize", () => {
    window.requestAnimationFrame(() => {
      syncResponsiveShell();
      applyStackLayout(state.activeNote);
      alignToActivePane();
    });
  });

  renderContainer?.addEventListener("scroll", scheduleSlidingClassSync, { passive: true });

  function graphSize() {
    const rect = graphView?.getBoundingClientRect();
    return {
      width: Math.max(180, Math.round(rect?.width || 242)),
      height: Math.max(180, Math.round(rect?.height || 250))
    };
  }

  function resizeCanvas(canvas, width, height) {
    if (!canvas) return null;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.width = Math.max(1, Math.round(width * dpr));
    canvas.height = Math.max(1, Math.round(height * dpr));
    const ctx = canvas.getContext("2d");
    ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    return ctx;
  }

  function graphNodeIdForPane(paneId) {
    const direct = graphData.nodes.find((node) => node.id === paneId);
    if (direct) return direct.id;
    const byPane = graphData.nodes.find((node) => node.pane === paneId);
    return byPane?.id || graphData.root || "now";
  }

  function visibleGraph() {
    const visible = new Set();
    if (state.graphMode === "global") {
      graphData.nodes.forEach((node) => visible.add(node.id));
    } else {
      const activeId = graphNodeIdForPane(state.activeNote);
      visible.add(activeId);
      const byId = new Map(graphData.nodes.map((node) => [node.id, node]));
      const neighbors = [];
      graphData.edges.forEach((edge) => {
        if (edge.source === activeId && byId.has(edge.target)) neighbors.push(byId.get(edge.target));
        if (edge.target === activeId && byId.has(edge.source)) neighbors.push(byId.get(edge.source));
      });
      const uniqueNeighbors = Array.from(new Map(neighbors.map((node) => [node.id, node])).values());
      const pageNeighbors = uniqueNeighbors.filter((node) => node.type === "page" || node.type === "system");
      const topicNeighbors = uniqueNeighbors
        .filter((node) => node.type === "topic")
        .sort((a, b) => Number(a.label_priority || 99) - Number(b.label_priority || 99));
      pageNeighbors.forEach((node) => visible.add(node.id));
      topicNeighbors.slice(0, activeId === "now" ? 8 : 10).forEach((node) => visible.add(node.id));
      // Keyword helper nodes support global clustering, but they are not real
      // Publish note links. Keeping them out of current-page graphs prevents a
      // local graph from looking like one labeled page dragging anonymous dots.
      if (visible.size < 10 && activeId === (graphData.root || "now")) {
        graphData.nodes
          .filter((node) => node.type === "page" || node.type === "system")
          .forEach((node) => visible.add(node.id));
        graphData.nodes
          .filter((node) => node.type === "topic")
          .sort((a, b) => Number(a.label_priority || 99) - Number(b.label_priority || 99))
          .slice(0, 8)
          .forEach((node) => visible.add(node.id));
      }
    }
    return {
      nodes: graphData.nodes.filter((node) => visible.has(node.id)).map((node) => ({ ...node })),
      edges: graphData.edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target))
    };
  }

  function seed(nodes, width, height) {
    const cx = width / 2;
    const cy = height / 2;
    const span = Math.min(width, height);
    const activeRoot = graphNodeIdForPane(state.activeNote);
    const primaryRoot = state.graphMode === "local" ? activeRoot : (graphData.root || "now");
    const radiusScale = graphContainer?.classList.contains("mod-expanded")
      ? Math.min(1.16, Math.max(0.94, span / 780))
      : 0.8;
    nodes.forEach((node, index) => {
      const saved = state.positions.get(node.id);
      const canReuseSaved = saved?.width && saved?.height
        && Math.max(width / saved.width, saved.width / width) < 1.35
        && Math.max(height / saved.height, saved.height / height) < 1.35;
      const angle = index * 2.399963229728653 - Math.PI / 2;
      const normalized = Math.sqrt((index + 1) / Math.max(1, nodes.length));
      const spread = span * normalized * (node.type === "keyword" ? 0.36 : node.type === "system" ? 0.24 : 0.28);
      const isPrimaryRoot = node.id === primaryRoot;
      const shouldGlideRoot = state.graphSoftRefresh && isPrimaryRoot && canReuseSaved;
      node.x = shouldGlideRoot ? saved.x : (isPrimaryRoot ? cx : (canReuseSaved ? saved.x : cx + Math.cos(angle) * spread));
      node.y = shouldGlideRoot ? saved.y : (isPrimaryRoot ? cy : (canReuseSaved ? saved.y : cy + Math.sin(angle) * spread));
      node.vx = canReuseSaved ? saved.vx : 0;
      node.vy = canReuseSaved ? saved.vy : 0;
      const isPinnedRoot = state.graphMode === "local" && node.id === activeRoot;
      const baseRadius = isPinnedRoot ? 6.2 : (node.type === "page" ? 5.4 : node.type === "topic" ? 3.8 : node.type === "system" ? 3.4 : 2.4);
      node.r = baseRadius * radiusScale;
      node.pinnedRoot = isPinnedRoot;
      // Do not hard-pin the active node with fx/fy on navigation: D3 applies
      // fixed coordinates immediately, which reads as a visual jump. The x/y
      // forces below still make the clicked node become the new center, but it
      // glides there from its saved position.
      node.fx = null;
      node.fy = null;
    });
  }

  function tick(width, height) {
    const byId = new Map(state.nodes.map((node) => [node.id, node]));
    state.edges.forEach((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const ideal = edge.type === "HAS_KEYWORD" ? 48 : 68;
      const force = (distance - ideal) * 0.006;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      if (!source.fixed) {
        source.vx += fx;
        source.vy += fy;
      }
      if (!target.fixed) {
        target.vx -= fx;
        target.vy -= fy;
      }
    });
    for (let i = 0; i < state.nodes.length; i += 1) {
      for (let j = i + 1; j < state.nodes.length; j += 1) {
        const a = state.nodes[i];
        const b = state.nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const force = 36 / (distance * distance);
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        if (!a.fixed) {
          a.vx -= fx;
          a.vy -= fy;
        }
        if (!b.fixed) {
          b.vx += fx;
          b.vy += fy;
        }
      }
    }
    const cx = width / 2;
    const cy = height / 2;
    state.nodes.forEach((node) => {
      if (!node.fixed) {
        node.vx += (cx - node.x) * 0.0025;
        node.vy += (cy - node.y) * 0.0025;
        node.vx *= 0.84;
        node.vy *= 0.84;
        node.x = Math.min(width - 18, Math.max(18, node.x + node.vx));
        node.y = Math.min(height - 18, Math.max(18, node.y + node.vy));
      }
      state.positions.set(node.id, { x: node.x, y: node.y, vx: node.vx, vy: node.vy, width, height });
    });
  }

  function connected(id) {
    const set = new Set([id]);
    state.edges.forEach((edge) => {
      if (edge.source === id) set.add(edge.target);
      if (edge.target === id) set.add(edge.source);
    });
    return set;
  }

  function cssVar(name, fallback) {
    return getComputedStyle(body).getPropertyValue(name).trim() || fallback;
  }

  function colorNumber(value, fallback) {
    const raw = String(value || fallback || "").trim();
    const hex = raw.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (hex) {
      const body = hex[1].length === 3
        ? hex[1].split("").map((ch) => ch + ch).join("")
        : hex[1];
      return Number.parseInt(body, 16);
    }
    const rgb = raw.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (rgb) return (Number(rgb[1]) << 16) + (Number(rgb[2]) << 8) + Number(rgb[3]);
    return colorNumber(fallback || "#38a6de", "#38a6de");
  }

  function ensurePixiRenderer(width, height) {
    if (!window.PIXI?.Application || !graphCanvas) return false;
    const resolution = Math.min(window.devicePixelRatio || 1, 2);
    if (!state.pixi) {
      try {
        const app = new window.PIXI.Application({
          view: graphCanvas,
          width,
          height,
          backgroundAlpha: 0,
          antialias: true,
          autoDensity: true,
          resolution
        });
        const links = new window.PIXI.Graphics();
        const nodes = new window.PIXI.Graphics();
        const labels = new window.PIXI.Container();
        app.stage.addChild(links);
        app.stage.addChild(nodes);
        app.stage.addChild(labels);
        state.pixi = { app, links, nodes, labels };
      } catch {
        state.pixi = null;
        return false;
      }
    }
    graphCanvas.style.width = `${width}px`;
    graphCanvas.style.height = `${height}px`;
    state.pixi.app.renderer.resize(width, height);
    resizeCanvas(hitCanvas, width, height);
    return true;
  }

  function drawPixi(width, height, muted) {
    const pixi = state.pixi;
    if (!pixi) return;
    const nodeColor = colorNumber(cssVar("--graph-node", "rgb(56, 166, 222)"), "#38a6de");
    const lineColor = colorNumber(cssVar("--graph-line", "rgba(118,117,117,0.58)"), "#767575");
    const textColor = colorNumber(cssVar("--graph-text", "rgba(136,159,170,1)"), "#889faa");
    const byId = new Map(state.nodes.map((node) => [node.id, node]));
    pixi.links.clear();
    pixi.nodes.clear();
    pixi.labels.removeChildren().forEach((child) => child.destroy({ children: true }));
    state.edges.forEach((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return;
      const alpha = muted && (!muted.has(source.id) || !muted.has(target.id)) ? 0.1 : 0.42;
      pixi.links.lineStyle(0.75, lineColor, alpha);
      pixi.links.moveTo(source.x, source.y);
      pixi.links.lineTo(target.x, target.y);
    });
    state.nodes.forEach((node) => {
      const isMuted = muted && !muted.has(node.id);
      const fill = nodeColor;
      const alpha = isMuted ? 0.22 : (node.type === "keyword" ? 0.38 : 1);
      pixi.nodes.beginFill(fill, alpha);
      pixi.nodes.drawCircle(node.x, node.y, node.r);
      pixi.nodes.endFill();
      if (!shouldShowLabel(node, width, muted)) return;
      const label = compactGraphLabel(node.label, width, node);
      const fontSize = graphLabelFontSize(width, node);
      const text = new window.PIXI.Text(label, {
        fontFamily: cssVar("--font-default", "serif"),
        fontSize,
        fill: textColor,
        align: "center",
        resolution: Math.min(window.devicePixelRatio || 1, 2)
      });
      text.anchor.set(0.5, 1);
      text.alpha = isMuted ? 0.28 : 1;
      text.position.set(node.x, node.y - node.r - 4);
      pixi.labels.addChild(text);
    });
    pixi.app.renderer.render(pixi.app.stage);
  }

  function drawCanvas(width, height, muted) {
    if (!graphCanvas) return;
    const ctx = resizeCanvas(graphCanvas, width, height);
    resizeCanvas(hitCanvas, width, height);
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    const nodeColor = cssVar("--graph-node", "rgb(56, 166, 222)");
    const lineColor = cssVar("--graph-line", "rgba(118,117,117,0.58)");
    const textColor = cssVar("--graph-text", "rgba(136,159,170,1)");
    const byId = new Map(state.nodes.map((node) => [node.id, node]));
    ctx.lineWidth = 0.75;
    state.edges.forEach((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return;
      ctx.globalAlpha = muted && (!muted.has(source.id) || !muted.has(target.id)) ? 0.1 : 0.42;
      ctx.strokeStyle = lineColor;
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
    state.nodes.forEach((node) => {
      const isMuted = muted && !muted.has(node.id);
      ctx.globalAlpha = isMuted ? 0.22 : (node.type === "keyword" ? 0.38 : 1);
      ctx.fillStyle = nodeColor;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
      ctx.fill();
      const showLabel = shouldShowLabel(node, width, muted);
      if (showLabel) {
        const fontSize = graphLabelFontSize(width, node);
        ctx.font = `${fontSize}px var(--font-default, serif)`;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        const label = compactGraphLabel(node.label, width, node);
        ctx.globalAlpha = isMuted ? 0.28 : 1;
        ctx.fillStyle = textColor;
        ctx.fillText(label, node.x, node.y - node.r - 4);
      }
    });
    ctx.globalAlpha = 1;
  }

  function draw() {
    if (!graphCanvas) return;
    const { width, height } = graphSize();
    const muted = state.hovered ? connected(state.hovered) : null;
    if (ensurePixiRenderer(width, height)) {
      drawPixi(width, height, muted);
      body.dataset.graphRenderer = "pixi";
      return;
    }
    drawCanvas(width, height, muted);
    body.dataset.graphRenderer = "canvas";
  }

  function shouldShowLabel(node, width, muted) {
    if (node.id === state.hovered) return true;
    const isGlobal = state.graphMode === "global";
    const isSparseLocal = !isGlobal && state.nodes.length <= 8;
    if (node.pinnedRoot) return true;
    if (isSparseLocal) return true;
    if (node.type === "keyword") return false;
    const priority = Number(node.label_priority || 99);
    if (isGlobal && width < 300) return node.type === "page" || node.type === "system" || priority <= 8;
    if (isGlobal && width < 520) {
      return node.type === "page" || node.type === "system" || priority <= 12 || Boolean(muted?.has?.(node.id));
    }
    if (width < 300) return node.type === "page" || node.type === "system";
    if (width < 520) return node.type === "page" || node.type === "system" || priority <= 14 || Boolean(muted?.has?.(node.id));
    return true;
  }

  function graphLabelFontSize(width, node = null) {
    const base = width < 300 ? 7 : width < 520 ? 8 : Math.min(12, Math.max(9, width / 150));
    return node?.pinnedRoot ? Math.max(base + 1.5, 8.5) : base;
  }

  function compactGraphLabel(label, width, node = null) {
    const limit = node?.pinnedRoot ? (width < 300 ? 26 : 36) : (width < 300 ? 12 : width < 520 ? 18 : 28);
    return label.length > limit ? `${label.slice(0, limit)}…` : label;
  }

  function animate() {
    const { width, height } = graphSize();
    for (let i = 0; i < 3; i += 1) tick(width, height);
    draw();
    state.frame = window.requestAnimationFrame(animate);
  }

  function renderGraph(options = {}) {
    if (!graphCanvas || !graphView) return;
    state.graphSoftRefresh = Boolean(options.soft);
    if (state.frame) window.cancelAnimationFrame(state.frame);
    if (state.simulation) {
      state.simulation.stop();
      state.simulation = null;
    }
    const { width, height } = graphSize();
    const graph = visibleGraph();
    state.nodes = graph.nodes;
    state.edges = graph.edges;
    seed(state.nodes, width, height);
    draw();
    if (!startD3Simulation(width, height, { soft: state.graphSoftRefresh })) {
      body.dataset.graphEngine = state.pixi ? "pixi+manual-force" : "manual-force";
      state.frame = window.requestAnimationFrame(animate);
    }
    state.graphSoftRefresh = false;
  }

  function startD3Simulation(width, height, options = {}) {
    if (!window.d3?.forceSimulation) return false;
    body.dataset.graphEngine = state.pixi ? "pixi+d3-force" : "d3-force";
    const links = state.edges.map((edge) => ({ ...edge }));
    const expanded = graphContainer?.classList.contains("mod-expanded");
    const layoutScale = Math.max(1, Math.min(expanded ? 5.2 : 2.25, Math.min(width, height) / (expanded ? 210 : 300)));
    const linkDistance = (edge) => (edge.type === "HAS_KEYWORD" ? 25 : edge.type === "TRACKS" ? 46 : 54) * layoutScale;
    const linkStrength = (edge) => edge.type === "HAS_KEYWORD" ? 0.48 : 0.68;
    const chargeStrength = (node) => {
      if (node.type === "keyword") return -3.5 * layoutScale;
      if (node.type === "page") return -92 * layoutScale;
      if (node.type === "system") return -34 * layoutScale;
      return (state.graphMode === "global" ? -26 : -30) * layoutScale;
    };
    state.simulation = window.d3.forceSimulation(state.nodes)
      .alpha(options.soft ? 0.36 : 0.82)
      .alphaDecay(options.soft ? 0.045 : 0.035)
      .velocityDecay(options.soft ? 0.62 : 0.42)
      .force("link", window.d3.forceLink(links).id((node) => node.id).distance(linkDistance).strength(linkStrength))
      .force("charge", window.d3.forceManyBody().strength(chargeStrength).distanceMin(18).distanceMax(Math.max(width, height) * 0.75))
      .force("collide", window.d3.forceCollide((node) => node.r + (node.type === "keyword" ? 2 : 5) * layoutScale).strength(0.72).iterations(2))
      .force("center", window.d3.forceCenter(width / 2, height / 2).strength(expanded ? 0.12 : 0.18))
      .force("x", window.d3.forceX(width / 2).strength((node) => node.pinnedRoot ? (options.soft ? 0.5 : 0.34) : (expanded ? 0.028 : 0.045)))
      .force("y", window.d3.forceY(height / 2).strength((node) => node.pinnedRoot ? (options.soft ? 0.5 : 0.34) : (expanded ? 0.028 : 0.045)))
      .on("tick", () => {
        clampNodes(width, height);
        draw();
      });
    return true;
  }

  function clampNodes(width, height) {
    state.nodes.forEach((node) => {
      node.x = Math.min(width - 16, Math.max(16, node.x));
      node.y = Math.min(height - 16, Math.max(16, node.y));
      state.positions.set(node.id, { x: node.x, y: node.y, vx: node.vx || 0, vy: node.vy || 0, width, height });
    });
  }

  function pointerPoint(event) {
    const rect = graphCanvas.getBoundingClientRect();
    const { width, height } = graphSize();
    return {
      x: ((event.clientX - rect.left) / rect.width) * width,
      y: ((event.clientY - rect.top) / rect.height) * height
    };
  }

  function hitTest(point) {
    let winner = null;
    for (const node of state.nodes) {
      if (Math.hypot(node.x - point.x, node.y - point.y) <= Math.max(12, node.r + 7)) {
        winner = node;
      }
    }
    return winner;
  }

  function scheduleGraphHoverDraw() {
    if (state.hoverFrame) return;
    state.hoverFrame = window.requestAnimationFrame(() => {
      state.hoverFrame = 0;
      draw();
    });
  }

  graphCanvas?.addEventListener("pointerdown", (event) => {
    const node = hitTest(pointerPoint(event));
    if (!node) return;
    state.dragging = node;
    state.dragStart = { x: event.clientX, y: event.clientY, moved: false, node };
    node.fixed = true;
    node.fx = node.x;
    node.fy = node.y;
    state.simulation?.alphaTarget(0.16).restart();
    graphCanvas.setPointerCapture?.(event.pointerId);
  });

  graphCanvas?.addEventListener("pointermove", (event) => {
    const point = pointerPoint(event);
    if (state.dragging) {
      if (state.dragStart && Math.hypot(event.clientX - state.dragStart.x, event.clientY - state.dragStart.y) > 4) {
        state.dragStart.moved = true;
      }
      state.dragging.x = point.x;
      state.dragging.y = point.y;
      state.dragging.fx = point.x;
      state.dragging.fy = point.y;
      return;
    }
    const hit = hitTest(point);
    const nextHovered = hit?.id || null;
    if (state.hovered !== nextHovered) {
      state.hovered = nextHovered;
      scheduleGraphHoverDraw();
    }
    graphCanvas.style.cursor = hit ? "pointer" : "default";
  });

  graphCanvas?.addEventListener("pointerleave", () => {
    if (!state.hovered) return;
    state.hovered = null;
    graphCanvas.style.cursor = "default";
    scheduleGraphHoverDraw();
  });

  graphCanvas?.addEventListener("pointerup", (event) => {
    if (!state.dragging) return;
    const clicked = state.dragStart && !state.dragStart.moved ? state.dragStart.node : null;
    const wasPinnedRoot = state.dragging.pinnedRoot;
    state.dragging.fixed = false;
    state.dragging.fx = null;
    state.dragging.fy = null;
    state.dragging = null;
    state.dragStart = null;
    state.simulation?.alphaTarget(0);
    graphCanvas.releasePointerCapture?.(event.pointerId);
    if (clicked?.pane) {
      // A graph click is a focus change, not just navigation. Obsidian Publish
      // recenters the clicked note as the local graph root; keeping global mode
      // here makes the page change but leaves the old hub visually in charge.
      state.graphMode = "local";
      setMainPage(clicked.pane, { clearPanes: true, softGraph: true });
      scheduleGraphControlSync();
    }
  });

  function setGraphButtonIcon(button, iconMarkup, iconKey) {
    if (!button || button.dataset.mobileGraphIcon === iconKey) return;
    button.innerHTML = iconMarkup;
    button.dataset.mobileGraphIcon = iconKey;
  }

  function syncGraphControls() {
    const expand = document.querySelector(".graph-view-container .graph-icon.graph-expand");
    const globalToggle = document.querySelector(".graph-view-container .graph-icon.graph-global");
    const mobileDrawer = isCompactLayout() && Boolean(rightColumn?.classList.contains("mobile-tools-drawer"));
    const isGlobalView = state.graphMode === "global";
    const isExpanded = Boolean(graphContainer?.classList.contains("mod-expanded"));

    if (expand) {
      if (mobileDrawer) {
        setGraphButtonIcon(expand, mobileCurrentGraphIcon, "current");
        expand.removeAttribute("aria-hidden");
        expand.tabIndex = 0;
        expand.setAttribute("title", isGlobalView ? "切换到当前页面图谱" : "当前页面图谱");
        expand.setAttribute("aria-label", isGlobalView ? "当前页面图谱" : "当前页面图谱（当前）");
        expand.classList.toggle("is-active", !isGlobalView);
      } else {
        setGraphButtonIcon(expand, desktopGraphExpandIcon, "expand");
        expand.setAttribute("title", isExpanded ? "Collapse Graph" : (isGlobalView ? "Expand Global Graph" : "Expand Current Graph"));
        expand.setAttribute("aria-label", isExpanded ? "Collapse Graph" : (isGlobalView ? "Expand Global Graph" : "Expand Current Graph"));
        expand.classList.remove("is-active");
      }
    }

    if (globalToggle) {
      setGraphButtonIcon(
        globalToggle,
        mobileDrawer ? mobileGlobalGraphIcon : desktopGraphGlobalIcon,
        mobileDrawer ? "global-mobile" : "global-desktop"
      );
      globalToggle.setAttribute("title", mobileDrawer && isGlobalView ? "全局图谱" : "Global Graph");
      globalToggle.setAttribute("aria-label", isGlobalView ? "Global Graph (active)" : "Global Graph");
      globalToggle.classList.toggle("is-active", isGlobalView);
    }
  }

  function scheduleGraphControlSync() {
    syncGraphControls();
    window.requestAnimationFrame?.(() => {
      syncGraphControls();
      window.setTimeout(syncGraphControls, 120);
      window.setTimeout(syncGraphControls, 260);
    });
  }

  function switchMobileGraphMode(mode) {
    const nextGlobalState = mode === "global";
    if ((state.graphMode === "global") === nextGlobalState && !graphContainer?.classList.contains("mod-expanded")) {
      scheduleGraphControlSync();
      return true;
    }
    state.graphMode = nextGlobalState ? "global" : "local";
    setGraphExpanded(false);
    renderGraph();
    scheduleGraphControlSync();
    return true;
  }

  document.querySelector(".graph-global")?.addEventListener("click", (event) => {
    if (isCompactLayout() && rightColumn?.classList.contains("mobile-tools-drawer")) {
      event.preventDefault();
      switchMobileGraphMode("global");
      return;
    }
    state.graphMode = state.graphMode === "global" ? "local" : "global";
    renderGraph();
    scheduleGraphControlSync();
  });

  function setGraphExpanded(expanded) {
    if (!graphContainer) return;
    const modal = graphContainer.closest(".modal-container");
    if (expanded && !modal) {
      graphPlaceholder = document.createComment("codex-memory-graph-placeholder");
      graphContainer.parentNode?.insertBefore(graphPlaceholder, graphContainer);
      const modalContainer = document.createElement("div");
      modalContainer.className = "modal-container";
      const modalBg = document.createElement("div");
      modalBg.className = "modal-bg";
      modalBg.addEventListener("click", () => setGraphExpanded(false));
      modalContainer.appendChild(modalBg);
      modalContainer.appendChild(graphContainer);
      document.body.appendChild(modalContainer);
      graphContainer.classList.add("mod-expanded");
      window.setTimeout(renderGraph, 90);
      scheduleGraphControlSync();
      return;
    }
    if (!expanded && modal) {
      graphContainer.classList.remove("mod-expanded");
      if (graphPlaceholder?.parentNode) {
        graphPlaceholder.parentNode.insertBefore(graphContainer, graphPlaceholder);
        graphPlaceholder.remove();
      }
      graphPlaceholder = null;
      modal.remove();
      window.setTimeout(renderGraph, 90);
      scheduleGraphControlSync();
    }
  }

  document.querySelector(".graph-expand")?.addEventListener("click", (event) => {
    if (isCompactLayout() && rightColumn?.classList.contains("mobile-tools-drawer")) {
      event.preventDefault();
      switchMobileGraphMode("local");
      return;
    }
    setGraphExpanded(!graphContainer?.classList.contains("mod-expanded"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const graphButton = event.target.closest?.(".graph-icon.graph-expand, .graph-icon.graph-global");
    if (!graphButton) return;
    event.preventDefault();
    graphButton.click();
  });

  window.addEventListener("resize", () => {
    renderGraph();
    scheduleGraphControlSync();
  });
  window.codexMemoryDashboard = { openNote, setMainPage, renderGraph, switchMobileGraphMode };
  try {
    window.publish = window.publish || {};
    window.publish.currentFilepath = "现在";
    window.publish.render = window.publish.render || { currentFilepath: "现在" };
    const publishGraph = { renderer: { onResize: renderGraph }, onNavigated: renderGraph };
    Object.defineProperties(publishGraph, {
      global: {
        get() { return state.graphMode === "global"; },
        set(value) {
          state.graphMode = value ? "global" : "local";
          renderGraph();
          scheduleGraphControlSync();
        }
      },
      expanded: {
        get() { return Boolean(graphContainer?.classList.contains("mod-expanded")); },
        set(value) {
          setGraphExpanded(Boolean(value));
        }
      }
    });
    window.publish.graph = publishGraph;
  } catch {
    // The copied Publish shell may expose a read-only graph facade. Keep the
    // private adapter alive through its own event listeners and public handle.
  }

  const initialTheme = (() => {
    try {
      const stored = window.localStorage?.getItem("codex-memory-theme");
      if (stored === "light" || stored === "dark") return stored;
    } catch {
      // Ignore storage failures and fall through to the same media-query driven
      // default used by Publish-like shells.
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  })();
  setTheme(initialTheme, { persist: false });

  const initialNote = paneData[decodeURIComponent(window.location.hash.replace(/^#/, ""))] ? decodeURIComponent(window.location.hash.replace(/^#/, "")) : "now";
  syncResponsiveShell();
  setMainPage(initialNote, { clearPanes: true });
  restoreFooter();
  [0, 120, 500, 1200].forEach((delay) => window.setTimeout(restoreFooter, delay));
  renderGraph();
  scheduleGraphControlSync();
})();
