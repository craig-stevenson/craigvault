"""The editor fills the window and shows line numbers that survive soft-wrapping.

The gutter numbers logical lines. A wrapped line occupies several rows, so each number is
sized to its line's rendered height, measured in a hidden mirror that shares the textarea's
font, width and padding. render() owns the gutter, so it follows every state change — and
after a lock it must show nothing derived from the plaintext.
"""

from harness import Page

PW = "gutter-test-passphrase"


def _rows(p):
    return p.eval("[...document.getElementById('gutter').children].map(d => d.textContent)", False)


def _heights(p):
    return p.eval("[...document.getElementById('gutter').children].map(d => parseFloat(d.style.height))", False)


def run(r):
    with Page() as p:
        p._cmd("Emulation.setDeviceMetricsOverride",
               {"width": 1400, "height": 800, "deviceScaleFactor": 1, "mobile": False})
        p.eval("renderGutter()", False)                     # the emulated width is new since boot
        geo = p.eval("""(()=>{ const m=document.querySelector('main').getBoundingClientRect(),
                               g=document.getElementById('gutter').getBoundingClientRect(),
                               e=editor.getBoundingClientRect();
          return {mainL:m.left, mainR:m.right, gL:g.left, gR:g.right, eL:e.left, eR:e.right}; })()""", False)
        r.check("the gutter starts at the left edge", geo["gL"] == geo["mainL"])
        r.check("the editor starts where the gutter ends", geo["eL"] == geo["gR"])
        r.check("and runs to the right edge of the window — no reading-measure cap", geo["eR"] == geo["mainR"])
        r.equal("an empty document shows a single line number", _rows(p), ["1"])

        # --- real keystrokes, real newlines ---
        p.click("#editor")
        p.type("one\ntwo\nthree")
        r.equal("three lines, three numbers", _rows(p), ["1", "2", "3"])
        lh = p.eval("parseFloat(getComputedStyle(editor).lineHeight)", False)
        r.check("unwrapped lines are one row tall", all(abs(h - lh) < 0.5 for h in _heights(p)))

        # --- a line long enough to wrap gets a taller number, and no extra numbers ---
        p.type("\n" + "wrap " * 120)
        rows, hs = _rows(p), _heights(p)
        r.equal("a wrapped line is still one logical line", rows, ["1", "2", "3", "4"])
        r.check("but its number is as tall as the wrapped rows it spans", hs[3] > lh * 1.5)
        r.check("and matches the mirror's measurement exactly",
                p.eval("document.getElementById('mirror').children[3].offsetHeight === "
                       "parseFloat(document.getElementById('gutter').children[3].style.height)", False))

        # --- narrower window: the same line wraps more, the number grows to match ---
        p._cmd("Emulation.setDeviceMetricsOverride",
               {"width": 700, "height": 800, "deviceScaleFactor": 1, "mobile": False})
        p.eval("renderGutter()", False)
        r.check("re-measured after a resize", _heights(p)[3] > hs[3])

        # --- scroll sync ---
        p.eval("editor.value = Array.from({length: 300}, (_, i) => 'line ' + (i + 1)).join('\\n');"
               "editor.dispatchEvent(new Event('input'));", False)
        r.equal("300 lines, 300 numbers", len(_rows(p)), 300)
        r.check("the gutter widens for three digits",
                p.eval("document.getElementById('gutter').style.width", False) == "5ch")
        p.eval("editor.scrollTop = 1234; editor.dispatchEvent(new Event('scroll'));", False)
        r.check("the gutter scrolls with the editor",
                p.eval("Math.abs(document.getElementById('gutter').scrollTop - editor.scrollTop) < 1", False))

        # --- locking must leave nothing derived from the text ---
        p.eval("password = %r" % PW, False)
        p.eval("(async()=>{ await doLock(); })()")
        p.wait("locked && !busy")
        r.equal("after a lock the gutter shows a lone 1", _rows(p), ["1"])
        r.equal("and the mirror holds no text", p.eval("document.getElementById('mirror').textContent", False), "")
        p.eval("document.getElementById('unlockPw').value = %r;"
               "document.getElementById('unlockForm').dispatchEvent(new Event('submit',{cancelable:true}))" % PW, False)
        p.wait("!busy && !locked")
        r.equal("unlocking brings the numbers back", len(_rows(p)), 300)

        # --- clicking the gutter, like clicking any margin, focuses the editor ---
        p.eval("editor.blur()", False)
        p.click("#gutter")
        r.check("clicking the gutter focuses the editor", p.eval("document.activeElement === editor", False))
