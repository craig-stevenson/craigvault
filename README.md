# CraigVault

A password-protected text editor that runs entirely in one HTML file — **including your data**. Saving writes a new HTML file that carries both the editor and your notes as AES-256-GCM ciphertext. Double-click it later and it asks for your password. No server, no account, no build step, no dependencies.

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
- **Manual lock** with `Ctrl+L`, showing a ciphertext-style wall instead of your text
- **Self-contained vaults** — one `.html` holds the app and the encrypted document; double-click to open
- **File System Access API** support for true in-place saves, with a download fallback on browsers that lack it
- Keyboard shortcuts: `Ctrl+S` save, `Ctrl+Shift+S` save as, `Ctrl+O` open, `Ctrl+L` lock
- Password strength meter, unsaved-changes guard, no telemetry of any kind

## Usage

`index.html` is the **blank template**. Each vault you save is a standalone copy of it with your data inside.

1. Open `index.html` in a modern browser (Chrome, Edge, and other Chromium browsers get in-place saving; Firefox and Safari fall back to downloads).
2. Type. Nothing touches disk until you save.
3. On first save you set a password and choose where to write the vault, e.g. `notes.html`. That password encrypts the document — **there is no recovery if you forget it.**
4. **Double-click `notes.html` any time after that.** It opens locked, asks for the password, and your text comes back.
5. Edit and save again to write the vault back over itself.

A page cannot be handed a file handle to itself, so the first save of each session opens the file picker — point it at the vault you opened and confirm the overwrite. After that, saving is silent for the rest of the session. On Firefox, and in embedded views like VS Code's Simple Browser, every save downloads a fresh copy that you replace by hand.

Because a vault carries its own copy of the editor, updating `index.html` does not update vaults you already saved. To move an old vault onto a newer editor, open it from a fresh template with **Open** and save it again.

To serve it over HTTP instead of `file://`:

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## File format

A vault is an ordinary HTML file. The encrypted document sits in an inert `<script>` element between two marker comments:

```html
<!--CRAIGVAULT:BEGIN--><script id="vault" type="text/plain">BASE64…</script><!--CRAIGVAULT:END-->
```

Empty content means a blank template. The base64 decodes to this payload:

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

Saving splices only the region between those markers into a copy of the page source captured **before the app touched the DOM**, then re-extracts the payload and byte-compares it before writing. Everything outside the markers is therefore identical to the file you opened, and a save that cannot verify itself does not happen.

Legacy `.sectxt` files — the raw payload, from before the data moved into the HTML — still open. Saving one produces a `.html` vault.

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
