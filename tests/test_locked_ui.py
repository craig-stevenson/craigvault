"""Issue #8 — a locked session must be inert, not just covered by an overlay.

The lockscreen is an absolutely-positioned div. Everything behind it stays live unless
something checks `locked`: doSave does, doLock does, nothing else did. #editor also
precedes #lockscreen in DOM order, so Tab reaches the textarea before the unlock field.

Unlocking must put all of it back, which is the other half of the contract.
"""

import json

from harness import Page, Results, STUB_HANDLE

PW = "locked-session-passphrase"
TEXT = "SECRET-CONTENT-8841"


def _lock(p):
    """Set a password, type, and lock — the state the issue describes."""
    p.eval(STUB_HANDLE, await_promise=False)
    p.eval("window.showOpenFilePicker = async () => { window.__openPrompts++;"
           "  return [window.__mkHandle('other.html','<html></html>')]; };"
           "window.__openPrompts = 0;", False)
    p.eval("password = %s; editor.value = %s; editor.dispatchEvent(new Event('input'));"
           % (json.dumps(PW), json.dumps(TEXT)), False)
    p.eval("(async()=>{ await doLock(); })()")
    p.wait("locked && !busy")


def run(r):
    # --- controls behind the overlay -------------------------------------
    with Page() as p:
        _lock(p)
        r.check("the auto-lock select is disabled while locked",
                p.eval("document.getElementById('autolock').disabled", False))
        r.check("New is disabled while locked",
                p.eval("document.getElementById('btnNew').disabled", False))
        r.check("Open is disabled while locked",
                p.eval("document.getElementById('btnOpen').disabled", False))
        r.check("the editor cannot be typed into while locked",
                p.eval("editor.disabled || editor.readOnly", False))

    # --- New must not discard an encrypted session without the password ---
    with Page() as p:
        _lock(p)
        before = p.eval("!!lockedBlob", False)
        p.eval("window.__confirmed = false;"
               "window.__origConfirm = askConfirm;"
               "askConfirm = async (...a) => { window.__confirmed = true; return true; };", False)
        p.eval("(async()=>{ await doNew(); })()")
        r.check("doNew is refused while locked (session still held as ciphertext)",
                before and p.eval("!!lockedBlob", False))
        r.check("and the session is still locked", p.eval("locked", False))
        r.check("it does not fall back to a generic discard prompt",
                not p.eval("window.__confirmed", False))

    # --- Open must not replace a locked session --------------------------
    with Page() as p:
        _lock(p)
        p.eval("(async()=>{ await doOpen(); })()")
        r.equal("doOpen is refused while locked (no picker shown)",
                p.eval("window.__openPrompts", False), 0)
        r.check("the locked session is intact", p.eval("locked && !!lockedBlob", False))

    # --- and via the keyboard --------------------------------------------
    with Page() as p:
        _lock(p)
        p.eval("document.dispatchEvent(new KeyboardEvent('keydown',"
               "{key:'o', ctrlKey:true, bubbles:true, cancelable:true}))", False)
        r.equal("Ctrl+O is refused while locked",
                p.eval("window.__openPrompts", False), 0)

    # --- focus must stay on the lockscreen -------------------------------
    with Page() as p:
        _lock(p)
        r.check("focus starts in the unlock field",
                p.eval("document.activeElement === document.getElementById('unlockPw')", False))
        reachable = p.eval("""(()=>{
          const wall = document.getElementById('lockscreen');
          return [...document.querySelectorAll(
            'a[href],button,input,select,textarea,[tabindex]')]
            .filter(el => !el.disabled && el.tabIndex !== -1)
            .filter(el => !wall.contains(el))
            // a closed <dialog> is display:none, so its fields are not actually reachable
            .filter(el => el.getClientRects().length > 0)
            .map(el => el.id || el.tagName);
        })()""", False)
        r.check("nothing outside the lockscreen is tab-reachable while locked",
                reachable == [], "reachable: %s" % reachable)

    # --- and unlocking must give all of it back --------------------------
    with Page() as p:
        _lock(p)
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent("
               "  new Event('submit',{cancelable:true}))" % json.dumps(PW), False)
        p.wait("!busy && !locked")
        r.equal("unlocking restores the plaintext", p.eval("editor.value", False), TEXT)
        r.check("New, Open and the auto-lock policy are usable again",
                p.eval("!document.getElementById('btnNew').disabled"
                       " && !document.getElementById('btnOpen').disabled"
                       " && !document.getElementById('autolock').disabled", False))
        r.check("the editor is writable and back in the tab order",
                p.eval("!editor.readOnly && editor.tabIndex !== -1", False))
        r.check("and focus returns to it", p.eval("document.activeElement === editor", False))
        p.type(" typed after unlock")
        r.check("typing works again",
                p.eval("editor.value", False).endswith(" typed after unlock"))
        r.check("doNew is allowed again once unlocked", p.eval("""(async()=>{
          window.__origConfirm = askConfirm; askConfirm = async () => true;
          await doNew();
          askConfirm = window.__origConfirm;
          return editor.value === '' && password === null && !locked; })()"""))


if __name__ == "__main__":
    import sys
    res = Results()
    run(res)
    for label, ok, detail in res.rows:
        print(("  \033[32m✓\033[0m " if ok else "  \033[31m✗\033[0m ") + label
              + (("  — " + detail) if detail and not ok else ""))
    print("\n%d of %d checks fail" % (len(res.failed), len(res.rows)))
    sys.exit(1 if res.failed else 0)
