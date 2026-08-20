# CraigVault

A password-protected text editor that runs entirely in one HTML file. Type notes, hit save, and what lands on disk is AES-256-GCM ciphertext — nothing else. No server, no account, no build step, no dependencies.

```
open index.html   # that's the whole install
```

## Why

Most "secure notes" apps ask you to trust a service. CraigVault has nothing to trust: it is a single static file that never makes a network request. Encryption and decryption happen in your browser via the [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API), and the password lives only in a JavaScript variable that dies with the tab.

## Features

- **AES-256-GCM** encryption with **PBKDF2-SHA256** key derivation (600,000 iterations)
- **Authenticated** — a modified file fails to decrypt rather than yielding garbage
- **Idle auto-lock** (off / 1 / 5 / 15 minutes) that wipes plaintext from the DOM and re-encrypts unsaved edits in memory
- **Manual lock** with `Ctrl+L`, showing a ciphertext-style wall instead of your text
- **File System Access API** support for true in-place saves, with a download fallback on browsers that lack it
- Keyboard shortcuts: `Ctrl+S` save, `Ctrl+Shift+S` save as, `Ctrl+O` open, `Ctrl+L` lock
- Password strength meter, unsaved-changes guard, no telemetry of any kind

## Usage

1. Open `index.html` in a modern browser (Chrome, Edge, and other Chromium browsers get in-place saving; Firefox and Safari fall back to downloads).
2. Type. Nothing touches disk until you save.
3. On first save you set a password. That password encrypts the file — **there is no recovery if you forget it.**
4. Reopen with **Open**, enter the password, and the plaintext comes back.

To serve it over HTTP instead of `file://`:

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## File format

Saved files use the `.sectxt` extension and this layout:

| Offset | Size     | Contents                          |
| ------ | -------- | --------------------------------- |
| 0      | 7 bytes  | Magic header `SECTXT1`            |
| 7      | 16 bytes | PBKDF2 salt (CSPRNG)              |
| 23     | 12 bytes | AES-GCM IV (CSPRNG)               |
| 35     | rest     | Ciphertext + 16-byte GCM auth tag |

Salt and IV are freshly generated on every save, so saving the same text twice produces different bytes.

## Security notes

CraigVault is a small, auditable tool — the entire implementation is a few dozen lines in [index.html](index.html) — but it has not been through a third-party security audit. Read the code before trusting it with anything that matters. Known limits:

- **Browser memory is not secure storage.** While unlocked, the plaintext and password sit in JS strings that cannot be reliably zeroed and may be swapped to disk by the OS.
- **Locking wipes the textarea, not the process.** Auto-lock is a shoulder-surfing and walk-away defense, not protection against an attacker with memory access on the machine.
- **The password is the whole security boundary.** PBKDF2 at 600k iterations slows offline guessing, but a weak password is still a weak password. Use a long passphrase.
- **No plausible deniability.** The `SECTXT1` header makes the file identifiable as an encrypted document.
- **No key rotation UI yet.** Changing a document's password means saving to a new file.

Found a problem? See [SECURITY.md](SECURITY.md).

## Browser support

Requires `crypto.subtle`, which browsers expose only in [secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts) — `https://`, `localhost`, or `file://`. In-place saving additionally needs the File System Access API (Chromium-based browsers today); elsewhere, saving downloads a new copy.

## Contributing

Issues and pull requests are welcome. Keep it dependency-free and keep it one file — that constraint is the point. Changes to the crypto core or file format should explain their threat-model reasoning in the PR description.

## License

[MIT](LICENSE) © Craig Stevenson
