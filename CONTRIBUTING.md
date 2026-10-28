# Contributing

Thanks for helping! The whole app is one file, [`app/index.html`](app/index.html), plus a few helper scripts.

## Rules that keep old TVs working
- **ES5 only** in the app's JavaScript: no `const`/`let`, arrow functions, template literals, `Array.prototype.find` or `async/await`. webOS 3.x runs Chromium 38. CI enforces this.
- Add a flexbox fallback before any `display: grid`, and guard `fetch` (see existing code).
- No new network destinations without listing them in the README's "Network requests" table. No telemetry.
- All third-party text (TMDB, TVMaze) must be set with `textContent`, never `innerHTML`.

## Workflow
1. Edit `app/index.html`.
2. `python scripts/sync_docs.py` copies the app into `docs/` (the live preview).
3. `python scripts/check.py` (scripts compile, docs in sync, ipk matches `appinfo.json`) and, with Chrome installed,
   `python scripts/browser_test.py` (boots the app in all five languages and checks translations).
4. If you changed the app for a release: bump `app/appinfo.json`, run `python scripts/build.py`, commit the new ipk
   in `dist/` (remove the old one), then tag `vX.Y.Z`; the release workflow publishes the ipk and Homebrew manifest.

## Adding or fixing a translation
UI text is looked up by its English string in the `I18N` object in `app/index.html`. Add the English text to every language
(the browser test fails if the language key sets differ) and wrap new JS-built text in `t('English text %s', value)`.

## Reporting a bug
Please include your TV model, webOS version and Free My TV version; the issue form asks for them.
