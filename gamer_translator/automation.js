(() => {
  const AUTOMATION_SCRIPT_VERSION = "2026-04-12-4";
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
    "CODE",
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
          "class",
          "data-message-author-role",
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

    const waitForChange = (timeoutMs) => new Promise((resolve) => {
      start();
      ensureFramePacer().pulseFor(Math.min(
        ASSISTANT_RESPONSE_FOLLOW_UP_MAX_MS,
        Math.max(FRAME_PACER_BURST_MS, Number(timeoutMs) || FRAME_PACER_BURST_MS)
      ));

      if (state.observer === null) {
        window.setTimeout(() => resolve("timeout"), Math.max(FRAME_INTERVAL_MS, timeoutMs));
        return;
      }

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
      state.listeners.add(handleChange);
      timeoutId = window.setTimeout(() => finish("timeout"), Math.max(FRAME_INTERVAL_MS, timeoutMs));
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

  function stopAssistantResponseFollowUp(followUpProgressCallId, options = {}) {
    const normalizedFollowUpProgressCallId = String(followUpProgressCallId || "").trim();

    if (!normalizedFollowUpProgressCallId) {
      return;
    }

    const followUps = ensureAssistantResponseFollowUps();
    const existingFollowUp = followUps[normalizedFollowUpProgressCallId];

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
      writeProgressEntry(normalizedFollowUpProgressCallId, {
        kind: "assistant_response_watch_done",
        done: true
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

  window.__gamerTranslatorDeliver = async function deliverPromptToChatGpt(payload) {
    const composerAutoRecovery = ensureComposerAutoRecoveryWatcher();
    const reportProgress = (progress) => {
      writeProgressEntry(payload.progressCallId, progress);
    };
    const shouldSuspendComposerAutoRecovery = !payload.initializeComposerAutoRecovery;

    if (shouldSuspendComposerAutoRecovery) {
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

      const assistantSnapshotBeforeSend = payload.copyResponseToClipboard
        ? captureAssistantSnapshot()
        : { count: 0, lastNodeId: "", lastText: "", lastPending: false };

      let activeComposer = await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "beviteli mező");

      if (payload.repairExistingComposerPayload && !payload.prompt && !payload.imageDataUrl) {
        if (payload.autoSubmit) {
          await submitExistingComposerPayload(activeComposer);
        }

        return {
          ok: true,
          assistantResponseText: "",
          assistantResponseCopied: false,
          followUpProgressCallId: ""
        };
      }

      if (payload.imageDataUrl) {
        activeComposer = await attachImage(activeComposer);
      }

      if (payload.prompt) {
        activeComposer = await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "frissített beviteli mező");
        writePrompt(activeComposer, payload.prompt);
        activeComposer = await waitForPromptApplied(
          activeComposer,
          payload.prompt,
          Math.min(payload.pageReadyTimeoutMs, 1800)
        );
      }

      if (payload.autoSubmit) {
        if (payload.imageDataUrl && !payload.prompt) {
          await submitImageMessage(activeComposer);
        } else {
          await submitTextMessage(activeComposer);
        }
      }

      let assistantResponseText = "";
      let followUpProgressCallId = "";

      if (payload.copyResponseToClipboard) {
        const responseResult = await waitForAssistantResponse(assistantSnapshotBeforeSend, payload.responseTimeoutMs, reportProgress);
        assistantResponseText = responseResult.text;
        followUpProgressCallId = String(responseResult.followUpProgressCallId || "").trim();
      }

      return {
        ok: true,
        assistantResponseText,
        assistantResponseCopied: false,
        followUpProgressCallId
      };
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      };
    } finally {
      if (shouldSuspendComposerAutoRecovery) {
        composerAutoRecovery.suspendedCount = Math.max(0, composerAutoRecovery.suspendedCount - 1);
        composerAutoRecovery.requestEvaluation();
      }
    }

    async function attachImage(composerCandidate) {
      let composer = composerCandidate ?? await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "beviteli mező képbeillesztéshez");
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const file = dataUrlToFile(
        payload.imageDataUrl,
        payload.imageFilename || "snip.png",
        payload.imageMimeType || "image/png"
      );
      const expectedFileKey = describeSelectedFile(file);
      let attachAttemptStarted = false;

      for (let checkIndex = 0; checkIndex < SELF_HEAL_CHECK_LIMIT; checkIndex += 1) {
        composer = findComposer() || composer;
        const currentSnapshot = captureComposerAttachmentSnapshot(composer);

        if (isAttachmentReadySnapshot(currentSnapshot) && snapshotHasExpectedFile(currentSnapshot, expectedFileKey)) {
          return composer;
        }

        if (!hasAttachmentSnapshot(currentSnapshot) || !currentSnapshot.hasPendingAttachmentWork) {
          const beforeSnapshot = currentSnapshot;
          const attachedByInput = attachViaFileInput(composer, file);
          const attachedByDrop = attachedByInput ? false : attachViaDrop(composer, file);

          if (!attachedByInput && !attachedByDrop && !attachAttemptStarted) {
            throw new Error("A kép csatolása nem sikerült.");
          }

          attachAttemptStarted = attachAttemptStarted || attachedByInput || attachedByDrop;
          const afterAttachComposer = findComposer() || composer;
          const afterAttachSnapshot = captureComposerAttachmentSnapshot(afterAttachComposer);

          if (
            getAttachmentSnapshotKey(afterAttachSnapshot) !== getAttachmentSnapshotKey(beforeSnapshot)
            || hasAttachmentSnapshot(afterAttachSnapshot)
            || afterAttachSnapshot.hasPendingAttachmentWork
          ) {
            const attachedComposer = await waitForAttachmentReady(
              afterAttachComposer,
              beforeSnapshot,
              imageUploadTimeoutMs,
            );

            if (attachedComposer) {
              composer = attachedComposer;
            }
          }
        }

        const verifiedComposer = findComposer() || composer;
        const verifiedSnapshot = captureComposerAttachmentSnapshot(verifiedComposer);

        if (isAttachmentReadySnapshot(verifiedSnapshot)) {
          return verifiedComposer;
        }

      }

      throw new Error("A kép csatolása az ismételt ellenőrzések után sem sikerült.");
    }

    function getImageUploadTimeoutMs() {
      const responseTimeoutMs = Number(payload.responseTimeoutMs);

      if (Number.isFinite(responseTimeoutMs) && responseTimeoutMs > 0) {
        return responseTimeoutMs;
      }

      const pageReadyTimeoutMs = Number(payload.pageReadyTimeoutMs);
      return Number.isFinite(pageReadyTimeoutMs) && pageReadyTimeoutMs > 0
        ? pageReadyTimeoutMs
        : 60000;
    }

    function attachViaFileInput(composer, file) {
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
      fileInput.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      return true;
    }

    function attachViaDrop(composer, file) {
      const target = findComposerScope(composer) || composer;

      if (!(target instanceof HTMLElement)) {
        return false;
      }

      const transfer = new DataTransfer();
      transfer.items.add(file);

      target.dispatchEvent(new DragEvent("dragenter", { bubbles: true, cancelable: true, dataTransfer: transfer }));
      target.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: transfer }));
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
      const [header, encoded] = String(dataUrl || "").split(",", 2);

      if (!header || !encoded) {
        throw new Error("A kép adatURL formátuma hibás.");
      }

      const binary = atob(encoded);
      const bytes = new Uint8Array(binary.length);

      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }

      return new File([bytes], filename, {
        type: mimeType || "image/png",
        lastModified: Date.now()
      });
    }

    async function submitTextMessage(composer, options = {}) {
      const liveComposer = await waitFor(() => findComposer() || composer, 15000, "beviteli mező");
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const requireReadyAttachment = Boolean(options.requireReadyAttachment ?? payload.imageDataUrl);
      const preparedComposer = await waitFor(() => {
        const candidate = findComposer() || liveComposer;
        const promptReady = Boolean(normalizePromptStructure(readComposerText(candidate)));

        if (!isComposerReadyForSubmit(candidate) || !promptReady) {
          return null;
        }

        if (requireReadyAttachment && !isImageReadyForSubmit(candidate)) {
          return null;
        }

        return candidate;
      }, requireReadyAttachment ? imageUploadTimeoutMs : 12000, "beküldhető tartalom");
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
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const preparedComposer = await waitFor(() => {
        const candidate = findComposer() || liveComposer;
        return isImageReadyForSubmit(candidate) ? candidate : null;
      }, imageUploadTimeoutMs, "feltöltött kép");
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

      const structuredText = normalizeStructuredDomText(readStructuredDomText(element));

      if (structuredText) {
        return structuredText;
      }

      return String(element.textContent || "");
    }

    async function waitForPromptApplied(composer, prompt, timeoutMs) {
      const expectedPrompt = normalizePromptStructure(prompt);

      if (!expectedPrompt) {
        return findComposer() || composer;
      }

      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const liveComposer = findComposer() || composer;
        const currentPrompt = normalizePromptStructure(readComposerText(liveComposer));

        if (
          currentPrompt
          && (
            currentPrompt === expectedPrompt
            || currentPrompt.includes(expectedPrompt)
            || expectedPrompt.includes(currentPrompt)
          )
        ) {
          return liveComposer;
        }

        await waitForNextStateTurn(timeoutMs - (Date.now() - startedAt));
      }

      return findComposer() || composer;
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

      return {
        attachmentCount: attachmentIndicators.length,
        attachmentIndicatorKey: attachmentIndicators.map((element) => describeAttachmentIndicator(element)).join("||"),
        fileInputCount: selectedFileKeys.length,
        fileSelectionKey: selectedFileKeys.join("||"),
        selectedFileKeys,
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
        String(snapshot.lastText || ""),
        snapshot.lastPending ? "1" : "0"
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
      return hasAttachmentSnapshot(snapshot) && !snapshot.hasPendingAttachmentWork;
    }

    async function waitForAttachmentReady(composer, beforeSnapshot, timeoutMs) {
      let observedSnapshot = beforeSnapshot;
      const beforeKey = getAttachmentSnapshotKey(beforeSnapshot);
      let attachmentAccepted = false;
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const liveComposer = findComposer() || composer;
        attachmentAccepted = attachmentAccepted
          || getAttachmentSnapshotKey(observedSnapshot) !== beforeKey
          || observedSnapshot.attachmentCount > beforeSnapshot.attachmentCount
          || observedSnapshot.fileInputCount > beforeSnapshot.fileInputCount;

        if (attachmentAccepted && isAttachmentReadySnapshot(observedSnapshot)) {
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
      attachmentAccepted = attachmentAccepted || getAttachmentSnapshotKey(finalSnapshot) !== beforeKey;
      return attachmentAccepted && isAttachmentReadySnapshot(finalSnapshot) ? finalComposer : null;
    }

    function isImageReadyForSubmit(composer) {
      if (!(composer instanceof HTMLElement)) {
        return false;
      }

      const scope = findComposerScope(composer);
      const hasAttachment = countAttachmentIndicators(scope) > 0 || countSelectedFiles(scope) > 0;
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
        'form, [data-testid*="composer" i], [data-testid*="prompt" i], [class*="composer" i], [class*="prompt" i]'
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

    function hasPendingAttachmentWork(scope) {
      if (!(scope instanceof Element)) {
        return false;
      }

      const pendingSelectors = [
        '[aria-busy="true"]',
        '[role="progressbar"]',
        '[data-state="uploading"]',
        '[data-status="uploading"]',
        '[data-testid*="upload" i]',
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

    function captureAssistantSnapshot() {
      const assistantNodes = findAssistantMessageNodes();
      let lastEntry = null;

      for (let index = assistantNodes.length - 1; index >= 0; index -= 1) {
        const node = assistantNodes[index];
        const pending = isAssistantResponsePending(node);
        const text = normalizeWhitespace(extractAssistantText(node));

        if (!text && !pending) {
          continue;
        }

        lastEntry = {
          nodeId: getDomNodeId(node),
          text,
          pending
        };
        break;
      }

      return {
        count: assistantNodes.length,
        lastNodeId: lastEntry?.nodeId || "",
        lastText: lastEntry?.text || "",
        lastPending: Boolean(lastEntry?.pending)
      };
    }

    async function waitForAssistantResponse(previousSnapshot, timeoutMs, reportProgress) {
      let observedSnapshot = captureAssistantSnapshot();
      let latestUsableSnapshot = null;
      const startedAt = Date.now();

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
      }

      const finalSnapshot = captureAssistantSnapshot();
      if (isFreshAssistantSnapshot(finalSnapshot, previousSnapshot) && isStableAssistantSnapshot(finalSnapshot)) {
        const followUpProgressCallId = startAssistantResponseFollowUp(previousSnapshot, finalSnapshot);
        reportAssistantSnapshotProgress(finalSnapshot, reportProgress);
        return {
          text: finalSnapshot.lastText,
          copied: false,
          followUpProgressCallId
        };
      }

      if (isUsableAssistantSnapshot(finalSnapshot, previousSnapshot)) {
        const followUpProgressCallId = startAssistantResponseFollowUp(previousSnapshot, finalSnapshot);
        reportAssistantSnapshotProgress(finalSnapshot, reportProgress);
        return {
          text: finalSnapshot.lastText,
          copied: false,
          followUpProgressCallId
        };
      }

      if (latestUsableSnapshot) {
        const followUpProgressCallId = startAssistantResponseFollowUp(previousSnapshot, latestUsableSnapshot);
        reportAssistantSnapshotProgress(latestUsableSnapshot, reportProgress);
        return {
          text: latestUsableSnapshot.lastText,
          copied: false,
          followUpProgressCallId
        };
      }

      throw new Error("A ChatGPT válasza nem érkezett meg időben.");
    }

    function startAssistantResponseFollowUp(previousSnapshot, initialSnapshot) {
      const baseProgressCallId = String(payload.progressCallId || "").trim();

      if (!baseProgressCallId || !isUsableAssistantSnapshot(initialSnapshot, previousSnapshot)) {
        return "";
      }

      const followUpProgressCallId = `${baseProgressCallId}-followup`;
      const domTracker = ensureDomActivityTracker();
      const followUps = ensureAssistantResponseFollowUps();
      const startUserCount = findUserMessageNodes().length;
      const followUpState = {
        stopped: false,
        previousSnapshot,
        latestText: String(initialSnapshot.lastText || ""),
        latestNodeId: String(initialSnapshot.lastNodeId || ""),
        startUserCount,
        startedAt: Date.now(),
        timeoutId: 0,
        unsubscribe: null
      };

      stopAssistantResponseFollowUp(followUpProgressCallId, { emitDone: false });

      const scheduleFollowUpStop = (delayMs) => {
        if (followUpState.timeoutId) {
          window.clearTimeout(followUpState.timeoutId);
        }

        const boundedDelayMs = Math.max(FRAME_INTERVAL_MS, Number(delayMs) || ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS);
        followUpState.timeoutId = window.setTimeout(() => {
          followUpState.timeoutId = 0;
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

        if (findUserMessageNodes().length > startUserCount) {
          stopAssistantResponseFollowUp(followUpProgressCallId);
          return;
        }

        const currentSnapshot = captureAssistantSnapshot();

        if (!isUsableAssistantSnapshot(currentSnapshot, previousSnapshot)) {
          return;
        }

        if (
          currentSnapshot.lastText === followUpState.latestText
          && currentSnapshot.lastNodeId === followUpState.latestNodeId
        ) {
          scheduleFollowUpStop(
            currentSnapshot.lastPending
              ? ASSISTANT_RESPONSE_FOLLOW_UP_IDLE_MS
              : ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS
          );
          return;
        }

        followUpState.latestText = String(currentSnapshot.lastText || "");
        followUpState.latestNodeId = String(currentSnapshot.lastNodeId || "");
        writeProgressEntry(followUpProgressCallId, {
          kind: "assistant_response",
          text: currentSnapshot.lastText
        });
        scheduleFollowUpStop(
          currentSnapshot.lastPending
            ? ASSISTANT_RESPONSE_FOLLOW_UP_IDLE_MS
            : ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS
        );
      };

      followUpState.unsubscribe = domTracker.subscribe(evaluateFollowUp);
      followUps[followUpProgressCallId] = followUpState;
      scheduleFollowUpStop(
        initialSnapshot.lastPending
          ? ASSISTANT_RESPONSE_FOLLOW_UP_IDLE_MS
          : ASSISTANT_RESPONSE_FOLLOW_UP_SETTLE_MS
      );
      return followUpProgressCallId;
    }

    function isFreshAssistantSnapshot(currentSnapshot, previousSnapshot) {
      if (!currentSnapshot || typeof currentSnapshot !== "object") {
        return false;
      }

      const candidate = currentSnapshot.lastText;
      return Boolean(candidate)
        && (
          currentSnapshot.count > previousSnapshot.count
          || currentSnapshot.lastNodeId !== previousSnapshot.lastNodeId
          || candidate !== previousSnapshot.lastText
        );
    }

    function isStableAssistantSnapshot(snapshot) {
      const candidate = snapshot?.lastText;

      if (!candidate) {
        return false;
      }

      if (isTransientAssistantText(candidate)) {
        return false;
      }

      return !snapshot.lastPending || isComposerBackInSendState();
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
        text: snapshot.lastText
      });
    }

    function isTransientAssistantText(text) {
      const normalized = normalizeWhitespace(text).toLowerCase();

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
      ].some((needle) => normalized.includes(needle));
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
        .filter((element) => isTopLevelAuthorMessageNode(element, normalizedAuthorRole));

      if (directMatches.length > 0) {
        return directMatches;
      }

      const fallbackMatches = Array.from(document.querySelectorAll('[data-testid^="conversation-turn-"], article'))
        .filter(isDomTrackableElement)
        .filter((element) => doesMessageNodeMatchAuthor(element, normalizedAuthorRole));

      return Array.from(new Set(fallbackMatches));
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

      const authorHints = [
        element.getAttribute("data-message-author-role"),
        element.querySelector('[data-message-author-role]')?.getAttribute("data-message-author-role"),
        element.getAttribute("aria-label")
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      const authorAliases = normalizedAuthorRole === "user"
        ? ["user", "you"]
        : [normalizedAuthorRole];

      if (!authorAliases.some((authorAlias) => authorHints.includes(authorAlias))) {
        return false;
      }

      const extractedText = normalizeWhitespace(extractMessageText(element));

      if (normalizedAuthorRole === "assistant") {
        return Boolean(extractedText) || isAssistantMessageBusy(element);
      }

      return Boolean(extractedText);
    }

    function extractAssistantText(element) {
      return extractMessageText(element);
    }

    function extractMessageText(element) {
      const structuredText = normalizeStructuredDomText(readStructuredDomText(element));

      if (structuredText) {
        return structuredText;
      }

      const preferredContainers = [
        element.querySelector(".markdown"),
        element.querySelector('[class*="markdown"]'),
        element.querySelector('[class*="prose"]'),
        element
      ];

      for (const container of preferredContainers) {
        if (!(container instanceof HTMLElement)) {
          continue;
        }

        const text = normalizeStructuredDomText(readStructuredDomText(container))
          || normalizeWhitespace(container.textContent);

        if (text) {
          return text;
        }
      }

      return "";
    }

    function isDomTrackableElement(element) {
      if (!(element instanceof HTMLElement) || !element.isConnected) {
        return false;
      }

      if (element.closest("template, script, style, noscript")) {
        return false;
      }

      return true;
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

      const style = window.getComputedStyle(element);

      return style.display === "none" || style.visibility === "hidden";
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

        if (parts.length === 0) {
          parts.push(normalizedText);
          return;
        }

        const previousPart = parts[parts.length - 1];

        if (previousPart === "\n" || /^[\s(/{[]*$/.test(previousPart) || /^[,.;:!?%)\]}]/.test(normalizedText)) {
          parts.push(normalizedText);
          return;
        }

        parts.push(" ", normalizedText);
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

        if (DOM_TEXT_SKIP_TAGS.has(tagName)) {
          return;
        }

        if (tagName === "BR") {
          appendBreak();
          return;
        }

        if (node.getAttribute("aria-hidden") === "true" && !node.hasAttribute("data-message-author-role")) {
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
      };

      const resetWatcherState = () => {
        watcherState.armedPayloadKey = "";
        watcherState.lastAttemptKey = "";
      };

      const armComposerAutoRecovery = (composerCandidate) => {
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
        const attempt = attempts[checkIndex % attempts.length];

        if (!hasComposerPayloadState(afterState)) {
          if (hasSubmissionTransition(beforeState, afterState) || hasConfirmedSubmissionStart(beforeState, afterState)) {
            clearSubmissionRetryGuard();
            return;
          }

          break;
        }

        armSubmissionRetryGuard(liveComposer, afterState);
        attempt.run(liveComposer);
        await waitForSubmissionTransition(
          beforeState,
          liveComposer,
          Math.max(attempt.timeoutMs, getSubmissionRetryGuardRemainingMs(liveComposer, afterState)),
        );

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

    function fireClickSequence(element) {
      element.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse", isPrimary: true }));
      element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
      element.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse", isPrimary: true }));
      element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, button: 0 }));
      element.click();
    }

    function dispatchFormSubmit(form) {
      try {
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      } catch (_error) {
        // Ha a submit event nem megy át, jön a következő fallback.
      }
    }

    function dispatchEnterSequence(element) {
      const events = [
        new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 }),
        new KeyboardEvent("keypress", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 }),
        new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 })
      ];

      for (const event of events) {
        element.dispatchEvent(event);
      }
    }

    function isComposerReadyForSubmit(composer) {
      if (!(composer instanceof HTMLElement)) {
        return false;
      }

      const scope = findComposerScope(composer);
      const hasPrompt = Boolean(normalizePromptStructure(readComposerText(composer)));
      const hasAttachment = countAttachmentIndicators(scope) > 0 || countSelectedFiles(scope) > 0;

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
      const boundedTimeout = Math.max(FRAME_INTERVAL_MS, Number(timeoutMs) || FRAME_INTERVAL_MS);
      await ensureDomActivityTracker().waitForChange(boundedTimeout);
    }

    async function waitForStateChange(readState, getStateKey, previousState, timeoutMs) {
      const previousKey = typeof getStateKey === "function" ? getStateKey(previousState) : "";
      const domTracker = ensureDomActivityTracker();
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const currentState = readState();

        if ((typeof getStateKey === "function" ? getStateKey(currentState) : "") !== previousKey) {
          return currentState;
        }

        const remainingTime = timeoutMs - (Date.now() - startedAt);

        if (remainingTime <= 0) {
          break;
        }

        if (await domTracker.waitForChange(remainingTime) !== "change") {
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
