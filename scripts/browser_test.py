#!/usr/bin/env python3
"""
Free My TV for webOS - headless browser test (stdlib only; needs Chrome/Chromium).

Loads a copy of app/index.html in headless Chrome once per language and checks:
  - no uncaught JavaScript errors during boot
  - the static UI really switched language (spot-checked strings)
  - every language has exactly the same translation keys, and every English string
    that the HTML/JS asks t() for has a translation entry (catches typos and
    forgotten strings when someone adds UI text)

Usage: python scripts/browser_test.py [--chrome PATH]
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO_DIR, "app", "index.html")

EXPECTED = {  # language -> (element id, expected text)
    "en": ("customizeBtn", "Customize"),
    "pt": ("customizeBtn", "Personalizar"),
    "es": ("customizeBtn", "Personalizar"),
    "de": ("customizeBtn", "Anpassen"),
    "fr": ("customizeBtn", "Personnaliser"),
}

# Runs inside the page after boot and reports into <pre id="__result">.
PROBE = r"""
setTimeout(function () {
  var out = { errors: window.__errors || [], missing: [], keyDiff: [], text: '' };
  var base = Object.keys(I18N.pt).sort().join('\n');
  Object.keys(I18N).forEach(function (l) {
    if (Object.keys(I18N[l]).sort().join('\n') !== base) out.keyDiff.push(l);
  });
  // Every translatable English string used in markup must exist in the dictionary.
  var seen = {};
  // Picks (titles, plots) come from data feeds and are intentionally left untranslated.
  document.querySelectorAll('[data-tag]:not(.pick-card),[data-title]:not(.pick-card),[data-desc]:not(.pick-card)').forEach(function (el) {
    ['tag', 'title', 'desc'].forEach(function (k) {
      var v = el.getAttribute('data-' + k);
      if (v) seen[v] = 1;
    });
  });
  DEFAULT_CATALOG.forEach(function (a) { seen[a.tag] = 1; seen[a.desc] = 1; });
  Object.keys(seen).forEach(function (v) {
    var isBrand = DEFAULT_CATALOG.some(function (a) { return a.title === v; }) || /^HDMI \d$/.test(v);
    if (!isBrand && !Object.prototype.hasOwnProperty.call(I18N.pt, v)) out.missing.push(v);
  });
  out.text = document.getElementById('customizeBtn').textContent.replace(/^\s+|\s+$/g, '').replace('⚙️ ', '');
  out.ambient = [];
  function eq(name, got, want) {
    if (got !== want) out.ambient.push(name + ': got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want));
  }
  function need(name) {
    if (typeof window[name] !== 'function') { out.ambient.push(name + ' missing'); return false; }
    return true;
  }
  if (need('ambientDim')) {
    eq('dim black', ambientDim('#000000'), 0.55);
    eq('dim white', ambientDim('#ffffff'), 0.25);
    eq('dim mid', ambientDim('#808080'), 0.4);
    eq('dim bad', ambientDim('nope'), 0.4);
    eq('dim none', ambientDim(undefined), 0.4);
  }
  if (need('ambientBudgetAllows')) {
    var now = 10000000, recent = [], old = [], i;
    for (i = 0; i < 40; i++) { recent.push(now - 1000); old.push(now - 3700000); }
    eq('budget full', ambientBudgetAllows(recent, now, 40), false);
    eq('budget 39', ambientBudgetAllows(recent.slice(1), now, 40), true);
    eq('budget old', ambientBudgetAllows(old, now, 40), true);
    eq('budget empty', ambientBudgetAllows([], now, 40), true);
    eq('budget ping cap', ambientBudgetAllows(recent.slice(0, 30), now, 30), false);
  }
  if (need('ambientPhotoUrl')) {
    eq('url 4k', ambientPhotoUrl('https://images.unsplash.com/p?ixid=1', 3840), 'https://images.unsplash.com/p?ixid=1&w=3840&q=70&fm=jpg');
    eq('url hd', ambientPhotoUrl('https://images.unsplash.com/p?ixid=1', 1920), 'https://images.unsplash.com/p?ixid=1&w=1920&q=70&fm=jpg');
    eq('url bare', ambientPhotoUrl('https://x.test/y', 1280), 'https://x.test/y?w=1920&q=70&fm=jpg');
  }
  if (need('ambientShape')) {
    var shaped = ambientShape({ id: 'a1', color: '#0a0a20', urls: { raw: 'https://images.unsplash.com/p?ixid=1' },
      user: { name: 'Ann' }, links: { download_location: 'https://api.unsplash.com/photos/a1/download?ixid=1' } });
    eq('shape id', shaped && shaped.id, 'a1');
    eq('shape raw', shaped && shaped.raw, 'https://images.unsplash.com/p?ixid=1');
    eq('shape color', shaped && shaped.color, '#0a0a20');
    eq('shape name', shaped && shaped.name, 'Ann');
    eq('shape dl', shaped && shaped.dl, 'https://api.unsplash.com/photos/a1/download?ixid=1');
    eq('shape partial', ambientShape({ id: 'x' }), null);
    eq('shape null', ambientShape(null), null);
  }
  var pre = document.createElement('pre');
  pre.id = '__result';
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}, 1500);
"""

ERROR_HOOK = "<script>window.__errors=[];window.addEventListener('error',function(e){window.__errors.push(String(e.message))});</script>"


def find_chrome(explicit):
    candidates = [explicit, os.environ.get("CHROME"), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for c in candidates:
        if c and (os.path.exists(c) or shutil.which(c)):
            return c
    return None


def run_language(chrome, lang, workdir):
    with open(APP, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("<head>", f'<head>{ERROR_HOOK}<script>localStorage.setItem("fmtv_lang","{lang}")</script>', 1)
    html = html.replace("</body>", f"<script>{PROBE}</script></body>")
    page = os.path.join(workdir, f"app_{lang}.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    shutil.copytree(os.path.join(REPO_DIR, "app", "assets"), os.path.join(workdir, "assets"), dirs_exist_ok=True)
    res = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--window-size=1920,1080",
         "--virtual-time-budget=6000", f"--user-data-dir={os.path.join(workdir, 'profile_' + lang)}",
         "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=120)
    m = re.search(r'<pre id="__result">(.*?)</pre>', res.stdout, re.S)
    if not m:
        return None, res.stderr[-400:]
    import html as htmllib
    return json.loads(htmllib.unescape(m.group(1))), ""


def main():
    chrome = find_chrome(sys.argv[sys.argv.index("--chrome") + 1] if "--chrome" in sys.argv else None)
    if not chrome:
        print("[!] Chrome/Chromium not found (set CHROME or pass --chrome PATH)")
        return 2
    failures = []
    with tempfile.TemporaryDirectory() as workdir:
        for lang, (_, expected) in EXPECTED.items():
            result, stderr = run_language(chrome, lang, workdir)
            if result is None:
                failures.append(f"{lang}: page did not finish booting ({stderr.strip()})")
                continue
            if result["errors"]:
                failures.append(f"{lang}: uncaught JS errors: {result['errors'][:3]}")
            if result["text"] != expected:
                failures.append(f"{lang}: expected Customize button '{expected}', got '{result['text']}'")
            if lang == "en":  # dictionary checks are language independent; report once
                if result["keyDiff"]:
                    failures.append(f"translation keys differ in: {result['keyDiff']}")
                if result["missing"]:
                    failures.append(f"strings without translations: {result['missing']}")
                if result["ambient"]:
                    failures.append(f"ambient checks: {result['ambient']}")
            print(f"[*] {lang}: ok" if not any(x.startswith(lang + ":") for x in failures) else f"[!] {lang}: failed")
    for f in failures:
        print(f"[!] {f}")
    print("[+] browser tests passed" if not failures else f"[!] {len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
