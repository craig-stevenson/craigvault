"""Issue #2 — fileHandle must only ever point at a document that was actually opened.

doOpen assigned fileHandle the moment a file was picked, before the payload check and
the password loop. Every early exit therefore left the handle aimed at a file that was
never opened, and an ordinary Save writes to fileHandle with no picker and no
confirmation. The same assignment also adopted legacy .sectxt files, so saving one
overwrote the original with HTML.
"""

import json

from harness import Page, STUB_HANDLE, read_fixture

PWA, PWB = "vault-a-passphrase", "vault-b-passphrase"
TEXT_A, TEXT_B = "AAA-vault-A-content", "BBB-vault-B-content"


def _setup(p):
    """Two real vaults, a junk file and an empty template, all behind a stubbed picker."""
    p.eval(STUB_HANDLE, await_promise=False)
    p.eval("""(async()=>{
      window.__a = window.__mkHandle('vault-A.html',
        buildVaultHtml(await encryptText(%s,%s)));
      window.__b = window.__mkHandle('vault-B.html',
        buildVaultHtml(await encryptText(%s,%s)));
      window.__junk  = window.__mkHandle('tax-return-2025.html','<html><body>not a vault</body></html>');
      window.__empty = window.__mkHandle('blank-template.html', PRISTINE);
      window.__pick = window.__a;
      window.showOpenFilePicker = async () => [window.__pick];
      window.showSaveFilePicker = async o => { window.__savePrompts++;
        window.__suggested = o && o.suggestedName; return window.__mkHandle('chosen.html'); };
      return 1;})()""" % (json.dumps(TEXT_A), json.dumps(PWA),
                          json.dumps(TEXT_B), json.dumps(PWB)))


def _open(p, handle, password):
    """Drive a full open through the real dialog."""
    p.eval("window.__pick = %s; window.__op = doOpen();" % handle, await_promise=False)
    p.wait("document.getElementById('openDialog').open")
    p.eval("document.getElementById('openPw').value = %s;"
           "document.getElementById('openForm').dispatchEvent(new Event('submit',{cancelable:true}))"
           % json.dumps(password), False)
    p.eval("(async()=>{ await window.__op; })()")


def _handle_name(p):
    return p.eval("fileHandle ? fileHandle.name : null", False)


def run(r):
    with Page() as p:
        _setup(p)
        _open(p, "window.__a", PWA)
        r.equal("a successful open adopts the file it opened", _handle_name(p), "vault-A.html")
        r.equal("and shows it in the header", p.eval("fileName", False), "vault-A.html")

        # --- every early exit must leave the handle alone --------------------
        p.eval("window.__pick = window.__b; window.__op = doOpen();", False)
        p.wait("document.getElementById('openDialog').open")
        p.click("#openCancel")
        p.eval("(async()=>{ await window.__op; })()")
        r.equal("cancelling the password prompt keeps the open document's handle",
                _handle_name(p), "vault-A.html")

        p.eval("window.__pick = window.__b; window.__op = doOpen();", False)
        p.wait("document.getElementById('openDialog').open")
        p.eval("document.getElementById('openPw').value='WRONG';"
               "document.getElementById('openForm').dispatchEvent(new Event('submit',{cancelable:true}))", False)
        p.wait("!busy")
        p.wait("document.getElementById('openDialog').open")
        p.click("#openCancel")
        p.eval("(async()=>{ await window.__op; })()")
        r.equal("a wrong password then cancel keeps the handle", _handle_name(p), "vault-A.html")

        p.eval("window.__pick = window.__junk;", False)
        p.eval("(async()=>{ await doOpen(); })()")
        r.equal("picking a file that is not a vault keeps the handle",
                _handle_name(p), "vault-A.html")
        r.check("and says so distinctly",
                "no encrypted payload" in p.eval("document.getElementById('toast').textContent", False))

        p.eval("window.__pick = window.__empty;", False)
        p.eval("(async()=>{ await doOpen(); })()")
        r.equal("picking an empty template keeps the handle", _handle_name(p), "vault-A.html")
        r.check("and reports it as empty rather than as a bad password",
                "empty" in p.eval("document.getElementById('toast').textContent", False))

        # --- the consequence the issue was really about ----------------------
        p.eval("editor.value = %s; editor.dispatchEvent(new Event('input'));"
               "window.__savePrompts = 0;" % json.dumps(TEXT_A + " edited"), False)
        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        wrote = p.eval("({a: !!window.__a.written, b: !!window.__b.written,"
                       " junk: !!window.__junk.written, prompts: window.__savePrompts})", False)
        r.check("Save writes to the document that is open", wrote["a"])
        r.check("Save does not touch the file that was merely browsed to",
                not wrote["b"] and not wrote["junk"])
        r.equal("an in-place save opens no picker", wrote["prompts"], 0)
        r.equal("what it wrote round-trips",
                p.eval("(async()=>await decryptBytes(extractPayload(window.__a.written).bytes,%s))()"
                       % json.dumps(PWA)), TEXT_A + " edited")

        # --- Save As must still prompt even with a live handle ---------------
        p.eval("window.__savePrompts = 0;", False)
        p.eval("(async()=>{ await doSave(true); })()")
        p.wait("!busy")
        r.equal("Save As opens a picker even when a handle exists",
                p.eval("window.__savePrompts", False), 1)

    # --- legacy .sectxt is imported, never written back to -------------------
    with Page() as p:
        fx = read_fixture()
        p.eval(STUB_HANDLE, await_promise=False)
        p.eval("""(()=>{
          window.__leg = window.__mkHandle('old-notes.sectxt',
            Uint8Array.from(atob(%s), c=>c.charCodeAt(0)));
          window.showOpenFilePicker = async () => [window.__leg];
          window.showSaveFilePicker = async o => { window.__savePrompts++;
            window.__suggested = o && o.suggestedName; return window.__mkHandle('chosen.html'); };
          return 1;})()""" % json.dumps(fx["payload_base64"]), False)
        _open(p, "window.__leg", fx["password"])
        r.check("a legacy .sectxt opens", p.eval("editor.value", False).startswith("Legacy SECTXT1"))
        r.equal("but is never adopted as a save target", _handle_name(p), None)
        r.equal("the header still names the file that is open",
                p.eval("fileName", False), "old-notes.sectxt")

        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        r.equal("saving it opens a picker", p.eval("window.__savePrompts", False), 1)
        r.equal("and suggests the same name as .html", p.eval("window.__suggested", False),
                "old-notes.html")
        r.check("the original .sectxt is left untouched",
                not p.eval("!!window.__leg.written", False))

    # --- the download fallback keeps the same discipline ---------------------
    with Page() as p:
        _setup(p)
        _open(p, "window.__a", PWA)
        p.eval("fsBlocked = true;"                       # force the non-FS path
               "window.__feed = null; window.__downloaded = null;"
               "HTMLInputElement.prototype.click = function(){"
               "  const dt = new DataTransfer(); if (window.__feed) dt.items.add(window.__feed);"
               "  Object.defineProperty(this,'files',{value:dt.files,configurable:true});"
               "  if (this.onchange) this.onchange(); };"
               "HTMLAnchorElement.prototype.click = function(){ window.__downloaded = this.download; };",
               False)
        p.eval("(async()=>{ window.__feed = new File([window.__b.reads],'vault-B.html',"
               "{type:'text/html'}); window.__op = doOpen(); })()", False)
        p.wait("document.getElementById('openDialog').open")
        p.click("#openCancel")
        p.eval("(async()=>{ await window.__op; })()")
        r.equal("a cancelled fallback open keeps the handle", _handle_name(p), "vault-A.html")

        p.eval("window.__op = doOpen();", False)
        p.wait("document.getElementById('openDialog').open")
        p.eval("document.getElementById('openPw').value = %s;"
               "document.getElementById('openForm').dispatchEvent(new Event('submit',{cancelable:true}))"
               % json.dumps(PWB), False)
        p.eval("(async()=>{ await window.__op; })()")
        r.equal("a successful fallback open clears the handle (there is none)", _handle_name(p), None)
        r.equal("and names the file it opened", p.eval("fileName", False), "vault-B.html")

        p.eval("(async()=>{ await doSave(false); })()")
        p.wait("!busy")
        r.equal("saving on the fallback path downloads under the right name",
                p.eval("window.__downloaded", False), "vault-B.html")
        r.check("and never writes through a handle", not p.eval("!!window.__a.written", False))

    # --- naming rule ---------------------------------------------------------
    with Page() as p:
        cases = {"untitled": "vault.html", "old-notes.sectxt": "old-notes.html",
                 "notes.html": "notes.html", "NOTES.HTML": "NOTES.HTML",
                 "my.notes.v2.sectxt": "my.notes.v2.html", "notes": "notes.html"}
        for given, want in cases.items():
            r.equal("htmlNameFor(%r)" % given,
                    p.eval("htmlNameFor(%s)" % json.dumps(given), False), want)
