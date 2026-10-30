# Ambient Extras (photo player, home photos, keep-awake) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Unsplash photos also run behind the home screen (settings switch), and stop LG's own screensaver from covering ours (settings switch), by first generalising the screensaver photo code into a reusable player.

**Architecture:** One `ambientPlayer(cfg)` factory (two `<img>` layers, rotation timer, run counter) is instantiated twice: for the screensaver and for a new full-screen layer behind the dashboard. A small keep-awake module plays a hidden muted canvas-stream video while our screensaver shows. Everything stays in `app/index.html`; tests extend the existing headless-Chrome scenario script.

**Tech Stack:** ES5 JavaScript (Chromium 38 floor on webOS 3.x), HTML/CSS, Python 3 test scripts, headless Chrome, Node (`es-check`).

## Global Constraints

- Source of truth: `docs/superpowers/specs/2026-10-30-ambient-screensaver-design.md`, including its Addendum.
- All app JS is ES5: `var`, `function`, no arrow functions, no `let`/`const`, no template literals, no `async`/`await`. `fetch` and `canvas.captureStream` are only used behind feature checks.
- `localStorage` keys: `fmtv_home_photos` (On/Off, default Off), `fmtv_keep_awake` (On/Off, default On); existing `fmtv_ambient*`, `fmtv_idle_mins`, `fmtv_unsplash_key` stay as they are.
- Home-screen photo opacity is `ambientDim(color)` times 0.55 (rounded to 2 decimals), so a dark photo shows at `0.3`; the screensaver keeps `ambientDim(color)` (`0.55` for dark photos).
- Credit text is exactly `Photo by NAME on Unsplash` via `t('Photo by %s on Unsplash', name)`; the home-screen credit is a small dim line at the bottom-left corner.
- Unsplash budget rules from the spec are unchanged: own cap 40 calls per rolling hour; pings only while fewer than 30 calls in the last hour; each photo pinged once; pause on 403/429 or `X-Ratelimit-Remaining` below 5.
- Every new UI string exists in all four dictionaries (`pt`, `es`, `de`, `fr`) of `I18N`; the key sets must stay identical.
- `docs/index.html` must stay a verbatim copy of `app/index.html` (`python scripts/sync_docs.py`); CI checks it.
- Work only on local branch `feature/ambient-screensaver`. Do not push or merge. Do not commit `dist/*.ipk`.
- Commit messages end with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

**Command conventions** (PowerShell, from `C:\Users\97254\Downloads\FreeMyTvWebOS`):

- Browser test (`TEST`):
  `$env:PYTHONUTF8='1'; python scripts/browser_test.py --chrome 'C:\Program Files\Google\Chrome\Application\chrome.exe'`
- Repo checks (`CHECK`): `python scripts/sync_docs.py; python scripts/check.py`
- ES5 check (`ES5`):
  `python scripts/check.py --extract-js "C:/Users/97254/AppData/Local/Temp/app.js"; npx --yes es-check@7.2.1 es5 "C:/Users/97254/AppData/Local/Temp/app.js"` (es-check needs a forward-slash path)

Baseline before starting (HEAD `9947c47` or later): `TEST` prints `[+] browser tests passed`; `CHECK` prints `[+] all checks passed`.

**Scenario test conventions** (inside the `SCENARIO` string of `scripts/browser_test.py`): new steps go immediately before the line `  (function run(i) {` near the end of the string. Available helpers there: `eq(name, got, want)`, `reset()` (clears the four internal `fmtv_ambient_*` keys), `fakeFetch(status, remaining, calls)`, `cacheSize()`, `seedCache()`, `overlay` (the screensaver element), `isAmbient()`. The scenario already overrides `window.ambientPhotoUrl` to return the raw URL, so photos with `raw: 'assets/icon.png'` load locally. Steps run in order and share page state, so each new step sets the `state.*` values it needs and restores anything it changes.

---

## File Structure

- Modify `app/index.html`: the photo player, the new home layer markup and CSS, keep-awake markup and code, settings controls, handlers, translations.
- Modify `docs/index.html`: regenerated copy (never hand-edit).
- Modify `scripts/browser_test.py`: probe assertions and scenario steps.
- Modify `README.md`, `ROADMAP.md` (Task 4 only).

---

### Task 1: Photo player refactor (fixes the stale-preload race)

**Files:**
- Modify: `scripts/browser_test.py` (new scenario steps)
- Modify: `app/index.html` (render module)

**Interfaces:**
- Consumes: existing `ambientRead`, `ambientDim`, `ambientMove`, `ambientPing`, `ambientPhotoUrl`, `ambientReady`, `state.ambientSecs`, `t()`.
- Produces: `ambientPlayer(cfg) -> player` where `cfg = {a, b, credit, dimScale, secs, onStart, onStop}` (`a`/`b` = ids of the two `<img>`, `credit` = id of the credit element, `dimScale` = number multiplied into `ambientDim`, `secs()` = seconds per photo, `onStart`/`onStop` optional callbacks) and `player = {on, show(), start(), stop()}`; the screensaver instance `screensaverPhotos`; thin wrappers `ambientShow()`, `ambientStart()`, `ambientStop()` that keep their current names and behaviour.

- [ ] **Step 1: Add the failing scenario steps**

In `scripts/browser_test.py`, replace this exact text:

```
  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

with:

```
  function photo(id, name, raw) {
    return { id: id, raw: raw || 'assets/icon.png', color: '#000000', name: name, dl: 'https://api.unsplash.com/photos/' + id + '/download' };
  }
  function seedMany(list) {
    reset();
    localStorage.setItem('fmtv_ambient_cache', JSON.stringify({ at: Date.now(), photos: list }));
  }
  function creditText() { return document.getElementById('screensaverCredit').textContent; }

  steps.push(function (done) { // a late image load from an earlier run must be ignored (stop then quick start)
    seedMany([photo('s1', 'Ann'), photo('s2', 'Bob')]);
    state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none'; state.perfMode = 'standard';
    var calls = []; window.fetch = fakeFetch(200, '49', calls);
    var realRandom = Math.random;
    Math.random = function () { return 0; };      // first run starts at photo 0 (Ann)
    enterScreensaver();
    exitScreensaver();
    Math.random = function () { return 0.001; };  // second run starts at photo 1 (Bob)
    enterScreensaver();
    Math.random = realRandom;
    setTimeout(function () {
      var pings = calls.filter(function (c) { return c.url.indexOf('/download') !== -1; });
      eq('stale pings', pings.length, 1);
      eq('stale ping id', !!pings[0] && pings[0].url.indexOf('/photos/s2/') !== -1, true);
      eq('stale credit', creditText(), t('Photo by %s on Unsplash', 'Bob'));
      exitScreensaver();
      done();
    }, 500);
  });
  steps.push(function (done) { // the A/B photos alternate on each rotation
    seedMany([photo('t1', 'Ann'), photo('t2', 'Bob')]);
    state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var a = document.getElementById('ssPhotoA'), b = document.getElementById('ssPhotoB');
      eq('swap first B', b.style.opacity, '0.55');
      eq('swap first A hidden', a.style.opacity === '' || a.style.opacity === '0', true);
      ambientShow();
      setTimeout(function () {
        eq('swap second A', a.style.opacity, '0.55');
        eq('swap second B', b.style.opacity, '0');
        exitScreensaver();
        done();
      }, 400);
    }, 400);
  });
  steps.push(function (done) { // a photo that fails to load is skipped; src is cleared after exit
    seedMany([photo('u1', 'Bad', 'assets/missing-image.png'), photo('u2', 'Good')]);
    state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none';
    window.fetch = fakeFetch(200, '49', []);
    var realRandom = Math.random;
    Math.random = function () { return 0; };      // starts at the bad photo
    enterScreensaver();
    Math.random = realRandom;
    setTimeout(function () {
      eq('skip credit', creditText(), t('Photo by %s on Unsplash', 'Good'));
      exitScreensaver();
      eq('src cleared A', document.getElementById('ssPhotoA').getAttribute('src'), null);
      eq('src cleared B', document.getElementById('ssPhotoB').getAttribute('src'), null);
      state.ambientMotion = 'kenburns';
      done();
    }, 600);
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL. Output contains `[!] ambient scenario: [...]` including `stale pings: got 2 want 1` (the old code lets the first run's image load fire after the second run started). The A/B swap and skip-on-error steps are regression guards and may already pass.

- [ ] **Step 3: Replace the render module with the player**

In `app/index.html`, find the block that starts at the line `        // --- Ambient (Unsplash) screensaver: photo layer ---` and ends with the closing brace of `function ambientStop() { ... }` (the line just before `        // --- OLED-Safe Idle Screensaver ---`). Keep the three functions `ambientReady`, `ambientMove` and `ambientPing` exactly as they are. Delete the variable declarations (`ambientOn`, `ambientTimer`, `ambientPos`, `ambientFailures`, `ambientFront`) and the old functions `ambientShow`, `ambientStart`, `ambientStop`. Insert the following in place of the deleted parts, keeping this order: the comment line, then the kept `ambientReady`, `ambientMove`, `ambientPing`, then this block:

```
        // One photo layer: two stacked images that crossfade, a rotation timer and a run counter so a late image
        // load from an earlier start/stop cycle is ignored. cfg: a, b = ids of the two <img>; credit = id of the
        // credit element; dimScale multiplies ambientDim(); secs() = seconds per photo; onStart/onStop optional.
        function ambientPlayer(cfg) {
            var player = { on: false, timer: null, pos: 0, failures: 0, front: cfg.a, run: 0 };

            function el(id) { return document.getElementById(id); }

            player.show = function() {
                var cache = ambientRead('fmtv_ambient_cache', null);
                if (!player.on || !cache || !cache.photos || !cache.photos.length) return;
                var photo = cache.photos[player.pos % cache.photos.length];
                player.pos++;
                var run = player.run;
                var cur = el(player.front);
                var next = el(player.front === cfg.a ? cfg.b : cfg.a);
                var pre = new Image();
                pre.onload = function() {
                    if (!player.on || run !== player.run) return;
                    player.failures = 0;
                    next.src = pre.src;
                    ambientMove(next, cfg.secs());
                    next.style.opacity = String(Math.round(ambientDim(photo.color) * cfg.dimScale * 100) / 100);
                    cur.style.opacity = '0';
                    player.front = next.id;
                    el(cfg.credit).textContent = t('Photo by %s on Unsplash', photo.name);
                    ambientPing(photo);
                };
                pre.onerror = function() {
                    if (!player.on || run !== player.run) return;
                    player.failures++;
                    if (player.failures < 5) player.show();
                };
                pre.src = ambientPhotoUrl(photo.raw, window.screen.width * (window.devicePixelRatio || 1));
            };

            player.start = function() {
                player.run++;
                player.on = true;
                player.failures = 0;
                player.front = cfg.a; // the first photo of every run fades in on the second image
                player.pos = Math.floor(Math.random() * 1000);
                if (cfg.onStart) cfg.onStart();
                player.show();
                player.timer = setInterval(player.show, cfg.secs() * 1000);
            };

            player.stop = function() {
                player.run++;
                player.on = false;
                clearInterval(player.timer);
                if (cfg.onStop) cfg.onStop();
                [cfg.a, cfg.b].forEach(function(id) {
                    var img = el(id);
                    img.style.transition = 'none';
                    img.style.opacity = '0';
                    img.removeAttribute('src');
                });
                el(cfg.credit).textContent = '';
            };

            return player;
        }

        function ambientSecs() {
            return parseInt(state.ambientSecs, 10) || 90;
        }

        var screensaverPhotos = ambientPlayer({
            a: 'ssPhotoA', b: 'ssPhotoB', credit: 'screensaverCredit', dimScale: 1, secs: ambientSecs,
            onStart: function() { document.getElementById('screensaverOverlay').classList.add('ambient'); },
            onStop: function() { document.getElementById('screensaverOverlay').classList.remove('ambient'); }
        });

        function ambientShow() { screensaverPhotos.show(); }
        function ambientStart() { screensaverPhotos.start(); }
        function ambientStop() { screensaverPhotos.stop(); }
```

Then search `scripts/browser_test.py` for the removed globals `ambientOn`, `ambientFront`, `ambientPos`, `ambientFailures`, `ambientTimer`; at the time of writing none are referenced besides the `typeof ambientStart` check, which keeps working. If any reference exists, change it to the `screensaverPhotos` equivalent (`screensaverPhotos.on`, `screensaverPhotos.front`, `screensaverPhotos.pos`).

- [ ] **Step 4: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed`.
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed` (the first `sync_docs.py` run prints `[+] updated docs/index.html`).

- [ ] **Step 5: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "refactor: reusable ambient photo player, ignore late loads from earlier runs

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Photos on the home screen (setting, layer, credit)

**Files:**
- Modify: `scripts/browser_test.py` (probe and scenario steps)
- Modify: `app/index.html` (state, markup, CSS, player instance, handlers, translations)

**Interfaces:**
- Consumes: `ambientPlayer(cfg)` from Task 1; `ambientRead`, `ambientRefresh`, `ambientReady`, `screensaverOn`, `enterScreensaver`, `exitScreensaver`, `ambientSecs()`.
- Produces: `state.homePhotos` (string `'on'|'off'`, default `'off'`, key `fmtv_home_photos`); element ids `cfgHomePhotos`, `homePhotos`, `hpPhotoA`, `hpPhotoB`, `homePhotoCredit`; `ambientCacheReady() -> boolean` (fetch available, key set, cache non-empty); `homePhotos` (a player instance); `homePhotosWanted() -> boolean`; `syncHomePhotos()` (starts or stops the home player to match the settings and screensaver state).

- [ ] **Step 1: Add failing probe assertions and scenario steps**

In `scripts/browser_test.py`, inside `PROBE`, replace this exact text:

```
  var keyField = document.getElementById('cfgUnsplashKey');
```

with:

```
  eq('state home photos', state.homePhotos, 'off');
  if (!document.getElementById('cfgHomePhotos')) out.ambient.push('missing #cfgHomePhotos');
  if (!document.getElementById('homePhotos')) out.ambient.push('missing #homePhotos');
  if (!Object.prototype.hasOwnProperty.call(I18N.pt, 'Photos on Home Screen')) out.ambient.push('no translation: Photos on Home Screen');
  var keyField = document.getElementById('cfgUnsplashKey');
```

In `SCENARIO`, replace this exact text:

```
  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

with:

```
  var home = document.getElementById('homePhotos');
  function homeActive() { return !!home && /\bactive\b/.test(home.className); }
  function homeCredit() { return document.getElementById('homePhotoCredit').textContent; }
  function homeOpacities() {
    return [document.getElementById('hpPhotoA').style.opacity, document.getElementById('hpPhotoB').style.opacity];
  }
  if (typeof syncHomePhotos !== 'function') { fails.push('syncHomePhotos missing'); write(); return; }

  steps.push(function (done) { // home photos show dimmed (0.3 for a dark photo), with credit and one ping; Off hides them
    seedMany([photo('h1', 'Ann')]);
    state.ambient = 'off'; state.homePhotos = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none'; state.perfMode = 'standard';
    var calls = []; window.fetch = fakeFetch(200, '49', calls);
    syncHomePhotos();
    setTimeout(function () {
      eq('home active', homeActive(), true);
      eq('home credit', homeCredit(), t('Photo by %s on Unsplash', 'Ann'));
      eq('home dim', homeOpacities().indexOf('0.3') !== -1, true);
      eq('home pings', calls.filter(function (c) { return c.url.indexOf('/photos/h1/download') !== -1; }).length, 1);
      state.homePhotos = 'off';
      syncHomePhotos();
      eq('home off inactive', homeActive(), false);
      eq('home off credit', homeCredit(), '');
      eq('home off src', document.getElementById('hpPhotoA').getAttribute('src'), null);
      done();
    }, 500);
  });
  steps.push(function (done) { // the screensaver takes over and the home photos resume on exit
    seedMany([photo('h2', 'Ann')]);
    state.ambient = 'on'; state.homePhotos = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none';
    window.fetch = fakeFetch(200, '49', []);
    syncHomePhotos();
    enterScreensaver();
    setTimeout(function () {
      eq('home paused', homeActive(), false);
      eq('screensaver ambient', isAmbient(), true);
      exitScreensaver();
      setTimeout(function () {
        eq('home resumes', homeActive(), true);
        state.homePhotos = 'off';
        syncHomePhotos();
        done();
      }, 300);
    }, 400);
  });
  steps.push(function (done) { // no key, or an empty cache, means no home photos
    seedMany([photo('h3', 'Ann')]);
    state.homePhotos = 'on'; state.unsplashKey = '';
    syncHomePhotos();
    eq('home nokey', homeActive(), false);
    state.unsplashKey = 'k'; reset();
    syncHomePhotos();
    eq('home empty cache', homeActive(), false);
    state.homePhotos = 'off';
    syncHomePhotos();
    done();
  });
  steps.push(function (done) { // refreshes run for the home photos alone, and stop when both switches are Off
    reset(); state.ambient = 'off'; state.homePhotos = 'on'; state.unsplashKey = 'k';
    var calls = []; window.fetch = fakeFetch(200, '49', calls);
    ambientRefresh(true);
    function randomCalls(list) { return list.filter(function (c) { return c.url.indexOf('/photos/random') !== -1; }).length; }
    setTimeout(function () {
      eq('home refresh calls', randomCalls(calls), 5); // the home layer also pings the first photo it shows
      state.homePhotos = 'off';
      syncHomePhotos();
      reset();
      var calls2 = []; window.fetch = fakeFetch(200, '49', calls2);
      ambientRefresh(true);
      setTimeout(function () {
        eq('both off refresh', randomCalls(calls2), 0);
        state.ambient = 'on';
        done();
      }, 200);
    }, 400);
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL with `[!] ambient checks:` listing `state home photos: got undefined want "off"`, `missing #cfgHomePhotos`, `missing #homePhotos`, `no translation: Photos on Home Screen`, and `[!] ambient scenario: ['syncHomePhotos missing']`.

- [ ] **Step 3: Add the state field**

In `app/index.html`, replace this exact line:

```
            ambientMotion: localStorage.getItem('fmtv_ambient_motion') || 'kenburns',
```

with:

```
            ambientMotion: localStorage.getItem('fmtv_ambient_motion') || 'kenburns',
            homePhotos: localStorage.getItem('fmtv_home_photos') || 'off',
```

- [ ] **Step 4: Add the home-screen markup**

Replace this exact line:

```
    <div class="ambient-glow" id="ambientGlow"></div>
```

with:

```
    <div class="ambient-glow" id="ambientGlow"></div>
    <div class="home-photos" id="homePhotos" aria-hidden="true">
        <img class="ss-photo" id="hpPhotoA" alt="">
        <img class="ss-photo" id="hpPhotoB" alt="">
    </div>
    <div class="home-photo-credit" id="homePhotoCredit"></div>
```

- [ ] **Step 5: Add the CSS**

Replace this exact line:

```
        .screensaver-credit:empty { display: none; }
```

with:

```
        .screensaver-credit:empty { display: none; }

        /* Home-screen photos: a dimmed full-screen layer under the dashboard (.container is z-index 10). */
        .home-photos {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            overflow: hidden;
            z-index: 0;
            pointer-events: none;
        }

        .home-photos.active {
            display: block;
        }

        .home-photos:after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(to bottom, rgba(0, 0, 0, 0.35) 0%, rgba(0, 0, 0, 0) 30%, rgba(0, 0, 0, 0) 55%, rgba(0, 0, 0, 0.55) 100%);
        }

        .home-photo-credit {
            position: fixed;
            left: 54px;
            bottom: 10px;
            z-index: 11;
            font-size: 13px;
            letter-spacing: 0.5px;
            color: rgba(255, 255, 255, 0.35);
            pointer-events: none;
        }

        .home-photo-credit:empty { display: none; }
```

- [ ] **Step 6: Add the Customize control**

Replace this exact text:

```
                            <option value="none">None</option>
                        </select>
                    </div>
```

with:

```
                            <option value="none">None</option>
                        </select>
                    </div>
                    <div class="field-group">
                        <label>Photos on Home Screen</label>
                        <select class="field-input modal-nav" id="cfgHomePhotos">
                            <option value="off">Off</option>
                            <option value="on">On</option>
                        </select>
                    </div>
```

- [ ] **Step 7: Wire open, reset and save**

Open handler: replace `            document.getElementById('cfgAmbientMotion').value = state.ambientMotion;` with:

```
            document.getElementById('cfgAmbientMotion').value = state.ambientMotion;
            document.getElementById('cfgHomePhotos').value = state.homePhotos;
```

Reset handler: replace `            document.getElementById('cfgAmbientMotion').value = 'kenburns';` with:

```
            document.getElementById('cfgAmbientMotion').value = 'kenburns';
            document.getElementById('cfgHomePhotos').value = 'off';
```

Save handler: replace `            state.ambientMotion = document.getElementById('cfgAmbientMotion').value;` with:

```
            state.ambientMotion = document.getElementById('cfgAmbientMotion').value;
            state.homePhotos = document.getElementById('cfgHomePhotos').value;
```

and replace `            localStorage.setItem('fmtv_ambient_motion', state.ambientMotion);` with:

```
            localStorage.setItem('fmtv_ambient_motion', state.ambientMotion);
            localStorage.setItem('fmtv_home_photos', state.homePhotos);
```

and replace this exact text:

```
            ambientRefresh(false);
            closeSettingsModal();
```

with:

```
            ambientRefresh(false);
            syncHomePhotos();
            closeSettingsModal();
```

- [ ] **Step 8: Split `ambientReady` and add the home player**

Replace this exact function:

```
        function ambientReady() {
            var cache = ambientRead('fmtv_ambient_cache', null);
            return typeof fetch === 'function' && state.ambient === 'on' && !!state.unsplashKey && !!cache && !!cache.photos && cache.photos.length > 0;
        }
```

with:

```
        // Photos can be shown: the engine has fetch, a key is set and the cache has photos.
        function ambientCacheReady() {
            var cache = ambientRead('fmtv_ambient_cache', null);
            return typeof fetch === 'function' && !!state.unsplashKey && !!cache && !!cache.photos && cache.photos.length > 0;
        }

        function ambientReady() {
            return state.ambient === 'on' && ambientCacheReady();
        }
```

Then, directly after the line `        function ambientStop() { screensaverPhotos.stop(); }`, insert:

```

        // Photos behind the home screen dashboard: dimmer than the screensaver, paused while the screensaver shows.
        var homePhotos = ambientPlayer({
            a: 'hpPhotoA', b: 'hpPhotoB', credit: 'homePhotoCredit', dimScale: 0.55, secs: ambientSecs,
            onStart: function() { document.getElementById('homePhotos').classList.add('active'); },
            onStop: function() { document.getElementById('homePhotos').classList.remove('active'); }
        });

        function homePhotosWanted() {
            return state.homePhotos === 'on' && ambientCacheReady() && !screensaverOn;
        }

        // Start or stop the home photos so they match the settings and the screensaver state.
        function syncHomePhotos() {
            var wanted = homePhotosWanted();
            if (wanted && !homePhotos.on) homePhotos.start();
            else if (!wanted && homePhotos.on) homePhotos.stop();
        }
```

- [ ] **Step 9: Refresh for either switch, and keep the layer in step with the screensaver and the cache**

Replace this exact text:

```
            if (ambientRefreshing || state.ambient !== 'on' || !state.unsplashKey || typeof fetch !== 'function') return;
```

with:

```
            if (ambientRefreshing || (state.ambient !== 'on' && state.homePhotos !== 'on') || !state.unsplashKey || typeof fetch !== 'function') return;
```

Replace this exact line (inside `finish()` of `ambientRefresh`):

```
                    try { localStorage.setItem('fmtv_ambient_cache', JSON.stringify({ photos: photos, at: Date.now() })); } catch (e) {}
```

with:

```
                    try { localStorage.setItem('fmtv_ambient_cache', JSON.stringify({ photos: photos, at: Date.now() })); } catch (e) {}
                    syncHomePhotos();
```

In `enterScreensaver()` replace this exact text:

```
            screensaverOn = true;
            screensaverOverlay.classList.add('active');
```

with:

```
            screensaverOn = true;
            syncHomePhotos();
            screensaverOverlay.classList.add('active');
```

In `exitScreensaver()` replace this exact text:

```
            screensaverOn = false;
            screensaverOverlay.classList.remove('active');
```

with:

```
            screensaverOn = false;
            syncHomePhotos();
            screensaverOverlay.classList.remove('active');
```

Replace this exact line (the boot-time refresh schedule):

```
        setTimeout(function() { ambientRefresh(false); }, 20000);
```

with:

```
        setTimeout(function() { ambientRefresh(false); }, 20000);
        setTimeout(syncHomePhotos, 2000);
```

- [ ] **Step 10: Add the translations**

In each language, replace the exact entry below with itself followed by the new entry (same line is fine).

Portuguese: replace `'Photo by %s on Unsplash': 'Foto de %s no Unsplash',` with `'Photo by %s on Unsplash': 'Foto de %s no Unsplash', 'Photos on Home Screen': 'Fotos na Tela Inicial',`

Spanish: replace `'Photo by %s on Unsplash': 'Foto de %s en Unsplash',` with `'Photo by %s on Unsplash': 'Foto de %s en Unsplash', 'Photos on Home Screen': 'Fotos en la Pantalla de Inicio',`

German: replace `'Photo by %s on Unsplash': 'Foto von %s auf Unsplash',` with `'Photo by %s on Unsplash': 'Foto von %s auf Unsplash', 'Photos on Home Screen': 'Fotos auf dem Startbildschirm',`

French: replace `'Photo by %s on Unsplash': 'Photo de %s sur Unsplash',` with `'Photo by %s on Unsplash': 'Photo de %s sur Unsplash', 'Photos on Home Screen': 'Photos sur l’écran d’accueil',`

- [ ] **Step 11: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed` (all five languages `ok`).
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed`.

- [ ] **Step 12: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: optional dimmed Unsplash photos behind the home screen

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Keep LG's screensaver away (setting and hidden video)

**Files:**
- Modify: `scripts/browser_test.py` (probe and scenario steps)
- Modify: `app/index.html` (state, markup, code, handlers, translations)

**Interfaces:**
- Consumes: `enterScreensaver`, `exitScreensaver`.
- Produces: `state.keepAwake` (string `'on'|'off'`, default `'on'`, key `fmtv_keep_awake`); element ids `cfgKeepAwake`, `keepAwakeCanvas`, `keepAwakeVideo`; `keepAwakeStart()`, `keepAwakeStop()` and the variable `keepAwakeTimer` (`null` when stopped).

- [ ] **Step 1: Add failing probe assertions and scenario steps**

In `scripts/browser_test.py`, inside `PROBE`, replace this exact text:

```
  eq('state home photos', state.homePhotos, 'off');
```

with:

```
  eq('state keep awake', state.keepAwake, 'on');
  if (!document.getElementById('cfgKeepAwake')) out.ambient.push('missing #cfgKeepAwake');
  if (!document.getElementById('keepAwakeVideo')) out.ambient.push('missing #keepAwakeVideo');
  if (!Object.prototype.hasOwnProperty.call(I18N.pt, 'Keep LG Screensaver Away')) out.ambient.push('no translation: Keep LG Screensaver Away');
  eq('state home photos', state.homePhotos, 'off');
```

In `SCENARIO`, replace this exact text:

```
  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

with:

```
  var awakeVideo = document.getElementById('keepAwakeVideo'), awakeCanvas = document.getElementById('keepAwakeCanvas');
  if (typeof keepAwakeStart !== 'function') { fails.push('keepAwakeStart missing'); write(); return; }

  steps.push(function (done) { // On: the hidden video plays only while our screensaver shows
    seedMany([photo('k1', 'Ann')]);
    state.ambient = 'on'; state.unsplashKey = 'k'; state.keepAwake = 'on'; state.homePhotos = 'off';
    window.fetch = fakeFetch(200, '49', []);
    eq('awake idle', awakeVideo.srcObject === null || awakeVideo.srcObject === undefined, true);
    enterScreensaver();
    setTimeout(function () {
      eq('awake playing', !!awakeVideo.srcObject, true);
      eq('awake timer', keepAwakeTimer !== null, true);
      exitScreensaver();
      eq('awake stopped', awakeVideo.srcObject === null || awakeVideo.srcObject === undefined, true);
      eq('awake timer cleared', keepAwakeTimer, null);
      done();
    }, 300);
  });
  steps.push(function (done) { // Off: nothing plays; the black-clock screensaver is unaffected
    reset(); state.keepAwake = 'off';
    enterScreensaver();
    setTimeout(function () {
      eq('awake off video', !!awakeVideo.srcObject, false);
      eq('awake off timer', keepAwakeTimer, null);
      exitScreensaver();
      state.keepAwake = 'on';
      done();
    }, 200);
  });
  steps.push(function (done) { // an engine without captureStream is skipped without errors
    reset(); state.keepAwake = 'on';
    awakeCanvas.captureStream = undefined; // shadows the prototype method on this element
    var threw = false;
    try { enterScreensaver(); } catch (e) { threw = true; }
    setTimeout(function () {
      eq('awake no captureStream threw', threw, false);
      eq('awake no captureStream video', !!awakeVideo.srcObject, false);
      eq('awake no captureStream timer', keepAwakeTimer, null);
      exitScreensaver();
      delete awakeCanvas.captureStream;
      done();
    }, 200);
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL with `[!] ambient checks:` listing `state keep awake: got undefined want "on"`, `missing #cfgKeepAwake`, `missing #keepAwakeVideo`, `no translation: Keep LG Screensaver Away`, and `[!] ambient scenario: ['keepAwakeStart missing']`.

- [ ] **Step 3: Add the state field**

In `app/index.html`, replace this exact line:

```
            homePhotos: localStorage.getItem('fmtv_home_photos') || 'off',
```

with:

```
            homePhotos: localStorage.getItem('fmtv_home_photos') || 'off',
            keepAwake: localStorage.getItem('fmtv_keep_awake') || 'on',
```

- [ ] **Step 4: Add the hidden video markup**

Replace this exact line:

```
    <div class="screensaver" id="screensaverOverlay">
```

with:

```
    <canvas id="keepAwakeCanvas" width="64" height="36" hidden></canvas>
    <video id="keepAwakeVideo" muted loop playsinline aria-hidden="true" style="position: fixed; right: 0; bottom: 0; width: 4px; height: 4px; opacity: 0.02; pointer-events: none;"></video>
    <div class="screensaver" id="screensaverOverlay">
```

- [ ] **Step 5: Add the Customize control**

Replace this exact text:

```
                        <label>Photos on Home Screen</label>
                        <select class="field-input modal-nav" id="cfgHomePhotos">
                            <option value="off">Off</option>
                            <option value="on">On</option>
                        </select>
                    </div>
```

with:

```
                        <label>Photos on Home Screen</label>
                        <select class="field-input modal-nav" id="cfgHomePhotos">
                            <option value="off">Off</option>
                            <option value="on">On</option>
                        </select>
                    </div>
                    <div class="field-group">
                        <label>Keep LG Screensaver Away</label>
                        <select class="field-input modal-nav" id="cfgKeepAwake">
                            <option value="on">On</option>
                            <option value="off">Off</option>
                        </select>
                    </div>
```

- [ ] **Step 6: Wire open, reset and save**

Open handler: replace `            document.getElementById('cfgHomePhotos').value = state.homePhotos;` with:

```
            document.getElementById('cfgHomePhotos').value = state.homePhotos;
            document.getElementById('cfgKeepAwake').value = state.keepAwake;
```

Reset handler: replace `            document.getElementById('cfgHomePhotos').value = 'off';` with:

```
            document.getElementById('cfgHomePhotos').value = 'off';
            document.getElementById('cfgKeepAwake').value = 'on';
```

Save handler: replace `            state.homePhotos = document.getElementById('cfgHomePhotos').value;` with:

```
            state.homePhotos = document.getElementById('cfgHomePhotos').value;
            state.keepAwake = document.getElementById('cfgKeepAwake').value;
```

and replace `            localStorage.setItem('fmtv_home_photos', state.homePhotos);` with:

```
            localStorage.setItem('fmtv_home_photos', state.homePhotos);
            localStorage.setItem('fmtv_keep_awake', state.keepAwake);
```

- [ ] **Step 7: Add the keep-awake code**

Replace this exact line:

```
        // --- OLED-Safe Idle Screensaver ---
```

with:

```
        // --- Keep LG's own screensaver away while ours shows ---
        // A playing video holds the TV's screensaver off (checked on an LG UR91, webOS 23). A 64x36 canvas stream
        // shown in a 4x4 px muted <video> is enough; engines without canvas.captureStream just skip it.
        var keepAwakeTimer = null;

        function keepAwakeStart() {
            if (state.keepAwake !== 'on' || keepAwakeTimer !== null) return;
            var canvas = document.getElementById('keepAwakeCanvas');
            var video = document.getElementById('keepAwakeVideo');
            if (!canvas || !video || !canvas.captureStream) return;
            try {
                var ctx = canvas.getContext('2d');
                keepAwakeTimer = setInterval(function() {
                    ctx.fillStyle = 'hsl(' + (Date.now() / 20 % 360) + ',60%,35%)';
                    ctx.fillRect(0, 0, 64, 36);
                }, 200);
                video.srcObject = canvas.captureStream(10);
                var played = video.play();
                if (played && played.catch) played.catch(function() {});
            } catch (e) {
                keepAwakeStop();
            }
        }

        function keepAwakeStop() {
            clearInterval(keepAwakeTimer);
            keepAwakeTimer = null;
            var video = document.getElementById('keepAwakeVideo');
            if (video) {
                try { video.pause(); } catch (e) {}
                video.srcObject = null;
            }
        }

        // --- OLED-Safe Idle Screensaver ---
```

Then in `enterScreensaver()` replace this exact text:

```
            if (ambientReady()) ambientStart();
```

with:

```
            if (ambientReady()) ambientStart();
            keepAwakeStart();
```

and in `exitScreensaver()` replace this exact text:

```
            ambientStop();
        }
```

with:

```
            ambientStop();
            keepAwakeStop();
        }
```

- [ ] **Step 8: Add the translations**

Portuguese: replace `'Photos on Home Screen': 'Fotos na Tela Inicial',` with `'Photos on Home Screen': 'Fotos na Tela Inicial', 'Keep LG Screensaver Away': 'Evitar o Protetor de Tela da LG',`

Spanish: replace `'Photos on Home Screen': 'Fotos en la Pantalla de Inicio',` with `'Photos on Home Screen': 'Fotos en la Pantalla de Inicio', 'Keep LG Screensaver Away': 'Evitar el Protector de Pantalla de LG',`

German: replace `'Photos on Home Screen': 'Fotos auf dem Startbildschirm',` with `'Photos on Home Screen': 'Fotos auf dem Startbildschirm', 'Keep LG Screensaver Away': 'LG-Bildschirmschoner verhindern',`

French: replace `'Photos on Home Screen': 'Photos sur l’écran d’accueil',` with `'Photos on Home Screen': 'Photos sur l’écran d’accueil', 'Keep LG Screensaver Away': 'Éviter l’écran de veille LG',`

- [ ] **Step 9: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed`.
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed`.

- [ ] **Step 10: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: keep LG's own screensaver away while ours shows

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Documentation

**Files:**
- Modify: `README.md` (English settings table; Portuguese settings table)
- Modify: `ROADMAP.md` (v1.3 screensaver bullet)

**Interfaces:**
- Consumes: the shipped behaviour of Tasks 1-3.
- Produces: user-facing docs only.

- [ ] **Step 1: Add the English README rows**

In `README.md`, find the row that starts with `| **Unsplash Access Key** |` (English table) and add these two rows directly after it:

```
| **Photos on Home Screen** | `Off` (default) or `On`. Shows the same Unsplash photos, slowly moving and dimmed, behind the home screen, with a small "Photo by NAME on Unsplash" credit in the bottom-left corner. Needs the Unsplash key; it pauses while the screensaver is showing. |
| **Keep LG Screensaver Away** | `On` (default) or `Off`. While Free My TV's screensaver is showing, a tiny hidden muted video plays so LG's own screensaver does not cover it. It may also stop the TV's own auto-sleep from firing during that time, so turn it `Off` if you prefer the TV to sleep normally. |
```

- [ ] **Step 2: Add the Portuguese README rows**

Find the Portuguese row that starts with `| **Protetor de Tela com Fotos** |` and add these two rows directly after it:

```
| **Fotos na Tela Inicial** | `Desligado` (padrão) ou `Ligado`. Mostra as mesmas fotos do Unsplash, em movimento lento e escurecidas, atrás da tela inicial, com o crédito "Foto de NOME no Unsplash" no canto inferior esquerdo. Precisa da chave do Unsplash e pausa enquanto o protetor de tela aparece. |
| **Evitar o Protetor de Tela da LG** | `Ligado` (padrão) ou `Desligado`. Enquanto o protetor de tela do Free My TV aparece, um vídeo minúsculo, mudo e invisível toca para que o protetor da própria LG não o cubra. Pode impedir também o desligamento automático da TV nesse período; desligue se preferir o comportamento normal. |
```

- [ ] **Step 3: Update the roadmap**

In `ROADMAP.md`, find the bullet that begins `- [x] **Idle Screensaver & Clock Overlay:**` and append this sentence at the end of that bullet's line: ` Photos can also run behind the home screen (setting), and a hidden muted video keeps LG's own screensaver from covering ours (setting).`

- [ ] **Step 4: Verify and commit**

Run `CHECK`. Expected: `[+] all checks passed`.

```bash
git add README.md ROADMAP.md
git commit -m "docs: document home-screen photos and keep-awake settings

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Verify on the real TV (manual, nothing committed)

**Files:**
- No source changes. Rebuilds `dist/org.webos.freemytv_1.4.0_all.ipk` locally; do not commit it.

**Interfaces:**
- Consumes: the finished app, the TV at `10.100.102.2` with Developer Mode on, and the LG skill scripts. The Unsplash key is already saved on the TV; never read it back or display it.

- [ ] **Step 1: Rebuild and install**

```powershell
Remove-Item 'C:\Users\97254\Downloads\FreeMyTvWebOS\dist\*.ipk'
python 'C:\Users\97254\Downloads\FreeMyTvWebOS\scripts\build.py'
python 'C:\Users\97254\Downloads\FreeMyTvWebOS\scripts\install.py' 10.100.102.2
```

Expected: `[+] SUCCESS! Free My TV is installed and running on your LG TV!`

- [ ] **Step 2: Home-screen photos**

In Customize set "Photos on Home Screen" to On and Save & Apply. Expected within about a minute: a dimmed photo behind the clock, shelf and weather, and a small "Photo by NAME on Unsplash" line at the bottom-left. Capture with `shot.py`. When viewing the Customize screenshot, black out the Unsplash key field first so the key is never displayed.

- [ ] **Step 2b: Masked key field**

Confirm the Unsplash Access Key field shows dots (not text) once a key is saved. Do not display the key.

- [ ] **Step 3: Keep LG's screensaver away**

Leave the TV untouched for 8 minutes (screenshots do not count as input). Expected: our screensaver is still showing (photo, clock and credit), not LG's analog clock. Capture at about 4 and 8 minutes.

- [ ] **Step 4: Exit and fallback**

Press any remote key: the home screen returns and the home photos resume. Set "Keep LG Screensaver Away" to Off, wait out the idle time plus a few minutes, and confirm LG's screensaver can take over again (this proves the switch works). Set it back to On.

- [ ] **Step 5: Report**

Report the observations, including whether the TV still sleeps by itself (ask the user to confirm, since it needs a long wait). Do not commit anything; `git status` should show only `dist/*.ipk` modified.
