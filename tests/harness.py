"""Headless-Chrome harness for the CraigVault suite.

Needs google-chrome (or chromium) on PATH and the `websocket-client` package:

    pip install websocket-client

Neither is a dependency of index.html. The vault stays one file with nothing to trust;
these are test-time tools only, and nothing here is ever shipped inside a vault.

Why a real browser and not a stub: crypto.subtle, <dialog>.showModal, the File System
Access API and genuine key events all have to behave like the real thing. --virtual-time-budget
is deliberately NOT used — it does not wait for a real scrypt derivation.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

import websocket

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
FIXTURE = os.path.join(ROOT, "tests", "legacy-sectxt1.json")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("no Chrome/Chromium on PATH — the suite needs one to run")


class Page:
    """One headless tab, driven over the DevTools protocol."""

    def __init__(self, path=INDEX, timeout=120):
        self.path = path
        self._n = 0
        self._port = _free_port()
        self._profile = tempfile.mkdtemp(prefix="craigvault-test-")
        self._proc = subprocess.Popen(
            [_chrome(), "--headless=new",
             "--remote-debugging-port=%d" % self._port,
             "--user-data-dir=" + self._profile,
             "--no-first-run", "--no-default-browser-check", "--no-sandbox",
             "--disable-gpu", "--disable-extensions",
             # DevTools refuses a websocket whose Origin it was not told to allow
             "--remote-allow-origins=*",
             "file://" + path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._ws = self._attach(timeout)
        # let the page's own boot() finish before anything pokes at it
        self.wait("typeof render === 'function'")

    def _attach(self, timeout):
        want = os.path.basename(self.path)
        deadline = time.time() + 30
        last = None
        while time.time() < deadline:
            try:
                tabs = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % self._port, timeout=2))
                hit = [t for t in tabs if t["type"] == "page" and want in t["url"]]
                if hit:
                    return websocket.create_connection(
                        hit[0]["webSocketDebuggerUrl"], timeout=timeout)
            except Exception as exc:      # chrome not up yet, or tab not registered
                last = exc
            time.sleep(0.2)
        self.close()
        raise RuntimeError("could not attach to %s (%r)" % (self.path, last))

    def _cmd(self, method, params=None):
        self._n += 1
        self._ws.send(json.dumps({"id": self._n, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == self._n:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result", {})

    def eval(self, expression, await_promise=True):
        """Evaluate in page scope. Raises PageError if the expression throws."""
        res = self._cmd("Runtime.evaluate", {
            "expression": expression, "awaitPromise": await_promise,
            "returnByValue": True, "userGesture": True})
        if "exceptionDetails" in res:
            desc = res["exceptionDetails"].get("exception", {}).get("description")
            raise PageError(desc or json.dumps(res["exceptionDetails"]))
        return res.get("result", {}).get("value")

    def wait(self, expression, timeout=30):
        """Poll a synchronous expression until it is truthy."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.eval(expression, await_promise=False):
                    return True
            except PageError:
                pass
            time.sleep(0.03)
        raise TimeoutError("never became true: " + expression)

    # ---- genuine user input, not synthesised value assignment ----------------
    def click(self, selector):
        box = self.eval(
            "(()=>{const e=document.querySelector(%s); if(!e) return null;"
            "const r=e.getBoundingClientRect();"
            "return {x:r.x+r.width/2, y:r.y+r.height/2};})()" % json.dumps(selector),
            await_promise=False)
        if not box:
            raise RuntimeError("no element matches " + selector)
        for kind in ("mousePressed", "mouseReleased"):
            self._cmd("Input.dispatchMouseEvent", {
                "type": kind, "x": box["x"], "y": box["y"],
                "button": "left", "clickCount": 1})

    def type(self, text):
        """Insert text the way a keyboard would — fires real input events."""
        self._cmd("Input.insertText", {"text": text})

    def press(self, ch, code, vk):
        for kind in ("keyDown", "char", "keyUp"):
            self._cmd("Input.dispatchKeyEvent", {
                "type": kind, "text": ch, "key": ch, "code": code,
                "windowsVirtualKeyCode": vk})

    def close(self):
        try:
            if getattr(self, "_ws", None):
                self._ws.close()
        except Exception:
            pass
        try:
            self._proc.kill()
            self._proc.wait(timeout=5)
        except Exception:
            pass
        shutil.rmtree(self._profile, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class PageError(Exception):
    """The page threw while evaluating."""


# --- stubs -------------------------------------------------------------------
# Only the browser's own file pickers are stubbed. Every code path under test is
# the app's; a picker cannot be driven headlessly and is not what is being tested.

STUB_HANDLE = """
window.__mkHandle = (name, content) => {
  const h = { name, written: null, reads: content === undefined ? '' : content };
  h.getFile = async () => new File([h.reads], name, {type:'text/html'});
  h.createWritable = async () => ({
    write: async d => { h.written = d; }, close: async () => {} });
  return h;
};
window.__savePrompts = 0;
window.__suggested = null;
"""


def stub_save_picker(page, name="vault.html"):
    """Make showSaveFilePicker return a recording handle instead of a real one."""
    page.eval(STUB_HANDLE, await_promise=False)
    page.eval(
        "window.__saveTarget = window.__mkHandle(%s);"
        "window.showSaveFilePicker = async o => { window.__savePrompts++;"
        "  window.__suggested = o && o.suggestedName; return window.__saveTarget; };"
        % json.dumps(name), await_promise=False)


def stub_open_picker(page, handle_expr):
    page.eval("window.showOpenFilePicker = async () => [%s];" % handle_expr,
              await_promise=False)


def read_fixture():
    with open(FIXTURE) as fh:
        return json.load(fh)


# --- result collection -------------------------------------------------------
class Results:
    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail=""):
        self.rows.append((name, bool(ok), str(detail)))
        return bool(ok)

    def equal(self, name, got, want):
        return self.check(name, got == want,
                          "" if got == want else "got %r, want %r" % (got, want))

    @property
    def failed(self):
        return [r for r in self.rows if not r[1]]
