# Ambient Screensaver (Unsplash) — Design

Date: 2026-10-30
Status: draft, awaiting review
Branch: `feature/ambient-screensaver` (off `main`, local only)

## Goal

Finish the v1.3 roadmap item "OLED Care Screensaver": replace the pure-black idle screen with a dimmed, slowly moving
Unsplash photo (night sky, aurora, dark mountains, aerial earth, forest) while keeping the existing pixel-shifting
clock and date on top. The existing black clock screensaver stays as the fallback.

## Scope

In scope
- Ambient photo layer behind the existing screensaver clock, in `app/index.html`.
- Unsplash fetching, caching, rate-limit budgeting, attribution.
- Three Customize-modal settings plus the Unsplash key field.
- Checks in `scripts/check.py` and `scripts/browser_test.py`; on-TV verification.
- README and ROADMAP wording for the shipped behavior.
- Run `python scripts/sync_docs.py` after editing `app/index.html`: `docs/index.html` is a verbatim copy served by
  GitHub Pages and CI fails if they differ. The live-preview copy has no TV, so the ambient layer falls back to the
  black clock there unless a key is set in its Customize modal.

Out of scope
- Bundled photos, Google Photos, other image sources.
- Changing the 25-second clock jump.
- Any change to the install scripts or `dist/` artifacts.

## Settings (Customize modal, persisted in `localStorage`)

| Setting | Key | Values | Default |
|---|---|---|---|
| Screensaver starts after | `fmtv_idle_mins` | 1 / 3 / 5 / 10 / 30 minutes | 3 minutes |
| Unsplash Access Key | `fmtv_unsplash_key` | text | empty |
| Ambient screensaver | `fmtv_ambient` | On / Off | On |
| Photo duration | `fmtv_ambient_secs` | 30 s / 90 s / 5 min | 90 s |
| Motion | `fmtv_ambient_motion` | Ken Burns / Drift only / None | Ken Burns |

"Screensaver starts after" replaces the hard-coded 3-minute idle limit and applies to both the ambient and the black
clock screensaver.

The ambient layer runs only when a key is set, the setting is On, the photo cache is non-empty, and the engine has
`fetch` (webOS 3.x on Chromium 38 does not, so those TVs keep the black clock). Otherwise the screensaver is exactly
today's black clock.

## Data and fetching

- Request: `GET https://api.unsplash.com/photos/random?count=30&orientation=landscape&content_filter=high&query=<theme>`
  with header `Authorization: Client-ID <key>`.
- Themes (one request each per refresh): `night sky stars`, `aurora`, `dark mountains night`, `aerial earth`,
  `forest fog`. A refresh is about 5 calls and about 150 photos.
- Cached per photo: `id`, raw URL, `color` (average colour), photographer name, `download_location`. Stored in
  `localStorage` as metadata only; image bytes use the browser cache.
- Image size: `urls.raw` with `w=3840&q=70&fm=jpg` when `screen.width >= 3840`, otherwise `w=1920`.
- Refresh: in the background while the TV is not in screensaver, at most every 12 hours, or when fewer than 20
  photos are cached. The screensaver itself never calls the API.

## Rate limit (key allows 50 requests per hour)

- A rolling one-hour call log in `localStorage`. The app caps itself at 40 calls per hour.
- Each API response's `X-Ratelimit-Remaining` is read; below 5 stops fetching.
- A 403 or 429 pauses fetching for one hour.
- `download_location` pings use the same call log. A ping is sent only while fewer than 30 calls were made in the
  last hour, which keeps 10 for refreshes, and each photo is pinged at most once (the ids are remembered in
  `localStorage`).
- Photo URLs load from Unsplash's image servers, not the API.
- Result: about 15 API calls a day for refreshes, plus one ping per photo shown (at most 30 per hour).

## Rendering

- New `.screensaver-photo` layer (two stacked `<img>` for crossfade) under the existing `.screensaver-clock-wrap`.
- Photo duration per setting; 4 s crossfade; the next photo preloads before the swap.
- Motion (compositor-only: `transform` and `opacity`):
  - Ken Burns: scale 1.06 to 1.14 across the photo duration, plus a random drift of at most 2.5% of the photo size,
    linear easing. The 1.06 floor over-scans 3% per side, so the drift never shows black edges.
  - Drift only: the same drift at a constant scale of 1.06.
  - None: crossfade only.
  - The existing performance mode forces None.
- Burn-in care: base layer opacity about 0.55; extra dimming computed from the photo's `color` luminance for bright
  photos; vignette; the clock and date keep the existing 25 s random jump.
- Attribution: "Photo by NAME on Unsplash" in the clock wrapper, so it moves with the clock.
- Exit: unchanged (any key, mouse move or click via the existing handlers).

## Failure behavior

A missing key, offline, a network error, bad JSON, an empty cache or a paused budget all fall back to the black clock
screensaver without error UI. A single photo that fails to load is skipped.

## Testing

- `scripts/browser_test.py` (headless Chrome, all five languages): the dim, budget, photo-URL and photo-shape helpers
  are checked with fixed inputs; settings defaults, the new controls and all translations must exist; with `fetch`
  stubbed, a refresh makes 5 calls and caches 150 photos, a 403 or a low `X-Ratelimit-Remaining` pauses fetching, the
  hourly cap blocks calls, and the ambient layer shows (with credit and one download ping) only when a key is set,
  the setting is On and the cache is non-empty; Ken Burns stays within 2.5% drift and performance mode stays still.
- `scripts/check.py` and the CI ES5 check keep passing (docs in sync, no ES6 syntax).
- On the TV: install, set the key, force the screensaver, screenshot to confirm photo, credit text and dimming.

## Git

Local branch `feature/ambient-screensaver` off `main`; this clone has no `development` branch. Nothing is pushed or
merged without explicit approval. The locally rebuilt `dist/*.ipk` is not part of any commit.

## Open items

None blocking. The Unsplash Access Key must be supplied by the user before the on-TV test.

## Addendum: keep LG's screensaver away, and photos on the home screen

Added after on-TV testing (LG UR91, webOS 23). LG's own screensaver takes over a few minutes after the last remote
press and covers ours. A throwaway test app showed that playing a tiny muted video (a 64x36 canvas stream shown in a
4x4 px `<video>`) held it off for 7+ minutes; the Screen Wake Lock API was refused (`NotAllowedError`).

### Keep LG's screensaver away (setting `fmtv_keep_awake`, On / Off, default On)
- While our screensaver is showing (ambient or black clock), the app plays that hidden muted video. It starts in
  `enterScreensaver()` and stops in `exitScreensaver()`. Any key press still exits.
- Skipped silently when the engine has no `canvas.captureStream` (older webOS).
- Risk to mention in the docs: the TV's own auto-sleep may also not fire while our screensaver runs; the switch turns
  the behaviour off.

### Photos on the home screen (setting `fmtv_home_photos`, On / Off, default Off)
- A full-screen photo layer behind the dashboard (below `.container`), fed by the same cache, key, photo duration and
  motion settings as the screensaver; opacity is the screensaver's dim value times 0.55 (about 0.30 for dark photos), plus
  a top and bottom gradient so text stays readable.
- It keeps the Unsplash credit in a small dim line in the bottom-left corner.
- It runs only when a key is set, the cache is non-empty and the engine has `fetch`; it pauses while the screensaver
  is showing and resumes on exit. It does not depend on the "Ambient Photo Screensaver" switch.
- Background refreshes run when either "Ambient Photo Screensaver" or "Photos on Home Screen" is On.
- Shown photos are pinged under the same budget rules (at most 30 per hour, each photo once).

### Photo player refactor
The screensaver-only render code becomes one `ambientPlayer(cfg)` factory with two instances (screensaver, home
screen). Each start or stop bumps a run counter so a late image load from an earlier run is ignored (this fixes the
deferred stale-preload finding).

### Testing additions
`scripts/browser_test.py` scenarios: stale preload ignored, A/B swap, skip-on-error and `src` cleared after exit; home
photos on and off, takeover by the screensaver and resume, no key, refresh for home photos only; keep-awake video
starts and stops with the screensaver, respects Off, and survives a missing `captureStream`. State defaults, new
controls and the new translations are probed.

## Addendum 2: Customize screen redesign (remote-friendly settings)

Why: on the real TV, pressing Down in the old Customize screen looked stuck. The modal treated Down and Right as "next
item" in one flat list of about 45 controls, so Down in the 4-column app grid moved one tile right, it took about 24
presses to leave the app grid, dropdowns and text boxes showed no focus mark, and nothing was saved until Save & Apply.
Mockups: https://claude.ai/artifact/6u5pzPR8CkQ42uPkQSYBia (boards 1-3).

### Layout
- Two panes inside the existing `#settingsModal`: a category list (left) and the settings of the current category
  (right), a footer line of key hints, and a short "Saved" confirmation in the header.
- Categories, in order: Shelf & Inputs, Look & Feel, Weather & Location, Photos & Screensaver, Accounts & Keys, plus a
  "Close" item at the end of the list.
- Every setting is one row: label (and an optional one-line hint) on the left, value on the right. A clearly visible
  focus ring (class `sf`) marks the focused item; the right pane scrolls to keep the focused row in view.
- Row types: `choice` (value cycles through options, with ◀ ▶ arrows shown), `text` (value shown; OK opens an inline
  input and the TV keyboard), `link` (OK opens a sub-page), `action` (OK runs it).
- Secret fields (Unsplash Access Key, TMDB API key) show only a fixed run of dots and never the value, in the row and
  in the inline input (`type="password"`).

### Settings by category
1. Shelf & Inputs: Shelf apps (link to the apps page, value "N of 8 selected"), then one choice row per HDMI input
   (device preset: HDMI, PS5, PS4, Xbox, Nintendo Switch, Gaming PC).
2. Look & Feel: Theme Mode, Clock Format, Text Size, Performance Mode, Language.
3. Weather & Location: City Name, Auto-locate by IP.
4. Photos & Screensaver: Photos on Home Screen, Ambient Photo Screensaver, Screensaver Starts After, Photo Duration,
   Photo Motion, Keep LG Screensaver Away.
5. Accounts & Keys: Unsplash Access Key, TMDB API Key, then "Reset to defaults" (needs a second OK to confirm).

### Remote keys
- Category list: Up and Down move (no wrap), Right or OK enters the category (focus lands on its first setting),
  Left does nothing; on "Close", OK closes.
- Settings list: the first item of every category is a "Categories" row (OK returns to the category list). Up and Down
  move (no wrap). On a `choice` row Left and Right change the value (they wrap through the options) and OK cycles
  forward; on a `text` row OK edits; on a `link` row OK opens the page.
- Editing text: OK shows an inline input with the value; Enter commits, Escape or Back cancels; leaving the input
  (blur) commits.
- Apps page: a 5-column grid of every catalog app, then a Done button below it. Up and Down move by row (the Done
  button after the last row), Left and Right by tile, OK adds or removes the app (maximum 8, minimum 1, with an inline
  message when refused), Back or Done returns to the Shelf & Inputs list.
- Back or Escape steps outward: apps page, then settings list, then category list, then closes the whole screen.
- Pointer (Magic Remote): hovering an item focuses it and clicking acts like OK; the arrows on a choice row act as
  Left and Right.
- Every change is applied and saved to `localStorage` immediately; there is no Save or Cancel. The same side effects
  run that the old Save & Apply ran, but only the ones that setting needs (for example a theme change re-applies the
  theme; a city change refetches the weather; an Unsplash key change clears the photo cache and pause marker and
  refreshes).

### Settings schema
A single `SETTINGS` array in `app/index.html` drives both the screen and the persistence. Each entry has `id`, `cat`,
`type`, `label`, optional `hint`, and for stored settings `field` (the `state` field), `store` (the `localStorage` key),
`def` (default), `options` (`[value, label]` pairs, for choices), `secret`, and `apply`. HDMI rows are generated from
the catalog. Defaults must equal the current state defaults.

### Strings and tests
All new UI strings are translated into pt, es, de and fr (key sets stay identical). The old controls (`cfg*` ids,
Save & Apply, Cancel, Reset Defaults, the flat focus list) are removed; the browser test is rewritten to probe the
schema, drive the screen with synthetic key events, and check persistence, masking, scroll-follow and the apps page.
