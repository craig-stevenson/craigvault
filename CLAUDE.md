# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CraigVault is a password-protected text editor that lives entirely in one HTML file. It encrypts to AES-256-GCM via the Web Crypto API and makes zero network requests.

## Commands

There is **no build step, no test runner, no linter, and no `package.json`**. Don't look for them.

```bash
xdg-open index.html            # run it — file:// is a secure context, so crypto.subtle works
python3 -m http.server 8000    # serve over HTTP when you need a real origin
```

In-place saving needs the File System Access API (Chromium only). Firefox and Safari exercise the download fallback, which is a separate code path — see gotcha 8.

## Architecture

Everything is `index.html`, 406 lines, three layers:

- **Styles** (`:7-81`) — CSS custom properties on `:root` are the whole design system (brass `#c9a227` accent on dark panels). No framework.
- **Markup** (`:83-165`) — header toolbar, editor `<textarea>`, an absolutely-positioned `.lockscreen` overlay, and two `<dialog method="dialog">` elements (`pwDialog` for setting a password, `openDialog` for entering one).
- **Script** (`:166-406`) — banner-commented sections: crypto core, app state, password dialogs, file ops, lock/unlock, idle auto-lock, wiring.

**State model.** Three states, driven by the module-scope `password` (`:207`) and `locked`:

```
no document  →  unlocked                    →  locked
(no password)   (password set,                 (plaintext wiped from the DOM,
                 plaintext in the textarea)     ciphertext held in lockedBlob)
```

**Crypto contract** (`:168-198`). `encryptText` and `decryptBytes` are the only functions that touch `crypto.subtle`. Salt and IV are freshly generated on every save. `decryptBytes` throwing is the *only* wrong-password signal — GCM authentication doubles as the password check, so there is no separate verifier to maintain.

## Hard constraints

- **Never add a dependency, bundler, framework, or `src/` split.** One self-contained file with nothing to trust is the product's security argument, not a stylistic preference. Push back on proposals that break it.
- **Never persist the password or plaintext.** No `localStorage`, `sessionStorage`, IndexedDB, cookies, or network calls. The password lives in a variable that dies with the tab.
- **The `.sectxt` format is frozen** — `SECTXT1` magic (7B) | salt (16B) | IV (12B) | ciphertext+tag. Changing `ITER` silently breaks every file a user has already saved; it is not a tunable. A format change needs a new magic string plus a read path for the old one.

## Gotchas

1. **The `els` lookup array (`:202`)** collects every DOM id into one `Object.fromEntries` call. Add an element to the markup without adding its id here and `els.yourThing` is silently `undefined` until something uses it.
2. **`render()` (`:218`) is the only UI-sync point.** There is no reactive framework — every state mutation must end in `render()` or `setDirty()` (`:217`, which calls it).
3. **Both dialogs use a promise-wrapping pattern** (`askNewPassword` `:228`, `askOpenPassword` `:257`): wrap `showModal()` in a Promise and *manually* `removeEventListener` on both the submit and cancel paths. Skip the cleanup and the stale handler fires again on the next open. Copy the existing shape for any new dialog.
4. **The crypto parameters are written in four places** — the `ITER` constant (`:172`), the footer spec text (`:131`), and the README's feature list and format table. Change one, change all of them, plus `SECURITY.md`.
5. **The error channel is a string comparison.** `decryptBytes` throws `Error("format")` for a bad header versus a WebCrypto `OperationError` for a wrong password or tampering; `doOpen` (`:332`) branches on `err.message === "format"` to pick its message. Fragile, but preserve the distinction if you refactor — telling "not our file" apart from "wrong password" matters to users.
6. **Lock requires a password.** `doLock` (`:353`) returns early when `password` is null, so a never-saved document cannot lock and auto-lock silently doesn't run. That's deliberate — there is no key to re-encrypt with. Don't "fix" it without designing what an unsaved lock would even mean.
7. **The cipherwall is cosmetic.** `cipherNoise` (`:347`) generates random base64-ish characters, *not* the document's real ciphertext, while the lockscreen copy says "The text above is what this document looks like at rest." Known discrepancy: rendering the real ciphertext would be more honest but leaks length and structure over the user's shoulder. Weigh that before changing either side.
8. **Every file op has two code paths.** `hasFS` (`:215`) branches both save and open into File System Access versus download / `<input type=file>`. Test both.
9. **`resetIdle` runs constantly** — five document-level passive listeners feed it (`:385`). Keep it cheap.

## Verifying a change

No automated tests exist. After touching crypto, file ops, or lock logic, run this by hand:

1. Type text → **Save** → set a password → a `.sectxt` file is written.
2. `xxd -l 7 file.sectxt` → `SECTXT1`. Save the same text twice → the bytes differ (fresh salt/IV).
3. **New** → **Open** → wrong password → reprompt loop with "Incorrect password, or the file was modified", no crash.
4. Correct password → plaintext returns, filename updates, dirty dot clears.
5. Flip a ciphertext byte in a hex editor → same failure as a wrong password (GCM tag rejection). Never partial plaintext.
6. Open a non-CraigVault file → the "bad header" message specifically.
7. `Ctrl+L` → textarea wipes, noise wall appears, unlock restores *unsaved* edits.
8. Auto-lock at 1 min → it locks when idle; typing resets the timer.
9. Repeat 1-4 in Firefox to exercise the non-`hasFS` path.

## Scope

**Likely next feature:** password/key rotation. Changing a document's password currently means saving to a new file.

**Permanent limits, not bugs.** Plaintext and password sitting in browser memory while unlocked, OS-level attacks (swap, memory dumps, keyloggers), weak user-chosen passwords, and the identifiable `SECTXT1` header are all documented as out of scope in `SECURITY.md`. Don't propose work to close them; auto-lock is a walk-away defense, not memory protection.

## Repo conventions

- `*.sectxt` is the first entry in `.gitignore`. Never commit a test vault.
- Crypto or format changes update `README.md` (features, format table, security notes) and `SECURITY.md` (scope) in the same commit.
