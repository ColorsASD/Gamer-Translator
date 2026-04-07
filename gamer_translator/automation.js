(() => {
  const FRAME_INTERVAL_MS = 20;
  const RESPONSE_CHANGE_WAIT_MS = 300;
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
      existingPacer.start();

      if (typeof existingPacer.ensureNode === "function") {
        existingPacer.ensureNode();
      }

      return;
    }

    const state = {
      intervalId: null,
      pulseState: false,
      pulseNode: null
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

    const start = () => {
      ensureNode();

      if (state.intervalId !== null) {
        return;
      }

      tick();
      state.intervalId = window.setInterval(tick, FRAME_INTERVAL_MS);
    };

    const stop = () => {
      if (state.intervalId === null) {
        return;
      }

      window.clearInterval(state.intervalId);
      state.intervalId = null;
    };

    state.ensureNode = ensureNode;
    state.start = start;
    state.stop = stop;
    window.__gamerTranslatorFramePacer = state;

    start();
    document.addEventListener("visibilitychange", start, { passive: true });
    window.addEventListener("pageshow", start, { passive: true });
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

      const handleChange = () => finish("mutation");
      state.listeners.add(handleChange);
      timeoutId = window.setTimeout(() => finish("timeout"), Math.max(FRAME_INTERVAL_MS, timeoutMs));
    });

    const tracker = {
      start,
      stop,
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

  if (typeof window.__gamerTranslatorDeliver === "function") {
    return;
  }

  window.__gamerTranslatorDeliver = async function deliverPromptToChatGpt(payload) {
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    try {
      if (!payload.prompt && !payload.imageDataUrl) {
        throw new Error("Nincs elküldhető tartalom.");
      }

      const assistantSnapshotBeforeSend = payload.copyResponseToClipboard
        ? captureAssistantSnapshot()
        : { count: 0, lastNodeId: "", lastText: "", lastPending: false };

      let activeComposer = await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "beviteli mező");

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

      if (payload.copyResponseToClipboard) {
        const responseResult = await waitForAssistantResponse(assistantSnapshotBeforeSend, payload.responseTimeoutMs);
        assistantResponseText = responseResult.text;
      }

      return {
        ok: true,
        assistantResponseText,
        assistantResponseCopied: false
      };
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      };
    }

    async function attachImage(composerCandidate) {
      const composer = composerCandidate ?? await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "beviteli mező képbeillesztéshez");
      const beforeSnapshot = captureComposerAttachmentSnapshot(composer);
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const file = dataUrlToFile(
        payload.imageDataUrl,
        payload.imageFilename || "snip.png",
        payload.imageMimeType || "image/png"
      );

      const attachedByInput = attachViaFileInput(composer, file);
      const attachedByDrop = attachedByInput ? false : attachViaDrop(composer, file);

      if (!attachedByInput && !attachedByDrop) {
        throw new Error("A kép csatolása nem sikerült.");
      }

      return waitForAttachmentReady(composer, beforeSnapshot, imageUploadTimeoutMs);
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

      return new File([bytes], filename, { type: mimeType || "image/png" });
    }

    async function submitTextMessage(composer) {
      const liveComposer = await waitFor(() => findComposer() || composer, 15000, "beviteli mező");
      const preparedComposer = await waitFor(() => {
        const candidate = findComposer() || liveComposer;
        return isComposerReadyForSubmit(candidate) ? candidate : null;
      }, 12000, "beküldhető tartalom");
      const beforeState = captureComposerSubmitState(preparedComposer);
      const sendButton = findSendButton(preparedComposer);
      const form = findClosestForm(preparedComposer);
      const expandedEditorMode = isExpandedComposerEditor(preparedComposer);
      const attempts = [];

      if (form instanceof HTMLFormElement) {
        attempts.push({
          timeoutMs: 450,
          run() {
            if (typeof form.requestSubmit === "function") {
              form.requestSubmit();
              return;
            }

            dispatchFormSubmit(form);
          }
        });
        attempts.push({
          timeoutMs: 350,
          run() {
            dispatchFormSubmit(form);
          }
        });
      }

      if (!expandedEditorMode) {
        attempts.push({
          timeoutMs: 350,
          run() {
            preparedComposer.focus();
            dispatchEnterSequence(preparedComposer);
          }
        });
      }

      if (sendButton instanceof HTMLButtonElement) {
        attempts.push({
          timeoutMs: 550,
          run() {
            fireClickSequence(sendButton);
          }
        });
      }

      for (const attempt of attempts) {
        attempt.run();

        if (await waitForSendTransition(beforeState, attempt.timeoutMs)) {
          return;
        }
      }

      throw new Error("A tartalom bekerült, de a beküldést nem tudtam elindítani.");
    }

    async function submitImageMessage(composer) {
      const liveComposer = await waitFor(() => findComposer() || composer, 15000, "beviteli mező");
      const imageUploadTimeoutMs = getImageUploadTimeoutMs();
      const preparedComposer = await waitFor(() => {
        const candidate = findComposer() || liveComposer;
        return isImageReadyForSubmit(candidate) ? candidate : null;
      }, imageUploadTimeoutMs, "feltöltött kép");
      const beforeState = captureComposerSubmitState(preparedComposer);
      const form = findClosestForm(preparedComposer);
      const attempts = [];

      attempts.push({
        timeoutMs: 1000,
        run() {
          const liveSendButton = findSendButton(preparedComposer);

          if (liveSendButton instanceof HTMLButtonElement) {
            fireClickSequence(liveSendButton);
          }
        }
      });

      if (form instanceof HTMLFormElement) {
        attempts.push({
          timeoutMs: 650,
          run() {
            if (typeof form.requestSubmit === "function") {
              form.requestSubmit();
              return;
            }

            dispatchFormSubmit(form);
          }
        });
        attempts.push({
          timeoutMs: 500,
          run() {
            dispatchFormSubmit(form);
          }
        });
      }

      for (const attempt of attempts) {
        attempt.run();

        if (await waitForImageSendTransition(beforeState, preparedComposer, attempt.timeoutMs)) {
          return;
        }
      }

      throw new Error("A kép csatolva maradt, de a beküldést nem tudtam elindítani.");
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

      return {
        attachmentCount: countAttachmentIndicators(scope),
        fileInputCount: countSelectedFiles(scope)
      };
    }

    function captureComposerSubmitState(composer) {
      const liveComposer = findComposer() || composer;
      const scope = findComposerScope(liveComposer);
      const userMessages = findUserMessageNodes();
      const assistantMessages = findAssistantMessageNodes();
      const lastUserMessage = userMessages.at(-1) || null;
      const lastAssistantMessage = assistantMessages.at(-1) || null;

      return {
        composerText: normalizePromptStructure(readComposerText(liveComposer)),
        attachmentCount: countAttachmentIndicators(scope),
        fileInputCount: countSelectedFiles(scope),
        userCount: userMessages.length,
        lastUserNodeId: lastUserMessage ? getDomNodeId(lastUserMessage) : "",
        assistantCount: assistantMessages.length,
        lastAssistantNodeId: lastAssistantMessage ? getDomNodeId(lastAssistantMessage) : "",
        lastAssistantPending: lastAssistantMessage ? isAssistantResponsePending(lastAssistantMessage) : false
      };
    }

    async function waitForAttachmentReady(composer, beforeSnapshot, timeoutMs) {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const liveComposer = findComposer() || composer;
        const scope = findComposerScope(liveComposer);
        const attachmentCount = countAttachmentIndicators(scope);
        const fileInputCount = countSelectedFiles(scope);
        const attachmentAccepted = attachmentCount > beforeSnapshot.attachmentCount || fileInputCount > beforeSnapshot.fileInputCount;
        const uploadPending = hasPendingAttachmentWork(scope);

        if (attachmentAccepted && !uploadPending) {
          return liveComposer;
        }

        await waitForNextStateTurn(timeoutMs - (Date.now() - startedAt));
      }

      return findComposer() || composer;
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
      if (!(scope instanceof Element)) {
        return 0;
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
      const uniqueVisibleMatches = Array.from(new Set(matches)).filter((element) => isTrackableAttachmentIndicator(element));

      return uniqueVisibleMatches.length;
    }

    function countSelectedFiles(scope) {
      if (!(scope instanceof Element)) {
        return 0;
      }

      return Array.from(scope.querySelectorAll('input[type="file"]'))
        .reduce((count, input) => count + ((input instanceof HTMLInputElement && input.files?.length) ? input.files.length : 0), 0);
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
      const assistantEntries = findAssistantMessageNodes()
        .map((node) => ({
          nodeId: getDomNodeId(node),
          text: normalizeWhitespace(extractAssistantText(node)),
          pending: isAssistantResponsePending(node)
        }))
        .filter((entry) => Boolean(entry.text) || entry.pending);

      const lastEntry = assistantEntries.at(-1) || null;

      return {
        count: assistantEntries.length,
        lastNodeId: lastEntry?.nodeId || "",
        lastText: lastEntry?.text || "",
        lastPending: Boolean(lastEntry?.pending)
      };
    }

    async function waitForAssistantResponse(previousSnapshot, timeoutMs) {
      const domTracker = ensureDomActivityTracker();
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const currentSnapshot = captureAssistantSnapshot();
        const candidate = currentSnapshot.lastText;
        const hasNewResponse = Boolean(candidate)
          && (
            currentSnapshot.count > previousSnapshot.count
            || currentSnapshot.lastNodeId !== previousSnapshot.lastNodeId
            || candidate !== previousSnapshot.lastText
          );

        if (hasNewResponse) {
          if (isTransientAssistantText(candidate) || currentSnapshot.lastPending) {
            const remainingBusyTime = timeoutMs - (Date.now() - startedAt);

            if (remainingBusyTime > 0) {
              await domTracker.waitForChange(Math.min(RESPONSE_CHANGE_WAIT_MS, remainingBusyTime));
            }

            continue;
          }

          return {
            text: candidate,
            copied: false
          };
        }

        const remainingTime = timeoutMs - (Date.now() - startedAt);

        if (remainingTime <= 0) {
          break;
        }

        await domTracker.waitForChange(Math.min(RESPONSE_CHANGE_WAIT_MS, remainingTime));
      }

      const finalSnapshot = captureAssistantSnapshot();
      const finalCandidate = finalSnapshot.lastText;
      const hasFinalResponse = Boolean(finalCandidate)
        && (finalSnapshot.count > previousSnapshot.count || finalCandidate !== previousSnapshot.lastText)
        && !isTransientAssistantText(finalCandidate)
        && !finalSnapshot.lastPending;

      if (hasFinalResponse) {
        return {
          text: finalCandidate,
          copied: false
        };
      }

      throw new Error("A ChatGPT válasza nem érkezett meg időben.");
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
        .filter((element) => doesMessageNodeMatchAuthor(element, normalizedAuthorRole));

      if (directMatches.length > 0) {
        return Array.from(new Set(directMatches));
      }

      const fallbackMatches = Array.from(document.querySelectorAll('[data-testid^="conversation-turn-"], article'))
        .filter(isDomTrackableElement)
        .filter((element) => doesMessageNodeMatchAuthor(element, normalizedAuthorRole));

      return Array.from(new Set(fallbackMatches));
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

    async function waitForSendTransition(beforeState, timeoutMs) {
      const startedAt = Date.now();
      const beforeComposerText = normalizePromptStructure(beforeState.composerText);

      while (Date.now() - startedAt < timeoutMs) {
        const composer = findComposer();
        const afterState = captureComposerSubmitState(composer);
        const afterComposerText = normalizePromptStructure(afterState.composerText);
        const composerChanged = Boolean(beforeComposerText) && afterComposerText !== beforeComposerText;
        const userMessageAppeared = afterState.userCount > beforeState.userCount
          || (Boolean(afterState.lastUserNodeId) && afterState.lastUserNodeId !== beforeState.lastUserNodeId);
        const assistantActivityStarted = afterState.assistantCount > beforeState.assistantCount
          || (Boolean(afterState.lastAssistantNodeId) && afterState.lastAssistantNodeId !== beforeState.lastAssistantNodeId)
          || (afterState.lastAssistantPending && !beforeState.lastAssistantPending);

        if (composerChanged || userMessageAppeared || assistantActivityStarted) {
          return true;
        }

        if (afterState.attachmentCount < beforeState.attachmentCount || afterState.fileInputCount < beforeState.fileInputCount) {
          return true;
        }

        if (isGenerationInProgress()) {
          return true;
        }

        await waitForNextStateTurn(timeoutMs - (Date.now() - startedAt));
      }

      return false;
    }

    async function waitForImageSendTransition(beforeState, composer, timeoutMs) {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const liveComposer = findComposer() || composer;
        const afterState = captureComposerSubmitState(liveComposer);
        const userMessageAppeared = afterState.userCount > beforeState.userCount
          || (Boolean(afterState.lastUserNodeId) && afterState.lastUserNodeId !== beforeState.lastUserNodeId);
        const assistantActivityStarted = afterState.assistantCount > beforeState.assistantCount
          || (Boolean(afterState.lastAssistantNodeId) && afterState.lastAssistantNodeId !== beforeState.lastAssistantNodeId)
          || (afterState.lastAssistantPending && !beforeState.lastAssistantPending);

        if (beforeState.attachmentCount > 0 && afterState.attachmentCount < beforeState.attachmentCount) {
          return true;
        }

        if (beforeState.fileInputCount > 0 && afterState.fileInputCount < beforeState.fileInputCount) {
          return true;
        }

        if (userMessageAppeared || assistantActivityStarted) {
          return true;
        }

        if (isGenerationInProgress()) {
          return true;
        }

        await waitForNextStateTurn(timeoutMs - (Date.now() - startedAt));
      }

      return false;
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
      const domTracker = ensureDomActivityTracker();
      await Promise.race([
        wait(FRAME_INTERVAL_MS),
        domTracker.waitForChange(Math.min(RESPONSE_CHANGE_WAIT_MS, boundedTimeout))
      ]);
    }
  };
})();
