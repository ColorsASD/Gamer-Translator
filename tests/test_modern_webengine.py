"""Az élő oldalon igazolt új DOM offline próbája valódi Chromium motorral."""
from __future__ import annotations

import json
import time
import unittest

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEngineScript

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
  document.body.dataset.submitStartedAt=String(performance.now());
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
    document.body.dataset.finished='true';
    document.body.dataset.stopFinishedAt=String(performance.now());},600);
});</script></body></html>"""


IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="

ROLE_ONLY_USER = """const userUnit=document.createElement('div');
  userUnit.dataset.messageId='u-'+count; userUnit.dataset.turnKey='user-'+count;
  const userHeadingWrapper=document.createElement('div');
  const userHeading=document.createElement('h5'); userHeading.dataset.conversationRole='user';
  userHeading.className='sr-only'; userHeading.textContent='You said:';
  userHeadingWrapper.append(userHeading); userUnit.append(userHeadingWrapper);
  const userContent=document.createElement('div');
  const userImage=document.createElement('img'); userImage.src='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
  userContent.append(userImage); userUnit.append(userContent); turn.append(userUnit);"""

RECOGNIZED_HISTORY = """const historyUser=document.createElement('div');
  historyUser.dataset.chatgptSearchUnitKey='history-user'; historyUser.dataset.chatgptSearchMessageIds='history-u';
  const historyUserHeading=document.createElement('h4'); historyUserHeading.dataset.conversationRole='user';
  historyUserHeading.className='sr-only'; historyUserHeading.textContent='You said:';
  const historyUserBody=document.createElement('div'); historyUserBody.textContent='Mesterséges előző kérés';
  historyUser.append(historyUserHeading,historyUserBody);
  const historyAssistant=document.createElement('div');
  historyAssistant.dataset.chatgptSearchUnitKey='history-assistant'; historyAssistant.dataset.chatgptSearchMessageIds='history-a';
  const historyAssistantHeading=document.createElement('h4'); historyAssistantHeading.dataset.conversationRole='assistant';
  historyAssistantHeading.className='sr-only'; historyAssistantHeading.textContent='ChatGPT said:';
  const historyAnswer=document.createElement('div'); historyAnswer.dataset.chatgptSelectionMessageId='history-a';
  const historyMarkdown=document.createElement('div'); historyMarkdown.dataset.markdownTextStyle='';
  historyMarkdown.textContent='Korábbi kész válasz.'; historyAnswer.append(historyMarkdown);
  historyAssistant.append(historyAssistantHeading,historyAnswer);
  document.querySelector('main').append(historyUser,historyAssistant);"""


def role_only_image_fixture(*, history=True):
    """A képkérés nem kap szöveges buborékot vagy régi szerepattribútumot."""
    old_user = """const userUnit=document.createElement('div');
  userUnit.dataset.chatgptSearchUnitKey='user-'+count; userUnit.dataset.chatgptSearchMessageIds='u-'+count;
  const user=document.createElement('div'); user.dataset.userMessageBubble='';
  user.textContent=composer.innerText || ''; userUnit.append(user); turn.append(userUnit);"""
    source = FIXTURE.replace(old_user, ROLE_ONLY_USER)
    if history:
        source = source.replace("document.querySelector('form').addEventListener('submit',", RECOGNIZED_HISTORY + "document.querySelector('form').addEventListener('submit',")
    return source


class ModernWebEngineTests(unittest.TestCase):
    setUpClass = classmethod(baseline.WebEngineStagingTests.setUpClass.__func__)
    setUp = baseline.WebEngineStagingTests.setUp
    tearDown = baseline.WebEngineStagingTests.tearDown
    raw_javascript = baseline.WebEngineStagingTests.raw_javascript
    deliver = baseline.WebEngineStagingTests.deliver

    def expose_message_snapshots(self):
        # A kizárólag offline tesztpéldány olvashatja a belső állapotot.
        original = self.harness.automation_script
        self.harness.automation_script = original.replace(
            "const composerAutoRecovery = ensureComposerAutoRecoveryWatcher();",
            """window.__offlineResponseSnapshot = captureAssistantSnapshot;
            window.__offlineResponseDetails = () => {
              const snapshot=captureAssistantSnapshot(), baseline=assistantSnapshotBeforeSend;
              const fresh=isFreshAssistantSnapshot(snapshot,baseline);
              const bound=Boolean(baseline?.requestUserKey);
              const submitStartedAt=Number(document.body.dataset.submitStartedAt || 0);
              const stopFinishedAt=Number(document.body.dataset.stopFinishedAt || 0);
              return {
                assistant_count:snapshot.count, user_count:snapshot.userCount,
                text_length:String(snapshot.lastText || '').length,
                pending:snapshot.lastPending, generation_pending:snapshot.generationPending,
                stable:isStableAssistantSnapshot(snapshot), fresh,
                request_user_bound:bound,
                last_user_matches_request:bound && snapshot.lastUserKey===baseline.requestUserKey,
                response_user_matches_request:bound && snapshot.responseUserKey===baseline.requestUserKey,
                user_role_source:snapshot.lastUserRoleSource || 'none',
                fixture_finished:document.body.dataset.finished==='true',
                submit_elapsed_ms:submitStartedAt ? Math.round(performance.now()-submitStartedAt) : 0,
                stop_elapsed_ms:stopFinishedAt && submitStartedAt ? Math.round(stopFinishedAt-submitStartedAt) : 0
              };
            };
            const composerAutoRecovery = ensureComposerAutoRecoveryWatcher();""",
        )
        self.assertNotEqual(self.harness.automation_script, original)

    def message_snapshot(self):
        return json.loads(self.raw_javascript(
            "JSON.stringify(window.__offlineResponseSnapshot())",
            world=QWebEngineScript.ScriptWorldId.ApplicationWorld,
        ))

    def deliver_role_only_image(self, **values):
        # A Stop gomb 600 ms-os Chromium-időzítője offscreen módban késhet;
        # a pozitív próbák a meglévő harness 3000 ms-os keretét használják.
        payload = dict(prompt="", imageDataUrl=IMAGE, imageMimeType="image/png",
                       imageFilename="szintetikus.png", waitForResponse=True,
                       copyResponseToClipboard=False, responseTimeoutMs=3000)
        payload.update(values)
        try:
            result = self.deliver(**payload)
        except RuntimeError as error:
            details = self.response_details()
            self.last_response_details = details
            raise RuntimeError(f"{error} Offline állapot: {json.dumps(details, ensure_ascii=True, sort_keys=True)}") from error
        self.last_response_details = self.response_details()
        return result

    def response_details(self):
        return json.loads(self.raw_javascript(
            "JSON.stringify(window.__offlineResponseDetails())",
            world=QWebEngineScript.ScriptWorldId.ApplicationWorld,
        ))

    def wait_for_fixture_completion(self):
        deadline = time.monotonic() + 3.0
        while self.raw_javascript("document.body.dataset.finished") != "true":
            if time.monotonic() >= deadline:
                self.fail(f"Az offline Stop-időzítő nem zárult le: {json.dumps(self.response_details(), sort_keys=True)}")
            self.harness._wait_with_events(20)

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

    def test_role_heading_image_request_without_bubble_has_fresh_response(self):
        self.load_fixture(role_only_image_fixture())
        self.expose_message_snapshots()
        result = self.deliver_role_only_image()
        self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
        self.assertTrue(result["assistantResponseComplete"])
        self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "1")
        self.assertEqual(self.raw_javascript("document.querySelectorAll('[data-user-message-bubble],[data-message-author-role],article,[data-testid^=\"conversation-turn-\"]').length"), 0)
        snapshot = self.message_snapshot()
        self.assertEqual((snapshot["userCount"], snapshot["count"]), (2, 2))
        self.assertEqual(snapshot["lastUserKey"], snapshot["responseUserKey"])
        self.assertFalse(snapshot["lastPending"])
        self.assertFalse(snapshot["generationPending"])
        self.assertEqual(self.page.errors, [])
        self.assertEqual(self.blocker.blocked, [])

    def test_role_heading_image_requests_accept_identical_successive_answers(self):
        self.load_fixture(role_only_image_fixture())
        self.expose_message_snapshots()
        user_keys = []
        for expected_count in (2, 3):
            self.raw_javascript("document.body.dataset.finished='false'")
            result = self.deliver_role_only_image()
            self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
            self.assertTrue(result["assistantResponseComplete"])
            self.assertEqual(self.raw_javascript("document.body.dataset.finished"), "true")
            snapshot = self.message_snapshot()
            self.assertEqual((snapshot["userCount"], snapshot["count"]), (expected_count, expected_count))
            self.assertEqual(snapshot["lastUserKey"], snapshot["responseUserKey"])
            user_keys.append(snapshot["lastUserKey"])
        self.assertNotEqual(*user_keys)
        self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "2")
        self.assertEqual(self.page.errors, [])
        self.assertEqual(self.blocker.blocked, [])

    def test_role_heading_history_loaded_during_attachment_is_not_current_response(self):
        history_loader = """attachment.addEventListener('change',()=>{
          if(document.querySelector('[data-chatgpt-search-unit-key="history-user"]')) return;
          HISTORY
        });""".replace("HISTORY", RECOGNIZED_HISTORY)
        source = role_only_image_fixture(history=False).replace(
            "document.querySelector('form').addEventListener('submit',",
            history_loader + "document.querySelector('form').addEventListener('submit',",
        )
        self.load_fixture(source)
        self.expose_message_snapshots()
        result = self.deliver_role_only_image()
        self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
        self.assertTrue(result["assistantResponseComplete"])
        snapshot = self.message_snapshot()
        self.assertEqual((snapshot["userCount"], snapshot["count"]), (2, 2))
        self.assertEqual(snapshot["lastUserKey"], snapshot["responseUserKey"])
        self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "1")
        self.assertEqual(self.page.errors, [])
        self.assertEqual(self.blocker.blocked, [])

    def test_role_heading_hidden_users_and_mixed_outer_wrapper_do_not_change_binding(self):
        additions = """turn.dataset.messageId='mixed-outer-'+count;
          for(const hiddenKind of ['hidden','aria-hidden','parent-display']) {
            const hiddenWrapper=document.createElement('div'); hiddenWrapper.dataset.messageId=hiddenKind+'-user-'+count;
            const headingWrapper=document.createElement('div');
            const hiddenHeading=document.createElement('h4'); hiddenHeading.dataset.conversationRole='user';
            hiddenHeading.className='sr-only'; headingWrapper.append(hiddenHeading); hiddenWrapper.append(headingWrapper);
            const hiddenImage=document.createElement('img'); hiddenWrapper.append(hiddenImage);
            if(hiddenKind==='parent-display') hiddenWrapper.style.display='none';
            else hiddenWrapper.setAttribute(hiddenKind,hiddenKind==='hidden'?'':'true');
            document.querySelector('main').append(hiddenWrapper);
          }
        """
        source = role_only_image_fixture().replace(
            "composer.replaceChildren(); attachment.value='';",
            additions + "composer.replaceChildren(); attachment.value='';",
        )
        self.load_fixture(source)
        self.expose_message_snapshots()
        result = self.deliver_role_only_image()
        self.assertEqual(result["assistantResponseText"], "Azonos kész fordítás.")
        self.assertTrue(result["assistantResponseComplete"])
        snapshot = self.message_snapshot()
        self.assertEqual((snapshot["userCount"], snapshot["count"]), (2, 2))
        self.assertEqual(snapshot["lastUserKey"], snapshot["responseUserKey"])
        self.assertEqual(self.page.errors, [])
        self.assertEqual(self.blocker.blocked, [])

    def test_new_assistant_without_new_user_cannot_be_taken_as_current_image_response(self):
        source = role_only_image_fixture().replace(ROLE_ONLY_USER, "")
        self.load_fixture(source)
        self.expose_message_snapshots()
        with self.assertRaisesRegex(RuntimeError, "válasza nem érkezett meg időben"):
            self.deliver_role_only_image(responseTimeoutMs=1000)
        self.wait_for_fixture_completion()
        snapshot = self.message_snapshot()
        self.assertEqual((snapshot["userCount"], snapshot["count"]), (1, 2))
        self.assertEqual(snapshot["lastText"], "Azonos kész fordítás.")
        self.assertFalse(snapshot["lastPending"])
        self.assertFalse(snapshot["generationPending"])
        self.assertFalse(self.response_details()["fresh"])
        self.assertEqual(self.page.errors, [])
        self.assertEqual(self.blocker.blocked, [])

    def test_redrawn_old_assistant_after_new_role_heading_user_is_rejected(self):
        source = role_only_image_fixture().replace(
            "unit.append(heading,answer); turn.append(unit); document.querySelector('main').append(turn);",
            """unit.append(heading,answer); document.querySelector('main').append(turn);
              const previousAssistant=document.querySelector('[data-chatgpt-search-unit-key="history-assistant"]');
              turn.append(previousAssistant);""",
        )
        self.load_fixture(source)
        self.expose_message_snapshots()
        with self.assertRaisesRegex(RuntimeError, "válasza nem érkezett meg időben"):
            self.deliver_role_only_image(responseTimeoutMs=1000)
        self.wait_for_fixture_completion()
        snapshot = self.message_snapshot()
        self.assertEqual((snapshot["userCount"], snapshot["count"]), (2, 1))
        self.assertEqual(snapshot["lastText"], "Korábbi kész válasz.")
        self.assertFalse(snapshot["lastPending"])
        self.assertFalse(snapshot["generationPending"])
        self.assertFalse(self.response_details()["fresh"])
        self.assertEqual(self.page.errors, [])
        self.assertEqual(self.blocker.blocked, [])

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
