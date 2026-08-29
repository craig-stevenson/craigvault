"""Issue #1 — a locked session must hold no key, and no field may keep a password.

doLock used to leave `password` in a live binding, so `doUnlock(password)` typed into
the console recovered the whole document without anyone knowing the password. The
password inputs were also cleared when their dialog opened rather than when it closed,
leaving plaintext in the DOM until the next open.
"""

import json
import os
import tempfile

from harness import Page

PW = "correct-horse-battery"
TEXT = "TOP-SECRET-CANARY-9271"


def _write_vault(tmp):
    with Page() as p:
        html = p.eval("(async()=>buildVaultHtml(await encryptText(%s,%s)))()"
                      % (json.dumps(TEXT), json.dumps(PW)))
    path = os.path.join(tmp, "notes.html")
    with open(path, "w") as fh:
        fh.write(html)
    return path


def run(r):
    tmp = tempfile.mkdtemp(prefix="craigvault-vault-")
    vault = _write_vault(tmp)

    with Page(vault) as p:
        r.check("a vault with a payload boots locked, with no key in memory",
                p.eval("locked && password === null && editor.value === '' "
                       "&& document.getElementById('lockscreen').classList.contains('show')", False))

        # wrong password must not adopt anything
        p.eval("document.getElementById('unlockPw').value = 'WRONG-PASSWORD';"
               "document.getElementById('unlockForm').dispatchEvent("
               "  new Event('submit',{cancelable:true}))", False)
        p.wait("!busy")
        r.check("a wrong password leaves the session locked and keyless",
                p.eval("locked && password === null", False))
        r.equal("the wrong-password message is shown",
                p.eval("document.getElementById('unlockErr').textContent", False),
                "Incorrect password.")

        # correct password unlocks and adopts the key
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent("
               "  new Event('submit',{cancelable:true}))" % json.dumps(PW), False)
        p.wait("!busy && !locked")
        r.equal("the correct password returns the exact plaintext",
                p.eval("editor.value", False), TEXT)
        r.check("the key is adopted on a successful unlock", p.eval("password === %s" % json.dumps(PW), False))
        r.equal("#unlockPw is cleared after a SUCCESSFUL unlock",
                p.eval("document.getElementById('unlockPw').value", False), "")

        # lock again: the key must go
        p.click("#btnLock")
        p.wait("locked && !busy")
        r.check("locking wipes the editor", p.eval("editor.value === ''", False))
        r.check("locking drops the key", p.eval("password === null", False))
        r.check("locking keeps the session as ciphertext", p.eval("!!lockedBlob", False))
        r.equal("#unlockPw is empty while locked",
                p.eval("document.getElementById('unlockPw').value", False), "")

        # the reported bypass
        p.eval("(async()=>{ await doUnlock(password); })()")
        r.check("doUnlock(password) no longer recovers anything",
                p.eval("locked && editor.value === ''", False))

        # unsaved edits survive a lock/unlock round trip
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent("
               "  new Event('submit',{cancelable:true}))" % json.dumps(PW), False)
        p.wait("!busy && !locked")
        p.eval("editor.value = %s; editor.dispatchEvent(new Event('input'))"
               % json.dumps(TEXT + " plus UNSAVED-EDIT"), False)
        p.click("#btnLock")
        p.wait("locked && !busy")
        p.eval("document.getElementById('unlockPw').value = %s;"
               "document.getElementById('unlockForm').dispatchEvent("
               "  new Event('submit',{cancelable:true}))" % json.dumps(PW), False)
        p.wait("!busy && !locked")
        r.equal("unsaved edits survive lock and unlock",
                p.eval("editor.value", False), TEXT + " plus UNSAVED-EDIT")

    # --- password fields must be wiped on every exit path --------------------
    with Page() as p:
        fields = p.eval("""(async()=>{
          const out = {};
          let pr = askNewPassword('SET PASSWORD');
          document.getElementById('pw1').value = %s;
          document.getElementById('pw2').value = %s;
          document.getElementById('pwForm').dispatchEvent(new Event('submit',{cancelable:true}));
          out.resolved = await pr;
          out.pw1 = document.getElementById('pw1').value;
          out.pw2 = document.getElementById('pw2').value;

          pr = askOpenPassword('notes.html');
          document.getElementById('openPw').value = %s;
          document.getElementById('openForm').dispatchEvent(new Event('submit',{cancelable:true}));
          out.openResolved = await pr;
          out.openPw = document.getElementById('openPw').value;

          pr = askNewPassword('SET PASSWORD');                    // cancel path
          document.getElementById('pw1').value = 'another-secret-value';
          document.getElementById('pwCancel').click(); await pr;
          out.pw1AfterCancel = document.getElementById('pw1').value;

          out.inPristine = PRISTINE.includes(%s);
          return out;})()""" % ((json.dumps(PW),) * 3 + (json.dumps(PW),)))

        r.equal("askNewPassword still resolves the typed password", fields["resolved"], PW)
        r.equal("#pw1 is wiped once the dialog closes", fields["pw1"], "")
        r.equal("#pw2 is wiped once the dialog closes", fields["pw2"], "")
        r.equal("askOpenPassword still resolves", fields["openResolved"], PW)
        r.equal("#openPw is wiped once the dialog closes", fields["openPw"], "")
        r.equal("#pw1 is wiped on the CANCEL path too", fields["pw1AfterCancel"], "")
        r.check("no password reaches the saved shell", not fields["inPristine"])
