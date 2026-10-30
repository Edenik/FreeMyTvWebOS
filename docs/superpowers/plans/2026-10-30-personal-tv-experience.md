# Personal TV Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the nine design boards in the "Personal TV Experience" artifact (https://claude.ai/artifact/CkmV85EuufAMyc8jkaVGGW) into the real app: a home screen that greets the user, resumes what they watched, offers one-press scenes, a first-run setup, profiles, a calm evening ambient mode, consistent remote focus, and an honest privacy line.

**Architecture:** Everything stays in the single file `app/index.html` (ES5, no build step) with data in `localStorage`. Each feature is a small pure function (unit-tested in `scripts/browser_test.py`) plus a thin DOM layer that reuses the existing patterns: the `state` object, the `SETTINGS` schema and `setSettingValue`, `.nav-item` elements for D-pad focus, `t()` for translations, and `launchApp()` for opening apps. Two spikes (TV picture mode / sleep timer, and LG's screensaver) run on the real TV first because their outcome decides scope.

**Tech Stack:** ES5 JavaScript (Chromium 38 floor on webOS 3.x: no arrow functions, `let`/`const`, template literals, `Array.prototype.find`; use `arrFind` / `arrFindIndex` / `toArray`), HTML/CSS, Python 3 test scripts, headless Chrome, Node `es-check`.

## Global Constraints

- **Branch flow:** work on `feature/personal-tv` (already created from `main`; the clone has no `development` branch). **Never merge or push without the user's explicit approval.** After finishing: show a diff summary, ask "Want to run the app to review?", wait for approval.
- **ES5 only:** CI runs `es-check@7.2.1 es5` on the extracted script. No arrow functions, `let`/`const`, template literals, default params, spread, `for…of`. Guard `fetch` and `canvas.captureStream`.
- **`docs/index.html` is a verbatim copy of `app/index.html`:** run `python scripts/sync_docs.py` before every commit.
- **Translations:** every new `t('…')` English string needs an entry in all four dictionaries (`pt`, `es`, `de`, `fr`, in `I18N` near line 1455). `scripts/browser_test.py` fails when keys differ between languages or a markup string is missing. Never duplicate a key inside one dictionary.
- **Remote navigation:** every focusable element has class `nav-item` and `data-tag` / `data-title` / `data-desc` (hero text). `refreshMainNavList()` filters out hidden elements (`offsetParent !== null`), so call it after any change that shows or hides one.
- **Honest copy:** the app does call Open-Meteo (weather), TMDB (trending), Unsplash (photos) and optionally ipapi.co. The design boards say "Nothing leaves this TV"; the shipped line must be **"No ads. No account. Your settings stay on this TV."** (Task 5 fixes the artifact too).
- **Never commit `dist/*.ipk`.** Rebuild locally only: `Remove-Item dist\*.ipk; python scripts\build.py; python scripts\install.py 10.100.102.2` (PowerShell; Git Bash lacks `scp`).
- **Windows quirks:** use Git Bash for Python heredocs (PowerShell has none); `PYTHONUTF8=1` for `browser_test.py`; es-check needs forward-slash paths; working tree is CRLF (`git` warns LF→CRLF, harmless). A commit message with `-F -` fails for `git merge`; use a message file.
- **Verification commands (`CHECK`, run in Git Bash from the repo root):**
  ```bash
  PYTHONUTF8=1 python scripts/sync_docs.py && PYTHONUTF8=1 python scripts/check.py \
   && PYTHONUTF8=1 python scripts/browser_test.py --chrome "/c/Program Files/Google/Chrome/Application/chrome.exe" \
   && python scripts/check.py --extract-js C:/Users/97254/Downloads/app_es5.js && npx --yes es-check@7.2.1 es5 C:/Users/97254/Downloads/app_es5.js
  ```
  Expected: `all checks passed`, `browser tests passed`, `no ES version matching errors`.
- **Test conventions (`scripts/browser_test.py`):** the `PROBE` string runs once after boot and holds pure-function checks (`eq(name, got, want)`, `need('fnName')` pushes into `out.ambient`); the `SCENARIO` string holds async `steps.push(function (done) { … done(); })` steps with `eq`. Note PROBE runs once per language, so compare translated text via `t('…')`, never a hard-coded English literal.
- **Test determinism:** tests run at any hour. Anything that depends on the clock or sunset must take its inputs as parameters (pure function) or be switched off in the test (Task 4 sets `state.nightDim = 'off'`).
- **TV checks:** the TV is at `10.100.102.2`; scripts in `C:\Users\97254\.claude\skills\lg-tv-control\scripts` (`tv.py btn X`, `shot.py out.jpg`) with `LGTV_IP=10.100.102.2`. The pointer-socket BACK key reaches the app now (`disableBackHistoryAPI` is set).

## File Structure

| File | Responsibility |
|---|---|
| `app/index.html` | All code, markup, CSS, translations (single file). New sections: greeting, launch history + pick-up row, scenes, setup wizard, profiles, night dimming. |
| `scripts/browser_test.py` | Add PROBE checks for pure functions and SCENARIO steps for DOM behaviour. |
| `app/appinfo.json` | Version bump only (Task 13), possibly `requiredPermissions` if the Task 10 spike needs it. |
| `README.md` | Document each new setting / feature in the settings table. |
| `docs/superpowers/specs/2026-10-30-tv-picture-mode-spike.md` | Written by Task 10 (result of the spike). |
| `docs/superpowers/specs/2026-10-30-lg-screensaver-spike.md` | Written by Task 11. |

## Task order and why

1 name+greeting → 2 pick-up row → 3 focus ring → 4 night dimming → 5 privacy line → 6 scenes → 7 setup wizard → 8 profiles → 9 habit-aware pick-up → 10 and 11 spikes (can run any time; do 11 early if the LG screensaver is the user's top complaint) → 12 artifact fixes → 13 release. Tasks 1–5 are small and change the feel most; 6–9 are larger; 10–11 are investigation.

---

### Task 1: Your name and the greeting

**Files:**
- Modify: `app/index.html` (state ~line 1416, markup in `.hero-shelf` ~line 1201, `updateClock` ~line 1835, SETTINGS ~line 2604, `I18N` dictionaries, CSS near `.hero-shelf`)
- Test: `scripts/browser_test.py`

**Interfaces:**
- Produces: `greetingKey(hour) -> string` (English key), `greetingText(hour, name) -> string` (translated, `"<Greeting>, <name>"` or just the greeting), `updateGreeting()` (DOM), `state.userName` (string, setting id `userName`, store `fmtv_user_name`).

- [ ] **Step 1: Write the failing probe test**

In `PROBE`, directly after the `if (need('ambientDim')) { … }` block, add:

```javascript
  if (need('greetingKey') && need('greetingText')) {
    eq('greet 4', greetingKey(4), 'Good night');
    eq('greet 5', greetingKey(5), 'Good morning');
    eq('greet 11', greetingKey(11), 'Good morning');
    eq('greet 12', greetingKey(12), 'Good afternoon');
    eq('greet 16', greetingKey(16), 'Good afternoon');
    eq('greet 17', greetingKey(17), 'Good evening');
    eq('greet 21', greetingKey(21), 'Good evening');
    eq('greet 22', greetingKey(22), 'Good night');
    eq('greet name', greetingText(19, 'Noa'), t('Good evening') + ', Noa');
    eq('greet no name', greetingText(19, ''), t('Good evening'));
  }
```

- [ ] **Step 2: Run it and see it fail**

Run `CHECK`. Expected: `ambient checks: ['greetingKey missing']`.

- [ ] **Step 3: Add state, helpers and the settings row**

In `state` add after `clockPos`: `userName: localStorage.getItem('fmtv_user_name') || '',`

Above `function updateClock()` add:

```javascript
        // 05-11 morning, 12-16 afternoon, 17-21 evening, otherwise night.
        function greetingKey(hour) {
            if (hour >= 5 && hour < 12) return 'Good morning';
            if (hour >= 12 && hour < 17) return 'Good afternoon';
            if (hour >= 17 && hour < 22) return 'Good evening';
            return 'Good night';
        }

        function greetingText(hour, name) {
            var base = t(greetingKey(hour));
            return name ? base + ', ' + name : base;
        }

        // Greeting block above the hero: "Friday evening" / "Good evening, Noa" / weather line.
        function updateGreeting() {
            var now = new Date();
            var weekday = now.toLocaleDateString(LANG_LOCALES[currentLang()], { weekday: 'long' });
            document.getElementById('greetingEyebrow').textContent = weekday;
            document.getElementById('greetingTitle').textContent = greetingText(now.getHours(), state.userName);
            var weather = document.getElementById('weatherText').textContent;
            var loaded = weather && weather !== 'Loading...' && weather !== t('Loading...');
            var sub = loaded ? weather : '';
            if (loaded && state.sunset) sub += ' · ' + t('Sunset') + ' ' + state.sunset;
            document.getElementById('greetingSub').textContent = sub;
        }
```

In `updateClock()` (end of the function, after the screensaver lines) add `updateGreeting();`. It runs every second but only sets three text nodes; that is cheap. At the end of the successful branch of `fetchWeather()` (right after `document.getElementById('weatherSub').textContent = cityLabel + sunsetStr;`) add `updateGreeting();`.

In `SETTINGS`, before the `theme` row (Look & Feel, `cat: 1`), add:

```javascript
            { id: 'userName', cat: 1, type: 'text', field: 'userName', store: 'fmtv_user_name', def: '', label: 'Your Name',
              placeholder: 'e.g. Noa', hint: 'Used in the greeting on the home screen',
              apply: function() { updateGreeting(); } },
```

- [ ] **Step 4: Add the markup and CSS**

Inside `<div class="hero-shelf">`, before `<div class="hero-tag" id="heroTag">`:

```html
            <div class="greeting" id="greeting">
                <div class="greeting-eyebrow" id="greetingEyebrow"></div>
                <div class="greeting-title" id="greetingTitle"></div>
                <div class="greeting-sub" id="greetingSub"></div>
            </div>
```

CSS next to `.hero-shelf`:

```css
        .greeting { margin-bottom: 18px; }
        .greeting-eyebrow { font-size: 15px; letter-spacing: 0.14em; text-transform: uppercase; color: #ffbd7a; font-weight: 600; }
        .greeting-title { font-size: 52px; line-height: 1.08; font-weight: 700; margin-top: 4px; }
        .greeting-sub { font-size: 20px; color: var(--text-secondary); margin-top: 6px; }
        .greeting-sub:empty { display: none; }
```

(If `--text-secondary` does not exist, use the variable the `.hero-desc` rule uses; check `.hero-desc`.)

- [ ] **Step 5: Translations**

Add to each dictionary (insert right before the `'Drift Speed': ` pair, which exists once per dictionary):

| key | pt | es | de | fr |
|---|---|---|---|---|
| `Good morning` | `Bom dia` | `Buenos días` | `Guten Morgen` | `Bonjour` |
| `Good afternoon` | `Boa tarde` | `Buenas tardes` | `Guten Tag` | `Bon après-midi` |
| `Good evening` | `Boa noite` | `Buenas noches` | `Guten Abend` | `Bonsoir` |
| `Good night` | `Boa madrugada` | `Buenas noches` | `Gute Nacht` | `Bonne nuit` |
| `Your Name` | `Seu Nome` | `Tu Nombre` | `Dein Name` | `Votre prénom` |
| `e.g. Noa` | `ex.: Noa` | `p. ej. Noa` | `z. B. Noa` | `ex. : Noa` |
| `Used in the greeting on the home screen` | `Usado na saudação da tela inicial` | `Se usa en el saludo de la pantalla de inicio` | `Wird in der Begrüßung auf dem Startbildschirm verwendet` | `Utilisé dans le message d’accueil de l’écran d’accueil` |

Use a small Python script run from Git Bash (same insertion technique as earlier commits: find the `'Drift Speed': ` anchor, assert exactly 4 occurrences, write the pairs before each, `newline=''` on read and write).

- [ ] **Step 6: Add a SCENARIO step for the DOM**

```javascript
  steps.push(function (done) { // the greeting shows the name and the part of the day
    state.userName = 'Noa'; updateGreeting();
    eq('greeting title', document.getElementById('greetingTitle').textContent, greetingText(new Date().getHours(), 'Noa'));
    eq('greeting eyebrow set', document.getElementById('greetingEyebrow').textContent.length > 0, true);
    state.userName = ''; updateGreeting();
    eq('greeting no name', document.getElementById('greetingTitle').textContent, t(greetingKey(new Date().getHours())));
    done();
  });
```

- [ ] **Step 7: Run `CHECK`; expected all green. Install and look on the TV**

Install, take `shot.py`, confirm the greeting block does not push the shelf off the screen (the hero area is shared). If it does, reduce `.greeting-title` to 44px or the `.hero-shelf` margin. Then in Customize → Look & Feel, set Your Name, and confirm the greeting updates.

- [ ] **Step 8: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py && git commit -m "feat: greeting by name on the home screen"
```

---

### Task 2: Launch history and the "Pick up where you left off" row

**Files:**
- Modify: `app/index.html` (state, `launchApp` ~line 2296, `renderAppsShelf` ~line 2366, new markup between `.hero-shelf` and `.shelf-wrapper`, CSS, `onVisibilityChange`, boot sequence, SETTINGS, I18N)
- Test: `scripts/browser_test.py`

**Interfaces:**
- Produces: `readLaunchHist()`, `recordLaunch(appId, nowMs)`, `recentApps(hist, catalog, limit) -> [{app, t}]`, `relativeWhen(ts, nowMs) -> string`, `buildAppIcon(app, device) -> HTMLElement` (extracted from `renderAppsShelf`), `renderPickup()`, `state.pickup` (`'on'|'off'`, setting `pickup`, store `fmtv_pickup`).
- Storage: `localStorage['fmtv_launch_hist']` = `{ "<appId>": { "t": <ms>, "n": <count> } }`, at most 30 apps.

- [ ] **Step 1: Failing probe tests**

In `PROBE` after the greeting block:

```javascript
  if (need('recordLaunch') && need('recentApps') && need('relativeWhen')) {
    localStorage.removeItem('fmtv_launch_hist');
    var T = new Date(2026, 9, 30, 21, 10).getTime();
    recordLaunch('netflix', T - 86400000);
    recordLaunch('youtube.leanback.v4', T - 3600000);
    recordLaunch('netflix', T - 86400000 + 1000);
    var hist = readLaunchHist();
    eq('hist count', hist.netflix.n, 2);
    var recent = recentApps(hist, DEFAULT_CATALOG, 3);
    eq('recent order', recent.map(function (r) { return r.app.id; }).join(','), 'youtube.leanback.v4,netflix');
    eq('recent limit', recentApps(hist, DEFAULT_CATALOG, 1).length, 1);
    eq('recent unknown app ignored', recentApps({ nope: { t: 1, n: 1 } }, DEFAULT_CATALOG, 3).length, 0);
    eq('when today', relativeWhen(T - 3600000, T), t('Today, %s', '20:10'));
    eq('when yesterday', relativeWhen(T - 86400000, T), t('Yesterday, %s', '21:10'));
    eq('when older', relativeWhen(T - 3 * 86400000, T).length > 0, true);
    localStorage.removeItem('fmtv_launch_hist');
  }
```

Run `CHECK`; expected failure `recordLaunch missing`.

- [ ] **Step 2: Implement the pure functions**

Above `function launchApp`:

```javascript
        // --- Launch history: what you opened last, kept only on this TV ---
        var LAUNCH_HIST_KEY = 'fmtv_launch_hist';
        var LAUNCH_HIST_MAX = 30;

        function readLaunchHist() {
            try {
                var h = JSON.parse(localStorage.getItem(LAUNCH_HIST_KEY) || '{}');
                return h && typeof h === 'object' && !Array.isArray(h) ? h : {};
            } catch (e) { return {}; }
        }

        function recordLaunch(appId, nowMs) {
            var hist = readLaunchHist();
            var entry = hist[appId] || { t: 0, n: 0 };
            entry.t = nowMs;
            entry.n = (entry.n || 0) + 1;
            hist[appId] = entry;
            var ids = Object.keys(hist);
            if (ids.length > LAUNCH_HIST_MAX) {
                ids.sort(function(a, b) { return hist[a].t - hist[b].t; });
                for (var i = 0; i < ids.length - LAUNCH_HIST_MAX; i++) delete hist[ids[i]];
            }
            try { localStorage.setItem(LAUNCH_HIST_KEY, JSON.stringify(hist)); } catch (e) {}
        }

        // Newest first, only apps that exist in the catalog.
        function recentApps(hist, catalog, limit) {
            var items = [];
            catalog.forEach(function(app) { if (hist[app.id]) items.push({ app: app, t: hist[app.id].t }); });
            items.sort(function(a, b) { return b.t - a.t; });
            return items.slice(0, limit);
        }

        function relativeWhen(ts, nowMs) {
            var then = new Date(ts), now = new Date(nowMs);
            var hhmm = pad2(then.getHours()) + ':' + pad2(then.getMinutes());
            var dayStart = function(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };
            var days = Math.round((dayStart(now) - dayStart(then)) / 86400000);
            if (days <= 0) return t('Today, %s', hhmm);
            if (days === 1) return t('Yesterday, %s', hhmm);
            var locale = LANG_LOCALES[currentLang()];
            if (days < 7) return then.toLocaleDateString(locale, { weekday: 'long' });
            return then.toLocaleDateString(locale, { month: 'short', day: 'numeric' });
        }
```

(`dayStart` is a function expression assigned to a `var`, which ES5 allows; no arrow functions.)

- [ ] **Step 3: Record launches on success**

In `launchApp`, replace the two success branches:

- In the main `onSuccess`: `else finish(t('Opening %s…', title));` → `else { recordLaunch(appId, Date.now()); finish(t('Opening %s…', title)); }`
- In the fallback `onSuccess`: `if (reply && reply.returnValue === true) finish(t('Opening %s…', title));` → `if (reply && reply.returnValue === true) { recordLaunch(appId, Date.now()); finish(t('Opening %s…', title)); }`

Skip recording for the LG Settings app: wrap with `if (appId !== LG_SETTINGS_APP)` (define the check once as `var track = appId !== LG_SETTINGS_APP;` near the top of `launchApp` and use `if (track) recordLaunch(...)`).

- [ ] **Step 4: Extract `buildAppIcon` from `renderAppsShelf`**

Move lines from `var iconDiv = document.createElement('div');` through the closing brace of the `if (isHDMI(app)) {…} else {…}` block into a new function above `renderAppsShelf`:

```javascript
        // The artwork block of a tile: HDMI device art, a brand logo, or the app title as readable fallback.
        function buildAppIcon(app, device) {
            var iconDiv = document.createElement('div');
            iconDiv.className = 'app-icon';
            /* …the moved body unchanged, ending with: */
            return iconDiv;
        }
```

and in `renderAppsShelf` replace the moved block by `var iconDiv = buildAppIcon(app, device);`. Run `CHECK`; all previous tests must still pass (pure refactor).

- [ ] **Step 5: Markup, CSS, render function**

Markup between `</div>` of `.hero-shelf` and `<!-- Glass Shelf: Apps -->`:

```html
        <div class="pickup-section" id="pickupSection" hidden>
            <div class="pickup-header">Pick up where you left off</div>
            <div class="pickup-row" id="pickupRow"></div>
        </div>
```

CSS (sizes mirror the 1080p layout; adjust after the TV screenshot):

```css
        .pickup-section { margin-bottom: 18px; }
        .pickup-header { font-size: 20px; font-weight: 600; margin-bottom: 10px; color: var(--text-primary); }
        .pickup-row { display: flex; gap: 18px; }
        .pickup-card { width: 340px; background: none; border: 0; padding: 0; color: inherit; text-align: left; cursor: pointer; font-family: inherit; }
        .pickup-art { width: 340px; height: 150px; border-radius: 14px; overflow: hidden; position: relative; }
        .pickup-art .app-icon { width: 100%; height: 100%; }
        .pickup-name { font-size: 18px; font-weight: 600; margin-top: 8px; }
        .pickup-when { font-size: 15px; color: var(--text-secondary); }
        .pickup-card.focused .pickup-art { transform: scale(1.06); box-shadow: 0 18px 40px rgba(0,0,0,.55), 0 0 30px rgba(255,255,255,.25); }
```

Render function (next to `renderAppsShelf`):

```javascript
        function renderPickup() {
            var section = document.getElementById('pickupSection');
            var row = document.getElementById('pickupRow');
            row.innerHTML = '';
            var recent = state.pickup === 'on' && !shelfEdit ? recentApps(readLaunchHist(), state.catalog, 3) : [];
            section.hidden = recent.length === 0;
            var now = Date.now();
            recent.forEach(function(item) {
                var app = item.app;
                var device = devicePreset(app, state.hdmiDevices);
                var title = device.title || app.title;
                var card = document.createElement('button');
                card.className = 'pickup-card nav-item';
                card.dataset.id = app.id;
                card.dataset.tag = app.tag;
                card.dataset.title = title;
                card.dataset.desc = app.desc;
                card.dataset.color = app.color;
                card.setAttribute('aria-label', title);
                var art = document.createElement('div');
                art.className = 'pickup-art';
                art.appendChild(buildAppIcon(app, device));
                var name = document.createElement('div');
                name.className = 'pickup-name';
                name.textContent = title;
                var when = document.createElement('div');
                when.className = 'pickup-when';
                when.textContent = relativeWhen(item.t, now);
                card.appendChild(art);
                card.appendChild(name);
                card.appendChild(when);
                card.addEventListener('mouseenter', function() { setMainFocus(card); });
                card.addEventListener('click', function() { launchApp(app.id); });
                row.appendChild(card);
            });
            refreshMainNavList();
        }
```

State: `pickup: localStorage.getItem('fmtv_pickup') || 'on',`. SETTINGS (Look & Feel, after `showTrending`):

```javascript
            { id: 'pickup', cat: 1, type: 'choice', field: 'pickup', store: 'fmtv_pickup', def: 'on', label: 'Pick-up Row',
              hint: 'Shows the apps you opened last, above the shelf',
              options: ON_OFF,
              apply: function() { renderPickup(); } },
```

Boot sequence: call `renderPickup();` right before `renderAppsShelf();`. In `onVisibilityChange`, in the visible branch add `renderPickup();`. In `applyStaticTranslations` the header string is translated automatically (leaf node with a pt entry).

- [ ] **Step 6: Translations** (same insertion technique)

| key | pt | es | de | fr |
|---|---|---|---|---|
| `Pick up where you left off` | `Continue de onde parou` | `Sigue donde lo dejaste` | `Dort weitermachen, wo du aufgehört hast` | `Reprenez où vous en étiez` |
| `Today, %s` | `Hoje, %s` | `Hoy, %s` | `Heute, %s` | `Aujourd’hui, %s` |
| `Yesterday, %s` | `Ontem, %s` | `Ayer, %s` | `Gestern, %s` | `Hier, %s` |
| `Pick-up Row` | `Linha Continuar` | `Fila Seguir viendo` | `Weiterschauen-Zeile` | `Rangée Reprendre` |
| `Shows the apps you opened last, above the shelf` | `Mostra os apps abertos por último, acima da prateleira` | `Muestra las últimas apps abiertas, sobre el estante` | `Zeigt zuletzt geöffnete Apps über der Leiste` | `Affiche les dernières applis ouvertes, au-dessus de l’étagère` |

- [ ] **Step 7: SCENARIO step**

```javascript
  steps.push(function (done) { // the pick-up row lists the last apps, newest first, and hides when off or empty
    localStorage.removeItem('fmtv_launch_hist');
    state.pickup = 'on'; renderPickup();
    eq('pickup empty hidden', document.getElementById('pickupSection').hidden, true);
    var T = Date.now();
    recordLaunch('netflix', T - 5000); recordLaunch('youtube.leanback.v4', T - 1000);
    renderPickup();
    var cards = document.querySelectorAll('#pickupRow .pickup-card');
    eq('pickup cards', cards.length, 2);
    eq('pickup first is newest', cards[0].dataset.id, 'youtube.leanback.v4');
    eq('pickup in nav', mainNavItems.indexOf(cards[0]) !== -1, true);
    state.pickup = 'off'; renderPickup();
    eq('pickup off hidden', document.getElementById('pickupSection').hidden, true);
    localStorage.removeItem('fmtv_launch_hist'); state.pickup = 'on'; renderPickup();
    done();
  });
```

- [ ] **Step 8: `CHECK`, install, TV check**

On the TV: open Netflix from the shelf, return to Free My TV; the row must show Netflix with "Today, hh:mm" and be reachable with Up/Down. Screenshot to confirm the three layout rows (greeting, pick-up, shelf) still fit; if not, hide `.hero-desc` when the pick-up row is visible (add a body class and a CSS rule).

- [ ] **Step 9: Commit** (`feat: pick up where you left off row from local launch history`).

---

### Task 3: One focus ring everywhere

**Files:** Modify `app/index.html` CSS (blocks at ~lines 220, 244, 387, 493, 526 and the new `.pickup-card`), test in `scripts/browser_test.py`.

- [ ] **Step 1: Failing SCENARIO step**

```javascript
  steps.push(function (done) { // D-pad focus draws a white ring on every kind of focusable element
    var ids = ['customizeBtn', 'tvSettingsBtn', 'weatherWidget', 'tabMovies'];
    var els = ids.map(function (id) { return document.getElementById(id); });
    var tile = document.querySelector('.app-tile'), card = document.querySelector('.pick-card');
    if (tile) els.push(tile);
    if (card) els.push(card);
    els.forEach(function (el, i) {
      el.classList.add('focused');
      var cs = getComputedStyle(el);
      eq('ring style ' + i, cs.outlineStyle, 'solid');
      eq('ring width ' + i, cs.outlineWidth, '3px');
      el.classList.remove('focused');
    });
    done();
  });
```

Run `CHECK`; expected failures (`ring style 0: got "none"`).

- [ ] **Step 2: Add the shared rule** (after the existing `.focused` rules so it wins on order, not specificity)

```css
        /* One focus language: white ring + size + glow. Colour alone never marks focus. */
        .header-btn.focused, .weather-widget.focused, .app-tile.focused, .pick-card.focused,
        .picks-tab.focused, .pickup-card.focused .pickup-art, .scene-chip.focused {
            outline: 3px solid #ffffff;
            outline-offset: 3px;
        }
```

The test checks `.pickup-card.focused` itself, so for that class apply the outline to the card instead: use `.pickup-card.focused { outline: 3px solid #fff; outline-offset: 6px; border-radius: 14px; }` and drop the `.pickup-art` selector. (`.scene-chip` arrives in Task 6; the selector may exist before the element.)

- [ ] **Step 3: Run `CHECK` (green), install, screenshot** focus on a tile, a header button, the weather widget, a pick card and a tab. The ring must be visible on all four themes: cycle themes in Customize → Look & Feel and re-shoot Daylight Blue in particular (white ring on a light background: add `.theme-day` override `outline-color: #0a2a5e`).

- [ ] **Step 4: Commit** (`feat: one white focus ring for every focusable element`).

---

### Task 4: Evening dimming and a quiet night screensaver

**Files:** Modify `app/index.html` (`ambientPlayer.show` opacity line, `updateClock`, markup in `.screensaver-clock-wrap`, CSS, SETTINGS, state, I18N), `scripts/browser_test.py`.

**Interfaces:** Produces `nightFactor(now, sunsetStr) -> 1|0.75|0.5`, `ambientNightFactor()`, `state.nightDim` (`'on'|'off'`, setting `nightDim`, store `fmtv_night_dim`).

Rules: from 23:00 until 05:00 the factor is `0.5`; between today's sunset time and 23:00 it is `0.75`; otherwise `1`. When the sunset time is unknown, assume 18:00.

- [ ] **Step 1: Failing probe**

```javascript
  if (need('nightFactor')) {
    eq('night noon', nightFactor(new Date(2026, 9, 30, 12, 0), '16:52'), 1);
    eq('night before sunset', nightFactor(new Date(2026, 9, 30, 16, 51), '16:52'), 1);
    eq('night after sunset', nightFactor(new Date(2026, 9, 30, 16, 52), '16:52'), 0.75);
    eq('night 22:59', nightFactor(new Date(2026, 9, 30, 22, 59), '16:52'), 0.75);
    eq('night 23:00', nightFactor(new Date(2026, 9, 30, 23, 0), '16:52'), 0.5);
    eq('night 04:59', nightFactor(new Date(2026, 9, 30, 4, 59), '16:52'), 0.5);
    eq('night 05:00', nightFactor(new Date(2026, 9, 30, 5, 0), '16:52'), 1);
    eq('night unknown sunset', nightFactor(new Date(2026, 9, 30, 17, 59), ''), 1);
    eq('night unknown sunset after', nightFactor(new Date(2026, 9, 30, 18, 0), ''), 0.75);
  }
```

- [ ] **Step 2: Implement**

Beside `ambientBrightness`:

```javascript
        function nightFactor(now, sunsetStr) {
            var h = now.getHours();
            if (h >= 23 || h < 5) return 0.5;
            var m = /^(\d{1,2}):(\d{2})$/.exec(sunsetStr || '');
            var sunsetMin = m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : 18 * 60;
            return h * 60 + now.getMinutes() >= sunsetMin ? 0.75 : 1;
        }

        function ambientNightFactor() {
            return state.nightDim === 'off' ? 1 : nightFactor(new Date(), state.sunset);
        }
```

In `ambientPlayer.show`, multiply the opacity expression: `… * ambientBrightness() * ambientNightFactor() * 100) / 100`. State: `nightDim: localStorage.getItem('fmtv_night_dim') || 'on',`. SETTINGS (Photos & Screensaver, after `ambientBright`):

```javascript
            { id: 'nightDim', cat: 3, type: 'choice', field: 'nightDim', store: 'fmtv_night_dim', def: 'on', label: 'Dim Photos at Night',
              hint: 'A little dimmer after sunset, much dimmer after 23:00',
              options: ON_OFF },
```

- [ ] **Step 3: Keep existing opacity tests deterministic**

In `SCENARIO`, at the top of `reset()` add `state.nightDim = 'off';` (the existing tests assert exact opacities such as `0.85`). Also set it to `'off'` at the start of the Photo Brightness step if that step does not call `reset()`. Then add a step proving the setting works:

```javascript
  steps.push(function (done) { // Dim Photos at Night scales the opacity when on
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none'; state.nightDim = 'on'; state.ambientBright = 'normal';
    var realNow = window.nightFactor;
    window.nightFactor = function () { return 0.5; };
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var a = document.getElementById('ssPhotoA').style.opacity, b = document.getElementById('ssPhotoB').style.opacity;
      eq('night dim opacity', a === '0.43' || b === '0.43', true); // 0.85 * 0.5 = 0.425, rounded to 0.43
      exitScreensaver();
      window.nightFactor = realNow; state.nightDim = 'off';
      done();
    }, 400);
  });
```

(`ambientNightFactor` calls the global `nightFactor` by name at call time, so the stub works.)

- [ ] **Step 4: A weather line on the screensaver that goes away after 23:00**

Markup, under `#screensaverDate`: `<div class="screensaver-weather" id="screensaverWeather"></div>`; CSS: `.screensaver-weather { font-size: 20px; color: rgba(255,255,255,0.5); margin-top: 6px; } .screensaver-weather:empty { display: none; }`. In `updateClock()` add:

```javascript
            var hr = now.getHours();
            var weatherNow = document.getElementById('weatherText').textContent;
            document.getElementById('screensaverWeather').textContent = (hr >= 23 || hr < 5 || weatherNow === 'Loading...') ? '' : weatherNow;
```

Add to `I18N_SKIP_IDS`? Not needed (its text is runtime data, not a pt key, so `applyStaticTranslations` leaves it alone).

- [ ] **Step 5: Translations**: `Dim Photos at Night` (pt `Escurecer Fotos à Noite`, es `Atenuar Fotos de Noche`, de `Fotos nachts abdunkeln`, fr `Assombrir les photos la nuit`), `A little dimmer after sunset, much dimmer after 23:00` (pt `Um pouco mais escuro após o pôr do sol, bem mais após 23:00`, es `Algo más tenue tras la puesta de sol, mucho más tras las 23:00`, de `Nach Sonnenuntergang etwas dunkler, nach 23:00 viel dunkler`, fr `Un peu plus sombre après le coucher du soleil, bien plus après 23 h`).

- [ ] **Step 6: `CHECK`, install, TV check** by setting the TV clock is not possible; instead temporarily `localStorage.setItem` is not enough. Verify with a debug build or by running the headless test only, and confirm on the TV that the photo is dimmer after sunset (it is evening when this is built; compare against `Dim Photos at Night: Off`).

- [ ] **Step 7: Commit** (`feat: dim screensaver photos after sunset and at night`).

---

### Task 5: The privacy line

**Files:** Modify `app/index.html` (markup at the end of `.container`, CSS, I18N), `README.md`.

- [ ] **Step 1: Failing check**

SCENARIO step: `eq('trust line', !!document.getElementById('trustLine') && document.getElementById('trustLine').textContent.indexOf('No ads') !== -1 || document.getElementById('trustLine').textContent.indexOf(t('No ads. No account. Your settings stay on this TV.')) !== -1, true);` (English page contains `No ads`; other languages contain the translation).

- [ ] **Step 2: Markup and CSS** (after the `.picks-section` `</div>`, still inside the container)

```html
        <div class="trust-line" id="trustLine">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>
            <span>No ads. No account. Your settings stay on this TV.</span>
        </div>
```

```css
        .trust-line { display: flex; align-items: center; gap: 8px; margin-top: 14px; font-size: 15px; color: var(--text-secondary); }
```

`applyStaticTranslations` skips elements with children, so the text must sit in its own `<span>` (leaf) as shown.

- [ ] **Step 3: Translations**: `No ads. No account. Your settings stay on this TV.` → pt `Sem anúncios. Sem conta. Suas configurações ficam nesta TV.`, es `Sin anuncios. Sin cuenta. Tus ajustes se quedan en este TV.`, de `Keine Werbung. Kein Konto. Deine Einstellungen bleiben auf diesem Fernseher.`, fr `Pas de pub. Pas de compte. Vos réglages restent sur cette TV.`

- [ ] **Step 4: README**: add one sentence under the privacy/“what it connects to” section listing the four outbound services (weather, trending, photos, optional IP lookup) so the line is verifiably accurate. `CHECK`, commit (`feat: honest privacy line on the home screen`).

---

### Task 6: Scenes (one press, built from what the app can already do)

**Files:** Modify `app/index.html` (markup under the greeting, CSS, scene engine, `onVisibilityChange`, SETTINGS, boot, I18N), `scripts/browser_test.py`, `README.md`.

**Scope note:** these scenes use only things proven to work: opening an app (`launchApp`), and this app's own look (`theme`, `homePhotos`, `ambient`). Changing the TV's own picture mode or sleep timer is Task 10; its result may add steps to these scenes.

**Interfaces:** Produces `SCENES`, `pickSceneApp(spec, hist, catalog, hdmiChoices) -> app|null`, `runScene(id)`, `restoreScene()`, `renderScenes()`; `state.scenes` (setting `scenes`, store `fmtv_scenes`). Storage `fmtv_scene_restore` = JSON of the previous values.

- [ ] **Step 1: Failing probe**

```javascript
  if (need('pickSceneApp')) {
    var hist2 = { 'com.disney.disneyplus-prod': { t: 5, n: 1 }, netflix: { t: 9, n: 1 } };
    eq('scene streaming newest', pickSceneApp('streaming', hist2, DEFAULT_CATALOG, {}).id, 'netflix');
    eq('scene streaming none used', pickSceneApp('streaming', {}, DEFAULT_CATALOG, {}).id, 'youtube.leanback.v4');
    eq('scene game none named', pickSceneApp('game', {}, DEFAULT_CATALOG, {}), null);
    eq('scene game ps5', pickSceneApp('game', {}, DEFAULT_CATALOG, { 'com.webos.app.hdmi2': 'ps5' }).id, 'com.webos.app.hdmi2');
    eq('scene direct id', pickSceneApp('spotify-beehive', {}, DEFAULT_CATALOG, {}).id, 'spotify-beehive');
    eq('scene direct missing', pickSceneApp('nope', {}, DEFAULT_CATALOG, {}), null);
  }
```

- [ ] **Step 2: Implement the engine**

```javascript
        // --- Scenes: one press opens the right app and sets this app's own look ---
        var STREAMING_APPS = ['netflix', 'youtube.leanback.v4', 'amazon', 'com.disney.disneyplus-prod', 'com.crunchyroll.webapp', 'cdp-30'];
        var SCENES = [
            { id: 'movie', label: 'Movie night', icon: 'M3 5h18v14H3zM10 9l5 3-5 3z', look: { theme: 'oled', homePhotos: 'off' }, open: 'streaming' },
            { id: 'game', label: 'Game on', icon: 'M2 8h20v10H2zM7 11v4M5 13h4M16 12h.01M18 14h.01', look: { homePhotos: 'off' }, open: 'game' },
            { id: 'music', label: 'Background music', icon: 'M9 18V6l11-2v12M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM17 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', look: {}, open: 'spotify-beehive' }
        ];

        // spec: 'streaming' (last used streaming app, else the first one in the catalog), 'game' (first HDMI input
        // you named as a console or PC), or an app id.
        function pickSceneApp(spec, hist, catalog, hdmiChoices) {
            function find(id) { return arrFind(catalog, function(c) { return c.id === id; }) || null; }
            if (spec === 'streaming') {
                var ids = STREAMING_APPS.filter(function(id) { return find(id); });
                ids.sort(function(a, b) { return ((hist[b] && hist[b].t) || 0) - ((hist[a] && hist[a].t) || 0); });
                return ids.length ? find(ids[0]) : null;
            }
            if (spec === 'game') {
                return arrFind(catalog, function(c) { return isHDMI(c) && !!hdmiChoices[c.id] && hdmiChoices[c.id] !== 'default'; }) || null;
            }
            return find(spec);
        }

        function settingDef(id) { return arrFind(SETTINGS, function(d) { return d.id === id; }); }

        function runScene(id) {
            var scene = arrFind(SCENES, function(s) { return s.id === id; });
            if (!scene) return;
            var app = pickSceneApp(scene.open, readLaunchHist(), state.catalog, state.hdmiDevices);
            if (!app) { showToast(t('Name a device on an HDMI input in Customize first'), 4000); return; }
            var restore = {};
            Object.keys(scene.look).forEach(function(field) {
                if (state[field] !== scene.look[field]) { restore[field] = state[field]; }
            });
            if (Object.keys(restore).length) {
                try { localStorage.setItem('fmtv_scene_restore', JSON.stringify(restore)); } catch (e) {}
                Object.keys(scene.look).forEach(function(field) { var def = settingDef(field); if (def) setSettingValue(def, scene.look[field]); });
            }
            launchApp(app.id);
        }

        // When the app comes back to the front, put the look back the way it was before the scene.
        function restoreScene() {
            var restore = null;
            try { restore = JSON.parse(localStorage.getItem('fmtv_scene_restore') || 'null'); } catch (e) {}
            if (!restore) return;
            try { localStorage.removeItem('fmtv_scene_restore'); } catch (e) {}
            Object.keys(restore).forEach(function(field) { var def = settingDef(field); if (def) setSettingValue(def, restore[field]); });
        }

        function renderScenes() {
            var row = document.getElementById('scenesRow');
            row.innerHTML = '';
            row.hidden = state.scenes === 'off';
            if (state.scenes !== 'off') {
                SCENES.forEach(function(scene) {
                    var chip = document.createElement('button');
                    chip.className = 'scene-chip nav-item';
                    chip.dataset.tag = 'Scene';
                    chip.dataset.title = scene.label;
                    chip.dataset.desc = 'Opens the right app and sets the look for it. Back in this app, everything returns as it was.';
                    chip.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + scene.icon + '"/></svg>';
                    var label = document.createElement('span');
                    label.textContent = t(scene.label);
                    chip.appendChild(label);
                    chip.addEventListener('mouseenter', function() { setMainFocus(chip); });
                    chip.addEventListener('click', function() { runScene(scene.id); });
                    row.appendChild(chip);
                });
            }
            refreshMainNavList();
        }
```

State `scenes: localStorage.getItem('fmtv_scenes') || 'on',`. Setting (Look & Feel): `{ id: 'scenes', cat: 1, type: 'choice', field: 'scenes', store: 'fmtv_scenes', def: 'on', label: 'Scenes', hint: 'One-press Movie night, Game on and Music on the home screen', options: ON_OFF, apply: function() { renderScenes(); } }`. Boot: `renderScenes();` before `renderPickup();`. `onVisibilityChange` visible branch: add `restoreScene(); renderScenes();`.

- [ ] **Step 3: Markup (under the greeting, above the pick-up section) and CSS**

```html
        <div class="scenes-row" id="scenesRow"></div>
```

```css
        .scenes-row { display: flex; gap: 10px; margin-bottom: 18px; }
        .scenes-row[hidden] { display: none; }
        .scene-chip { display: flex; align-items: center; gap: 9px; height: 52px; padding: 0 22px; border-radius: 26px; background: rgba(255,255,255,0.12); border: 0; color: var(--text-primary); font-size: 18px; font-weight: 500; font-family: inherit; cursor: pointer; }
        .scene-chip.focused { transform: scale(1.06); background: rgba(255,255,255,0.22); }
```

- [ ] **Step 4: Translations.** `chip.dataset.title`, `.tag` and `.desc` go through `t()` in `setMainFocus`, so every English string below must exist in all four dictionaries (insert before `'Drift Speed': ` as in Task 1):

| key | pt | es | de | fr |
|---|---|---|---|---|
| `Movie night` | `Noite de filme` | `Noche de cine` | `Filmabend` | `Soirée cinéma` |
| `Game on` | `Hora do jogo` | `A jugar` | `Spielzeit` | `Place au jeu` |
| `Background music` | `Música de fundo` | `Música de fondo` | `Hintergrundmusik` | `Musique d’ambiance` |
| `Scenes` | `Cenas` | `Escenas` | `Szenen` | `Scènes` |
| `Scene` | `Cena` | `Escena` | `Szene` | `Scène` |
| `One-press Movie night, Game on and Music on the home screen` | `Noite de filme, jogo e música com um toque na tela inicial` | `Noche de cine, juego y música con una pulsación en el inicio` | `Filmabend, Spiel und Musik mit einem Tastendruck auf dem Startbildschirm` | `Soirée cinéma, jeu et musique en une pression sur l’écran d’accueil` |
| `Opens the right app and sets the look for it. Back in this app, everything returns as it was.` | `Abre o app certo e ajusta o visual. De volta a este app, tudo volta como era.` | `Abre la app adecuada y ajusta el aspecto. Al volver a esta app, todo queda como estaba.` | `Öffnet die passende App und stellt das Aussehen ein. Zurück in dieser App ist alles wie vorher.` | `Ouvre la bonne appli et règle l’apparence. De retour ici, tout redevient comme avant.` |
| `Name a device on an HDMI input in Customize first` | `Primeiro nomeie um dispositivo em uma entrada HDMI em Personalizar` | `Primero nombra un dispositivo en una entrada HDMI en Personalizar` | `Benenne zuerst in Anpassen ein Gerät an einem HDMI-Eingang` | `Nommez d’abord un appareil sur une entrée HDMI dans Personnaliser` |

- [ ] **Step 5: SCENARIO test**

```javascript
  steps.push(function (done) { // Movie night switches the look, opens an app, and coming back restores the look
    var calls = [], oldWebOS = window.webOS;
    window.webOS = { service: { request: function (uri, o) { calls.push(o); } } };
    state.theme = 'auto'; state.homePhotos = 'on';
    localStorage.removeItem('fmtv_scene_restore');
    runScene('movie');
    eq('scene theme', state.theme, 'oled');
    eq('scene photos', state.homePhotos, 'off');
    eq('scene launched', calls.length > 0 && /^(netflix|youtube\.leanback\.v4|amazon|com\.disney\.disneyplus-prod|com\.crunchyroll\.webapp|cdp-30)$/.test(calls[0].parameters.id), true);
    if (calls[0]) calls[0].onSuccess({ returnValue: true });
    restoreScene();
    eq('scene restored theme', state.theme, 'auto');
    eq('scene restored photos', state.homePhotos, 'on');
    eq('scene restore key gone', localStorage.getItem('fmtv_scene_restore'), null);
    var before = calls.length;
    state.hdmiDevices = {};
    runScene('game');
    eq('game scene without a named device launches nothing', calls.length, before);
    var chips = document.querySelectorAll('#scenesRow .scene-chip');
    eq('scene chips', chips.length, SCENES.length);
    state.scenes = 'off'; renderScenes();
    eq('scenes hidden when off', document.getElementById('scenesRow').hidden, true);
    state.scenes = 'on'; renderScenes();
    window.webOS = oldWebOS;
    done();
  });
```

- [ ] **Step 6: `CHECK`, install, TV check:** press the Movie night chip: Netflix (or the last used streaming app) opens, press Home, reopen Free My TV: theme is back. Screenshot the chips row and the focus ring.

- [ ] **Step 7: Commit** (`feat: one-press scenes (Movie night, Game on, Background music)`).

---

### Task 7: First-run setup wizard

**Files:** Modify `app/index.html` (overlay markup, CSS, wizard engine, key routing, SETTINGS `run` row, boot, I18N), `scripts/browser_test.py`, `README.md`.

**Interfaces:** Produces `WIZARD_STEPS`, `wizardNeeded()`, `openWizard()`, `closeWizard(done)`, `renderWizard()`, `handleWizardKey(e)`; storage `fmtv_setup_done` = `'1'`.

Behaviour (from board 4): 5 steps + done: Welcome → Your name and city → Your apps → Your look → Screensaver photos. Remote: Left/Right and Up/Down move focus, OK activates, Back goes to the previous step (first step: Back leaves the wizard like "Skip"). It must never block someone who just wants the app: a `Skip setup` button exists on every step.

- [ ] **Step 1: Failing probe**

```javascript
  if (need('wizardNeeded')) {
    var keep = { done: localStorage.getItem('fmtv_setup_done'), fav: localStorage.getItem('fmtv_favorites'), city: state.city };
    localStorage.removeItem('fmtv_setup_done'); localStorage.removeItem('fmtv_favorites'); state.city = '';
    eq('wizard fresh', wizardNeeded(), true);
    localStorage.setItem('fmtv_favorites', '["netflix"]');
    eq('wizard existing user', wizardNeeded(), false);
    localStorage.removeItem('fmtv_favorites'); state.city = 'Tel Aviv';
    eq('wizard has city', wizardNeeded(), false);
    state.city = ''; localStorage.setItem('fmtv_setup_done', '1');
    eq('wizard done', wizardNeeded(), false);
    localStorage.removeItem('fmtv_setup_done');
    if (keep.done !== null) localStorage.setItem('fmtv_setup_done', keep.done);
    if (keep.fav !== null) localStorage.setItem('fmtv_favorites', keep.fav);
    state.city = keep.city;
  }
```

(Existing users, who already have a stored shelf or a city, are never shown the wizard on upgrade.)

- [ ] **Step 2: Engine**

```javascript
        // --- First-run setup ---
        var WIZARD_STEPS = ['welcome', 'who', 'apps', 'look', 'photos', 'done'];
        var WIZARD_LOOKS = [
            { key: 'auto', label: 'Follow the sun', desc: 'Light by day, warm at sunset, dark at night.' },
            { key: 'night', label: 'Deep Midnight', desc: 'Blue-black, easy on eyes in a dark room.' },
            { key: 'oled', label: 'Pure Black', desc: 'True black for movies and OLED panels.' },
            { key: 'day', label: 'Daylight Blue', desc: 'Bright and airy for a sunny living room.' }
        ];
        var wizard = { open: false, step: 0, focus: 0 };

        function wizardNeeded() {
            var done = null, favs = null;
            try { done = localStorage.getItem('fmtv_setup_done'); favs = localStorage.getItem('fmtv_favorites'); } catch (e) {}
            return !done && !favs && !state.city;
        }
```

Complete code for the wizard (place it after `wizardNeeded`):

```javascript
        function wzEl(tag, cls, text) {
            var e = document.createElement(tag);
            if (cls) e.className = cls;
            if (text !== undefined) e.textContent = text;
            return e;
        }

        function wzButton(label, onOk) {
            var b = wzEl('button', 'wz-item wz-button', t(label));
            b.onOk = onOk;
            b.onclick = function() { onOk(); };
            return b;
        }

        function wizardGo(step) {
            wizard.step = Math.max(0, Math.min(step, WIZARD_STEPS.length - 1));
            wizard.focus = 0;
            renderWizard();
        }

        function paintWizardFocus() {
            wizard.items.forEach(function(item, i) { item.classList.toggle('focused', i === wizard.focus); });
        }

        function wizardMove(delta) {
            var next = Math.max(0, Math.min(wizard.focus + delta, wizard.items.length - 1));
            if (next === wizard.focus) return;
            wizard.focus = next;
            paintWizardFocus();
            var look = wizard.items[next].dataset.look;
            if (look) setSettingValue(settingDef('theme'), look); // moving over a look previews it
        }

        function renderWizard() {
            var main = document.getElementById('wizardMain');
            var rail = document.getElementById('wizardRail');
            main.innerHTML = '';
            rail.innerHTML = '';
            var name = WIZARD_STEPS[wizard.step];
            var items = [];
            var railLabels = ['Welcome', 'Your name and city', 'Your apps', 'Your look', 'Screensaver photos'];
            railLabels.forEach(function(label, i) {
                var r = wzEl('div', 'wz-rail-row' + (i === wizard.step ? ' current' : (i < wizard.step ? ' done' : '')), t(label));
                rail.appendChild(r);
            });
            function title(text) { main.appendChild(wzEl('div', 'wz-title', text)); }
            function lead(text) { main.appendChild(wzEl('div', 'wz-lead', text)); }
            function add(el) { items.push(el); main.appendChild(el); }

            if (name === 'welcome') {
                title(t('Welcome to Free My TV'));
                lead(t('A quiet home screen with no ads. This takes about a minute and every choice can be changed later in Customize.'));
                add(wzButton('Start', function() { wizardGo(1); }));
                add(wzButton('Skip setup', function() { closeWizard(false); }));
            } else if (name === 'who') {
                title(t('Your name and city'));
                lead(t('Used for the greeting and the weather. Leave the city empty to find it automatically.'));
                var nameInput = wzEl('input', 'wz-item wz-input');
                nameInput.id = 'wzName';
                nameInput.placeholder = t('e.g. Noa');
                nameInput.value = state.userName || '';
                nameInput.oninput = function() { setSettingValue(settingDef('userName'), nameInput.value); };
                var cityInput = wzEl('input', 'wz-item wz-input');
                cityInput.id = 'wzCity';
                cityInput.placeholder = t('e.g. Sao Paulo, Lisbon, NYC');
                cityInput.value = state.city || '';
                cityInput.oninput = function() { state.city = cityInput.value; try { localStorage.setItem('fmtv_city', state.city); } catch (e) {} };
                nameInput.onOk = function() { nameInput.focus(); };
                cityInput.onOk = function() { cityInput.focus(); };
                add(nameInput);
                add(cityInput);
                add(wzButton('Continue', function() { scheduleSettingsNetwork(true, false); wizardGo(2); }));
                add(wzButton('Skip setup', function() { closeWizard(false); }));
            } else if (name === 'apps') {
                title(t('Your apps'));
                lead(t('Pick up to 8 for your shelf.'));
                var grid = wzEl('div', 'wz-grid wz-apps');
                state.catalog.forEach(function(app) {
                    var on = state.favorites.indexOf(app.id) !== -1;
                    var tile = wzEl('button', 'wz-item wz-tile' + (on ? ' on' : ''), app.title);
                    tile.setAttribute('aria-pressed', String(on));
                    tile.onOk = function() {
                        var result = toggleFavorite(app.id);
                        if (result === 'full') showToast(t('Max 8 apps on shelf'), 3000);
                        else if (result === 'last') showToast(t('Keep at least one app on the shelf.'), 3000);
                        var keep = wizard.focus;
                        renderWizard();
                        wizard.focus = keep;
                        paintWizardFocus();
                    };
                    tile.onclick = tile.onOk;
                    items.push(tile);
                    grid.appendChild(tile);
                });
                main.appendChild(grid);
                add(wzButton('Continue', function() { wizardGo(3); }));
            } else if (name === 'look') {
                title(t('How should it look?'));
                lead(t('Pick one. The whole screen changes as you move over it.'));
                var cards = wzEl('div', 'wz-grid wz-looks');
                WIZARD_LOOKS.forEach(function(look) {
                    var card = wzEl('button', 'wz-item wz-look' + (state.theme === look.key ? ' on' : ''));
                    card.dataset.look = look.key;
                    card.appendChild(wzEl('div', 'wz-look-name', t(look.label)));
                    card.appendChild(wzEl('div', 'wz-look-desc', t(look.desc)));
                    card.onOk = function() { setSettingValue(settingDef('theme'), look.key); wizard.focus = items.length - 1; paintWizardFocus(); };
                    card.onclick = card.onOk;
                    items.push(card);
                    cards.appendChild(card);
                });
                main.appendChild(cards);
                add(wzButton('Continue', function() { wizardGo(4); }));
            } else if (name === 'photos') {
                title(t('Screensaver photos'));
                lead(t('When the TV is idle it shows photos behind the clock. You can add your free Unsplash key later in Customize.'));
                var toggle = wzButton(state.ambient === 'on' ? 'Photo screensaver: On' : 'Photo screensaver: Off', function() {
                    setSettingValue(settingDef('ambient'), state.ambient === 'on' ? 'off' : 'on');
                    var keep = wizard.focus;
                    renderWizard();
                    wizard.focus = keep;
                    paintWizardFocus();
                });
                add(toggle);
                add(wzButton('Finish', function() { wizardGo(5); }));
                add(wzButton('Skip setup', function() { closeWizard(false); }));
            } else {
                title(t('Your TV is ready'));
                lead(t('Everything stays on this TV. Change anything later in Customize.'));
                add(wzButton('Open my home screen', function() { closeWizard(true); }));
            }
            wizard.items = items;
            if (wizard.focus >= items.length) wizard.focus = 0;
            paintWizardFocus();
        }

        function openWizard() {
            wizard.open = true;
            wizard.step = 0;
            wizard.focus = 0;
            document.getElementById('wizardOverlay').hidden = false;
            renderWizard();
        }

        function closeWizard() {
            wizard.open = false;
            document.getElementById('wizardOverlay').hidden = true;
            try { localStorage.setItem('fmtv_setup_done', '1'); } catch (e) {}
            applyTheme(); renderAppsShelf(); renderPickup(); updateGreeting();
            refreshMainNavList();
            setMainFocus(mainNavItems[curIndex]);
        }

        function handleWizardKey(e) {
            var key = e.key;
            var active = document.activeElement;
            var typing = active && active.tagName === 'INPUT';
            var back = e.keyCode === 461 || key === 'Escape' || key === 'GoBack';
            if (typing) {
                if (key === 'Enter') { active.blur(); wizardMove(1); e.preventDefault(); }
                else if (back) { active.blur(); e.preventDefault(); }
                return;
            }
            var name = WIZARD_STEPS[wizard.step];
            var cols = name === 'apps' ? 4 : (name === 'look' ? 2 : 1);
            var inGrid = name === 'apps' || name === 'look';
            var gridCount = name === 'apps' ? state.catalog.length : (name === 'look' ? WIZARD_LOOKS.length : 0);
            if (back) { if (wizard.step === 0) closeWizard(); else wizardGo(wizard.step - 1); e.preventDefault(); return; }
            if (key === 'Enter') {
                var item = wizard.items[wizard.focus];
                if (item && item.onOk) item.onOk();
                e.preventDefault();
                return;
            }
            var delta = 0;
            if (key === 'ArrowRight') delta = 1;
            else if (key === 'ArrowLeft') delta = -1;
            else if (key === 'ArrowDown') delta = inGrid && wizard.focus < gridCount ? cols : 1;
            else if (key === 'ArrowUp') delta = inGrid && wizard.focus < gridCount ? -cols : -1;
            else return;
            if (!inGrid && (key === 'ArrowLeft' || key === 'ArrowRight')) { e.preventDefault(); return; }
            // From the last grid row, Down lands on the button after the grid.
            if (inGrid && key === 'ArrowDown' && wizard.focus < gridCount && wizard.focus + cols >= gridCount) delta = gridCount - wizard.focus;
            wizardMove(delta);
            e.preventDefault();
        }
```

Markup for the overlay (put before the Customize modal):

```html
    <div class="wizard" id="wizardOverlay" hidden>
        <aside class="wz-rail" id="wizardRail"></aside>
        <section class="wz-main" id="wizardMain"></section>
    </div>
```

CSS (mirrors board 4):

```css
        .wizard { position: fixed; inset: 0; z-index: 2500; display: flex; gap: 56px; padding: 64px; background: linear-gradient(180deg, #0f1528 0%, #080b16 100%); color: #f2f5fb; }
        .wizard[hidden] { display: none; }
        .wz-rail { width: 300px; flex: none; display: flex; flex-direction: column; gap: 6px; padding-top: 70px; }
        .wz-rail-row { font-size: 22px; color: #8c97ae; padding: 10px 0; }
        .wz-rail-row.current { color: #fff; font-weight: 600; }
        .wz-rail-row.done { color: #7fd8a8; }
        .wz-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
        .wz-title { font-size: 48px; font-weight: 700; line-height: 1.08; }
        .wz-lead { font-size: 22px; color: #b3bdd3; max-width: 900px; }
        .wz-button, .wz-input { height: 64px; padding: 0 28px; border-radius: 32px; border: 0; background: rgba(255,255,255,0.12); color: inherit; font-size: 22px; font-family: inherit; text-align: left; align-self: flex-start; min-width: 360px; box-sizing: border-box; }
        .wz-grid { display: grid; gap: 14px; }
        .wz-apps { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        .wz-looks { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .wz-tile, .wz-look { min-height: 72px; border-radius: 14px; border: 0; padding: 12px 18px; background: rgba(255,255,255,0.08); color: inherit; font-size: 20px; font-family: inherit; text-align: left; }
        .wz-tile.on, .wz-look.on { background: rgba(77,163,255,0.22); }
        .wz-look-name { font-size: 24px; font-weight: 600; }
        .wz-look-desc { font-size: 17px; color: #b3bdd3; margin-top: 4px; }
        .wz-item.focused { outline: 3px solid #ffffff; outline-offset: 3px; transform: scale(1.03); }
```

Layout of each step's focus items (what `wizard.items` holds, in order):

| step | items (in focus order) | OK on item |
|---|---|---|
| welcome | `Start`, `Skip setup` | next step / close |
| who | name input, city input, `Continue`, `Skip setup` | input: `focus()` (TV keyboard); Enter in an input: move to next item |
| apps | one toggle per `state.catalog` entry (4 columns), `Continue` | `toggleFavorite(id)` then re-render, keep focus; full shelf shows the existing `Max 8 apps on shelf` toast |
| look | 4 look cards, `Continue` | focusing a card applies it at once (`setSettingValue(settingDef('theme'), key)`); OK confirms and moves to Continue |
| photos | `Photo screensaver: On/Off` toggle, `Finish`, `Skip setup` | toggle: `setSettingValue(settingDef('ambient'), …)` |
| done | `Open my home screen` | `closeWizard(true)` |

Route the wizard's keys in the global `keydown` listener right after the screensaver check and before the `shelfEdit` block: `if (wizard.open) { handleWizardKey(e); return; }`. Also stop `setMainFocus` from stealing DOM focus while the wizard is open (extend the existing `modalOpen` guard to `if (modalOpen || wizard.open) ...`). Boot: `if (wizardNeeded()) openWizard();` after the first render.

The code above persists the name and city as the user types and calls `scheduleSettingsNetwork(true, false)` (the call the City setting uses) when leaving the name-and-city step so the weather loads for the new city.

Every exit (Skip, Back on the first step, Open my home screen) goes through `closeWizard()`, which writes `fmtv_setup_done = '1'` so the wizard never nags again.

- [ ] **Step 3: Markup and CSS**

Overlay `<div class="wizard" id="wizardOverlay" hidden>` with `<aside class="wz-rail" id="wizardRail">` (steps list with check, current and upcoming states) and `<section class="wz-main" id="wizardMain">`; CSS mirrors board 4 (`.wizard { position: fixed; inset: 0; z-index: 2500; background: linear-gradient(180deg,#0f1528,#080b16); display: flex; gap: 56px; padding: 64px; }`, big type 44px title, 18px copy, 64px+ buttons, focus ring from Task 3: add `.wz-item.focused` to the shared ring rule). Its `z-index` is below the screensaver (3000) and above the Customize screen.

- [ ] **Step 4: "Run setup again"** row. In SETTINGS (Look & Feel, last): `{ id: 'runSetup', cat: 1, type: 'run', label: 'Run setup again', run: function() { closeSettingsModal(); openWizard(); } }`. In `renderSettings`, add `|| def.type === 'run'` to the `link` branch but with `sr-edit` text `t('OK to run')` and no value span; in `activateRow` add `else if (def.type === 'run') { def.run(); return; }`. `resetAllSettings` skips defs without `field`, so `run` rows are safe (it already does `if (!def.field) return;`). Boot: `if (wizardNeeded()) openWizard();` after the first render.

- [ ] **Step 5: Translations** (insert before `'Drift Speed': ` in each dictionary, as in Task 1):

| key | pt | es | de | fr |
|---|---|---|---|---|
| `Welcome to Free My TV` | `Bem-vindo ao Free My TV` | `Te damos la bienvenida a Free My TV` | `Willkommen bei Free My TV` | `Bienvenue sur Free My TV` |
| `A quiet home screen with no ads. This takes about a minute and every choice can be changed later in Customize.` | `Uma tela inicial tranquila, sem anúncios. Leva cerca de um minuto e tudo pode ser mudado depois em Personalizar.` | `Una pantalla de inicio tranquila y sin anuncios. Tarda un minuto y todo se puede cambiar luego en Personalizar.` | `Ein ruhiger Startbildschirm ohne Werbung. Das dauert etwa eine Minute und alles lässt sich später in Anpassen ändern.` | `Un écran d’accueil calme, sans pub. Cela prend environ une minute et tout se change ensuite dans Personnaliser.` |
| `Start` | `Começar` | `Empezar` | `Los geht’s` | `Commencer` |
| `Continue` | `Continuar` | `Continuar` | `Weiter` | `Continuer` |
| `Finish` | `Concluir` | `Terminar` | `Fertig` | `Terminer` |
| `Skip setup` | `Pular configuração` | `Omitir configuración` | `Einrichtung überspringen` | `Passer la configuration` |
| `Open my home screen` | `Abrir minha tela inicial` | `Abrir mi pantalla de inicio` | `Meinen Startbildschirm öffnen` | `Ouvrir mon écran d’accueil` |
| `Welcome` | `Boas-vindas` | `Bienvenida` | `Willkommen` | `Bienvenue` |
| `Your name and city` | `Seu nome e cidade` | `Tu nombre y ciudad` | `Dein Name und Ort` | `Votre prénom et ville` |
| `Used for the greeting and the weather. Leave the city empty to find it automatically.` | `Usados na saudação e no clima. Deixe a cidade vazia para encontrá-la automaticamente.` | `Se usan para el saludo y el tiempo. Deja la ciudad vacía para encontrarla automáticamente.` | `Für Begrüßung und Wetter. Ort leer lassen, um ihn automatisch zu finden.` | `Utilisés pour l’accueil et la météo. Laissez la ville vide pour la trouver automatiquement.` |
| `Your apps` | `Seus apps` | `Tus apps` | `Deine Apps` | `Vos applis` |
| `Pick up to 8 for your shelf.` | `Escolha até 8 para a prateleira.` | `Elige hasta 8 para tu estante.` | `Wähle bis zu 8 für deine Leiste.` | `Choisissez-en jusqu’à 8 pour votre étagère.` |
| `Your look` | `Seu visual` | `Tu aspecto` | `Dein Look` | `Votre style` |
| `How should it look?` | `Como deve ficar?` | `¿Cómo quieres que se vea?` | `Wie soll es aussehen?` | `Quel style voulez-vous ?` |
| `Pick one. The whole screen changes as you move over it.` | `Escolha um. A tela inteira muda ao passar por ele.` | `Elige uno. Toda la pantalla cambia al pasar sobre él.` | `Wähle einen. Der ganze Bildschirm ändert sich, sobald du darüber gehst.` | `Choisissez-en un. Tout l’écran change quand vous le survolez.` |
| `Follow the sun` | `Seguir o sol` | `Seguir al sol` | `Der Sonne folgen` | `Suivre le soleil` |
| `Light by day, warm at sunset, dark at night.` | `Claro de dia, quente no pôr do sol, escuro à noite.` | `Claro de día, cálido al atardecer, oscuro de noche.` | `Hell am Tag, warm bei Sonnenuntergang, dunkel in der Nacht.` | `Clair le jour, chaud au coucher du soleil, sombre la nuit.` |
| `Deep Midnight` | `Meia-noite Profunda` | `Medianoche Profunda` | `Tiefe Mitternacht` | `Minuit profond` |
| `Blue-black, easy on eyes in a dark room.` | `Azul-escuro, confortável em ambiente escuro.` | `Azul oscuro, suave a la vista en una sala oscura.` | `Blauschwarz, schonend für die Augen im dunklen Raum.` | `Bleu nuit, reposant dans une pièce sombre.` |
| `Pure Black` | `Preto Puro` | `Negro Puro` | `Reines Schwarz` | `Noir pur` |
| `True black for movies and OLED panels.` | `Preto real para filmes e telas OLED.` | `Negro real para películas y paneles OLED.` | `Echtes Schwarz für Filme und OLED-Displays.` | `Noir absolu pour les films et les écrans OLED.` |
| `Daylight Blue` | `Azul Diurno` | `Azul Diurno` | `Tageslichtblau` | `Bleu lumière du jour` |
| `Bright and airy for a sunny living room.` | `Claro e arejado para uma sala ensolarada.` | `Luminoso y aireado para un salón soleado.` | `Hell und luftig für ein sonniges Wohnzimmer.` | `Lumineux et aéré pour un salon ensoleillé.` |
| `Screensaver photos` | `Fotos do protetor de tela` | `Fotos del protector` | `Bildschirmschoner-Fotos` | `Photos de l’écran de veille` |
| `When the TV is idle it shows photos behind the clock. You can add your free Unsplash key later in Customize.` | `Com a TV parada, mostra fotos atrás do relógio. Você pode adicionar sua chave Unsplash gratuita depois em Personalizar.` | `Con la TV en reposo muestra fotos tras el reloj. Puedes añadir tu clave gratuita de Unsplash luego en Personalizar.` | `Im Leerlauf zeigt der Fernseher Fotos hinter der Uhr. Deinen kostenlosen Unsplash-Schlüssel kannst du später in Anpassen eintragen.` | `En veille, la TV affiche des photos derrière l’horloge. Vous pourrez ajouter votre clé Unsplash gratuite plus tard dans Personnaliser.` |
| `Photo screensaver: On` | `Protetor de fotos: Ligado` | `Protector con fotos: Activado` | `Foto-Bildschirmschoner: An` | `Écran de veille photo : activé` |
| `Photo screensaver: Off` | `Protetor de fotos: Desligado` | `Protector con fotos: Desactivado` | `Foto-Bildschirmschoner: Aus` | `Écran de veille photo : désactivé` |
| `Your TV is ready` | `Sua TV está pronta` | `Tu TV está lista` | `Dein Fernseher ist bereit` | `Votre TV est prête` |
| `Everything stays on this TV. Change anything later in Customize.` | `Tudo fica nesta TV. Mude o que quiser depois em Personalizar.` | `Todo se queda en este TV. Cambia lo que quieras luego en Personalizar.` | `Alles bleibt auf diesem Fernseher. Ändere später alles in Anpassen.` | `Tout reste sur cette TV. Modifiez ce que vous voulez plus tard dans Personnaliser.` |
| `Run setup again` | `Repetir a configuração` | `Repetir la configuración` | `Einrichtung erneut starten` | `Relancer la configuration` |
| `OK to run` | `OK para executar` | `OK para ejecutar` | `OK zum Starten` | `OK pour lancer` |

Before inserting, grep each English key in the dictionaries: `Continue`, `Start`, `Welcome` and `Finish` may already exist; skip existing keys so no dictionary gets a duplicate. `e.g. Sao Paulo, Lisbon, NYC`, `Max 8 apps on shelf` and `Keep at least one app on the shelf.` already exist.

- [ ] **Step 6: Tests (SCENARIO)**

```javascript
  steps.push(function (done) { // the setup wizard walks every step with the remote and saves name, look and photos
    localStorage.removeItem('fmtv_setup_done');
    var oldTheme = state.theme, oldName = state.userName, oldAmbient = state.ambient, oldFavs = state.favorites.slice();
    function key(k) { handleWizardKey({ key: k, keyCode: 0, preventDefault: function () {} }); }
    openWizard();
    eq('wizard open', wizard.open && !document.getElementById('wizardOverlay').hidden, true);
    eq('wizard step welcome', WIZARD_STEPS[wizard.step], 'welcome');
    key('Enter');
    eq('wizard step who', WIZARD_STEPS[wizard.step], 'who');
    var nameInput = document.getElementById('wzName');
    nameInput.value = 'Noa'; nameInput.dispatchEvent(new Event('input'));
    eq('wizard name saved', state.userName, 'Noa');
    wizard.focus = wizard.items.length - 2; key('Enter');
    eq('wizard step apps', WIZARD_STEPS[wizard.step], 'apps');
    var firstApp = state.catalog[0].id, had = state.favorites.indexOf(firstApp) !== -1;
    wizard.focus = 0; key('Enter');
    eq('wizard toggles an app', state.favorites.indexOf(firstApp) !== -1, !had);
    wizard.focus = wizard.items.length - 1; key('Enter');
    eq('wizard step look', WIZARD_STEPS[wizard.step], 'look');
    wizard.focus = 0; key('ArrowRight');
    eq('wizard previews a look', state.theme, 'night');
    key('Enter');
    eq('wizard look confirm moves to Continue', wizard.focus, wizard.items.length - 1);
    key('Enter');
    eq('wizard step photos', WIZARD_STEPS[wizard.step], 'photos');
    state.ambient = 'on'; renderWizard(); wizard.focus = 0; key('Enter');
    eq('wizard photos toggle', state.ambient, 'off');
    wizard.focus = 1; key('Enter');
    eq('wizard step done', WIZARD_STEPS[wizard.step], 'done');
    key('Enter');
    eq('wizard closed', wizard.open, false);
    eq('wizard remembered', localStorage.getItem('fmtv_setup_done'), '1');
    eq('wizard no longer needed', wizardNeeded(), false);
    openWizard(); key('Escape');
    eq('wizard back on first step closes', wizard.open, false);
    state.theme = oldTheme; state.userName = oldName; state.ambient = oldAmbient; state.favorites = oldFavs;
    applyTheme(); renderAppsShelf();
    localStorage.removeItem('fmtv_setup_done');
    done();
  });
```

- [ ] **Step 7: `CHECK`; TV check:** clear app data (`Remove` the app and reinstall or run `localStorage.clear()` via a debug build) to see the wizard from the sofa; walk it with the remote only; confirm the TV keyboard opens for the name field and Back closes it.

- [ ] **Step 8: Commit** (`feat: first-run setup wizard`).

---

### Task 8: Profiles ("Who is watching?")

**Files:** Modify `app/index.html`, `scripts/browser_test.py`, `README.md`.

**Interfaces:** Produces `PROFILE_FIELDS`, `snapshotProfile()`, `applyProfile(p)`, `readProfiles()`, `saveProfiles(list)`, `activeProfileId()`, `switchProfile(id)`, `openProfilePicker()`; storage `fmtv_profiles` (JSON array) and `fmtv_active_profile`.

A profile is a snapshot of: `userName`, `favorites`, `theme`, `city`, `lat`, `lon`, `hdmiDevices`, `ambient`, `homePhotos`, `locked` (boolean: hides Customize and TV Settings buttons). It is stored only on the TV; it is not an account.

- [ ] **Step 1: Failing probe**

```javascript
  if (need('snapshotProfile') && need('applyProfile')) {
    var before = JSON.stringify(snapshotProfile());
    var snap = snapshotProfile();
    snap.userName = 'Kid'; snap.theme = 'day'; snap.favorites = ['youtube.leanback.v4'];
    applyProfile(snap);
    eq('profile name', state.userName, 'Kid');
    eq('profile theme', state.theme, 'day');
    eq('profile shelf', state.favorites.join(','), 'youtube.leanback.v4');
    eq('profile persisted', localStorage.getItem('fmtv_theme'), 'day');
    applyProfile(JSON.parse(before));
    eq('profile restored', JSON.stringify(snapshotProfile()), before);
  }
```

- [ ] **Step 2: Implement**

```javascript
        var PROFILE_FIELDS = ['userName', 'theme', 'city', 'lat', 'lon', 'ambient', 'homePhotos'];

        function snapshotProfile() {
            var p = { favorites: state.favorites.slice(), hdmiDevices: JSON.parse(JSON.stringify(state.hdmiDevices)), locked: !!state.locked };
            PROFILE_FIELDS.forEach(function(f) { p[f] = state[f]; });
            return p;
        }

        // Write a snapshot into state + storage, then refresh everything that shows it.
        function applyProfile(p) {
            PROFILE_FIELDS.forEach(function(f) {
                if (p[f] === undefined) return;
                state[f] = p[f];
                var def = settingDef(f);
                var store = def ? def.store : (f === 'lat' ? 'fmtv_lat' : (f === 'lon' ? 'fmtv_lon' : ''));
                if (store) { try { localStorage.setItem(store, String(p[f])); } catch (e) {} }
            });
            if (p.favorites) { state.favorites = p.favorites.slice(); try { localStorage.setItem('fmtv_favorites', JSON.stringify(state.favorites)); } catch (e) {} }
            if (p.hdmiDevices) { state.hdmiDevices = JSON.parse(JSON.stringify(p.hdmiDevices)); try { localStorage.setItem('fmtv_hdmi_devices', JSON.stringify(state.hdmiDevices)); } catch (e) {} }
            state.locked = !!p.locked;
            applyTheme(); renderAppsShelf(); renderPickup(); updateGreeting(); applyLock();
            fetchWeather(); applyHomePhotosSettings(); ambientRefresh(false);
        }
```

(`applyLock()` toggles `hidden` on `#customizeBtn` and `#tvSettingsBtn` from `state.locked` and calls `refreshMainNavList()`.)

Profile list, switching, lock and picker (add after `applyProfile`):

```javascript
        function readProfiles() {
            try {
                var list = JSON.parse(localStorage.getItem('fmtv_profiles') || '[]');
                return Array.isArray(list) ? list.filter(function(p) { return p && p.id && p.name && p.data; }) : [];
            } catch (e) { return []; }
        }

        function saveProfiles(list) {
            try { localStorage.setItem('fmtv_profiles', JSON.stringify(list)); } catch (e) {}
        }

        function activeProfileId() {
            try { return localStorage.getItem('fmtv_active_profile') || ''; } catch (e) { return ''; }
        }

        function shouldAskWho() {
            return readProfiles().length >= 2 && state.askWho === 'on';
        }

        // Show or hide the settings buttons for a locked (kids) profile.
        function applyLock() {
            ['customizeBtn', 'tvSettingsBtn'].forEach(function(id) { document.getElementById(id).hidden = !!state.locked; });
            refreshMainNavList();
        }

        // Save the current person's state into their profile, then load the chosen person.
        function switchProfile(id) {
            var list = readProfiles();
            var current = activeProfileId();
            list.forEach(function(p) { if (p.id === current) p.data = snapshotProfile(); });
            var target = arrFind(list, function(p) { return p.id === id; });
            if (!target) return;
            saveProfiles(list);
            try { localStorage.setItem('fmtv_active_profile', id); } catch (e) {}
            applyProfile(target.data);
        }

        function addProfile(name) {
            var list = readProfiles();
            if (!list.length) list.push({ id: 'p0', name: state.userName || t('You'), color: '#2a7de1', data: snapshotProfile() });
            var data = snapshotProfile();
            data.userName = name;
            data.favorites = DEFAULT_FAVORITES.slice();
            data.locked = false;
            var colors = ['#1fa05a', '#ff9f43', '#7a4de0', '#ee5a8b'];
            list.push({ id: 'p' + Date.now(), name: name, color: colors[list.length % colors.length], data: data });
            saveProfiles(list);
            return list[list.length - 1].id;
        }

        // "Who is watching?" overlay: one card per person plus "Add person"; Left/Right choose, OK enters, Back keeps the current person.
        var picker = { open: false, focus: 0 };

        function renderPicker() {
            var host = document.getElementById('profileCards');
            host.innerHTML = '';
            readProfiles().forEach(function(p, i) {
                var card = document.createElement('button');
                card.className = 'profile-card' + (i === picker.focus ? ' focused' : '');
                card.dataset.id = p.id;
                var avatar = document.createElement('div');
                avatar.className = 'profile-avatar';
                avatar.style.background = p.color || '#2a7de1';
                avatar.textContent = p.name.charAt(0).toUpperCase();
                var name = document.createElement('div');
                name.className = 'profile-name';
                name.textContent = p.name;
                card.appendChild(avatar);
                card.appendChild(name);
                card.onclick = function() { switchProfile(p.id); closePicker(); };
                host.appendChild(card);
            });
        }

        function openPicker() {
            picker.open = true;
            picker.focus = 0;
            document.getElementById('profileOverlay').hidden = false;
            renderPicker();
        }

        function closePicker() {
            picker.open = false;
            document.getElementById('profileOverlay').hidden = true;
            refreshMainNavList();
        }

        function handlePickerKey(e) {
            var count = readProfiles().length;
            var back = e.keyCode === 461 || e.key === 'Escape' || e.key === 'GoBack';
            if (back) closePicker();
            else if (e.key === 'ArrowRight') picker.focus = Math.min(picker.focus + 1, count - 1);
            else if (e.key === 'ArrowLeft') picker.focus = Math.max(picker.focus - 1, 0);
            else if (e.key === 'Enter') { var p = readProfiles()[picker.focus]; if (p) { switchProfile(p.id); closePicker(); } }
            else return;
            if (picker.open) renderPicker();
            e.preventDefault();
        }
```

Route `if (picker.open) { handlePickerKey(e); return; }` in the global `keydown` listener next to the wizard routing. Overlay markup `<div class="profile-overlay" id="profileOverlay" hidden><div class="profile-title">Who is watching?</div><div class="profile-cards" id="profileCards"></div></div>` with CSS like board 5 (170 px rounded avatars, 24 px names, focus ring from Task 3: add `.profile-card.focused .profile-avatar` to the shared ring rule). `Add person` reuses the wizard: `addProfile(name)` with the name typed in the wizard's name step, then `switchProfile(newId)`. Boot: `applyLock(); if (shouldAskWho()) openPicker();`. SETTINGS (Look & Feel): `{ id: 'askWho', cat: 1, type: 'choice', field: 'askWho', store: 'fmtv_ask_who', def: 'on', label: 'Ask who is watching', options: ON_OFF }` plus two `run` rows `Switch person` (`openPicker()` after `closeSettingsModal()`) and `Add person` (`closeSettingsModal(); openWizard();` with the wizard's step starting at `who`, and on Finish `addProfile(state.userName)`). State additions: `askWho: localStorage.getItem('fmtv_ask_who') || 'on', locked: false,`. Add `'You': 'Você' / 'Tú' / 'Du' / 'Vous'` to the translation table of this task.

- [ ] **Step 3: SCENARIO tests**

```javascript
  steps.push(function (done) { // profiles swap shelf, look and name; a locked profile hides the settings buttons
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    var base = snapshotProfile();
    var kid = snapshotProfile(); kid.userName = 'Kid'; kid.theme = 'day'; kid.favorites = ['youtube.leanback.v4']; kid.locked = true;
    function two() { saveProfiles([{ id: 'p1', name: 'Noa', color: '#2a7de1', data: base }, { id: 'p2', name: 'Kid', color: '#ff9f43', data: kid }]); }
    two();
    eq('profiles read', readProfiles().length, 2);
    localStorage.setItem('fmtv_profiles', '{nope');
    eq('profiles garbage tolerated', readProfiles().length, 0);
    two();
    localStorage.setItem('fmtv_active_profile', 'p1');
    switchProfile('p2');
    eq('profile switched name', state.userName, 'Kid');
    eq('profile switched shelf', state.favorites.join(','), 'youtube.leanback.v4');
    eq('locked hides Customize', document.getElementById('customizeBtn').offsetParent, null);
    eq('locked leaves nav', mainNavItems.indexOf(document.getElementById('customizeBtn')), -1);
    eq('active profile saved', localStorage.getItem('fmtv_active_profile'), 'p2');
    switchProfile('p1');
    eq('profile switched back', state.userName, base.userName);
    eq('unlocked shows Customize', document.getElementById('customizeBtn').offsetParent !== null, true);
    eq('picker needs two profiles', shouldAskWho(), true);
    saveProfiles([{ id: 'p1', name: 'Noa', color: '#2a7de1', data: base }]);
    eq('picker hidden for one profile', shouldAskWho(), false);
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    applyProfile(base);
    done();
  });
```

`shouldAskWho()` is `readProfiles().length >= 2 && state.askWho === 'on'`; `readProfiles`, `saveProfiles(list)` (JSON in `fmtv_profiles`, tolerant of garbage) and `applyLock()` belong to the interfaces of this task.

- [ ] **Step 4: Translations** (before `'Drift Speed': `; skip keys that already exist):

| key | pt | es | de | fr |
|---|---|---|---|---|
| `Who is watching?` | `Quem está assistindo?` | `¿Quién está viendo?` | `Wer schaut gerade?` | `Qui regarde ?` |
| `Add person` | `Adicionar pessoa` | `Añadir persona` | `Person hinzufügen` | `Ajouter une personne` |
| `Switch person` | `Trocar de pessoa` | `Cambiar de persona` | `Person wechseln` | `Changer de personne` |
| `Ask who is watching` | `Perguntar quem está assistindo` | `Preguntar quién está viendo` | `Fragen, wer schaut` | `Demander qui regarde` |
| `Kids` | `Crianças` | `Niños` | `Kinder` | `Enfants` |
| `A profile is a shelf, a look, a city and a screensaver. It is not an account, and it is stored only on this TV.` | `Um perfil é uma prateleira, um visual, uma cidade e um protetor de tela. Não é uma conta e fica guardado só nesta TV.` | `Un perfil es un estante, un aspecto, una ciudad y un protector. No es una cuenta y se guarda solo en este TV.` | `Ein Profil ist eine Leiste, ein Look, ein Ort und ein Bildschirmschoner. Es ist kein Konto und wird nur auf diesem Fernseher gespeichert.` | `Un profil, c’est une étagère, un style, une ville et un écran de veille. Ce n’est pas un compte et il reste sur cette TV.` |

- [ ] **Step 5: `CHECK`, TV check** (create a second person, switch, confirm the shelf and name change, the first person's settings are intact after switching back), commit (`feat: profiles stored on the TV`).

---

### Task 9: Habit-aware pick-up (time of day)

**Files:** Modify `app/index.html` (`recordLaunch`, `recentApps`), tests.

- [ ] **Step 1:** extend each history entry with `b`: counts per six-hour bucket `[night, morning, afternoon, evening]` (hour 0-5, 6-11, 12-17, 18-23). `recordLaunch` increments `entry.b[bucket(now)]`.
- [ ] **Step 2:** `recentApps(hist, catalog, limit, nowMs)` sorts by `score = recencyRank + (bucketCount(now) > 0 ? 1 : 0) * 0.5` so an app you usually open at this hour edges ahead of one you opened more recently at another hour. Keep recency dominant: a pure unit test must show (a) the old order is unchanged when no bucket data exists, (b) an app used twice in the current bucket beats an app used once an hour ago in another bucket.
- [ ] **Step 3:** update the Task 2 probe call signature (`recentApps(hist, DEFAULT_CATALOG, 3, T)`) and `renderPickup` to pass `now`. `CHECK`, commit (`feat: pick-up row prefers apps you open at this time of day`).

---

### Task 10: Spike — can the app change the TV's picture mode or set a sleep timer?

**Files:** Create `docs/superpowers/specs/2026-10-30-tv-picture-mode-spike.md`. Temporary debug code in a scratch branch is NOT committed to `feature/personal-tv`.

- [ ] **Step 1:** on a throwaway branch add a debug button that calls, via `webOS.service.request('luna://com.webos.settingsservice', …)`: `getSystemSettings {category: 'picture', keys: ['pictureMode']}` and `setSystemSettings {category: 'picture', settings: {pictureMode: 'cinema'}}`, and for the timer `luna://com.webos.service.tvpower` / settings key candidates for sleep timer (record which method names the TV accepts). Show every response as a toast and write it to `console.log`.
- [ ] **Step 2:** install, press the button on the TV, read the results with `shot.py`. If the call returns a permission error, add the missing permission to `requiredPermissions` in `app/appinfo.json` on the throwaway branch and retry; record the exact permission names that were needed.
- [ ] **Step 3:** write the findings document: which calls work from inside an app, what they need, what the TV did. **Decision gate:** if picture mode works, add `picture: 'cinema'` (Movie night) and `picture: 'game'` (Game on) steps to `SCENES` with restore, plus the Sleep scene; if not, remove "TV picture mode" and "Sleep timer" from the artifact (Task 12) and keep scenes as they are.
- [ ] **Step 4:** delete the throwaway branch; commit only the findings document on `feature/personal-tv`.

---

### Task 11: Spike — why does LG's own screensaver still cover ours?

Evidence so far (see the session notes): keep-awake held for about 19 minutes in one run, but LG's analog clock covered our running screensaver in others; our app was alive behind it. Hypotheses: (A) LG has a longer timer that a playing video does not stop; (B) the hidden video pauses or is throttled; (C) the timer is measured from the last physical remote key.

**Files:** Create `docs/superpowers/specs/2026-10-30-lg-screensaver-spike.md`. Debug code on a throwaway branch only.

- [ ] **Step 1: instrument.** Add an on-screen debug line (this exact snippet worked before) and a log of the video state:

```javascript
(function () {
    var d = document.createElement('div');
    d.style.cssText = 'position:fixed;left:0;bottom:0;z-index:99999;background:#000;color:#0f0;font:20px monospace;padding:4px 8px;';
    document.body.appendChild(d);
    setInterval(function () {
        var v = document.getElementById('keepAwakeVideo');
        d.textContent = 'ss=' + (screensaverOn ? 1 : 0) + ' kaOn=' + (keepAwakeTimer !== null ? 1 : 0) +
            ' vPaused=' + (v ? (v.paused ? 1 : 0) : '?') + ' vT=' + (v ? v.currentTime.toFixed(1) : '?') +
            ' idleFor=' + Math.round((Date.now() - lastActivity) / 1000) + 's';
    }, 1000);
})();
```

- [ ] **Step 2: watchdog test.** Add `video.addEventListener('pause', function () { if (keepAwakeTimer !== null) video.play(); })` and a 5-second interval that calls `play()` when `paused`. Run the app idle for 30 minutes on the home screen with no remote input, sampling `shot.py` every 2 minutes and logging `vPaused`/`vT`. Record the minute LG's screen appears, if ever, and whether `vT` was advancing.
- [ ] **Step 3: compare** with the video made larger (`width: 64px; height: 36px; opacity: 1` placed bottom-right) in case the TV ignores a 4-px, near-transparent element. Record the result.
- [ ] **Step 4: decide and write the document:** one of (a) keep-awake works with the watchdog → keep the watchdog and commit it as `fix: restart keep-awake video if the TV pauses it`; (b) the video keeps playing and LG still covers it → LG's timer wins; document how the user turns LG's screensaver off (TV Settings → General → Screen Saver), and add a "Turn off LG's screensaver" tip to the README; (c) other.
- [ ] **Step 5:** delete the throwaway branch; commit the document (and the watchdog if chosen) on `feature/personal-tv`.

---

### Task 12: Correct and extend the artifact

**Files:** the artifact `https://claude.ai/artifact/CkmV85EuufAMyc8jkaVGGW` (files under `project/`; the local copies are in the session scratchpad `…\scratchpad\ux\project\`).

- [ ] **Step 1:** in `Home.dc.html` and `Profiles.dc.html` replace "Nothing leaves this TV" and "stored only on this TV" claims with the shipped wording from Task 5. In `Idea.dc.html` replace "It is mine, and says so … Everything stays on this TV" with "Your settings stay on this TV. No account, no ads." and in `Plan.dc.html` move shipped tasks to the first column.
- [ ] **Step 2:** update `Scenes.dc.html` according to the Task 10 decision (remove or confirm the "Needs a TV test" rows) and `Ambient.dc.html` ("night dimming" row: the rule is 0.75 after sunset and 0.5 from 23:00 to 05:00, decided by the clock and the sunset time).
- [ ] **Step 3:** publish each changed file with the Artifact tool (`url` of the artifact, `root` = the `ux` scratchpad folder, `file_path` = the changed file, `edits` for small changes). Do not republish `index.html` or `SKILL.md`.

---

### Task 13: Release 1.5.0

**Files:** `app/appinfo.json`, `APP_VERSION` in `app/index.html` (must match), `README.md`, `ROADMAP.md`.

- [ ] **Step 1:** bump both versions to `1.5.0`; add README rows for every new setting (Your Name, Pick-up Row, Scenes, Dim Photos at Night, Ask who is watching, Run setup again) and a short "What's new in 1.5" list.
- [ ] **Step 2:** `CHECK` (the check script verifies the committed `dist/*.ipk` version equals `appinfo.json`; if it complains, rebuild the ipk and follow what `check.py` says; **commit the ipk only if `check.py` requires it for CI, otherwise leave it out**, and confirm with the user first).
- [ ] **Step 3:** install the final build on the TV and run the smoke list: home shows greeting + chips + pick-up row + shelf + Trending + trust line; focus ring visible on each; Customize opens, Back steps out; TV Settings opens; screensaver starts after the idle time and survives 10 minutes; Sliding panels/Ken Burns/drift all play; wizard shows after clearing data; profile switch works.
- [ ] **Step 4:** show the diff summary, ask "Want to run the app to review?", and wait. Only after explicit approval: merge `feature/personal-tv` → `main`, push to `origin` (the user's fork `Edenik/FreeMyTvWebOS`), never to `upstream`.

---

## Self-review against the artifact

| Board | Covered by |
|---|---|
| 1 Research findings | informs all tasks; no code |
| 2 Idea and journey | Tasks 1, 2, 4, 5, 7 (greeting, recognized, calm, mine, day-0 setup) |
| 3 Home | Tasks 1 (greeting), 2 (pick-up), 6 (scene chips), 3 (focus), 5 (trust line) |
| 4 First run | Task 7 |
| 5 Who is watching | Task 8 |
| 6 Scenes | Task 6 (own-look + app steps), Task 10 (picture mode / sleep decision) |
| 7 Evening ambient | Task 4 |
| 8 Remote rules | Task 3 (focus), the Back ladder already shipped (`d59deda`); margin/type/press-count targets are verified by screenshots in Tasks 1, 2 and 6 (Task 2 step 8 / Task 1 step 7) |
| 9 Plan | this document; Task 12 updates it |

Known gaps handled explicitly: "Shelf order by time of day" is Task 9 (pick-up row only, the shelf order stays the user's); the Sleep scene and picture-mode steps depend on Task 10; rename/delete profile is a follow-up after Task 8; the `Nothing leaves this TV` wording is corrected in Task 5 and Task 12.
