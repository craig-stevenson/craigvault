# Tests

A headless-Chrome suite for `index.html`. It drives the real page over the DevTools
protocol — real dialogs, real `crypto.subtle`, real key events — because almost every
bug these cover only exists in a browser.

```bash
python3 tests/run.py                 # everything (~20s)
python3 tests/run.py password        # only modules matching "password"
python3 tests/run.py lock file       # several filters
```

Exit status is 0 only if every check passed.

## What it needs

- **Chrome or Chromium** on `PATH` (`google-chrome`, `chromium`, …)
- **`websocket-client`**: `pip install websocket-client`

Neither is a dependency of `index.html`. The vault is still one self-contained file with
nothing to trust; these are test-time tools and nothing here is ever shipped inside a vault.

## Layout

| file | covers |
| --- | --- |
| `harness.py` | Chrome launch, DevTools client, input helpers, picker stubs |
| `run.py` | runner and reporting |
| `test_container.py` | no plaintext escapes the container; `SECTXT2` layout, AAD, `SECTXT1` |
| `test_lock_state.py` | a locked session holds no key; password fields are wiped (#1) |
| `test_file_targets.py` | `fileHandle` only ever points at a document actually opened (#2) |
| `test_editor_lock.py` | the editor is inert while encrypting (#3) |
| `test_autolock.py` | auto-lock arms after the first save, and fires (#4) |
| `test_password_policy.py` | the meter rewards length; short passwords warn, not refuse (#5) |
| `legacy-sectxt1.json` | **permanent fixture — never regenerate.** See below. |

`test_container.py` runs first on purpose: if a save can leak plaintext, or the format
contract is broken, nothing else matters.

## Rules

**Only the browser's file pickers are stubbed.** A picker cannot be driven headlessly and
is not what is under test. Every code path exercised is the app's own. A test that stubs
app logic is testing the stub.

**Type, don't assign.** Races and read-only behaviour are only real if the input is real,
so tests use `Input.insertText` and `Input.dispatchKeyEvent` rather than setting
`editor.value`. Assigning a value bypasses `readonly` and would pass against a broken build.

**Assert behaviour, not internals.** `idleTimer` keeps a stale numeric id after
`clearTimeout`, so it is not a reliable "is a lock pending" signal — the test waits to see
whether a lock actually fires instead.

**Never regenerate `legacy-sectxt1.json`.** It is the only evidence the `SECTXT1` read path
still works, and it is only evidence because it was written by the old PBKDF2 build. A
fixture produced by today's code would prove nothing. The file carries the same note.

**Do not use `--virtual-time-budget`.** It does not wait for a real scrypt derivation.

## Adding a test

A module exposes `run(r)` and records checks against `r`:

```python
from harness import Page

def run(r):
    with Page() as p:                      # opens the repo's index.html
        r.check("label", p.eval("someCondition", False))
        r.equal("label", p.eval("expr", False), "expected")
```

`Page.eval` awaits promises by default; pass `False` for synchronous expressions. Add the
filename to `ORDER` in `run.py`.
