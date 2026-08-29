"""Issue #5 — the strength meter must not mislead, and a short password warns once.

The old meter weighted composition 3 points to length's 2, which rated "P@ssw0rd"
Strong and a 25-character passphrase Weak — the opposite of the README's own advice
to use a long passphrase, and of what actually costs an offline attacker anything.

MIN_PW is advisory. Setting a password under it warns, explains why and relabels the
primary button; a second submit goes through. It is never applied on open or unlock,
or vaults whose passwords predate the rule would become unopenable.
"""

import json

from harness import Page

SHORT = "short1"
LONG = "abcdefghijkl"          # exactly MIN_PW


def _meter(p, value):
    return p.eval("(()=>{ meter(%s); return {label: document.getElementById('meterTxt').textContent,"
                  " width: document.getElementById('meterBar').style.width}; })()"
                  % json.dumps(value), False)


def run(r):
    with Page() as p:
        min_pw = p.eval("MIN_PW", False)
        r.equal("MIN_PW is 12", min_pw, 12)

        # --- the meter must reward length, not punctuation -------------------
        weak = ["q", "Pa1!", "P@ssw0rd", "Aa1!Aa1!", "a" * 30]
        strong = ["correcthorsebatterystaple", "my cat eats far too much tuna"]
        for pw in weak:
            r.equal("meter rates %r Weak" % pw, _meter(p, pw)["label"], "Weak")
        for pw in strong:
            r.equal("meter rates %r Strong" % pw, _meter(p, pw)["label"], "Strong")
        r.equal("an empty field shows no label", _meter(p, "")["label"], "")
        r.check("'Weak' means exactly 'shorter than MIN_PW'", p.eval("""(()=>{
          for (let n = 1; n <= 40; n++){
            meter('abcdefghijklmnopqrstuvwxyz0123456789xyzw'.slice(0, n));
            const weak = document.getElementById('meterTxt').textContent === 'Weak';
            if (weak !== (n < MIN_PW)) return false;
          }
          return true; })()""", False))
        r.check("a run of one character cannot score as a long password",
                _meter(p, "a" * 40)["label"] == "Weak")

        # --- the dialog ------------------------------------------------------
        state = p.eval("""(async()=>{
          const out = {};
          const pw1 = document.getElementById('pw1'), pw2 = document.getElementById('pw2');
          const err = document.getElementById('pwErr'), ok = document.getElementById('pwOk');
          const form = document.getElementById('pwForm');
          const fill = (a, b) => { pw1.value = a; pw1.dispatchEvent(new Event('input'));
                                   pw2.value = b === undefined ? a : b; };
          const submit = () => form.dispatchEvent(new Event('submit',{cancelable:true}));

          let pr = askNewPassword('SET PASSWORD');
          out.defaultLabel = ok.textContent;
          fill(''); submit();
          out.emptyBlocked = document.getElementById('pwDialog').open;
          out.emptyErr = err.textContent;
          document.getElementById('pwCancel').click(); await pr;

          pr = askNewPassword('SET PASSWORD');
          fill(%s, 'something-else'); submit();
          out.mismatchBlocked = document.getElementById('pwDialog').open;
          out.mismatchErr = err.textContent;
          document.getElementById('pwCancel').click(); await pr;

          pr = askNewPassword('SET PASSWORD');
          fill(%s); submit();
          out.shortBlockedOnce = document.getElementById('pwDialog').open;
          out.shortErr = err.textContent;
          out.relabelled = ok.textContent;
          submit();
          out.shortAccepted = await pr;

          pr = askNewPassword('SET PASSWORD');
          fill(%s); submit();
          out.armedLabel = ok.textContent;
          fill(%s + 'x');
          out.labelAfterEdit = ok.textContent;
          submit();
          out.reWarned = document.getElementById('pwDialog').open;
          document.getElementById('pwCancel').click(); await pr;
          out.labelAfterCancel = ok.textContent;

          pr = askNewPassword('SET PASSWORD');
          fill(%s); submit();
          out.longAccepted = await pr;
          return out; })()""" % (json.dumps(LONG), json.dumps(SHORT), json.dumps(SHORT),
                                 json.dumps(SHORT), json.dumps(LONG)))

        r.check("an empty password is still refused outright", state["emptyBlocked"])
        r.equal("with the empty message", state["emptyErr"], "Password can't be empty.")
        r.check("a mismatch is still refused", state["mismatchBlocked"])
        r.equal("with the mismatch message", state["mismatchErr"], "Passwords don't match.")

        r.check("a short password is held back on the first submit", state["shortBlockedOnce"])
        r.check("the warning names the actual length", "Only 6 characters" in state["shortErr"])
        r.check("and explains why length is what matters",
                "offline" in state["shortErr"] and str(min_pw) in state["shortErr"])
        r.equal("the button offers the override", state["relabelled"], "Use it anyway")
        r.equal("a second submit accepts it — warned, not refused",
                state["shortAccepted"], SHORT)

        r.equal("editing the password restores the normal button",
                state["labelAfterEdit"], state["defaultLabel"])
        r.check("and re-arms the warning", state["reWarned"])
        r.equal("cancelling leaves the button back at its default",
                state["labelAfterCancel"], state["defaultLabel"])
        r.equal("a password at MIN_PW goes straight through", state["longAccepted"], LONG)

        # --- the policy must never reach the open/unlock paths ---------------
        r.equal("a short password still encrypts and decrypts normally",
                p.eval("(async()=>await decryptBytes(await encryptText('data',%s),%s))()"
                       % (json.dumps(SHORT), json.dumps(SHORT))), "data")

    # a vault whose password predates the rule must open without any complaint
    with Page() as p:
        p.eval("""(async()=>{
          const h = { name:'legacy-short.html', written:null };
          h.reads = buildVaultHtml(await encryptText('older document', %s));
          h.getFile = async () => new File([h.reads], h.name, {type:'text/html'});
          h.createWritable = async () => ({write:async()=>{}, close:async()=>{}});
          window.showOpenFilePicker = async () => [h];
          window.__op = doOpen(); return 1; })()""" % json.dumps(SHORT), False)
        p.wait("document.getElementById('openDialog').open")
        p.eval("document.getElementById('openPw').value = %s;"
               "document.getElementById('openForm').dispatchEvent(new Event('submit',{cancelable:true}))"
               % json.dumps(SHORT), False)
        p.eval("(async()=>{ await window.__op; })()")
        r.equal("a vault with a short password still opens", p.eval("editor.value", False),
                "older document")
        r.check("with no warning shown on the unlock path",
                not p.eval("document.getElementById('pwDialog').open", False))
