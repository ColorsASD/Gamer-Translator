"""Az élő oldalon igazolt új DOM offline próbája valódi Chromium motorral."""
from __future__ import annotations

import unittest

from PySide6.QtCore import QEventLoop, QTimer, QUrl

import test_webengine as baseline


FIXTURE = """<!doctype html><html><head><meta charset="utf-8"><link rel="icon" href="data:,"></head>
<body><main id="conversation"></main><form data-chatgpt-composer>
<div contenteditable="true" role="textbox" data-composer-markdown></div>
<input type="file" accept="image/*"><button type="submit" aria-label="Send message">Send</button>
</form><script>
const composer=document.querySelector('[role="textbox"]'), send=document.querySelector('button');
const attachment=document.querySelector('input'); let count=0;
document.body.dataset.submitCount='0';
attachment.addEventListener('change',()=>{
  const preview=document.createElement('img'); preview.src=URL.createObjectURL(attachment.files[0]);
  document.querySelector('form').append(preview);
});
document.querySelector('form').addEventListener('submit',event=>{
  event.preventDefault(); count++; document.body.dataset.submitCount=String(count);
  document.body.dataset.submittedText=composer.innerText;
  document.body.dataset.fileCount=String(attachment.files.length);
  const turn=document.createElement('div'); turn.dataset.turnKey='turn-'+count;
  const userUnit=document.createElement('div');
  userUnit.dataset.chatgptSearchUnitKey='user-'+count; userUnit.dataset.chatgptSearchMessageIds='u-'+count;
  const user=document.createElement('div'); user.dataset.userMessageBubble='';
  user.textContent=composer.innerText || ''; userUnit.append(user); turn.append(userUnit);
  const unit=document.createElement('div'); unit.dataset.chatgptSearchUnitKey='assistant-'+count;
  unit.dataset.chatgptSearchMessageIds='a-'+count; unit.dataset.contentSearchUnitKey='assistant-'+count;
  const heading=document.createElement('h4'); heading.dataset.conversationRole='assistant';
  heading.className='sr-only'; heading.textContent='ChatGPT said:';
  const answer=document.createElement('div'); answer.dataset.chatgptSelectionMessageId='a-'+count;
  const markdown=document.createElement('div'); markdown.dataset.markdownTextStyle='';
  markdown.textContent='Folyamatban lévő részlet'; answer.append(markdown);
  unit.append(heading,answer); turn.append(unit); document.querySelector('main').append(turn);
  composer.replaceChildren(); attachment.value='';
  for(const image of document.querySelectorAll('form img')) image.remove();
  send.setAttribute('aria-label','Stop'); send.textContent='Stop';
  setTimeout(()=>{markdown.textContent='Azonos kész fordítás.';},80);
  setTimeout(()=>{send.setAttribute('aria-label','Send message'); send.textContent='Send';
    document.body.dataset.finished='true';},600);
});</script></body></html>"""


class ModernWebEngineTests(unittest.TestCase):
    setUpClass = classmethod(baseline.WebEngineStagingTests.setUpClass.__func__)
    setUp = baseline.WebEngineStagingTests.setUp
    tearDown = baseline.WebEngineStagingTests.tearDown
    raw_javascript = baseline.WebEngineStagingTests.raw_javascript
    deliver = baseline.WebEngineStagingTests.deliver

    def load_fixture(self, source=FIXTURE):
        loop = QEventLoop()
        loaded = []

        def finished(ok):
            loaded.append(ok)
            loop.quit()

        self.page.loadFinished.connect(finished)
        QTimer.singleShot(5000, loop.quit)
        self.page.setHtml(source, QUrl("https://chatgpt.com/"))
        loop.exec()
        self.page.loadFinished.disconnect(finished)
        self.assertEqual(loaded, [True])

    def test_new_dom_waits_for_stop_and_recognizes_identical_new_response(self):
        self.load_fixture()
        for prompt in ("Első szintetikus kérés", "Második szintetikus kérés"):
            self.raw_javascript("document.body.dataset.finished='false'")
            result = self.deliver(prompt=prompt, copyResponseToClipboard=False, waitForResponse=True)
            self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
            self.assertTrue(result["assistantResponseComplete"])
            self.assertEqual(self.raw_javascript("document.body.dataset.finished"), "true")
        self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "2")
        self.assertEqual(self.raw_javascript("document.querySelectorAll('[data-message-author-role],article').length"), 0)
        self.assertEqual(self.page.errors, [])

    def test_new_dom_image_only_request_has_user_identity_and_fresh_response(self):
        self.load_fixture()
        image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
        result = self.deliver(prompt="", imageDataUrl=image, imageMimeType="image/png",
                              imageFilename="szintetikus.png", waitForResponse=True,
                              copyResponseToClipboard=False)
        self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
        self.assertTrue(result["assistantResponseComplete"])
        self.assertEqual(self.raw_javascript("document.body.dataset.fileCount"), "1")
        self.assertEqual(self.page.errors, [])

    def test_hidden_legacy_message_cannot_replace_visible_completed_response(self):
        source = FIXTURE.replace(
            "composer.replaceChildren(); attachment.value='';",
            """for(const hiddenKind of ['hidden','aria-hidden','parent-display']) {
              const parent=document.createElement('div');
              const duplicate=document.createElement('article');
              duplicate.dataset.messageAuthorRole='assistant'; duplicate.dataset.messageId=hiddenKind+'-'+count;
              duplicate.textContent='Rejtett részlet'; parent.append(duplicate);
              if(hiddenKind==='parent-display') parent.style.display='none';
              else parent.setAttribute(hiddenKind,hiddenKind==='hidden'?'':'true');
              document.querySelector('main').append(parent);
            }
            const hiddenPart=document.createElement('div'); hiddenPart.dataset.markdownTextStyle='';
            hiddenPart.hidden=true; hiddenPart.textContent='Rejtett belső részlet'; answer.append(hiddenPart);
            composer.replaceChildren(); attachment.value='';""",
        )
        self.load_fixture(source)
        result = self.deliver(prompt="Rejtett másolat próbája", waitForResponse=True, copyResponseToClipboard=False)
        self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
        self.assertTrue(result["assistantResponseComplete"])
        self.assertEqual(self.page.errors, [])

    def test_history_loaded_during_preparation_is_not_bound_as_new_request(self):
        history_loader = """const loadHistory=()=>{
          if(document.querySelector('[data-chatgpt-search-unit-key="history-user"]')) return;
          const userUnit=document.createElement('div'); userUnit.dataset.chatgptSearchUnitKey='history-user';
          userUnit.dataset.chatgptSearchMessageIds='history-u';
          const user=document.createElement('div'); user.dataset.userMessageBubble='';
          user.textContent='Mesterséges előző kérés'; userUnit.append(user);
          const unit=document.createElement('div'); unit.dataset.chatgptSearchUnitKey='history-assistant';
          unit.dataset.chatgptSearchMessageIds='history-a';
          const heading=document.createElement('h4'); heading.dataset.conversationRole='assistant'; heading.className='sr-only';
          const answer=document.createElement('div'); answer.dataset.chatgptSelectionMessageId='history-a';
          const body=document.createElement('div'); body.dataset.markdownTextStyle='';
          body.textContent='Mesterséges előző válasz'; answer.append(body); unit.append(heading,answer);
          document.querySelector('main').append(userUnit,unit);
        };
        composer.addEventListener('input',loadHistory); attachment.addEventListener('change',loadHistory);
        """
        source = FIXTURE.replace("document.querySelector('form').addEventListener('submit',", history_loader + "document.querySelector('form').addEventListener('submit',")
        image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
        for kind, values in (
            ("text", {"prompt": "Új szintetikus kérés"}),
            ("image", {"imageDataUrl": image, "imageMimeType": "image/png", "imageFilename": "szintetikus.png"}),
            ("image_text", {"prompt": "Új szintetikus kérés", "imageDataUrl": image, "imageMimeType": "image/png", "imageFilename": "szintetikus.png"}),
        ):
            with self.subTest(kind=kind):
                self.load_fixture(source)
                result = self.deliver(**values, waitForResponse=True, copyResponseToClipboard=False)
                self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
                self.assertTrue(result["assistantResponseComplete"])
                self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "1")
                self.assertEqual(self.raw_javascript("document.querySelectorAll('[data-user-message-bubble]').length"), 2)
                self.assertEqual(self.page.errors, [])


if __name__ == "__main__":
    unittest.main()
