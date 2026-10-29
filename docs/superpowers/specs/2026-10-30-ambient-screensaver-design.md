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
- Result: under about 15 API calls a day in normal use.

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

- `scripts/check.py`: a luminance-to-dim function and the rate-limit budget logic are pure functions, covered with
  fixed inputs. Settings keys and defaults present.
- `scripts/browser_test.py`: with `fetch` stubbed, the ambient layer shows when a key is set and the cache is
  populated; the black clock shows with no key, with a 403, and when offline.
- On the TV: install, set the key, force the screensaver, screenshot to confirm photo, credit text and dimming.

## Git

Local branch `feature/ambient-screensaver` off `main`; this clone has no `development` branch. Nothing is pushed or
merged without explicit approval. The locally rebuilt `dist/*.ipk` is not part of any commit.

## Open items

None blocking. The Unsplash Access Key must be supplied by the user before the on-TV test.
