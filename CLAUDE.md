# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CraigVault is a password-protected text editor that lives entirely in one HTML file — **and so does the document**. Saving writes a new HTML file carrying the editor plus the user's notes as AES-256-GCM ciphertext; double-clicking that file boots straight into a password prompt. Zero network requests. `index.html` is the blank template; every saved vault is a standalone copy of it with a payload.

## Commands

There is **no build step, no linter, and no `package.json`**, and there never will be — see the hard constraints. There *is* a test suite.

```bash
xdg-open index.html            # run it — file:// is a secure context, so crypto.subtle works
python3 -m http.server 8000    # serve over HTTP when you need a real origin
python3 tests/run.py           # the suite: ~150 checks, ~26s, exit 0 only if all pass
python3 tests/run.py password  # just the modules matching a filter
```

The suite needs Chrome/Chromium on `PATH` and `pip install websocket-client`. Neither is a dependency *of the product* — `index.html` stays self-contained with nothing to trust, and nothing from `tests/` is ever shipped inside a vault. See `tests/README.md`.

In-place saving needs the File System Access API (Chromium only). Firefox and Safari exercise the download fallback, which is a separate code path — see gotcha 10. **Embedded browser views (VS Code's Simple Browser, and anything else that frames the page cross-origin) also fall back**, because Chromium refuses the picker there — see gotcha 15. Test in a real browser window, not the editor's preview pane.

## Architecture

Everything is `index.html`, 969 lines, three layers:

- **Styles** (`:7-119`) — CSS custom properties on `:root` are the whole design system (brass `#c9a227` accent on dark panels). No framework.
- **Markup** (`:120-254`) — header toolbar, editor `<textarea>`, an absolutely-positioned `.lockscreen` overlay, and three `<dialog method="dialog">` elements (`pwDialog` for setting a password, `openDialog` for entering one, `confirmDialog` for destructive confirmations). A `#toast` div carries transient status messages.
- **Payload** (`:254`) — `<!--CRAIGVAULT:BEGIN--><script id="vault" type="text/plain">…</script><!--CRAIGVAULT:END-->`, the base64 document. Empty in the template.
- **Script** (`:255-967`) — banner-commented sections: `PRISTINE` capture, crypto core (scrypt + AES-GCM), vault container, app state, transient messages, password dialogs, file ops, lock/unlock, idle auto-lock, wiring, boot.

**State model.** Three states, driven by `password` (`:489`) and `locked`. Note the script at `:255` is a *classic* script, not a module, so these top-level `let`s are global lexical bindings — the DevTools console resolves them by name, and `function` declarations land on `window`. Anything left in a variable is reachable, which is why locking clears rather than merely hides:

```
no document  →  unlocked                    →  locked
(no password)   (password set,                 (plaintext wiped from the DOM,
                 plaintext in the textarea)     password back to null,
                                                ciphertext held in lockedBlob)
      ↑                                              ↑
 blank template                            boot() lands here directly when
 (empty payload)                           the file carries a payload
```

`boot()` (`:947`) is the entry point: a payload means come up `locked` with `lockedBlob` set and no `password`. That is the *same* state `doLock` produces — locked always means no key in memory, however it was reached — so there is exactly one locked state to reason about, not two. `doUnlock` adopts the password on success, which is what makes it resolvable in both cases.

**Crypto contract** (`:263-427`). AES-256-GCM for the cipher, **scrypt** (RFC 7914) for key derivation. `encryptText` / `decryptBytes` / `deriveKey` are the only functions that touch `crypto.subtle`. Salt and IV are freshly generated on every save. `decryptBytes` throwing is the *only* wrong-password signal — GCM authentication doubles as the password check, so there is no separate verifier to maintain.

scrypt is PBKDF2-HMAC-SHA256 bookends around a memory-hard core, and both bookends run at **one** iteration, so `crypto.subtle` still does every hash. The only hand-written cryptographic code is `salsa20_8` (`:300`), `blockMix` (`:326`) and `roMix` (`:338`) — pure arithmetic, checked against the RFC 7914 vectors. **Do not reimplement a hash function here.**

Measured in Chrome: N=2^14 → 124ms, 2^15 → 245ms, 2^16 → 485ms; the PBKDF2 it replaced was 74ms. Shipping `LOGN = 15` (`:286`) — 32 MB per guess. The point is not wall-clock but memory: PBKDF2 let a GPU run thousands of guesses in parallel almost free, scrypt makes each one cost 32 MB.

## Hard constraints

- **Never add a dependency, bundler, framework, or `src/` split.** One self-contained file with nothing to trust is the product's security argument, not a stylistic preference. Push back on proposals that break it.
- **Never persist the password or plaintext.** No `localStorage`, `sessionStorage`, IndexedDB, cookies, or network calls. The password lives in a variable that dies with the tab.
- **Formats are versioned by magic, and a read path is never deleted.** Current: `SECTXT2` (7B) | kdf id (1B) | log2(N) (1B) | r (1B) | p (1B) | salt (16B) | IV (12B) | ct+tag. Legacy `SECTXT1` (7B) | salt (16B) | IV (12B) | ct+tag is still read via PBKDF2 at `ITER`; `encryptText` only ever writes `SECTXT2`, so a vault upgrades itself on its next save. Any further format change gets `SECTXT3` and keeps both older paths.
- **Cost parameters are read from the file, never from the constants.** `LOGN`/`RPAR`/`PPAR` apply only to vaults being *written*; `decryptBytes` uses the values in the header. This is what makes raising the cost safe, and it is the fix for the old design where `ITER` was compiled in and could not be changed without orphaning every existing file.
- **The 39-byte header is AES-GCM additional authenticated data.** Stored parameters therefore cannot be edited — no downgrading `log2(N)` to 1. If you change the header layout, change the AAD with it.
- **A save must never serialise the live DOM.** It splices `PRISTINE` (`:261`) — see gotcha 16. This is the difference between writing ciphertext and writing the user's plaintext to disk.

## Gotchas

1. **The `els` lookup array (`:482-487`)** collects every DOM id into one `Object.fromEntries` call. Add an element to the markup without adding its id here and `els.yourThing` is silently `undefined` until something uses it.
2. **`locked` gates every entry point, exactly like `busy`.** The lockscreen is an absolutely-positioned `div`, so nothing behind it is unreachable by virtue of being covered — it stays clickable, tabbable and scriptable until something checks the flag. `doSave`, `doOpen` and `doNew` all open with `if (locked || busy) return;`, and `render()` disables the toolbar and takes the editor out of the tab order to match. Put the guard in the **function**, not only in `render()`: a disabled button is not a boundary, and `Ctrl+O` reaches `doOpen` regardless (issue #8).

   `doNew` refusing while locked is the load-bearing one. Its "discard unsaved edits?" prompt is not an authentication step, and since `doLock` drops the password (**gotcha 8**), `lockedBlob` is the only copy of those edits — one click behind the wall used to destroy them for good.

   Use `readOnly` + `tabIndex = -1` on the editor rather than `inert`: `doUnlock` calls `editor.focus()` *before* `render()` runs in its `finally`, and an inert element silently refuses focus. Both of these still permit programmatic focus.

3. **`render()` (`:510`) is the only UI-sync point.** There is no reactive framework — every state mutation must end in `render()` or `setDirty()` (`:509`, which calls it). It also owns the `busy` flag: every button's `disabled` is decided here, so never set one ad hoc.
4. **All three dialogs use a promise-wrapping pattern** (`askNewPassword` `:574`, `askOpenPassword` `:632`, `askConfirm` `:647`): wrap `showModal()` in a Promise and *manually* `removeEventListener` on both the submit and cancel paths. Skip the cleanup and the stale handler fires again on the next open. Copy the existing shape for any new dialog.

   **Wipe password fields in `done()`, not on entry.** Closing a `<dialog>` does not clear its inputs, so clearing only at the top of the function leaves the plaintext password in the DOM until the *next* open — which was half of issue #1. `done()` is the single choke point both submit and cancel reach, and it receives `val` already evaluated, so wiping there cannot corrupt the resolved value. `doUnlock` needs the same treatment on its **success** path; the `catch` already clears. `wipeField` (`:572`) exists to make the intent greppable.
5. **`MIN_PW` is advisory, and only for setting a password.** `askNewPassword` (`:574`) warns once below `MIN_PW` (`:567`) and relabels its primary button to *Use it anyway*; a second submit proceeds. It is never applied on open or unlock — enforcing it there would lock people out of vaults whose passwords predate the rule. `SECURITY.md` draws the same line: what you choose after being warned is out of scope, misinforming you about it is not.

   `meter` (`:615`) scores on **length alone**, and its thresholds are tied to `MIN_PW` so that "Weak" means exactly "shorter than the warning threshold" — change one and check the other. The old scoring weighted composition 3 points to length's 2, which rated `P@ssw0rd` *Strong* and a 25-character passphrase *Weak*, contradicting the README's own advice to use a long passphrase. Do not reintroduce a composition bonus: any bonus is precisely what lets a short password climb. The one non-length rule is a distinct-character floor, so `aaaa…` cannot score as long.

6. **The crypto parameters are written in four places** — the cost constants `LOGN`/`RPAR`/`PPAR` (`:287`), the footer spec text (`:181`), and the README's feature list and format table. Change one, change all of them, plus `SECURITY.md`.
7. **The error channel is a string comparison.** `decryptBytes` throws `Error("format")` for a bad header versus a WebCrypto `OperationError` for a wrong password or tampering; `doOpen` (`:763`) branches on `err.message === "format"` to pick its message. Fragile, but preserve the distinction if you refactor — telling "not our file" apart from "wrong password" matters to users.
8. **Lock acquires a password if there isn't one, then throws it away.** Locking needs a key to re-encrypt with, so `doLock` opens `askNewPassword("SET PASSWORD TO LOCK")` when `password` is null — the same thing `doSave` does on a first save, and the inconsistency issue #7 reported. Cancelling that prompt leaves the document untouched.

   **Auto-lock deliberately does not come through that path.** `resetIdle` still requires a password, so an unsaved document never arms a timer. A modal firing after someone walks away would leave the plaintext on screen behind it until they came back and typed — worse than not locking. The footer says `no password · auto-lock off`, which stays accurate: manual lock is available, automatic lock is not.

   Either way, once `encryptText` has succeeded, `doLock` sets `password = null` alongside wiping the textarea. Keeping it live made `doUnlock(password)` a one-line console bypass of the entire lockscreen (issue #1). Nothing reads the variable while locked — `doSave` and `doLock` both bail on `locked` first, `resetIdle` is guarded by `!locked`, and `render()`'s `btnLock.title` checks `locked` before `password` precisely because it would otherwise misreport. Re-read that list before adding any code that touches `password`.
9. **The cipherwall is cosmetic.** `cipherNoise` (`:842`) generates random base64-ish characters, *not* the document's real ciphertext. The lockscreen copy says so outright ("The pattern behind this card is illustrative, not your file's bytes"), so the two now agree — keep them that way. Rendering the real ciphertext would leak length and structure over the user's shoulder; that's why it stays fake.
10. **Every file op has two code paths.** `hasFS` (`:503`) branches both save and open into File System Access versus download / `<input type=file>`. Test both — the download path is the one that historically drifted (it used to leave `fileName` as `untitled`).

   **Only ever record a target you actually used.** `fileHandle`, `fileName`, `password` and the editor contents must always describe the *same* document; an ordinary Save writes to `fileHandle` with no picker and no confirmation, so any moment where they disagree is a silent overwrite of a file the user never chose. `doSave` commits both together only after the write succeeds; `doOpen` holds the picked handle in a local and commits it only after the decrypt succeeds. It used to assign at pick time, so a cancelled password prompt — or a non-vault file, or an empty template — left `fileHandle` aimed at a file that was never opened, and the next Save destroyed it (issue #2). Add an early `return` to `doOpen` and this is the invariant you have to re-check.

   `doOpen` also refuses to adopt a handle to anything that isn't `.html`, so importing a legacy `.sectxt` writes a *new* vault instead of overwriting the original. `htmlNameFor` supplies the suggested name for both the picker and the download, so the two paths can't drift apart on naming again.
11. **A download is not a confirmed save.** `a.click()` is fire-and-forget — nothing reports whether a download was blocked, cancelled, redirected or written — so the non-`hasFS` path clears `dirty` but sets `unverified` (`:495`). `beforeunload` (`:747`) checks both, because the bug in issue #6 was a tab closing in silence on a document whose only copy may never have existed. Only proof clears it: a completed `createWritable` write, or opening the file. Don't clear `unverified` anywhere a write has merely been *attempted*.

12. **`resetIdle` runs constantly** — five document-level passive listeners feed it (`:915`). Keep it cheap. `doSave` also calls it in its `finally`, which is what arms auto-lock immediately after the first save.
13. **`busy` gates every crypto entry point.** `doSave`/`doOpen`/`doLock`/`doUnlock` each open with `if (busy) return;` and set the flag around the `await`, because a scrypt derivation is slow enough for a second Enter to re-enter the flow. Any new async crypto path needs the same guard and a `finally` that clears it.

    **It makes the editor read-only too** (`:531`). A save encrypts a snapshot read *before* a ~300ms derivation. The textarea used to stay writable across that window — `roMix` yields precisely so the tab keeps responding (**gotcha 20**) — so keystrokes landed after the snapshot, were written nowhere, and `dirty` was cleared regardless. `beforeunload` (`:747`) gates on `dirty` alone, so the tab would then close with no prompt on text that existed nowhere else (issue #3).

    `readOnly` is the entire fix, and it is deliberately blunt: it blocks typing, paste, drop and undo alike, so the content cannot move mid-derivation and there is nothing to reconcile afterwards. The cost is real — keystrokes during a save are dropped, not queued — which is why `textarea[readonly]` dims and shows a progress cursor rather than silently ignoring the user. Anything that widens the window (a slower KDF, a bigger document) makes that dropout longer, so measure before raising `LOGN`.
14. **`*{margin:0}` (`:15`) kills the UA's `dialog{margin:auto}`.** Modal dialogs need `margin:auto` restated (`:75`) or they render in the top-left corner instead of centred.
15. **`hasFS` is an existence check, not a permission check.** `"showSaveFilePicker" in window` is `true` inside VS Code's Simple Browser, but the call throws `SecurityError: Cross origin sub frames aren't allowed to show a file picker` — the API is gated by Permissions Policy in a cross-origin iframe. So both pickers are wrapped in their own `try` and classified by `pickerRefused` (`SecurityError`/`NotAllowedError`): a refusal sets the session-scoped `fsBlocked` and falls through to the download / `<input type=file>` path, while `AbortError` still means "user cancelled" and anything else still reports as a real failure. Keep those three outcomes distinct — collapsing them either swallows real errors or turns a cancel into a stray download.
16. **`PRISTINE` (`:261`) must stay the first statement in the script.** It is `document.documentElement.outerHTML` captured before any DOM mutation, and every save is built by slicing it (`buildVaultHtml`, `:461`). Capture it any later — or rebuild it from the live DOM — and a save bakes in runtime state: `lockMeta` and the cipherwall are *derived from the plaintext*. The prefix and suffix of a written vault are slices of `PRISTINE`, so nothing outside the payload can change by construction; that property is the safety argument, not the care taken.
17. **The payload markers are HTML comments for a reason.** `V_BEGIN`/`V_END` (`:429`) are what the splice locates, never the `<script id="vault">` tag: comments survive DOM serialisation verbatim, whereas a serialiser may renormalise tag attributes. The `<script>` element is regenerated on every save, so no code depends on how it was rendered. `type="text/plain"` keeps it inert, and base64 can never contain `</scr`+`ipt>`.
18. **A save that cannot verify itself does not happen.** `buildVaultHtml` re-extracts the payload from the document it just built and byte-compares it before returning, and it runs *before* the picker opens. App and data now share one file, so a bad write loses both — a throw here is correct and must stay louder than a silent partial save.
19. **Serialisation is idempotent after one round-trip, and tested.** The first save normalises formatting; generation 2 onward is byte-identical outside the payload. `h_vault`/`e2e_vault` assert this, so drift across saves would fail the suite rather than accumulate silently.
20. **scrypt runs on the main thread; PBKDF2 did not.** WebCrypto derived keys off-thread, so the old code could freeze-free. `roMix` therefore yields every 2048 iterations and reports progress through `setProgress` (`:547`), which drives the footer to `deriving key… 47%`. The yield is a **MessageChannel** round-trip (`yieldToUI`, `:295`), not `setTimeout(0)` — setTimeout is clamped to ~4ms once nested, which would have added ~250ms to a 245ms derivation. Measured overhead of yielding plus progress: 240ms → 251ms. Any new work in that loop must keep it cheap.
21. **`decryptBytes` reads cost parameters from the file, `encryptText` writes the constants.** Mixing those up produces a build that appears to work while quietly ignoring what a vault actually says — the `h_scrypt` suite pins this with a vault hand-built at `logN=12`.
22. **Never regenerate the legacy fixture with the current build.** `SECTXT1` backward compatibility is only proven by a file produced by the *old* PBKDF2 code; a fixture made by today's build proves nothing. The one in use was captured before the change and lives at `tests/legacy-sectxt1.json`, which carries its own do-not-regenerate note.

## Verifying a change

**Run `python3 tests/run.py` first.** It drives the real page over the DevTools protocol and covers the container property, the `SECTXT2` format and its AAD, `SECTXT1` compatibility, lock/unlock state, save-target discipline, the editor read-only guard, auto-lock, locked-session inertness, and password policy. `tests/README.md` explains the rules it follows; the two that matter most when adding to it are *only the browser's file pickers are stubbed* (a test that stubs app logic tests the stub) and *type, don't assign* (setting `editor.value` bypasses `readonly` and would pass against a broken build). `--virtual-time-budget` will *not* wait for a real key derivation.

The manual checks below are what the suite does not reach: real pickers, real downloads, and how any of it feels.

**The property that must never regress — no plaintext leaves via the container:**

1. Type a distinctive string, show the lockscreen (so `lockMeta`/cipherwall are populated), then build a save. The output must not contain the string, `#lockMeta`/`#cipherwall`/`#editor`/`#toast` must serialise empty, no `<dialog open>`, and the regions outside the markers must be byte-identical to `PRISTINE`.

**Crypto correctness comes first, and runs in Node — no browser needed.** The scrypt core uses
`crypto.subtle` only for its single-iteration bookends, which Node provides, so the shipped code runs
headless. Check it against the **RFC 7914 test vectors** before anything else: §8 Salsa20/8, §9
BlockMix, §10 ROMix, and §12 vectors 1–3 (vector 2 has `p=16` and is the only one exercising the
multi-block path). If those fail nothing else matters. Then, in the browser: `SECTXT2` header layout,
AAD rejection of edited parameters, refusal of absurd `log2(N)`, and decryption of a vault hand-built
at a *different* `logN` than the constant.

**Backward compatibility, against a genuinely old file:** decrypt `tests/legacy-sectxt1.json`
(**gotcha 22** — never regenerate it), then confirm re-saving produces `SECTXT2` and still opens.

**Round-trip, by hand:**

2. Type text → **Save** → set a password → choose `notes.html`.
3. Open `notes.html` in a new tab: it boots **locked**, password field focused, header naming the file, footer `locked`, counter `—`, Save disabled.
4. Wrong password → "Incorrect password.", stays locked, textarea still empty. Correct password → exact text returns, `Lock now` enables, dirty dot clear.
5. Edit → Save → reload → the new text appears. Save twice → the payloads differ (fresh salt/IV) while the shell outside the markers stays byte-identical.
6. Flip a base64 character in the payload → unlock fails like a wrong password (GCM tag). Never partial plaintext. Flip a byte inside the 39-byte header instead → same clean failure, via the AAD.
6b. Unlock a large vault and watch the footer: it must count up (`deriving key… 47%`) and the tab must stay responsive — scrypt is on the main thread, so a regression here shows as a freeze (**gotcha 20**).
7. Delete a marker → Save throws and writes **nothing**.
8. Open a non-vault `.html` → "no encrypted payload found", distinct from a wrong password; an empty template → "that vault is empty".
9. Open a legacy `.sectxt` → imports and decrypts; saving it produces `.html`.
10. `Ctrl+L` → textarea wipes, noise wall appears, unlock restores *unsaved* edits. Auto-lock at 1 min locks when idle; typing resets the timer.
11. Repeat 2-5 in Firefox for the non-`hasFS` path, and in VS Code's Simple Browser for the `fsBlocked` fallback (Save must download and the header must update, not stay `untitled`).
12. The blank template with no payload must still come up unlocked with the editor focused and no prompt.

## Scope

**Likely next feature:** password/key rotation. Changing a vault's password currently means saving to a new file. `askNewPassword(title)` is already parameterised for it, and the container makes it cheap: re-encrypt and splice, no format work.

**Permanent limits, not bugs.** Plaintext and password sitting in browser memory while unlocked, OS-level attacks (swap, memory dumps, keyloggers), weak user-chosen passwords, and the identifiable `SECTXT1` header and HTML shell are all documented as out of scope in `SECURITY.md`. Don't propose work to close them; auto-lock is a walk-away defense, not memory protection.

## Repo conventions

- **Never commit a vault.** `.gitignore` ignores `/*.html` and re-admits only `!/index.html`, because a saved vault is now an `.html` and would otherwise look exactly like the template. `*.sectxt` stays ignored for legacy files. Check `git status` before committing anything at the repo root.
- `index.html` is the blank template — its payload element stays empty in the repo. If a diff ever shows base64 inside `<script id="vault">`, someone committed their data.
- `tests/legacy-sectxt1.json` is a permanent fixture, not scratch: it is the only evidence the `SECTXT1` read path still works, and it cannot be rebuilt now that the PBKDF2 writer is gone.
- Crypto, container, or format changes update `README.md` (features, format section, security notes) and `SECURITY.md` (scope) in the same commit.
