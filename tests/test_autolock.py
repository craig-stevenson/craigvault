"""Issue #4 — auto-lock has to arm after the first save sets a password.

resetIdle used to be called from doOpen and doUnlock but never from doSave, so a
document created, given a password and saved never started its countdown. Fixed in
7034ae8, which restructured doSave's tail into try/finally and added the call.

resetIdle still no-ops while `password` is null. That is deliberate: there is no key
to re-encrypt with before the first save, and the footer says so rather than implying
a countdown is running. Whether an unsaved document should be lockable is issue #7.
"""

import json
import time

from harness import Page, stub_save_picker

PW = "auto-lock-passphrase"


def run(r):
    with Page() as p:
        stub_save_picker(p, "notes.html")

        r.equal("a fresh document has no timer", p.eval("String(idleTimer)", False), "null")
        r.equal("the auto-lock policy defaults to 5 minutes",
                p.eval("document.getElementById('autolock').value", False), "300")
        r.equal("and the footer says auto-lock is off, rather than implying a countdown",
                p.eval("document.getElementById('stateTxt').textContent", False),
                "no password · auto-lock off")

        p.click("#editor")
        p.type("secret content")
        r.equal("typing before a password exists still arms nothing",
                p.eval("String(idleTimer)", False), "null")

        # the issue's repro: Save, then set a password through the real dialog
        p.eval("window.__s = doSave(false);", False)
        p.wait("document.getElementById('pwDialog').open")
        p.eval("document.getElementById('pw1').value = %s;"
               "document.getElementById('pw2').value = %s;" % (json.dumps(PW), json.dumps(PW)), False)
        p.click("#pwOk")
        p.eval("(async()=>{ await window.__s; })()")
        p.wait("!busy")

        r.check("the save completed", p.eval("!!window.__saveTarget.written", False))
        r.check("a password is now set", p.eval("password !== null", False))
        r.check("auto-lock is armed straight after the first save",
                p.eval("idleTimer !== null", False))
        r.equal("and the footer reflects it",
                p.eval("document.getElementById('stateTxt').textContent", False), "unlocked")

        # shorten the pending timer rather than waiting five minutes
        p.eval("clearTimeout(idleTimer); idleTimer = setTimeout(doLock, 150);", False)
        p.wait("locked", timeout=20)
        r.check("the timer actually fires and locks", p.eval("locked", False))
        r.check("firing wipes the editor", p.eval("editor.value === ''", False))
        r.check("and drops the key", p.eval("password === null", False))

        # activity must reset, not stack up
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent("
               "  new Event('submit',{cancelable:true}))" % json.dumps(PW), False)
        p.wait("!busy && !locked")
        r.check("unlocking re-arms the countdown", p.eval("idleTimer !== null", False))
        first = p.eval("idleTimer", False)
        p.click("#editor")
        p.type("x")
        r.check("typing resets the timer rather than leaving the old one running",
                p.eval("idleTimer", False) != first)

        # Assert the behaviour, not the variable: resetIdle calls clearTimeout but leaves the old
        # numeric id in `idleTimer`, so the variable is not a reliable "is it armed" signal once a
        # timer has been cancelled. What matters is that a pending lock does not fire.
        p.eval("clearTimeout(idleTimer); idleTimer = setTimeout(doLock, 200);", False)
        p.eval("document.getElementById('autolock').value = '0';"
               "document.getElementById('autolock').dispatchEvent(new Event('change'));", False)
        time.sleep(0.8)
        r.check("switching auto-lock off cancels a pending lock", not p.eval("locked", False))
        r.check("and the session is still usable", not p.eval("editor.readOnly", False))
