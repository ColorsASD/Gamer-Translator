(() => {
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
        await maybeDelayLocal(payload.beforeSubmitDelayMs);
      }

      if (payload.autoSubmit) {
        await submitMessage(activeComposer);
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

    async function submitMessage(composer) {
      const liveComposer = findComposer() || composer;
      const sendButton = await waitFor(() => findSendButton(liveComposer), 15000, "küldés gomb");

      if (!(sendButton instanceof HTMLButtonElement)) {
        throw new Error("A küldés gomb nem található.");
      }

      const beforeState = readButtonState(sendButton);

      fireClickSequence(sendButton);

      if (await waitForSendTransition(beforeState, 2000)) {
        return;
      }

      const form = liveComposer?.closest("form");

      if (form && typeof form.requestSubmit === "function") {
        form.requestSubmit();

        if (await waitForSendTransition(beforeState, 1200)) {
          return;
        }
      }

      if (liveComposer) {
        liveComposer.focus();
        dispatchEnterSequence(liveComposer);

        if (await waitForSendTransition(beforeState, 1200)) {
          return;
        }
      }

      throw new Error("A kép bekerült, de a beküldést nem tudtam elindítani.");
    }

    function writePrompt(element, prompt) {
      element.focus();

      if (element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement) {
        const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");

        descriptor?.set?.call(element, prompt);
        element.dispatchEvent(
          new InputEvent("input", {
            bubbles: true,
            composed: true,
            data: prompt,
            inputType: "insertText"
          })
        );
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

        try {
          inserted = document.execCommand("insertText", false, prompt);
        } catch (_error) {
          inserted = false;
        }

        if (!inserted || normalizeWhitespace(element.textContent) !== normalizeWhitespace(prompt)) {
          element.textContent = prompt;
        }

        element.dispatchEvent(
          new InputEvent("input", {
            bubbles: true,
            composed: true,
            data: prompt,
            inputType: "insertText"
          })
        );
        return;
      }

      throw new Error("A talált beviteli mező típusa nem támogatott.");
    }

    function findComposer() {
      const selectors = [
        "#prompt-textarea",
        '[data-testid="prompt-textarea"]',
        "textarea",
        '[contenteditable="true"]',
        '[role="textbox"]'
      ];
      const candidates = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));

      return candidates.find((element) => {
        if (!(element instanceof HTMLElement) || !isVisible(element)) {
          return false;
        }

        if (element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement) {
          return !element.disabled && !element.readOnly;
        }

        return element.isContentEditable;
      }) || null;
    }

    function captureComposerAttachmentSnapshot(composer) {
      const scope = findComposerScope(composer);
      const sendButton = findSendButton(composer);

      return {
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
        const sendButton = findSendButton(liveComposer);
        const sendButtonState = sendButton ? readButtonState(sendButton) : null;

        if (attachmentCount > beforeSnapshot.attachmentCount || fileInputCount > beforeSnapshot.fileInputCount) {
          return liveComposer;
        }

        if (
          sendButtonState
          && !sendButtonState.disabled
          && (
            !beforeSnapshot.sendButtonState
            || beforeSnapshot.sendButtonState.disabled
            || !sameButtonState(beforeSnapshot.sendButtonState, sendButtonState)
          )
        ) {
          return liveComposer;
        }

        await wait(80);
      }

      return findComposer() || composer;
    }

    function findComposerScope(composer) {
      return composer?.closest("form")
        || findComposerContainer(composer)
        || composer?.parentElement
        || null;
    }

    function findComposerContainer(composer) {
      if (!(composer instanceof Element)) {
        return null;
      }

      let current = composer.parentElement;
      let depth = 0;

      while (current && depth < 8) {
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

    function findSendButton(composer) {
      const scope = findComposerScope(composer);
      const specificSelectors = [
        'button[data-testid="send-button"]',
        'button[data-testid*="send"]',
        'button[aria-label*="send" i]',
        'button[aria-label*="küld" i]',
        'button[title*="send" i]',
        'button[title*="küld" i]',
        'form button[type="submit"]'
      ];

      for (const selector of specificSelectors) {
        const scopedMatch = findBestSendButtonMatch(scope, selector, composer);

        if (scopedMatch) {
          return scopedMatch;
        }
      }

      if (scope instanceof Element) {
        const scopedButtons = Array.from(scope.querySelectorAll("button"))
          .filter((button) => button instanceof HTMLButtonElement)
          .filter((button) => isEligibleSendButton(button) && looksLikeSendButton(button) && isNearComposer(button, composer));

        const nearestScopedButton = pickNearestButton(scopedButtons, composer);

        if (nearestScopedButton) {
          return nearestScopedButton;
        }
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
            await wait(120);
            continue;
          }

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

        await wait(120);
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

    function isEligibleSendButton(button) {
      if (!(button instanceof HTMLButtonElement) || !isVisible(button) || button.disabled) {
        return false;
      }

      if (button.closest('[role="menu"], [role="menuitem"], [data-radix-menu-content], [data-radix-dropdown-menu-content]')) {
        return false;
      }

      return true;
    }

    function findBestSendButtonMatch(scope, selector, composer) {
      if (!(scope instanceof Element)) {
        return null;
      }

      const matches = Array.from(scope.querySelectorAll(selector))
        .filter((button) => button instanceof HTMLButtonElement)
        .filter((button) => isEligibleSendButton(button) && looksLikeSendButton(button) && isNearComposer(button, composer));

      return pickNearestButton(matches, composer);
    }

    function looksLikeSendButton(button) {
      if (!(button instanceof HTMLButtonElement)) {
        return false;
      }

      const label = readButtonLabel(button);

      if (button.type === "submit" && !looksLikeNonSendAction(label)) {
        return true;
      }

      return ["send", "küld", "elküld", "submit", "prompt"].some((needle) => label.includes(needle))
        && !looksLikeNonSendAction(label);
    }

    function looksLikeNonSendAction(label) {
      return ["stop", "állj", "megszakít", "cancel", "copy", "másol", "like", "dislike", "share", "regenerate", "more", "megoszt", "átnevez", "rögzít", "archiv", "törlés", "delete"].some((needle) => label.includes(needle));
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
          const sameFormBonus = composer.closest("form") && composer.closest("form") === button.closest("form") ? -500 : 0;
          const afterComposerBonus = rect.left >= composerRect.left ? -100 : 0;
          const score = horizontalDistance + verticalDistance + sameFormBonus + afterComposerBonus;

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

        await wait(250);
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

    async function waitForSendTransition(beforeState, timeoutMs) {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const composer = findComposer();
        const sendButton = findSendButton(composer);

        if (!sendButton) {
          return true;
        }

        const afterState = readButtonState(sendButton);

        if (afterState.disabled && !beforeState.disabled) {
          return true;
        }

        if (buttonLooksLikeStop(afterState) && !buttonLooksLikeStop(beforeState)) {
          return true;
        }

        if (!sameButtonState(beforeState, afterState)) {
          return true;
        }

        await wait(100);
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
  };
})();
