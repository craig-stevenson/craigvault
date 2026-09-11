"""The armoured .txt container — the third read path, and the first write path that is not HTML.

The payload bytes are identical to a vault's; only the wrapper differs. Base64 between
plain-text markers makes the file genuinely text (it survives an email or a chat paste),
and a preamble above the markers explains the file to anyone who opens it in Notepad.
Only what sits between the markers is parsed, so the preamble is free — but it must
never contain the BEGIN marker itself.
"""

import json

from harness import Page, STUB_HANDLE, read_fixture

PW = "armoured-text-passphrase"
TEXT = "TOP-SECRET-CANARY-9271 in a text file"


def run(r):
    with Page() as p:
        built = p.eval("""(async()=>{
          const bytes = await encryptText(%s, %s);
          const text = buildVaultText(bytes);
          const back = extractArmoured(text);
          const viaDetector = payloadFrom(new TextEncoder().encode(text));
          const same = (a, b) => a && b && a.length === b.length && a.every((x, i) => x === b[i]);
          return {
            startsWithPreamble: text.startsWith("CraigVault encrypted document"),
            preambleSafe: !T_PREAMBLE.includes(T_BEGIN),
            hasMarkers: text.includes(T_BEGIN) && text.includes(T_END),
            endsWithNewline: text.endsWith("\\n"),
            noPlaintext: !text.includes(%s), noPassword: !text.includes(%s),
            isText: /^[\\x09\\x0a\\x0d\\x20-\\x7e]*$/.test(text),
            roundTrips: same(back.bytes, bytes),
            detectorAgrees: viaDetector.markers && same(viaDetector.bytes, bytes),
            decrypts: (await decryptBytes(back.bytes, %s)) === %s,
            wrapped: text.split("\\n").every(l => l.length <= 80),
          };})()""" % (json.dumps(TEXT), json.dumps(PW),       # encryptText(text, pw)
                       json.dumps(TEXT), json.dumps(PW),       # noPlaintext / noPassword
                       json.dumps(PW), json.dumps(TEXT)))      # decryptBytes(bytes, pw) === text
        r.check("a .txt opens with the plain-English preamble", built["startsWithPreamble"])
        r.check("the preamble can never be mistaken for the BEGIN marker", built["preambleSafe"])
        r.check("both markers are present", built["hasMarkers"])
        r.check("the file is pure printable ASCII — genuinely text", built["isText"])
        r.check("no line is longer than 80 columns", built["wrapped"])
        r.check("no plaintext in the .txt", built["noPlaintext"])
        r.check("no password in the .txt", built["noPassword"])
        r.check("extractArmoured returns the exact payload bytes", built["roundTrips"])
        r.check("payloadFrom detects it and agrees", built["detectorAgrees"])
        r.check("and the payload decrypts", built["decrypts"])

        # --- it survives being pasted into the middle of something else ---------
        r.check("the block still extracts when pasted inside other text", p.eval("""(async()=>{
          const text = buildVaultText(await encryptText('pasted', %s));
          const wrapped = "Hi Sam,\\n\\nhere it is:\\n\\n" + text + "\\n\\ncheers\\n";
          const got = payloadFrom(new TextEncoder().encode(wrapped)).bytes;
          return (await decryptBytes(got, %s)) === 'pasted'; })()""" % (json.dumps(PW), json.dumps(PW))))

        # --- degenerate inputs are told apart --------------------------------------
        deg = p.eval("""(()=>({
          empty:   extractArmoured(T_BEGIN + "\\n\\n" + T_END),
          garbage: extractArmoured(T_BEGIN + "\\n!!not base64!!\\n" + T_END),
          none:    extractArmoured("just some text"),
          reversed:extractArmoured(T_END + "\\nabc\\n" + T_BEGIN),
        }))()""", False)
        r.check("an empty block is 'ours but empty', not 'not ours'",
                deg["empty"]["markers"] and deg["empty"]["bytes"] is None)
        r.check("corrupt base64 is 'ours but unreadable'",
                deg["garbage"]["markers"] and deg["garbage"]["bytes"] is None)
        r.check("plain text is 'not ours'", not deg["none"]["markers"])
        r.check("markers in the wrong order are 'not ours'", not deg["reversed"]["markers"])

        # --- every read path dispatches to the right place -------------------------
        fx = read_fixture()
        paths = p.eval("""(async()=>{
          const raw2 = await encryptText('raw', %s);
          const raw1 = Uint8Array.from(atob(%s), c => c.charCodeAt(0));
          const html = new TextEncoder().encode(buildVaultHtml(await encryptText('html', %s)));
          const txt  = new TextEncoder().encode(buildVaultText(await encryptText('txt', %s)));
          const tmpl = new TextEncoder().encode(PRISTINE);
          const junk = new TextEncoder().encode("<html><body>hello</body></html>");
          const d = async b => { const f = payloadFrom(b); return f.bytes ? await decryptBytes(f.bytes, %s) : (f.markers ? "EMPTY" : "NONE"); };
          return { raw2: await d(raw2), html: await d(html), txt: await d(txt),
                   tmpl: await d(tmpl), junk: await d(junk),
                   raw1: payloadFrom(raw1).markers && new TextDecoder().decode(raw1.slice(0,7)) };
        })()""" % (json.dumps(PW), json.dumps(fx["payload_base64"]), json.dumps(PW), json.dumps(PW), json.dumps(PW)))
        r.equal("raw SECTXT2 bytes (legacy .sectxt)", paths["raw2"], "raw")
        r.equal("raw SECTXT1 bytes (the fixture) are recognised", paths["raw1"], "SECTXT1")
        r.equal("an HTML vault", paths["html"], "html")
        r.equal("an armoured .txt", paths["txt"], "txt")
        r.equal("the blank template is 'empty', not 'not ours'", paths["tmpl"], "EMPTY")
        r.equal("an unrelated HTML file is 'not ours'", paths["junk"], "NONE")

        # --- naming -------------------------------------------------------------------
        for given, want in {"untitled": "vault.txt", "old-notes.sectxt": "old-notes.txt",
                            "notes.html": "notes.txt", "notes.txt": "notes.txt",
                            "NOTES.TXT": "NOTES.TXT", "my.notes.v2.html": "my.notes.v2.txt",
                            "notes": "notes.txt"}.items():
            r.equal("txtNameFor(%r)" % given, p.eval("txtNameFor(%s)" % json.dumps(given), False), want)
        r.equal("htmlNameFor('notes.txt') crosses back", p.eval("htmlNameFor('notes.txt')", False), "notes.html")

    # --- and Open reads one end to end ------------------------------------------
    with Page() as p:
        p.eval(STUB_HANDLE, await_promise=False)
        p.eval("""(async()=>{
          const h = window.__mkHandle('notes.txt', buildVaultText(await encryptText(%s, %s)));
          window.showOpenFilePicker = async () => [h];
          window.__op = doOpen(); return 1; })()""" % (json.dumps(TEXT), json.dumps(PW)), False)
        p.wait("document.getElementById('openDialog').open")
        r.equal("the open prompt names the .txt",
                p.eval("document.getElementById('openName').textContent", False), "notes.txt")
        p.eval("document.getElementById('openPw').value = %s;"
               "document.getElementById('openForm').dispatchEvent(new Event('submit',{cancelable:true}))"
               % json.dumps(PW), False)
        p.eval("(async()=>{ await window.__op; })()")
        r.equal("Open decrypts a .txt through the real dialog", p.eval("editor.value", False), TEXT)
        r.equal("and names it in the header", p.eval("fileName", False), "notes.txt")
