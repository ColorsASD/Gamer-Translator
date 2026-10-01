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
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  hasAttribute(name) { return this.attributes.has(name); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  matches() { return false; }
  closest(selector) {
    if (selector === 'button' && this instanceof FakeButton) return this;
    if (selector === 'form' && this instanceof FakeForm) return this;
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
  const second = await harness.window.__gamerTranslatorDeliver({ prompt: 'Második', autoSubmit: false });
  assert.equal(second.ok, false);
  assert.match(second.error, /folyamatban/);
  assert.equal(harness.composer.value, 'Első');
  release();
  assert.equal((await first).ok, true);
  assert.equal((await harness.window.__gamerTranslatorDeliver({ prompt: 'Harmadik', autoSubmit: false })).ok, true);
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
  assert.deepEqual(Object.keys(entries[0].fields).sort(), ['pending', 'stage', 'text_length']);
  const serialized = JSON.stringify(entries);
  assert.equal(serialized.includes('titkos'), false); assert.equal(serialized.includes('data:image'), false); assert.equal(serialized.includes('https://'), false);
  for (let index = 0; index < 30; index += 1) harness.helpers.writeDiagnosticEntry(`call-${index}`, 'composer_ready');
  assert.equal(Object.keys(harness.window.__gamerTranslatorDiagnostics).length, 16);
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
