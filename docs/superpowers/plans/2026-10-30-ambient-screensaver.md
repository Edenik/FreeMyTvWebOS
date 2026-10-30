# Ambient Screensaver (Unsplash) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dimmed, slowly moving Unsplash photo behind the existing pixel-shifting clock screensaver, with settings for idle time, on/off, photo duration, motion and the Unsplash key.

**Architecture:** Everything lives in the single `app/index.html` (the app's established shape), as pure helper functions plus a small fetch/cache module plus a render module hooked into the existing `enterScreensaver()` / `exitScreensaver()`. Tests run inside the repo's headless-Chrome harness (`scripts/browser_test.py`) by probing globals and driving scenarios with a stubbed `fetch`. Any failure falls back to today's black clock screensaver.

**Tech Stack:** ES5 JavaScript (Chromium 38 on webOS 3.x), HTML/CSS, Python 3 test scripts, headless Chrome, Node (`es-check`).

## Global Constraints

- Source of truth: `docs/superpowers/specs/2026-10-30-ambient-screensaver-design.md`.
- All app JS is ES5: `var`, `function`, no arrow functions, no `let`/`const`, no template literals, no `async`/`await`. `fetch` is only used behind `typeof fetch === 'function'`.
- `localStorage` keys: `fmtv_idle_mins`, `fmtv_unsplash_key`, `fmtv_ambient`, `fmtv_ambient_secs`, `fmtv_ambient_motion`, plus internal `fmtv_ambient_cache`, `fmtv_ambient_calls`, `fmtv_ambient_pause`, `fmtv_ambient_pinged`.
- Defaults: idle 3 minutes, ambient On, photo duration 90 s, motion Ken Burns, key empty.
- Unsplash budget: own cap 40 API calls per rolling hour; download pings only while fewer than 30 calls in the last hour; each photo pinged at most once; one refresh is 5 calls of `count=30` (one per theme); refresh at most every 12 hours or when fewer than 20 photos are cached; pause fetching for one hour on 403/429 or when `X-Ratelimit-Remaining` is below 5.
- Photo credit text is exactly `Photo by NAME on Unsplash`, shown inside the clock wrapper so it moves with the clock.
- Every new UI string exists in all four dictionaries (`pt`, `es`, `de`, `fr`) of `I18N`; the dictionaries must keep identical key sets.
- Ken Burns: scale 1.06 to 1.14, drift at most 2.5% of the photo size; Drift only: constant scale 1.06. Performance mode (`state.perfMode === 'high'`) forces no motion.
- `docs/index.html` must stay a verbatim copy of `app/index.html` (`python scripts/sync_docs.py`); CI checks it.
- Work only on local branch `feature/ambient-screensaver`. Do not push or merge. Do not commit `dist/*.ipk`.
- Commit messages end with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

**Command conventions** (PowerShell, from `C:\Users\97254\Downloads\FreeMyTvWebOS`):

- Browser test (`TEST`):
  `$env:PYTHONUTF8='1'; python scripts/browser_test.py --chrome 'C:\Program Files\Google\Chrome\Application\chrome.exe'`
  (`PYTHONUTF8=1` works around a Windows text-decoding crash in the repo's test script.)
- Repo checks (`CHECK`): `python scripts/sync_docs.py; python scripts/check.py`
- ES5 check (`ES5`):
  `python scripts/check.py --extract-js "$env:TEMP\app.js"; npx --yes es-check@7.2.1 es5 "$env:TEMP\app.js"`

Baseline before starting: `TEST` prints `[+] browser tests passed` and `CHECK` prints `[+] all checks passed`.

---

## File Structure

- Modify `app/index.html`: state fields, Customize-modal markup and handlers, translations, helper/fetch/render code, screensaver markup and CSS, idle-time wiring.
- Modify `docs/index.html`: regenerated copy via `scripts/sync_docs.py` (never hand-edit).
- Modify `scripts/browser_test.py`: probe assertions for helpers, defaults and translations; a scenario script with a stubbed `fetch`.
- Modify `README.md`, `ROADMAP.md`: document the shipped behavior.

---

### Task 1: Pure helpers (dim, budget, photo URL, photo shape)

**Files:**
- Modify: `scripts/browser_test.py` (probe and main check)
- Modify: `app/index.html` (new helper block above `// --- OLED-Safe Idle Screensaver ---`)

**Interfaces:**
- Produces (globals): `AMBIENT_THEMES` (array of 5 strings), `AMBIENT_HOUR_MS` (3600000), `AMBIENT_MAX_CALLS` (40), `AMBIENT_PING_CAP` (30), `ambientDim(color) -> number`, `ambientBudgetAllows(log, now, limit) -> boolean`, `ambientPhotoUrl(raw, screenWidth) -> string`, `ambientShape(unsplashPhoto) -> {id, raw, color, name, dl} | null`.

- [ ] **Step 1: Add failing probe assertions**

In `scripts/browser_test.py`, replace this exact text inside `PROBE`:

```
  var pre = document.createElement('pre');
  pre.id = '__result';
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}, 1500);
```

with:

```
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
```

Then in `main()`, replace this exact text:

```
                if result["missing"]:
                    failures.append(f"strings without translations: {result['missing']}")
```

with:

```
                if result["missing"]:
                    failures.append(f"strings without translations: {result['missing']}")
                if result["ambient"]:
                    failures.append(f"ambient checks: {result['ambient']}")
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL. Output contains `[!] ambient checks: ['ambientDim missing', 'ambientBudgetAllows missing', 'ambientPhotoUrl missing', 'ambientShape missing']` and ends with `[!] 1 problem(s)`.

- [ ] **Step 3: Add the helpers**

In `app/index.html`, replace this exact line:

```
        // --- OLED-Safe Idle Screensaver ---
```

with:

```
        // --- Ambient (Unsplash) screensaver: pure helpers ---
        var AMBIENT_THEMES = ['night sky stars', 'aurora', 'dark mountains night', 'aerial earth', 'forest fog'];
        var AMBIENT_HOUR_MS = 3600000;
        var AMBIENT_MAX_CALLS = 40; // our own cap inside Unsplash's 50 requests per hour
        var AMBIENT_PING_CAP = 30;  // download pings stop here, keeping 10 calls for refreshes

        // Opacity for a photo from its average colour: dark photos 0.55, white 0.25.
        function ambientDim(color) {
            var lum = 0.5;
            var m = /^#?([0-9a-f]{6})$/i.exec(color || '');
            if (m) {
                var n = parseInt(m[1], 16);
                lum = (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
            }
            return Math.max(0.25, Math.min(0.55, Math.round((0.55 - lum * 0.3) * 100) / 100));
        }

        // log = timestamps (ms) of earlier calls; true while fewer than `limit` happened in the last hour.
        function ambientBudgetAllows(log, now, limit) {
            var recent = 0;
            for (var i = 0; i < log.length; i++) {
                if (log[i] > now - AMBIENT_HOUR_MS) recent++;
            }
            return recent < limit;
        }

        function ambientPhotoUrl(raw, screenWidth) {
            return raw + (raw.indexOf('?') === -1 ? '?' : '&') + 'w=' + (screenWidth >= 3840 ? 3840 : 1920) + '&q=70&fm=jpg';
        }

        // The few fields we keep from an Unsplash photo, or null when one is missing.
        function ambientShape(p) {
            if (!p || !p.id || !p.urls || !p.urls.raw || !p.user || !p.user.name || !p.links || !p.links.download_location) return null;
            return { id: p.id, raw: p.urls.raw, color: p.color || '', name: p.user.name, dl: p.links.download_location };
        }

        // --- OLED-Safe Idle Screensaver ---
```

- [ ] **Step 4: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed`.
Run `ES5`. Expected: `No errors found` style success from es-check (exit code 0).
Run `CHECK`. Expected: `[+] updated docs/index.html` then `[+] all checks passed`.

- [ ] **Step 5: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: ambient screensaver pure helpers with tests

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Settings, translations and configurable idle time

**Files:**
- Modify: `scripts/browser_test.py` (probe assertions)
- Modify: `app/index.html` (state, modal markup, open/reset/save handlers, idle wiring, four dictionaries)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `state.idleMins` (string, default `'3'`), `state.unsplashKey` (default `''`), `state.ambient` (default `'on'`), `state.ambientSecs` (default `'90'`), `state.ambientMotion` (default `'kenburns'`); element ids `cfgIdleMins`, `cfgAmbient`, `cfgAmbientSecs`, `cfgAmbientMotion`, `cfgUnsplashKey`; `idleTimeoutMs() -> number`; a local variable `previousUnsplashKey` in the save handler (used in Task 3).

- [ ] **Step 1: Add failing probe assertions**

In `scripts/browser_test.py`, replace this exact text:

```
  var pre = document.createElement('pre');
  pre.id = '__result';
```

with:

```
  eq('state ambient', state.ambient, 'on');
  eq('state secs', state.ambientSecs, '90');
  eq('state motion', state.ambientMotion, 'kenburns');
  eq('state idle', state.idleMins, '3');
  eq('state key', state.unsplashKey, '');
  if (need('idleTimeoutMs')) {
    var keepIdle = state.idleMins;
    state.idleMins = '10';
    eq('idle 10', idleTimeoutMs(), 600000);
    state.idleMins = 'x';
    eq('idle bad', idleTimeoutMs(), 180000);
    state.idleMins = keepIdle;
  }
  ['cfgIdleMins', 'cfgAmbient', 'cfgAmbientSecs', 'cfgAmbientMotion', 'cfgUnsplashKey'].forEach(function (id) {
    if (!document.getElementById(id)) out.ambient.push('missing #' + id);
  });
  ['Screensaver Starts After', '1 minute', '3 minutes', '5 minutes', '10 minutes', '30 minutes',
   'Ambient Photo Screensaver', 'Off', 'Photo Duration', '30 seconds', '90 seconds', 'Photo Motion',
   'Ken Burns (zoom & drift)', 'Drift only', 'None', 'Unsplash Access Key (Optional)',
   'Optional for photo screensaver', 'Photo by %s on Unsplash'].forEach(function (k) {
    if (!Object.prototype.hasOwnProperty.call(I18N.pt, k)) out.ambient.push('no translation: ' + k);
  });
  var pre = document.createElement('pre');
  pre.id = '__result';
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL. The `ambient checks:` line lists `state ambient: got undefined want "on"`, `idleTimeoutMs missing`, `missing #cfgIdleMins` and the `no translation:` entries.

- [ ] **Step 3: Add the state fields**

In `app/index.html`, replace this exact line:

```
            textSize: localStorage.getItem('fmtv_text_size') || 'normal',
```

with:

```
            textSize: localStorage.getItem('fmtv_text_size') || 'normal',
            idleMins: localStorage.getItem('fmtv_idle_mins') || '3',
            unsplashKey: localStorage.getItem('fmtv_unsplash_key') || '',
            ambient: localStorage.getItem('fmtv_ambient') || 'on',
            ambientSecs: localStorage.getItem('fmtv_ambient_secs') || '90',
            ambientMotion: localStorage.getItem('fmtv_ambient_motion') || 'kenburns',
```

- [ ] **Step 4: Add the modal controls**

Replace this exact text:

```
                        <input type="text" class="field-input modal-nav" id="cfgTmdbKey" placeholder="Optional for TMDB Trending">
                    </div>
                </div>
```

with:

```
                        <input type="text" class="field-input modal-nav" id="cfgTmdbKey" placeholder="Optional for TMDB Trending">
                    </div>
                </div>
                <div class="settings-row" style="margin-top: 14px;">
                    <div class="field-group">
                        <label>Screensaver Starts After</label>
                        <select class="field-input modal-nav" id="cfgIdleMins">
                            <option value="1">1 minute</option>
                            <option value="3">3 minutes</option>
                            <option value="5">5 minutes</option>
                            <option value="10">10 minutes</option>
                            <option value="30">30 minutes</option>
                        </select>
                    </div>
                    <div class="field-group">
                        <label>Ambient Photo Screensaver</label>
                        <select class="field-input modal-nav" id="cfgAmbient">
                            <option value="on">On</option>
                            <option value="off">Off</option>
                        </select>
                    </div>
                    <div class="field-group">
                        <label>Photo Duration</label>
                        <select class="field-input modal-nav" id="cfgAmbientSecs">
                            <option value="30">30 seconds</option>
                            <option value="90">90 seconds</option>
                            <option value="300">5 minutes</option>
                        </select>
                    </div>
                    <div class="field-group">
                        <label>Photo Motion</label>
                        <select class="field-input modal-nav" id="cfgAmbientMotion">
                            <option value="kenburns">Ken Burns (zoom &amp; drift)</option>
                            <option value="drift">Drift only</option>
                            <option value="none">None</option>
                        </select>
                    </div>
                    <div class="field-group" style="grid-column: span 2;">
                        <label>Unsplash Access Key (Optional)</label>
                        <input type="text" class="field-input modal-nav" id="cfgUnsplashKey" placeholder="Optional for photo screensaver">
                    </div>
                </div>
```

- [ ] **Step 5: Wire open, reset and save**

Open handler: replace `            document.getElementById('cfgTmdbKey').value = state.tmdbKey;` with:

```
            document.getElementById('cfgTmdbKey').value = state.tmdbKey;
            document.getElementById('cfgIdleMins').value = state.idleMins;
            document.getElementById('cfgAmbient').value = state.ambient;
            document.getElementById('cfgAmbientSecs').value = state.ambientSecs;
            document.getElementById('cfgAmbientMotion').value = state.ambientMotion;
            document.getElementById('cfgUnsplashKey').value = state.unsplashKey;
```

Reset handler: replace `            document.getElementById('cfgTmdbKey').value = '';` with:

```
            document.getElementById('cfgTmdbKey').value = '';
            document.getElementById('cfgIdleMins').value = '3';
            document.getElementById('cfgAmbient').value = 'on';
            document.getElementById('cfgAmbientSecs').value = '90';
            document.getElementById('cfgAmbientMotion').value = 'kenburns';
            document.getElementById('cfgUnsplashKey').value = '';
```

Save handler: replace `            state.tmdbKey = document.getElementById('cfgTmdbKey').value.trim();` with:

```
            state.tmdbKey = document.getElementById('cfgTmdbKey').value.trim();
            var previousUnsplashKey = state.unsplashKey;
            state.idleMins = document.getElementById('cfgIdleMins').value;
            state.ambient = document.getElementById('cfgAmbient').value;
            state.ambientSecs = document.getElementById('cfgAmbientSecs').value;
            state.ambientMotion = document.getElementById('cfgAmbientMotion').value;
            state.unsplashKey = document.getElementById('cfgUnsplashKey').value.trim();
```

and replace `            localStorage.setItem('fmtv_tmdb_key', state.tmdbKey);` with:

```
            localStorage.setItem('fmtv_tmdb_key', state.tmdbKey);
            localStorage.setItem('fmtv_idle_mins', state.idleMins);
            localStorage.setItem('fmtv_ambient', state.ambient);
            localStorage.setItem('fmtv_ambient_secs', state.ambientSecs);
            localStorage.setItem('fmtv_ambient_motion', state.ambientMotion);
            localStorage.setItem('fmtv_unsplash_key', state.unsplashKey);
```

- [ ] **Step 6: Make the idle time configurable**

Replace this exact line:

```
        var IDLE_TIMEOUT_MS = 3 * 60 * 1000;
```

with:

```
        function idleTimeoutMs() {
            var mins = parseInt(state.idleMins, 10);
            return (mins > 0 ? mins : 3) * 60 * 1000;
        }
```

and replace `Date.now() - lastActivity > IDLE_TIMEOUT_MS` with `Date.now() - lastActivity > idleTimeoutMs()`.

- [ ] **Step 7: Add the translations**

In each language, replace the exact `TMDB API Key (Optional)` entry below with itself followed by the new entries (the new entries start on a new line indented 16 spaces).

Portuguese: replace `'TMDB API Key (Optional)': 'Chave da API TMDB (Opcional)',` with:

```
'TMDB API Key (Optional)': 'Chave da API TMDB (Opcional)',
                'Screensaver Starts After': 'Protetor de Tela Inicia Após', '1 minute': '1 minuto', '3 minutes': '3 minutos', '5 minutes': '5 minutos', '10 minutes': '10 minutos', '30 minutes': '30 minutos',
                'Ambient Photo Screensaver': 'Protetor de Tela com Fotos', 'Off': 'Desligado', 'Photo Duration': 'Duração da Foto', '30 seconds': '30 segundos', '90 seconds': '90 segundos',
                'Photo Motion': 'Movimento da Foto', 'Ken Burns (zoom & drift)': 'Ken Burns (zoom e deslize)', 'Drift only': 'Só deslize', 'None': 'Nenhum',
                'Unsplash Access Key (Optional)': 'Chave de Acesso Unsplash (Opcional)', 'Optional for photo screensaver': 'Opcional para o protetor de fotos', 'Photo by %s on Unsplash': 'Foto de %s no Unsplash',
```

Spanish: replace `'TMDB API Key (Optional)': 'Clave API de TMDB (Opcional)',` with:

```
'TMDB API Key (Optional)': 'Clave API de TMDB (Opcional)',
                'Screensaver Starts After': 'El Protector de Pantalla Inicia Tras', '1 minute': '1 minuto', '3 minutes': '3 minutos', '5 minutes': '5 minutos', '10 minutes': '10 minutos', '30 minutes': '30 minutos',
                'Ambient Photo Screensaver': 'Protector de Pantalla con Fotos', 'Off': 'Desactivado', 'Photo Duration': 'Duración de la Foto', '30 seconds': '30 segundos', '90 seconds': '90 segundos',
                'Photo Motion': 'Movimiento de la Foto', 'Ken Burns (zoom & drift)': 'Ken Burns (zoom y desplazamiento)', 'Drift only': 'Solo desplazamiento', 'None': 'Ninguno',
                'Unsplash Access Key (Optional)': 'Clave de acceso de Unsplash (Opcional)', 'Optional for photo screensaver': 'Opcional para el protector con fotos', 'Photo by %s on Unsplash': 'Foto de %s en Unsplash',
```

German: replace `'TMDB API Key (Optional)': 'TMDB-API-Schlüssel (optional)',` with:

```
'TMDB API Key (Optional)': 'TMDB-API-Schlüssel (optional)',
                'Screensaver Starts After': 'Bildschirmschoner startet nach', '1 minute': '1 Minute', '3 minutes': '3 Minuten', '5 minutes': '5 Minuten', '10 minutes': '10 Minuten', '30 minutes': '30 Minuten',
                'Ambient Photo Screensaver': 'Foto-Bildschirmschoner', 'Off': 'Aus', 'Photo Duration': 'Fotodauer', '30 seconds': '30 Sekunden', '90 seconds': '90 Sekunden',
                'Photo Motion': 'Fotobewegung', 'Ken Burns (zoom & drift)': 'Ken Burns (Zoom & Drift)', 'Drift only': 'Nur Drift', 'None': 'Keine',
                'Unsplash Access Key (Optional)': 'Unsplash-Zugriffsschlüssel (optional)', 'Optional for photo screensaver': 'Optional für den Foto-Bildschirmschoner', 'Photo by %s on Unsplash': 'Foto von %s auf Unsplash',
```

French: replace `'TMDB API Key (Optional)': 'Clé API TMDB (Facultatif)',` with:

```
'TMDB API Key (Optional)': 'Clé API TMDB (Facultatif)',
                'Screensaver Starts After': 'Écran de veille après', '1 minute': '1 minute', '3 minutes': '3 minutes', '5 minutes': '5 minutes', '10 minutes': '10 minutes', '30 minutes': '30 minutes',
                'Ambient Photo Screensaver': 'Écran de veille photo', 'Off': 'Désactivé', 'Photo Duration': 'Durée de la photo', '30 seconds': '30 secondes', '90 seconds': '90 secondes',
                'Photo Motion': 'Mouvement de la photo', 'Ken Burns (zoom & drift)': 'Ken Burns (zoom et dérive)', 'Drift only': 'Dérive seule', 'None': 'Aucun',
                'Unsplash Access Key (Optional)': 'Clé d’accès Unsplash (Facultatif)', 'Optional for photo screensaver': 'Facultatif pour l’écran de veille photo', 'Photo by %s on Unsplash': 'Photo de %s sur Unsplash',
```

- [ ] **Step 8: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed` (all five languages `ok`).
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed`.

- [ ] **Step 9: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: configurable screensaver idle time and ambient settings

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Unsplash fetching, cache and rate-limit budget

**Files:**
- Modify: `scripts/browser_test.py` (scenario script, harness wiring)
- Modify: `app/index.html` (fetch/cache module, schedule, save-handler hook)

**Interfaces:**
- Consumes: `ambientShape`, `ambientBudgetAllows`, `AMBIENT_THEMES`, `AMBIENT_HOUR_MS`, `AMBIENT_MAX_CALLS` (Task 1); `state.unsplashKey`, `state.ambient` and `previousUnsplashKey` (Task 2).
- Produces: `ambientRead(key, fallback) -> value`, `ambientCalls() -> number[]`, `ambientPaused() -> boolean`, `ambientApi(pathOrUrl, cap, done(err, json))`, `ambientRefresh(force)`; cache in `localStorage['fmtv_ambient_cache']` as `{photos: [{id, raw, color, name, dl}], at: ms}`.

- [ ] **Step 1: Add the failing scenario harness**

In `scripts/browser_test.py`, add this constant directly after the `PROBE = r"""..."""` block (before `ERROR_HOOK`):

````python
# Drives the app with a stubbed fetch and reports into <pre id="__scenario">.
SCENARIO = r"""
setTimeout(function () {
  var fails = [], steps = [];
  function eq(name, got, want) {
    if (got !== want) fails.push(name + ': got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want));
  }
  function write() {
    var pre = document.createElement('pre');
    pre.id = '__scenario';
    pre.textContent = JSON.stringify({ fails: fails });
    document.body.appendChild(pre);
  }
  function reset() {
    ['fmtv_ambient_cache', 'fmtv_ambient_calls', 'fmtv_ambient_pause', 'fmtv_ambient_pinged'].forEach(function (k) {
      localStorage.removeItem(k);
    });
  }
  function fakeFetch(status, remaining, calls) {
    return function (url, opts) {
      calls.push({ url: url, auth: opts && opts.headers && opts.headers.Authorization });
      var n = calls.length, list = [], i;
      for (i = 0; i < 30; i++) {
        list.push({ id: 'p' + n + '_' + i, color: '#101020', urls: { raw: 'assets/icon.png' }, user: { name: 'Ann' },
          links: { download_location: 'https://api.unsplash.com/photos/p' + n + '_' + i + '/download' } });
      }
      return Promise.resolve({ status: status, ok: status === 200, headers: { get: function () { return remaining; } },
        json: function () { return Promise.resolve(list); } });
    };
  }
  function cacheSize() {
    var c = JSON.parse(localStorage.getItem('fmtv_ambient_cache') || 'null');
    return c ? c.photos.length : null;
  }
  if (typeof ambientRefresh !== 'function') { fails.push('ambientRefresh missing'); write(); return; }

  steps.push(function (done) { // a normal refresh: 5 themes x 30 photos
    reset(); state.unsplashKey = 'test-key'; state.ambient = 'on';
    var calls = []; window.fetch = fakeFetch(200, '49', calls);
    ambientRefresh(true);
    setTimeout(function () {
      eq('refresh calls', calls.length, 5);
      eq('refresh auth', calls[0] && calls[0].auth, 'Client-ID test-key');
      eq('refresh url', !!calls[0] && calls[0].url.indexOf('https://api.unsplash.com/photos/random?count=30&orientation=landscape&content_filter=high&query=') === 0, true);
      eq('refresh cache', cacheSize(), 150);
      eq('refresh log', JSON.parse(localStorage.getItem('fmtv_ambient_calls')).length, 5);
      done();
    }, 400);
  });
  steps.push(function (done) { // 403 pauses fetching and keeps the old cache untouched
    reset(); var calls = []; window.fetch = fakeFetch(403, null, calls);
    ambientRefresh(true);
    setTimeout(function () {
      eq('403 calls', calls.length, 1);
      eq('403 cache', cacheSize(), null);
      eq('403 paused', parseInt(localStorage.getItem('fmtv_ambient_pause'), 10) > Date.now(), true);
      ambientRefresh(true);
      setTimeout(function () { eq('403 stays paused', calls.length, 1); done(); }, 200);
    }, 300);
  });
  steps.push(function (done) { // low X-Ratelimit-Remaining keeps the data but stops further calls
    reset(); var calls = []; window.fetch = fakeFetch(200, '3', calls);
    ambientRefresh(true);
    setTimeout(function () {
      eq('low calls', calls.length, 1);
      eq('low cache', cacheSize(), 30);
      eq('low paused', parseInt(localStorage.getItem('fmtv_ambient_pause'), 10) > Date.now(), true);
      done();
    }, 300);
  });
  steps.push(function (done) { // our own hourly cap of 40 calls
    reset(); var calls = [], log = [], i;
    for (i = 0; i < 40; i++) log.push(Date.now() - 1000);
    localStorage.setItem('fmtv_ambient_calls', JSON.stringify(log));
    window.fetch = fakeFetch(200, '49', calls);
    ambientRefresh(true);
    setTimeout(function () { eq('cap calls', calls.length, 0); done(); }, 200);
  });
  steps.push(function (done) { // a fresh, big-enough cache is not refreshed unless forced
    reset(); var calls = [], photos = [], i;
    for (i = 0; i < 150; i++) photos.push({ id: 'c' + i, raw: 'assets/icon.png', color: '#000000', name: 'Ann', dl: 'https://api.unsplash.com/photos/c' + i + '/download' });
    localStorage.setItem('fmtv_ambient_cache', JSON.stringify({ photos: photos, at: Date.now() }));
    window.fetch = fakeFetch(200, '49', calls);
    ambientRefresh(false);
    setTimeout(function () { eq('fresh calls', calls.length, 0); done(); }, 200);
  });
  steps.push(function (done) { // no key, no calls
    reset(); state.unsplashKey = ''; var calls = []; window.fetch = fakeFetch(200, '49', calls);
    ambientRefresh(true);
    setTimeout(function () { eq('nokey calls', calls.length, 0); done(); }, 200);
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
    steps[i](function () { setTimeout(function () { run(i + 1); }, 100); });
  })(0);
}, 2000);
"""
````

Then replace this exact text in `run_language`:

```
    html = html.replace("</body>", f"<script>{PROBE}</script></body>")
```

with:

```
    html = html.replace("</body>", f"<script>{PROBE}</script><script>{SCENARIO}</script></body>")
```

replace `"--virtual-time-budget=6000"` with `"--virtual-time-budget=15000"`, and replace this exact text:

```
    import html as htmllib
    return json.loads(htmllib.unescape(m.group(1))), ""
```

with:

```
    import html as htmllib
    result = json.loads(htmllib.unescape(m.group(1)))
    m2 = re.search(r'<pre id="__scenario">(.*?)</pre>', res.stdout, re.S)
    result["scenario"] = json.loads(htmllib.unescape(m2.group(1))) if m2 else None
    return result, ""
```

and in `main()` replace this exact text:

```
                if result["ambient"]:
                    failures.append(f"ambient checks: {result['ambient']}")
```

with:

```
                if result["ambient"]:
                    failures.append(f"ambient checks: {result['ambient']}")
                if result["scenario"] is None:
                    failures.append("ambient scenario did not finish")
                elif result["scenario"]["fails"]:
                    failures.append(f"ambient scenario: {result['scenario']['fails']}")
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL with `[!] ambient scenario: ['ambientRefresh missing']` and `[!] 1 problem(s)`.

- [ ] **Step 3: Implement the fetch/cache module**

In `app/index.html`, replace this exact line:

```
        // --- OLED-Safe Idle Screensaver ---
```

with:

```
        // --- Ambient (Unsplash) screensaver: fetching, cache and call budget ---
        var AMBIENT_REFRESH_MS = 12 * AMBIENT_HOUR_MS;
        var AMBIENT_MIN_CACHED = 20;
        var AMBIENT_MIN_REMAINING = 5;
        var ambientRefreshing = false;

        function ambientRead(key, fallback) {
            try {
                var raw = localStorage.getItem(key);
                return raw ? JSON.parse(raw) : fallback;
            } catch (e) {
                return fallback;
            }
        }

        // Timestamps of API calls made in the last hour.
        function ambientCalls() {
            var now = Date.now(), log = ambientRead('fmtv_ambient_calls', []), recent = [];
            for (var i = 0; i < log.length; i++) {
                if (log[i] > now - AMBIENT_HOUR_MS) recent.push(log[i]);
            }
            return recent;
        }

        function ambientPaused() {
            return Date.now() < (parseInt(localStorage.getItem('fmtv_ambient_pause'), 10) || 0);
        }

        // GET an Unsplash API path (or a full URL); done(err, json). Every call is logged against the hourly cap.
        function ambientApi(pathOrUrl, cap, done) {
            var now = Date.now(), log = ambientCalls();
            if (typeof fetch !== 'function' || !state.unsplashKey || ambientPaused() || !ambientBudgetAllows(log, now, cap)) {
                done(new Error('blocked'));
                return;
            }
            log.push(now);
            localStorage.setItem('fmtv_ambient_calls', JSON.stringify(log));
            var url = pathOrUrl.indexOf('http') === 0 ? pathOrUrl : 'https://api.unsplash.com' + pathOrUrl;
            fetch(url, { headers: { 'Authorization': 'Client-ID ' + state.unsplashKey, 'Accept-Version': 'v1' } }).then(function(res) {
                var remaining = parseInt(res.headers.get('X-Ratelimit-Remaining'), 10);
                if (res.status === 403 || res.status === 429 || remaining < AMBIENT_MIN_REMAINING) {
                    localStorage.setItem('fmtv_ambient_pause', String(Date.now() + AMBIENT_HOUR_MS));
                }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            }).then(function(data) { done(null, data); }, function(err) { done(err); });
        }

        // One random-30 call per theme (about 150 photos). Keeps the old cache unless at least 20 photos came back.
        function ambientRefresh(force) {
            if (ambientRefreshing || state.ambient !== 'on' || !state.unsplashKey || typeof fetch !== 'function') return;
            var cache = ambientRead('fmtv_ambient_cache', null);
            if (!force && cache && cache.photos && cache.photos.length >= AMBIENT_MIN_CACHED && Date.now() - cache.at < AMBIENT_REFRESH_MS) return;
            ambientRefreshing = true;
            var photos = [], seen = {}, step = 0;

            function finish() {
                ambientRefreshing = false;
                if (photos.length >= AMBIENT_MIN_CACHED) {
                    localStorage.setItem('fmtv_ambient_cache', JSON.stringify({ photos: photos, at: Date.now() }));
                }
            }

            function next() {
                if (step >= AMBIENT_THEMES.length) { finish(); return; }
                var theme = AMBIENT_THEMES[step++];
                ambientApi('/photos/random?count=30&orientation=landscape&content_filter=high&query=' + encodeURIComponent(theme), AMBIENT_MAX_CALLS, function(err, list) {
                    if (err || !list || !list.length) { finish(); return; }
                    for (var i = 0; i < list.length; i++) {
                        var s = ambientShape(list[i]);
                        if (s && !seen[s.id]) { seen[s.id] = 1; photos.push(s); }
                    }
                    next();
                });
            }
            next();
        }

        // --- OLED-Safe Idle Screensaver ---
```

- [ ] **Step 4: Schedule the refresh and hook the save handler**

Replace this exact line:

```
        document.getElementById('closeModalBtn').addEventListener('click', closeSettingsModal);
```

with:

```
        // Refresh the photo cache in the background (never from inside the screensaver).
        setTimeout(function() { ambientRefresh(false); }, 20000);
        setInterval(function() { if (!screensaverOn) ambientRefresh(false); }, 30 * 60 * 1000);

        document.getElementById('closeModalBtn').addEventListener('click', closeSettingsModal);
```

In the save handler, replace this exact text:

```
            fetchTrendingPicks();
            closeSettingsModal();
            showToast(t('Saved & Applied!'));
```

with:

```
            fetchTrendingPicks();
            if (previousUnsplashKey !== state.unsplashKey) {
                localStorage.removeItem('fmtv_ambient_cache');
                localStorage.removeItem('fmtv_ambient_pause');
            }
            ambientRefresh(false);
            closeSettingsModal();
            showToast(t('Saved & Applied!'));
```

- [ ] **Step 5: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed`.
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed`.

- [ ] **Step 6: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: Unsplash photo cache with hourly call budget

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Render the ambient photo layer

**Files:**
- Modify: `scripts/browser_test.py` (extra scenario steps)
- Modify: `app/index.html` (screensaver markup, CSS, render module, enter/exit hooks)

**Interfaces:**
- Consumes: everything from Tasks 1-3 (`ambientDim`, `ambientPhotoUrl`, `ambientRead`, `ambientApi`, `AMBIENT_PING_CAP`, `state.ambient`, `state.unsplashKey`, `state.ambientSecs`, `state.ambientMotion`, `state.perfMode`, `screensaverOn`).
- Produces: `ambientReady() -> boolean`, `ambientStart()`, `ambientStop()`, `ambientShow()`; overlay class `ambient`; elements `ssPhotoA`, `ssPhotoB`, `screensaverCredit`.

- [ ] **Step 1: Add failing scenario steps**

In `scripts/browser_test.py`, inside `SCENARIO`, replace this exact text:

```
  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

with:

```
  if (typeof ambientStart !== 'function') { fails.push('ambientStart missing'); write(); return; }
  var overlay = document.getElementById('screensaverOverlay');
  function isAmbient() { return /\bambient\b/.test(overlay.className); }
  function seedCache() {
    reset();
    localStorage.setItem('fmtv_ambient_cache', JSON.stringify({ at: Date.now(), photos: [
      { id: 'z1', raw: 'assets/icon.png', color: '#000000', name: 'Ann', dl: 'https://api.unsplash.com/photos/z1/download' }] }));
  }
  window.ambientPhotoUrl = function (raw) { return raw; }; // load the local test asset as-is

  steps.push(function (done) { // ambient shows a photo, the credit, and pings the download endpoint once
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'kenburns'; state.perfMode = 'standard';
    var calls = []; window.fetch = fakeFetch(200, '49', calls);
    enterScreensaver();
    setTimeout(function () {
      var a = document.getElementById('ssPhotoA').style.opacity, b = document.getElementById('ssPhotoB').style.opacity;
      eq('ambient class', isAmbient(), true);
      eq('credit', document.getElementById('screensaverCredit').textContent, t('Photo by %s on Unsplash', 'Ann'));
      eq('photo visible', a === '0.55' || b === '0.55', true);
      eq('ping once', calls.filter(function (c) { return c.url.indexOf('/photos/z1/download') !== -1; }).length, 1);
      exitScreensaver();
      eq('ambient removed', isAmbient(), false);
      eq('credit cleared', document.getElementById('screensaverCredit').textContent, '');
      done();
    }, 500);
  });
  steps.push(function (done) { // no key falls back to the black clock
    seedCache(); state.ambient = 'on'; state.unsplashKey = '';
    enterScreensaver();
    setTimeout(function () { eq('nokey ambient', isAmbient(), false); exitScreensaver(); done(); }, 200);
  });
  steps.push(function (done) { // Off falls back to the black clock
    seedCache(); state.ambient = 'off'; state.unsplashKey = 'k';
    enterScreensaver();
    setTimeout(function () { eq('off ambient', isAmbient(), false); exitScreensaver(); done(); }, 200);
  });
  steps.push(function (done) { // an empty cache falls back to the black clock
    reset(); state.ambient = 'on'; state.unsplashKey = 'k';
    enterScreensaver();
    setTimeout(function () { eq('empty ambient', isAmbient(), false); exitScreensaver(); done(); }, 200);
  });
  steps.push(function (done) { // motion None and performance mode both leave the photo still
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none'; state.perfMode = 'standard';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var img = document.getElementById('ssPhotoB');
      eq('none transform', img.style.transform, 'translate(0%, 0%) scale(1.06)');
      exitScreensaver();
      state.ambientMotion = 'kenburns'; state.perfMode = 'high';
      enterScreensaver();
      setTimeout(function () {
        var other = document.getElementById('ssPhotoB');
        eq('perf transform', other.style.transform, 'translate(0%, 0%) scale(1.06)');
        exitScreensaver();
        state.perfMode = 'standard';
        done();
      }, 400);
    }, 400);
  });
  steps.push(function (done) { // Ken Burns zooms and drifts within 2.5%
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'kenburns';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var shown = document.getElementById('ssPhotoA').style.opacity === '0.55' ? document.getElementById('ssPhotoA') : document.getElementById('ssPhotoB');
      var m = /translate\((-?[\d.]+)%, (-?[\d.]+)%\) scale\(([\d.]+)\)/.exec(shown.style.transform);
      eq('kb parsed', !!m, true);
      if (m) {
        eq('kb dx', Math.abs(parseFloat(m[1])) <= 2.5, true);
        eq('kb dy', Math.abs(parseFloat(m[2])) <= 2.5, true);
        eq('kb scale', m[3], '1.14');
      }
      exitScreensaver();
      done();
    }, 400);
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL with `[!] ambient scenario: ['ambientStart missing']` (the Task 3 steps still pass) and `[!] 1 problem(s)`.

- [ ] **Step 3: Add the screensaver markup**

In `app/index.html`, replace this exact text:

```
    <div class="screensaver" id="screensaverOverlay">
        <div class="screensaver-clock-wrap" id="screensaverClockWrap">
            <div class="screensaver-clock" id="screensaverClock">20:30</div>
            <div class="screensaver-date" id="screensaverDate">Mon, Oct 19</div>
        </div>
    </div>
```

with:

```
    <div class="screensaver" id="screensaverOverlay">
        <div class="screensaver-photos" id="screensaverPhotos">
            <img class="ss-photo" id="ssPhotoA" alt="">
            <img class="ss-photo" id="ssPhotoB" alt="">
        </div>
        <div class="screensaver-clock-wrap" id="screensaverClockWrap">
            <div class="screensaver-clock" id="screensaverClock">20:30</div>
            <div class="screensaver-date" id="screensaverDate">Mon, Oct 19</div>
            <div class="screensaver-credit" id="screensaverCredit"></div>
        </div>
    </div>
```

- [ ] **Step 4: Add the CSS**

Replace this exact text (end of the stylesheet):

```
            margin-top: 6px;
        }
    </style>
```

with:

```
            margin-top: 6px;
        }

        /* Ambient photo layer: dimmed photos behind the clock; only opacity and transform animate. */
        .screensaver .screensaver-clock-wrap {
            position: relative;
            z-index: 1;
        }

        .screensaver-photos {
            display: none;
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            overflow: hidden;
            background: #000000;
        }

        .screensaver.ambient .screensaver-photos {
            display: block;
        }

        .screensaver-photos:after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: radial-gradient(ellipse at center, rgba(0, 0, 0, 0) 45%, rgba(0, 0, 0, 0.65) 100%);
        }

        .ss-photo {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            opacity: 0;
            will-change: opacity, transform;
        }

        .screensaver-credit {
            font-size: 16px;
            letter-spacing: 1px;
            color: rgba(255, 255, 255, 0.35);
            margin-top: 14px;
        }
    </style>
```

- [ ] **Step 5: Add the render module**

Replace this exact line:

```
        // --- OLED-Safe Idle Screensaver ---
```

with:

```
        // --- Ambient (Unsplash) screensaver: photo layer ---
        var ambientOn = false;
        var ambientTimer = null;
        var ambientPos = 0;
        var ambientFailures = 0;
        var ambientFront = 'ssPhotoA';

        function ambientReady() {
            var cache = ambientRead('fmtv_ambient_cache', null);
            return state.ambient === 'on' && !!state.unsplashKey && !!cache && !!cache.photos && cache.photos.length > 0;
        }

        // Slow zoom and drift (Ken Burns), drift only, or still. Only transform and opacity animate.
        function ambientMove(img, secs) {
            var still = state.ambientMotion === 'none' || state.perfMode === 'high';
            img.style.transition = 'none';
            img.style.transform = 'translate(0%, 0%) scale(1.06)';
            void img.offsetWidth;
            img.style.transition = 'opacity 4s linear' + (still ? '' : ', transform ' + (secs + 4) + 's linear');
            if (still) return;
            var dx = Math.round((Math.random() - 0.5) * 50) / 10; // -2.5 .. 2.5 (% of the photo size)
            var dy = Math.round((Math.random() - 0.5) * 50) / 10;
            var scale = state.ambientMotion === 'drift' ? 1.06 : 1.14;
            img.style.transform = 'translate(' + dx + '%, ' + dy + '%) scale(' + scale + ')';
        }

        // Tell Unsplash once per photo; pings stop while 30+ calls were made in the last hour.
        function ambientPing(p) {
            var pinged = ambientRead('fmtv_ambient_pinged', []);
            if (pinged.indexOf(p.id) !== -1) return;
            pinged.push(p.id);
            localStorage.setItem('fmtv_ambient_pinged', JSON.stringify(pinged.slice(-300)));
            ambientApi(p.dl, AMBIENT_PING_CAP, function() {});
        }

        function ambientShow() {
            var cache = ambientRead('fmtv_ambient_cache', null);
            if (!ambientOn || !cache || !cache.photos || !cache.photos.length) return;
            var p = cache.photos[ambientPos % cache.photos.length];
            ambientPos++;
            var secs = parseInt(state.ambientSecs, 10) || 90;
            var cur = document.getElementById(ambientFront);
            var next = document.getElementById(ambientFront === 'ssPhotoA' ? 'ssPhotoB' : 'ssPhotoA');
            var pre = new Image();
            pre.onload = function() {
                if (!ambientOn) return;
                ambientFailures = 0;
                next.src = pre.src;
                ambientMove(next, secs);
                next.style.opacity = String(ambientDim(p.color));
                cur.style.opacity = '0';
                ambientFront = next.id;
                document.getElementById('screensaverCredit').textContent = t('Photo by %s on Unsplash', p.name);
                ambientPing(p);
            };
            pre.onerror = function() {
                ambientFailures++;
                if (ambientOn && ambientFailures < 5) ambientShow();
            };
            pre.src = ambientPhotoUrl(p.raw, window.screen.width * (window.devicePixelRatio || 1));
        }

        function ambientStart() {
            ambientOn = true;
            ambientFailures = 0;
            ambientFront = 'ssPhotoA'; // the first photo of every run fades in on ssPhotoB
            ambientPos = Math.floor(Math.random() * 1000);
            document.getElementById('screensaverOverlay').classList.add('ambient');
            ambientShow();
            ambientTimer = setInterval(ambientShow, (parseInt(state.ambientSecs, 10) || 90) * 1000);
        }

        function ambientStop() {
            ambientOn = false;
            clearInterval(ambientTimer);
            document.getElementById('screensaverOverlay').classList.remove('ambient');
            ['ssPhotoA', 'ssPhotoB'].forEach(function(id) {
                var img = document.getElementById(id);
                img.style.transition = 'none';
                img.style.opacity = '0';
                img.removeAttribute('src');
            });
            document.getElementById('screensaverCredit').textContent = '';
        }

        // --- OLED-Safe Idle Screensaver ---
```

- [ ] **Step 6: Hook enter and exit**

Replace this exact text:

```
            screensaverOverlay.classList.add('active');
            shiftScreensaverClock();
```

with:

```
            screensaverOverlay.classList.add('active');
            if (ambientReady()) ambientStart();
            shiftScreensaverClock();
```

and replace this exact text:

```
            clearInterval(pixelShiftTimer);
        }
```

with:

```
            clearInterval(pixelShiftTimer);
            ambientStop();
        }
```

- [ ] **Step 7: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed`.
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed`.

- [ ] **Step 8: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: dimmed Ken Burns photo layer behind the screensaver clock

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md` (feature bullet and settings table, English and Portuguese sections)
- Modify: `ROADMAP.md` (v1.3 screensaver bullet)

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1-4.
- Produces: user-facing docs only.

- [ ] **Step 1: Update the English README**

Replace this exact line:

```
- **🌑 OLED-Safe Idle Screensaver.** A pure-black floating clock kicks in after a few minutes idle and gently shifts position to avoid burn-in—dismissed by any key or remote movement.
```

with:

```
- **🌑 OLED-Safe Idle Screensaver.** After the idle time you choose (1 to 30 minutes), a dimmed, slowly moving [Unsplash](https://unsplash.com) night-sky, aurora and landscape photo fades in behind a floating clock that shifts position to avoid burn-in. Without an Unsplash key it is a pure-black floating clock. Dismissed by any key or remote movement.
```

Replace this exact line:

```
| **TMDB API Key** | Paste a free [TMDB API Key](https://www.themoviedb.org/settings/api) for live weekly trending movies & shows, or leave empty to use the built-in zero-key live popular feed. |
```

with:

```
| **TMDB API Key** | Paste a free [TMDB API Key](https://www.themoviedb.org/settings/api) for live weekly trending movies & shows, or leave empty to use the built-in zero-key live popular feed. |
| **Screensaver Starts After** | Idle time before the screensaver starts: 1, 3, 5, 10 or 30 minutes. Applies to the photo and the black-clock screensaver. |
| **Ambient Photo Screensaver** | `On` or `Off`. Photos need an Unsplash key and a TV with `fetch` support (webOS 4 or newer); otherwise the black clock is used. |
| **Photo Duration / Photo Motion** | 30 seconds, 90 seconds or 5 minutes per photo; `Ken Burns (zoom & drift)`, `Drift only` or `None`. High Performance mode always uses no motion. |
| **Unsplash Access Key** | Paste the Access Key of a free [Unsplash developer app](https://unsplash.com/developers) (50 requests per hour). The app makes about 5 calls per refresh, at most every 12 hours, and shows "Photo by NAME on Unsplash". |
```

- [ ] **Step 2: Update the Portuguese README**

Replace this exact line:

```
- **🌑 Screensaver Seguro para OLED.** Um relógio flutuante em tela totalmente preta aparece após alguns minutos parado e muda de posição aos poucos para evitar marcação de imagem — some com qualquer tecla ou movimento do controle.
```

with:

```
- **🌑 Screensaver Seguro para OLED.** Após o tempo parado que você escolher (1 a 30 minutos), uma foto escura e em movimento lento do [Unsplash](https://unsplash.com) aparece atrás de um relógio flutuante que muda de posição para evitar marcação de imagem. Sem chave do Unsplash, é só o relógio em tela preta. Some com qualquer tecla ou movimento do controle.
```

Replace this exact line:

```
| **Chave da API do TMDB** | Cole uma [chave gratuita da API do TMDB](https://www.themoviedb.org/settings/api) para ver filmes e séries em alta da semana ao vivo, ou deixe em branco para usar o feed ao vivo popular embutido (sem necessidade de chave). |
```

with:

```
| **Chave da API do TMDB** | Cole uma [chave gratuita da API do TMDB](https://www.themoviedb.org/settings/api) para ver filmes e séries em alta da semana ao vivo, ou deixe em branco para usar o feed ao vivo popular embutido (sem necessidade de chave). |
| **Protetor de Tela Inicia Após** | Tempo parado antes do protetor de tela: 1, 3, 5, 10 ou 30 minutos. |
| **Protetor de Tela com Fotos** | `Ligado` ou `Desligado`, com duração (30 s, 90 s ou 5 min) e movimento (Ken Burns, só deslize ou nenhum). Precisa de uma chave de acesso do [Unsplash](https://unsplash.com/developers) (50 requisições por hora). |
```

- [ ] **Step 3: Update the roadmap**

In `ROADMAP.md`, replace this exact line:

```
- [x] **Idle Screensaver & Clock Overlay *(landed early, partial)*:** A pure-black, OLED-safe screensaver with a floating clock that pixel-shifts position every ~25s kicks in after 3 minutes idle. The curated 4K photo-backdrop variant is still pending.
```

with:

```
- [x] **Idle Screensaver & Clock Overlay:** An OLED-safe screensaver with a floating clock that pixel-shifts position every ~25s, starting after a configurable idle time (1-30 minutes, default 3). With an Unsplash key it shows dimmed, slowly moving night-sky and landscape photos behind the clock (5 API calls per 12-hour refresh, inside Unsplash's 50 requests per hour); without one it stays pure black.
```

- [ ] **Step 4: Verify and commit**

Run `CHECK`. Expected: `[+] all checks passed`.

```bash
git add README.md ROADMAP.md
git commit -m "docs: document the ambient photo screensaver settings

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Verify on the real TV (manual, nothing committed)

**Files:**
- No source changes. Rebuilds `dist/org.webos.freemytv_1.4.0_all.ipk` locally; do not commit it.

**Interfaces:**
- Consumes: the finished app, the TV at `10.100.102.2` with Developer Mode on, `~/.ssh/webos_tv_rsa_decrypted`, and the LG skill scripts in `C:\Users\97254\.claude\skills\lg-tv-control\scripts` (`LGTV_IP=10.100.102.2`).
- Produces: screenshots in `C:\Users\97254\Downloads` confirming the feature.

- [ ] **Step 1: Get the Unsplash Access Key from the user**

Ask the user for their Unsplash Access Key (registered at unsplash.com/developers). Do not create one or log it in a commit, file or chat summary.

- [ ] **Step 2: Rebuild the package from source and install**

```powershell
Remove-Item 'C:\Users\97254\Downloads\FreeMyTvWebOS\dist\*.ipk'
python 'C:\Users\97254\Downloads\FreeMyTvWebOS\scripts\build.py'
python 'C:\Users\97254\Downloads\FreeMyTvWebOS\scripts\install.py' 10.100.102.2
```

Expected: `[+] SUCCESS! Free My TV is installed and running on your LG TV!`

- [ ] **Step 3: Enter the key and a short idle time**

On the TV open Customize, type the key into "Unsplash Access Key (Optional)", set "Screensaver Starts After" to `1 minute`, then press Save & Apply. (Move with the arrow keys; focus on inputs and dropdowns has no visible highlight, so check with screenshots after each step and type with the skill's `insert_text`.)
Expected: toast "Saved & Applied!". Within about 20 seconds the cache fills (5 API calls).

- [ ] **Step 4: Wait out the idle time and capture the screensaver**

Leave the TV untouched for 70 seconds, then:

```powershell
$env:LGTV_IP='10.100.102.2'; python 'C:\Users\97254\.claude\skills\lg-tv-control\scripts\shot.py' 'C:\Users\97254\Downloads\tv_ambient.jpg'
```

Expected: a dimmed photo with the clock, the date and "Photo by NAME on Unsplash" under it. Take a second screenshot after about 30 seconds and confirm the clock moved.

- [ ] **Step 5: Confirm exit and fallback**

Press any remote key: the screensaver leaves and the home screen shows. Clear the key in Customize, save, wait out the idle time: the screen shows the black clock only.

- [ ] **Step 6: Restore the user's setting**

Set "Screensaver Starts After" back to the user's preferred time (default 3 minutes). Do not commit anything; `git status` should still show only `dist/*.ipk` as modified.
