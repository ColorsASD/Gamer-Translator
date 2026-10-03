(() => {
  const AUTOMATION_SCRIPT_VERSION = "2026-10-03-2";
  const TRUSTED_ORIGINS = new Set(["https://chatgpt.com", "https://chat.openai.com"]);
  const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
  let deliveryInProgress = false;
  let activeDelivery = null;
  const cancelledDeliveryIds = new Set();
  const normalizeDeliveryCallId = (value) => typeof value === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(value) ? value : "";

  function isTrustedPage() {
    return window.top === window && TRUSTED_ORIGINS.has(window.location.origin);
  }

  // A vágólap tartalma csak a kijelölt HTTPS eredet fődokumentumába kerülhet.
  if (!isTrustedPage()) {
    return;
  }
  const FRAME_INTERVAL_MS = 20;
  const SELF_HEAL_CHECK_LIMIT = 5;
  const SUBMISSION_RETRY_GUARD_MS = 2200;
  const FRAME_PACER_BURST_MS = 3000;
  const ASSISTANT_RESPONSE_FOLLOW_UP_IDLE_MS = 15000;
  const ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS = 4000;
  const ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS = 120000;
  const DOM_TEXT_BLOCK_TAGS = new Set([
    "ARTICLE",
    "ASIDE",
    "BLOCKQUOTE",
    "BR",
    "DIV",
    "DL",
    "DT",
    "DD",
    "FIGCAPTION",
    "FIGURE",
    "FOOTER",
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
    "HEADER",
    "HR",
    "LI",
    "MAIN",
    "OL",
    "P",
    "PRE",
    "SECTION",
    "TABLE",
    "TBODY",
    "TD",
    "TH",
    "THEAD",
    "TR",
    "UL"
  ]);
  const DOM_TEXT_SKIP_TAGS = new Set([
    "BUTTON",
    "NOSCRIPT",
    "SCRIPT",
    "STYLE",
    "SVG",
    "TEMPLATE"
  ]);
  const assistantNodeIds = new WeakMap();
  let nextAssistantNodeId = 1;

  function ensureFramePacer() {
    const existingPacer = window.__gamerTranslatorFramePacer;

    if (existingPacer && typeof existingPacer.start === "function") {
      existingPacer.start(FRAME_PACER_BURST_MS);

      if (typeof existingPacer.ensureNode === "function") {
        existingPacer.ensureNode();
      }

      return existingPacer;
    }

    const state = {
      intervalId: null,
      pulseState: false,
      pulseNode: null,
      stopTimeoutId: null
    };

    const ensureNode = () => {
      if (state.pulseNode instanceof HTMLElement && state.pulseNode.isConnected) {
        return state.pulseNode;
      }

      const host = document.body || document.documentElement;

      if (!(host instanceof HTMLElement)) {
        return null;
      }

      const pulseNode = document.createElement("div");
      pulseNode.id = "__gamerTranslatorFramePacer";
      pulseNode.setAttribute("aria-hidden", "true");
      Object.assign(pulseNode.style, {
        position: "fixed",
        right: "0",
        bottom: "0",
        width: "1px",
        height: "1px",
        margin: "0",
        padding: "0",
        border: "0",
        pointerEvents: "none",
        zIndex: "2147483647",
        backgroundColor: "rgba(14, 17, 23, 0.006)",
        opacity: "1",
        transform: "translateZ(0)",
        willChange: "background-color, transform"
      });
      host.appendChild(pulseNode);
      state.pulseNode = pulseNode;
      return pulseNode;
    };

    const tick = () => {
      const pulseNode = ensureNode();

      if (!(pulseNode instanceof HTMLElement)) {
        return;
      }

      state.pulseState = !state.pulseState;
      pulseNode.style.backgroundColor = state.pulseState
        ? "rgba(14, 17, 23, 0.006)"
        : "rgba(18, 22, 29, 0.012)";
      pulseNode.style.transform = state.pulseState
        ? "translateZ(0)"
        : "translate3d(0, 0, 0)";
    };

    const stop = () => {
      if (state.stopTimeoutId !== null) {
        window.clearTimeout(state.stopTimeoutId);
        state.stopTimeoutId = null;
      }

      if (state.intervalId === null) {
        return;
      }

      window.clearInterval(state.intervalId);
      state.intervalId = null;
    };

    const start = (durationMs = FRAME_PACER_BURST_MS) => {
      ensureNode();

      if (state.intervalId === null) {
        tick();
        state.intervalId = window.setInterval(tick, FRAME_INTERVAL_MS);
      }

      const boundedDurationMs = Math.max(FRAME_INTERVAL_MS, Number(durationMs) || FRAME_PACER_BURST_MS);

      if (state.stopTimeoutId !== null) {
        window.clearTimeout(state.stopTimeoutId);
      }

      state.stopTimeoutId = window.setTimeout(() => {
        state.stopTimeoutId = null;
        stop();
      }, boundedDurationMs);
    };

    state.ensureNode = ensureNode;
    state.start = start;
    state.pulseFor = start;
    state.stop = stop;
    window.__gamerTranslatorFramePacer = state;

    document.addEventListener("visibilitychange", () => start(FRAME_PACER_BURST_MS), { passive: true });
    window.addEventListener("pageshow", () => start(FRAME_PACER_BURST_MS), { passive: true });
    return state;
  }

  ensureFramePacer();

  function getDomNodeId(node) {
    if (!(node instanceof Node)) {
      return "";
    }

    const existingId = assistantNodeIds.get(node);

    if (existingId) {
      return existingId;
    }

    const createdId = `assistant-node-${nextAssistantNodeId}`;
    nextAssistantNodeId += 1;
    assistantNodeIds.set(node, createdId);
    return createdId;
  }

  function ensureDomActivityTracker() {
    const existingTracker = window.__gamerTranslatorDomTracker;

    if (existingTracker && typeof existingTracker.start === "function" && typeof existingTracker.waitForChange === "function") {
      existingTracker.start();
      return existingTracker;
    }

    const state = {
      observer: null,
      version: 0,
      listeners: new Set()
    };

    const isInternalTrackerNode = (node) => {
      if (!(node instanceof Node)) {
        return false;
      }

      if (node instanceof Element) {
        return node.id === "__gamerTranslatorFramePacer"
          || Boolean(node.closest("#__gamerTranslatorFramePacer"));
      }

      return isInternalTrackerNode(node.parentNode);
    };

    const hasMeaningfulNode = (nodes) => Array.from(nodes || []).some((node) => !isInternalTrackerNode(node));

    const isMeaningfulMutation = (mutation) => {
      if (!(mutation instanceof MutationRecord)) {
        return false;
      }

      if (mutation.type === "childList") {
        return hasMeaningfulNode(mutation.addedNodes)
          || hasMeaningfulNode(mutation.removedNodes)
          || !isInternalTrackerNode(mutation.target);
      }

      return !isInternalTrackerNode(mutation.target);
    };

    const notifyListeners = () => {
      state.version += 1;

      for (const listener of Array.from(state.listeners)) {
        try {
          listener(state.version);
        } catch (_error) {
          // A tracker listener hibája nem állíthatja meg a többi figyelést.
        }
      }
    };

    const start = () => {
      if (state.observer !== null || !(document.documentElement instanceof HTMLElement) || typeof MutationObserver !== "function") {
        return;
      }

      state.observer = new MutationObserver((mutations) => {
        if (!Array.isArray(mutations) || mutations.length === 0) {
          return;
        }

        if (!mutations.some((mutation) => isMeaningfulMutation(mutation))) {
          return;
        }

        notifyListeners();
      });
      state.observer.observe(document.documentElement, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: [
          "aria-busy",
          "aria-hidden",
          "aria-label",
          "class",
          "data-message-id",
          "data-message-author-role",
          "data-chatgpt-selection-message-id",
          "data-chatgpt-search-message-ids",
          "data-chatgpt-search-unit-key",
          "data-conversation-role",
          "data-turn-id",
          "data-state",
          "data-status",
          "data-testid",
          "disabled",
          "hidden",
          "title"
        ]
      });
    };

    const stop = () => {
      if (state.observer === null) {
        return;
      }

      state.observer.disconnect();
      state.observer = null;
    };

    const waitForChange = (timeoutMs, cancellationPromise = null) => new Promise((resolve) => {
      start();
      ensureFramePacer().pulseFor(Math.min(
        ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS,
        Math.max(FRAME_PACER_BURST_MS, Number(timeoutMs) || FRAME_PACER_BURST_MS)
      ));

      let finished = false;
      let timeoutId = 0;

      const finish = (reason) => {
        if (finished) {
          return;
        }

        finished = true;
        state.listeners.delete(handleChange);

        if (timeoutId) {
          window.clearTimeout(timeoutId);
        }

        resolve(reason);
      };

      const handleChange = () => finish("change");
      if (state.observer !== null) state.listeners.add(handleChange);
      timeoutId = window.setTimeout(() => finish("timeout"), Math.max(FRAME_INTERVAL_MS, timeoutMs));
      if (cancellationPromise) cancellationPromise.then(() => finish("cancelled"));
    });

    const subscribe = (listener) => {
      if (typeof listener !== "function") {
        return () => {};
      }

      start();
      state.listeners.add(listener);

      return () => {
        state.listeners.delete(listener);
      };
    };

    const tracker = {
      start,
      stop,
      subscribe,
      waitForChange,
      getVersion() {
        return state.version;
      }
    };

    window.__gamerTranslatorDomTracker = tracker;
    start();
    return tracker;
  }

  ensureDomActivityTracker();

  function writeProgressEntry(progressCallId, progress) {
    const normalizedProgressCallId = String(progressCallId || "").trim();

    if (!normalizedProgressCallId || !progress || typeof progress !== "object") {
      return;
    }

    window.__gamerTranslatorProgress = window.__gamerTranslatorProgress || Object.create(null);

    let nextSequence = 1;
    const previousEntry = window.__gamerTranslatorProgress[normalizedProgressCallId];

    if (typeof previousEntry === "string" && previousEntry) {
      try {
        const parsedEntry = JSON.parse(previousEntry);
        nextSequence = Number(parsedEntry?.seq || 0) + 1;
      } catch (_error) {
        nextSequence = 1;
      }
    }

    window.__gamerTranslatorProgress[normalizedProgressCallId] = JSON.stringify({
      ...progress,
      seq: nextSequence
    });
  }

  function ensureAssistantResponseFollowUps() {
    window.__gamerTranslatorAssistantResponseFollowUps = window.__gamerTranslatorAssistantResponseFollowUps || Object.create(null);
    return window.__gamerTranslatorAssistantResponseFollowUps;
  }

  // Csak technikai állapot kerül a diagnosztikába, beszélgetés és képtartalom nem.
  function writeDiagnosticEntry(callId, event, fields = {}) {
    const normalizedCallId = String(callId || "").trim();
    if (!/^[A-Za-z0-9_-]{1,120}$/.test(normalizedCallId)) {
      return;
    }
    const safeFields = {};
    const allowedFields = new Set([
      "stage", "reason", "kind", "method", "attempt", "elapsed_ms", "timeout_ms",
      "prompt_length", "image_bytes", "attachment_count", "file_count", "pending",
      "assistant_count", "user_count", "text_length", "fresh", "stable", "has_identity",
      "request_user_bound", "last_user_matches_request", "response_user_matches_request",
      "assistant_identity_new", "user_role_source", "rejection_reason",
      "user_role_candidates", "clickable_image_candidates",
      "auto_submit", "copy_response", "late", "ok"
    ]);
    const bindingBooleanFields = new Set([
      "request_user_bound", "last_user_matches_request", "response_user_matches_request", "assistant_identity_new"
    ]);
    const roleSources = new Set(["none", "message_author", "user_bubble", "conversation_role", "aria_role", "heading_role", "role_conflict"]);
    const rejectionReasons = new Set([
      "none", "request_user_unbound", "last_user_mismatch", "response_user_mismatch", "assistant_identity_old",
      "assistant_text_missing", "assistant_text_transient", "assistant_pending"
    ]);
    for (const [key, value] of Object.entries(fields)) {
      if (!allowedFields.has(key)) continue;
      if (bindingBooleanFields.has(key) && typeof value !== "boolean") continue;
      if (key === "user_role_source" && !roleSources.has(value)) continue;
      if (key === "rejection_reason" && !rejectionReasons.has(value)) continue;
      if (typeof value === "boolean") safeFields[key] = value;
      else if (typeof value === "number" && Number.isFinite(value)) safeFields[key] = Math.max(0, Math.min(100000000, value));
      else if (typeof value === "string" && /^[a-z][a-z0-9_]{0,39}$/.test(value)) safeFields[key] = value;
    }
    window.__gamerTranslatorDiagnostics = window.__gamerTranslatorDiagnostics || Object.create(null);
    const buckets = window.__gamerTranslatorDiagnostics;
    const entries = Array.isArray(buckets[normalizedCallId]) ? buckets[normalizedCallId] : [];
    const nextSequence = Number(entries[entries.length - 1]?.seq || 0) + 1;
    entries.push({ event, fields: safeFields, seq: nextSequence });
    if (entries.length > 100) entries.splice(0, entries.length - 100);
    buckets[normalizedCallId] = entries;
    const keys = Object.keys(buckets);
    for (const oldKey of keys.slice(0, Math.max(0, keys.length - 16))) delete buckets[oldKey];
  }

  function stopAssistantResponseFollowUp(followUpProgressCallId, options = {}) {
    const normalizedFollowUpProgressCallId = String(followUpProgressCallId || "").trim();

    if (!normalizedFollowUpProgressCallId) {
      return;
    }

    const followUps = ensureAssistantResponseFollowUps();
    const existingFollowUp = followUps[normalizedFollowUpProgressCallId];
    let latestText = String(existingFollowUp?.latestText || "");
    let latestComplete = existingFollowUp?.latestComplete === true;

    if (existingFollowUp) {
      existingFollowUp.stopped = true;

      if (existingFollowUp.timeoutId) {
        window.clearTimeout(existingFollowUp.timeoutId);
      }

      if (typeof existingFollowUp.unsubscribe === "function") {
        existingFollowUp.unsubscribe();
      }

      delete followUps[normalizedFollowUpProgressCallId];
    }

    if (options.emitDone !== false) {
      if (!latestText) {
        try {
          const previousProgress = JSON.parse(window.__gamerTranslatorProgress?.[normalizedFollowUpProgressCallId] || "null");
          if (previousProgress?.kind === "assistant_response") {
            latestText = String(previousProgress.text || "");
            latestComplete = previousProgress.complete === true;
          }
        } catch (_error) {
          // A sérült korábbi jelzés nem blokkolhatja a figyelés lezárását.
        }
      }
      writeProgressEntry(normalizedFollowUpProgressCallId, {
        kind: latestText ? "assistant_response" : "assistant_response_watch_done",
        done: true,
        ...(latestText ? { text: latestText, complete: latestComplete } : {})
      });
    }
  }

  window.__gamerTranslatorStopResponseFollowUp = stopAssistantResponseFollowUp;

  if (window.__gamerTranslatorDeliverVersion !== AUTOMATION_SCRIPT_VERSION) {
    const previousAssistantResponseFollowUps = ensureAssistantResponseFollowUps();
    const previousComposerAutoRecovery = window.__gamerTranslatorComposerAutoRecovery;

    for (const followUpProgressCallId of Object.keys(previousAssistantResponseFollowUps)) {
      stopAssistantResponseFollowUp(followUpProgressCallId, { emitDone: false });
    }

    if (previousComposerAutoRecovery && typeof previousComposerAutoRecovery === "object") {
      previousComposerAutoRecovery.suspendedCount = Number.MAX_SAFE_INTEGER;

      if (typeof previousComposerAutoRecovery.destroy === "function") {
        previousComposerAutoRecovery.destroy();
      } else if (typeof previousComposerAutoRecovery.unsubscribe === "function") {
        previousComposerAutoRecovery.unsubscribe();
      }
    }

    window.__gamerTranslatorComposerAutoRecovery = null;
  }

  if (
    typeof window.__gamerTranslatorDeliver === "function"
    && window.__gamerTranslatorDeliverVersion === AUTOMATION_SCRIPT_VERSION
  ) {
    try {
      window.__gamerTranslatorDeliver({
        initializeComposerAutoRecovery: true,
        autoSubmit: false,
        copyResponseToClipboard: false,
        pageReadyTimeoutMs: 15000,
        responseTimeoutMs: 0
      }).catch(() => {});
    } catch (_error) {
      // Ha a korabbi automatikus inicializalas mar fut, nem blokkolhatja az ujrabekotest.
    }

    return;
  }

  window.__gamerTranslatorIsDeliveryCancelled = (callId) => cancelledDeliveryIds.has(normalizeDeliveryCallId(callId));
  window.__gamerTranslatorCancelDelivery = (callId) => {
    const normalizedCallId = normalizeDeliveryCallId(callId);
    if (!normalizedCallId) return { ok: false, cancelled: false, active: false };
    cancelledDeliveryIds.add(normalizedCallId);
    while (cancelledDeliveryIds.size > 256) cancelledDeliveryIds.delete(cancelledDeliveryIds.values().next().value);
    const operation = activeDelivery;
    const wasActive = Boolean(operation && operation.callId === normalizedCallId);
    if (wasActive) operation.cancel();
    return { ok: true, cancelled: true, active: wasActive };
  };

  window.__gamerTranslatorDeliver = async function deliverPromptToChatGpt(payload) {
    if (!isTrustedPage()) {
      return { ok: false, error: "Az oldal eredete nem engedélyezett." };
    }

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return { ok: false, error: "A küldési adatok formátuma hibás." };
    }

    const initializesWatcher = payload.initializeComposerAutoRecovery === true;
    const deliveryCallId = normalizeDeliveryCallId(payload.deliveryCallId);
    if (payload.deliveryCallId != null && !deliveryCallId) {
      return { ok: false, error: "A küldés azonosítója hibás." };
    }
    if (deliveryCallId && cancelledDeliveryIds.has(deliveryCallId)) {
      return { ok: false, cancelled: true, error: "A küldés megszakítva lett." };
    }

    // Két átfedő küldés összekeverhetné a promptot, a képet és a választ.
    if (!initializesWatcher && deliveryInProgress) {
      writeDiagnosticEntry(payload.diagnosticCallId, "delivery_rejected", { reason: "delivery_busy" });
      return { ok: false, error: "Már folyamatban van egy küldés." };
    }

    if ((payload.prompt != null && typeof payload.prompt !== "string")
      || (payload.imageDataUrl != null && typeof payload.imageDataUrl !== "string")) {
      return { ok: false, error: "A prompt és a kép csak szöveges adat lehet." };
    }

    payload = {
      ...payload,
      initializeComposerAutoRecovery: initializesWatcher,
      autoSubmit: payload.autoSubmit === true,
      copyResponseToClipboard: payload.copyResponseToClipboard === true && payload.autoSubmit === true,
      waitForResponse: (payload.waitForResponse === true || payload.copyResponseToClipboard === true) && payload.autoSubmit === true,
      pageReadyTimeoutMs: Math.min(120000, Math.max(20, Number(payload.pageReadyTimeoutMs) || 25000)),
      responseTimeoutMs: Math.min(600000, Math.max(0, Number(payload.responseTimeoutMs) || 0))
    };

    const composerAutoRecovery = ensureComposerAutoRecoveryWatcher();
    const deliveryStartedAt = Date.now();
    let deliveryStage = "initialization";
    let assistantSnapshotBeforeSend = null;
    let responseBaselineCaptured = false;
    const reportDiagnostic = (event, fields = {}) => writeDiagnosticEntry(payload.diagnosticCallId, event, fields);
    const reportProgress = (progress) => {
      writeProgressEntry(payload.progressCallId, progress);
    };
    const shouldSuspendComposerAutoRecovery = !payload.initializeComposerAutoRecovery;
    let resolveCancellation;
    const operation = {
      callId: deliveryCallId, cancelled: false, released: false,
      cancellationPromise: new Promise((resolve) => { resolveCancellation = resolve; }),
      release() {
        if (operation.released || !shouldSuspendComposerAutoRecovery) return;
        operation.released = true;
        // Egy korábban megszakított finally nem oldhatja fel az új kérés zárát.
        if (activeDelivery === operation) {
          activeDelivery = null;
          deliveryInProgress = false;
          composerAutoRecovery.suspendedCount = Math.max(0, composerAutoRecovery.suspendedCount - 1);
          composerAutoRecovery.requestEvaluation();
        }
      },
      cancel() {
        if (operation.cancelled) return;
        operation.cancelled = true;
        resolveCancellation();
        reportDiagnostic("delivery_cancelled", { stage: deliveryStage, ok: true });
        operation.release();
      }
    };
    const assertDeliveryActive = () => {
      if (operation.cancelled) throw new Error("A küldés megszakítva lett.");
    };

    if (shouldSuspendComposerAutoRecovery) {
      deliveryInProgress = true;
      activeDelivery = operation;
      composerAutoRecovery.suspendedCount += 1;
    }

    try {
      if (payload.initializeComposerAutoRecovery) {
        composerAutoRecovery.requestEvaluation();
        return {
          ok: true,
          composerAutoRecoveryReady: true
        };
      }

      if (!payload.prompt && !payload.imageDataUrl && !payload.repairExistingComposerPayload) {
        throw new Error("Nincs elküldhető tartalom.");
      }

      for (const followUpCallId of Object.keys(ensureAssistantResponseFollowUps())) {
        stopAssistantResponseFollowUp(followUpCallId);
      }
      reportDiagnostic("delivery_started", { prompt_length: String(payload.prompt || "").length, auto_submit: payload.autoSubmit, copy_response: payload.copyResponseToClipboard });

      assistantSnapshotBeforeSend = payload.waitForResponse
        ? captureAssistantSnapshot()
        : { count: 0, lastNodeId: "", lastText: "", lastPending: false };

      deliveryStage = "composer";
      let activeComposer = await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "beviteli mező");
      assertDeliveryActive();
      reportDiagnostic("composer_ready");

      if (payload.repairExistingComposerPayload && !payload.prompt && !payload.imageDataUrl) {
        if (payload.autoSubmit) {
          await submitExistingComposerPayload(activeComposer);
          assertDeliveryActive();
        }

        return {
          ok: true,
          assistantResponseText: "",
          assistantResponseCopied: false,
          followUpProgressCallId: ""
        };
      }

      if (payload.imageDataUrl) {
        deliveryStage = "attachment";
        activeComposer = await attachImage(activeComposer);
        assertDeliveryActive();
      }

      if (payload.prompt) {
        deliveryStage = "prompt";
        activeComposer = await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "frissített beviteli mező");
        assertDeliveryActive();
        writePrompt(activeComposer, payload.prompt);
        activeComposer = await waitForPromptApplied(
          activeComposer,
          payload.prompt,
          Math.min(payload.pageReadyTimeoutMs, 1800)
        );
        assertDeliveryActive();
        reportDiagnostic("prompt_verified", { prompt_length: payload.prompt.length });
      }

      if (payload.autoSubmit) {
        deliveryStage = "submission";
        reportDiagnostic("submission_started", { kind: payload.imageDataUrl ? "image" : "text" });
        if (payload.imageDataUrl && !payload.prompt) {
          await submitImageMessage(activeComposer);
        } else {
          await submitTextMessage(activeComposer);
        }
        assertDeliveryActive();
        reportDiagnostic("submission_confirmed");
      }

      let assistantResponseText = "";
      let followUpProgressCallId = "";

      if (payload.waitForResponse) {
        deliveryStage = "response";
        const responseResult = await waitForAssistantResponse(assistantSnapshotBeforeSend, payload.responseTimeoutMs, reportProgress);
        assertDeliveryActive();
        assistantResponseText = responseResult.text;
        followUpProgressCallId = String(responseResult.followUpProgressCallId || "").trim();
        if (responseResult.responsePending) {
          return { ok: false, error: "A ChatGPT válasza nem érkezett meg időben.", responsePending: true, followUpProgressCallId };
        }
      }

      reportDiagnostic("delivery_finished", { ok: true, elapsed_ms: Date.now() - deliveryStartedAt });

      return {
        ok: true,
        assistantResponseText,
        assistantResponseComplete: Boolean(assistantResponseText),
        assistantResponseCopied: false,
        followUpProgressCallId
      };
    } catch (error) {
      reportDiagnostic("delivery_failed", { stage: deliveryStage, elapsed_ms: Date.now() - deliveryStartedAt });
      return {
        ok: false,
        ...(operation.cancelled ? { cancelled: true } : {}),
        error: error instanceof Error ? error.message : String(error)
      };
    } finally {
      operation.release();
    }

    async function attachImage(composerCandidate) {
      let composer = composerCandidate ?? await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "beviteli mező képbeillesztéshez");
      assertDeliveryActive();
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const file = dataUrlToFile(payload.imageDataUrl, payload.imageFilename || "snip.png", payload.imageMimeType || "image/png");
      const expectedFileKey = describeSelectedFile(file);
      const beforeSnapshot = captureComposerAttachmentSnapshot(composer);
      reportDiagnostic("attachment_started", { image_bytes: file.size, timeout_ms: imageUploadTimeoutMs });

      // Egy korábbi csatolmányhoz nem adunk új képet és nem küldjük el véletlenül.
      if (beforeSnapshot.hasAttachmentPreview || Number(beforeSnapshot.fileInputCount) > 0 || beforeSnapshot.hasPendingAttachmentWork) {
        reportDiagnostic("attachment_failed", { reason: "existing_attachment" });
        throw new Error("A beviteli mezőben már van csatolmány vagy folyamatban levő feltöltés. Töröld azt az új kép beillesztése előtt.");
      }

      const methods = ["input", "drop"];
      for (let attempt = 0; attempt < methods.length; attempt += 1) {
        assertDeliveryActive();
        composer = findComposer() || composer;
        const method = methods[attempt];
        const started = method === "input" ? attachViaFileInput(composer, file) : attachViaDrop(composer, file);
        reportDiagnostic("attachment_attempt", { method, attempt: attempt + 1, ok: started });
        if (!started) continue;

        // Az input.files saját beállítása nem bizonyít feltöltést. A teljes
        // várakozás lejártáig nincs második drop, így a lassú oldal nem dupláz képet.
        const attachedComposer = await waitForAttachmentReady(composer, beforeSnapshot, imageUploadTimeoutMs, expectedFileKey);
        assertDeliveryActive();
        if (attachedComposer) {
          reportDiagnostic("attachment_ready", { method, attempt: attempt + 1 });
          return attachedComposer;
        }
        const finalSnapshot = captureComposerAttachmentSnapshot(findComposer() || composer);
        reportDiagnostic("attachment_timeout", { method, attempt: attempt + 1, attachment_count: finalSnapshot.attachmentCount, file_count: finalSnapshot.fileInputCount, pending: finalSnapshot.hasPendingAttachmentWork });
        if (finalSnapshot.hasAttachmentPreview || finalSnapshot.hasPendingAttachmentWork) break;
      }
      clearUnconfirmedImageFileSelection(findComposer() || composer, expectedFileKey);
      throw new Error("A kép feldolgozását a ChatGPT nem igazolta vissza időben. Ellenőrizd a csatolmányt az oldalon.");
    }

    function clearUnconfirmedImageFileSelection(composer, expectedFileKey) {
      assertDeliveryActive();
      const snapshot = captureComposerAttachmentSnapshot(composer);
      if (snapshot.hasAttachmentPreview || snapshot.hasPendingAttachmentWork) return;
      const scope = findComposerScope(composer);
      const inputs = new Set([
        ...Array.from(scope?.querySelectorAll('input[type="file"]') || []),
        findFileInput(document)
      ]);
      for (const input of inputs) {
        if (!(input instanceof HTMLInputElement) || input.files?.length !== 1) continue;
        if (describeSelectedFile(input.files[0]) !== expectedFileKey) continue;
        try {
          // Csak a saját, vissza nem igazolt próbálkozás maradványát töröljük.
          // A change esemény új feltöltést indíthatna, ezért nem küldünk eseményt.
          input.value = "";
          reportDiagnostic("attachment_selection_cleared", { ok: !input.files?.length });
        } catch (_error) {
          reportDiagnostic("attachment_selection_cleared", { ok: false });
        }
      }
    }

    function getImageUploadTimeoutMs() {
      return Math.min(60000, Math.max(20, Number(payload.pageReadyTimeoutMs) || 25000));
    }

    function attachViaFileInput(composer, file) {
      assertDeliveryActive();
      const scope = findComposerScope(composer);
      const fileInput = findFileInput(scope) || findFileInput(document);

      if (!(fileInput instanceof HTMLInputElement)) {
        return false;
      }

      const transfer = new DataTransfer();
      transfer.items.add(file);
      try {
        fileInput.value = "";
      } catch (_error) {
        // Nem minden böngésző engedi a value közvetlen törlését.
      }
      fileInput.files = transfer.files;
      fileInput.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      assertDeliveryActive();
      fileInput.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      return true;
    }

    function attachViaDrop(composer, file) {
      assertDeliveryActive();
      const target = findComposerScope(composer) || composer;

      if (!(target instanceof HTMLElement)) {
        return false;
      }

      const transfer = new DataTransfer();
      transfer.items.add(file);

      target.dispatchEvent(new DragEvent("dragenter", { bubbles: true, cancelable: true, dataTransfer: transfer }));
      assertDeliveryActive();
      target.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: transfer }));
      assertDeliveryActive();
      target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
      return true;
    }

    function findFileInput(scope) {
      if (!(scope instanceof Element || scope instanceof Document)) {
        return null;
      }

      return Array.from(scope.querySelectorAll('input[type="file"]')).find((input) => {
        if (!(input instanceof HTMLInputElement) || input.disabled) {
          return false;
        }

        const accept = String(input.getAttribute("accept") || "").toLowerCase();
        return !accept || accept.includes("image") || accept.includes("*/*");
      }) || null;
    }

    function dataUrlToFile(dataUrl, filename, mimeType) {
      const match = /^data:(image\/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/]+={0,2})$/i.exec(String(dataUrl || ""));

      if (!match) {
        throw new Error("A kép adatURL formátuma hibás.");
      }

      const [, declaredMimeType, encoded] = match;

      if (mimeType && String(mimeType).toLowerCase() !== declaredMimeType.toLowerCase()) {
        throw new Error("A kép MIME-típusa nem egyezik az adatURL típusával.");
      }

      // A korlát dekódolás előtt is érvényesül, így a base64 nem foglalhat korlátlan memóriát.
      if (encoded.length > Math.ceil(MAX_IMAGE_BYTES / 3) * 4) {
        throw new Error("A kép mérete legfeljebb 20 MiB lehet.");
      }

      const binary = atob(encoded);

      if (!binary.length || binary.length > MAX_IMAGE_BYTES) {
        throw new Error("A kép mérete legfeljebb 20 MiB lehet.");
      }

      const bytes = new Uint8Array(binary.length);

      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }

      return new File([bytes], filename, {
        type: declaredMimeType.toLowerCase(),
        lastModified: Date.now()
      });
    }

    async function submitTextMessage(composer, options = {}) {
      const liveComposer = await waitFor(() => findComposer() || composer, 15000, "beviteli mező");
      assertDeliveryActive();
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const requireReadyAttachment = Boolean(options.requireReadyAttachment ?? payload.imageDataUrl);
      const preparedComposer = await waitFor(() => {
        const candidate = findComposer() || liveComposer;
        const promptReady = Boolean(normalizePromptStructure(readComposerText(candidate)));
        const sendButton = findSendButton(candidate);

        if (!isComposerReadyForSubmit(candidate) || !promptReady
          || !(sendButton instanceof HTMLButtonElement) || isGenerationInProgress()) {
          return null;
        }

        if (payload.prompt && normalizePromptStructure(readComposerText(candidate)) !== normalizePromptStructure(payload.prompt)) {
          return null;
        }

        if (requireReadyAttachment && !isImageReadyForSubmit(candidate)) {
          return null;
        }

        return candidate;
      }, requireReadyAttachment ? imageUploadTimeoutMs : 12000, "beküldhető tartalom");
      assertDeliveryActive();
      const beforeState = captureComposerSubmitState(preparedComposer);
      const expandedEditorMode = isExpandedComposerEditor(preparedComposer);
      const attempts = [];

      attempts.push({
        timeoutMs: 450,
        run(targetComposer) {
          const liveTargetComposer = findComposer() || targetComposer;
          const liveForm = findClosestForm(liveTargetComposer);

          if (!(liveForm instanceof HTMLFormElement)) {
            return;
          }

          if (typeof liveForm.requestSubmit === "function") {
            captureResponseBaselineBeforeSubmit();
            liveForm.requestSubmit();
            return;
          }

          dispatchFormSubmit(liveForm);
        }
      });
      attempts.push({
        timeoutMs: 350,
        run(targetComposer) {
          const liveTargetComposer = findComposer() || targetComposer;
          const liveForm = findClosestForm(liveTargetComposer);

          if (!(liveForm instanceof HTMLFormElement)) {
            return;
          }

          dispatchFormSubmit(liveForm);
        }
      });

      if (!expandedEditorMode) {
        attempts.push({
          timeoutMs: 350,
          run(targetComposer) {
            const liveTargetComposer = findComposer() || targetComposer;
            liveTargetComposer.focus();
            dispatchEnterSequence(liveTargetComposer);
          }
        });
      }

      attempts.push({
        timeoutMs: 550,
        run(targetComposer) {
          const liveTargetComposer = findComposer() || targetComposer;
          const liveSendButton = findSendButton(liveTargetComposer);

          if (liveSendButton instanceof HTMLButtonElement) {
            fireClickSequence(liveSendButton);
          }
        }
      });

      await ensureSubmissionDelivered(
        preparedComposer,
        beforeState,
        attempts,
        "A tartalom bekerült, de a beküldést nem tudtam elindítani.",
      );
    }

    async function submitExistingComposerPayload(composerCandidate) {
      const liveComposer = await waitFor(() => findComposer() || composerCandidate, 15000, "beviteli mező");
      assertDeliveryActive();
      let currentState = captureComposerSubmitState(liveComposer);

      if (!hasComposerPayloadState(currentState)) {
        return;
      }

      if (currentState.hasPendingAttachmentWork) {
        const awaitedComposer = await waitFor(() => {
          const candidate = findComposer() || liveComposer;
          const candidateState = captureComposerSubmitState(candidate);
          return hasComposerPayloadState(candidateState) && !candidateState.hasPendingAttachmentWork
            ? candidate
            : null;
        }, getImageUploadTimeoutMs(), "beküldhető composer tartalom");
        assertDeliveryActive();

        currentState = captureComposerSubmitState(awaitedComposer);
      }

      const preparedComposer = findComposer() || liveComposer;
      currentState = captureComposerSubmitState(preparedComposer);
      const hasTextPayload = Boolean(normalizePromptStructure(currentState.composerText));
      const hasAttachmentPayload = hasAttachmentSnapshot(currentState);

      if (!hasTextPayload && !hasAttachmentPayload) {
        return;
      }

      if (hasTextPayload) {
        await submitTextMessage(preparedComposer, {
          requireReadyAttachment: hasAttachmentPayload
        });
        return;
      }

      await submitImageMessage(preparedComposer);
    }

    async function submitImageMessage(composer) {
      const liveComposer = await waitFor(() => findComposer() || composer, 15000, "beviteli mező");
      assertDeliveryActive();
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const preparedComposer = await waitFor(() => {
        const candidate = findComposer() || liveComposer;
        return isImageReadyForSubmit(candidate) ? candidate : null;
      }, imageUploadTimeoutMs, "feltöltött kép");
      assertDeliveryActive();
      const beforeState = captureComposerSubmitState(preparedComposer);
      const attempts = [];

      attempts.push({
        timeoutMs: 1000,
        run(targetComposer) {
          const liveTargetComposer = findComposer() || targetComposer;
          const liveSendButton = findSendButton(liveTargetComposer);

          if (liveSendButton instanceof HTMLButtonElement) {
            fireClickSequence(liveSendButton);
          }
        }
      });

      attempts.push({
        timeoutMs: 650,
        run(targetComposer) {
          const liveTargetComposer = findComposer() || targetComposer;
          const liveForm = findClosestForm(liveTargetComposer);

          if (!(liveForm instanceof HTMLFormElement)) {
            return;
          }

          if (typeof liveForm.requestSubmit === "function") {
            captureResponseBaselineBeforeSubmit();
            liveForm.requestSubmit();
            return;
          }

          dispatchFormSubmit(liveForm);
        }
      });
      attempts.push({
        timeoutMs: 500,
        run(targetComposer) {
          const liveTargetComposer = findComposer() || targetComposer;
          const liveForm = findClosestForm(liveTargetComposer);

          if (!(liveForm instanceof HTMLFormElement)) {
            return;
          }

          dispatchFormSubmit(liveForm);
        }
      });

      await ensureSubmissionDelivered(
        preparedComposer,
        beforeState,
        attempts,
        "A kép csatolva maradt, de a beküldést nem tudtam elindítani.",
      );
    }

    function writePrompt(element, prompt) {
      assertDeliveryActive();
      element.focus();
      const hasMultilinePrompt = String(prompt || "").includes("\n");

      if (element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement) {
        const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");

        descriptor?.set?.call(element, prompt);
        dispatchComposerInput(element, prompt, hasMultilinePrompt);
        element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
        return;
      }

      if (element.isContentEditable) {
        const selection = window.getSelection();
        const range = document.createRange();

        range.selectNodeContents(element);
        selection?.removeAllRanges();
        selection?.addRange(range);

        let inserted = false;

        if (!hasMultilinePrompt) {
          try {
            inserted = document.execCommand("insertText", false, prompt);
          } catch (_error) {
            inserted = false;
          }
        }

        if (!inserted || normalizePromptStructure(readComposerText(element)) !== normalizePromptStructure(prompt)) {
          setContentEditablePrompt(element, prompt);
        }

        dispatchComposerInput(element, prompt, hasMultilinePrompt);
        element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
        return;
      }

      throw new Error("A talált beviteli mező típusa nem támogatott.");
    }

    function readComposerText(element) {
      if (!(element instanceof HTMLElement)) {
        return "";
      }

      if (element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement) {
        return String(element.value || "");
      }

      const paragraphs = Array.from(element.childNodes);

      if (paragraphs.length > 0 && paragraphs.every((node) => node instanceof HTMLElement && node.tagName === "P")) {
        // A beillesztett prompt üres sorai önálló bekezdések; ezeket a válaszok
        // általános DOM-normalizálása nem vonhatja össze az ellenőrzés előtt.
        return paragraphs.map((paragraph) => normalizeStructuredDomText(readStructuredDomText(paragraph))).join("\n");
      }

      const structuredText = normalizeStructuredDomText(readStructuredDomText(element));

      if (structuredText) {
        return structuredText;
      }

      return String(element.textContent || "");
    }

    async function waitForPromptApplied(composer, prompt, timeoutMs) {
      assertDeliveryActive();
      const expectedPrompt = normalizePromptStructure(prompt);

      if (!expectedPrompt) {
        return findComposer() || composer;
      }

      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        assertDeliveryActive();
        const liveComposer = findComposer() || composer;
        const currentPrompt = normalizePromptStructure(readComposerText(liveComposer));

        if (currentPrompt === expectedPrompt) {
          return liveComposer;
        }

        await waitForNextStateTurn(timeoutMs - (Date.now() - startedAt));
      }

      const finalComposer = findComposer() || composer;

      if (normalizePromptStructure(readComposerText(finalComposer)) === expectedPrompt) {
        return finalComposer;
      }

      // Részleges vagy visszaállított bevitelt nem szabad sikeresnek tekinteni és elküldeni.
      throw new Error("A teljes prompt beillesztése nem sikerült; a tartalom nem lett elküldve.");
    }

    function setContentEditablePrompt(element, prompt) {
      const normalizedPrompt = String(prompt || "").replace(/\r\n?/g, "\n");
      const lines = normalizedPrompt.split("\n");
      const fragment = document.createDocumentFragment();

      lines.forEach((line) => {
        const paragraph = document.createElement("p");

        if (line) {
          paragraph.appendChild(document.createTextNode(line));
        } else {
          paragraph.appendChild(document.createElement("br"));
        }

        fragment.appendChild(paragraph);
      });

      if (lines.length === 0) {
        const paragraph = document.createElement("p");
        paragraph.appendChild(document.createElement("br"));
        fragment.appendChild(paragraph);
      }

      element.replaceChildren(fragment);

      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(element);
      range.collapse(false);
      selection?.removeAllRanges();
      selection?.addRange(range);
    }

    function dispatchComposerInput(element, prompt, hasMultilinePrompt) {
      const inputType = hasMultilinePrompt ? "insertFromPaste" : "insertText";
      const data = hasMultilinePrompt ? null : prompt;

      try {
        element.dispatchEvent(
          new InputEvent("beforeinput", {
            bubbles: true,
            composed: true,
            data,
            inputType
          })
        );
      } catch (_error) {
        // A beforeinput itt csak kompatibilitási fallback, hiba esetén megyünk tovább.
      }

      try {
        element.dispatchEvent(
          new InputEvent("input", {
            bubbles: true,
            composed: true,
            data,
            inputType
          })
        );
        return;
      } catch (_error) {
        element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      }
    }

    function findComposer() {
      const selectorWeights = [
        ["#prompt-textarea", 5000],
        ['[data-testid="prompt-textarea"]', 4800],
        ["textarea", 3200],
        ['[role="textbox"]', 2500],
        ['[contenteditable="true"]', 1800]
      ];
      const candidateWeights = new Map();

      for (const [selector, weight] of selectorWeights) {
        for (const element of document.querySelectorAll(selector)) {
          const previousWeight = candidateWeights.get(element) || 0;

          if (weight > previousWeight) {
            candidateWeights.set(element, weight);
          }
        }
      }

      const candidates = Array.from(candidateWeights.entries())
        .map(([element, weight]) => ({ element, weight }))
        .filter(({ element }) => isComposerElement(element))
        .sort((left, right) => scoreComposerCandidate(right.element, right.weight) - scoreComposerCandidate(left.element, left.weight));

      return candidates[0]?.element || null;
    }

    function isComposerElement(element) {
      if (!(element instanceof HTMLElement) || !isDomAccessibleElement(element)) {
        return false;
      }

      if (element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement) {
        return !element.disabled && !element.readOnly;
      }

      return element.isContentEditable;
    }

    function scoreComposerCandidate(element, selectorWeight) {
      if (!(element instanceof HTMLElement)) {
        return Number.NEGATIVE_INFINITY;
      }

      const scope = findComposerScope(element);
      const form = findClosestForm(element);
      const activeElementBonus = document.activeElement === element ? 240 : 0;
      const promptSelectorBonus = element.id === "prompt-textarea" || element.getAttribute("data-testid") === "prompt-textarea" ? 1600 : 0;
      const textAreaBonus = element instanceof HTMLTextAreaElement ? 520 : 0;
      const contentEditableBonus = element.isContentEditable ? 360 : 0;
      const scopeFileInputBonus = scopeHasLikelyFileInput(scope) ? 280 : 0;
      const formBonus = form instanceof HTMLFormElement ? 240 : 0;
      const conversationPenalty = element.closest('[data-testid^="conversation-turn-"], article') ? 3200 : 0;
      const hiddenPenalty = isDomAccessibleElement(element) ? 0 : 2800;

      return selectorWeight
        + activeElementBonus
        + promptSelectorBonus
        + textAreaBonus
        + contentEditableBonus
        + scopeFileInputBonus
        + formBonus
        - conversationPenalty
        - hiddenPenalty;
    }

    function scopeHasLikelyFileInput(scope) {
      if (!(scope instanceof Element)) {
        return false;
      }

      return Boolean(scope.querySelector('input[type="file"]'));
    }

    function captureComposerAttachmentSnapshot(composer) {
      const scope = findComposerScope(composer);
      const attachmentIndicators = collectAttachmentIndicators(scope);
      const selectedFileKeys = collectSelectedFileKeys(scope);
      const sendButton = findSendButton(composer, { allowDisabled: true });
      const hasAttachmentPreview = attachmentIndicators.some((element) => (
        (element instanceof HTMLImageElement && Boolean(element.currentSrc || element.getAttribute("src")))
        || Boolean(element.querySelector('img[src]'))
      ));

      return {
        attachmentCount: attachmentIndicators.length,
        attachmentIndicatorKey: attachmentIndicators.map((element) => describeAttachmentIndicator(element)).join("||"),
        fileInputCount: selectedFileKeys.length,
        fileSelectionKey: selectedFileKeys.join("||"),
        selectedFileKeys,
        hasAttachmentPreview,
        sendButtonDisabled: sendButton instanceof HTMLButtonElement && sendButton.disabled,
        hasPendingAttachmentWork: hasPendingAttachmentWork(scope),
      };
    }

    function captureComposerSubmitState(composer) {
      const liveComposer = findComposer() || composer;
      const scope = findComposerScope(liveComposer);
      const attachmentCount = countAttachmentIndicators(scope);
      const fileInputCount = countSelectedFiles(scope);
      const userMessages = findUserMessageNodes();
      const assistantMessages = findAssistantMessageNodes();
      const lastUserMessage = userMessages.at(-1) || null;
      const lastAssistantMessage = assistantMessages.at(-1) || null;
      const sendButton = findSendButton(liveComposer, { allowDisabled: true });
      const sendButtonLabel = sendButton instanceof HTMLButtonElement ? readButtonLabel(sendButton) : "";

      return {
        composerText: normalizePromptStructure(readComposerText(liveComposer)),
        attachmentCount,
        fileInputCount,
        hasPendingAttachmentWork: hasPendingAttachmentWork(scope),
        userCount: userMessages.length,
        lastUserNodeId: lastUserMessage ? getDomNodeId(lastUserMessage) : "",
        assistantCount: assistantMessages.length,
        lastAssistantNodeId: lastAssistantMessage ? getDomNodeId(lastAssistantMessage) : "",
        lastAssistantPending: lastAssistantMessage ? isAssistantResponsePending(lastAssistantMessage) : false,
        sendButtonDisabled: sendButton instanceof HTMLButtonElement ? sendButton.disabled : false,
        sendButtonLabel,
        sendButtonIsNonSend: sendButton instanceof HTMLButtonElement ? looksLikeNonSendAction(sendButtonLabel) : false
      };
    }

    function getAssistantSnapshotKey(snapshot) {
      if (!snapshot || typeof snapshot !== "object") {
        return "";
      }

      return [
        Number(snapshot.count) || 0,
        String(snapshot.lastNodeId || ""),
        String(snapshot.lastStableId || ""),
        String(snapshot.lastUserKey || ""),
        String(snapshot.responseUserKey || ""),
        String(snapshot.lastText || ""),
        snapshot.lastPending ? "1" : "0",
        snapshot.generationPending ? "1" : "0"
      ].join("|");
    }

    function getAttachmentSnapshotKey(snapshot) {
      if (!snapshot || typeof snapshot !== "object") {
        return "";
      }

      return [
        Number(snapshot.attachmentCount) || 0,
        String(snapshot.attachmentIndicatorKey || ""),
        Number(snapshot.fileInputCount) || 0,
        String(snapshot.fileSelectionKey || ""),
        snapshot.hasAttachmentPreview ? "1" : "0",
        snapshot.sendButtonDisabled ? "1" : "0",
        snapshot.hasPendingAttachmentWork ? "1" : "0"
      ].join("|");
    }

    function getSubmissionStateKey(state) {
      if (!state || typeof state !== "object") {
        return "";
      }

      return [
        String(state.composerText || ""),
        Number(state.attachmentCount) || 0,
        Number(state.fileInputCount) || 0,
        state.hasPendingAttachmentWork ? "1" : "0",
        Number(state.userCount) || 0,
        String(state.lastUserNodeId || ""),
        Number(state.assistantCount) || 0,
        String(state.lastAssistantNodeId || ""),
        state.lastAssistantPending ? "1" : "0",
        state.sendButtonDisabled ? "1" : "0",
        String(state.sendButtonLabel || ""),
        state.sendButtonIsNonSend ? "1" : "0"
      ].join("|");
    }

    function ensureSubmissionRetryGuard() {
      const existingGuard = window.__gamerTranslatorSubmissionRetryGuard;

      if (
        existingGuard
        && typeof existingGuard === "object"
        && typeof existingGuard.arm === "function"
        && typeof existingGuard.getRemainingMs === "function"
        && typeof existingGuard.clear === "function"
      ) {
        return existingGuard;
      }

      const guardState = {
        payloadKey: "",
        activeUntil: 0,
        arm(composerCandidate, submissionStateCandidate) {
          const composer = findComposer() || composerCandidate;
          const submissionState = submissionStateCandidate || captureComposerSubmitState(composer);
          const payloadKey = getComposerAutoRecoveryPayloadKey(submissionState);

          if (!payloadKey) {
            guardState.clear();
            return;
          }

          guardState.payloadKey = payloadKey;
          guardState.activeUntil = Date.now() + SUBMISSION_RETRY_GUARD_MS;
        },
        getRemainingMs(composerCandidate, submissionStateCandidate) {
          if (Date.now() >= guardState.activeUntil) {
            guardState.clear();
            return 0;
          }

          const composer = findComposer() || composerCandidate;

          if (!(composer instanceof HTMLElement)) {
            guardState.clear();
            return 0;
          }

          const submissionState = submissionStateCandidate || captureComposerSubmitState(composer);
          const payloadKey = getComposerAutoRecoveryPayloadKey(submissionState);

          if (!payloadKey || payloadKey !== guardState.payloadKey) {
            guardState.clear();
            return 0;
          }

          return Math.max(0, guardState.activeUntil - Date.now());
        },
        clear() {
          guardState.payloadKey = "";
          guardState.activeUntil = 0;
        }
      };

      window.__gamerTranslatorSubmissionRetryGuard = guardState;
      return guardState;
    }

    function armSubmissionRetryGuard(composerCandidate, submissionStateCandidate) {
      ensureSubmissionRetryGuard().arm(composerCandidate, submissionStateCandidate);
    }

    function getSubmissionRetryGuardRemainingMs(composerCandidate, submissionStateCandidate) {
      return ensureSubmissionRetryGuard().getRemainingMs(composerCandidate, submissionStateCandidate);
    }

    function isSubmissionRetryGuardActive(composerCandidate, submissionStateCandidate) {
      return getSubmissionRetryGuardRemainingMs(composerCandidate, submissionStateCandidate) > 0;
    }

    function clearSubmissionRetryGuard() {
      ensureSubmissionRetryGuard().clear();
    }

    function hasAttachmentSnapshot(snapshot) {
      if (!snapshot || typeof snapshot !== "object") {
        return false;
      }

      return Number(snapshot.attachmentCount) > 0 || Number(snapshot.fileInputCount) > 0;
    }

    function isAttachmentReadySnapshot(snapshot) {
      return Number(snapshot?.attachmentCount) > 0 && snapshot.hasAttachmentPreview === true
        && !snapshot.hasPendingAttachmentWork && !snapshot.sendButtonDisabled;
    }

    async function waitForAttachmentReady(composer, beforeSnapshot, timeoutMs, expectedFileKey) {
      assertDeliveryActive();
      let observedSnapshot = beforeSnapshot;
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const liveComposer = findComposer() || composer;

        if (isExpectedAttachmentReadySnapshot(observedSnapshot, beforeSnapshot, expectedFileKey)) {
          return liveComposer;
        }

        const remainingTime = timeoutMs - (Date.now() - startedAt);

        if (remainingTime <= 0) {
          break;
        }

        const nextSnapshot = await waitForStateChange(
          () => captureComposerAttachmentSnapshot(findComposer() || composer),
          getAttachmentSnapshotKey,
          observedSnapshot,
          remainingTime,
        );

        if (!nextSnapshot) {
          break;
        }

        observedSnapshot = nextSnapshot;
      }

      const finalComposer = findComposer() || composer;
      const finalSnapshot = captureComposerAttachmentSnapshot(finalComposer);
      return isExpectedAttachmentReadySnapshot(finalSnapshot, beforeSnapshot, expectedFileKey) ? finalComposer : null;
    }

    function isImageReadyForSubmit(composer) {
      if (!(composer instanceof HTMLElement)) {
        return false;
      }

      const scope = findComposerScope(composer);
      const hasAttachment = captureComposerAttachmentSnapshot(composer).hasAttachmentPreview;
      const sendButton = findSendButton(composer, { allowDisabled: true });

      if (!hasAttachment || hasPendingAttachmentWork(scope)) {
        return false;
      }

      return sendButton instanceof HTMLButtonElement && !sendButton.disabled;
    }

    function findComposerScope(composer) {
      return findClosestForm(composer)
        || findComposerContainer(composer)
        || composer?.parentElement
        || null;
    }

    function findClosestForm(composer) {
      if (!(composer instanceof Element)) {
        return null;
      }

      const directForm = composer.closest("form");

      if (directForm instanceof HTMLFormElement) {
        return directForm;
      }

      const container = findComposerContainer(composer) || composer.parentElement;
      const nestedForm = container?.querySelector("form");

      return nestedForm instanceof HTMLFormElement ? nestedForm : null;
    }

    function findComposerContainer(composer) {
      if (!(composer instanceof Element)) {
        return null;
      }

      const structuralContainer = composer.closest(
        '[data-chatgpt-composer], form, [data-testid*="composer" i], [data-testid*="prompt" i], [class*="composer" i], [class*="prompt" i]'
      );

      if (structuralContainer instanceof Element && structuralContainer !== composer) {
        return structuralContainer;
      }

      let current = composer.parentElement;
      let depth = 0;

      while (current && depth < 12) {
        if (
          current.querySelector('input[type="file"]')
          || current.querySelector('form')
          || current.querySelector('button[data-testid="send-button"]')
          || current.querySelector('button[data-testid*="send"]')
          || current.querySelector('button[aria-label*="send" i]')
          || current.querySelector('button[aria-label*="küld" i]')
          || current.querySelector('button[title*="send" i]')
          || current.querySelector('button[title*="küld" i]')
          || current.querySelector('button[type="submit"]')
        ) {
          return current;
        }

        current = current.parentElement;
        depth += 1;
      }

      return null;
    }

    function countAttachmentIndicators(scope) {
      return collectAttachmentIndicators(scope).length;
    }

    function collectAttachmentIndicators(scope) {
      if (!(scope instanceof Element)) {
        return [];
      }

      const selectors = [
        'img[src^="blob:"]',
        'img[src^="data:image"]',
        'img[src^="https:"]',
        '[data-testid*="attachment" i]',
        '[data-testid*="upload" i]',
        '[aria-label*="attachment" i]',
        '[aria-label*="image" i]',
        '[class*="attachment"]',
        '[class*="upload"]'
      ];

      const matches = selectors.flatMap((selector) => Array.from(scope.querySelectorAll(selector)));
      return Array.from(new Set(matches)).filter((element) => isTrackableAttachmentIndicator(element));
    }

    function describeAttachmentIndicator(element) {
      if (!(element instanceof HTMLElement)) {
        return "";
      }

      const imageSource = element instanceof HTMLImageElement
        ? element.currentSrc || element.getAttribute("src") || ""
        : "";
      const className = typeof element.className === "string"
        ? element.className.trim().split(/\s+/).filter(Boolean).sort().join(".")
        : "";
      const text = normalizeStructuredDomText(readStructuredDomText(element)).slice(0, 160);

      return [
        element.tagName.toLowerCase(),
        imageSource,
        String(element.getAttribute("data-testid") || ""),
        String(element.getAttribute("aria-label") || ""),
        String(element.getAttribute("title") || ""),
        className,
        text
      ].join("|");
    }

    function countSelectedFiles(scope) {
      return collectSelectedFileKeys(scope).length;
    }

    function collectSelectedFileKeys(scope) {
      if (!(scope instanceof Element)) {
        return [];
      }

      return Array.from(scope.querySelectorAll('input[type="file"]'))
        .flatMap((input) => (
          input instanceof HTMLInputElement && input.files?.length
            ? Array.from(input.files).map((file) => describeSelectedFile(file))
            : []
        ));
    }

    function describeSelectedFile(file) {
      if (!(file instanceof File)) {
        return "";
      }

      return [
        String(file.name || ""),
        Number(file.size) || 0,
        String(file.type || ""),
        Number(file.lastModified) || 0
      ].join(":");
    }

    function snapshotHasExpectedFile(snapshot, expectedFileKey) {
      if (!snapshot || typeof snapshot !== "object" || !expectedFileKey) {
        return false;
      }

      return Array.isArray(snapshot.selectedFileKeys) && snapshot.selectedFileKeys.includes(expectedFileKey);
    }

    function isExpectedAttachmentReadySnapshot(snapshot, beforeSnapshot, expectedFileKey) {
      if (!isAttachmentReadySnapshot(snapshot) || !beforeSnapshot) return false;
      // Ha az oldal megőrizte a fájlkiválasztást, annak az aktuális képhez kell tartoznia.
      if (Number(snapshot.fileInputCount) > 0 && !snapshotHasExpectedFile(snapshot, expectedFileKey)) return false;
      return Number(snapshot.attachmentCount) > Number(beforeSnapshot.attachmentCount)
        || (Number(snapshot.attachmentCount) > 0 && snapshot.attachmentIndicatorKey !== beforeSnapshot.attachmentIndicatorKey);
    }

    function hasPendingAttachmentWork(scope) {
      if (!(scope instanceof Element)) {
        return false;
      }

      const pendingSelectors = [
        '[aria-busy="true"]',
        '[role="progressbar"]',
        '[data-state="uploading"]',
        '[data-status="uploading"]',
        '[class*="uploading"]',
        '[class*="progress"]'
      ];

      const pendingNodes = [];

      if (scope instanceof HTMLElement) {
        for (const selector of pendingSelectors) {
          try {
            if (scope.matches(selector) && isTrackablePendingNode(scope)) {
              pendingNodes.push(scope);
              break;
            }
          } catch (_error) {
            // A selector kompatibilitási hibája miatt nem állhat meg a pending-ellenőrzés.
          }
        }
      }

      pendingNodes.push(
        ...pendingSelectors
          .flatMap((selector) => Array.from(scope.querySelectorAll(selector)))
          .filter((element) => isTrackablePendingNode(element))
      );

      if (pendingNodes.length > 0) {
        return true;
      }

      return false;
    }

    function findSendButton(composer, options = {}) {
      const allowDisabled = Boolean(options.allowDisabled);
      const scope = findComposerScope(composer);
      const form = findClosestForm(composer);
      const specificSelectors = [
        'button[data-testid="send-button"]',
        'button[data-testid*="send"]',
        'button[aria-label*="send" i]',
        'button[aria-label*="küld" i]',
        'button[title*="send" i]',
        'button[title*="küld" i]',
        'form button[type="submit"]'
      ];

      const explicitFormMatch = findExplicitSendButton(form, composer, allowDisabled);

      if (explicitFormMatch) {
        return explicitFormMatch;
      }

      const explicitScopedMatch = findExplicitSendButton(scope, composer, allowDisabled);

      if (explicitScopedMatch) {
        return explicitScopedMatch;
      }

      for (const selector of specificSelectors) {
        const scopedMatch = findBestSendButtonMatch(scope, selector, composer, allowDisabled);

        if (scopedMatch) {
          return scopedMatch;
        }
      }

      if (scope instanceof Element) {
        const scopedButtons = Array.from(scope.querySelectorAll("button"))
          .filter((button) => button instanceof HTMLButtonElement)
          .filter((button) => isEligibleSendButton(button, { allowDisabled }) && looksLikeSendButton(button) && isNearComposer(button, composer));

        const nearestScopedButton = pickNearestButton(scopedButtons, composer);

        if (nearestScopedButton) {
          return nearestScopedButton;
        }
      }

      const documentButtons = Array.from(document.querySelectorAll("button"))
        .filter((button) => button instanceof HTMLButtonElement)
        .filter((button) => isEligibleSendButton(button, { allowDisabled }) && looksLikeSendButton(button) && isNearComposer(button, composer));
      const nearestDocumentButton = pickNearestButton(documentButtons, composer);

      if (nearestDocumentButton) {
        return nearestDocumentButton;
      }

      return null;
    }

    function getMessageStableId(node) {
      if (!(node instanceof HTMLElement)) return "";
      // A legközelebbi saját üzenethatár azonosítója elsőbbséget élvez
      // egy külső, akár usert és assistantet együtt tartalmazó körével szemben.
      const messageBoundary = node.closest('[data-chatgpt-selection-message-id], [data-message-id], [data-chatgpt-search-unit-key][data-chatgpt-search-message-ids]');
      const selectionId = messageBoundary?.getAttribute("data-chatgpt-selection-message-id");
      if (selectionId) return `message:${selectionId}`;
      const messageId = messageBoundary?.getAttribute("data-message-id");
      if (messageId) return `message:${messageId}`;
      const messageIds = messageBoundary?.getAttribute("data-chatgpt-search-message-ids");
      if (messageIds) return `messages:${messageIds}`;
      const unitKey = messageBoundary?.getAttribute("data-chatgpt-search-unit-key");
      if (unitKey) return `unit:${unitKey}`;
      const turnNode = node.closest('[data-testid^="conversation-turn-"], [data-turn-id]');
      const turnId = turnNode?.getAttribute("data-turn-id") || turnNode?.getAttribute("data-testid");
      return turnId ? `turn:${turnId}` : "";
    }

    function getMessageKey(node) {
      return getMessageStableId(node) || (node ? `dom:${getDomNodeId(node)}` : "");
    }

    function captureAssistantSnapshot() {
      const assistantNodes = findAssistantMessageNodes();
      const userNodes = findUserMessageNodes();
      const lastUser = userNodes.at(-1) || null;
      let lastEntry = null;
      for (let index = assistantNodes.length - 1; index >= 0; index -= 1) {
        const node = assistantNodes[index];
        const pending = isAssistantResponsePending(node);
        const text = normalizeWhitespace(extractAssistantText(node));
        if (!text && !pending) continue;
        // A tényleges DOM-sorrend köti a választ az előtte álló felhasználói körhöz.
        // Egy korábbi válasz újrarajzolása nem kerülhet az új kérés eredményei közé.
        const precedingUser = [...userNodes].reverse().find((userNode) => (
          typeof userNode.compareDocumentPosition === "function"
          && Boolean(userNode.compareDocumentPosition(node) & 4)
          && !Boolean(userNode.compareDocumentPosition(node) & 1)
        ));
        lastEntry = { nodeId: getDomNodeId(node), stableId: getMessageStableId(node), userKey: getMessageKey(precedingUser), text, pending };
        break;
      }
      return {
        count: assistantNodes.length,
        lastNodeId: lastEntry?.nodeId || "",
        lastStableId: lastEntry?.stableId || "",
        lastText: lastEntry?.text || "",
        lastPending: Boolean(lastEntry?.pending),
        generationPending: hasActiveGenerationControl(),
        responseUserKey: lastEntry?.userKey || "",
        userCount: userNodes.length,
        lastUserKey: getMessageKey(lastUser),
        lastUserStableId: getMessageStableId(lastUser),
        lastUserNodeId: lastUser ? getDomNodeId(lastUser) : "",
        lastUserRoleSource: lastUser ? getMessageAuthorEvidence(lastUser).source : "none",
        userKeys: userNodes.map(getMessageKey),
        userNodeIds: userNodes.map(getDomNodeId),
        userStableIds: userNodes.map(getMessageStableId).filter(Boolean),
        assistantNodeIds: assistantNodes.map(getDomNodeId),
        assistantStableIds: assistantNodes.map(getMessageStableId).filter(Boolean)
      };
    }

    function bindResponseUserTurn(previousSnapshot, currentSnapshot) {
      if (previousSnapshot.requestUserKey) return;
      const previousKeys = previousSnapshot.userKeys || [];
      let nextKey = "";
      if (!previousSnapshot.lastUserKey) {
        nextKey = currentSnapshot.userKeys?.[0] || "";
      } else if (previousSnapshot.lastUserStableId) {
        const previousIndex = (currentSnapshot.userKeys || []).indexOf(previousSnapshot.lastUserKey);
        nextKey = previousIndex >= 0
          ? currentSnapshot.userKeys?.[previousIndex + 1] || ""
          : (currentSnapshot.lastUserStableId && !previousKeys.includes(currentSnapshot.lastUserKey) ? currentSnapshot.lastUserKey : "");
      } else {
        // Stabil azonosító hiányában a régi felhasználói node megmaradása igazol
        // új kört. A teljes DOM újrarajzolása és a virtualizáció önmagában nem.
        const previousIndex = (currentSnapshot.userNodeIds || []).indexOf(previousSnapshot.lastUserNodeId);
        if (previousIndex >= 0) nextKey = currentSnapshot.userKeys?.[previousIndex + 1] || "";
      }
      if (nextKey) previousSnapshot.requestUserKey = nextKey;
    }

    async function waitForAssistantResponse(previousSnapshot, timeoutMs, reportProgress) {
      assertDeliveryActive();
      let observedSnapshot = captureAssistantSnapshot();
      let latestUsableSnapshot = null;
      const startedAt = Date.now();
      const recordSnapshot = (snapshot) => reportAssistantSnapshotDiagnostic(snapshot, previousSnapshot, {
        elapsed_ms: Date.now() - startedAt, late: false
      });
      reportDiagnostic("response_wait_started", { timeout_ms: timeoutMs });
      recordSnapshot(observedSnapshot);

      while (Date.now() - startedAt < timeoutMs) {
        if (isUsableAssistantSnapshot(observedSnapshot, previousSnapshot)) {
          latestUsableSnapshot = observedSnapshot;
        }

        if (isFreshAssistantSnapshot(observedSnapshot, previousSnapshot) && isStableAssistantSnapshot(observedSnapshot)) {
          const followUpProgressCallId = startAssistantResponseFollowUp(previousSnapshot, observedSnapshot);
          reportAssistantSnapshotProgress(observedSnapshot, reportProgress);
          return {
            text: observedSnapshot.lastText,
            copied: false,
            followUpProgressCallId
          };
        }

        const remainingTime = timeoutMs - (Date.now() - startedAt);

        if (remainingTime <= 0) {
          break;
        }

        const nextSnapshot = await waitForStateChange(
          () => captureAssistantSnapshot(),
          getAssistantSnapshotKey,
          observedSnapshot,
          remainingTime,
        );

        if (!nextSnapshot) {
          break;
        }

        observedSnapshot = nextSnapshot;
        recordSnapshot(observedSnapshot);
      }

      const finalSnapshot = captureAssistantSnapshot();
      recordSnapshot(finalSnapshot);
      if (isFreshAssistantSnapshot(finalSnapshot, previousSnapshot) && isStableAssistantSnapshot(finalSnapshot)) {
        const followUpProgressCallId = startAssistantResponseFollowUp(previousSnapshot, finalSnapshot);
        reportAssistantSnapshotProgress(finalSnapshot, reportProgress);
        return {
          text: finalSnapshot.lastText,
          copied: false,
          followUpProgressCallId
        };
      }

      const partialSnapshot = isUsableAssistantSnapshot(finalSnapshot, previousSnapshot)
        ? finalSnapshot : latestUsableSnapshot && finalSnapshot.lastUserKey === previousSnapshot.requestUserKey ? latestUsableSnapshot : null;
      const followUpProgressCallId = startAssistantResponseFollowUp(previousSnapshot, partialSnapshot);
      reportDiagnostic("response_timeout", { elapsed_ms: Date.now() - startedAt, late: Boolean(followUpProgressCallId) });
      if (followUpProgressCallId) return { text: "", copied: false, responsePending: true, followUpProgressCallId };
      throw new Error("A ChatGPT válasza nem érkezett meg időben.");
    }

    function startAssistantResponseFollowUp(previousSnapshot, initialSnapshot) {
      assertDeliveryActive();
      const baseProgressCallId = String(payload.progressCallId || "").trim();

      if (!baseProgressCallId || (initialSnapshot && !isUsableAssistantSnapshot(initialSnapshot, previousSnapshot))) {
        return "";
      }

      const followUpProgressCallId = `${baseProgressCallId}-followup`;
      const domTracker = ensureDomActivityTracker();
      const followUps = ensureAssistantResponseFollowUps();
      const followUpState = {
        stopped: false,
        previousSnapshot,
        latestText: String(initialSnapshot?.lastText || ""),
        latestNodeId: String(initialSnapshot?.lastNodeId || ""),
        latestComplete: initialSnapshot ? isStableAssistantSnapshot(initialSnapshot) : false,
        startedAt: Date.now(),
        timeoutId: 0,
        unsubscribe: null
      };

      stopAssistantResponseFollowUp(followUpProgressCallId, { emitDone: false });
      reportDiagnostic("response_watch_started", { late: !initialSnapshot, timeout_ms: ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS });

      const scheduleFollowUpStop = (delayMs) => {
        if (followUpState.timeoutId) {
          window.clearTimeout(followUpState.timeoutId);
        }

        const boundedDelayMs = Math.min(
          Math.max(FRAME_INTERVAL_MS, ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS - (Date.now() - followUpState.startedAt)),
          Math.max(FRAME_INTERVAL_MS, Number(delayMs) || ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS)
        );
        followUpState.timeoutId = window.setTimeout(() => {
          followUpState.timeoutId = 0;
          reportDiagnostic("response_watch_finished", { elapsed_ms: Date.now() - followUpState.startedAt });
          stopAssistantResponseFollowUp(followUpProgressCallId);
        }, boundedDelayMs);
      };

      const evaluateFollowUp = () => {
        if (followUpState.stopped) {
          return;
        }

        if (Date.now() - followUpState.startedAt >= ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS) {
          stopAssistantResponseFollowUp(followUpProgressCallId);
          return;
        }

        const currentSnapshot = captureAssistantSnapshot();
        bindResponseUserTurn(previousSnapshot, currentSnapshot);
        reportAssistantSnapshotDiagnostic(currentSnapshot, previousSnapshot, {
          elapsed_ms: Date.now() - followUpState.startedAt, late: !initialSnapshot
        });
        if (previousSnapshot.requestUserKey && currentSnapshot.lastUserKey !== previousSnapshot.requestUserKey) {
          reportDiagnostic("response_watch_finished", { reason: "user_turn_changed", elapsed_ms: Date.now() - followUpState.startedAt });
          stopAssistantResponseFollowUp(followUpProgressCallId);
          return;
        }

        if (!isUsableAssistantSnapshot(currentSnapshot, previousSnapshot)) {
          return;
        }

        if (
          currentSnapshot.lastText === followUpState.latestText
          && currentSnapshot.lastNodeId === followUpState.latestNodeId
          && isStableAssistantSnapshot(currentSnapshot) === followUpState.latestComplete
        ) {
          scheduleFollowUpStop(
            !isStableAssistantSnapshot(currentSnapshot)
              ? ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS
              : ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS
          );
          return;
        }

        followUpState.latestText = String(currentSnapshot.lastText || "");
        followUpState.latestNodeId = String(currentSnapshot.lastNodeId || "");
        followUpState.latestComplete = isStableAssistantSnapshot(currentSnapshot);
        writeProgressEntry(followUpProgressCallId, {
          kind: "assistant_response",
          text: currentSnapshot.lastText,
          complete: followUpState.latestComplete
        });
        reportDiagnostic("response_received", { late: !initialSnapshot, text_length: String(currentSnapshot.lastText || "").length, pending: currentSnapshot.lastPending });
        scheduleFollowUpStop(
          !isStableAssistantSnapshot(currentSnapshot)
            ? ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS
            : ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS
        );
      };

      followUpState.unsubscribe = domTracker.subscribe(evaluateFollowUp);
      followUps[followUpProgressCallId] = followUpState;
      scheduleFollowUpStop(
        !initialSnapshot ? ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS
          : !isStableAssistantSnapshot(initialSnapshot) ? ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS : ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS
      );
      return followUpProgressCallId;
    }

    function isFreshAssistantSnapshot(currentSnapshot, previousSnapshot) {
      if (!currentSnapshot || !previousSnapshot || !currentSnapshot.lastText) return false;
      bindResponseUserTurn(previousSnapshot, currentSnapshot);
      const requestUserKey = previousSnapshot.requestUserKey;
      if (!requestUserKey || currentSnapshot.lastUserKey !== requestUserKey || currentSnapshot.responseUserKey !== requestUserKey) return false;
      if (currentSnapshot.lastStableId) {
        return !(previousSnapshot.assistantStableIds || []).includes(currentSnapshot.lastStableId);
      }
      return !(previousSnapshot.assistantNodeIds || []).includes(currentSnapshot.lastNodeId);
    }

    function reportAssistantSnapshotDiagnostic(snapshot, previousSnapshot, fields = {}) {
      if (snapshot && previousSnapshot) bindResponseUserTurn(previousSnapshot, snapshot);
      const fresh = isFreshAssistantSnapshot(snapshot, previousSnapshot);
      const requestUserKey = previousSnapshot?.requestUserKey || "";
      const requestUserBound = Boolean(requestUserKey);
      const lastUserMatchesRequest = requestUserBound && snapshot?.lastUserKey === requestUserKey;
      const responseUserMatchesRequest = requestUserBound && snapshot?.responseUserKey === requestUserKey;
      const assistantIdentityNew = Boolean(snapshot?.lastStableId || snapshot?.lastNodeId)
        && (snapshot.lastStableId
          ? !(previousSnapshot?.assistantStableIds || []).includes(snapshot.lastStableId)
          : !(previousSnapshot?.assistantNodeIds || []).includes(snapshot.lastNodeId));
      const stable = isStableAssistantSnapshot(snapshot);
      let rejectionReason = "none";
      if (!requestUserBound) rejectionReason = "request_user_unbound";
      else if (!lastUserMatchesRequest) rejectionReason = "last_user_mismatch";
      else if (!responseUserMatchesRequest) rejectionReason = "response_user_mismatch";
      else if (!assistantIdentityNew) rejectionReason = "assistant_identity_old";
      else if (!snapshot?.lastText) rejectionReason = "assistant_text_missing";
      else if (isTransientAssistantText(snapshot.lastText)) rejectionReason = "assistant_text_transient";
      else if (!stable) rejectionReason = "assistant_pending";
      const userRoleCandidates = Array.from(document.querySelectorAll('[data-message-author-role="user"], [data-conversation-role="user"], [data-user-message-bubble], h1, h2, h3, h4, h5, h6'))
        .filter((element) => isDomTrackableElement(element) && (element.getAttribute("data-message-author-role") === "user"
          || element.getAttribute("data-conversation-role") === "user" || element.hasAttribute("data-user-message-bubble")
          || getUiMessageHeadingRole(element) === "user")).length;
      const clickableImageCandidates = Array.from(document.querySelectorAll('img'))
        .filter((image) => isDomTrackableElement(image) && image.closest('button, [role="button"]')
          && getMessageAuthorEvidence(image).role === "user"
          && !image.closest('[role="menu"], [role="menuitem"], [role="toolbar"], [role="heading"], [data-radix-menu-content], [data-radix-dropdown-menu-content]')
          && !isAvatarOrMessageControlImage(image, document.body)).length;
      reportDiagnostic("response_snapshot", {
        assistant_count: snapshot?.count || 0, user_count: snapshot?.userCount || 0,
        text_length: String(snapshot?.lastText || "").length, pending: Boolean(snapshot?.lastPending),
        has_identity: Boolean(snapshot?.lastStableId), fresh, stable,
        request_user_bound: requestUserBound, last_user_matches_request: lastUserMatchesRequest,
        response_user_matches_request: responseUserMatchesRequest, assistant_identity_new: assistantIdentityNew,
        user_role_source: snapshot?.lastUserRoleSource || "none", rejection_reason: rejectionReason,
        user_role_candidates: userRoleCandidates, clickable_image_candidates: clickableImageCandidates,
        ...fields
      });
    }

    function isStableAssistantSnapshot(snapshot) {
      const candidate = snapshot?.lastText;

      if (!candidate) {
        return false;
      }

      if (isTransientAssistantText(candidate)) {
        return false;
      }

      return !snapshot.lastPending && !snapshot.generationPending;
    }

    function hasActiveGenerationControl() {
      const composer = findComposer();
      const scope = findComposerScope(composer);
      if (!(scope instanceof Element)) return false;
      return Array.from(scope.querySelectorAll("button")).some((button) => (
        button instanceof HTMLButtonElement && isDomAccessibleElement(button)
        && ["stop", "állj", "leállít", "megszakít"].some((alias) => readButtonLabel(button).includes(alias))
      ));
    }

    function isUsableAssistantSnapshot(snapshot, previousSnapshot) {
      return isFreshAssistantSnapshot(snapshot, previousSnapshot)
        && Boolean(snapshot?.lastText)
        && !isTransientAssistantText(snapshot.lastText);
    }

    function isComposerBackInSendState() {
      const composer = findComposer();

      if (!(composer instanceof HTMLElement)) {
        return false;
      }

      const sendButton = findSendButton(composer, { allowDisabled: true });

      if (!(sendButton instanceof HTMLButtonElement)) {
        return false;
      }

      return !looksLikeNonSendAction(readButtonLabel(sendButton));
    }

    function reportAssistantSnapshotProgress(snapshot, reportProgress) {
      if (typeof reportProgress !== "function" || !snapshot?.lastText) {
        return;
      }

      reportProgress({
        kind: "assistant_response",
        text: snapshot.lastText,
        complete: isStableAssistantSnapshot(snapshot)
      });
      reportDiagnostic("response_received", { late: false, text_length: snapshot.lastText.length, pending: snapshot.lastPending });
    }

    function isTransientAssistantText(text) {
      const normalized = normalizeWhitespace(text).toLowerCase().replace(/[.\u2026]+$/, "").trim();

      if (!normalized) {
        return true;
      }

      return [
        "kép elemzése folyamatban",
        "elemzés folyamatban",
        "képelemzés folyamatban",
        "gondolkodás folyamatban",
        "analyzing image",
        "image analysis in progress",
        "analysis in progress",
        "thinking",
        "processing image"
      ].includes(normalized);
    }

    function isAssistantMessageBusy(element) {
      if (!(element instanceof HTMLElement)) {
        return true;
      }

      if (element.getAttribute("aria-busy") === "true") {
        return true;
      }

      return hasPendingResponseSignals(element);
    }

    function isAssistantResponsePending(element) {
      if (!(element instanceof HTMLElement)) {
        return true;
      }

      if (isAssistantMessageBusy(element)) {
        return true;
      }

      const responseScope = findAssistantResponseScope(element);
      return hasPendingResponseSignals(responseScope);
    }

    function findAssistantResponseScope(element) {
      if (!(element instanceof HTMLElement)) {
        return null;
      }

      return element.closest('[data-testid^="conversation-turn-"], article, section')
        || element.closest('[role="presentation"], [role="group"]')
        || element.parentElement
        || element;
    }

    function hasPendingResponseSignals(scope) {
      if (!(scope instanceof Element)) {
        return false;
      }

      const pendingSelectors = [
        '[aria-busy="true"]',
        '[role="progressbar"]',
        '[data-state="streaming"]',
        '[data-state="thinking"]',
        '[data-status="in_progress"]',
        '[data-testid*="stream" i]',
        '[data-testid*="thinking" i]',
        '[data-testid*="typing" i]',
        '[data-testid*="loading" i]',
        '[class*="streaming"]',
        '[class*="thinking"]',
        '[class*="typing"]',
        '[class*="loading"]',
        '[class*="progress"]'
      ];

      if (scope instanceof HTMLElement) {
        for (const selector of pendingSelectors) {
          try {
            if (scope.matches(selector) && isTrackablePendingNode(scope)) {
              return true;
            }
          } catch (_error) {
            // A selector kompatibilitási hibája miatt nem állhat meg a pending-ellenőrzés.
          }
        }
      }

      return pendingSelectors
        .flatMap((selector) => Array.from(scope.querySelectorAll(selector)))
        .some((element) => isTrackablePendingNode(element));
    }

    function isGenerationInProgress() {
      return findAssistantMessageNodes().some((assistantNode) => isAssistantResponsePending(assistantNode));
    }

    function findUserMessageNodes() {
      return findMessageNodesByAuthor("user");
    }

    function findAssistantMessageNodes() {
      return findMessageNodesByAuthor("assistant");
    }

    function findMessageNodesByAuthor(authorRole) {
      const normalizedAuthorRole = String(authorRole || "").trim().toLowerCase();

      if (!normalizedAuthorRole) {
        return [];
      }

      const directMatches = Array.from(document.querySelectorAll(`[data-message-author-role="${normalizedAuthorRole}"]`))
        .filter(isDomTrackableElement)
        .filter((element) => isTopLevelAuthorMessageNode(element, normalizedAuthorRole))
        .filter((element) => doesMessageNodeMatchAuthor(element, normalizedAuthorRole));

      const modernMatches = Array.from(document.querySelectorAll(normalizedAuthorRole === "user"
        ? '[data-user-message-bubble]' : '[data-chatgpt-selection-message-id]'))
        .filter(isDomTrackableElement)
        .filter((element) => doesMessageNodeMatchAuthor(element, normalizedAuthorRole));
      const roleScopeMatches = Array.from(document.querySelectorAll('[data-conversation-role]'))
        .filter(isDomTrackableElement)
        .map(findConversationRoleMessageScope)
        .filter((element) => element && doesMessageNodeMatchAuthor(element, normalizedAuthorRole));
      const headingScopeMatches = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'))
        .filter((element) => getUiMessageHeadingRole(element) === normalizedAuthorRole)
        .map(findConversationRoleMessageScope)
        .filter((element) => element && doesMessageNodeMatchAuthor(element, normalizedAuthorRole));
      const fallbackMatches = Array.from(document.querySelectorAll('[data-testid^="conversation-turn-"], article, [data-chatgpt-search-unit-key][data-chatgpt-search-message-ids]'))
        .filter(isDomTrackableElement)
        .filter((element) => doesMessageNodeMatchAuthor(element, normalizedAuthorRole));
      const matches = Array.from(new Set([...directMatches, ...modernMatches, ...roleScopeMatches, ...headingScopeMatches, ...fallbackMatches]));
      // A belső szerep-node elsőbbséget élvez a körülötte álló article helyett.
      const deduplicated = matches.filter((element) => !matches.some((other) => other !== element && element.contains(other)));
      return deduplicated.sort((left, right) => left.compareDocumentPosition(right) & 4 ? -1 : left.compareDocumentPosition(right) & 2 ? 1 : 0);
    }

    function isTopLevelAuthorMessageNode(element, authorRole) {
      if (!(element instanceof HTMLElement)) {
        return false;
      }

      const normalizedAuthorRole = String(authorRole || "").trim().toLowerCase();

      if (!normalizedAuthorRole) {
        return false;
      }

      const parentMessageNode = element.parentElement?.closest(`[data-message-author-role="${normalizedAuthorRole}"]`);
      return !(parentMessageNode instanceof HTMLElement);
    }

    function doesMessageNodeMatchAuthor(element, authorRole) {
      if (!(element instanceof HTMLElement)) {
        return false;
      }

      const normalizedAuthorRole = String(authorRole || "").trim().toLowerCase();

      if (!normalizedAuthorRole) {
        return false;
      }

      const evidence = getMessageAuthorEvidence(element);
      if (evidence.role !== normalizedAuthorRole) return false;

      const extractedText = normalizeWhitespace(extractMessageText(element));

      if (normalizedAuthorRole === "assistant") {
        return Boolean(extractedText) || isAssistantMessageBusy(element);
      }

      return Boolean(extractedText) || hasUserMessageImage(element)
        || element.hasAttribute("data-user-message-bubble") || element.hasAttribute("data-message-author-role");
    }

    function findConversationRoleMessageScope(marker) {
      if (!(marker instanceof HTMLElement) || !isDomTrackableElement(marker)) return null;
      const role = String(marker.getAttribute("data-conversation-role") || getUiMessageHeadingRole(marker)).trim().toLowerCase();
      if (!["user", "assistant"].includes(role)) return null;
      const boundarySelector = '[data-message-id], [data-chatgpt-selection-message-id], [data-message-author-role], [data-user-message-bubble], [data-chatgpt-search-unit-key][data-chatgpt-search-message-ids], [data-testid^="conversation-turn-"], [data-turn-id], [data-turn-key], [data-content-search-turn-key], article';
      let scope = /^H[1-6]$/.test(marker.tagName) || marker.getAttribute("role") === "heading"
        ? marker.parentElement : marker;
      for (; scope instanceof HTMLElement; scope = scope.parentElement) {
        if (["HTML", "BODY", "MAIN", "FORM"].includes(scope.tagName) || scope.hasAttribute("data-chatgpt-composer")) return null;
        const evidence = getMessageAuthorEvidence(scope, { inherit: false });
        // A közös user+assistant kör nem üzenet. A mély szerepfejlécet csak
        // a saját tartalmáig vagy a legközelebbi igazolt üzenethatárig követjük.
        if (evidence.role === role && (normalizeWhitespace(extractMessageText(scope)) || hasUserMessageImage(scope))) return scope;
        if (scope.matches(boundarySelector)) return evidence.role === role ? scope : null;
      }
      return null;
    }

    function getUiMessageHeadingRole(marker) {
      if (!(marker instanceof HTMLElement) || !isDomTrackableElement(marker)
        || !/^H[1-6]$/.test(marker.tagName)
        || !String(marker.getAttribute("class") || "").split(/\s+/).includes("sr-only")) return "";
      // Csak a ChatGPT saját teljes UI-felirata szerepjel. A felhasználói
      // tartalomban idézett fejléc és a tetszőleges név-/szövegrészlet nem az.
      const label = normalizeWhitespace(marker.textContent).toLowerCase();
      const role = label === "you said:" ? "user" : label === "chatgpt said:" ? "assistant" : "";
      if (!role || marker.closest('blockquote, pre, code, form, button, [role="button"], [role="menu"], [role="menuitem"], [role="toolbar"], [data-radix-menu-content], [data-radix-dropdown-menu-content], [data-chatgpt-composer], [data-user-message-bubble], [data-chatgpt-selection-message-id]')) return "";
      for (let parent = marker.parentElement; parent instanceof HTMLElement; parent = parent.parentElement) {
        if (parent.hasAttribute("data-markdown-text-style") || /(?:markdown|prose)/i.test(String(parent.getAttribute("class") || ""))) return "";
        // Az igazolt user UI-fejléc a saját keresőegység testvérága.
        // A kereshető üzenettartalom belsejében álló szöveg nem fejlécjel.
        if (parent.hasAttribute("data-chatgpt-search-unit-key") && parent.hasAttribute("data-chatgpt-search-message-ids")) return "";
        if (["HTML", "BODY", "MAIN"].includes(parent.tagName)) break;
      }
      const container = marker.parentElement;
      const contentUnits = Array.from(container.querySelectorAll('[data-chatgpt-search-unit-key][data-chatgpt-search-message-ids]'))
        .filter((unit) => isDomTrackableElement(unit) && !unit.contains(marker)
          && String(unit.getAttribute("data-chatgpt-search-unit-key") || "").trim()
          && String(unit.getAttribute("data-chatgpt-search-message-ids") || "").trim());
      // Az attribútum nélküli fejléc csak a saját, egyetlen igazolt
      // üzenetágának szerepét adja meg; egy kép önmagában nem üzenethatár.
      if (contentUnits.length !== 1) return "";
      return role;
    }

    function getAdjacentMessageHeadingEvidence(boundary) {
      const container = boundary.parentElement;
      if (!(container instanceof HTMLElement) || ["HTML", "BODY", "MAIN", "FORM"].includes(container.tagName)) return { role: "", source: "none" };
      const ownHeadings = Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6'))
        .filter((marker) => !boundary.contains(marker) && getUiMessageHeadingRole(marker)
          && findConversationRoleMessageScope(marker) === container);
      // A belső stabil üzenethatár csak a saját konténerének fejlécét
      // örökölheti; egy külső közös user+assistant körét nem.
      return ownHeadings.length ? getMessageAuthorEvidence(container, { inherit: false }) : { role: "", source: "none" };
    }

    function getMessageAuthorEvidence(element, options = {}) {
      if (!(element instanceof HTMLElement) || !isDomTrackableElement(element)) return { role: "", source: "none" };
      const collect = (scope) => {
        const signals = [];
        const nodes = [scope, ...Array.from(scope.querySelectorAll('[data-message-author-role], [data-conversation-role], [data-user-message-bubble], h1, h2, h3, h4, h5, h6'))]
          .filter(isDomTrackableElement);
        for (const node of nodes) {
          for (const [attribute, source] of [["data-message-author-role", "message_author"], ["data-conversation-role", "conversation_role"]]) {
            const role = String(node.getAttribute(attribute) || "").trim().toLowerCase();
            if (["user", "assistant"].includes(role)) signals.push({ role, source });
          }
          if (node.hasAttribute("data-user-message-bubble")) signals.push({ role: "user", source: "user_bubble" });
          const headingRole = getUiMessageHeadingRole(node);
          if (headingRole) signals.push({ role: headingRole, source: "heading_role" });
        }
        const label = String(scope.getAttribute("aria-label") || "").trim().toLowerCase();
        if (/^(?:user|you)(?:\s+(?:said|message))?:?$/.test(label)) signals.push({ role: "user", source: "aria_role" });
        if (/^(?:assistant|chatgpt)(?:\s+(?:said|message))?:?$/.test(label)) signals.push({ role: "assistant", source: "aria_role" });
        const roles = new Set(signals.map((signal) => signal.role));
        return roles.size > 1 ? { role: "", source: "role_conflict" } : signals[0] || { role: "", source: "none" };
      };
      let evidence = collect(element);
      // A belső bubble nem írhatja felül a külső explicit ellenkező szerepet.
      for (let parent = element.parentElement; parent instanceof HTMLElement; parent = parent.parentElement) {
        const parentRole = String(parent.getAttribute("data-message-author-role") || parent.getAttribute("data-conversation-role") || "").trim().toLowerCase();
        if (evidence.role && ["user", "assistant"].includes(parentRole) && parentRole !== evidence.role) return { role: "", source: "role_conflict" };
      }
      if (evidence.role || evidence.source === "role_conflict" || options.inherit === false) return evidence;
      if (element.matches('[data-chatgpt-search-unit-key][data-chatgpt-search-message-ids]')) {
        // A saját, szerep nélküli keresőegység nem örökölheti egy
        // következő assistant testvérágának szerepét a közös külső körből.
        return getAdjacentMessageHeadingEvidence(element);
      }
      for (let parent = element.parentElement; parent instanceof HTMLElement; parent = parent.parentElement) {
        if (["HTML", "BODY", "MAIN", "FORM"].includes(parent.tagName)) break;
        evidence = collect(parent);
        if (evidence.role || evidence.source === "role_conflict") return evidence;
        if (parent.matches('[data-message-id], [data-chatgpt-search-unit-key][data-chatgpt-search-message-ids], [data-turn-key], [data-content-search-turn-key], article')) {
          evidence = getAdjacentMessageHeadingEvidence(parent);
          if (evidence.role || evidence.source === "role_conflict") return evidence;
          break;
        }
      }
      return { role: "", source: "none" };
    }

    function hasUserMessageImage(scope) {
      if (!(scope instanceof HTMLElement)) return false;
      return Array.from(scope.querySelectorAll("img")).some((image) => (
        isDomTrackableElement(image) && Boolean(image.getAttribute("src") || image.getAttribute("srcset"))
        && !image.closest('[role="menu"], [role="menuitem"], [role="toolbar"], [role="heading"], [data-radix-menu-content], [data-radix-dropdown-menu-content], h1[data-conversation-role], h2[data-conversation-role], h3[data-conversation-role], h4[data-conversation-role], h5[data-conversation-role], h6[data-conversation-role]')
        && !isAvatarOrMessageControlImage(image, scope)
        // A képnézegető button tartalma a saját explicit user kör képe.
        // Önmagában egy tetszőleges gombban vagy avatarban álló kép nem szerepbizonyíték.
        && (!image.closest('button, [role="button"]') || getMessageAuthorEvidence(scope).role === "user")
      ));
    }

    function isAvatarOrMessageControlImage(image, scope) {
      const avatarPattern = /(?:^|[\s_/-])(?:avatar|profile[\s_-]*(?:photo|picture|image)|user[\s_-]*icon)(?:$|[\s_/-])/i;
      for (let node = image; node instanceof HTMLElement; node = node.parentElement) {
        if (node.hasAttribute("data-avatar") || node.getAttribute("data-slot") === "avatar") return true;
        if (["class", "data-testid", "alt", "aria-label"].some((attribute) => avatarPattern.test(String(node.getAttribute(attribute) || "")))) return true;
        if (node.matches('button, [role="button"]') && ((node.hasAttribute("aria-haspopup")
          && !["dialog", "false"].includes(String(node.getAttribute("aria-haspopup") || "").toLowerCase()))
          || node.getAttribute("type") === "submit")) return true;
        if (node === scope) break;
      }
      return false;
    }

    function extractAssistantText(element) {
      return extractMessageText(element);
    }

    function extractMessageText(element) {
      const preferredContainers = [
        ...Array.from(element.querySelectorAll('[data-markdown-text-style], .markdown, [class*="markdown"], [class*="prose"]')),
        element.querySelector('[data-markdown-text-style]'),
        element.querySelector(".markdown"),
        element.querySelector('[class*="markdown"]'),
        element.querySelector('[class*="prose"]')
      ];
      const uniqueContainers = Array.from(new Set(preferredContainers)).filter((container) => container instanceof HTMLElement);
      const textContainers = uniqueContainers.filter((container) => !uniqueContainers.some((other) => other !== container && other.contains(container)));
      textContainers.sort((left, right) => left.compareDocumentPosition(right) & 4 ? -1 : left.compareDocumentPosition(right) & 2 ? 1 : 0);
      const text = normalizeStructuredDomText(textContainers.map((container) => readStructuredDomText(container)).filter(Boolean).join("\n\n"));
      if (text) return text;
      return normalizeStructuredDomText(readStructuredDomText(element));
    }

    function isDomTrackableElement(element) {
      if (!(element instanceof HTMLElement) || !element.isConnected) {
        return false;
      }

      if (element.closest("template, script, style, noscript")) {
        return false;
      }

      return !isSemanticallyHidden(element);
    }

    function isSemanticallyHidden(element) {
      if (!(element instanceof HTMLElement) || !element.isConnected) {
        return true;
      }

      if (element.hidden || element.closest("template, script, style, noscript, [hidden]")) {
        return true;
      }

      if (element.getAttribute("aria-hidden") === "true" || element.closest('[aria-hidden="true"]')) {
        return true;
      }

      // A viewporton kívüli üzenet továbbra is olvasható. A CSS-sel elrejtett
      // szülő viszont a belső üzenetet is elrejti, annak saját display értékétől függetlenül.
      for (let current = element; current instanceof HTMLElement; current = current.parentElement) {
        const style = window.getComputedStyle(current);
        if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") return true;
      }
      return false;
    }

    function isDomAccessibleElement(element) {
      return element instanceof HTMLElement
        && element.isConnected
        && !isSemanticallyHidden(element);
    }

    function isTrackableAttachmentIndicator(element) {
      if (!(element instanceof HTMLElement) || !isDomAccessibleElement(element)) {
        return false;
      }

      if (element instanceof HTMLInputElement && element.type === "file") {
        return false;
      }

      if (element instanceof HTMLButtonElement) {
        return false;
      }

      return !element.closest("template, script, style, noscript");
    }

    function isTrackablePendingNode(element) {
      if (!(element instanceof HTMLElement) || !isDomAccessibleElement(element)) {
        return false;
      }

      return !element.closest("template, script, style, noscript");
    }

    function readStructuredDomText(root) {
      if (!(root instanceof Node)) {
        return "";
      }

      const parts = [];

      const appendText = (text) => {
        const normalizedText = String(text || "").replace(/\u00a0/g, " ");

        if (!normalizedText) {
          return;
        }

        // Az inline formázás nem szúrhat szóközt egy szó vagy parancs közepébe.
        parts.push(normalizedText);
      };

      const appendBreak = () => {
        if (parts.length === 0 || parts[parts.length - 1] === "\n") {
          return;
        }

        parts.push("\n");
      };

      const visit = (node) => {
        if (node instanceof Text) {
          appendText(node.textContent || "");
          return;
        }

        if (!(node instanceof HTMLElement)) {
          return;
        }

        const tagName = node.tagName.toUpperCase();

        if (DOM_TEXT_SKIP_TAGS.has(tagName)
          || (/^H[1-6]$/.test(tagName) && (node.hasAttribute("data-conversation-role")
            || String(node.getAttribute("class") || "").split(/\s+/).includes("sr-only")))) {
          return;
        }

        if (tagName === "BR") {
          appendBreak();
          return;
        }

        if (isSemanticallyHidden(node)) {
          return;
        }

        const isBlockLike = DOM_TEXT_BLOCK_TAGS.has(tagName);

        if (isBlockLike) {
          appendBreak();
        }

        for (const childNode of Array.from(node.childNodes)) {
          visit(childNode);
        }

        if (isBlockLike) {
          appendBreak();
        }
      };

      visit(root);
      return parts.join("");
    }

    function normalizeStructuredDomText(value) {
      return String(value || "")
        .replace(/\r\n?/g, "\n")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n[ \t]+/g, "\n")
        .replace(/[ \t]{2,}/g, " ")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
    }

    function isEligibleSendButton(button, options = {}) {
      const allowDisabled = Boolean(options.allowDisabled);

      if (!(button instanceof HTMLButtonElement) || !button.isConnected || (button.disabled && !allowDisabled)) {
        return false;
      }

      if (!isDomAccessibleElement(button)) {
        return false;
      }

      if (button.closest('[role="menu"], [role="menuitem"], [data-radix-menu-content], [data-radix-dropdown-menu-content]')) {
        return false;
      }

      return true;
    }

    function findExplicitSendButton(scope, composer, allowDisabled = false) {
      if (!(scope instanceof Element)) {
        return null;
      }

      const matches = Array.from(scope.querySelectorAll("button"))
        .filter((button) => button instanceof HTMLButtonElement)
        .filter((button) => isEligibleSendButton(button, { allowDisabled }))
        .filter((button) => buttonHasExplicitSendIntent(button));

      return pickNearestButton(matches, composer);
    }

    function findBestSendButtonMatch(scope, selector, composer, allowDisabled = false) {
      if (!(scope instanceof Element)) {
        return null;
      }

      const matches = Array.from(scope.querySelectorAll(selector))
        .filter((button) => button instanceof HTMLButtonElement)
        .filter((button) => {
          if (!isEligibleSendButton(button, { allowDisabled }) || !looksLikeSendButton(button)) {
            return false;
          }

          return buttonHasExplicitSendIntent(button) || sharesComposerScope(button, composer) || sharesComposerForm(button, composer);
        });

      return pickNearestButton(matches, composer);
    }

    function looksLikeSendButton(button) {
      if (!(button instanceof HTMLButtonElement)) {
        return false;
      }

      const label = readButtonLabel(button);

      if (buttonHasExplicitSendIntent(button)) {
        return true;
      }

      if (button.type === "submit" && !looksLikeNonSendAction(label)) {
        return true;
      }

      return false;
    }

    function buttonHasExplicitSendIntent(button) {
      if (!(button instanceof HTMLButtonElement)) {
        return false;
      }

      const label = readButtonLabel(button);

      return ["send", "küld", "elküld", "submit", "prompt"].some((needle) => label.includes(needle))
        && !looksLikeNonSendAction(label);
    }

    function looksLikeNonSendAction(label) {
      return ["stop", "állj", "megszakít", "cancel", "copy", "másol", "like", "dislike", "share", "regenerate", "more", "megoszt", "átnevez", "rögzít", "archiv", "törlés", "delete"].some((needle) => label.includes(needle));
    }

    function looksLikeCancelAction(button) {
      if (!(button instanceof HTMLButtonElement)) {
        return false;
      }

      const label = readButtonLabel(button);
      return ["cancel", "mégse", "vetés", "elvet", "discard"].some((needle) => label.includes(needle));
    }

    function readButtonLabel(button) {
      return [
        button.getAttribute("aria-label"),
        button.getAttribute("title"),
        button.dataset?.testid,
        button.textContent
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
    }

    function pickNearestButton(buttons, composer) {
      if (!Array.isArray(buttons) || buttons.length === 0) {
        return null;
      }

      if (!(composer instanceof Element)) {
        return buttons[0] || null;
      }

      const composerScope = findComposerScope(composer);
      const composerForm = findClosestForm(composer);
      const ranked = buttons
        .map((button) => {
          const explicitSendBonus = buttonHasExplicitSendIntent(button) ? 4000 : 0;
          const sameFormBonus = composerForm instanceof HTMLFormElement && composerForm === button.closest("form") ? 2400 : 0;
          const sameScopeBonus = composerScope instanceof Element && composerScope.contains(button) ? 1400 : 0;
          const submitTypeBonus = button.type === "submit" ? 500 : 0;
          const domDistanceBonus = 1200 - Math.min(getDomDistance(composer, button) * 40, 1200);
          const score = explicitSendBonus + sameFormBonus + sameScopeBonus + submitTypeBonus + domDistanceBonus;

          return { button, score };
        })
        .sort((left, right) => right.score - left.score);

      return ranked[0]?.button || null;
    }

    function isNearComposer(button, composer) {
      return sharesComposerScope(button, composer) || sharesComposerForm(button, composer);
    }

    function sharesComposerForm(button, composer) {
      if (!(button instanceof HTMLButtonElement) || !(composer instanceof Element)) {
        return false;
      }

      const composerForm = findClosestForm(composer);
      return composerForm instanceof HTMLFormElement && composerForm === button.closest("form");
    }

    function sharesComposerScope(button, composer) {
      if (!(button instanceof HTMLButtonElement) || !(composer instanceof Element)) {
        return false;
      }

      const composerScope = findComposerScope(composer);
      return composerScope instanceof Element && composerScope.contains(button);
    }

    function getDomDistance(left, right) {
      if (!(left instanceof Node) || !(right instanceof Node)) {
        return Number.MAX_SAFE_INTEGER;
      }

      if (left === right) {
        return 0;
      }

      const leftAncestors = [];
      let currentLeft = left;

      while (currentLeft) {
        leftAncestors.push(currentLeft);
        currentLeft = currentLeft.parentNode;
      }

      const rightAncestors = [];
      let currentRight = right;

      while (currentRight) {
        rightAncestors.push(currentRight);
        currentRight = currentRight.parentNode;
      }

      for (let leftIndex = 0; leftIndex < leftAncestors.length; leftIndex += 1) {
        const leftAncestor = leftAncestors[leftIndex];
        const rightIndex = rightAncestors.indexOf(leftAncestor);

        if (rightIndex !== -1) {
          return leftIndex + rightIndex;
        }
      }

      return Number.MAX_SAFE_INTEGER;
    }
    async function waitFor(factory, timeoutMs, label) {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        assertDeliveryActive();
        const value = factory();

        if (value) {
          return value;
        }

        await waitForNextStateTurn(timeoutMs - (Date.now() - startedAt));
      }

      throw new Error(`Nem található: ${label}.`);
    }

    function isVisible(element) {
      return isDomAccessibleElement(element);
    }

    function normalizeWhitespace(value) {
      return String(value || "").replace(/\s+/g, " ").trim();
    }

    function normalizePromptStructure(value) {
      return String(value || "")
        .replace(/\r\n?/g, "\n")
        .split("\n")
        .map((line) => line.replace(/[ \t]+/g, " ").trimEnd())
        .join("\n")
        .trim();
    }

    function hasSendButtonSubmissionTransition(beforeState, afterState) {
      if (!beforeState || typeof beforeState !== "object" || !afterState || typeof afterState !== "object") {
        return false;
      }

      const labelChanged = String(afterState.sendButtonLabel || "") !== String(beforeState.sendButtonLabel || "");
      return (afterState.sendButtonDisabled && !beforeState.sendButtonDisabled)
        || (afterState.sendButtonIsNonSend && !beforeState.sendButtonIsNonSend)
        || (labelChanged && (afterState.sendButtonIsNonSend || afterState.sendButtonDisabled));
    }

    function hasSubmissionTransition(beforeState, afterState) {
      const beforeComposerText = normalizePromptStructure(beforeState.composerText);
      const afterComposerText = normalizePromptStructure(afterState.composerText);
      const composerChanged = Boolean(beforeComposerText) && afterComposerText !== beforeComposerText;
      const userMessageAppeared = afterState.userCount > beforeState.userCount
        || (Boolean(afterState.lastUserNodeId) && afterState.lastUserNodeId !== beforeState.lastUserNodeId);
      const assistantActivityStarted = afterState.assistantCount > beforeState.assistantCount
        || (Boolean(afterState.lastAssistantNodeId) && afterState.lastAssistantNodeId !== beforeState.lastAssistantNodeId)
        || (afterState.lastAssistantPending && !beforeState.lastAssistantPending);
      const attachmentRemoved = afterState.attachmentCount < beforeState.attachmentCount
        || afterState.fileInputCount < beforeState.fileInputCount;
      const sendButtonTransitionStarted = hasSendButtonSubmissionTransition(beforeState, afterState);

      return composerChanged || userMessageAppeared || assistantActivityStarted || attachmentRemoved || sendButtonTransitionStarted || isGenerationInProgress();
    }

    function hasConfirmedSubmissionStart(beforeState, afterState) {
      if (!afterState || typeof afterState !== "object") {
        return false;
      }

      const beforeComposerText = normalizePromptStructure(beforeState.composerText);
      const afterComposerText = normalizePromptStructure(afterState.composerText);
      const composerChanged = Boolean(beforeComposerText) && afterComposerText !== beforeComposerText;
      const userMessageAppeared = afterState.userCount > beforeState.userCount
        || (Boolean(afterState.lastUserNodeId) && afterState.lastUserNodeId !== beforeState.lastUserNodeId);
      const assistantActivityStarted = afterState.assistantCount > beforeState.assistantCount
        || (Boolean(afterState.lastAssistantNodeId) && afterState.lastAssistantNodeId !== beforeState.lastAssistantNodeId)
        || (afterState.lastAssistantPending && !beforeState.lastAssistantPending);
      const generationStarted = Boolean(afterState.lastAssistantPending) || isGenerationInProgress();
      const attachmentRemoved = afterState.attachmentCount < beforeState.attachmentCount
        || afterState.fileInputCount < beforeState.fileInputCount;
      const sendButtonTransitionStarted = hasSendButtonSubmissionTransition(beforeState, afterState);

      return userMessageAppeared || assistantActivityStarted || generationStarted || attachmentRemoved || composerChanged || sendButtonTransitionStarted;
    }

    function hasComposerPayloadState(state) {
      if (!state || typeof state !== "object") {
        return false;
      }

      return Boolean(normalizePromptStructure(state.composerText))
        || Number(state.attachmentCount) > 0
        || Number(state.fileInputCount) > 0;
    }

    function getComposerAutoRecoveryPayloadKey(submissionState) {
      if (!submissionState || typeof submissionState !== "object") {
        return "";
      }

      return [
        normalizePromptStructure(submissionState.composerText),
        Number(submissionState.attachmentCount) || 0,
        Number(submissionState.fileInputCount) || 0,
        submissionState.hasPendingAttachmentWork ? "1" : "0"
      ].join("|");
    }

    function getComposerAutoRecoveryKey(composer, submissionState) {
      const sendButton = findSendButton(composer, { allowDisabled: true });

      return [
        getComposerAutoRecoveryPayloadKey(submissionState),
        isGenerationInProgress() ? "1" : "0",
        sendButton instanceof HTMLButtonElement && sendButton.disabled ? "1" : "0",
        sendButton instanceof HTMLButtonElement ? readButtonLabel(sendButton) : ""
      ].join("|");
    }

    function isComposerAutoRecoveryReady(composer, submissionState) {
      if (!(composer instanceof HTMLElement) || !hasComposerPayloadState(submissionState)) {
        return false;
      }

      if (isSubmissionRetryGuardActive(composer, submissionState)) {
        return false;
      }

      if (submissionState.hasPendingAttachmentWork || isGenerationInProgress()) {
        return false;
      }

      const sendButton = findSendButton(composer, { allowDisabled: true });

      if (!(sendButton instanceof HTMLButtonElement) || sendButton.disabled) {
        return false;
      }

      if (looksLikeNonSendAction(readButtonLabel(sendButton))) {
        return false;
      }

      if (hasAttachmentSnapshot(submissionState) && !isImageReadyForSubmit(composer)) {
        return false;
      }

      return isComposerReadyForSubmit(composer);
    }

    function ensureComposerAutoRecoveryWatcher() {
      const existingWatcher = window.__gamerTranslatorComposerAutoRecovery;

      if (
        existingWatcher
        && typeof existingWatcher === "object"
        && typeof existingWatcher.requestEvaluation === "function"
        && !existingWatcher.destroyed
      ) {
        return existingWatcher;
      }

      const domTracker = ensureDomActivityTracker();
      const watcherState = {
        busy: false,
        destroyed: false,
        suspendedCount: 0,
        queued: false,
        armedPayloadKey: "",
        lastAttemptKey: "",
        unsubscribe: null,
        destroy: null,
        requestEvaluation: null,
        retryTimeoutId: null,
      };

      const resetWatcherState = () => {
        watcherState.armedPayloadKey = "";
        watcherState.lastAttemptKey = "";

        if (watcherState.retryTimeoutId !== null) {
          window.clearTimeout(watcherState.retryTimeoutId);
          watcherState.retryTimeoutId = null;
        }
      };

      const armComposerAutoRecovery = (composerCandidate) => {
        // Az automatizálás saját küldési eseményei nem indíthatnak új háttérküldést.
        if (watcherState.destroyed || watcherState.busy || watcherState.suspendedCount > 0) {
          return;
        }

        const composer = findComposer() || composerCandidate;

        if (!(composer instanceof HTMLElement)) {
          return;
        }

        const submissionState = captureComposerSubmitState(composer);
        const payloadKey = getComposerAutoRecoveryPayloadKey(submissionState);

        if (!payloadKey) {
          return;
        }

        watcherState.armedPayloadKey = payloadKey;
        watcherState.lastAttemptKey = "";
        armSubmissionRetryGuard(composer, submissionState);

        if (watcherState.retryTimeoutId !== null) {
          window.clearTimeout(watcherState.retryTimeoutId);
        }

        // A lejárat DOM-változás nélkül is felébreszti az egyszeri helyreállítást.
        watcherState.retryTimeoutId = window.setTimeout(() => {
          watcherState.retryTimeoutId = null;
          watcherState.requestEvaluation();
        }, getSubmissionRetryGuardRemainingMs(composer, submissionState) + FRAME_INTERVAL_MS);
        watcherState.requestEvaluation();
      };

      const handleSubmitIntentClick = (event) => {
        const target = event.target;
        const composer = findComposer();

        if (!(target instanceof Element) || !(composer instanceof HTMLElement)) {
          return;
        }

        const clickedButton = target.closest("button");
        const sendButton = findSendButton(composer, { allowDisabled: true });

        if (!(clickedButton instanceof HTMLButtonElement) || !(sendButton instanceof HTMLButtonElement)) {
          return;
        }

        if (clickedButton !== sendButton) {
          return;
        }

        if (looksLikeNonSendAction(readButtonLabel(sendButton))) {
          return;
        }

        armComposerAutoRecovery(composer);
      };

      const handleSubmitIntentForm = (event) => {
        const composer = findComposer();
        const form = event.target;

        if (!(composer instanceof HTMLElement) || !(form instanceof HTMLFormElement)) {
          return;
        }

        if (findClosestForm(composer) !== form) {
          return;
        }

        armComposerAutoRecovery(composer);
      };

      const handleSubmitIntentKeyDown = (event) => {
        const target = event.target;
        const composer = findComposer();

        if (
          !(target instanceof Node)
          || !(composer instanceof HTMLElement)
          || event.key !== "Enter"
          || event.shiftKey
          || event.ctrlKey
          || event.altKey
          || event.metaKey
          || event.isComposing
        ) {
          return;
        }

        const scope = findComposerScope(composer);

        if (!(scope instanceof Element) || !scope.contains(target)) {
          return;
        }

        if (isExpandedComposerEditor(composer)) {
          return;
        }

        armComposerAutoRecovery(composer);
      };

      const evaluateComposerState = async () => {
        if (watcherState.destroyed || watcherState.busy || watcherState.suspendedCount > 0) {
          return;
        }

        const composer = findComposer();

        if (!(composer instanceof HTMLElement)) {
          resetWatcherState();
          return;
        }

        const submissionState = captureComposerSubmitState(composer);

        if (!hasComposerPayloadState(submissionState)) {
          resetWatcherState();
          return;
        }

        const payloadKey = getComposerAutoRecoveryPayloadKey(submissionState);

        if (!payloadKey) {
          resetWatcherState();
          return;
        }

        if (!watcherState.armedPayloadKey) {
          watcherState.lastAttemptKey = "";
          return;
        }

        if (watcherState.armedPayloadKey !== payloadKey) {
          resetWatcherState();
          return;
        }

        const attemptKey = getComposerAutoRecoveryKey(composer, submissionState);

        if (!isComposerAutoRecoveryReady(composer, submissionState)) {
          return;
        }

        if (watcherState.lastAttemptKey === attemptKey) {
          return;
        }

        watcherState.busy = true;
        watcherState.lastAttemptKey = attemptKey;

        try {
          await window.__gamerTranslatorDeliver({
            repairExistingComposerPayload: true,
            autoSubmit: true,
            copyResponseToClipboard: false,
            pageReadyTimeoutMs: 15000,
            responseTimeoutMs: 0
          });
        } catch (_error) {
          // A sikertelen onjavito kuldes nem allithatja meg a tovabbi figyelest.
        } finally {
          watcherState.busy = false;

          const liveComposer = findComposer();

          if (!(liveComposer instanceof HTMLElement)) {
            resetWatcherState();
            return;
          }

          const liveSubmissionState = captureComposerSubmitState(liveComposer);

          if (!hasComposerPayloadState(liveSubmissionState)) {
            resetWatcherState();
          } else if (getComposerAutoRecoveryPayloadKey(liveSubmissionState) !== watcherState.armedPayloadKey) {
            resetWatcherState();
          } else if (getComposerAutoRecoveryKey(liveComposer, liveSubmissionState) !== attemptKey) {
            watcherState.lastAttemptKey = "";
          }

          watcherState.requestEvaluation();
        }
      };

      watcherState.requestEvaluation = () => {
        if (watcherState.destroyed || watcherState.queued) {
          return;
        }

        watcherState.queued = true;
        Promise.resolve().then(() => {
          watcherState.queued = false;
          evaluateComposerState().catch(() => {});
        });
      };

      watcherState.unsubscribe = domTracker.subscribe(() => {
        if (!watcherState.armedPayloadKey && !watcherState.busy) {
          return;
        }

        watcherState.requestEvaluation();
      });
      document.addEventListener("click", handleSubmitIntentClick, true);
      document.addEventListener("submit", handleSubmitIntentForm, true);
      document.addEventListener("keydown", handleSubmitIntentKeyDown, true);
      watcherState.destroy = () => {
        if (watcherState.destroyed) {
          return;
        }

        watcherState.destroyed = true;
        watcherState.suspendedCount = Number.MAX_SAFE_INTEGER;
        resetWatcherState();

        if (typeof watcherState.unsubscribe === "function") {
          watcherState.unsubscribe();
          watcherState.unsubscribe = null;
        }

        document.removeEventListener("click", handleSubmitIntentClick, true);
        document.removeEventListener("submit", handleSubmitIntentForm, true);
        document.removeEventListener("keydown", handleSubmitIntentKeyDown, true);
      };

      window.__gamerTranslatorComposerAutoRecovery = watcherState;
      watcherState.requestEvaluation();
      return watcherState;
    }

    async function waitForSubmissionTransition(beforeState, composer, timeoutMs) {
      assertDeliveryActive();
      let observedState = captureComposerSubmitState(findComposer() || composer);

      if (hasSubmissionTransition(beforeState, observedState)) {
        return true;
      }

      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const remainingTime = timeoutMs - (Date.now() - startedAt);

        if (remainingTime <= 0) {
          break;
        }

        const nextState = await waitForStateChange(
          () => captureComposerSubmitState(findComposer() || composer),
          getSubmissionStateKey,
          observedState,
          remainingTime,
        );

        if (!nextState) {
          break;
        }

        observedState = nextState;

        if (hasSubmissionTransition(beforeState, observedState)) {
          return true;
        }
      }

      return hasSubmissionTransition(beforeState, captureComposerSubmitState(findComposer() || composer));
    }

    async function ensureSubmissionDelivered(composer, beforeState, attempts, failureMessage) {
      assertDeliveryActive();
      let liveComposer = findComposer() || composer;
      let afterState = captureComposerSubmitState(liveComposer);

      if (hasConfirmedSubmissionStart(beforeState, afterState)) {
        clearSubmissionRetryGuard();
        return;
      }

      if (hasSubmissionTransition(beforeState, afterState) && !hasComposerPayloadState(afterState)) {
        clearSubmissionRetryGuard();
        return;
      }

      for (let checkIndex = 0; checkIndex < SELF_HEAL_CHECK_LIMIT; checkIndex += 1) {
        assertDeliveryActive();
        const attempt = attempts[checkIndex % attempts.length];

        if (!hasComposerPayloadState(afterState)) {
          if (hasSubmissionTransition(beforeState, afterState) || hasConfirmedSubmissionStart(beforeState, afterState)) {
            clearSubmissionRetryGuard();
            return;
          }

          break;
        }

        armSubmissionRetryGuard(liveComposer, afterState);
        reportDiagnostic("submission_retry", { attempt: checkIndex + 1, attachment_count: afterState.attachmentCount, file_count: afterState.fileInputCount, pending: afterState.hasPendingAttachmentWork });
        attempt.run(liveComposer);
        await waitForSubmissionTransition(
          beforeState,
          liveComposer,
          Math.max(attempt.timeoutMs, getSubmissionRetryGuardRemainingMs(liveComposer, afterState)),
        );
        assertDeliveryActive();

        liveComposer = findComposer() || liveComposer;
        afterState = captureComposerSubmitState(liveComposer);

        if (hasConfirmedSubmissionStart(beforeState, afterState)) {
          clearSubmissionRetryGuard();
          return;
        }

        if (hasSubmissionTransition(beforeState, afterState) && !hasComposerPayloadState(afterState)) {
          clearSubmissionRetryGuard();
          return;
        }
      }

      clearSubmissionRetryGuard();
      throw new Error(failureMessage);
    }

    function captureResponseBaselineBeforeSubmit() {
      assertDeliveryActive();
      if (!payload.waitForResponse || responseBaselineCaptured) return;
      // A composer és a feltöltés várakozása közben érkező előzmény nem új kérés.
      // Retry során viszont már az első próbálkozás userét kell megőriznünk.
      assistantSnapshotBeforeSend = captureAssistantSnapshot();
      responseBaselineCaptured = true;
      reportDiagnostic("response_baseline", { user_count: assistantSnapshotBeforeSend.userCount, assistant_count: assistantSnapshotBeforeSend.count });
    }

    function fireClickSequence(element) {
      captureResponseBaselineBeforeSubmit();
      element.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse", isPrimary: true }));
      assertDeliveryActive();
      element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
      assertDeliveryActive();
      element.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse", isPrimary: true }));
      assertDeliveryActive();
      element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, button: 0 }));
      assertDeliveryActive();
      element.click();
    }

    function dispatchFormSubmit(form) {
      assertDeliveryActive();
      try {
        captureResponseBaselineBeforeSubmit();
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      } catch (_error) {
        // Ha a submit event nem megy át, jön a következő fallback.
      }
    }

    function dispatchEnterSequence(element) {
      captureResponseBaselineBeforeSubmit();
      const events = [
        new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 }),
        new KeyboardEvent("keypress", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 }),
        new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 })
      ];

      for (const event of events) {
        assertDeliveryActive();
        element.dispatchEvent(event);
      }
    }

    function isComposerReadyForSubmit(composer) {
      if (!(composer instanceof HTMLElement)) {
        return false;
      }

      const scope = findComposerScope(composer);
      const hasPrompt = Boolean(normalizePromptStructure(readComposerText(composer)));
      const hasAttachment = captureComposerAttachmentSnapshot(composer).hasAttachmentPreview;

      return hasPrompt || hasAttachment;
    }

    function isExpandedComposerEditor(composer) {
      if (!(composer instanceof HTMLElement)) {
        return false;
      }

      const scope = findComposerScope(composer);

      if (!(scope instanceof Element)) {
        return false;
      }

      const visibleButtons = Array.from(scope.querySelectorAll("button"))
        .filter((button) => button instanceof HTMLButtonElement)
        .filter((button) => isEligibleSendButton(button, { allowDisabled: true }));

      const hasCancel = visibleButtons.some((button) => looksLikeCancelAction(button));
      const hasExplicitSend = visibleButtons.some((button) => buttonHasExplicitSendIntent(button));

      return hasCancel && hasExplicitSend;
    }

    async function waitForNextStateTurn(timeoutMs) {
      assertDeliveryActive();
      const boundedTimeout = Math.max(FRAME_INTERVAL_MS, Number(timeoutMs) || FRAME_INTERVAL_MS);
      await ensureDomActivityTracker().waitForChange(boundedTimeout, operation.cancellationPromise);
      assertDeliveryActive();
    }

    async function waitForStateChange(readState, getStateKey, previousState, timeoutMs) {
      const previousKey = typeof getStateKey === "function" ? getStateKey(previousState) : "";
      const domTracker = ensureDomActivityTracker();
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        assertDeliveryActive();
        const currentState = readState();

        if ((typeof getStateKey === "function" ? getStateKey(currentState) : "") !== previousKey) {
          return currentState;
        }

        const remainingTime = timeoutMs - (Date.now() - startedAt);

        if (remainingTime <= 0) {
          break;
        }

        const changeReason = await domTracker.waitForChange(remainingTime, operation.cancellationPromise);
        assertDeliveryActive();
        if (changeReason !== "change") {
          break;
        }
      }

      const finalState = readState();
      return (typeof getStateKey === "function" ? getStateKey(finalState) : "") !== previousKey
        ? finalState
        : null;
    }
  };

  window.__gamerTranslatorDeliverVersion = AUTOMATION_SCRIPT_VERSION;
  window.__gamerTranslatorDeliver({
    initializeComposerAutoRecovery: true,
    autoSubmit: false,
    copyResponseToClipboard: false,
    pageReadyTimeoutMs: 15000,
    responseTimeoutMs: 0
  }).catch(() => {});
})();
