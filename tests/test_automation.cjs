// Offline regressziók: hálózat és bejelentkezett ChatGPT munkamenet nélkül.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { File } = require('node:buffer');

const source = fs.readFileSync(path.join(__dirname, '..', 'gamer_translator', 'automation.js'), 'utf8');
const helperNames = [
  'dataUrlToFile', 'waitForPromptApplied', 'isTransientAssistantText',
  'readStructuredDomText', 'writePrompt', 'findComposer', 'findSendButton',
  'captureComposerSubmitState', 'isGenerationInProgress', 'submitTextMessage',
  'waitForAssistantResponse', 'isComposerReadyForSubmit',
  'captureAssistantSnapshot', 'isFreshAssistantSnapshot', 'findAssistantMessageNodes', 'findUserMessageNodes',
  'isAssistantResponsePending', 'isExpectedAttachmentReadySnapshot', 'isAttachmentReadySnapshot',
  'attachImage', 'attachViaFileInput', 'attachViaDrop', 'captureComposerAttachmentSnapshot',
  'isImageReadyForSubmit', 'writeDiagnosticEntry',
  'extractMessageText',
  'isStableAssistantSnapshot', 'hasActiveGenerationControl',
  'captureResponseBaselineBeforeSubmit',
  'reportAssistantSnapshotDiagnostic',
  'getUiMessageHeadingRole', 'getMessageAuthorEvidence', 'getMessageStableId',
];
// Csak a tesztpéldány kap hozzáférést a belső függvényekhez; az éles forrás nem exportál teszt API-t.
const hook = helperNames.map((name) => `
  if (typeof window.__testOverrides?.${name} === 'function') ${name} = window.__testOverrides.${name};
`).join('') + `window.__testHelpers = { ${helperNames.join(', ')} };`;
const instrumentedSource = source.replace(
  'const composerAutoRecovery = ensureComposerAutoRecoveryWatcher();',
  `${hook}\nconst composerAutoRecovery = ensureComposerAutoRecoveryWatcher();`,
);
assert.notEqual(instrumentedSource, source, 'A teszthozzáférés beszúrási pontja megváltozott.');

class FakeNode {
  constructor() { this.childNodes = []; this.parentNode = null; }
  appendChild(child) {
    if (child instanceof FakeFragment) {
      for (const node of [...child.childNodes]) this.appendChild(node);
      return child;
    }
    this.childNodes.push(child);
    child.parentNode = this;
    return child;
  }
  get parentElement() { return this.parentNode instanceof FakeElement ? this.parentNode : null; }
  get textContent() { return this.childNodes.map((child) => child.textContent).join(''); }
  contains(node) { return this === node || this.childNodes.some((child) => child.contains(node)); }
  compareDocumentPosition(node) {
    const root = (entry) => { while (entry.parentNode) entry = entry.parentNode; return entry; };
    if (root(this) !== root(node)) return 1;
    const ordered = [];
    const walk = (entry) => { ordered.push(entry); for (const child of entry.childNodes) walk(child); };
    walk(root(this));
    return ordered.indexOf(this) < ordered.indexOf(node) ? 4 : this === node ? 0 : 2;
  }
}
class FakeText extends FakeNode {
  constructor(value) { super(); this.value = value; }
  get textContent() { return this.value; }
}
class FakeFragment extends FakeNode {}
class FakeElement extends FakeNode {
  constructor(tagName = 'div') {
    super(); this.tagName = tagName.toUpperCase(); this.isConnected = true;
    this.style = {}; this.attributes = new Map(); this.listeners = new Map();
    this.dataset = {}; this.disabled = false; this.id = ''; this.isContentEditable = false;
  }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  get children() { return this.childNodes.filter((child) => child instanceof FakeElement); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  hasAttribute(name) { return this.attributes.has(name); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  matches(selector) {
    return selector.split(',').some((part) => {
      part = part.trim();
      const attrs = [...part.matchAll(/\[([a-z0-9-]+)(?:(\^?=)"([^"]*)")?\]/g)];
      const tag = part.slice(0, part.indexOf('['));
      if (attrs.length && `${tag}${attrs.map((match) => match[0]).join('')}` === part) {
        return (!tag || tag.toLowerCase() === this.tagName.toLowerCase()) && attrs.every(([, key, operator, value]) => (
          value === undefined ? this.hasAttribute(key)
            : operator === '^=' ? String(this.getAttribute(key) || '').startsWith(value) : this.getAttribute(key) === value
        ));
      }
      return part.toLowerCase() === this.tagName.toLowerCase();
    });
  }
  closest(selector) {
    if (selector === 'button' && this instanceof FakeButton) return this;
    if (selector === 'form' && this instanceof FakeForm) return this;
    if (this.matches(selector)) return this;
    return this.parentElement?.closest(selector) || null;
  }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(handler);
  }
  removeEventListener(type, handler) { this.listeners.get(type)?.delete(handler); }
  dispatchEvent(event) {
    event.target ||= this;
    for (const handler of this.listeners.get(event.type) || []) handler(event);
    if (event.bubbles && this.parentElement) this.parentElement.dispatchEvent(event);
    return true;
  }
  replaceChildren(...children) { this.childNodes = []; for (const child of children) this.appendChild(child); }
  focus() {}
}
class FakeInput extends FakeElement {}
class FakeTextarea extends FakeElement {
  constructor() { super('textarea'); this._value = ''; }
  get value() { return this._value; }
  set value(value) { this._value = String(value); }
}
class FakeButton extends FakeElement { constructor() { super('button'); this.type = 'submit'; } }
class FakeForm extends FakeElement { constructor() { super('form'); } }
class FakeImage extends FakeElement {}
class FakeDocument extends FakeElement {
  constructor() {
    super('document'); this.documentElement = this.appendChild(new FakeElement('html'));
    this.body = this.documentElement.appendChild(new FakeElement('body'));
  }
  createElement(tag) { return new FakeElement(tag); }
  createTextNode(value) { return new FakeText(value); }
  createDocumentFragment() { return new FakeFragment(); }
  createRange() { return { selectNodeContents() {}, collapse() {} }; }
  execCommand() { return false; }
}
class FakeEvent {
  constructor(type, options = {}) { this.type = type; Object.assign(this, options); }
}

async function flush() { for (let index = 0; index < 12; index += 1) await Promise.resolve(); }

function createHarness({ origin = 'https://chatgpt.com', subframe = false, overrides = {} } = {}) {
  let now = 1000;
  let nextTimerId = 1;
  const timers = new Map();
  const document = new FakeDocument();
  const composer = document.body.appendChild(new FakeTextarea());
  const sendButton = document.body.appendChild(new FakeButton());
  sendButton.setAttribute('aria-label', 'Send message');
  const getSubmissionState = () => ({
    composerText: composer.value, attachmentCount: 0, fileInputCount: 0,
    hasPendingAttachmentWork: false, userCount: 0, lastUserNodeId: '',
    assistantCount: 0, lastAssistantNodeId: '', lastAssistantPending: false,
    sendButtonDisabled: sendButton.disabled, sendButtonLabel: 'send message', sendButtonIsNonSend: false,
  });
  const window = {
    location: { origin },
    __testOverrides: {
      findComposer: () => composer,
      findSendButton: () => sendButton.disabled ? null : sendButton,
      captureComposerSubmitState: getSubmissionState,
      isGenerationInProgress: () => false,
      ...overrides,
    },
    getComputedStyle: () => ({ display: 'block', visibility: 'visible' }),
    getSelection: () => ({ removeAllRanges() {}, addRange() {} }),
    addEventListener() {},
    setTimeout(callback, delay) { const id = nextTimerId++; timers.set(id, { callback, at: now + delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    setInterval() { return nextTimerId++; },
    clearInterval() {},
  };
  window.top = subframe ? {} : window;
  class FakeDate extends Date { static now() { return now; } }
  const context = vm.createContext({
    window, document, Date: FakeDate, File, atob, Uint8Array,
    Node: FakeNode, Text: FakeText, Element: FakeElement, HTMLElement: FakeElement,
    HTMLInputElement: FakeInput, HTMLTextAreaElement: FakeTextarea, HTMLButtonElement: FakeButton,
    HTMLFormElement: FakeForm, HTMLImageElement: FakeImage, Document: FakeDocument,
    Event: FakeEvent, InputEvent: FakeEvent, KeyboardEvent: FakeEvent,
    PointerEvent: FakeEvent, MouseEvent: FakeEvent,
    MutationRecord: class {}, MutationObserver: class { observe() {} disconnect() {} },
  });
  vm.runInContext(instrumentedSource, context, { filename: 'automation.js' });
  return {
    window, document, composer, sendButton, context,
    get helpers() { return window.__testHelpers; },
    async advance(milliseconds) {
      const deadline = now + milliseconds;
      await flush();
      for (let count = 0; count < 1000; count += 1) {
        const ready = [...timers].filter(([, timer]) => timer.at <= deadline).sort((a, b) => a[1].at - b[1].at)[0];
        if (!ready) { now = deadline; await flush(); return; }
        now = ready[1].at; timers.delete(ready[0]); ready[1].callback(); await flush();
      }
      throw new Error('Végtelen időzítőciklus a tesztben.');
    },
  };
}

test('Az automatizálás csak az engedélyezett HTTPS fődokumentumokban indul', () => {
  for (const origin of ['https://chatgpt.com', 'https://chat.openai.com']) {
    assert.equal(typeof createHarness({ origin }).window.__gamerTranslatorDeliver, 'function');
  }
  for (const origin of ['http://chatgpt.com', 'https://chatgpt.com:444', 'https://chatgpt.com.evil.example', 'https://evil.chatgpt.com', 'null']) {
    assert.equal(createHarness({ origin }).window.__gamerTranslatorDeliver, undefined, origin);
  }
  assert.equal(createHarness({ subframe: true }).window.__gamerTranslatorDeliver, undefined);
});

test('Navigáció után a megmaradt kézbesítő sem dolgozik idegen eredeten', async () => {
  const harness = createHarness();
  harness.window.location.origin = 'https://example.com';
  assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'titok' })).ok, false);
  assert.equal(harness.composer.value, '');
});

test('Hibás payload visszautasítása nem indít DOM-műveletet', async () => {
  const harness = createHarness();
  for (const payload of [null, undefined, [], 'prompt', { prompt: {} }, { imageDataUrl: 42 }]) {
    assert.equal((await harness.window.__gamerTranslatorDeliver(payload)).ok, false);
  }
  assert.equal(harness.composer.value, '');
});

test('Csak a teljes, normalizált prompt igazolható vissza', async () => {
  const harness = createHarness();
  harness.composer.value = 'Első sor\r\nMásodik sor';
  assert.equal(await harness.helpers.waitForPromptApplied(harness.composer, 'Első sor\nMásodik sor', 40), harness.composer);
  for (const wrongText of ['Első sor', 'Előzmény Első sor\nMásodik sor', 'Korábbi titkos szöveg']) {
    harness.composer.value = wrongText;
    const pending = harness.helpers.waitForPromptApplied(harness.composer, 'Első sor\nMásodik sor', 40);
    const rejected = assert.rejects(pending, /teljes prompt/);
    await harness.advance(40);
    await rejected;
  }
});

test('Részlegesen visszaállított prompt esetén a nyilvános küldés sem küld semmit', async () => {
  let submitCount = 0;
  const harness = createHarness({ overrides: { submitTextMessage: async () => { submitCount += 1; } } });
  harness.composer.addEventListener('input', () => { harness.composer.value = 'A teljes'; });
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'A teljes fordítandó szöveg', autoSubmit: true, pageReadyTimeoutMs: 40 });
  await harness.advance(80);
  const result = await pending;
  assert.equal(result.ok, false);
  assert.match(result.error, /teljes prompt/);
  assert.equal(submitCount, 0);
});

test('Küldés nélküli beillesztés nem vár idegen válaszra és nem értelmez HTML-t', async () => {
  const harness = createHarness({ overrides: { waitForAssistantResponse: async () => { throw new Error('Nem futhat.'); } } });
  const prompt = '<img src=x onerror=alert(1)>\nMásodik sor';
  const result = await harness.window.__gamerTranslatorDeliver({ prompt, autoSubmit: false, copyResponseToClipboard: true });
  assert.equal(result.ok, true);
  assert.equal(harness.composer.value, prompt);
  const editable = new FakeElement('div');
  editable.isContentEditable = true;
  harness.helpers.writePrompt(editable, prompt);
  assert.equal(editable.childNodes[0].childNodes[0] instanceof FakeText, true);
  assert.equal(editable.childNodes[0].textContent, '<img src=x onerror=alert(1)>');
});

test('Párhuzamos kézbesítés nem írhatja felül az aktív promptot', async () => {
  let release;
  const hold = new Promise((resolve) => { release = resolve; });
  const harness = createHarness({ overrides: { waitForPromptApplied: async (composer) => { await hold; return composer; } } });
  const first = harness.window.__gamerTranslatorDeliver({ prompt: 'Első', autoSubmit: false });
  await flush();
  const second = await harness.window.__gamerTranslatorDeliver({ prompt: 'Második', autoSubmit: false, diagnosticCallId: 'busy-rejection' });
  assert.equal(second.ok, false);
  assert.match(second.error, /folyamatban/);
  assert.equal(harness.window.__gamerTranslatorDiagnostics['busy-rejection'][0].event, 'delivery_rejected');
  assert.equal(harness.window.__gamerTranslatorDiagnostics['busy-rejection'][0].fields.reason, 'delivery_busy');
  assert.equal(harness.composer.value, 'Első');
  release();
  assert.equal((await first).ok, true);
  assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'Harmadik', autoSubmit: false })).ok, true);
});

test('Előzetes megszakítás után a késve végrehajtott küldés nem írhatja át a composert', async () => {
  const harness = createHarness();
  assert.equal(harness.window.__gamerTranslatorCancelDelivery('late-call').ok, true);
  assert.equal(harness.window.__gamerTranslatorIsDeliveryCancelled('late-call'), true);
  const result = await harness.window.__gamerTranslatorDeliver({ prompt: 'Elavult szöveg', autoSubmit: true, deliveryCallId: 'late-call' });
  assert.equal(result.ok, false); assert.equal(result.cancelled, true); assert.equal(harness.composer.value, '');
  for (const invalid of ['', 'invalid id', {}, 42]) {
    assert.equal(harness.window.__gamerTranslatorCancelDelivery(invalid).ok, false);
    assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'Tiltott', deliveryCallId: invalid })).ok, false);
  }
  assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'Új szöveg', autoSubmit: false, deliveryCallId: 'new-call' })).ok, true);
  assert.equal(harness.composer.value, 'Új szöveg');
});

test('Megszakított régi finally nem oldhatja fel a már elindult új küldés zárát', async () => {
  let releaseOld, releaseNew, submitCount = 0;
  const oldGate = new Promise((resolve) => { releaseOld = resolve; });
  const newGate = new Promise((resolve) => { releaseNew = resolve; });
  const harness = createHarness({ overrides: {
    waitForPromptApplied: async (composer, prompt) => { await (prompt === 'Régi' ? oldGate : newGate); return composer; },
    submitTextMessage: async () => { submitCount += 1; },
  } });
  const oldDelivery = harness.window.__gamerTranslatorDeliver({ prompt: 'Régi', autoSubmit: true, deliveryCallId: 'old-call' });
  await flush();
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 1);
  assert.equal(harness.window.__gamerTranslatorCancelDelivery('different-call').active, false);
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 1);
  assert.equal(harness.window.__gamerTranslatorCancelDelivery('old-call').active, true);
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 0);
  const newDelivery = harness.window.__gamerTranslatorDeliver({ prompt: 'Új', autoSubmit: true, deliveryCallId: 'new-call' });
  await flush();
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 1);
  releaseOld(); const oldResult = await oldDelivery;
  assert.equal(oldResult.cancelled, true); assert.equal(submitCount, 0);
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 1);
  assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'Harmadik', deliveryCallId: 'third-call' })).ok, false);
  releaseNew(); assert.equal((await newDelivery).ok, true); assert.equal(submitCount, 1);
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 0);
});

test('Megszakítás a valódi válaszvárakozást azonnal lezárja késői figyelés nélkül', async () => {
  let submitCount = 0;
  const harness = createHarness({ overrides: { submitTextMessage: async () => { submitCount += 1; } } });
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'Kérés', autoSubmit: true, waitForResponse: true,
    responseTimeoutMs: 600000, deliveryCallId: 'response-call', progressCallId: 'response-progress', diagnosticCallId: 'response-diagnostic' });
  await flush(); assert.equal(submitCount, 1);
  assert.equal(harness.window.__gamerTranslatorCancelDelivery('response-call').active, true);
  const result = await pending;
  assert.equal(result.cancelled, true); assert.equal(result.ok, false);
  assert.equal(Object.keys(harness.window.__gamerTranslatorAssistantResponseFollowUps || {}).length, 0);
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 0);
  assert.equal(harness.window.__gamerTranslatorDiagnostics['response-diagnostic'].some((entry) => entry.event === 'delivery_cancelled'), true);
});

test('Csatoló folytatás megszakítás után nem küldhet képet', async () => {
  let releaseAttachment;
  const gate = new Promise((resolve) => { releaseAttachment = resolve; });
  const harness = createHarness({ overrides: { attachImage: async (composer) => { await gate; return composer; } } });
  const pending = harness.window.__gamerTranslatorDeliver({ imageDataUrl: 'data:image/png;base64,aGVsbG8=', autoSubmit: true, deliveryCallId: 'attachment-call' });
  await flush(); assert.equal(harness.window.__gamerTranslatorCancelDelivery('attachment-call').active, true);
  releaseAttachment(); const result = await pending;
  assert.equal(result.cancelled, true); assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.suspendedCount, 0);
  assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'Következő', autoSubmit: false, deliveryCallId: 'next-call' })).ok, true);
});

test('Kép adatURL MIME-, base64- és méretellenőrzése', () => {
  const harness = createHarness();
  const decode = harness.helpers.dataUrlToFile;
  const file = decode('data:image/png;base64,aGVsbG8=', 'snip.png', 'image/png');
  assert.equal(file.type, 'image/png');
  assert.equal(file.size, 5);
  for (const invalid of ['data:text/html;base64,aGVsbG8=', 'data:image/svg+xml;base64,aGVsbG8=', 'data:image/png,hello', 'data:image/png;base64,@@@', 'data:image/png;base64,', 'data:image/png;base64,aGVsbG8=,extra']) {
    assert.throws(() => decode(invalid, 'snip.png', 'image/png'), /formátuma/);
  }
  assert.throws(() => decode('data:image/jpeg;base64,aGVsbG8=', 'snip.png', 'image/png'), /MIME/);
  let decoded = false;
  harness.context.atob = () => { decoded = true; return ''; };
  assert.throws(() => decode(`data:image/png;base64,${'A'.repeat(Math.ceil((20 * 1024 * 1024) / 3) * 4 + 4)}`, 'large.png', 'image/png'), /20 MiB/);
  assert.equal(decoded, false, 'A túlméretes kép nem dekódolható a méretellenőrzés előtt.');
});

test('A thinking szót tartalmazó fordítás nem veszik el állapotjelzésként', () => {
  const harness = createHarness();
  for (const text of ['Thinking', 'Thinking...', 'Gondolkodás folyamatban…', 'analyzing image']) {
    assert.equal(harness.helpers.isTransientAssistantText(text), true);
  }
  for (const text of ['I was thinking about the next round.', 'Stop overthinking it.', 'Image analysis in progress is the displayed error.']) {
    assert.equal(harness.helpers.isTransientAssistantText(text), false);
  }
});

test('Inline formázás és kód nem töri szét a fordítás szavait', () => {
  const harness = createHarness();
  const root = new FakeElement('div');
  const paragraph = root.appendChild(new FakeElement('p'));
  paragraph.appendChild(new FakeText('Mine'));
  paragraph.appendChild(new FakeElement('strong')).appendChild(new FakeText('Wild'));
  paragraph.appendChild(new FakeText(': '));
  paragraph.appendChild(new FakeElement('code')).appendChild(new FakeText('/spawn'));
  paragraph.appendChild(new FakeText(' most.'));
  assert.equal(harness.helpers.readStructuredDomText(root).trim(), 'MineWild: /spawn most.');
});

test('A kézi küldés helyreállítása DOM-változás nélkül is egyszer elindul', async () => {
  const harness = createHarness();
  await flush();
  harness.composer.value = 'Kézi fordítás';
  let retries = 0;
  harness.window.__gamerTranslatorDeliver = async () => { retries += 1; return { ok: false }; };
  harness.document.dispatchEvent(new FakeEvent('click', { target: harness.sendButton }));
  await harness.advance(2200);
  assert.equal(retries, 0);
  await harness.advance(20);
  assert.equal(retries, 1);
  await harness.advance(10000);
  assert.equal(retries, 1, 'Változatlan hibás állapot nem indíthat végtelen újraküldést.');
});

test('Az automatizálás saját eseménye nem élesíti a kézi helyreállítást', async () => {
  let harness;
  let submitCount = 0;
  harness = createHarness({ overrides: { submitTextMessage: async () => {
    submitCount += 1;
    harness.document.dispatchEvent(new FakeEvent('click', { target: harness.sendButton }));
  } } });
  const result = await harness.window.__gamerTranslatorDeliver({ prompt: 'Automatikus', autoSubmit: true });
  assert.equal(result.ok, true);
  assert.equal(harness.window.__gamerTranslatorComposerAutoRecovery.armedPayloadKey, '');
  await harness.advance(5000);
  assert.equal(submitCount, 1);
});

test('A megfigyelő leállítása törli a függő helyreállítás időzítőjét', async () => {
  const harness = createHarness();
  await flush();
  harness.composer.value = 'Ne küldd el később';
  let retries = 0;
  harness.window.__gamerTranslatorDeliver = async () => { retries += 1; };
  harness.document.dispatchEvent(new FakeEvent('click', { target: harness.sendButton }));
  harness.window.__gamerTranslatorComposerAutoRecovery.destroy();
  await harness.advance(5000);
  assert.equal(retries, 0);
});


function appendMessage(harness, id, text) {
  const message = harness.document.body.appendChild(new FakeElement('div'));
  message.setAttribute('data-message-id', id);
  message.appendChild(new FakeText(text));
  return message;
}

function conversationHarness() {
  const users = [];
  const assistants = [];
  const harness = createHarness({ overrides: {
    findUserMessageNodes: () => users,
    findAssistantMessageNodes: () => assistants,
    isAssistantResponsePending: () => false,
  } });
  return { harness, users, assistants };
}

test('Régi válasz és user kör újrarajzolása nem ad friss fordítást', () => {
  const { harness, users, assistants } = conversationHarness();
  users.push(appendMessage(harness, 'user-old', 'Korábbi kérés'));
  assistants.push(appendMessage(harness, 'answer-old', 'Korábbi válasz'));
  const previous = harness.helpers.captureAssistantSnapshot();
  users[0] = appendMessage(harness, 'user-old', 'Korábbi kérés');
  assistants[0] = appendMessage(harness, 'answer-old', 'Korábbi válasz');
  let current = harness.helpers.captureAssistantSnapshot();
  assert.notEqual(current.lastNodeId, previous.lastNodeId);
  assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), false);
  assistants.push(appendMessage(harness, 'answer-other-old', 'Eltérő régi szöveg'));
  current = harness.helpers.captureAssistantSnapshot();
  assert.equal(current.count > previous.count, true);
  assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), false);
});

test('Azonos fordítás egy valóban új user körhöz érvényes eredmény', () => {
  const { harness, users, assistants } = conversationHarness();
  users.push(appendMessage(harness, 'user-1', 'Kérés'));
  assistants.push(appendMessage(harness, 'answer-1', 'Azonos fordítás'));
  const previous = harness.helpers.captureAssistantSnapshot();
  users.push(appendMessage(harness, 'user-2', 'Másik kérés'));
  assert.equal(harness.helpers.isFreshAssistantSnapshot(harness.helpers.captureAssistantSnapshot(), previous), false,
    'A korábbi válasz az új user üzenet előtt van.');
  assistants.push(appendMessage(harness, 'answer-2', 'Azonos fordítás'));
  assert.equal(harness.helpers.isFreshAssistantSnapshot(harness.helpers.captureAssistantSnapshot(), previous), true);
  users.push(appendMessage(harness, 'user-3', 'Kézzel beküldött másik kérés'));
  assistants.push(appendMessage(harness, 'answer-3', 'Másik fordítás'));
  assert.equal(harness.helpers.isFreshAssistantSnapshot(harness.helpers.captureAssistantSnapshot(), previous), false,
    'A már azonosított kéréshez másik user kör válasza nem vehető át.');
});

test('Virtualizált beszélgetésben a stabil üzenetazonosító köti az új választ', () => {
  const { harness, users, assistants } = conversationHarness();
  users.push(appendMessage(harness, 'user-1', 'Kérés'));
  assistants.push(appendMessage(harness, 'answer-1', 'Azonos fordítás'));
  const previous = harness.helpers.captureAssistantSnapshot();
  users.splice(0, users.length, appendMessage(harness, 'user-2', 'Kérés'));
  assistants.splice(0, assistants.length, appendMessage(harness, 'answer-2', 'Azonos fordítás'));
  const current = harness.helpers.captureAssistantSnapshot();
  assert.equal(current.count, previous.count);
  assert.equal(current.userCount, previous.userCount);
  assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), true);
});

test('Stabil azonosító nélküli teljes DOM-csere önmagában nem friss eredmény', () => {
  const { harness, users, assistants } = conversationHarness();
  const user = appendMessage(harness, 'old', 'Kérés');
  const answer = appendMessage(harness, 'old-answer', 'Fordítás');
  user.attributes.delete('data-message-id'); answer.attributes.delete('data-message-id');
  users.push(user); assistants.push(answer);
  const previous = harness.helpers.captureAssistantSnapshot();
  const newUser = appendMessage(harness, 'replacement', 'Kérés');
  const newAnswer = appendMessage(harness, 'replacement-answer', 'Fordítás');
  newUser.attributes.delete('data-message-id'); newAnswer.attributes.delete('data-message-id');
  users[0] = newUser; assistants[0] = newAnswer;
  assert.equal(harness.helpers.isFreshAssistantSnapshot(harness.helpers.captureAssistantSnapshot(), previous), false);
});

test('Kép input.files beállítása és változatlan régi preview nem igazol csatolást', () => {
  const harness = createHarness();
  const before = { attachmentCount: 0, attachmentIndicatorKey: '', fileInputCount: 0, selectedFileKeys: [], hasPendingAttachmentWork: false };
  const selectedOnly = { ...before, fileInputCount: 1, selectedFileKeys: ['expected'] };
  assert.equal(harness.helpers.isAttachmentReadySnapshot(selectedOnly), false);
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot(selectedOnly, before, 'expected'), false);
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot({ ...selectedOnly, attachmentCount: 1, attachmentIndicatorKey: 'static-upload-wrapper', hasAttachmentPreview: false }, before, 'expected'), false);
  const ready = { ...selectedOnly, attachmentCount: 1, attachmentIndicatorKey: 'new-preview', hasAttachmentPreview: true };
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot(ready, before, 'expected'), true);
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot({ ...ready, hasPendingAttachmentWork: true }, before, 'expected'), false);
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot({ ...ready, sendButtonDisabled: true }, before, 'expected'), false);
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot(ready, before, 'different-file'), false);
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot(ready, ready, 'expected'), false);
  assert.equal(harness.helpers.isExpectedAttachmentReadySnapshot({ ...ready, fileInputCount: 0, selectedFileKeys: [] }, before, 'expected'), true);
});

test('Aszinkron képbeillesztés csak a teljes timeout után használ egyszeri drop fallbacket', async () => {
  let inputCount = 0; let dropCount = 0; let selectedKey = ''; let preview = false;
  const harness = createHarness({ overrides: {
    captureComposerAttachmentSnapshot: () => ({ attachmentCount: preview ? 2 : 1, attachmentIndicatorKey: preview ? 'static-wrapper|preview' : 'static-wrapper', hasAttachmentPreview: preview, fileInputCount: selectedKey ? 1 : 0, selectedFileKeys: selectedKey ? [selectedKey] : [], fileSelectionKey: selectedKey, hasPendingAttachmentWork: false }),
    attachViaFileInput: (_composer, file) => { inputCount += 1; selectedKey = `${file.name}:${file.size}:${file.type}:${file.lastModified}`; return true; },
    attachViaDrop: () => { dropCount += 1; preview = true; return true; },
  } });
  const pending = harness.window.__gamerTranslatorDeliver({ imageDataUrl: 'data:image/png;base64,aGVsbG8=', pageReadyTimeoutMs: 40, diagnosticCallId: 'image-test' });
  await harness.advance(20);
  assert.equal(inputCount, 1); assert.equal(dropCount, 0);
  await harness.advance(20);
  const result = await pending;
  assert.equal(result.ok, true); assert.equal(dropCount, 1);
  const events = harness.window.__gamerTranslatorDiagnostics['image-test'].map((entry) => entry.event);
  assert.equal(events.includes('attachment_timeout'), true);
  assert.equal(events.includes('attachment_ready'), true);
});

test('Aktív képfeldolgozás timeoutja nem indít újabb feltöltést', async () => {
  let inputCount = 0; let dropCount = 0; let selectedKey = '';
  const harness = createHarness({ overrides: {
    captureComposerAttachmentSnapshot: () => ({ attachmentCount: 0, attachmentIndicatorKey: '', fileInputCount: selectedKey ? 1 : 0, selectedFileKeys: selectedKey ? [selectedKey] : [], fileSelectionKey: selectedKey, hasPendingAttachmentWork: Boolean(selectedKey) }),
    attachViaFileInput: (_composer, file) => { inputCount += 1; selectedKey = `${file.name}:${file.size}:${file.type}:${file.lastModified}`; return true; },
    attachViaDrop: () => { dropCount += 1; return true; },
  } });
  const pending = harness.window.__gamerTranslatorDeliver({ imageDataUrl: 'data:image/png;base64,aGVsbG8=', pageReadyTimeoutMs: 40 });
  await harness.advance(40);
  assert.equal((await pending).ok, false); assert.equal(inputCount, 1); assert.equal(dropCount, 0);
});

test('Válasz timeout után a késői eredmény ugyanahhoz a kéréshez érkezhet', async () => {
  const { harness, users, assistants } = conversationHarness();
  const callbacks = new Set();
  harness.window.__gamerTranslatorDomTracker.subscribe = (callback) => { callbacks.add(callback); return () => callbacks.delete(callback); };
  harness.window.__testOverrides.submitTextMessage = async () => { users.push(appendMessage(harness, 'user-late', 'Kérés')); };
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'Kérés', autoSubmit: true, copyResponseToClipboard: true, responseTimeoutMs: 40, progressCallId: 'late-test', diagnosticCallId: 'late-diagnostics' });
  await harness.advance(40);
  const result = await pending;
  assert.equal(result.ok, false); assert.equal(result.responsePending, true); assert.equal(result.followUpProgressCallId, 'late-test-followup');
  assistants.push(appendMessage(harness, 'answer-late', 'Késői fordítás'));
  for (const callback of [...callbacks]) callback();
  const progress = JSON.parse(harness.window.__gamerTranslatorProgress['late-test-followup']);
  assert.equal(progress.kind, 'assistant_response'); assert.equal(progress.text, 'Késői fordítás');
  assert.equal(harness.window.__gamerTranslatorDiagnostics['late-diagnostics'].some((entry) => entry.event === 'response_received' && entry.fields.late), true);
  const snapshots = harness.window.__gamerTranslatorDiagnostics['late-diagnostics'].filter((entry) => entry.event === 'response_snapshot');
  assert.equal(snapshots.some((entry) => !entry.fields.late && entry.fields.request_user_bound && entry.fields.rejection_reason === 'response_user_mismatch'), true);
  assert.equal(snapshots.some((entry) => entry.fields.late && entry.fields.request_user_bound
    && entry.fields.last_user_matches_request && entry.fields.response_user_matches_request
    && entry.fields.assistant_identity_new && entry.fields.rejection_reason === 'none'), true);
  users.push(appendMessage(harness, 'user-other', 'Másik kérés'));
  assistants.push(appendMessage(harness, 'answer-other', 'Idegen válasz'));
  for (const callback of [...callbacks]) callback();
  const doneProgress = JSON.parse(harness.window.__gamerTranslatorProgress['late-test-followup']);
  assert.equal(doneProgress.kind, 'assistant_response'); assert.equal(doneProgress.done, true);
  assert.equal(doneProgress.text, 'Késői fordítás');
  assert.equal(callbacks.size, 0);
});

test('Üres kezdetű késői válaszfigyelés legfeljebb 120 másodpercig marad aktív', async () => {
  const { harness, users } = conversationHarness();
  harness.window.__testOverrides.submitTextMessage = async () => { users.push(appendMessage(harness, 'user-wait', 'Kérés')); };
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'Kérés', autoSubmit: true, copyResponseToClipboard: true, responseTimeoutMs: 40, progressCallId: 'bounded-test' });
  await harness.advance(40);
  assert.equal((await pending).responsePending, true);
  await harness.advance(119999);
  assert.equal(Boolean(harness.window.__gamerTranslatorAssistantResponseFollowUps['bounded-test-followup']), true);
  await harness.advance(1);
  assert.equal(harness.window.__gamerTranslatorAssistantResponseFollowUps['bounded-test-followup'], undefined);
  assert.equal(JSON.parse(harness.window.__gamerTranslatorProgress['bounded-test-followup']).kind, 'assistant_response_watch_done');
});

test('Új kézbesítés leállítja a korábbi késői figyelést', async () => {
  const { harness, users } = conversationHarness();
  harness.window.__testOverrides.submitTextMessage = async () => { users.push(appendMessage(harness, 'user-first', 'Első kérés')); };
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'Első kérés', autoSubmit: true, copyResponseToClipboard: true, responseTimeoutMs: 40, progressCallId: 'first-test' });
  await harness.advance(40);
  assert.equal((await pending).responsePending, true);
  assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'Második kérés', autoSubmit: false })).ok, true);
  assert.equal(harness.window.__gamerTranslatorAssistantResponseFollowUps['first-test-followup'], undefined);
});

test('A diagnosztika korlátos és kizárja a szöveget, képet és URL-t', () => {
  const harness = createHarness();
  for (let index = 0; index < 150; index += 1) {
    harness.helpers.writeDiagnosticEntry('diagnostic-test', 'response_snapshot', { text_length: index, prompt_text: 'titkos szöveg', imageDataUrl: 'data:image/png;base64,aGVsbG8=', url: 'https://example.com/private', reason: 'https://example.com/private', stage: 'response', pending: false });
  }
  const entries = harness.window.__gamerTranslatorDiagnostics['diagnostic-test'];
  assert.equal(entries.length, 100); assert.equal(entries[0].fields.text_length, 50);
  assert.equal(entries[0].seq, 51); assert.equal(entries.at(-1).seq, 150);
  assert.deepEqual(Object.keys(entries[0].fields).sort(), ['pending', 'stage', 'text_length']);
  const serialized = JSON.stringify(entries);
  assert.equal(serialized.includes('titkos'), false); assert.equal(serialized.includes('data:image'), false); assert.equal(serialized.includes('https://'), false);
  for (let index = 0; index < 30; index += 1) harness.helpers.writeDiagnosticEntry(`call-${index}`, 'composer_ready');
  assert.equal(Object.keys(harness.window.__gamerTranslatorDiagnostics).length, 16);
});

test('Kéréskötési diagnosztika csak bool értéket és ismert ok/szerep tokent enged át', () => {
  const harness = createHarness();
  harness.helpers.writeDiagnosticEntry('binding-types', 'response_snapshot', {
    request_user_bound: 'raw_request_secret', last_user_matches_request: 1,
    response_user_matches_request: null, assistant_identity_new: {},
    user_role_source: 'raw_user_secret', rejection_reason: 'raw_assistant_secret',
  });
  assert.equal(Object.keys(harness.window.__gamerTranslatorDiagnostics['binding-types'][0].fields).length, 0);
  harness.helpers.writeDiagnosticEntry('binding-types', 'response_snapshot', {
    request_user_bound: true, last_user_matches_request: false, response_user_matches_request: true,
    assistant_identity_new: false, user_role_source: 'conversation_role', rejection_reason: 'response_user_mismatch',
  });
  const fields = harness.window.__gamerTranslatorDiagnostics['binding-types'][1].fields;
  assert.equal(fields.request_user_bound, true); assert.equal(fields.last_user_matches_request, false);
  assert.equal(fields.response_user_matches_request, true); assert.equal(fields.assistant_identity_new, false);
  assert.equal(fields.user_role_source, 'conversation_role'); assert.equal(fields.rejection_reason, 'response_user_mismatch');
  assert.equal(JSON.stringify(harness.window.__gamerTranslatorDiagnostics).includes('secret'), false);
});

test('Első és késői snapshot minden kötési elutasítás okát tartalommentesen jelzi', async () => {
  const harness = createHarness();
  await harness.window.__gamerTranslatorDeliver({ prompt: 'Előkészítés', autoSubmit: false, diagnosticCallId: 'binding-reasons' });
  const previous = {
    lastUserKey: 'message:old_secret_user', lastUserStableId: 'message:old_secret_user',
    userKeys: ['message:old_secret_user'], assistantStableIds: ['message:old_secret_answer'],
  };
  const current = {
    count: 2, userCount: 2, lastText: 'titkos fordítás', lastStableId: 'message:new_secret_answer', lastNodeId: 'new_secret_node',
    lastUserKey: 'message:new_secret_user', lastUserStableId: 'message:new_secret_user',
    userKeys: ['message:old_secret_user', 'message:new_secret_user'], responseUserKey: 'message:new_secret_user',
    lastUserRoleSource: 'conversation_role', lastPending: false,
  };
  const variants = [
    ['request_user_unbound', { ...current, lastUserKey: previous.lastUserKey, lastUserStableId: previous.lastUserStableId, userKeys: previous.userKeys }, false],
    ['last_user_mismatch', { ...current, lastUserKey: 'message:other_secret_user' }, true],
    ['response_user_mismatch', { ...current, responseUserKey: previous.lastUserKey }, true],
    ['assistant_identity_old', { ...current, lastStableId: previous.assistantStableIds[0] }, true],
    ['assistant_text_missing', { ...current, lastText: '' }, true],
    ['assistant_text_transient', { ...current, lastText: 'Thinking' }, true],
    ['assistant_pending', { ...current, generationPending: true }, true],
    ['none', current, true],
  ];
  for (const [reason, snapshot, bound] of variants) {
    for (const late of [false, true]) {
      const baseline = { ...previous, requestUserKey: bound ? current.lastUserKey : '' };
      harness.helpers.reportAssistantSnapshotDiagnostic(snapshot, baseline, { late });
      const last = harness.window.__gamerTranslatorDiagnostics['binding-reasons'].at(-1);
      assert.equal(last.event, 'response_snapshot'); assert.equal(last.fields.rejection_reason, reason);
      assert.equal(last.fields.request_user_bound, bound); assert.equal(last.fields.late, late);
      assert.equal(last.fields.user_role_source, 'conversation_role');
    }
  }
  const serialized = JSON.stringify(harness.window.__gamerTranslatorDiagnostics);
  assert.equal(serialized.includes('secret'), false); assert.equal(serialized.includes('titkos'), false);
});


test('Képfeltöltés teljes kudarca kitakarítja a saját fájlmezőt a következő kivágáshoz', async () => {
  let input = null; let preview = false; let shouldSucceed = false;
  const harness = createHarness({ overrides: {
    captureComposerAttachmentSnapshot: () => {
      const selected = Array.from(input?.files || []).map((file) => `${file.name}:${file.size}:${file.type}:${file.lastModified}`);
      return { attachmentCount: preview ? 1 : 0, attachmentIndicatorKey: preview ? 'preview' : '', hasAttachmentPreview: preview, fileInputCount: selected.length, selectedFileKeys: selected, fileSelectionKey: selected.join('||'), hasPendingAttachmentWork: false };
    },
    attachViaFileInput: (_composer, file) => { input.files = [file]; preview = shouldSucceed; return true; },
    attachViaDrop: () => true,
  } });
  input = harness.document.body.appendChild(new FakeInput('input')); input.type = 'file'; input.files = [];
  Object.defineProperty(input, 'value', { get: () => '', set: (value) => { if (value === '') input.files = []; } });
  harness.document.body.querySelectorAll = (selector) => selector === 'input[type="file"]' ? [input] : [];
  const payload = { imageDataUrl: 'data:image/png;base64,aGVsbG8=', pageReadyTimeoutMs: 40, diagnosticCallId: 'cleanup-test' };
  const failed = harness.window.__gamerTranslatorDeliver(payload);
  await harness.advance(80);
  assert.equal((await failed).ok, false); assert.equal(input.files.length, 0);
  assert.equal(harness.window.__gamerTranslatorDiagnostics['cleanup-test'].some((entry) => entry.event === 'attachment_selection_cleared' && entry.fields.ok), true);
  shouldSucceed = true;
  assert.equal((await harness.window.__gamerTranslatorDeliver(payload)).ok, true);
  assert.equal(input.files.length, 1, 'A sikeres csatolmány fájlmezőjét meg kell őrizni.');
});

test('Sikertelen várakozás valós preview vagy folyamatban levő feltöltés fájlját nem törli', async () => {
  for (const mode of ['preview', 'pending']) {
    let input = null;
    const harness = createHarness({ overrides: {
      captureComposerAttachmentSnapshot: () => {
        const selected = Array.from(input?.files || []).map((file) => `${file.name}:${file.size}:${file.type}:${file.lastModified}`);
        const present = Boolean(selected.length);
        return { attachmentCount: present && mode === 'preview' ? 1 : 0, attachmentIndicatorKey: present && mode === 'preview' ? 'preview' : '', hasAttachmentPreview: present && mode === 'preview', sendButtonDisabled: present, fileInputCount: selected.length, selectedFileKeys: selected, fileSelectionKey: selected.join('||'), hasPendingAttachmentWork: present && mode === 'pending' };
      },
      attachViaFileInput: (_composer, file) => { input.files = [file]; return true; },
      attachViaDrop: () => { throw new Error('Nem indulhat második feltöltés.'); },
    } });
    input = harness.document.body.appendChild(new FakeInput('input')); input.type = 'file'; input.files = [];
    Object.defineProperty(input, 'value', { get: () => '', set: (value) => { if (value === '') input.files = []; } });
    harness.document.body.querySelectorAll = (selector) => selector === 'input[type="file"]' ? [input] : [];
    const pending = harness.window.__gamerTranslatorDeliver({ imageDataUrl: 'data:image/png;base64,aGVsbG8=', pageReadyTimeoutMs: 40 });
    await harness.advance(40);
    assert.equal((await pending).ok, false); assert.equal(input.files.length, 1, mode);
  }
});

test('Késleltetett poll esetén a lezáró progress rekord megőrzi a késői végső választ', async () => {
  const { harness, users, assistants } = conversationHarness();
  const callbacks = new Set();
  harness.window.__gamerTranslatorDomTracker.subscribe = (callback) => { callbacks.add(callback); return () => callbacks.delete(callback); };
  harness.window.__testOverrides.submitTextMessage = async () => { users.push(appendMessage(harness, 'user-delayed-poll', 'Kérés')); };
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'Kérés', autoSubmit: true, copyResponseToClipboard: true, responseTimeoutMs: 40, progressCallId: 'delayed-poll' });
  await harness.advance(40);
  assert.equal((await pending).responsePending, true);
  assistants.push(appendMessage(harness, 'answer-delayed-poll', 'A végső fordítás megmarad.'));
  for (const callback of [...callbacks]) callback();
  // A Python oldali poll ebben a 4 másodpercben egyáltalán nem olvassa a bucketet.
  await harness.advance(4000);
  const progress = JSON.parse(harness.window.__gamerTranslatorProgress['delayed-poll-followup']);
  assert.equal(progress.done, true); assert.equal(progress.kind, 'assistant_response');
  assert.equal(progress.text, 'A végső fordítás megmarad.');
  assert.equal(harness.window.__gamerTranslatorAssistantResponseFollowUps['delayed-poll-followup'], undefined);
  assert.equal(callbacks.size, 0);
});


test('Vágólapmásolás nélkül is kérhető befejezett fordítás a begépelési cache-hez', async () => {
  let watched = 0;
  const harness = createHarness({ overrides: {
    submitTextMessage: async () => {},
    waitForAssistantResponse: async () => { watched += 1; return { text: 'Kész fordítás' }; },
  } });
  const result = await harness.window.__gamerTranslatorDeliver({ prompt: 'Kérés', autoSubmit: true, copyResponseToClipboard: false, waitForResponse: true });
  assert.equal(result.ok, true); assert.equal(result.assistantResponseText, 'Kész fordítás');
  assert.equal(result.assistantResponseComplete, true); assert.equal(watched, 1);
});

test('Streaming timeout nem ad kész fordítást, azonos szöveg befejezése később átvehető', async () => {
  const baseline = { count: 0, lastText: '', lastNodeId: '', lastPending: false, lastUserKey: '', userKeys: [], userNodeIds: [], assistantNodeIds: [], assistantStableIds: [] };
  let current = baseline;
  const partial = { count: 1, lastText: 'Még folyamatban levő szöveg', lastNodeId: 'assistant-1', lastStableId: 'message:answer-1', lastPending: true, lastUserKey: 'message:user-1', lastUserStableId: 'message:user-1', userKeys: ['message:user-1'], userNodeIds: ['user-node-1'], assistantNodeIds: ['assistant-1'], assistantStableIds: ['message:answer-1'], responseUserKey: 'message:user-1', userCount: 1 };
  const harness = createHarness({ overrides: { captureAssistantSnapshot: () => current, submitTextMessage: async () => { current = partial; } } });
  const callbacks = new Set();
  harness.window.__gamerTranslatorDomTracker.subscribe = (callback) => { callbacks.add(callback); return () => callbacks.delete(callback); };
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'Kérés', autoSubmit: true, waitForResponse: true, responseTimeoutMs: 40, progressCallId: 'streaming-test' });
  await harness.advance(40);
  const result = await pending;
  assert.equal(result.ok, false); assert.equal(result.responsePending, true);
  assert.equal(Boolean(result.assistantResponseText), false);
  await harness.advance(16000);
  assert.equal(Boolean(harness.window.__gamerTranslatorAssistantResponseFollowUps['streaming-test-followup']), true);
  current = { ...partial, lastPending: false };
  for (const callback of [...callbacks]) callback();
  const progress = JSON.parse(harness.window.__gamerTranslatorProgress['streaming-test-followup']);
  assert.equal(progress.text, partial.lastText); assert.equal(progress.complete, true);
});

test('Vegyes közvetlen és article üzenetek egyesítve és duplikáció nélkül látszanak', () => {
  const harness = createHarness();
  const article = harness.document.body.appendChild(new FakeElement('article'));
  article.setAttribute('aria-label', 'assistant');
  const direct = article.appendChild(new FakeElement('div'));
  direct.setAttribute('data-message-author-role', 'assistant'); direct.appendChild(new FakeText('Korábbi válasz'));
  const newer = harness.document.body.appendChild(new FakeElement('article'));
  newer.setAttribute('aria-label', 'assistant'); newer.appendChild(new FakeText('Új válasz'));
  harness.document.querySelectorAll = (selector) => selector === '[data-message-author-role="assistant"]' ? [direct]
    : selector === '[data-testid^="conversation-turn-"], article, [data-chatgpt-search-unit-key][data-chatgpt-search-message-ids]' ? [article, newer] : [];
  const found = harness.helpers.findAssistantMessageNodes();
  assert.equal(found.length, 2); assert.equal(found[0], direct); assert.equal(found[1], newer);
});

test('Article szerzőfejléc helyett a markdown választest kerül kiolvasásra', () => {
  const harness = createHarness();
  const article = new FakeElement('article');
  article.appendChild(new FakeElement('h5')).appendChild(new FakeText('Assistant said:'));
  const content = article.appendChild(new FakeElement('div'));
  content.appendChild(new FakeText('A kész fordítás.'));
  article.querySelector = (selector) => selector === '.markdown' ? content : null;
  assert.equal(harness.helpers.extractMessageText(article), 'A kész fordítás.');
  const fallback = new FakeElement('article');
  const heading = fallback.appendChild(new FakeElement('h5')); heading.setAttribute('class', 'sr-only');
  heading.appendChild(new FakeText('ChatGPT said:'));
  fallback.appendChild(new FakeText('A kész fordítás.'));
  assert.equal(harness.helpers.extractMessageText(fallback), 'A kész fordítás.');
});


function modernDomHarness() {
  const harness = createHarness();
  const installQueries = (root) => {
    const all = [];
    const walk = (node) => { for (const child of node.childNodes) { if (child instanceof FakeElement) { all.push(child); walk(child); } } };
    walk(root);
    for (const element of [root, ...all]) {
      element.querySelectorAll = (selector) => {
        const found = [];
        const descend = (node) => { for (const child of node.childNodes) { if (child instanceof FakeElement) { if (child.matches(selector)) found.push(child); descend(child); } } };
        descend(element); return found;
      };
      element.querySelector = (selector) => element.querySelectorAll(selector)[0] || null;
    }
  };
  const addTurn = (index, text, withAssistant = true) => {
    const turn = harness.document.body.appendChild(new FakeElement('div')); turn.setAttribute('data-turn-key', `shared-turn-${index}`);
    const userUnit = turn.appendChild(new FakeElement('div')); userUnit.setAttribute('data-chatgpt-search-unit-key', `user-unit-${index}`);
    userUnit.setAttribute('data-chatgpt-search-message-ids', `["user-${index}"]`);
    const bubble = userUnit.appendChild(new FakeElement('div')); bubble.setAttribute('data-user-message-bubble', '');
    bubble.appendChild(new FakeText('Mesterséges kérés'));
    let assistantBody = null;
    if (withAssistant) {
      const assistantUnit = turn.appendChild(new FakeElement('div')); assistantUnit.setAttribute('data-chatgpt-search-unit-key', `assistant-unit-${index}`);
      assistantUnit.setAttribute('data-chatgpt-search-message-ids', `["assistant-${index}"]`);
      assistantUnit.setAttribute('data-content-search-unit-key', `assistant-unit-${index}`);
      const heading = assistantUnit.appendChild(new FakeElement('h4')); heading.setAttribute('data-conversation-role', 'assistant'); heading.setAttribute('class', 'sr-only');
      heading.appendChild(new FakeText('ChatGPT said:'));
      assistantBody = assistantUnit.appendChild(new FakeElement('div')); assistantBody.setAttribute('data-chatgpt-selection-message-id', `assistant-${index}`);
      const markdown = assistantBody.appendChild(new FakeElement('div')); markdown.setAttribute('data-markdown-text-style', ''); markdown.setAttribute('class', 'MarkdownRoot-fixture');
      markdown.appendChild(new FakeText(text));
    }
    installQueries(harness.document);
    return { bubble, assistantBody };
  };
  const addRoleImageTurn = (index, text, { searchMetadata = false, boundary = 'div' } = {}) => {
    const turn = harness.document.body.appendChild(new FakeElement('div'));
    const userUnit = turn.appendChild(new FakeElement(boundary));
    userUnit.setAttribute('data-message-id', `role-image-user-${index}`);
    if (searchMetadata) {
      userUnit.setAttribute('data-chatgpt-search-unit-key', `role-image-unit-${index}`);
      userUnit.setAttribute('data-chatgpt-search-message-ids', `["role-image-user-${index}"]`);
    }
    const userHeading = userUnit.appendChild(new FakeElement('h4'));
    userHeading.setAttribute('data-conversation-role', 'user'); userHeading.setAttribute('class', 'sr-only');
    userHeading.appendChild(new FakeText('You said:'));
    const image = userUnit.appendChild(new FakeImage('img'));
    image.setAttribute('src', 'data:image/png;base64,aGVsbG8=');
    const assistantUnit = turn.appendChild(new FakeElement('div'));
    assistantUnit.setAttribute('data-chatgpt-search-unit-key', `role-image-answer-unit-${index}`);
    assistantUnit.setAttribute('data-chatgpt-search-message-ids', `["role-image-answer-${index}"]`);
    const heading = assistantUnit.appendChild(new FakeElement('h4'));
    heading.setAttribute('data-conversation-role', 'assistant'); heading.setAttribute('class', 'sr-only');
    const assistantBody = assistantUnit.appendChild(new FakeElement('div'));
    assistantBody.setAttribute('data-chatgpt-selection-message-id', `role-image-answer-${index}`);
    const markdown = assistantBody.appendChild(new FakeElement('div'));
    markdown.setAttribute('data-markdown-text-style', ''); markdown.appendChild(new FakeText(text));
    installQueries(harness.document);
    return { turn, userUnit, userHeading, image, assistantBody };
  };
  const addLiveHeadingImageTurn = (index, text) => {
    const result = addRoleImageTurn(index, text);
    const { userUnit, userHeading, image } = result;
    userUnit.attributes.delete('data-message-id');
    userHeading.attributes.delete('data-conversation-role');
    userHeading.replaceChildren(new FakeText('You said:'));
    userUnit.childNodes = userUnit.childNodes.filter((node) => node !== image);
    const content = userUnit.appendChild(new FakeElement('div'));
    content.setAttribute('data-chatgpt-search-unit-key', `live-user-unit-${index}`);
    content.setAttribute('data-chatgpt-search-message-ids', `["live-user-${index}"]`);
    const imageWrapper = content.appendChild(new FakeElement('div'));
    const viewer = imageWrapper.appendChild(new FakeElement('div')); viewer.setAttribute('role', 'button');
    viewer.setAttribute('aria-label', 'Enlarge image');
    image.setAttribute('src', `blob:https://chatgpt.com/synthetic-image-${index}`);
    image.setAttribute('data-state', 'loaded'); viewer.appendChild(image);
    installQueries(harness.document);
    return { ...result, content, imageWrapper, viewer };
  };
  return { harness, addTurn, addRoleImageTurn, addLiveHeadingImageTurn, refreshQueries: () => installQueries(harness.document) };
}

test('Az új, article nélküli ChatGPT DOM szerepei és üzenetazonosítói felismerhetők', () => {
  const { harness, addTurn } = modernDomHarness();
  addTurn(1, 'Azonos fordítás');
  const previous = harness.helpers.captureAssistantSnapshot();
  assert.equal(previous.count, 1); assert.equal(previous.userCount, 1);
  assert.equal(previous.lastText, 'Azonos fordítás'); assert.equal(previous.lastStableId, 'message:assistant-1');
  assert.equal(previous.lastUserStableId, 'messages:["user-1"]');
  assert.notEqual(previous.lastStableId, previous.lastUserStableId);
  addTurn(2, 'Azonos fordítás');
  const current = harness.helpers.captureAssistantSnapshot();
  assert.equal(current.count, 2); assert.equal(current.userCount, 2);
  assert.equal(current.lastText.includes('ChatGPT said:'), false);
  assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), true);
});

test('Az új ChatGPT user bubble szöveg nélküli képkérésként is külön üzenet', () => {
  const { harness, addTurn } = modernDomHarness();
  const { bubble } = addTurn(1, '', false);
  bubble.replaceChildren(new FakeImage('img'));
  const snapshot = harness.helpers.captureAssistantSnapshot();
  assert.equal(snapshot.userCount, 1); assert.equal(snapshot.lastUserStableId, 'messages:["user-1"]');
});

test('Szerepfejléces kép-only user kör keresőattribútumok és bubble nélkül is az új válaszhoz köthető', () => {
  for (const boundary of ['div', 'article']) {
    const { harness, addTurn, addRoleImageTurn } = modernDomHarness();
    addTurn(1, 'Korábbi fordítás');
    const previous = harness.helpers.captureAssistantSnapshot();
    addRoleImageTurn(2, 'A képkérés kész fordítása.', { boundary });
    const current = harness.helpers.captureAssistantSnapshot();
    assert.equal(current.userCount, 2, boundary);
    assert.equal(current.lastUserStableId, 'message:role-image-user-2', boundary);
    assert.equal(current.responseUserKey, current.lastUserKey, boundary);
    assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), true, boundary);
  }
});

test('Az igazolt élő attribútum nélküli UI-fejléc a saját stabil képkörét és két azonos választ köti', async () => {
  const { harness, addTurn, addLiveHeadingImageTurn } = modernDomHarness();
  addTurn(1, 'Korábbi fordítás');
  const userKeys = [];
  for (const index of [2, 3]) {
    const previous = harness.helpers.captureAssistantSnapshot();
    const { userHeading, image } = addLiveHeadingImageTurn(index, 'Azonos kész fordítás.');
    const current = harness.helpers.captureAssistantSnapshot();
    assert.equal(current.userCount, index); assert.equal(current.count, index);
    assert.equal(current.lastUserStableId, `messages:["live-user-${index}"]`);
    assert.equal(current.lastUserRoleSource, 'heading_role');
    assert.equal(current.responseUserKey, current.lastUserKey);
    assert.equal(harness.helpers.getUiMessageHeadingRole(userHeading), 'user');
    assert.equal(harness.helpers.getMessageAuthorEvidence(image).role, 'user');
    assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), true);
    userKeys.push(current.lastUserKey);
    await harness.window.__gamerTranslatorDeliver({ prompt: 'Diagnosztikapróba', diagnosticCallId: `live-heading-${index}` });
    harness.helpers.reportAssistantSnapshotDiagnostic(current, previous);
    const fields = harness.window.__gamerTranslatorDiagnostics[`live-heading-${index}`].at(-1).fields;
    assert.equal(fields.user_role_source, 'heading_role');
    assert.equal(fields.request_user_bound, true); assert.equal(fields.fresh, true);
    assert.equal(fields.user_role_candidates, index); assert.equal(fields.clickable_image_candidates, index - 1);
  }
  assert.notEqual(...userKeys);
});

test('A belső saját keresőazonosítót közös user-assistant külső message-id nem írja felül', () => {
  const { harness, addTurn, addLiveHeadingImageTurn, refreshQueries } = modernDomHarness();
  addTurn(1, 'Korábbi fordítás');
  const previous = harness.helpers.captureAssistantSnapshot();
  const { turn, content } = addLiveHeadingImageTurn(2, 'Új képkör fordítása.');
  turn.setAttribute('data-message-id', 'shared-outer-turn-id'); refreshQueries();
  const current = harness.helpers.captureAssistantSnapshot();
  assert.equal(harness.helpers.getMessageStableId(content), 'messages:["live-user-2"]');
  assert.equal(current.lastUserStableId, 'messages:["live-user-2"]');
  assert.equal(current.lastStableId, 'message:role-image-answer-2');
  assert.notEqual(current.lastUserStableId, current.lastStableId);
  assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), true);
});

test('UI-fejléc helyett idézett tartalom, pontatlan név és határ nélküli kép nem bizonyíthat user szerepet', () => {
  const invalidKinds = ['non-heading', 'not-sr-only', 'partial-label', 'no-own-boundary', 'empty-identity', 'multiple-content-units',
    'quoted', 'code', 'markdown', 'search-content', 'assistant-wrapper', 'mixed-role',
    'hidden-heading', 'hidden-image', 'hidden-wrapper', 'aria-hidden-heading', 'avatar', 'menu', 'toolbar'];
  for (const kind of invalidKinds) {
    const { harness, addTurn, addLiveHeadingImageTurn, refreshQueries } = modernDomHarness();
    addTurn(1, 'Korábbi fordítás');
    const previous = harness.helpers.captureAssistantSnapshot();
    const { userUnit, userHeading, content, imageWrapper, image } = addLiveHeadingImageTurn(2, 'Különálló új asszisztensválasz.');
    if (kind === 'non-heading') userHeading.tagName = 'DIV';
    else if (kind === 'not-sr-only') userHeading.setAttribute('class', '');
    else if (kind === 'partial-label') userHeading.replaceChildren(new FakeText('Young user: You said:'));
    else if (kind === 'no-own-boundary') { content.attributes.delete('data-chatgpt-search-unit-key'); content.attributes.delete('data-chatgpt-search-message-ids'); }
    else if (kind === 'empty-identity') content.setAttribute('data-chatgpt-search-message-ids', '');
    else if (kind === 'multiple-content-units') { const other = userUnit.appendChild(new FakeElement('div')); other.setAttribute('data-chatgpt-search-unit-key', 'other-user'); other.setAttribute('data-chatgpt-search-message-ids', 'other-id'); }
    else if (['quoted', 'code', 'markdown', 'search-content'].includes(kind)) {
      userUnit.childNodes = userUnit.childNodes.filter((node) => node !== userHeading);
      if (kind === 'search-content') content.appendChild(userHeading);
      else { const wrapper = userUnit.appendChild(new FakeElement(kind === 'quoted' ? 'blockquote' : kind === 'code' ? 'code' : 'div'));
        if (kind === 'markdown') wrapper.setAttribute('data-markdown-text-style', ''); wrapper.appendChild(userHeading); }
    } else if (kind === 'assistant-wrapper') userUnit.setAttribute('data-message-author-role', 'assistant');
    else if (kind === 'mixed-role') { const other = userUnit.appendChild(new FakeElement('h4')); other.setAttribute('data-conversation-role', 'assistant'); }
    else if (kind === 'hidden-heading') userHeading.hidden = true;
    else if (kind === 'hidden-image') image.hidden = true;
    else if (kind === 'hidden-wrapper') userUnit.setAttribute('hidden', '');
    else if (kind === 'aria-hidden-heading') userHeading.setAttribute('aria-hidden', 'true');
    else if (kind === 'avatar') imageWrapper.setAttribute('data-slot', 'avatar');
    else imageWrapper.setAttribute('role', kind);
    refreshQueries();
    const current = harness.helpers.captureAssistantSnapshot();
    assert.equal(current.userCount, 1, kind);
    assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), false, kind);
    assert.equal(Boolean(previous.requestUserKey), false, kind);
  }
});

test('Keresőüzenet belsejében idézett plain assistant UI-fejléc sem adhat szerepet', () => {
  const { harness, addLiveHeadingImageTurn, refreshQueries } = modernDomHarness();
  const { userUnit, userHeading, content } = addLiveHeadingImageTurn(1, 'Különálló válasz.');
  userUnit.childNodes = userUnit.childNodes.filter((node) => node !== userHeading);
  userHeading.replaceChildren(new FakeText('ChatGPT said:')); content.appendChild(userHeading); refreshQueries();
  assert.equal(harness.helpers.getUiMessageHeadingRole(userHeading), '');
  assert.equal(harness.helpers.getMessageAuthorEvidence(content).role, '');
  assert.equal(harness.helpers.findUserMessageNodes().length, 0);
});

test('Kattintható kép explicit user szerep mellett a második kérés saját válaszához köthető', async () => {
  for (const buttonKind of ['button', 'role-button', 'dialog-button', 'dialog-role-button']) {
    const { harness, addTurn, addRoleImageTurn, refreshQueries } = modernDomHarness();
    addTurn(1, 'Korábbi fordítás');
    const previous = harness.helpers.captureAssistantSnapshot();
    const { userUnit, image } = addRoleImageTurn(2, 'A második kép kész fordítása.');
    userUnit.childNodes = userUnit.childNodes.filter((node) => node !== image);
    const nativeButton = buttonKind === 'button' || buttonKind === 'dialog-button';
    const viewer = userUnit.appendChild(new FakeElement(nativeButton ? 'button' : 'div'));
    if (nativeButton) viewer.setAttribute('type', 'button');
    else viewer.setAttribute('role', 'button');
    if (buttonKind.startsWith('dialog-')) viewer.setAttribute('aria-haspopup', 'dialog');
    viewer.appendChild(image); refreshQueries();
    const current = harness.helpers.captureAssistantSnapshot();
    assert.equal(current.userCount, 2, buttonKind);
    assert.equal(current.responseUserKey, current.lastUserKey, buttonKind);
    assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), true, buttonKind);
    await harness.window.__gamerTranslatorDeliver({ prompt: 'Diagnosztikapróba', diagnosticCallId: 'clickable-diagnostic' });
    harness.helpers.reportAssistantSnapshotDiagnostic(current, previous);
    const fields = harness.window.__gamerTranslatorDiagnostics['clickable-diagnostic'].at(-1).fields;
    assert.equal(fields.user_role_candidates, 2); assert.equal(fields.clickable_image_candidates, 1);
  }
});

test('Explicit user szerep mellett is kizárt az avatar, menü, toolbar és beküldőikon képe', () => {
  for (const invalidKind of ['avatar-image', 'avatar-wrapper', 'profile-alt', 'menu', 'toolbar', 'radix-menu', 'radix-dropdown', 'popup-button', 'submit-button', 'avatar-dialog', 'menu-dialog']) {
    const { harness, addRoleImageTurn, refreshQueries } = modernDomHarness();
    const { userUnit, image } = addRoleImageTurn(1, 'Különálló kész asszisztensválasz.');
    userUnit.childNodes = userUnit.childNodes.filter((node) => node !== image);
    const wrapper = userUnit.appendChild(new FakeElement('div'));
    const button = wrapper.appendChild(new FakeElement('button')); button.setAttribute('type', 'button'); button.appendChild(image);
    if (invalidKind === 'avatar-image') image.setAttribute('data-testid', 'user-avatar');
    else if (invalidKind === 'avatar-wrapper') wrapper.setAttribute('data-slot', 'avatar');
    else if (invalidKind === 'profile-alt') image.setAttribute('alt', 'User profile picture');
    else if (invalidKind === 'menu' || invalidKind === 'toolbar') wrapper.setAttribute('role', invalidKind);
    else if (invalidKind === 'radix-menu') wrapper.setAttribute('data-radix-menu-content', '');
    else if (invalidKind === 'radix-dropdown') wrapper.setAttribute('data-radix-dropdown-menu-content', '');
    else if (invalidKind === 'popup-button') button.setAttribute('aria-haspopup', 'menu');
    else if (invalidKind === 'avatar-dialog') { button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-label', 'Open user avatar'); }
    else if (invalidKind === 'menu-dialog') { button.setAttribute('aria-haspopup', 'dialog'); wrapper.setAttribute('role', 'menu'); }
    else button.setAttribute('type', 'submit');
    refreshQueries();
    assert.equal(harness.helpers.findUserMessageNodes().length, 0, invalidKind);
  }
});

test('Megmaradt régi stabil user horgony új DOM-node mellett az azonosító nélküli új képkérést is köti', () => {
  const { harness, addTurn, addRoleImageTurn, refreshQueries } = modernDomHarness();
  const { bubble } = addTurn(1, 'Korábbi fordítás');
  const previous = harness.helpers.captureAssistantSnapshot();
  const oldUnit = bubble.parentElement;
  const redrawnOldBubble = new FakeElement('div'); redrawnOldBubble.setAttribute('data-user-message-bubble', '');
  redrawnOldBubble.appendChild(new FakeText('Mesterséges kérés')); oldUnit.replaceChildren(redrawnOldBubble);
  const { userUnit } = addRoleImageTurn(2, 'Az új képkérés fordítása.');
  userUnit.attributes.delete('data-message-id'); userUnit.setAttribute('data-turn-key', 'own-image-turn-2');
  refreshQueries();
  const current = harness.helpers.captureAssistantSnapshot();
  assert.equal(current.userCount, 2); assert.equal(current.userKeys[0], previous.lastUserKey);
  assert.notEqual(current.userNodeIds[0], previous.lastUserNodeId);
  assert.equal(current.lastUserStableId, ''); assert.equal(current.lastUserKey.startsWith('dom:'), true);
  assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), true);
});

test('Eltűnt régi stabil user horgony új DOM-key másolata nem bizonyít új képkérést', () => {
  const { harness, addRoleImageTurn, refreshQueries } = modernDomHarness();
  const { userUnit } = addRoleImageTurn(1, 'Korábbi fordítás');
  const previous = harness.helpers.captureAssistantSnapshot();
  const replacement = new FakeElement('div'); replacement.setAttribute('data-turn-key', 'redrawn-old-turn');
  const heading = replacement.appendChild(new FakeElement('h4')); heading.setAttribute('data-conversation-role', 'user');
  heading.setAttribute('class', 'sr-only');
  const image = replacement.appendChild(new FakeImage('img')); image.setAttribute('src', 'data:image/png;base64,aGVsbG8=');
  userUnit.parentElement.replaceChildren(replacement);
  const answer = harness.document.body.appendChild(new FakeElement('div'));
  answer.setAttribute('data-message-author-role', 'assistant'); answer.setAttribute('data-message-id', 'redrawn-old-answer');
  answer.appendChild(new FakeText('Korábbi fordítás'));
  refreshQueries();
  const current = harness.helpers.captureAssistantSnapshot();
  assert.equal(current.userCount, 1); assert.equal(current.lastUserStableId, '');
  assert.equal(current.userKeys.includes(previous.lastUserKey), false);
  assert.equal(current.lastUserKey.startsWith('dom:'), true);
  assert.equal(harness.helpers.isFreshAssistantSnapshot(current, previous), false);
});

test('Kép vagy névrészlet explicit user szerep nélkül nem lehet felhasználói kör', () => {
  const { harness, refreshQueries } = modernDomHarness();
  for (const label of ['', 'Young user avatar', 'User settings']) {
    const wrapper = harness.document.body.appendChild(new FakeElement('article'));
    if (label) wrapper.setAttribute('aria-label', label);
    const image = wrapper.appendChild(new FakeImage('img'));
    image.setAttribute('src', 'data:image/png;base64,aGVsbG8=');
  }
  refreshQueries();
  assert.equal(harness.helpers.findUserMessageNodes().length, 0);
});

test('Rejtett szerepjel vagy kép és vegyes szerepű wrapper nem igazolhat kép-only user kört', () => {
  for (const invalidKind of ['hidden-heading', 'hidden-image', 'hidden-wrapper', 'mixed-heading', 'mixed-bubble']) {
    const { harness, addRoleImageTurn, refreshQueries } = modernDomHarness();
    const { userUnit, userHeading, image } = addRoleImageTurn(1, 'A különálló asszisztensválasz.');
    if (invalidKind === 'hidden-heading') userHeading.setAttribute('hidden', '');
    else if (invalidKind === 'hidden-image') image.setAttribute('hidden', '');
    else if (invalidKind === 'hidden-wrapper') userUnit.setAttribute('hidden', '');
    else {
      const opposite = userUnit.appendChild(new FakeElement('h4'));
      opposite.setAttribute('data-conversation-role', 'assistant');
      if (invalidKind === 'mixed-bubble') userUnit.setAttribute('data-user-message-bubble', '');
    }
    refreshQueries();
    assert.equal(harness.helpers.findUserMessageNodes().length, 0, invalidKind);
  }
});


test('Composer Stop vezérlő mellett a pending attribútum nélküli új DOM sem kész válasz', () => {
  const harness = createHarness();
  const stop = new FakeButton(); stop.setAttribute('aria-label', 'Stop generating');
  harness.document.body.querySelectorAll = (selector) => selector === 'button' ? [stop] : [];
  assert.equal(harness.helpers.hasActiveGenerationControl(), true);
  assert.equal(harness.helpers.isStableAssistantSnapshot({ lastText: 'Részleges', lastPending: false, generationPending: true }), false);
  stop.setAttribute('aria-label', 'Send message');
  assert.equal(harness.helpers.hasActiveGenerationControl(), false);
  assert.equal(harness.helpers.isStableAssistantSnapshot({ lastText: 'Végleges', lastPending: false, generationPending: false }), true);
});

test('Több markdown válaszrész hiánytalanul, duplikáció nélkül kerül a cache szövegébe', () => {
  const harness = createHarness();
  const body = new FakeElement('div');
  const first = body.appendChild(new FakeElement('div')); first.appendChild(new FakeText('Első bekezdés.'));
  const second = body.appendChild(new FakeElement('div')); second.appendChild(new FakeText('Második bekezdés.'));
  body.querySelectorAll = () => [first, second]; body.querySelector = () => first;
  assert.equal(harness.helpers.extractMessageText(body), 'Első bekezdés.\n\nMásodik bekezdés.');
});

test('Rejtett régi üzenetmásolat és válaszrész nem előzheti meg a látható teljes fordítást', () => {
  for (const hiddenKind of ['hidden', 'aria-hidden', 'parent-display']) {
    const { harness, addTurn } = modernDomHarness();
    const { assistantBody } = addTurn(1, 'A látható teljes fordítás.');
    harness.window.getComputedStyle = (element) => ({ display: element.style.display || 'block', visibility: element.style.visibility || 'visible' });
    const parent = harness.document.body.appendChild(new FakeElement('div'));
    const duplicate = parent.appendChild(new FakeElement('article'));
    duplicate.setAttribute('data-message-author-role', 'assistant');
    duplicate.setAttribute('data-message-id', `hidden-${hiddenKind}`);
    duplicate.appendChild(new FakeText('Rejtett részlet'));
    if (hiddenKind === 'parent-display') parent.style.display = 'none';
    else parent.setAttribute(hiddenKind, hiddenKind === 'hidden' ? '' : 'true');
    const hiddenPart = assistantBody.appendChild(new FakeElement('div'));
    hiddenPart.setAttribute('hidden', ''); hiddenPart.appendChild(new FakeText('Rejtett részlet'));
    assert.equal(harness.helpers.findAssistantMessageNodes().length, 1, hiddenKind);
    assert.equal(harness.helpers.captureAssistantSnapshot().lastText, 'A látható teljes fordítás.', hiddenKind);
  }
});

test('Prompt előkészítése közben betöltött előzmény után az új submit saját válasza érkezik', async () => {
  const empty = { count: 0, lastText: '', lastUserKey: '', userKeys: [], userNodeIds: [], assistantNodeIds: [], assistantStableIds: [] };
  const history = { count: 1, lastText: 'Korábbi válasz', lastUserKey: 'message:old-user', lastUserStableId: 'message:old-user',
    userKeys: ['message:old-user'], userNodeIds: ['old-user-node'], assistantStableIds: ['message:old-answer'] };
  const answer = { count: 2, lastText: 'Az új kérés kész fordítása.', lastStableId: 'message:new-answer', lastNodeId: 'new-answer-node',
    lastUserKey: 'message:new-user', lastUserStableId: 'message:new-user', responseUserKey: 'message:new-user',
    userKeys: ['message:old-user', 'message:new-user'], userNodeIds: ['old-user-node', 'new-user-node'], lastPending: false };
  let current = empty;
  const harness = createHarness({ overrides: { captureAssistantSnapshot: () => current } });
  const form = harness.document.body.appendChild(new FakeForm());
  form.appendChild(harness.composer); form.appendChild(harness.sendButton);
  form.querySelectorAll = (selector) => selector === 'button' ? [harness.sendButton] : [];
  harness.composer.addEventListener('input', () => { current = history; });
  let submitted = 0;
  form.requestSubmit = () => { submitted += 1; current = answer; harness.composer.value = ''; };
  const result = await harness.window.__gamerTranslatorDeliver({ prompt: 'Új kérés', autoSubmit: true, waitForResponse: true, responseTimeoutMs: 40 });
  assert.equal(result.ok, true); assert.equal(result.assistantResponseText, answer.lastText);
  assert.equal(result.assistantResponseComplete, true); assert.equal(submitted, 1);
});

test('Retry nem veheti fel baseline-nak az első kísérlet már elküldött userét', async () => {
  const empty = { count: 0, lastText: '', lastUserKey: '', userKeys: [], userNodeIds: [], assistantNodeIds: [], assistantStableIds: [] };
  const history = { count: 1, lastText: 'Korábbi válasz', lastUserKey: 'message:old-user', lastUserStableId: 'message:old-user',
    userKeys: ['message:old-user'], userNodeIds: ['old-user-node'], assistantStableIds: ['message:old-answer'] };
  const answer = { count: 2, lastText: 'Az első beküldés kész fordítása.', lastStableId: 'message:new-answer', lastNodeId: 'new-answer-node',
    lastUserKey: 'message:new-user', lastUserStableId: 'message:new-user', responseUserKey: 'message:new-user',
    userKeys: ['message:old-user', 'message:new-user'], userNodeIds: ['old-user-node', 'new-user-node'], lastPending: false };
  let current = empty;
  let harness;
  harness = createHarness({ overrides: {
    captureAssistantSnapshot: () => current,
    submitTextMessage: async () => {
      harness.helpers.captureResponseBaselineBeforeSubmit();
      current = answer;
      // Egy későbbi küldési fallback a már látható új user után fut.
      harness.helpers.captureResponseBaselineBeforeSubmit();
    },
  } });
  harness.composer.addEventListener('input', () => { current = history; });
  const pending = harness.window.__gamerTranslatorDeliver({ prompt: 'Új kérés', autoSubmit: true, waitForResponse: true, responseTimeoutMs: 40 });
  await harness.advance(40);
  const result = await pending;
  assert.equal(result.ok, true); assert.equal(result.assistantResponseText, answer.lastText);
});
