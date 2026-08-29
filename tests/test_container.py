"""The property that must never regress, plus the SECTXT2 format contract.

No plaintext leaves via the container: a written vault is PRISTINE with only the
payload region replaced, so nothing outside the markers can carry runtime state.
Also pins that cost parameters are read from the file rather than the constants,
that the 39-byte header is authenticated, and that SECTXT1 still opens.
"""

import json

from harness import Page, read_fixture

CANARY = "TOP-SECRET-CANARY-9271"


def run(r):
    with Page() as p:
        # --- a save must not carry plaintext or runtime state -----------------
        built = p.eval("""(async()=>{
          const ed = document.getElementById('editor');
          ed.value = %s; ed.dispatchEvent(new Event('input'));
          showLock(600);                       // populate lockMeta + cipherwall from the plaintext
          const html = buildVaultHtml(await encryptText(ed.value, 'a-long-test-passphrase'));
          const V1 = '<!--CRAIGVAULT:BEGIN-->', V2 = '<!--CRAIGVAULT:END-->';
          const doc = new DOMParser().parseFromString(html, 'text/html');
          const txt = id => (doc.getElementById(id) || {}).textContent;
          return {
            prefixSame: html.slice(0, html.indexOf(V1)) === PRISTINE.slice(0, PRISTINE.indexOf(V1)),
            suffixSame: html.slice(html.indexOf(V2)) === PRISTINE.slice(PRISTINE.indexOf(V2)),
            noCanary: !html.includes(%s),
            noPassword: !html.includes('a-long-test-passphrase'),
            noOpenDialog: !/<dialog[^>]*\\sopen/.test(html),
            lockMeta: txt('lockMeta'), cipherwall: txt('cipherwall'),
            editor: doc.getElementById('editor').textContent, toast: txt('toast'),
          };})()""" % (json.dumps(CANARY), json.dumps(CANARY)))

        r.check("regions outside the markers are byte-identical to PRISTINE",
                built["prefixSame"] and built["suffixSame"])
        r.check("no plaintext in the written vault", built["noCanary"])
        r.check("no password in the written vault", built["noPassword"])
        r.check("no <dialog open> serialised", built["noOpenDialog"])
        for field in ("lockMeta", "cipherwall", "editor", "toast"):
            r.equal("#%s serialises empty" % field, built[field], "")

        # --- idempotent after one round-trip ---------------------------------
        r.check("shell is stable across saves (only the payload differs)", p.eval("""(async()=>{
          const a = buildVaultHtml(await encryptText('x','a-long-test-passphrase'));
          const b = buildVaultHtml(await encryptText('x','a-long-test-passphrase'));
          const V1='<!--CRAIGVAULT:BEGIN-->', V2='<!--CRAIGVAULT:END-->';
          const shell = h => h.slice(0,h.indexOf(V1)) + h.slice(h.indexOf(V2));
          return shell(a) === shell(b) && a !== b;   // fresh salt/IV each time
        })()"""))

        # --- SECTXT2 header layout -------------------------------------------
        head = p.eval("""(async()=>{
          const b = await encryptText('hello','a-long-test-passphrase');
          return {magic: new TextDecoder().decode(b.slice(0,7)), kdf: b[7],
                  logN: b[8], r: b[9], p: b[10], len: b.length};})()""")
        r.equal("magic is SECTXT2", head["magic"], "SECTXT2")
        r.equal("kdf id is 1 (scrypt)", head["kdf"], 1)
        r.equal("log2(N) matches LOGN", head["logN"], p.eval("LOGN", False))
        r.equal("r matches RPAR", head["r"], p.eval("RPAR", False))
        r.equal("p matches PPAR", head["p"], p.eval("PPAR", False))

        # --- the header is AAD: edited parameters must not decrypt ------------
        r.check("flipping a header byte fails like a wrong password", p.eval("""(async()=>{
          const b = await encryptText('hello','a-long-test-passphrase');
          const t = b.slice(); t[8] = t[8] ^ 1;          // change log2(N) inside the AAD
          try { await decryptBytes(t,'a-long-test-passphrase'); return false; }
          catch(e){ return e.name === 'OperationError' || !/format/.test(e.message); }})()"""))
        r.check("flipping a ciphertext byte fails (GCM tag)", p.eval("""(async()=>{
          const b = await encryptText('hello','a-long-test-passphrase');
          const t = b.slice(); t[t.length-1] = t[t.length-1] ^ 1;
          try { await decryptBytes(t,'a-long-test-passphrase'); return false; }
          catch(e){ return true; }})()"""))
        r.check("a bad magic reports as a format error, not a bad password", p.eval("""(async()=>{
          const t = new Uint8Array(60); t.set(new TextEncoder().encode('NOTAVLT'));
          try { await decryptBytes(t,'a-long-test-passphrase'); return false; }
          catch(e){ return e.message === 'format'; }})()"""))

        # --- cost parameters come from the file, not the constants ------------
        r.check("a vault built at logN=12 decrypts while LOGN is 15", p.eval("""(async()=>{
          const pw='a-long-test-passphrase', text='parameters come from the file';
          const salt=crypto.getRandomValues(new Uint8Array(16));
          const iv=crypto.getRandomValues(new Uint8Array(12));
          const head=new Uint8Array(39);
          head.set(new TextEncoder().encode('SECTXT2'),0);
          head[7]=1; head[8]=12; head[9]=8; head[10]=1;      // logN 12, not the shipped 15
          head.set(salt,11); head.set(iv,27);
          const key=await deriveKey(pw,salt,12,8,1);
          const ct=new Uint8Array(await crypto.subtle.encrypt(
            {name:'AES-GCM',iv,additionalData:head}, key, new TextEncoder().encode(text)));
          const blob=new Uint8Array(head.length+ct.length);
          blob.set(head,0); blob.set(ct,head.length);
          return (await decryptBytes(blob,pw)) === text && LOGN !== 12;})()"""))

        # --- legacy SECTXT1 ---------------------------------------------------
        fx = read_fixture()
        legacy = p.eval("""(async()=>{
          const raw = Uint8Array.from(atob(%s), c=>c.charCodeAt(0));
          const text = await decryptBytes(raw, %s);
          const again = await encryptText(text, %s);
          const back = extractPayload(buildVaultHtml(again)).bytes;
          return {reads: text, magic: new TextDecoder().decode(back.slice(0,7)),
                  reopens: (await decryptBytes(back, %s)) === text};})()"""
          % (json.dumps(fx["payload_base64"]), json.dumps(fx["password"]),
             json.dumps(fx["password"]), json.dumps(fx["password"])))
        r.equal("legacy SECTXT1 fixture decrypts", legacy["reads"], fx["plaintext"])
        r.equal("re-saving a legacy vault writes SECTXT2", legacy["magic"], "SECTXT2")
        r.check("the upgraded vault still opens", legacy["reopens"])

    # --- the blank template boots unlocked -----------------------------------
    with Page() as p:
        r.check("blank template comes up unlocked, focused, with no prompt",
                p.eval("!locked && password === null && document.activeElement === editor "
                       "&& !document.getElementById('openDialog').open", False))
        r.check("empty payload is reported as empty, not as a bad password",
                p.eval("extractPayload(PRISTINE).bytes === null "
                       "|| extractPayload(PRISTINE).bytes.length === 0", False))
