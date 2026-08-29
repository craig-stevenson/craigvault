"""Issue #6 — a download nobody can confirm is not a finished save.

On browsers without the File System Access API, saving is a synthetic <a download>
click. That is fire-and-forget: no API reports whether the download was blocked,
cancelled, redirected or written. doSave cleared `dirty` anyway and reported success,
and beforeunload gates on `dirty` — so the tab closed with no warning at all on a
document whose only copy may never have existed.

`unverified` now records that doubt: dirty still clears so the app stays usable, but
the close is guarded and the footer says so. An in-place write, or opening the file,
is proof and clears it.
"""

import json

from harness import Page, STUB_HANDLE

PW = "download-path-passphrase"
TEXT = "THE ONLY COPY"


def _fallback(p):
    """The genuine non-FS path, with a download that goes nowhere."""
    p.eval(STUB_HANDLE, await_promise=False)
    p.eval("fsBlocked = true; window.__downloaded = null;"
           "HTMLAnchorElement.prototype.click = function(){ window.__downloaded = this.download; };"
           "password = %s; editor.value = %s; editor.dispatchEvent(new Event('input'));"
           % (json.dumps(PW), json.dumps(TEXT)), False)


def _closes_silently(p):
    return not p.eval("(()=>{ const e = new Event('beforeunload',{cancelable:true});"
                      "  window.dispatchEvent(e); return e.defaultPrevented; })()", False)


def run(r):
    with Page() as p:
        _fallback(p)
        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")

        r.equal("the download was attempted", p.eval("window.__downloaded", False), "vault.html")
        r.check("dirty clears, so the app stays usable", not p.eval("dirty", False))
        r.check("but the save is recorded as unverified", p.eval("unverified", False))
        r.check("the message says delivery cannot be confirmed",
                "can't confirm" in p.eval("document.getElementById('toast').textContent", False))
        r.equal("and the footer says so too",
                p.eval("document.getElementById('stateTxt').textContent", False),
                "downloaded · unconfirmed")
        r.check("closing the tab is guarded rather than silent", not _closes_silently(p))

        # editing afterwards is the ordinary dirty case again
        p.click("#editor")
        p.type(" more")
        r.check("editing still marks the document dirty", p.eval("dirty", False))
        r.check("and the close stays guarded", not _closes_silently(p))

    # --- a completed in-place write is proof -----------------------------
    with Page() as p:
        _fallback(p)
        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        r.check("precondition: unverified after a download", p.eval("unverified", False))
        p.eval("fsBlocked = false;"
               "window.__target = window.__mkHandle('notes.html');"
               "window.showSaveFilePicker = async () => window.__target;"
               "fileHandle = null;", False)
        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        r.check("an in-place write clears the doubt", not p.eval("unverified", False))
        r.check("and the close is no longer guarded", _closes_silently(p))
        r.equal("the footer is back to normal",
                p.eval("document.getElementById('stateTxt').textContent", False), "unlocked")

    # --- so is opening the file --------------------------------------------
    with Page() as p:
        _fallback(p)
        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        p.eval("""(async()=>{
          const h = window.__mkHandle('notes.html',
            buildVaultHtml(await encryptText(%s, %s)));
          window.showOpenFilePicker = async () => [h];
          fsBlocked = false; window.__op = doOpen(); })()""" % (json.dumps(TEXT), json.dumps(PW)), False)
        p.wait("document.getElementById('openDialog').open")
        p.eval("document.getElementById('openPw').value = %s;"
               "document.getElementById('openForm').dispatchEvent(new Event('submit',{cancelable:true}))"
               % json.dumps(PW), False)
        p.eval("(async()=>{ await window.__op; })()")
        r.check("opening the file proves it exists", not p.eval("unverified", False))

    # --- and starting over ---------------------------------------------------
    with Page() as p:
        _fallback(p)
        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        r.check("doNew clears the doubt along with everything else", p.eval("""(async()=>{
          const orig = askConfirm; askConfirm = async () => true;
          await doNew(); askConfirm = orig;
          return !unverified; })()"""))
