"""Share — the app and this document in one HTML file, for someone without CraigVault.

Share is not Save. It writes a different file under its own password, never adopts the
save target, never clears dirty, and never marks the document unverified: the .txt is the
copy of record and a shared copy is a snapshot of it. It respects lock and busy exactly as
the other entry points do, and it has no keyboard shortcut on purpose.
"""

import json
import os
import tempfile

from harness import Page, STUB_HANDLE

DOC_PW, SHARE_PW = "the-documents-own-passphrase", "a-different-one-for-the-recipient"
TEXT = "TOP-SECRET-CANARY-9271 to be shared"


def _doc(p):
    """A saved .txt document, open and clean, with a live save handle."""
    p.eval(STUB_HANDLE, await_promise=False)
    p.eval("""(()=>{
      window.__txt = window.__mkHandle('notes.txt');
      window.__out = null;
      window.showSaveFilePicker = async o => { window.__savePrompts++; window.__suggested = o && o.suggestedName;
        window.__out = window.__mkHandle('picked.html'); return window.__out; };
      password = %s; fileName = 'notes.txt'; fileHandle = window.__txt;
      editor.value = %s; editor.dispatchEvent(new Event('input')); setDirty(false); return 1; })()"""
           % (json.dumps(DOC_PW), json.dumps(TEXT)), False)


def _share(p, pw):
    p.eval("window.__sh = doShare();", False)
    p.wait("document.getElementById('pwDialog').open")
    p.eval("document.getElementById('pw1').value = %s; document.getElementById('pw2').value = %s;"
           % (json.dumps(pw), json.dumps(pw)), False)
    p.click("#pwOk")
    p.eval("(async()=>{ await window.__sh; })()")
    p.wait("!busy")


def run(r):
    # --- the toolbar ------------------------------------------------------------
    with Page() as p:
        groups = p.eval("[...document.querySelectorAll('.actions [role=group]')]"
                        ".map(g => g.getAttribute('aria-label'))", False)
        r.equal("the toolbar is three labelled clusters", groups, ["Document", "Share", "Session"])
        r.check("Share sits in its own cluster, not beside Save",
                p.eval("document.getElementById('btnShare').closest('[role=group]') !== "
                       "document.getElementById('btnSave').closest('[role=group]')", False))
        r.check("the label carries the ellipsis that says 'this opens a dialog'",
                p.eval("document.getElementById('btnShare').textContent.endsWith('…')", False))
        r.check("Share is secondary weight; Save stays primary",
                p.eval("!document.getElementById('btnShare').classList.contains('primary') && "
                       "document.getElementById('btnSave').classList.contains('primary')", False))
        r.check("Share advertises no keyboard shortcut",
                "Ctrl" not in p.eval("document.getElementById('btnShare').title", False))
        r.check("New and Open keep their own titles when unlocked (render used to blank them)",
                p.eval("document.getElementById('btnNew').title === 'Start a new document' && "
                       "document.getElementById('btnOpen').title.startsWith('Open')", False))

    # --- the dialog -------------------------------------------------------------
    with Page() as p:
        _doc(p)
        p.eval("window.__sh = doShare();", False)
        p.wait("document.getElementById('pwDialog').open")
        r.equal("Share opens its own dialog", p.eval("document.getElementById('pwTitle').textContent", False), "SHARE A COPY")
        r.equal("the field is labelled for the recipient",
                p.eval("document.getElementById('pw1Label').textContent", False), "Password for the recipient")
        r.equal("and the button says what it does",
                p.eval("document.getElementById('pwOk').textContent", False), "Create file")
        r.check("the hint tells you to send the password separately, where the decision is made",
                "separately" in p.eval("document.getElementById('pwHint').textContent", False))
        r.check("the field is empty — the document's password is never pre-filled",
                p.eval("document.getElementById('pw1').value === ''", False))
        # cancel changes nothing
        p.click("#pwCancel")
        p.eval("(async()=>{ await window.__sh; })()")
        r.check("cancelling writes nothing", p.eval("window.__out === null", False))
        r.check("and changes nothing", p.eval("fileHandle === window.__txt && fileName === 'notes.txt' && !dirty", False))

        # the next ordinary password prompt must not be wearing Share's clothes
        p.eval("window.__np = askNewPassword('SET PASSWORD');", False)
        p.wait("document.getElementById('pwDialog').open")
        r.check("the dialog defaults are restored afterwards",
                p.eval("document.getElementById('pwTitle').textContent === 'SET PASSWORD' && "
                       "document.getElementById('pw1Label').textContent === 'Password' && "
                       "document.getElementById('pwOk').textContent === 'Encrypt & continue' && "
                       "!document.getElementById('pwHint').textContent.includes('separately')", False))
        p.click("#pwCancel")
        p.eval("(async()=>{ await window.__np; })()")

    # --- a share, and what it must not touch ----------------------------------------
    with Page() as p:
        _doc(p)
        p.eval("editor.value += ' plus an unsaved edit'; editor.dispatchEvent(new Event('input'));", False)
        _share(p, SHARE_PW)
        r.equal("Share prompts for a location", p.eval("window.__savePrompts", False), 1)
        r.equal("suggesting the document's name as .html", p.eval("window.__suggested", False), "notes.html")
        r.check("and writes a self-contained HTML bundle",
                p.eval("!!window.__out.written && window.__out.written.startsWith('<!doctype html>')", False))
        r.check("the .txt was not written to", p.eval("window.__txt.written === null", False))
        r.check("the save target is unchanged", p.eval("fileHandle === window.__txt", False))
        r.equal("the header still names the .txt", p.eval("fileName", False), "notes.txt")
        r.check("dirty is untouched — sharing is not saving", p.eval("dirty", False))
        r.check("and the confirmation says the document still has unsaved edits",
                "unsaved" in p.eval("document.getElementById('toast').textContent", False))
        r.check("the confirmation reminds you to send the password separately",
                "separately" in p.eval("document.getElementById('toast').textContent", False))
        r.check("unverified is not set by a share", not p.eval("unverified", False))
        r.check("the editor was read-only while the share encrypted, and is writable again",
                not p.eval("editor.readOnly", False))
        bundle = p.eval("window.__out.written", False)

    # --- the bundle stands on its own, under the share password only ------------------
    tmp = tempfile.mkdtemp(prefix="craigvault-share-")
    path = os.path.join(tmp, "notes.html")
    with open(path, "w") as fh:
        fh.write(bundle)
    with Page(path) as p:
        r.check("the shared file boots locked with no key in memory",
                p.eval("locked && password === null && !!lockedBlob", False))
        card = p.eval("document.querySelector('.lockcard').textContent", False)
        r.check("the card tells a recipient where the password comes from",
                "ask them for the password" in card)
        r.check("and answers 'is it safe to open this?'", "Nothing is sent anywhere" in card)
        r.check("without dropping the note that the wall is not real ciphertext",
                "illustrative" in card)
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent(new Event('submit',{cancelable:true}))"
               % json.dumps(DOC_PW), False)
        p.wait("!busy")
        r.check("the DOCUMENT's password does not open it", p.eval("locked", False))
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent(new Event('submit',{cancelable:true}))"
               % json.dumps(SHARE_PW), False)
        p.wait("!busy && !locked")
        r.equal("the SHARE password does, and returns the snapshot including the unsaved edit",
                p.eval("editor.value", False), TEXT + " plus an unsaved edit")
        r.equal("a bundle is never adopted as a save target", p.eval("fileHandle", False), None)

    # --- clean document: no 'unsaved' warning ------------------------------------------
    with Page() as p:
        _doc(p)
        _share(p, SHARE_PW)
        r.check("a clean document's confirmation does not mention unsaved edits",
                "unsaved" not in p.eval("document.getElementById('toast').textContent", False))
        r.check("and dirty stays clear", not p.eval("dirty", False))

    # --- lock and busy ---------------------------------------------------------------
    with Page() as p:
        _doc(p)
        p.eval("(async()=>{ await doLock(); })()")
        p.wait("locked && !busy")
        r.check("Share is disabled while locked", p.eval("document.getElementById('btnShare').disabled", False))
        r.equal("with a title saying why", p.eval("document.getElementById('btnShare').title", False),
                "Unlock this document first")
        p.eval("(async()=>{ await doShare(); })()")
        r.check("and doShare is refused outright", p.eval("window.__out === null && locked", False))

    # --- the download fallback never marks the document unverified --------------------
    with Page() as p:
        _doc(p)
        p.eval("fsBlocked = true; window.__dl = null;"
               "HTMLAnchorElement.prototype.click = function(){ window.__dl = this.download; };", False)
        _share(p, SHARE_PW)
        r.equal("on the fallback path Share downloads the .html", p.eval("window.__dl", False), "notes.html")
        r.check("and still does not set unverified — it is not the copy of record", not p.eval("unverified", False))
        r.check("nor touch dirty", not p.eval("dirty", False))
