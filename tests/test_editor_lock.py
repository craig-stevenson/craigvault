"""Issue #3 — the editor must be inert while a save or lock is encrypting.

Both doSave and doLock read editor.value, await a ~300ms scrypt derivation, then act
on conclusions that were only true when they started. roMix yields to the UI on purpose
so the tab keeps responding, which is exactly what let keystrokes land in the discard
window: the file got the old snapshot, dirty was cleared anyway, and beforeunload gates
on dirty — so the tab would close silently on text that existed nowhere else.

render() now makes the editor read-only for the duration, so the content cannot move.
The keystrokes below are genuine browser input events, not value assignment.
"""

import json

from harness import Page, stub_save_picker

PW = "editor-lock-passphrase"


def _ready(p):
    stub_save_picker(p, "v.html")
    p.eval("password = %s; fileName = 'v.html'; fileHandle = window.__saveTarget;"
           % json.dumps(PW), False)


def run(r):
    with Page() as p:
        _ready(p)
        p.click("#editor")
        p.type("OLD SNAPSHOT")
        r.check("the editor is writable when idle", not p.eval("editor.readOnly", False))

        # --- save, raced by real keystrokes ---------------------------------
        p.eval("window.__p = doSave(false);", False)
        r.check("a save marks the session busy", p.eval("busy", False))
        r.check("and makes the editor read-only", p.eval("editor.readOnly", False))
        p.type(" TYPED MIDSAVE")
        p.press("X", "KeyX", 88)             # a real key press, not synthesised text
        r.equal("keystrokes during the derivation are refused",
                p.eval("editor.value", False), "OLD SNAPSHOT")
        p.eval("(async()=>{ await window.__p; })()")
        r.check("the editor is writable again afterwards", not p.eval("editor.readOnly", False))
        r.equal("what reached the file matches what is on screen",
                p.eval("(async()=>await decryptBytes("
                       "extractPayload(window.__saveTarget.written).bytes,%s))()" % json.dumps(PW)),
                p.eval("editor.value", False))
        r.check("dirty is cleared, and truthfully", not p.eval("dirty", False))

        # --- lock, raced the same way ---------------------------------------
        p.eval("window.__saveTarget.written = null;", False)
        p.click("#editor")
        p.type(" AND MORE")
        before = p.eval("editor.value", False)
        p.eval("window.__l = doLock();", False)
        r.check("a lock also makes the editor read-only", p.eval("editor.readOnly", False))
        p.type(" TYPED MIDLOCK")
        r.equal("keystrokes during a lock are refused too",
                p.eval("editor.value", False), before)
        p.eval("(async()=>{ await window.__l; })()")
        p.wait("locked && !busy")
        r.check("the lock completes and wipes the editor", p.eval("editor.value === ''", False))
        r.equal("and holds the whole document as ciphertext",
                p.eval("(async()=>await decryptBytes(lockedBlob,%s))()" % json.dumps(PW)), before)
        # readOnly stays on while locked — that is issue #8's guard, not a leftover from the save.
        # What must not happen is `busy` being stuck, which would freeze the editor permanently.
        r.check("the editor stays read-only while locked, with busy correctly cleared",
                p.eval("editor.readOnly && locked && !busy", False))

        # --- typing works again once unlocked --------------------------------
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent("
               "  new Event('submit',{cancelable:true}))" % json.dumps(PW), False)
        p.wait("!busy && !locked")
        p.click("#editor")
        p.type(" TYPED AFTER UNLOCK")
        r.check("typing resumes after an unlock",
                p.eval("editor.value", False).endswith(" TYPED AFTER UNLOCK"))
        r.check("and marks the document dirty", p.eval("dirty", False))

        # --- the quiet path is unchanged -------------------------------------
        p.eval("window.__saveTarget.written = null; window.__savePrompts = 0;", False)
        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        r.check("an unraced save still reports success",
                "saved" in p.eval("document.getElementById('toast').textContent", False).lower())
        r.check("an unraced save still clears dirty", not p.eval("dirty", False))
        r.equal("and writes exactly what is on screen",
                p.eval("(async()=>await decryptBytes("
                       "extractPayload(window.__saveTarget.written).bytes,%s))()" % json.dumps(PW)),
                p.eval("editor.value", False))
