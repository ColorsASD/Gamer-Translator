(() => {
  const TARGET_UI_FPS = 50;
  const FRAME_INTERVAL_MS = 20;

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
        : { count: 0, lastText: "" };

      let activeComposer = await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "beviteli mező");

      if (payload.imageDataUrl) {
        activeComposer = await attachImage(activeComposer);
        await maybeDelayLocal(payload.afterAttachDelayMs);
      }

      if (payload.prompt) {
        activeComposer = await waitFor(() => findComposer(), payload.pageReadyTimeoutMs, "frissített beviteli mező");
        writePrompt(activeComposer, payload.prompt);
        activeComposer = await waitForPromptApplied(
          activeComposer,
          payload.prompt,
          Math.min(payload.pageReadyTimeoutMs, 1800)
        );
        await maybeDelayLocal(payload.beforeSubmitDelayMs);
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

      return waitForAttachmentReady(composer, beforeSnapshot, Math.min(payload.pageReadyTimeoutMs, 8000));
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

    async function maybeDelayLocal(ms) {
      const delayMs = Number(ms) || 0;

      if (delayMs > 0) {
        await wait(delayMs);
      }
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

      if (sendButton instanceof HTMLButtonElement) {
        attempts.push({
          timeoutMs: 850,
          run() {
            fireClickSequence(sendButton);
          }
        });
      }

      if (form instanceof HTMLFormElement) {
        attempts.push({
          timeoutMs: 700,
          run() {
            if (typeof form.requestSubmit === "function") {
              form.requestSubmit();
              return;
            }

            dispatchFormSubmit(form);
          }
        });
        attempts.push({
          timeoutMs: 650,
          run() {
            dispatchFormSubmit(form);
          }
        });
      }

      if (!expandedEditorMode) {
        attempts.push({
          timeoutMs: 650,
          run() {
            preparedComposer.focus();
            dispatchEnterSequence(preparedComposer);
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
      const preparedComposer = await waitFor(() => {
        const candidate = findComposer() || liveComposer;
        return isImageReadyForSubmit(candidate) ? candidate : null;
      }, 12000, "feltöltött kép");
      const beforeState = captureComposerSubmitState(preparedComposer);
      const form = findClosestForm(preparedComposer);
      const attempts = [];

      attempts.push({
        timeoutMs: 1500,
        run() {
          const liveSendButton = findSendButton(preparedComposer);

          if (!(liveSendButton instanceof HTMLButtonElement)) {
            throw new Error("A képküldés gomb nem található.");
          }

          fireClickSequence(liveSendButton);
        }
      });

      if (form instanceof HTMLFormElement) {
        attempts.push({
          timeoutMs: 900,
          run() {
            if (typeof form.requestSubmit === "function") {
              form.requestSubmit();
              return;
            }

            dispatchFormSubmit(form);
          }
        });
        attempts.push({
          timeoutMs: 850,
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

      return String(element.innerText || element.textContent || "");
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

        await wait(FRAME_INTERVAL_MS);
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
      if (!(element instanceof HTMLElement) || !isVisible(element)) {
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

      const rect = element.getBoundingClientRect();
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
      const scope = findComposerScope(element);
      const activeElementBonus = document.activeElement === element ? 240 : 0;
      const promptSelectorBonus = element.id === "prompt-textarea" || element.getAttribute("data-testid") === "prompt-textarea" ? 1600 : 0;
      const lowerViewportBonus = rect.bottom >= viewportHeight * 0.55 ? 1400 : 0;
      const lowestPositionBonus = Math.max(0, rect.bottom);
      const scopeSendButtonBonus = scopeHasLikelyComposerActions(scope) ? 900 : 0;
      const conversationPenalty = element.closest('[data-testid^="conversation-turn-"], article') ? 3200 : 0;
      const topHalfPenalty = rect.bottom < viewportHeight * 0.45 ? 1800 : 0;

      return selectorWeight
        + activeElementBonus
        + promptSelectorBonus
        + lowerViewportBonus
        + lowestPositionBonus
        + scopeSendButtonBonus
        - conversationPenalty
        - topHalfPenalty;
    }

    function scopeHasLikelyComposerActions(scope) {
      if (!(scope instanceof Element)) {
        return false;
      }

      return Boolean(
        scope.querySelector('button[data-testid="send-button"]')
        || scope.querySelector('button[data-testid*="send"]')
        || scope.querySelector('button[aria-label*="send" i]')
        || scope.querySelector('button[aria-label*="küld" i]')
        || scope.querySelector('button[title*="send" i]')
        || scope.querySelector('button[title*="küld" i]')
        || scope.querySelector('button[type="submit"]')
      );
    }

    function captureComposerAttachmentSnapshot(composer) {
      const scope = findComposerScope(composer);
      const sendButton = findSendButton(composer, { allowDisabled: true });

      return {
        attachmentCount: countAttachmentIndicators(scope),
        fileInputCount: countSelectedFiles(scope),
        sendButtonState: sendButton ? readButtonState(sendButton) : null
      };
    }

    function captureComposerSubmitState(composer) {
      const liveComposer = findComposer() || composer;
      const scope = findComposerScope(liveComposer);
      const sendButton = findSendButton(liveComposer, { allowDisabled: true });

      return {
        composerText: normalizePromptStructure(readComposerText(liveComposer)),
        attachmentCount: countAttachmentIndicators(scope),
        fileInputCount: countSelectedFiles(scope),
        sendButtonState: sendButton ? readButtonState(sendButton) : null
      };
    }

    async function waitForAttachmentReady(composer, beforeSnapshot, timeoutMs) {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const liveComposer = findComposer() || composer;
        const scope = findComposerScope(liveComposer);
        const attachmentCount = countAttachmentIndicators(scope);
        const fileInputCount = countSelectedFiles(scope);
        const sendButton = findSendButton(liveComposer, { allowDisabled: true });
        const sendButtonState = sendButton ? readButtonState(sendButton) : null;
        const attachmentAccepted = attachmentCount > beforeSnapshot.attachmentCount || fileInputCount > beforeSnapshot.fileInputCount;
        const uploadPending = hasPendingAttachmentWork(scope);

        if (attachmentAccepted && !uploadPending) {
          return liveComposer;
        }

        if (
          sendButtonState
          && (
            !beforeSnapshot.sendButtonState
            || !sameButtonState(beforeSnapshot.sendButtonState, sendButtonState)
          )
        ) {
          if (!sendButtonState.disabled || !uploadPending) {
            return liveComposer;
          }
        }

        await wait(FRAME_INTERVAL_MS);
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

      let current = composer.parentElement;
      let depth = 0;

      while (current && depth < 12) {
        if (
          current.querySelector('button[data-testid="send-button"]')
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
      const uniqueVisibleMatches = Array.from(new Set(matches)).filter((element) => element instanceof Element && isVisible(element));

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

      const pendingNodes = pendingSelectors
        .flatMap((selector) => Array.from(scope.querySelectorAll(selector)))
        .filter((element) => element instanceof Element && isVisible(element));

      if (pendingNodes.length > 0) {
        return true;
      }

      const attachmentCount = countAttachmentIndicators(scope);
      const fileInputCount = countSelectedFiles(scope);

      if (attachmentCount === 0 && fileInputCount === 0) {
        return false;
      }

      const sendButton = findSendButton(findComposer(), { allowDisabled: true });
      return sendButton instanceof HTMLButtonElement && sendButton.disabled;
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
      const texts = findAssistantMessageNodes()
        .map((node) => extractAssistantText(node))
        .map((text) => normalizeWhitespace(text))
        .filter(Boolean);

      return {
        count: texts.length,
        lastText: texts.at(-1) || ""
      };
    }

    async function waitForAssistantResponse(previousSnapshot, timeoutMs) {
      const startedAt = Date.now();
      let lastCandidate = "";
      let latestUsableCandidate = "";
      let stableSince = 0;

      while (Date.now() - startedAt < timeoutMs) {
        const assistantNodes = findAssistantMessageNodes();
        const latestAssistantNode = assistantNodes.at(-1) || null;
        const currentSnapshot = captureAssistantSnapshot();
        const candidate = currentSnapshot.lastText;
        const hasNewResponse = Boolean(candidate)
          && (currentSnapshot.count > previousSnapshot.count || candidate !== previousSnapshot.lastText);

        if (hasNewResponse) {
          if (isTransientAssistantText(candidate) || isAssistantMessageBusy(latestAssistantNode)) {
            lastCandidate = "";
            stableSince = 0;
            await wait(FRAME_INTERVAL_MS);
            continue;
          }

          latestUsableCandidate = candidate;

          if (candidate !== lastCandidate) {
            lastCandidate = candidate;
            stableSince = Date.now();
          }

          if (!isGenerationInProgress() && hasReadyResponseActions(latestAssistantNode)) {
            return {
              text: candidate,
              copied: false
            };
          }

          if (!isGenerationInProgress() && Date.now() - stableSince >= 450) {
            return {
              text: candidate,
              copied: false
            };
          }
        }

        await wait(FRAME_INTERVAL_MS);
      }

      const finalSnapshot = captureAssistantSnapshot();
      const finalCandidate = finalSnapshot.lastText;
      const hasFinalResponse = Boolean(finalCandidate)
        && (finalSnapshot.count > previousSnapshot.count || finalCandidate !== previousSnapshot.lastText)
        && !isTransientAssistantText(finalCandidate);

      if (hasFinalResponse) {
        return {
          text: finalCandidate,
          copied: false
        };
      }

      if (latestUsableCandidate) {
        return {
          text: latestUsableCandidate,
          copied: false
        };
      }

      throw new Error("A ChatGPT válasza nem érkezett meg időben.");
    }

    function hasReadyResponseActions(messageElement) {
      if (!(messageElement instanceof HTMLElement)) {
        return false;
      }

      const actionLabels = collectResponseActionLabels(messageElement);

      if (actionLabels.length === 0) {
        return false;
      }

      return actionLabels.some((label) => ["like", "dislike", "share", "regenerate", "more", "tetszik", "nem tetszik", "megoszt", "újragenerál", "további"].some((needle) => label.includes(needle)));
    }

    function collectResponseActionLabels(messageElement) {
      const scope = messageElement.closest('[data-testid^="conversation-turn-"], article, section, div')
        || messageElement;

      return Array.from(scope.querySelectorAll("button"))
        .filter((button) => button instanceof HTMLButtonElement && !button.disabled)
        .map((button) => [
          button.getAttribute("aria-label"),
          button.getAttribute("title"),
          button.dataset?.testid,
          button.textContent
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .trim())
        .filter(Boolean);
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

      return Boolean(
        element.querySelector('[aria-busy="true"], [data-state="streaming"], [data-state="thinking"], [data-status="in_progress"]')
      );
    }

    function isGenerationInProgress() {
      const sendButton = findSendButton(findComposer());

      if (!sendButton) {
        return false;
      }

      return buttonLooksLikeStop(readButtonState(sendButton));
    }

    function findAssistantMessageNodes() {
      const directMatches = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'))
        .filter(isVisible);

      if (directMatches.length > 0) {
        return Array.from(new Set(directMatches));
      }

      const fallbackMatches = Array.from(document.querySelectorAll('[data-testid^="conversation-turn-"], article'))
        .filter(isVisible)
        .filter((element) => {
          const authorHints = [
            element.getAttribute("data-message-author-role"),
            element.querySelector('[data-message-author-role]')?.getAttribute("data-message-author-role"),
            element.getAttribute("aria-label")
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

          if (!authorHints.includes("assistant")) {
            return false;
          }

          return Boolean(normalizeWhitespace(extractAssistantText(element)));
        });

      return Array.from(new Set(fallbackMatches));
    }

    function extractAssistantText(element) {
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

        const text = normalizeWhitespace(container.innerText || container.textContent);

        if (text) {
          return text;
        }
      }

      return "";
    }

    function isEligibleSendButton(button, options = {}) {
      const allowDisabled = Boolean(options.allowDisabled);

      if (!(button instanceof HTMLButtonElement) || !isVisible(button) || (button.disabled && !allowDisabled)) {
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

          return buttonHasExplicitSendIntent(button) || isNearComposer(button, composer);
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

      const composerRect = composer.getBoundingClientRect();
      const ranked = buttons
        .map((button) => {
          const rect = button.getBoundingClientRect();
          const horizontalDistance = Math.abs(rect.left - composerRect.right);
          const verticalDistance = Math.abs((rect.top + rect.height / 2) - (composerRect.top + composerRect.height / 2));
          const explicitSendBonus = buttonHasExplicitSendIntent(button) ? -2000 : 0;
          const sameFormBonus = composer.closest("form") && composer.closest("form") === button.closest("form") ? -500 : 0;
          const afterComposerBonus = rect.left >= composerRect.left ? -100 : 0;
          const score = horizontalDistance + verticalDistance + explicitSendBonus + sameFormBonus + afterComposerBonus;

          return { button, score };
        })
        .sort((left, right) => left.score - right.score);

      return ranked[0]?.button || null;
    }

    function isNearComposer(button, composer) {
      if (!(button instanceof HTMLButtonElement) || !(composer instanceof Element)) {
        return true;
      }

      const composerRect = composer.getBoundingClientRect();
      const rect = button.getBoundingClientRect();
      const verticalCenterDistance = Math.abs((rect.top + rect.height / 2) - (composerRect.top + composerRect.height / 2));
      const buttonIsBelowBottom = rect.top > composerRect.bottom + 140;
      const buttonIsFarLeft = rect.right < composerRect.left - 40;
      const buttonIsFarRight = rect.left > composerRect.right + 220;

      if (verticalCenterDistance > 140) {
        return false;
      }

      if (buttonIsBelowBottom || buttonIsFarLeft || buttonIsFarRight) {
        return false;
      }

      return true;
    }

    function readButtonState(button) {
      return {
        text: normalizeWhitespace(button.textContent),
        ariaLabel: normalizeWhitespace(button.getAttribute("aria-label")),
        title: normalizeWhitespace(button.getAttribute("title")),
        testId: normalizeWhitespace(button.dataset?.testid),
        disabled: Boolean(button.disabled)
      };
    }

    async function waitFor(factory, timeoutMs, label) {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const value = factory();

        if (value) {
          return value;
        }

        await wait(FRAME_INTERVAL_MS);
      }

      throw new Error(`Nem található: ${label}.`);
    }

    function isVisible(element) {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();

      return (
        style.display !== "none"
        && style.visibility !== "hidden"
        && Number.parseFloat(style.opacity || "1") !== 0
        && rect.width > 0
        && rect.height > 0
      );
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

      while (Date.now() - startedAt < timeoutMs) {
        const composer = findComposer();
        const afterState = captureComposerSubmitState(composer);
        const beforeButtonState = beforeState.sendButtonState;
        const afterButtonState = afterState.sendButtonState;

        if (beforeButtonState && !afterButtonState) {
          return true;
        }

        if (afterButtonState && beforeButtonState) {
          if (afterButtonState.disabled && !beforeButtonState.disabled) {
            return true;
          }

          if (buttonLooksLikeStop(afterButtonState) && !buttonLooksLikeStop(beforeButtonState)) {
            return true;
          }

          if (!sameButtonState(beforeButtonState, afterButtonState)) {
            return true;
          }
        }

        if (
          beforeState.composerText
          && normalizePromptStructure(afterState.composerText) !== normalizePromptStructure(beforeState.composerText)
        ) {
          return true;
        }

        if (afterState.attachmentCount < beforeState.attachmentCount || afterState.fileInputCount < beforeState.fileInputCount) {
          return true;
        }

        if (isGenerationInProgress()) {
          return true;
        }

        await wait(FRAME_INTERVAL_MS);
      }

      return false;
    }

    async function waitForImageSendTransition(beforeState, composer, timeoutMs) {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const liveComposer = findComposer() || composer;
        const scope = findComposerScope(liveComposer);
        const afterState = captureComposerSubmitState(liveComposer);

        if (beforeState.attachmentCount > 0 && afterState.attachmentCount < beforeState.attachmentCount) {
          return true;
        }

        if (beforeState.fileInputCount > 0 && afterState.fileInputCount < beforeState.fileInputCount) {
          return true;
        }

        if (beforeState.sendButtonState && afterState.sendButtonState) {
          if (buttonLooksLikeStop(afterState.sendButtonState) && !buttonLooksLikeStop(beforeState.sendButtonState)) {
            return true;
          }

          if (!sameButtonState(beforeState.sendButtonState, afterState.sendButtonState) && !hasPendingAttachmentWork(scope)) {
            return true;
          }
        }

        if (isGenerationInProgress()) {
          return true;
        }

        await wait(FRAME_INTERVAL_MS);
      }

      return false;
    }

    function sameButtonState(left, right) {
      return left.text === right.text
        && left.ariaLabel === right.ariaLabel
        && left.title === right.title
        && left.testId === right.testId
        && left.disabled === right.disabled;
    }

    function buttonLooksLikeStop(state) {
      const label = [state.text, state.ariaLabel, state.title, state.testId]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return ["stop", "állj", "leállít", "megszakít", "cancel"].some((needle) => label.includes(needle));
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
        .filter((button) => isVisible(button));

      const hasCancel = visibleButtons.some((button) => looksLikeCancelAction(button));
      const hasExplicitSend = visibleButtons.some((button) => buttonHasExplicitSendIntent(button));

      return hasCancel && hasExplicitSend;
    }
  };
})();
