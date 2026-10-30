# Customize Screen Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat, hard-to-navigate Customize modal with a two-pane, remote-friendly screen (categories, one row per setting, an apps page) that applies and saves every change instantly.

**Architecture:** A `SETTINGS` schema (one entry per setting, with its `state` field, `localStorage` key, default, options and `apply` side effect) drives both persistence (Task 1, no UI change) and the new screen (Task 2). The screen is built imperatively in vanilla ES5 inside the existing `#settingsModal`, with a small focus state machine (`settingsUi`) for the category list, the settings list, inline text editing and the apps page. Task 3 adds translations, docs and test tidy-up.

**Tech Stack:** ES5 JavaScript (Chromium 38 floor on webOS 3.x), HTML/CSS, Python 3 test scripts, headless Chrome, Node (`es-check`).

## Global Constraints

- Source of truth: `docs/superpowers/specs/2026-10-30-ambient-screensaver-design.md`, section "Addendum 2: Customize screen redesign". Mockups: https://claude.ai/artifact/6u5pzPR8CkQ42uPkQSYBia.
- All app JS is ES5: `var`, `function`, no arrow functions, no `let`/`const`, no template literals, no `async`/`await`. Layout needing CSS Grid keeps a flexbox fallback as the existing code does (declare `display: flex` before `display: grid`).
- Categories, in this order: `Shelf & Inputs`, `Look & Feel`, `Weather & Location`, `Photos & Screensaver`, `Accounts & Keys`, plus a `Close` item after them.
- Every change applies and saves immediately; there is no Save, Cancel or Reset-Defaults button. "Reset to defaults" is a row in `Accounts & Keys` and needs a second OK to confirm.
- Secret fields (`unsplashKey`, `tmdbKey`) never show their value: the row shows a fixed `••••••••` (or `Not set`), and the inline editor is `type="password"`.
- Focus is always visible: exactly one element in the open screen carries the class `sf`. The settings list and the apps grid scroll to keep the focused item visible.
- Back or Escape steps outward: editing, apps page, settings list, category list, then closes the screen. The Magic Remote Back key is `keyCode` 461 or key `GoBack`.
- Maximum 8 shelf apps, minimum 1. Defaults must equal the current `state` defaults (theme `auto`, clock `24h`, text size `normal`, performance `standard`, language `auto`, city empty, IP locate `off`, home photos `off`, ambient `on`, idle minutes `3`, photo duration `90`, photo motion `kenburns`, keep awake `on`, keys empty).
- Every new UI string must exist in all four dictionaries (`pt`, `es`, `de`, `fr`) of `I18N`; key sets must stay identical (Task 3).
- `docs/index.html` must stay a verbatim copy of `app/index.html` (`python scripts/sync_docs.py`); CI checks it.
- Work only on local branch `feature/ambient-screensaver`. Do not push or merge. Do not commit `dist/*.ipk`.
- Commit messages end with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (an agent may use its own model name).

**Command conventions** (PowerShell, from `C:\Users\97254\Downloads\FreeMyTvWebOS`):

- Browser test (`TEST`): `$env:PYTHONUTF8='1'; python scripts/browser_test.py --chrome 'C:\Program Files\Google\Chrome\Application\chrome.exe'`
- Repo checks (`CHECK`): `python scripts/sync_docs.py; python scripts/check.py`
- ES5 check (`ES5`): `python scripts/check.py --extract-js "C:/Users/97254/AppData/Local/Temp/app.js"; npx --yes es-check@7.2.1 es5 "C:/Users/97254/AppData/Local/Temp/app.js"` (forward slashes required)

Baseline before starting (HEAD `5ec465f` or later): `TEST` prints `[+] browser tests passed`; `CHECK` prints `[+] all checks passed`.

**Scenario test conventions** (inside the `SCENARIO` string of `scripts/browser_test.py`): new steps go immediately before the line `  (function run(i) {` near the end of the string. Existing helpers there include `eq(name, got, want)`, `reset()`, `fakeFetch(status, remaining, calls)`, `photo(...)`, `seedMany(list)`. The scenario's `--virtual-time-budget` is `25000`; if the added steps make it run out ("ambient scenario did not finish"), raise it (it is virtual time, no wall-clock cost). Steps run in order and share page state, so each new step sets the `state.*` values it needs and restores what it changes. The `PROBE` string runs once about 1.5 s after boot with a fresh `localStorage` (only `fmtv_lang` set to the language under test).

---

## File Structure

- Modify `app/index.html`: the `SETTINGS` schema and helpers; the new modal markup, CSS, rendering and key handling; removal of the old modal controls and handlers.
- Modify `docs/index.html`: regenerated copy (never hand-edit).
- Modify `scripts/browser_test.py`: probe and scenario steps; old `cfg*` checks removed.
- Modify `README.md`, `ROADMAP.md` (Task 3).

---

### Task 1: Settings schema and instant-apply engine (no UI change)

**Files:**
- Modify: `scripts/browser_test.py` (probe and scenario steps)
- Modify: `app/index.html` (new block above `        // --- Customize Shelf & Settings Modal ---`)

**Interfaces:**
- Consumes (existing globals): `state`, `DEFAULT_FAVORITES`, `DEVICE_PRESETS`, `devicePreset(app, choices)`, `isHDMI(app)`, `t()`, `showToast()`, `applyTheme()`, `updateClock()`, `applyTextSize()`, `applyPerfMode()`, `applyStaticTranslations()`, `renderAppsShelf()`, `fetchWeather()`, `fetchTrendingPicks()`, `ambientRefresh(force)`, `applyHomePhotosSettings()`.
- Produces: `SETTING_CATEGORIES` (array of 5 English names); `SETTINGS` (array of schema entries); `findSetting(id) -> def|undefined`; `hdmiSettings() -> def[]`; `settingsForCategory(cat) -> def[]` (the category's entries in order, with the HDMI rows directly after `shelf` in category 0); `settingValue(def) -> string`; `setSettingValue(def, value)`; `cycleSetting(def, step)`; `settingValueText(def) -> string`; `toggleFavorite(id) -> 'added'|'removed'|'full'|'last'`; `resetAllSettings()`.

- [ ] **Step 1: Add the failing probe assertions and scenario step**

In `scripts/browser_test.py`, inside `PROBE`, replace this exact text:

```
  var keyField = document.getElementById('cfgUnsplashKey');
```

with:

```
  if (typeof SETTINGS !== 'object' || !SETTINGS.length) {
    out.ambient.push('SETTINGS missing');
  } else {
    SETTINGS.forEach(function (d) {
      if (d.field && d.id !== 'lang' && state[d.field] !== d.def) out.ambient.push('default mismatch: ' + d.id + ' state=' + JSON.stringify(state[d.field]) + ' def=' + JSON.stringify(d.def));
      if (d.type === 'choice' && !d.options) out.ambient.push('no options: ' + d.id);
    });
  }
  var keyField = document.getElementById('cfgUnsplashKey');
```

In `SCENARIO`, replace this exact text:

```
  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

with:

```
  if (typeof setSettingValue !== 'function') { fails.push('setSettingValue missing'); write(); return; }

  steps.push(function (done) { // the settings engine: persistence, side effects, cycling, favorites, reset
    var seen = [];
    var names = ['applyTheme', 'updateClock', 'applyTextSize', 'applyPerfMode', 'applyStaticTranslations', 'renderAppsShelf',
      'fetchWeather', 'fetchTrendingPicks', 'applyHomePhotosSettings', 'ambientRefresh'];
    var real = {};
    names.forEach(function (n) { real[n] = window[n]; window[n] = function () { seen.push(n); }; });
    var saved = { favorites: state.favorites.slice(), hdmiDevices: JSON.parse(JSON.stringify(state.hdmiDevices)) };
    var savedStore = {};
    SETTINGS.forEach(function (d) { if (d.field) { saved[d.field] = state[d.field]; savedStore[d.store] = localStorage.getItem(d.store); } });
    try {
      setSettingValue(findSetting('theme'), 'oled');
      eq('engine theme state', state.theme, 'oled');
      eq('engine theme stored', localStorage.getItem('fmtv_theme'), 'oled');
      eq('engine theme apply', seen.indexOf('applyTheme') !== -1, true);

      state.idleMins = '3';
      cycleSetting(findSetting('idleMins'), 1);
      eq('engine cycle +1', state.idleMins, '5');
      state.idleMins = '30';
      cycleSetting(findSetting('idleMins'), 1);
      eq('engine cycle wraps up', state.idleMins, '1');
      cycleSetting(findSetting('idleMins'), -1);
      eq('engine cycle wraps down', state.idleMins, '30');

      seen.length = 0;
      setSettingValue(findSetting('city'), 'Haifa');
      eq('engine city state', state.city, 'Haifa');
      eq('engine city weather', seen.indexOf('fetchWeather') !== -1, true);

      localStorage.setItem('fmtv_ambient_cache', '{"photos":[],"at":1}');
      setSettingValue(findSetting('unsplashKey'), 'key-one');
      eq('engine key clears cache', localStorage.getItem('fmtv_ambient_cache'), null);
      localStorage.setItem('fmtv_ambient_cache', '{"photos":[],"at":1}');
      setSettingValue(findSetting('unsplashKey'), 'key-one');
      eq('engine same key keeps cache', localStorage.getItem('fmtv_ambient_cache') !== null, true);
      eq('engine secret hidden', settingValueText(findSetting('unsplashKey')).indexOf('key-one'), -1);
      state.unsplashKey = '';
      eq('engine secret empty', settingValueText(findSetting('unsplashKey')), t('Not set'));

      var hd = hdmiSettings();
      eq('engine hdmi rows', hd.length, state.catalog.filter(isHDMI).length);
      if (hd.length) {
        seen.length = 0;
        setSettingValue(hd[0], 'ps5');
        eq('engine hdmi state', state.hdmiDevices[hd[0].hdmi.id], 'ps5');
        eq('engine hdmi stored', JSON.parse(localStorage.getItem('fmtv_hdmi_devices'))[hd[0].hdmi.id], 'ps5');
        eq('engine hdmi value', settingValue(hd[0]), 'ps5');
        eq('engine hdmi shelf', seen.indexOf('renderAppsShelf') !== -1, true);
      }
      var cat0 = settingsForCategory(0);
      eq('engine cat0 first is shelf', cat0[0] && cat0[0].id, 'shelf');
      eq('engine cat0 hdmi follow', cat0.length, 1 + hd.length);

      state.favorites = ['a'];
      eq('engine fav last', toggleFavorite('a'), 'last');
      eq('engine fav add', toggleFavorite('b'), 'added');
      eq('engine fav stored', localStorage.getItem('fmtv_favorites'), JSON.stringify(['a', 'b']));
      eq('engine fav remove', toggleFavorite('b'), 'removed');
      state.favorites = ['1', '2', '3', '4', '5', '6', '7', '8'];
      eq('engine fav full', toggleFavorite('x'), 'full');
      eq('engine fav full unchanged', state.favorites.length, 8);

      seen.length = 0;
      setSettingValue(findSetting('theme'), 'day');
      resetAllSettings();
      eq('engine reset theme', state.theme, 'auto');
      eq('engine reset city', state.city, '');
      eq('engine reset favorites', JSON.stringify(state.favorites), JSON.stringify(DEFAULT_FAVORITES));
      eq('engine reset hdmi', JSON.stringify(state.hdmiDevices), '{}');
      eq('engine reset applies', seen.indexOf('applyTheme') !== -1 && seen.indexOf('fetchWeather') !== -1 && seen.indexOf('renderAppsShelf') !== -1, true);
    } finally {
      names.forEach(function (n) { window[n] = real[n]; });
      Object.keys(saved).forEach(function (f) { state[f] = saved[f]; });
      Object.keys(savedStore).forEach(function (k) {
        if (savedStore[k] === null) localStorage.removeItem(k); else localStorage.setItem(k, savedStore[k]);
      });
      localStorage.setItem('fmtv_favorites', JSON.stringify(state.favorites));
      localStorage.setItem('fmtv_hdmi_devices', JSON.stringify(state.hdmiDevices));
      localStorage.removeItem('fmtv_ambient_cache');
    }
    done();
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL. `[!] ambient checks:` contains `SETTINGS missing` and `[!] ambient scenario: ['setSettingValue missing']`.

- [ ] **Step 3: Add the schema and engine**

In `app/index.html`, replace this exact line:

```
        // --- Customize Shelf & Settings Modal ---
```

with:

```
        // --- Settings schema: one entry per setting; the Customize screen and the persistence both use it ---
        var SETTING_CATEGORIES = ['Shelf & Inputs', 'Look & Feel', 'Weather & Location', 'Photos & Screensaver', 'Accounts & Keys'];
        var ON_OFF = [['on', 'On'], ['off', 'Off']];
        var SECRET_DOTS = '••••••••';

        // type: 'choice' (options cycle), 'text' (opens the keyboard), 'link' (opens a page), 'action'.
        // field = the state field, store = its localStorage key, def = default, apply(previous) = side effects.
        var SETTINGS = [
            { id: 'shelf', cat: 0, type: 'link', label: 'Shelf apps' },
            { id: 'theme', cat: 1, type: 'choice', field: 'theme', store: 'fmtv_theme', def: 'auto', label: 'Theme Mode',
              options: [['auto', 'Auto (Follows Sunset)'], ['night', 'Deep Midnight (Default)'], ['oled', 'Pure OLED Black'], ['day', 'Daylight Blue']],
              apply: function() { applyTheme(); } },
            { id: 'clockFormat', cat: 1, type: 'choice', field: 'clockFormat', store: 'fmtv_clock_format', def: '24h', label: 'Clock Format',
              options: [['24h', '24-Hour (20:30)'], ['12h', '12-Hour (8:30 PM)']],
              apply: function() { updateClock(); } },
            { id: 'textSize', cat: 1, type: 'choice', field: 'textSize', store: 'fmtv_text_size', def: 'normal', label: 'Text Size (weather & clock)',
              options: [['normal', 'Normal'], ['large', 'Large'], ['xlarge', 'Extra large']],
              apply: function() { applyTextSize(); } },
            { id: 'perfMode', cat: 1, type: 'choice', field: 'perfMode', store: 'fmtv_perf_mode', def: 'standard', label: 'Performance Mode',
              options: [['standard', 'Standard (Glass & Glow)'], ['high', 'High Performance (60 FPS Boost)']],
              apply: function() { applyPerfMode(); applyHomePhotosSettings(); } },
            { id: 'lang', cat: 1, type: 'choice', field: 'lang', store: 'fmtv_lang', def: 'auto', label: 'Language',
              options: [['auto', 'Auto (TV language)'], ['en', 'English'], ['pt', 'Português (Brasil)'], ['es', 'Español'], ['de', 'Deutsch'], ['fr', 'Français']],
              apply: function() { applyStaticTranslations(); renderAppsShelf(); updateClock(); fetchWeather(); } },
            { id: 'city', cat: 2, type: 'text', field: 'city', store: 'fmtv_city', def: '', label: 'City Name (or leave Auto)',
              placeholder: 'e.g. Sao Paulo, Lisbon, NYC',
              apply: function() { fetchWeather(); } },
            { id: 'ipLocate', cat: 2, type: 'choice', field: 'ipLocate', store: 'fmtv_ip_locate', def: 'off', label: 'Auto-locate by IP (sends your IP to ipapi.co)',
              options: [['off', 'Off (use the city above)'], ['on', 'On']],
              apply: function() { fetchWeather(); } },
            { id: 'homePhotos', cat: 3, type: 'choice', field: 'homePhotos', store: 'fmtv_home_photos', def: 'off', label: 'Photos on Home Screen',
              hint: 'Dimmed, slowly moving photos behind the dashboard',
              options: [['off', 'Off'], ['on', 'On']],
              apply: function() { ambientRefresh(false); applyHomePhotosSettings(); } },
            { id: 'ambient', cat: 3, type: 'choice', field: 'ambient', store: 'fmtv_ambient', def: 'on', label: 'Ambient Photo Screensaver',
              hint: 'Photos behind the clock when the TV is idle',
              options: ON_OFF,
              apply: function() { ambientRefresh(false); } },
            { id: 'idleMins', cat: 3, type: 'choice', field: 'idleMins', store: 'fmtv_idle_mins', def: '3', label: 'Screensaver Starts After',
              options: [['1', '1 minute'], ['3', '3 minutes'], ['5', '5 minutes'], ['10', '10 minutes'], ['30', '30 minutes']] },
            { id: 'ambientSecs', cat: 3, type: 'choice', field: 'ambientSecs', store: 'fmtv_ambient_secs', def: '90', label: 'Photo Duration',
              options: [['30', '30 seconds'], ['90', '90 seconds'], ['300', '5 minutes']],
              apply: function() { applyHomePhotosSettings(); } },
            { id: 'ambientMotion', cat: 3, type: 'choice', field: 'ambientMotion', store: 'fmtv_ambient_motion', def: 'kenburns', label: 'Photo Motion',
              options: [['kenburns', 'Ken Burns (zoom & drift)'], ['drift', 'Drift only'], ['none', 'None']],
              apply: function() { applyHomePhotosSettings(); } },
            { id: 'keepAwake', cat: 3, type: 'choice', field: 'keepAwake', store: 'fmtv_keep_awake', def: 'on', label: 'Keep LG Screensaver Away',
              hint: 'Plays a hidden video so LG does not cover ours',
              options: ON_OFF },
            { id: 'unsplashKey', cat: 4, type: 'text', secret: true, field: 'unsplashKey', store: 'fmtv_unsplash_key', def: '', label: 'Unsplash Access Key (Optional)',
              hint: 'For the photos. Stored on this TV only',
              apply: function(previous) {
                  if (previous !== state.unsplashKey) {
                      try { localStorage.removeItem('fmtv_ambient_cache'); localStorage.removeItem('fmtv_ambient_pause'); } catch (e) {}
                  }
                  ambientRefresh(false);
                  applyHomePhotosSettings();
              } },
            { id: 'tmdbKey', cat: 4, type: 'text', secret: true, field: 'tmdbKey', store: 'fmtv_tmdb_key', def: '', label: 'TMDB API Key (Optional)',
              hint: 'Optional, for weekly trending movies and shows',
              apply: function() { fetchTrendingPicks(); } },
            { id: 'reset', cat: 4, type: 'action', label: 'Reset to defaults' }
        ];

        function findSetting(id) {
            return arrFind(SETTINGS, function(def) { return def.id === id; });
        }

        // One choice row per HDMI input of the catalog (device preset: HDMI, PS5, PS4, Xbox, Switch, Gaming PC).
        function hdmiSettings() {
            return state.catalog.filter(isHDMI).map(function(app) {
                return {
                    id: 'hdmi:' + app.id, cat: 0, type: 'choice', label: app.title, hdmi: app,
                    options: DEVICE_PRESETS.map(function(p) { return [p.key, p.title || 'HDMI']; })
                };
            });
        }

        // A category's entries in order; the HDMI rows follow the "Shelf apps" row.
        function settingsForCategory(cat) {
            var list = [];
            SETTINGS.forEach(function(def) {
                if (def.cat !== cat) return;
                list.push(def);
                if (def.id === 'shelf') hdmiSettings().forEach(function(h) { list.push(h); });
            });
            return list;
        }

        function settingValue(def) {
            if (def.hdmi) return devicePreset(def.hdmi, state.hdmiDevices).key;
            return state[def.field];
        }

        // Change a setting: update state, save it, run its side effects. Nothing is "pending".
        function setSettingValue(def, value) {
            var previous = settingValue(def);
            if (def.hdmi) {
                state.hdmiDevices[def.hdmi.id] = value;
                try { localStorage.setItem('fmtv_hdmi_devices', JSON.stringify(state.hdmiDevices)); } catch (e) {}
                renderAppsShelf();
                return;
            }
            state[def.field] = value;
            try { localStorage.setItem(def.store, value); } catch (e) {}
            if (def.apply) def.apply(previous);
        }

        function cycleSetting(def, step) {
            var current = settingValue(def);
            var index = arrFindIndex(def.options, function(o) { return o[0] === current; });
            if (index < 0) index = 0;
            var next = (index + step + def.options.length) % def.options.length;
            setSettingValue(def, def.options[next][0]);
        }

        // The text shown for a setting's current value. Secrets are never shown.
        function settingValueText(def) {
            var value = settingValue(def);
            if (def.type === 'choice') {
                var option = arrFind(def.options, function(o) { return o[0] === value; });
                return t(option ? option[1] : def.options[0][1]);
            }
            if (def.type === 'text') {
                if (!value) return t('Not set');
                return def.secret ? SECRET_DOTS : value;
            }
            return '';
        }

        // Add or remove a shelf app (at most 8, at least 1); returns 'added', 'removed', 'full' or 'last'.
        function toggleFavorite(id) {
            var index = state.favorites.indexOf(id);
            if (index !== -1) {
                if (state.favorites.length <= 1) return 'last';
                state.favorites.splice(index, 1);
            } else if (state.favorites.length >= 8) {
                return 'full';
            } else {
                state.favorites.push(id);
            }
            try { localStorage.setItem('fmtv_favorites', JSON.stringify(state.favorites)); } catch (e) {}
            renderAppsShelf();
            return index !== -1 ? 'removed' : 'added';
        }

        // Put every setting, the shelf and the HDMI device names back to their defaults, then re-apply once.
        function resetAllSettings() {
            SETTINGS.forEach(function(def) {
                if (!def.field) return;
                state[def.field] = def.def;
                try { localStorage.setItem(def.store, def.def); } catch (e) {}
            });
            state.favorites = DEFAULT_FAVORITES.slice();
            state.hdmiDevices = {};
            try {
                localStorage.setItem('fmtv_favorites', JSON.stringify(state.favorites));
                localStorage.setItem('fmtv_hdmi_devices', '{}');
                localStorage.removeItem('fmtv_ambient_cache');
                localStorage.removeItem('fmtv_ambient_pause');
            } catch (e) {}
            applyStaticTranslations();
            applyPerfMode();
            applyTextSize();
            renderAppsShelf();
            applyTheme();
            updateClock();
            fetchWeather();
            fetchTrendingPicks();
            ambientRefresh(false);
            applyHomePhotosSettings();
            showToast(t('Defaults restored'));
        }

        // --- Customize Shelf & Settings Modal ---
```

- [ ] **Step 4: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed`.
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed`.

- [ ] **Step 5: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: settings schema with instant persistence and per-setting side effects

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The new Customize screen (categories, rows, inline editing, apps page)

**Files:**
- Modify: `app/index.html` (modal markup, CSS, rendering, key handling; remove the old modal controls and handlers)
- Modify: `scripts/browser_test.py` (probe: remove the old `cfg*` checks; scenario: navigation steps)

**Interfaces:**
- Consumes: everything Task 1 produced; `modalOpen`, `shelfEdit`, `drawerOpen`, `setMainFocus`, `mainNavItems`, `curIndex`, `showToast`, `t`, `state.catalog`, `state.favorites`.
- Produces: `settingsUi` (`{zone, cat, catFocus, row, appIdx, confirmReset, message}` with `zone` one of `'cats'|'rows'|'apps'|'edit'`); `openSettingsModal()`, `closeSettingsModal()`; `renderSettings()` (rebuilds the DOM), `paintFocus()` (only moves the `sf` class and scrolls); `handleSettingsKey(e)`; DOM ids `settingsModal`, `settingsTitle`, `settingsSaved`, `settingsCats`, `settingsMain`, `settingsRows`, `settingsHints`, `settingsEditInput`, `appsPage`, `appsGrid`, `appsDone`, `appsMessage`; classes `.settings-panel`, `.settings-cat` (+ `.selected`, `.sf`, `.settings-close`), `.settings-row` (+ `.sf`, `[data-i]`, `[data-id]`), `.sr-arrow` (`[data-dir]`), `.apps-tile` (+ `.on`, `.sf`, `[data-i]`).

**Design contract** (the mockups are the visual reference; sizes are for a 1920x1080 TV):

- Panel `.settings-panel`: width `min(1500px, 94vw)`, height `min(880px, 90vh)`, flex column, the existing glass look (`rgba(22, 27, 40, 0.94)`, 1px light border, 28px radius). Header row: title left, `#settingsSaved` right (22px, `var(--text-secondary)`). Body: two columns, `.settings-cats` 380px wide with 10px gaps between 72px-high buttons (font 28px, count badge on the right in 20px muted), `.settings-main` filling the rest with `min-width: 0`. Footer `#settingsHints`: one muted 20px line.
- A settings row `.settings-row`: min-height 88px, 0 22px padding, 16px radius, background `rgba(255,255,255,0.06)`, 1px border `rgba(255,255,255,0.12)`, rows 12px apart. Label 28px, hint 20px muted below it; the value on the right in 28px semibold; for `choice` rows a 52px round arrow button `.sr-arrow` on each side of the value (value min-width 300px, centered). Text/link rows show a small muted pill (`OK to edit` / `OK to open`) after the value.
- Focus ring: `.settings-cat.sf`, `.settings-row.sf`, `.apps-tile.sf`, `.apps-done.sf` get `box-shadow: 0 0 0 4px #0a84ff` and a lighter background; `.settings-cat.selected` (current category while focus is elsewhere) gets a solid accent-tinted background. Nothing relies on color alone for focus: the ring is always 4px. No element may use `outline: none` without this ring replacing it.
- Apps page `.apps-page` (inside `.settings-main` instead of the rows): a header line (`Shelf apps`, a counter pill with `%s of 8 selected`), `#appsMessage` (22px, one line, empty when nothing to say), `#appsGrid` a 5-column grid of 84px-high `.apps-tile` buttons (name left, a check icon when `.on`), then the `Done` button `#appsDone`. Selected tiles (`.on`) have an accent-tinted background and a check.
- The rows list `#settingsRows` has `position: relative; overflow-y: auto; flex: 1; min-height: 0; padding: 6px` so the focus ring is never clipped.
- Use `<button type="button">` for every focusable item; label text is set with `textContent` (installed app titles come from the TV).

- [ ] **Step 1: Replace the old probe checks and add the failing scenario steps**

In `scripts/browser_test.py`, inside `PROBE`, delete the old checks of the removed controls: the `['cfgIdleMins', 'cfgAmbient', 'cfgAmbientSecs', 'cfgAmbientMotion', 'cfgUnsplashKey'].forEach(...)` block, the `cfgKeepAwake`, `cfgHomePhotos` and `keepAwakeVideo`-unrelated `cfg*` lines (keep `keepAwakeVideo`), and the `keyField` assertion lines (`var keyField = ...` and `eq('unsplash key field masked', ...)`). Add in their place:

```
  ['settingsModal', 'settingsCats', 'settingsMain', 'settingsHints', 'settingsSaved'].forEach(function (id) {
    if (!document.getElementById(id)) out.ambient.push('missing #' + id);
  });
  ['cfgCity', 'cfgTheme', 'cfgUnsplashKey', 'saveModalBtn', 'resetDefaultBtn', 'closeModalBtn'].forEach(function (id) {
    if (document.getElementById(id)) out.ambient.push('old control still present: #' + id);
  });
```

In `SCENARIO`, replace this exact text:

```
  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

with:

```
  if (typeof handleSettingsKey !== 'function') { fails.push('handleSettingsKey missing'); write(); return; }

  function press(key) {
    var ev = new KeyboardEvent('keydown', { key: key, bubbles: true, cancelable: true });
    document.dispatchEvent(ev);
    return ev;
  }
  function modalEl() { return document.getElementById('settingsModal'); }
  function sfCount() { return modalEl().querySelectorAll('.sf').length; }
  function focusedText() { var n = modalEl().querySelector('.sf'); return n ? n.textContent : ''; }
  function inView(node, box) {
    var a = node.getBoundingClientRect(), b = box.getBoundingClientRect();
    return a.top >= b.top - 1 && a.bottom <= b.bottom + 1;
  }
  function rowIndexOf(id) {
    var rows = settingsForCategory(settingsUi.cat);
    for (var i = 0; i < rows.length; i++) if (rows[i].id === id) return i + 1; // +1: the "Categories" row comes first
    return -1;
  }
  function goToRow(id) { var n = rowIndexOf(id), guard = 40; while (settingsUi.row < n && guard--) press('ArrowDown'); while (settingsUi.row > n && guard--) press('ArrowUp'); }

  var uiReal = {};
  ['fetchWeather', 'fetchTrendingPicks', 'ambientRefresh'].forEach(function (n) { uiReal[n] = window[n]; });

  steps.push(function (done) { // opening: category list focused, one visible focus mark, old controls gone
    window.fetch = fakeFetch(200, '49', []);
    ['fetchWeather', 'fetchTrendingPicks', 'ambientRefresh'].forEach(function (n) { window[n] = function () {}; }); // no network from these steps
    openSettingsModal();
    eq('modal open', modalOpen, true);
    eq('zone cats', settingsUi.zone, 'cats');
    eq('one focus mark', sfCount(), 1);
    eq('first category focused', focusedText().indexOf(t('Shelf & Inputs')) !== -1, true);
    press('ArrowDown'); press('ArrowDown'); press('ArrowDown');
    eq('down x3 selects category 3', settingsUi.cat, 3);
    eq('rows show that category', !!modalEl().querySelector('.settings-row[data-id="homePhotos"]'), true);
    press('ArrowDown'); press('ArrowDown');
    eq('down reaches Close', settingsUi.catFocus, 5);
    press('ArrowDown');
    eq('no wrap past Close', settingsUi.catFocus, 5);
    press('ArrowUp'); press('ArrowUp'); press('ArrowUp'); press('ArrowUp'); press('ArrowUp'); press('ArrowUp'); press('ArrowUp');
    eq('no wrap above first', settingsUi.catFocus, 0);
    done();
  });
  steps.push(function (done) { // entering a category, choice rows change with Left and Right and save at once
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings();
    press('ArrowRight');
    eq('zone rows', settingsUi.zone, 'rows');
    eq('lands on first setting', settingsUi.row, 1);
    eq('one focus mark rows', sfCount(), 1);
    state.idleMins = '3';
    goToRow('idleMins');
    press('ArrowRight');
    eq('right changes value', state.idleMins, '5');
    eq('value saved at once', localStorage.getItem('fmtv_idle_mins'), '5');
    eq('saved message', document.getElementById('settingsSaved').textContent, t('Saved'));
    press('ArrowLeft'); press('ArrowLeft');
    eq('left changes value (wraps)', state.idleMins, '1');
    press('Enter');
    eq('OK cycles forward', state.idleMins, '3');
    eq('still one focus mark', sfCount(), 1);
    done();
  });
  steps.push(function (done) { // back chain: rows -> categories -> closes
    press('Escape');
    eq('back from rows', settingsUi.zone, 'cats');
    press('Escape');
    eq('back from cats closes', modalOpen, false);
    openSettingsModal();
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings(); press('Enter');
    goToRow('keepAwake'); // then up to the "Categories" row
    var guard = 20; while (settingsUi.row > 0 && guard--) press('ArrowUp');
    eq('categories row first', settingsUi.row, 0);
    press('Enter');
    eq('Categories row returns', settingsUi.zone, 'cats');
    press('ArrowDown'); press('ArrowDown');
    eq('Close item closes', (function () { settingsUi.catFocus = 5; press('Enter'); return modalOpen; })(), false);
    done();
  });
  steps.push(function (done) { // text rows: inline editor, commit, cancel; secrets are masked everywhere
    openSettingsModal();
    settingsUi.cat = 2; settingsUi.catFocus = 2; renderSettings(); press('Enter');
    goToRow('city');
    press('Enter');
    var input = document.getElementById('settingsEditInput');
    eq('editor opens', !!input && settingsUi.zone === 'edit', true);
    eq('city editor is text', input && input.type, 'text');
    input.value = 'Haifa';
    press('Enter');
    eq('city committed', state.city, 'Haifa');
    eq('city saved', localStorage.getItem('fmtv_city'), 'Haifa');
    eq('back in rows', settingsUi.zone, 'rows');
    press('Enter');
    document.getElementById('settingsEditInput').value = 'Eilat';
    press('Escape');
    eq('escape cancels', state.city, 'Haifa');
    eq('modal stays open after cancel', modalOpen, true);

    settingsUi.cat = 4; settingsUi.catFocus = 4; settingsUi.zone = 'cats'; renderSettings(); press('Enter');
    goToRow('unsplashKey');
    press('Enter');
    var secret = document.getElementById('settingsEditInput');
    eq('secret editor is password', secret && secret.type, 'password');
    secret.value = 'SECRET-KEY-12345';
    press('Enter');
    eq('secret committed', state.unsplashKey, 'SECRET-KEY-12345');
    eq('secret never shown in rows', modalEl().textContent.indexOf('SECRET-KEY-12345'), -1);
    eq('secret shows dots', modalEl().querySelector('.settings-row[data-id="unsplashKey"]').textContent.indexOf('••••••••') !== -1, true);
    state.unsplashKey = ''; localStorage.removeItem('fmtv_unsplash_key'); state.city = ''; localStorage.removeItem('fmtv_city');
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // long lists scroll to keep the focused row in view (Photos & Screensaver has 7 rows, taller than the list at 1080p)
    openSettingsModal();
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings(); press('Enter');
    var rows = document.getElementById('settingsRows'), last = settingsForCategory(3).length, guard = 60;
    while (settingsUi.row < last && guard--) press('ArrowDown');
    var focused = modalEl().querySelector('.settings-row.sf');
    eq('focused last row exists', !!focused, true);
    eq('focused row in view', !!focused && inView(focused, rows), true);
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // apps page: rows by 5, toggle, limits, Done and Back return
    var keep = state.favorites.slice();
    state.favorites = [state.catalog[0].id];
    openSettingsModal();
    settingsUi.cat = 0; settingsUi.catFocus = 0; renderSettings(); press('Enter');
    press('Enter'); // "Shelf apps" is the first setting
    eq('apps zone', settingsUi.zone, 'apps');
    eq('apps page shown', !!document.getElementById('appsPage'), true);
    eq('apps one focus', sfCount(), 1);
    settingsUi.appIdx = 0; paintFocus();
    press('ArrowDown');
    eq('down moves one row (5)', settingsUi.appIdx, 5);
    press('ArrowRight');
    eq('right moves one tile', settingsUi.appIdx, 6);
    press('ArrowUp');
    eq('up moves one row back', settingsUi.appIdx, 1);
    settingsUi.appIdx = 1; paintFocus(); press('Enter');
    eq('OK adds the app', state.favorites.indexOf(state.catalog[1].id) !== -1, true);
    eq('apps saved at once', localStorage.getItem('fmtv_favorites'), JSON.stringify(state.favorites));
    eq('tile marked on', document.querySelectorAll('.apps-tile.on').length, state.favorites.length);
    state.favorites = [state.catalog[0].id];
    renderSettings();
    settingsUi.appIdx = 0; paintFocus(); press('Enter');
    eq('last app cannot be removed', state.favorites.length, 1);
    eq('last app message', document.getElementById('appsMessage').textContent, t('Keep at least one app on the shelf.'));
    state.favorites = state.catalog.slice(0, 8).map(function (a) { return a.id; });
    renderSettings();
    settingsUi.appIdx = 9; paintFocus(); press('Enter');
    eq('ninth app refused', state.favorites.length, 8);
    eq('full message', document.getElementById('appsMessage').textContent, t('Max 8 apps on shelf'));
    var n = state.catalog.length, guard = 10;
    while (settingsUi.appIdx < n && guard--) press('ArrowDown');
    eq('down reaches Done', settingsUi.appIdx, n);
    press('Enter');
    eq('Done returns to rows', settingsUi.zone, 'rows');
    press('Enter');
    eq('reopen apps', settingsUi.zone, 'apps');
    press('Escape');
    eq('back returns to rows', settingsUi.zone, 'rows');
    state.favorites = keep; localStorage.setItem('fmtv_favorites', JSON.stringify(keep));
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // reset needs a second OK
    state.theme = 'day'; localStorage.setItem('fmtv_theme', 'day');
    openSettingsModal();
    settingsUi.cat = 4; settingsUi.catFocus = 4; renderSettings(); press('Enter');
    goToRow('reset');
    press('Enter');
    eq('first OK only asks', state.theme, 'day');
    eq('asks to confirm', modalEl().querySelector('.settings-row[data-id="reset"]').textContent.indexOf(t('Press OK again to confirm')) !== -1, true);
    press('ArrowUp'); goToRow('reset');
    eq('moving away cancels the ask', modalEl().querySelector('.settings-row[data-id="reset"]').textContent.indexOf(t('Press OK again to confirm')), -1);
    press('Enter'); press('Enter');
    eq('second OK resets', state.theme, 'auto');
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // the idle screensaver does not start while the screen is open; hover only moves focus
    openSettingsModal();
    var before = settingsUi.catFocus;
    var cats = modalEl().querySelectorAll('.settings-cat');
    cats[2].dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    eq('hover focuses without rebuilding', modalEl().querySelectorAll('.settings-cat')[2] === cats[2], true);
    eq('hover focus moved', settingsUi.catFocus, 2);
    cats[2].click();
    eq('click enters the category', settingsUi.zone, 'rows');
    eq('click selected category', settingsUi.cat, 2);
    closeSettingsModal();
    ['fetchWeather', 'fetchTrendingPicks', 'ambientRefresh'].forEach(function (n) { window[n] = uiReal[n]; });
    done();
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`.
Expected: FAIL: `[!] ambient checks:` lists `missing #settingsCats` (and the other new ids) plus `old control still present: #cfgCity` (and the other old ids), and `[!] ambient scenario: ['handleSettingsKey missing']`.

- [ ] **Step 3: Replace the modal markup**

In `app/index.html`, replace the whole old modal: from the line `    <!-- Customize Shelf & Settings Modal -->` through the closing `</div>` of `<div class="modal-backdrop" id="settingsModal">` (the block that ends just before `    <!-- Weather & Sun Drawer -->`) with:

```
    <!-- Customize Free My TV: categories, one row per setting, an apps page; every change applies at once -->
    <div class="modal-backdrop" id="settingsModal">
        <div class="settings-panel" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
            <div class="settings-head">
                <div class="settings-title" id="settingsTitle">Customize Free My TV</div>
                <div class="settings-saved" id="settingsSaved" role="status" aria-live="polite"></div>
            </div>
            <div class="settings-body">
                <div class="settings-cats" id="settingsCats"></div>
                <div class="settings-main" id="settingsMain"></div>
            </div>
            <div class="settings-foot" id="settingsHints"></div>
        </div>
    </div>
```

The footer used to carry `#appVersion` (`<span class="modal-version" id="appVersion">`); the boot code sets its text (`document.getElementById('appVersion').textContent = 'Free My TV v' + APP_VERSION;`). Keep the version visible: add `<span class="modal-version" id="appVersion"></span>` as the last child of `.settings-head`, before `#settingsSaved`, and leave that boot line as it is.

- [ ] **Step 4: Replace the modal CSS**

In the `<style>` block, delete the rules that only the old modal used, after checking by search that nothing else in the markup or scripts uses the class: `.modal-box`, `.modal-section-title`, `.app-selector-grid` (and its `.app-toggle-item` descendants), `.app-toggle-item` (all its variants), `.hdmi-options` (and `.hdmi-options .app-toggle-item`), `.settings-row` (the old 3-column grid), `.field-group` (and `.field-group label`), `.field-input` (and its focus variants), `.modal-actions`, `.btn-primary`, `.btn-secondary` (and their hover/focus rule). Keep `.modal-backdrop`, `.modal-backdrop.active`, `.modal-header`, `.modal-title` and `.modal-version` (the weather drawer uses `.modal-header` and `.modal-title`). Then add, next to `.modal-backdrop`:

```
        /* Customize screen */
        .settings-panel {
            width: 1500px;
            max-width: 94vw;
            height: 880px;
            max-height: 90vh;
            box-sizing: border-box;
            background: rgba(22, 27, 40, 0.94);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 28px;
            padding: 30px 38px 22px;
            display: flex;
            flex-direction: column;
            gap: 18px;
            box-shadow: 0 30px 80px rgba(0, 0, 0, 0.85);
        }

        .settings-head {
            display: flex;
            align-items: center;
            gap: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 14px;
        }

        .settings-title {
            font-size: 34px;
            font-weight: 700;
            flex: 1;
        }

        .settings-saved {
            font-size: 22px;
            color: var(--text-secondary);
            min-width: 120px;
            text-align: right;
        }

        .settings-body {
            flex: 1;
            min-height: 0;
            display: flex;
            gap: 30px;
        }

        .settings-cats {
            flex: 0 0 380px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding: 6px;
        }

        .settings-main {
            flex: 1;
            min-width: 0;
            min-height: 0;
            display: flex;
            flex-direction: column;
        }

        .settings-cat {
            display: flex;
            align-items: center;
            gap: 12px;
            min-height: 72px;
            padding: 0 22px;
            border: 1px solid transparent;
            border-radius: 16px;
            background: transparent;
            color: var(--text-primary);
            font-size: 28px;
            font-family: inherit;
            text-align: left;
            cursor: pointer;
        }

        .settings-cat .sc-name { flex: 1; }
        .settings-cat .sc-count { font-size: 20px; color: var(--text-secondary); }
        .settings-cat.selected { background: rgba(10, 132, 255, 0.22); }
        .settings-close { margin-top: auto; justify-content: center; background: rgba(255, 255, 255, 0.08); }

        .settings-rows {
            position: relative;
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: 6px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .settings-row {
            display: flex;
            align-items: center;
            gap: 16px;
            min-height: 88px;
            flex: 0 0 auto;
            padding: 0 22px;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.12);
        }

        .sr-main {
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 4px;
            padding: 12px 0;
            background: transparent;
            border: 0;
            color: var(--text-primary);
            font-family: inherit;
            text-align: left;
            cursor: pointer;
        }

        .sr-label { font-size: 28px; }
        .sr-hint { font-size: 20px; color: var(--text-secondary); }
        .sr-value { min-width: 300px; text-align: center; font-size: 28px; font-weight: 600; }
        .sr-edit { flex: 0 0 auto; font-size: 20px; padding: 6px 14px; border-radius: 10px; background: rgba(255, 255, 255, 0.1); color: var(--text-secondary); }

        .sr-arrow {
            width: 52px;
            height: 52px;
            flex: 0 0 52px;
            border-radius: 26px;
            border: 0;
            background: rgba(255, 255, 255, 0.12);
            color: var(--text-primary);
            font-size: 24px;
            cursor: pointer;
        }

        .sr-input {
            min-width: 300px;
            font-family: inherit;
            font-size: 28px;
            padding: 8px 14px;
            border-radius: 12px;
            border: 2px solid var(--accent);
            background: rgba(0, 0, 0, 0.45);
            color: #ffffff;
        }

        .settings-cat.sf,
        .settings-row.sf,
        .apps-tile.sf,
        .apps-done.sf {
            box-shadow: 0 0 0 4px #0a84ff;
            background: rgba(255, 255, 255, 0.16);
        }

        .apps-page { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
        .apps-head { display: flex; align-items: center; gap: 16px; }
        .apps-title { font-size: 30px; font-weight: 700; flex: 1; }
        .apps-count { font-size: 24px; padding: 8px 18px; border-radius: 999px; background: rgba(10, 132, 255, 0.22); }
        .apps-message { min-height: 28px; font-size: 22px; color: var(--text-secondary); }

        .apps-grid {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: 6px;
            display: flex;
            flex-wrap: wrap;
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            align-content: start;
        }

        .apps-tile {
            display: flex;
            align-items: center;
            gap: 10px;
            min-height: 84px;
            padding: 0 18px;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-primary);
            font-size: 24px;
            font-family: inherit;
            text-align: left;
            cursor: pointer;
        }

        .apps-tile .at-name { flex: 1; min-width: 0; }
        .apps-tile.on { background: rgba(10, 132, 255, 0.28); border-color: #0a84ff; }
        .apps-done { align-self: flex-start; padding: 16px 40px; border-radius: 16px; border: 0; background: var(--accent); color: #ffffff; font-size: 24px; font-weight: 600; font-family: inherit; cursor: pointer; }

        .settings-foot { font-size: 20px; color: var(--text-secondary); min-height: 28px; }
```

- [ ] **Step 5: Replace the modal script**

In `app/index.html`, remove the old modal script: the block from `var settingsModal = document.getElementById('settingsModal');` through the end of `function setModalFocus(el) { ... }` (it contains `tempFavorites`, `tempDevices`, `openSettingsModal`, `renderHDMIOptions`, `closeSettingsModal`, `renderAppSelectorGrid`, `refreshModalNavList`, `setModalFocus`), and the three listeners `document.getElementById('closeModalBtn').addEventListener(...)`, `resetDefaultBtn`, `saveModalBtn` together with their bodies (the Save handler body is replaced by `setSettingValue` calls; nothing in it should remain). Keep `var modalOpen = false;` and delete `var modalNavItems = [];` and `var modalIndex = 0;`. Keep `document.getElementById('customizeBtn')` listeners (`click` -> `openSettingsModal`, `mouseenter` -> `setMainFocus`). Insert, where the removed block was (after the `// --- Customize Shelf & Settings Modal ---` comment):

```
        var settingsModal = document.getElementById('settingsModal');
        var settingsUi = { zone: 'cats', cat: 0, catFocus: 0, row: 1, appIdx: 0, confirmReset: false, message: '' };
        var settingsSavedTimer = null;

        function sEl(tag, className, text) {
            var node = document.createElement(tag);
            if (className) node.className = className;
            if (text !== undefined) node.textContent = text;
            if (tag === 'button') node.setAttribute('type', 'button');
            return node;
        }

        // The "Categories" row comes first, then the category's settings (HDMI rows follow "Shelf apps").
        function settingsRowsFor(cat) {
            return [{ id: 'back', type: 'back', label: 'Categories' }].concat(settingsForCategory(cat));
        }

        function flashSaved() {
            var saved = document.getElementById('settingsSaved');
            saved.textContent = t('Saved');
            clearTimeout(settingsSavedTimer);
            settingsSavedTimer = setTimeout(function() { saved.textContent = ''; }, 1800);
        }

        function settingsHintsFor(zone) {
            if (zone === 'apps') return t('Up / Down: move one row') + '   ' + t('OK: add or remove') + '   ' + t('Back: return');
            if (zone === 'edit') return t('Enter: save') + '   ' + t('Back: cancel');
            return t('Up / Down: move') + '   ' + t('Left / Right: change value') + '   ' + t('OK: select or edit') + '   ' + t('Back: close') + '   ' + t('Changes apply instantly');
        }

        function openSettingsModal() {
            if (shelfEdit) return;
            modalOpen = true;
            settingsUi.zone = 'cats';
            settingsUi.cat = 0;
            settingsUi.catFocus = 0;
            settingsUi.row = 1;
            settingsUi.appIdx = 0;
            settingsUi.confirmReset = false;
            settingsUi.message = '';
            document.getElementById('settingsSaved').textContent = '';
            settingsModal.classList.add('active');
            renderSettings();
        }

        function closeSettingsModal() {
            cancelEdit();
            modalOpen = false;
            settingsModal.classList.remove('active');
            setMainFocus(mainNavItems[curIndex]);
        }

        function renderSettings() {
            var cats = document.getElementById('settingsCats');
            var main = document.getElementById('settingsMain');
            cats.innerHTML = '';
            main.innerHTML = '';
            SETTING_CATEGORIES.forEach(function(name, i) {
                var button = sEl('button', 'settings-cat' + (i === settingsUi.cat ? ' selected' : ''));
                button.setAttribute('data-i', String(i));
                button.appendChild(sEl('span', 'sc-name', t(name)));
                button.appendChild(sEl('span', 'sc-count', String(settingsRowsFor(i).length - 1)));
                button.onmouseover = function() { if (settingsUi.zone === 'cats' || settingsUi.zone === 'rows') { settingsUi.zone = 'cats'; settingsUi.catFocus = i; settingsUi.cat = i; renderRowsOnly(); paintFocus(); } };
                button.onclick = function() { settingsUi.cat = i; settingsUi.catFocus = i; enterRows(); };
                cats.appendChild(button);
            });
            var close = sEl('button', 'settings-cat settings-close', t('Close'));
            close.setAttribute('data-i', String(SETTING_CATEGORIES.length));
            close.onmouseover = function() { if (settingsUi.zone === 'cats') { settingsUi.catFocus = SETTING_CATEGORIES.length; paintFocus(); } };
            close.onclick = closeSettingsModal;
            cats.appendChild(close);
            if (settingsUi.zone === 'apps') renderApps(main); else renderRows(main);
            document.getElementById('settingsHints').textContent = settingsHintsFor(settingsUi.zone);
            paintFocus();
        }

        // Only the right-hand list (used when hovering a category so the category buttons are not rebuilt).
        function renderRowsOnly() {
            var main = document.getElementById('settingsMain');
            main.innerHTML = '';
            renderRows(main);
            Array.prototype.forEach.call(document.querySelectorAll('#settingsCats .settings-cat'), function(b) {
                var i = parseInt(b.getAttribute('data-i'), 10);
                if (i < SETTING_CATEGORIES.length) b.className = 'settings-cat' + (i === settingsUi.cat ? ' selected' : '');
            });
        }

        function renderRows(main) {
            var list = sEl('div', 'settings-rows');
            list.id = 'settingsRows';
            settingsRowsFor(settingsUi.cat).forEach(function(def, i) {
                var row = sEl('div', 'settings-row');
                row.setAttribute('data-i', String(i));
                row.setAttribute('data-id', def.id);
                var label = def.type === 'back' ? '‹ ' + t(def.label) : t(def.label);
                var mainButton = sEl('button', 'sr-main');
                mainButton.appendChild(sEl('span', 'sr-label', label));
                if (def.hint) mainButton.appendChild(sEl('span', 'sr-hint', t(def.hint)));
                mainButton.onclick = function() { settingsUi.zone = 'rows'; settingsUi.row = i; activateRow(def); };
                row.onmouseover = function() { if (settingsUi.zone === 'rows' && settingsUi.row !== i) { settingsUi.row = i; paintFocus(); } };
                row.appendChild(mainButton);
                if (def.type === 'choice') {
                    var prev = sEl('button', 'sr-arrow', '◀');
                    prev.setAttribute('data-dir', '-1');
                    prev.setAttribute('aria-label', t('Previous value'));
                    prev.onclick = function() { settingsUi.zone = 'rows'; settingsUi.row = i; cycleSetting(def, -1); flashSaved(); renderSettings(); };
                    var next = sEl('button', 'sr-arrow', '▶');
                    next.setAttribute('data-dir', '1');
                    next.setAttribute('aria-label', t('Next value'));
                    next.onclick = function() { settingsUi.zone = 'rows'; settingsUi.row = i; cycleSetting(def, 1); flashSaved(); renderSettings(); };
                    row.appendChild(prev);
                    row.appendChild(sEl('span', 'sr-value', settingValueText(def)));
                    row.appendChild(next);
                } else if (def.type === 'text') {
                    row.appendChild(sEl('span', 'sr-value', settingValueText(def)));
                    row.appendChild(sEl('span', 'sr-edit', t('OK to edit')));
                } else if (def.type === 'link') {
                    row.appendChild(sEl('span', 'sr-value', t('%s of 8 selected', String(state.favorites.length))));
                    row.appendChild(sEl('span', 'sr-edit', t('OK to open')));
                } else if (def.type === 'action' && settingsUi.confirmReset) {
                    row.appendChild(sEl('span', 'sr-value', t('Press OK again to confirm')));
                }
                list.appendChild(row);
            });
            main.appendChild(list);
        }

        function renderApps(main) {
            var page = sEl('div', 'apps-page');
            page.id = 'appsPage';
            var head = sEl('div', 'apps-head');
            head.appendChild(sEl('div', 'apps-title', t('Shelf apps')));
            head.appendChild(sEl('div', 'apps-count', t('%s of 8 selected', String(state.favorites.length))));
            page.appendChild(head);
            var message = sEl('div', 'apps-message', settingsUi.message);
            message.id = 'appsMessage';
            page.appendChild(message);
            var grid = sEl('div', 'apps-grid');
            grid.id = 'appsGrid';
            state.catalog.forEach(function(app, i) {
                var on = state.favorites.indexOf(app.id) !== -1;
                var tile = sEl('button', 'apps-tile' + (on ? ' on' : ''));
                tile.setAttribute('data-i', String(i));
                tile.appendChild(sEl('span', 'at-name', app.title));
                if (on) tile.appendChild(sEl('span', 'at-check', '✓'));
                tile.onmouseover = function() { if (settingsUi.appIdx !== i) { settingsUi.appIdx = i; paintFocus(); } };
                tile.onclick = function() { settingsUi.appIdx = i; appsActivate(); };
                grid.appendChild(tile);
            });
            page.appendChild(grid);
            var done = sEl('button', 'apps-done', t('Done'));
            done.id = 'appsDone';
            done.onmouseover = function() { settingsUi.appIdx = state.catalog.length; paintFocus(); };
            done.onclick = function() { settingsUi.zone = 'rows'; renderSettings(); };
            page.appendChild(done);
            main.appendChild(page);
        }

        // Keep the item that is in view in a scrolling list.
        function ensureVisible(container, node) {
            if (!container || !node) return;
            var top = node.offsetTop;
            var bottom = top + node.offsetHeight;
            if (top < container.scrollTop) container.scrollTop = Math.max(0, top - 8);
            else if (bottom > container.scrollTop + container.clientHeight) container.scrollTop = bottom - container.clientHeight + 8;
        }

        // Move the visible focus ring (class "sf") without rebuilding anything.
        function paintFocus() {
            Array.prototype.forEach.call(settingsModal.querySelectorAll('.sf'), function(n) { n.classList.remove('sf'); });
            var node = null;
            if (settingsUi.zone === 'cats') {
                node = settingsModal.querySelector('#settingsCats .settings-cat[data-i="' + settingsUi.catFocus + '"]');
            } else if (settingsUi.zone === 'rows' || settingsUi.zone === 'edit') {
                node = settingsModal.querySelector('#settingsRows .settings-row[data-i="' + settingsUi.row + '"]');
                ensureVisible(document.getElementById('settingsRows'), node);
            } else if (settingsUi.zone === 'apps') {
                node = settingsUi.appIdx >= state.catalog.length ? document.getElementById('appsDone')
                    : settingsModal.querySelector('#appsGrid .apps-tile[data-i="' + settingsUi.appIdx + '"]');
                if (settingsUi.appIdx < state.catalog.length) ensureVisible(document.getElementById('appsGrid'), node);
            }
            if (node) node.classList.add('sf');
        }

        function enterRows() {
            settingsUi.zone = 'rows';
            settingsUi.row = 1;
            settingsUi.confirmReset = false;
            renderSettings();
        }

        function activateRow(def) {
            if (def.type === 'back') { settingsUi.zone = 'cats'; settingsUi.catFocus = settingsUi.cat; settingsUi.confirmReset = false; }
            else if (def.type === 'choice') { cycleSetting(def, 1); flashSaved(); }
            else if (def.type === 'text') { settingsUi.confirmReset = false; renderSettings(); startEdit(def); return; }
            else if (def.type === 'link') { settingsUi.zone = 'apps'; settingsUi.appIdx = 0; settingsUi.message = ''; }
            else if (def.type === 'action') {
                if (settingsUi.confirmReset) { settingsUi.confirmReset = false; resetAllSettings(); flashSaved(); }
                else settingsUi.confirmReset = true;
            }
            renderSettings();
        }

        function startEdit(def) {
            var row = settingsModal.querySelector('#settingsRows .settings-row[data-i="' + settingsUi.row + '"]');
            if (!row) return;
            var value = row.querySelector('.sr-value');
            var input = sEl('input', 'sr-input');
            input.id = 'settingsEditInput';
            input.type = def.secret ? 'password' : 'text';
            input.value = state[def.field] || '';
            input.setAttribute('autocomplete', 'off');
            if (def.placeholder) input.setAttribute('placeholder', t(def.placeholder));
            settingsUi.zone = 'edit';
            settingsUi.editDef = def;
            row.replaceChild(input, value);
            document.getElementById('settingsHints').textContent = settingsHintsFor('edit');
            input.onblur = function() { if (settingsUi.zone === 'edit') commitEdit(); };
            input.focus();
        }

        function commitEdit() {
            var input = document.getElementById('settingsEditInput');
            var def = settingsUi.editDef;
            if (settingsUi.zone !== 'edit' || !input || !def) return;
            settingsUi.zone = 'rows';
            var value = input.value.trim();
            if (value !== (state[def.field] || '')) { setSettingValue(def, value); flashSaved(); }
            renderSettings();
        }

        function cancelEdit() {
            if (settingsUi.zone !== 'edit') return;
            settingsUi.zone = 'rows';
            renderSettings();
        }

        function appsActivate() {
            if (settingsUi.appIdx >= state.catalog.length) { settingsUi.zone = 'rows'; renderSettings(); return; }
            var result = toggleFavorite(state.catalog[settingsUi.appIdx].id);
            settingsUi.message = result === 'full' ? t('Max 8 apps on shelf') : result === 'last' ? t('Keep at least one app on the shelf.') : '';
            if (result === 'added' || result === 'removed') flashSaved();
            renderSettings();
        }

        function isBackKey(e) {
            return e.keyCode === 461 || e.key === 'Escape' || e.key === 'GoBack';
        }

        // Back steps outward: apps page, settings list, category list, then closes the screen.
        function settingsBack() {
            if (settingsUi.zone === 'apps') { settingsUi.zone = 'rows'; renderSettings(); }
            else if (settingsUi.zone === 'rows') { settingsUi.zone = 'cats'; settingsUi.catFocus = settingsUi.cat; settingsUi.confirmReset = false; renderSettings(); }
            else closeSettingsModal();
        }

        function handleSettingsKey(e) {
            var ui = settingsUi, key = e.key, rows, def, count;
            if (ui.zone === 'edit') {
                if (key === 'Enter') { commitEdit(); e.preventDefault(); }
                else if (isBackKey(e)) { cancelEdit(); e.preventDefault(); }
                return;
            }
            if (isBackKey(e)) { settingsBack(); e.preventDefault(); return; }
            if (ui.zone === 'cats') {
                if (key === 'ArrowDown') ui.catFocus = Math.min(ui.catFocus + 1, SETTING_CATEGORIES.length);
                else if (key === 'ArrowUp') ui.catFocus = Math.max(ui.catFocus - 1, 0);
                else if (key === 'ArrowRight' || key === 'Enter') {
                    if (ui.catFocus === SETTING_CATEGORIES.length) { if (key === 'Enter') closeSettingsModal(); e.preventDefault(); return; }
                    enterRows();
                    e.preventDefault();
                    return;
                } else return;
                if (ui.catFocus < SETTING_CATEGORIES.length) ui.cat = ui.catFocus;
                e.preventDefault();
                renderSettings();
                return;
            }
            if (ui.zone === 'rows') {
                rows = settingsRowsFor(ui.cat);
                def = rows[ui.row];
                if (key === 'ArrowDown') { ui.row = Math.min(ui.row + 1, rows.length - 1); ui.confirmReset = false; }
                else if (key === 'ArrowUp') { ui.row = Math.max(ui.row - 1, 0); ui.confirmReset = false; }
                else if ((key === 'ArrowLeft' || key === 'ArrowRight') && def.type === 'choice') { cycleSetting(def, key === 'ArrowRight' ? 1 : -1); flashSaved(); }
                else if (key === 'Enter') { activateRow(def); e.preventDefault(); return; }
                else return;
                e.preventDefault();
                renderSettings();
                return;
            }
            if (ui.zone === 'apps') {
                count = state.catalog.length;
                if (key === 'ArrowDown') ui.appIdx = ui.appIdx >= count ? count : (ui.appIdx + 5 < count ? ui.appIdx + 5 : count);
                else if (key === 'ArrowUp') ui.appIdx = ui.appIdx >= count ? count - 1 : (ui.appIdx - 5 >= 0 ? ui.appIdx - 5 : ui.appIdx);
                else if (key === 'ArrowLeft') ui.appIdx = ui.appIdx >= count ? count - 1 : Math.max(ui.appIdx - 1, 0);
                else if (key === 'ArrowRight') ui.appIdx = ui.appIdx >= count ? count : Math.min(ui.appIdx + 1, count - 1);
                else if (key === 'Enter') { appsActivate(); e.preventDefault(); return; }
                else return;
                e.preventDefault();
                paintFocus();
            }
        }
```

- [ ] **Step 6: Route keys to the new screen**

In the key handler (`document.addEventListener('keydown', function(e) {`), replace this exact block:

```
            // Back button on LG Magic Remote (461) or Escape
            if (e.keyCode === 461 || e.key === 'Escape' || e.key === 'GoBack') {
                if (modalOpen) {
                    closeSettingsModal();
                    e.preventDefault();
                } else if (drawerOpen) {
```

with:

```
            if (modalOpen) {
                handleSettingsKey(e);
                return;
            }

            // Back button on LG Magic Remote (461) or Escape
            if (e.keyCode === 461 || e.key === 'Escape' || e.key === 'GoBack') {
                if (drawerOpen) {
```

and delete the old `if (modalOpen) { ... modalNavItems ... }` block that follows the `if (drawerOpen) { ... }` block (the one with `modalIndex = (modalIndex + 1) % modalNavItems.length`).

- [ ] **Step 7: Run the checks to verify they pass**

Run `TEST`. Expected: `[+] browser tests passed`. (If it reports `ambient scenario did not finish`, raise `--virtual-time-budget` as described in the conventions.)
Run `ES5`. Expected: success, exit code 0.
Run `CHECK`. Expected: `[+] all checks passed`.
Also search `app/index.html` for leftovers and confirm none remain: `modal-nav`, `modalNavItems`, `modalIndex`, `tempFavorites`, `tempDevices`, `refreshModalNavList`, `setModalFocus`, `renderAppSelectorGrid`, `renderHDMIOptions`, `cfgCity`, `saveModalBtn`.

- [ ] **Step 8: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py
git commit -m "feat: remote-friendly Customize screen with categories, rows and an apps page

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Translations, docs and test tidy-up

**Files:**
- Modify: `app/index.html` (`I18N` dictionaries: `pt`, `es`, `de`, `fr`)
- Modify: `scripts/browser_test.py` (probe translation list)
- Modify: `README.md`, `ROADMAP.md`

**Interfaces:**
- Consumes: the strings used by Tasks 1 and 2.
- Produces: complete translations; docs for the new screen.

- [ ] **Step 1: Add the failing probe check**

In `scripts/browser_test.py`, inside `PROBE`, find the line that checks translations of the earlier new strings (the `.forEach(function (k) { if (!Object.prototype.hasOwnProperty.call(I18N.pt, k)) out.ambient.push('no translation: ' + k); })` list) and add these keys to that list (keep the existing ones):

```
'Shelf & Inputs', 'Look & Feel', 'Weather & Location', 'Photos & Screensaver', 'Accounts & Keys', 'Close', 'Categories',
'Shelf apps', 'OK to edit', 'OK to open', 'Not set', 'Saved', 'Reset to defaults', 'Press OK again to confirm',
'Up / Down: move', 'Left / Right: change value', 'OK: select or edit', 'Back: close', 'Changes apply instantly',
'Up / Down: move one row', 'OK: add or remove', 'Back: return', 'Enter: save', 'Back: cancel', '%s of 8 selected',
'Keep at least one app on the shelf.', 'Previous value', 'Next value',
'Dimmed, slowly moving photos behind the dashboard', 'Photos behind the clock when the TV is idle',
'Plays a hidden video so LG does not cover ours', 'For the photos. Stored on this TV only',
'Optional, for weekly trending movies and shows'
```

- [ ] **Step 2: Run the test to verify it fails**

Run `TEST`. Expected: FAIL with `no translation:` entries for every key above that is not already in the dictionaries (`Close`, `Saved`, `Done`-style keys that exist are fine).

- [ ] **Step 3: Add the translations**

In `app/index.html`, in each of the four `I18N` language dictionaries, add an entry for every English string below that is not already a key there (check with a search; `Max 8 apps on shelf`, `Defaults restored`, `Done`, `Cancel`, `On`, `Off` and the old setting labels already exist and must not be duplicated). Write natural, short UI translations in the same style as the neighbouring entries in each dictionary (informal-neutral, `pt` is Brazilian Portuguese, `es` neutral Spanish, `de` uses "du"-free neutral labels, `fr` uses infinitive or noun labels). Put the new entries together at the end of each dictionary's last line group, using typographic apostrophes (`’`) inside French strings. The English keys:

```
'Shelf & Inputs', 'Look & Feel', 'Weather & Location', 'Photos & Screensaver', 'Accounts & Keys', 'Close', 'Categories',
'Shelf apps', 'OK to edit', 'OK to open', 'Not set', 'Saved', 'Reset to defaults', 'Press OK again to confirm',
'Up / Down: move', 'Left / Right: change value', 'OK: select or edit', 'Back: close', 'Changes apply instantly',
'Up / Down: move one row', 'OK: add or remove', 'Back: return', 'Enter: save', 'Back: cancel',
'%s of 8 selected' (keep the %s placeholder), 'Keep at least one app on the shelf.', 'Previous value', 'Next value',
'Dimmed, slowly moving photos behind the dashboard', 'Photos behind the clock when the TV is idle',
'Plays a hidden video so LG does not cover ours', 'For the photos. Stored on this TV only',
'Optional, for weekly trending movies and shows'
```

Reference translations already in the file to stay consistent with: `Customize` -> `Personalizar` (pt, es), `Anpassen` (de), `Personnaliser` (fr); `Theme Mode`, `Clock Format`, `Language`, `Performance Mode` are translated in each dictionary.

- [ ] **Step 4: Run the checks to verify they pass**

Run `TEST` (all five languages `ok`, `translation keys differ` must not appear), `ES5`, `CHECK`. Expected: all pass.

- [ ] **Step 5: Update the README and ROADMAP**

In `README.md` (English), directly above the settings table (the table whose header row is `| Setting | What It Does |`), add this paragraph:

```
**Using the Customize screen with the remote:** pick a category on the left (Up/Down, then Right or OK), then move through its settings with Up/Down. On a setting, Left/Right changes its value (or OK cycles it); OK on a text setting opens the keyboard. **Shelf apps** opens a page where Up/Down move a whole row of apps and OK adds or removes one (up to 8). Every change is saved the moment you make it, so there is no Save button; Back steps out one level at a time. Keys (Unsplash, TMDB) are never shown on screen, only dots.
```

Add the equivalent Portuguese paragraph above the Portuguese settings table (header row `| Configuração | O Que Faz |`):

```
**Usando a tela Personalizar com o controle remoto:** escolha uma categoria à esquerda (Cima/Baixo, depois Direita ou OK) e percorra os ajustes com Cima/Baixo. Em um ajuste, Esquerda/Direita muda o valor (ou OK avança); OK em um ajuste de texto abre o teclado. **Apps da prateleira** abre uma página em que Cima/Baixo movem uma linha inteira de apps e OK adiciona ou remove um (até 8). Cada mudança é salva na hora, por isso não há botão Salvar; Voltar sai um nível por vez. As chaves (Unsplash, TMDB) nunca aparecem na tela, só pontos.
```

In `ROADMAP.md`, add a new checked bullet under the v1.3 heading's list: `- [x] **Remote-friendly Customize screen:** categories, one row per setting, an apps page, instant save, visible focus and masked keys.`

Run `CHECK`. Expected: `[+] all checks passed`.

- [ ] **Step 6: Commit**

```bash
git add app/index.html docs/index.html scripts/browser_test.py README.md ROADMAP.md
git commit -m "feat: translate the new Customize screen and document how to use it

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Verify on the real TV (manual, nothing committed)

**Files:**
- No source changes. Rebuilds `dist/org.webos.freemytv_1.4.0_all.ipk` locally; do not commit it.

**Interfaces:**
- Consumes: the finished app and the TV at `10.100.102.2` with Developer Mode on. Never read back or display a saved key.

- [ ] **Step 1: Rebuild and install**

```powershell
Remove-Item 'C:\Users\97254\Downloads\FreeMyTvWebOS\dist\*.ipk'
python 'C:\Users\97254\Downloads\FreeMyTvWebOS\scripts\build.py'
python 'C:\Users\97254\Downloads\FreeMyTvWebOS\scripts\install.py' 10.100.102.2
```

Expected: `[+] SUCCESS! Free My TV is installed and running on your LG TV!`

- [ ] **Step 2: Walk the new screen with the remote**

Open Customize. Confirm: a visible focus ring on the first category; Down moves through the categories and the right pane changes; Right enters a category; on a choice row Left/Right changes the value and "Saved" flashes; the first category's HDMI rows work; Shelf apps opens the grid and Down moves a whole row; the shelf behind updates immediately; Back steps outward and finally closes. Capture screenshots with `shot.py`, blacking out any key field first if one is visible.

- [ ] **Step 3: Keys and the keyboard**

On Accounts & Keys, press OK on the Unsplash row: the TV keyboard opens on an inline password input. The user types or pastes the key with the key-entry helper; afterwards the row shows only dots. Do not display the key.

- [ ] **Step 4: Report**

Report what worked and anything awkward (focus visibility, scrolling, keyboard behaviour). Do not commit anything; `git status` should show only `dist/*.ipk` modified.
