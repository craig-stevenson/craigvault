# CraigVault

A password-protected text editor that runs entirely in one HTML file. Saving writes your notes as AES-256-GCM ciphertext to an ordinary `.txt` — plain text on the outside, unreadable without the password on the inside. A self-contained `.html` vault that carries the editor *and* the notes together still opens, and is how you hand a document to someone who doesn't have the app. No server, no account, no build step, no dependencies.

```
open index.html   # that's the whole install
```

## Why

Most "secure notes" apps ask you to trust a service. CraigVault has nothing to trust: it is a single static file that never makes a network request. Encryption and decryption happen in your browser via the [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API), and the password lives only in a JavaScript variable that dies with the tab.

## Features

- **AES-256-GCM** encryption with **scrypt** key derivation (N=2^15, r=8, p=1 — 32 MB per guess)
- **Memory-hard by design** — scrypt forces an attacker to commit 32 MB per password guess, which is what actually defeats GPU and ASIC cracking
- **Versioned format** — KDF parameters live in the file, so costs can be raised later without breaking vaults you already saved
- **Authenticated** — a modified file fails to decrypt rather than yielding garbage
- **Idle auto-lock** (off / 1 / 5 / 15 minutes) that wipes plaintext from the DOM, re-encrypts unsaved edits in memory, and discards the key — unlocking derives it from your password again
- **Manual lock** with `Ctrl+L`, showing a ciphertext-style wall instead of your text — available even before the first save, which asks for a password so there is a key to lock with
- **Encrypted `.txt` files** — the document of record: genuinely text, pasteable into an email, readable only by CraigVault with the password
- **Self-contained vaults** — one `.html` holds the app and the encrypted document; double-click to open
- **File System Access API** support for true in-place saves, with a download fallback on browsers that lack it
- Keyboard shortcuts: `Ctrl+S` save, `Ctrl+Shift+S` save as, `Ctrl+O` open, `Ctrl+L` lock
- Length-based password strength meter that warns, once and with a reason, below 12 characters — and never refuses a password you insist on
- Unsaved-changes guard, no telemetry of any kind
- The editor goes read-only for the moment a save or lock is encrypting, so nothing you type can be quietly left out of the file

## Usage

`index.html` is the app. Your documents are encrypted `.txt` files beside it.

1. Open `index.html` in a modern browser (Chrome, Edge, and other Chromium browsers get in-place saving; Firefox and Safari fall back to downloads).
2. Type. Nothing touches disk until you save.
3. On first save you set a password and choose where to write the file, e.g. `notes.txt`. That password encrypts the document — **there is no recovery if you forget it.**
4. Next time, **Open** (`Ctrl+O`) `notes.txt`, enter the password, and your text comes back. Saving then writes straight back to it.
5. A `.txt` opened in any other editor shows a short note explaining what it is, then the ciphertext.

A self-contained `.html` vault — the app and a document in one file — opens the same way, or by double-clicking it, which boots straight into a password prompt. Saving after that writes a *new* `.txt` beside it rather than back into the bundle, so the bundle is never silently changed. On Firefox, and in embedded views like VS Code's Simple Browser, every save downloads a fresh copy that you replace by hand.

Tests live in [tests/](tests/) — `python3 tests/run.py` drives a real headless browser against `index.html`. They need Chrome and `websocket-client`; the vault itself still has no dependencies.

To serve it over HTTP instead of `file://`:

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## File format

A saved document is an ordinary text file: a short plain-English preamble, then the encrypted payload as base64 between two markers.

```
CraigVault encrypted document

This file is encrypted with AES-256-GCM. Opening it here shows you nothing
useful: open it with CraigVault and enter the password it was saved with.
…
-----BEGIN CRAIGVAULT-----
U0VDVFhUMgEPCAG1wH6VnXrhhR4ig4/wOI1+q9kccqf/aER634pMiM26…
-----END CRAIGVAULT-----
```

Only what lies between the markers is read, so the block survives being pasted into an email or a chat message and extracted back out.

A self-contained vault is an ordinary HTML file carrying the same payload. It sits in an inert `<script>` element between two marker comments:

```html
<!--CRAIGVAULT:BEGIN--><script id="vault" type="text/plain">BASE64…</script><!--CRAIGVAULT:END-->
```

Empty content means a blank template. In either container the base64 decodes to this payload:

| Offset | Size     | Contents                            |
| ------ | -------- | ----------------------------------- |
| 0      | 7 bytes  | Magic header `SECTXT2`              |
| 7      | 1 byte   | KDF id (`1` = scrypt)               |
| 8      | 1 byte   | log2(N) — cost, `15` by default     |
| 9      | 1 byte   | r — block size, `8`                 |
| 10     | 1 byte   | p — parallelism, `1`                |
| 11     | 16 bytes | scrypt salt (CSPRNG)                |
| 27     | 12 bytes | AES-GCM IV (CSPRNG)                 |
| 39     | rest     | Ciphertext + 16-byte GCM auth tag   |

Salt and IV are freshly generated on every save, so saving the same text twice produces different bytes.

The **whole 39-byte header is authenticated** as AES-GCM additional data, so the stored cost parameters cannot be edited — an attacker cannot rewrite `log2(N)` down to `1` and hand you back a vault that derives its key cheaply. Tampering fails authentication exactly like a wrong password.

Because the parameters live in the file rather than in the code, raising the cost later is safe: new vaults use the new setting and old ones keep opening with theirs.

**scrypt is built on the platform's own hashing.** It is PBKDF2-HMAC-SHA256 bookends wrapped around a memory-hard core, and both bookends run at a single iteration, so `crypto.subtle` still performs all the hashing. The only hand-written cryptographic code is the Salsa20/8 / BlockMix / ROMix core, verified against the RFC 7914 test vectors.

### Older vaults

Files with the `SECTXT1` magic — written before the move to scrypt, using PBKDF2 at 600,000 iterations — still open. Saving one rewrites it as `SECTXT2`, so a vault upgrades itself the first time you save it. Nothing to do by hand.

Building a vault splices only the region between those markers into a copy of the page source captured **before the app touched the DOM**, then re-extracts the payload and byte-compares it before writing. Everything outside the markers is therefore identical to the template, and a file that cannot verify itself is never written. The `.txt` writer verifies itself the same way.

Legacy `.sectxt` files — the raw payload bytes with no wrapper at all — still open. Saving one produces a *new* `.txt` and leaves the original `.sectxt` untouched, so importing is never destructive. The same is true of an `.html` vault: opening it never makes it the save target.

## Security notes

CraigVault is a small, auditable tool — the entire implementation is a few dozen lines in [index.html](index.html) — but it has not been through a third-party security audit. Read the code before trusting it with anything that matters. Known limits:

- **Browser memory is not secure storage.** While unlocked, the plaintext and password sit in JS strings that cannot be reliably zeroed and may be swapped to disk by the OS.
- **Locking wipes the textarea and drops the key, but not the process.** Locking discards the in-memory password, so unlocking has to derive the key from what you type — there is no live key sitting behind the lockscreen for a script or a console to reuse. What it cannot do is scrub strings the garbage collector has already released, so auto-lock remains a shoulder-surfing and walk-away defense, not protection against an attacker who can dump the process memory.
- **The password is the whole security boundary.** scrypt at 32 MB makes offline guessing far more expensive than PBKDF2 did — an attacker's GPU can no longer run thousands of guesses in parallel for free — but a weak password is still a weak password. Use a long passphrase.
- **Unlocking takes about a quarter of a second.** That cost is deliberate: it is paid once by you and once per guess by an attacker.
- **No plausible deniability.** A vault is plainly a CraigVault file: the HTML shell and the `SECTXT2` header both identify it as an encrypted document.
- **The app and the data share one file.** That is the point, but it means the vault is a single artifact to look after — back it up like you would any other document. Saves are verified before they are written, and the app shell is copied verbatim from the file you opened, so a save cannot silently corrupt the editor around your data.
- **A vault runs whatever editor it was saved with.** Opening a vault executes the JavaScript inside it. Only open vaults you wrote, exactly as you would only run scripts you trust.
- **No key rotation UI yet.** Changing a document's password means saving to a new file.

Found a problem? See [SECURITY.md](SECURITY.md).

## Browser support

Requires `crypto.subtle`, which browsers expose only in [secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts) — `https://`, `localhost`, or `file://`. In-place saving additionally needs the File System Access API (Chromium-based browsers today); elsewhere, saving downloads a new copy.

## Contributing

Issues and pull requests are welcome. Keep it dependency-free and keep it one file — that constraint is the point. Changes to the crypto core or file format should explain their threat-model reasoning in the PR description.

## License

[MIT](LICENSE) © Craig Stevenson
