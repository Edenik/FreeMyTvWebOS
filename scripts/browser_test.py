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
    "en": ("customizeBtn", "Settings"),
    "pt": ("customizeBtn", "Ajustes"),
    "es": ("customizeBtn", "Ajustes"),
    "de": ("customizeBtn", "Einstellungen"),
    "fr": ("customizeBtn", "Réglages"),
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
  out.text = document.getElementById('customizeBtn').textContent.replace(/^\s+|\s+$/g, '');
  out.ambient = [];
  function eq(name, got, want) {
    if (got !== want) out.ambient.push(name + ': got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want));
  }
  function need(name) {
    if (typeof window[name] !== 'function') { out.ambient.push(name + ' missing'); return false; }
    return true;
  }
  if (need('ambientDim')) {
    eq('dim black', ambientDim('#000000'), 0.85);
    eq('dim white', ambientDim('#ffffff'), 0.5);
    eq('dim mid', ambientDim('#808080'), 0.67);
    eq('dim bad', ambientDim('nope'), 0.68);
    eq('dim none', ambientDim(undefined), 0.68);
  }
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
  if (need('screensaverWeatherVisible')) {
    eq('ssweather noon', screensaverWeatherVisible(12, '22C'), true);
    eq('ssweather 22', screensaverWeatherVisible(22, '22C'), true);
    eq('ssweather 23', screensaverWeatherVisible(23, '22C'), false);
    eq('ssweather 04', screensaverWeatherVisible(4, '22C'), false);
    eq('ssweather 05', screensaverWeatherVisible(5, '22C'), true);
    eq('ssweather loading', screensaverWeatherVisible(12, 'Loading...'), false);
  }
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
  if (need('wizardNeeded')) {
    var savedKeys = {}, k2, n2;
    for (n2 = localStorage.length - 1; n2 >= 0; n2--) { k2 = localStorage.key(n2); if (k2.indexOf('fmtv_') === 0) { savedKeys[k2] = localStorage.getItem(k2); localStorage.removeItem(k2); } }
    eq('wizard fresh', wizardNeeded(), true);
    ['fmtv_launch_hist', 'fmtv_theme', 'fmtv_favorites', 'fmtv_city'].forEach(function (key) {
      localStorage.setItem(key, 'x');
      eq('wizard existing install (' + key + ')', wizardNeeded(), false);
      localStorage.removeItem(key);
    });
    localStorage.setItem('fmtv_setup_done', '1');
    eq('wizard done', wizardNeeded(), false);
    localStorage.removeItem('fmtv_setup_done');
    eq('wizard fresh again', wizardNeeded(), true);
    eq('wizard boot flag is a boolean', typeof wizardAtBoot, 'boolean');
    // The harness seeds fmtv_lang and fmtv_setup_done before the app starts, so this profile counts as an existing install.
    eq('wizard not shown at boot for a seeded profile', wizardAtBoot, false);
    Object.keys(savedKeys).forEach(function (key) { localStorage.setItem(key, savedKeys[key]); });
  }
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
    applyProfile({ userName: 'Only' });
    eq('profile applies only the fields present', state.theme + '|' + state.favorites.join(','), JSON.parse(before).theme + '|' + JSON.parse(before).favorites.join(','));
    applyProfile(JSON.parse(before));
    eq('profile restored again', JSON.stringify(snapshotProfile()), before);
    eq('profile fields', PROFILE_FIELDS.join(','), 'userName,theme,city,lat,lon,ambient,homePhotos');
    eq('profile snapshot has the lock', typeof snapshotProfile().locked, 'boolean');
  }
  if (need('recordLaunch') && need('recentApps')) {
    localStorage.removeItem('fmtv_launch_hist');
    var T = new Date(2026, 9, 30, 21, 10).getTime();
    var TA = new Date(2026, 9, 30, 15, 10).getTime(); // afternoon: netflix's 21:10 launches are no habit then, so plain recency decides
    recordLaunch('netflix', T - 86400000);
    recordLaunch('youtube.leanback.v4', T - 3600000);
    recordLaunch('netflix', T - 86400000 + 1000);
    var hist = readLaunchHist();
    eq('hist count', hist.netflix.n, 2);
    var recent = recentApps(hist, DEFAULT_CATALOG, 3, TA);
    eq('recent order', recent.map(function (r) { return r.app.id; }).join(','), 'youtube.leanback.v4,netflix');
    eq('recent limit', recentApps(hist, DEFAULT_CATALOG, 1, TA).length, 1);
    eq('recent unknown app ignored', recentApps({ nope: { t: 1, n: 1 } }, DEFAULT_CATALOG, 3, TA).length, 0);
    eq('caption today', openedCaption('Netflix', T - 3600000, T), t('%s, opened at %s', 'Netflix', '20:10'));
    eq('caption older day', openedCaption('Netflix', T - 3 * 86400000, T).indexOf('Netflix') !== -1, true);
    localStorage.setItem('fmtv_launch_hist', JSON.stringify({ netflix: 5, youtube: { t: 'x' }, ok: { t: 1, n: 1 } }));
    eq('hist malformed dropped', Object.keys(readLaunchHist()).join(','), 'ok');
    localStorage.removeItem('fmtv_launch_hist');
    // time-of-day buckets: hours 3, 8, 14, 21 land in buckets 0..3
    [3, 8, 14, 21].forEach(function (h) { recordLaunch('bk', new Date(2026, 9, 30, h, 5).getTime()); });
    recordLaunch('bk', new Date(2026, 9, 30, 23, 59).getTime());
    eq('buckets counted', JSON.stringify(readLaunchHist().bk.b), '[1,1,1,2]');
    eq('bucket edges', [0, 5, 6, 11, 12, 17, 18, 23].map(function (h) { return launchBucket(new Date(2026, 9, 30, h).getTime()); }).join(','), '0,0,1,1,2,2,3,3');
    localStorage.setItem('fmtv_launch_hist', JSON.stringify({ old: { t: T, n: 3 }, bad: { t: T, n: 1, b: 'x' }, bad2: { t: T, n: 1, b: [1, 'a', null, -4, 9, 9] }, bad3: { t: T, n: 1, b: { 0: 5 } } }));
    eq('old entry gets zeros', JSON.stringify(readLaunchHist().old.b), '[0,0,0,0]');
    eq('malformed b zeros', JSON.stringify(readLaunchHist().bad.b), '[0,0,0,0]');
    eq('partly malformed b', JSON.stringify(readLaunchHist().bad2.b), '[1,0,0,0]');
    eq('object b zeros', JSON.stringify(readLaunchHist().bad3.b), '[0,0,0,0]');
    recordLaunch('bad', new Date(2026, 9, 30, 9, 0).getTime());
    eq('record repairs malformed b', JSON.stringify(readLaunchHist().bad.b), '[0,1,0,0]');
    localStorage.removeItem('fmtv_launch_hist');
    for (var ci = 0; ci < 40; ci++) recordLaunch('app' + ci, T + ci);
    eq('history cap', Object.keys(readLaunchHist()).length, 30);
    localStorage.removeItem('fmtv_launch_hist');
    // habit ranking (T is 21:10 = evening bucket 3)
    var ids = function (h) { return recentApps(h, DEFAULT_CATALOG, 5, T).map(function (r) { return r.app.id; }).join(','); };
    var HR = 3600000, DAY = 86400000;
    eq('rank (a) no bucket data = newest first', ids({ netflix: { t: T - 5 * HR, n: 1 }, 'youtube.leanback.v4': { t: T - HR, n: 1 } }), 'youtube.leanback.v4,netflix');
    eq('rank (a) empty b = newest first', ids({ netflix: { t: T - 5 * HR, n: 1, b: [0, 0, 0, 0] }, 'youtube.leanback.v4': { t: T - HR, n: 1, b: 'x' } }), 'youtube.leanback.v4,netflix');
    eq('rank (b) habit beats recent', ids({ netflix: { t: T - 5 * HR, n: 2, b: [0, 0, 0, 2] }, 'youtube.leanback.v4': { t: T - HR, n: 1, b: [0, 1, 0, 0] } }), 'netflix,youtube.leanback.v4');
    eq('rank (c) one launch is not a habit', ids({ netflix: { t: T - 5 * HR, n: 1, b: [0, 0, 0, 1] }, 'youtube.leanback.v4': { t: T - HR, n: 1, b: [0, 1, 0, 0] } }), 'youtube.leanback.v4,netflix');
    eq('rank habit in other bucket ignored', ids({ netflix: { t: T - 5 * HR, n: 5, b: [0, 5, 0, 0] }, 'youtube.leanback.v4': { t: T - HR, n: 1, b: [0, 0, 0, 0] } }), 'youtube.leanback.v4,netflix');
    eq('rank stale habit ignored', ids({ netflix: { t: T - 20 * DAY, n: 9, b: [0, 0, 0, 9] }, 'youtube.leanback.v4': { t: T - HR, n: 1 } }), 'youtube.leanback.v4,netflix');
    eq('rank (d) tie by recency', ids({ netflix: { t: T - 5 * HR, n: 2, b: [0, 0, 0, 2] }, 'youtube.leanback.v4': { t: T - HR, n: 2, b: [0, 0, 0, 2] } }), 'youtube.leanback.v4,netflix');
    var cat0 = DEFAULT_CATALOG[0].id, cat1 = DEFAULT_CATALOG[1].id, tieH = {};
    tieH[cat1] = { t: T - HR, n: 1 }; tieH[cat0] = { t: T - HR, n: 1 };
    eq('rank (d) tie by catalog order', ids(tieH), cat0 + ',' + cat1);
    eq('rank 3-arg form still works', recentApps({ netflix: { t: 1, n: 1 }, 'youtube.leanback.v4': { t: 2, n: 1 } }, DEFAULT_CATALOG, 3).map(function (r) { return r.app.id; }).join(','), 'youtube.leanback.v4,netflix');
    eq('scene ignores habit', pickSceneApp('streaming', { netflix: { t: 9, n: 1, b: [0, 0, 0, 0] }, 'com.disney.disneyplus-prod': { t: 5, n: 8, b: [0, 0, 0, 8] } }, DEFAULT_CATALOG, {}).id, 'netflix');
  }
  if (need('pickSceneApp')) {
    var hist2 = { 'com.disney.disneyplus-prod': { t: 5, n: 1 }, netflix: { t: 9, n: 1 } };
    eq('scene streaming newest', pickSceneApp('streaming', hist2, DEFAULT_CATALOG, {}).id, 'netflix');
    eq('scene streaming none used', pickSceneApp('streaming', {}, DEFAULT_CATALOG, {}).id, 'youtube.leanback.v4');
    eq('scene game none named', pickSceneApp('game', {}, DEFAULT_CATALOG, {}), null);
    eq('scene game ps5', pickSceneApp('game', {}, DEFAULT_CATALOG, { 'com.webos.app.hdmi2': 'ps5' }).id, 'com.webos.app.hdmi2');
    eq('scene direct id', pickSceneApp('spotify-beehive', {}, DEFAULT_CATALOG, {}).id, 'spotify-beehive');
    eq('scene direct missing', pickSceneApp('nope', {}, DEFAULT_CATALOG, {}), null);
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
  var bootFocus = document.querySelector('.nav-item.focused');
  eq('boot focus starts on the first app tile', !!bootFocus && bootFocus.classList.contains('app-tile'), true);
  eq('state ambient', state.ambient, 'on');
  eq('state secs', state.ambientSecs, '90');
  eq('state motion', state.ambientMotion, 'drift');
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
  ['settingsModal', 'settingsCats', 'settingsMain', 'settingsHints', 'settingsSaved'].forEach(function (id) {
    if (!document.getElementById(id)) out.ambient.push('missing #' + id);
  });
  ['cfgCity', 'cfgTheme', 'cfgUnsplashKey', 'saveModalBtn', 'resetDefaultBtn', 'closeModalBtn'].forEach(function (id) {
    if (document.getElementById(id)) out.ambient.push('old control still present: #' + id);
  });
  eq('state keep awake', state.keepAwake, 'on');
  if (!document.getElementById('keepAwakeVideo')) out.ambient.push('missing #keepAwakeVideo');
  if (!Object.prototype.hasOwnProperty.call(I18N.pt, 'Keep LG screensaver away')) out.ambient.push('no translation: Keep LG screensaver away');
  eq('state home photos', state.homePhotos, 'off');
  if (!document.getElementById('homePhotos')) out.ambient.push('missing #homePhotos');
  if (!Object.prototype.hasOwnProperty.call(I18N.pt, 'Photos on Home')) out.ambient.push('no translation: Photos on Home');
  if (typeof SETTINGS !== 'object' || !SETTINGS.length) {
    out.ambient.push('SETTINGS missing');
  } else {
    SETTINGS.forEach(function (d) {
      if (d.field && d.id !== 'lang' && state[d.field] !== d.def) out.ambient.push('default mismatch: ' + d.id + ' state=' + JSON.stringify(state[d.field]) + ' def=' + JSON.stringify(d.def));
      if (d.type === 'choice' && !d.options) out.ambient.push('no options: ' + d.id);
    });
  }
  ['Starts after', '1 minute', '3 minutes', '5 minutes', '10 minutes', '30 minutes',
   'Photo screensaver', 'Off', 'Photo length', '30 seconds', '90 seconds', 'Motion',
   'Ken Burns (zoom & drift)', 'Drift only', 'None', 'Photos from',
   'Optional for photo screensaver', 'Photo by %s on Unsplash',
   'Home', 'Look', 'Screensaver', 'You and this TV', 'People', 'HDMI names', 'Close', 'More options',
   'Apps on Home', '%s apps', '1 app', 'Not set', 'Saved', 'Reset settings', 'Puts every setting and the shelf back to defaults. People and history stay.',
   'Erase everything on this TV', 'Deletes every person, setting, key and history, then starts first-run setup',
   'Press OK again to erase everything', 'Selected', 'Press OK again to confirm', 'LG TV settings', 'Unsplash, connected',
   'OK switch', 'OK edit', 'OK open', 'OK confirm', 'Left / Right change', 'Back close', 'Back groups', 'Back return', 'Back cancel',
   'Up / Down: move one row', 'OK: add or remove', 'Back: return', 'Enter: save', 'Back: cancel', '%s of 8 selected',
   'Keep at least one app on the shelf.', 'Keep at least one grown-up profile',
   'Dimmed, slowly moving photos behind the dashboard', 'Photos and the clock when the TV is idle',
   'The apps you opened last, first in the row', 'Movie night, Game on, Music', 'Off uses your city. On sends your IP to ipapi.co.',
   'Plays a hidden video so LG does not cover ours', 'Your Unsplash key, kept on this TV only',
   'Optional, for weekly trending movies and shows'].forEach(function (k) {
    if (!Object.prototype.hasOwnProperty.call(I18N.pt, k)) out.ambient.push('no translation: ' + k);
  });
  var pre = document.createElement('pre');
  pre.id = '__result';
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}, 1500);
"""

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
    state.nightDim = 'off'; // the clock must not change exact opacity assertions
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
    reset(); var calls = [], old = [], i;
    for (i = 0; i < 30; i++) old.push({ id: 'o' + i, raw: 'assets/icon.png', color: '#000000', name: 'Ann', dl: 'https://api.unsplash.com/photos/o' + i + '/download' });
    localStorage.setItem('fmtv_ambient_cache', JSON.stringify({ photos: old, at: Date.now() - 13 * 3600000 }));
    window.fetch = fakeFetch(403, null, calls);
    ambientRefresh(true);
    setTimeout(function () {
      var kept = JSON.parse(localStorage.getItem('fmtv_ambient_cache') || 'null');
      eq('403 calls', calls.length, 1);
      eq('403 cache', cacheSize(), 30);
      eq('403 cache same', !!kept && kept.photos[0].id === 'o0' && kept.photos[29].id === 'o29', true);
      eq('403 paused', parseInt(localStorage.getItem('fmtv_ambient_pause'), 10) > Date.now(), true);
      ambientRefresh(true);
      setTimeout(function () { eq('403 stays paused', calls.length, 1); done(); }, 200);
    }, 300);
  });
  steps.push(function (done) { // storage that throws must not wedge later refreshes
    reset(); var calls = [], origSet = Storage.prototype.setItem;
    window.fetch = fakeFetch(200, '49', calls);
    Storage.prototype.setItem = function (k, v) {
      if (k === 'fmtv_ambient_calls') throw new Error('quota');
      return origSet.call(this, k, v);
    };
    try { ambientRefresh(true); } catch (e) { fails.push('storage throw escaped: ' + e.message); }
    setTimeout(function () {
      Storage.prototype.setItem = origSet;
      eq('storage-throw calls', calls.length, 0);
      try { ambientRefresh(true); } catch (e2) { fails.push('second refresh threw: ' + e2.message); }
      setTimeout(function () { eq('storage-throw recovery', calls.length > 0, true); done(); }, 300);
    }, 200);
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
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'drift'; state.perfMode = 'standard';
    var calls = []; window.fetch = fakeFetch(200, '49', calls);
    enterScreensaver();
    setTimeout(function () {
      var a = document.getElementById('ssPhotoA').style.opacity, b = document.getElementById('ssPhotoB').style.opacity;
      eq('ambient class', isAmbient(), true);
      eq('credit', document.getElementById('screensaverCredit').textContent, t('Photo by %s on Unsplash', 'Ann'));
      eq('photo visible', a === '0.85' || b === '0.85', true);
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
  steps.push(function (done) { // motion None leaves the photo still; performance mode does not
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none'; state.perfMode = 'standard';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var img = document.getElementById('ssPhotoB');
      eq('none transform', img.style.transform, 'translate(0%, 0%) scale(1.06)');
      exitScreensaver();
      state.ambientMotion = 'drift'; state.perfMode = 'high';
      enterScreensaver();
      setTimeout(function () {
        var other = document.getElementById('ssPhotoB');
        eq('perf keeps motion', /scale\(1\.2\)/.test(other.style.transform), true);
        exitScreensaver();
        state.perfMode = 'standard';
        done();
      }, 400);
    }, 400);
  });
  steps.push(function (done) { // Trending This Week can be hidden: the row disappears, leaves the focus list and stops fetching
    var sec = document.querySelector('.picks-section'), fetched = 0, realFetch = window.fetch;
    window.fetch = function () { fetched++; return realFetch.apply(window, arguments); };
    eq('trending default on', state.showTrending, 'on');
    state.showTrending = 'off'; applyTrendingClass(); refreshMainNavList();
    eq('trending hidden class', sec.classList.contains('picks-off'), true);
    eq('trending hidden', sec.offsetParent === null, true);
    eq('trending out of nav', mainNavItems.indexOf(document.getElementById('tabMovies')), -1);
    fetchTrendingPicks();
    eq('trending off no fetch', fetched, 0);
    state.showTrending = 'on'; applyTrendingClass(); refreshMainNavList();
    eq('trending shown', sec.offsetParent !== null, true);
    eq('trending in nav', mainNavItems.indexOf(document.getElementById('tabMovies')) !== -1, true);
    window.fetch = realFetch;
    done();
  });
  steps.push(function (done) { // Back (461): steps out of Customize one level at a time, and leaves the app from the home screen
    var oldWebOS = window.webOS, left = 0;
    function back() { document.dispatchEvent(new KeyboardEvent('keydown', { keyCode: 461, key: 'GoBack', bubbles: true, cancelable: true })); }
    window.webOS = { platformBack: function () { left++; } };
    openSettingsModal();
    settingsUi.zone = 'rows';
    back();
    eq('back rows to cats', settingsUi.zone, 'cats');
    eq('back keeps modal', modalOpen, true);
    back();
    eq('back cats closes', modalOpen, false);
    eq('back no leave in modal', left, 0);
    back();
    eq('back home leaves app', left, 1);
    window.webOS = oldWebOS;
    done();
  });
  steps.push(function (done) { // openLgTvSettings launches the LG Settings app (the button left the top bar; Settings reuses the function)
    var got = null, oldWebOS = window.webOS;
    eq('tv settings function', typeof openLgTvSettings, 'function');
    window.webOS = { service: { request: function (uri, o) { got = { uri: uri, o: o }; } } };
    openLgTvSettings();
    eq('tv settings uri', got && got.uri, 'luna://com.webos.applicationManager');
    eq('tv settings id', got && got.o.parameters.id, 'com.palm.app.settings');
    if (got) got.o.onSuccess({ returnValue: true });
    window.webOS = oldWebOS;
    done();
  });
  steps.push(function (done) { // Photo Brightness scales the opacity (capped at 1); Clock Position sets the overlay class
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none';
    eq('bright soft', (state.ambientBright = 'soft', ambientBrightness()), 0.75);
    eq('bright normal', (state.ambientBright = 'normal', ambientBrightness()), 1);
    eq('bright bright', (state.ambientBright = 'bright', ambientBrightness()), 1.25);
    state.ambientBright = 'soft';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var a = document.getElementById('ssPhotoA').style.opacity, b = document.getElementById('ssPhotoB').style.opacity;
      eq('soft opacity', a === '0.64' || b === '0.64', true);
      exitScreensaver();
      state.ambientBright = 'normal';
      var ov = document.getElementById('screensaverOverlay');
      state.clockPos = 'tr'; applyClockPosition();
      eq('pos tr', ov.classList.contains('pos-tr') && !ov.classList.contains('pos-bl'), true);
      state.clockPos = 'br'; applyClockPosition();
      eq('pos br', ov.classList.contains('pos-br') && !ov.classList.contains('pos-tr'), true);
      state.clockPos = 'center'; applyClockPosition();
      eq('pos center', /pos-/.test(ov.className), false);
      state.clockPos = 'bl'; applyClockPosition();
      var m = /translate\((-?\d+)px, (-?\d+)px\)/.exec(document.getElementById('screensaverClockWrap').style.transform);
      eq('corner shift small', !!m && Math.abs(+m[1]) <= 6 && Math.abs(+m[2]) <= 6, true);
      eq('pos bl', ov.classList.contains('pos-bl'), true);
      done();
    }, 400);
  });
  steps.push(function (done) { // Ken Burns makes one zoom-and-pan per photo and starts no drift legs
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'kenburns';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var shown = document.getElementById('ssPhotoA').style.opacity === '0.85' ? document.getElementById('ssPhotoA') : document.getElementById('ssPhotoB');
      eq('kenburns end scale', /scale\(1\.22\)/.test(shown.style.transform), true);
      eq('kenburns one move', /transform 94s/.test(shown.style.transition), true);
      eq('kenburns no leg timer', !!shown._moveTimer, false);
      exitScreensaver();
      state.ambientMotion = 'drift';
      done();
    }, 400);
  });
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
  steps.push(function (done) { // Sliding panels: six strips slide away to reveal the next photo, then are removed
    seedMany([photo('p1', 'Ann'), photo('p2', 'Bob')]);
    state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'panels'; state.ambientBright = 'normal';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var box = document.getElementById('screensaverPhotos');
      eq('panels none first', box.querySelectorAll('.pn-strips').length, 0);
      eq('panels still transform', document.getElementById('ssPhotoA').style.transform === 'none' || document.getElementById('ssPhotoB').style.transform === 'none', true);
      ambientShow();
      setTimeout(function () {
        eq('panels strips', box.querySelectorAll('.pn-strip').length, 6);
        eq('panels strips sliding', box.querySelector('.pn-strip').style.transform, 'translateY(-101%)');
        setTimeout(function () {
          eq('panels strips removed', box.querySelectorAll('.pn-strips').length, 0);
          var a = document.getElementById('ssPhotoA').style.opacity, b = document.getElementById('ssPhotoB').style.opacity;
          eq('panels next shown', (a === '0.85') !== (b === '0.85'), true);
          exitScreensaver();
          eq('panels cleaned on stop', box.querySelectorAll('.pn-strips').length, 0);
          state.ambientMotion = 'drift';
          done();
        }, 3500);
      }, 300);
    }, 500);
  });
  steps.push(function (done) { // Continuous drift zooms and keeps gliding in legs within 8%
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'drift';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      var shown = document.getElementById('ssPhotoA').style.opacity === '0.85' ? document.getElementById('ssPhotoA') : document.getElementById('ssPhotoB');
      var m = /translate\((-?[\d.]+)%, (-?[\d.]+)%\) scale\(([\d.]+)\)/.exec(shown.style.transform);
      eq('kb parsed', !!m, true);
      if (m) {
        eq('kb dx', Math.abs(parseFloat(m[1])) <= 8, true);
        eq('kb dy', Math.abs(parseFloat(m[2])) <= 8, true);
        eq('kb scale', m[3], '1.2');
        eq('kb leg timer', !!shown._moveTimer, true);
      }
      exitScreensaver();
      done();
    }, 400);
  });

  var pingPhoto = { id: 'q1', raw: 'assets/icon.png', color: '#000000', name: 'Ann', dl: 'https://api.unsplash.com/photos/q1/download' };
  steps.push(function (done) { // ping budget blocked: no fetch, id not recorded
    reset(); state.unsplashKey = 'k'; var calls = [], log = [], n;
    for (n = 0; n < 30; n++) log.push(Date.now() - 1000);
    localStorage.setItem('fmtv_ambient_calls', JSON.stringify(log));
    window.fetch = fakeFetch(200, '49', calls);
    ambientPing(pingPhoto);
    setTimeout(function () {
      eq('ping blocked calls', calls.length, 0);
      eq('ping blocked unrecorded', (localStorage.getItem('fmtv_ambient_pinged') || '').indexOf('q1'), -1);
      done();
    }, 100);
  });
  steps.push(function (done) { // ping sent once and recorded once
    reset(); state.unsplashKey = 'k'; var calls = [];
    window.fetch = fakeFetch(200, '49', calls);
    ambientPing(pingPhoto); ambientPing(pingPhoto);
    setTimeout(function () {
      eq('ping once calls', calls.length, 1);
      eq('ping once url', calls[0] && calls[0].url, pingPhoto.dl);
      eq('ping once recorded', JSON.parse(localStorage.getItem('fmtv_ambient_pinged')).join(','), 'q1');
      done();
    }, 100);
  });
  steps.push(function (done) { // JSON null in the call log does not wedge a refresh
    reset(); state.ambient = 'on'; state.unsplashKey = 'k'; var calls = [];
    localStorage.setItem('fmtv_ambient_calls', 'null');
    window.fetch = fakeFetch(200, '49', calls);
    ambientRefresh(true);
    setTimeout(function () {
      eq('null log calls', calls.length, 5);
      eq('null log refreshing', ambientRefreshing, false);
      done();
    }, 400);
  });
  steps.push(function (done) { // empty credit takes no space
    reset(); exitScreensaver();
    eq('credit hidden', getComputedStyle(document.getElementById('screensaverCredit')).display, 'none');
    done();
  });
  steps.push(function (done) { // key is only sent to api.unsplash.com
    reset(); state.unsplashKey = 'k'; var calls = [], got = null;
    window.fetch = fakeFetch(200, '49', calls);
    ambientApi('https://evil.test/x', 40, function (err) { got = err; });
    setTimeout(function () {
      eq('evil calls', calls.length, 0);
      eq('evil error', !!got, true);
      eq('evil unlogged', localStorage.getItem('fmtv_ambient_calls'), null);
      done();
    }, 100);
  });
  steps.push(function (done) { // ambientReady needs fetch
    seedCache(); state.ambient = 'on'; state.unsplashKey = 'k';
    var saved = window.fetch;
    window.fetch = undefined;
    eq('ready no fetch', ambientReady(), false);
    window.fetch = saved || fakeFetch(200, '49', []);
    eq('ready with fetch', ambientReady(), true);
    done();
  });

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
      eq('swap first B', b.style.opacity, '0.85');
      eq('swap first A hidden', a.style.opacity === '' || a.style.opacity === '0', true);
      ambientShow();
      setTimeout(function () {
        eq('swap second A', a.style.opacity, '0.85');
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
      state.ambientMotion = 'drift';
      done();
    }, 600);
  });

  var home = document.getElementById('homePhotos');
  function homeActive() { return !!home && /\bactive\b/.test(home.className); }
  function homeCredit() { return document.getElementById('homePhotoCredit').textContent; }
  function homeOpacities() {
    return [document.getElementById('hpPhotoA').style.opacity, document.getElementById('hpPhotoB').style.opacity];
  }
  if (typeof syncHomePhotos !== 'function') { fails.push('syncHomePhotos missing'); write(); return; }

  steps.push(function (done) { // home photos show dimmed (0.47 for a dark photo), with credit and one ping; Off hides them
    seedMany([photo('h1', 'Ann')]);
    state.ambient = 'off'; state.homePhotos = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none'; state.perfMode = 'standard';
    var calls = []; window.fetch = fakeFetch(200, '49', calls);
    syncHomePhotos();
    setTimeout(function () {
      eq('home active', homeActive(), true);
      eq('home credit', homeCredit(), t('Photo by %s on Unsplash', 'Ann'));
      eq('home dim', homeOpacities().indexOf('0.47') !== -1, true);
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

  var awakeVideo = document.getElementById('keepAwakeVideo'), awakeCanvas = document.getElementById('keepAwakeCanvas');
  if (typeof keepAwakeStart !== 'function') { fails.push('keepAwakeStart missing'); write(); return; }

  steps.push(function (done) { // On: the hidden video plays whenever the app is in front, and our screensaver ending does not stop it
    seedMany([photo('k1', 'Ann')]);
    state.ambient = 'on'; state.unsplashKey = 'k'; state.keepAwake = 'on'; state.homePhotos = 'off';
    window.fetch = fakeFetch(200, '49', []);
    keepAwakeStop();
    eq('awake stopped first', keepAwakeTimer, null);
    keepAwakeSync();
    setTimeout(function () {
      eq('awake playing', !!awakeVideo.srcObject, true);
      eq('awake timer', keepAwakeTimer !== null, true);
      enterScreensaver();
      exitScreensaver();
      eq('awake survives screensaver exit', keepAwakeTimer !== null, true);
      keepAwakeStop();
      eq('awake stopped', awakeVideo.srcObject === null || awakeVideo.srcObject === undefined, true);
      eq('awake timer cleared', keepAwakeTimer, null);
      done();
    }, 300);
  });
  steps.push(function (done) { // Off: nothing plays; the black-clock screensaver is unaffected
    reset(); state.keepAwake = 'off';
    keepAwakeSync();
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
    keepAwakeStop();
    awakeCanvas.captureStream = undefined; // shadows the prototype method on this element
    var threw = false;
    try { keepAwakeSync(); enterScreensaver(); } catch (e) { threw = true; }
    setTimeout(function () {
      eq('awake no captureStream threw', threw, false);
      eq('awake no captureStream video', !!awakeVideo.srcObject, false);
      eq('awake no captureStream timer', keepAwakeTimer, null);
      exitScreensaver();
      delete awakeCanvas.captureStream;
      keepAwakeSync();
      done();
    }, 200);
  });

  steps.push(function (done) { // a changed Photo Duration restarts the running home player
    seedMany([photo('d1', 'Ann')]);
    state.ambient = 'off'; state.homePhotos = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none';
    window.fetch = fakeFetch(200, '49', []);
    syncHomePhotos();
    setTimeout(function () {
      eq('duration active', homeActive(), true);
      var before = homePhotoPlayer.run;
      state.ambientSecs = '30';
      if (typeof applyHomePhotosSettings !== 'function') { fails.push('applyHomePhotosSettings missing'); }
      else { applyHomePhotosSettings(); }
      eq('duration restarted', homePhotoPlayer.run > before, true);
      eq('duration still active', homeActive(), true);
      state.ambientSecs = '90'; state.homePhotos = 'off';
      syncHomePhotos();
      done();
    }, 400);
  });

  var hiddenFlag = false;
  Object.defineProperty(document, 'hidden', { configurable: true, get: function () { return hiddenFlag; } });
  function setHidden(v) { hiddenFlag = v; document.dispatchEvent(new Event('visibilitychange')); }
  steps.push(function (done) { // home photos stop while the app is in the background and resume on return
    seedMany([photo('v1', 'Ann')]);
    state.ambient = 'off'; state.homePhotos = 'on'; state.unsplashKey = 'k'; state.ambientMotion = 'none';
    window.fetch = fakeFetch(200, '49', []);
    syncHomePhotos();
    setTimeout(function () {
      eq('vis home active', homeActive(), true);
      setHidden(true);
      eq('vis home hidden', homeActive(), false);
      eq('vis wanted hidden', homePhotosWanted(), false);
      setHidden(false);
      eq('vis home visible again', homeActive(), true);
      state.homePhotos = 'off'; syncHomePhotos();
      done();
    }, 400);
  });
  steps.push(function (done) { // the screensaver and keep-awake end when the app goes to the background
    seedMany([photo('v2', 'Ann')]);
    state.ambient = 'on'; state.unsplashKey = 'k'; state.keepAwake = 'on'; state.homePhotos = 'off';
    window.fetch = fakeFetch(200, '49', []);
    enterScreensaver();
    setTimeout(function () {
      eq('vis saver on', isAmbient(), true);
      setHidden(true);
      eq('vis saver flag', screensaverOn, false);
      eq('vis saver ambient', isAmbient(), false);
      eq('vis keepAwake timer', keepAwakeTimer, null);
      setHidden(false);
      eq('vis keepAwake back', keepAwakeTimer !== null, true);
      delete document.hidden;
      state.homePhotos = 'off'; syncHomePhotos();
      done();
    }, 400);
  });

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
    var extraKeys = ['fmtv_ambient_cache', 'fmtv_ambient_pause'];
    var extra = {};
    extraKeys.forEach(function (k) { extra[k] = localStorage.getItem(k); });
    function flushNet() { if (typeof flushSettingsNetwork === 'function') flushSettingsNetwork(); }
    function count(n) { return seen.filter(function (s) { return s === n; }).length; }
    eq('engine has flushSettingsNetwork', typeof flushSettingsNetwork, 'function');
    function called(label, id, value, expected) {
      seen.length = 0;
      setSettingValue(findSetting(id), value);
      flushNet();
      expected.forEach(function (n) { eq('engine ' + label + ' calls ' + n, seen.indexOf(n) !== -1, true); });
    }
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
      flushNet();
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
      eq('engine has hdmi rows', hd.length > 0, true);
      seen.length = 0;
      setSettingValue(hd[0], 'ps5');
      eq('engine hdmi state', state.hdmiDevices[hd[0].hdmi.id], 'ps5');
      eq('engine hdmi stored', JSON.parse(localStorage.getItem('fmtv_hdmi_devices'))[hd[0].hdmi.id], 'ps5');
      eq('engine hdmi value', settingValue(hd[0]), 'ps5');
      eq('engine hdmi shelf', seen.indexOf('renderAppsShelf') !== -1, true);
      var cat0 = settingsForCategory(0);
      eq('engine cat0 first is shelf', cat0[0] && cat0[0].id, 'shelf');
      eq('engine cat0 hdmi follow', cat0.length, 5 + hd.length);

      state.favorites = ['a'];
      eq('engine fav last', toggleFavorite('a'), 'last');
      eq('engine fav add', toggleFavorite('b'), 'added');
      eq('engine fav stored', localStorage.getItem('fmtv_favorites'), JSON.stringify(['a', 'b']));
      eq('engine fav remove', toggleFavorite('b'), 'removed');
      state.favorites = ['1', '2', '3', '4', '5', '6', '7', '8'];
      eq('engine fav full', toggleFavorite('x'), 'full');
      eq('engine fav full unchanged', state.favorites.length, 8);

      called('lang', 'lang', 'en', ['applyStaticTranslations', 'renderAppsShelf', 'updateClock', 'applyTheme', 'fetchWeather', 'fetchTrendingPicks']);
      called('perfMode', 'perfMode', 'high', ['applyPerfMode', 'applyHomePhotosSettings', 'applyTheme']);
      called('ipLocate', 'ipLocate', 'on', ['fetchWeather']);
      called('tmdbKey', 'tmdbKey', 'tmdb-test', ['fetchTrendingPicks']);

      seen.length = 0;
      for (var r = 0; r < 5; r++) cycleSetting(findSetting('lang'), 1);
      eq('engine rapid lang: no weather before flush', count('fetchWeather'), 0);
      eq('engine rapid lang: no picks before flush', count('fetchTrendingPicks'), 0);
      flushNet();
      eq('engine rapid lang: weather once', count('fetchWeather'), 1);
      eq('engine rapid lang: picks once', count('fetchTrendingPicks'), 1);
      flushNet();
      eq('engine flush twice runs nothing more', count('fetchWeather') + count('fetchTrendingPicks'), 2);
      seen.length = 0;
      setSettingValue(findSetting('city'), 'Debounce');
      eq('engine city weather waits', count('fetchWeather'), 0);
      flushNet();
      eq('engine city weather after flush', count('fetchWeather'), 1);
      eq('engine city fetches no picks', count('fetchTrendingPicks'), 0);
      seen.length = 0;
      cycleSetting(findSetting('lang'), 1); // debounce pending
      resetAllSettings();
      flushNet();
      eq('engine reset drops pending weather', count('fetchWeather'), 1);
      eq('engine reset drops pending picks', count('fetchTrendingPicks'), 1);
      called('textSize', 'textSize', 'large', ['applyTextSize']);
      called('clockFormat', 'clockFormat', '12h', ['updateClock']);
      called('homePhotos', 'homePhotos', 'on', ['ambientRefresh', 'applyHomePhotosSettings']);
      setSettingValue(findSetting('city'), '  Rome  ');
      eq('engine text trimmed', state.city, 'Rome');

      seen.length = 0;
      setSettingValue(findSetting('theme'), 'day');
      seen.length = 0;
      resetAllSettings();
      eq('engine reset theme', state.theme, 'auto');
      eq('engine reset city', state.city, '');
      eq('engine reset favorites', JSON.stringify(state.favorites), JSON.stringify(DEFAULT_FAVORITES));
      eq('engine reset hdmi', JSON.stringify(state.hdmiDevices), '{}');
      ['applyStaticTranslations', 'applyPerfMode', 'applyTextSize', 'renderAppsShelf', 'applyTheme', 'updateClock', 'fetchWeather',
        'fetchTrendingPicks', 'ambientRefresh', 'applyHomePhotosSettings'].forEach(function (n) {
        eq('engine reset calls ' + n, seen.indexOf(n) !== -1, true);
      });
    } catch (e) {
      fails.push('engine threw: ' + e);
    } finally {
      flushNet(); // nothing pending may fire after the spies are gone
      names.forEach(function (n) { window[n] = real[n]; });
      Object.keys(saved).forEach(function (f) { state[f] = saved[f]; });
      Object.keys(savedStore).forEach(function (k) {
        if (savedStore[k] === null) localStorage.removeItem(k); else localStorage.setItem(k, savedStore[k]);
      });
      localStorage.setItem('fmtv_favorites', JSON.stringify(state.favorites));
      localStorage.setItem('fmtv_hdmi_devices', JSON.stringify(state.hdmiDevices));
      extraKeys.forEach(function (k) {
        if (extra[k] === null) localStorage.removeItem(k); else localStorage.setItem(k, extra[k]);
      });
    }
    done();
  });

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
    var rows = settingsRowsFor(settingsUi.cat);
    for (var i = 0; i < rows.length; i++) if (rows[i].id === id) return i;
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
    eq('first category focused', focusedText().indexOf(t('Home')) !== -1, true);
    press('ArrowDown'); press('ArrowDown');
    eq('down x2 selects group 2', settingsUi.cat, 2);
    eq('rows show that group', !!modalEl().querySelector('.settings-row[data-id="idleMins"]'), true);
    press('ArrowDown');
    eq('down reaches the last group', settingsUi.catFocus, 3);
    press('ArrowDown');
    eq('no wrap past the last group', settingsUi.catFocus, 3);
    for (var u = 0; u < 9; u++) press('ArrowUp');
    eq('no wrap above first', settingsUi.catFocus, 0);
    eq('fr key hint feminine', I18N.fr['Your Unsplash key, kept on this TV only'].indexOf('uniquement sur ce téléviseur') !== -1, true);
    eq('es keep one says estante', I18N.es['Keep at least one app on the shelf.'].indexOf('estante') !== -1 && I18N.es['Keep at least one app on the shelf.'].indexOf('estantería') === -1, true);
    eq('de not set', I18N.de['Not set'], 'Nicht festgelegt');
    eq('de confirm', I18N.de['Press OK again to confirm'], 'Zum Bestätigen erneut OK drücken');
    press('ArrowLeft');
    eq('left in categories is a no-op', settingsUi.zone + ':' + settingsUi.catFocus, 'cats:0');
    eq('cats hints', document.getElementById('settingsHints').textContent, t('OK open') + ' · ' + t('Back close'));
    var catNode = modalEl().querySelectorAll('.settings-cat')[1];
    press('ArrowDown');
    eq('category keys do not rebuild the category list', modalEl().querySelectorAll('.settings-cat')[1] === catNode, true);
    eq('category keys still show that category', settingsUi.cat === 1 && modalEl().querySelector('#settingsRows').getAttribute('data-cat') === '1', true);
    press('ArrowUp');
    done();
  });
  steps.push(function (done) { // entering a category, choice rows change with Left and Right and save at once
    settingsUi.cat = 2; settingsUi.catFocus = 2; renderSettings();
    press('ArrowRight');
    eq('zone rows', settingsUi.zone, 'rows');
    eq('lands on first setting', settingsUi.row, 0);
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
    eq('rows hints', document.getElementById('settingsHints').textContent, t('Left / Right change') + ' · ' + t('Back groups'));
    modalEl().querySelector('.settings-row[data-id="idleMins"] .sr-value').click();
    eq('clicking the value acts like OK', state.idleMins, '5');
    modalEl().querySelector('.settings-row[data-id="idleMins"] .sr-chevron').click();
    eq('clicking the chevron acts like OK', state.idleMins, '10');
    setSettingValue(findSetting('idleMins'), '3');
    done();
  });
  steps.push(function (done) { // back chain: rows -> categories -> closes
    press('Escape');
    eq('back from rows', settingsUi.zone, 'cats');
    press('Escape');
    eq('back from cats closes', modalOpen, false);
    openSettingsModal();
    settingsUi.cat = 2; settingsUi.catFocus = 2; renderSettings(); press('Enter');
    goToRow('moreOptions'); // then up past the first row
    var guard = 20; while (settingsUi.row > 0 && guard--) press('ArrowUp');
    eq('first row reached', settingsUi.row, 0);
    press('ArrowUp');
    eq('Up from the first row returns to the category list', settingsUi.zone + ':' + settingsUi.catFocus, 'cats:2');
    press('Escape');
    eq('Back from the group list closes', modalOpen, false);
    done();
  });
  steps.push(function (done) { // text rows: inline editor, commit, cancel; secrets are masked everywhere
    openSettingsModal();
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings(); press('Enter');
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
    press('Enter');
    eq('letter key not prevented while editing', press('a').defaultPrevented, false);
    var blurInput = document.getElementById('settingsEditInput'), commits = 0, realSet = window.setSettingValue;
    window.setSettingValue = function (d, v) { commits++; return realSet(d, v); };
    blurInput.value = 'Tiberias';
    blurInput.dispatchEvent(new Event('blur'));
    blurInput.blur();
    window.setSettingValue = realSet;
    eq('blur commits', state.city, 'Tiberias');
    eq('blur commits once', commits, 1);
    eq('blur returns to rows', settingsUi.zone, 'rows');

    settingsUi.cat = 2; settingsUi.catFocus = 2; settingsUi.zone = 'cats'; renderSettings(); press('Enter');
    goToRow('unsplashKey');
    press('Enter');
    var secret = document.getElementById('settingsEditInput');
    eq('secret editor is password', secret && secret.type, 'password');
    secret.value = 'SECRET-KEY-12345';
    press('Enter');
    eq('secret committed', state.unsplashKey, 'SECRET-KEY-12345');
    eq('secret never shown in rows', modalEl().textContent.indexOf('SECRET-KEY-12345'), -1);
    eq('secret shows only that it is connected', modalEl().querySelector('.settings-row[data-id="unsplashKey"] .sr-value').textContent, t('Unsplash, connected'));
    state.tmdbKey = 'TMDB-SECRET-1'; eq('other secrets show dots', settingValueText(findSetting('tmdbKey')), '••••••••'); state.tmdbKey = '';
    state.unsplashKey = ''; localStorage.removeItem('fmtv_unsplash_key'); state.city = ''; localStorage.removeItem('fmtv_city');
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // background renders (shelf, picks) do not steal focus from an open editor
    var keepCity = state.city;
    openSettingsModal();
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings(); press('Enter');
    goToRow('city');
    press('Enter');
    var input = document.getElementById('settingsEditInput');
    eq('city editor open', !!input && settingsUi.zone === 'edit', true);
    input.value = 'Half-typ';
    renderAppsShelf();
    renderPicks(FALLBACK_MOVIES);
    eq('editor survives background renders', settingsUi.zone, 'edit');
    eq('editor keeps DOM focus', document.activeElement && document.activeElement.id, 'settingsEditInput');
    eq('half-typed text not committed', state.city, keepCity);
    press('Escape');
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // long lists scroll to keep the focused row in view (the Screensaver More page has 6 rows with hints)
    openSettingsModal();
    settingsUi.cat = 2; settingsUi.catFocus = 2; renderSettings(); press('Enter');
    goToRow('moreOptions'); press('Enter');
    var rows = document.getElementById('settingsRows'), last = settingsRowsFor(2).length, guard = 60;
    while (settingsUi.row < last - 1 && guard--) press('ArrowDown');
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
  steps.push(function (done) { // a long apps grid keeps the focused tile fully visible going down and back up; partial last rows and empty catalogs
    var keepCat = state.catalog, keepFav = state.favorites.slice(), big = state.catalog.slice(), k;
    big.unshift({ id: 'test.longtitle', title: 'Amazon Prime Video Live TV Channel Network' });
    for (k = 0; big.length < 60; k++) big.push({ id: 'test.dummy' + k, title: 'Dummy ' + k });
    state.catalog = big;
    eq('no settings apps grid while the page is closed', document.querySelectorAll('#settingsAppsGrid').length, 0);
    eq('home shelf grid id stays single', document.querySelectorAll('#appsGrid').length, 1);
    openSettingsModal();
    press('Enter'); press('Enter'); // category 0, then "Shelf apps"
    var grid = document.getElementById('settingsAppsGrid'), guard = 80, okDown = true, okUp = true, node;
    eq('home shelf grid id is unique', document.querySelectorAll('#appsGrid').length, 1);
    eq('settings apps grid id is unique', document.querySelectorAll('#settingsAppsGrid').length, 1);
    eq('apps grid overflows', !!grid && grid.scrollHeight > grid.clientHeight, true);
    eq('long title does not widen the grid', !!grid && grid.scrollWidth <= grid.clientWidth, true);
    var firstRow = Array.prototype.slice.call(grid.querySelectorAll('.apps-tile'), 0, 5).map(function (n) { return n.getBoundingClientRect().width; });
    eq('first row tiles equal width', firstRow.length === 5 && firstRow.every(function (w) { return Math.abs(w - firstRow[0]) < 2; }), true);
    function check() { node = grid.querySelector('.apps-tile.sf'); return !!node && inView(node, grid); }
    while (settingsUi.appIdx < big.length - 5 && guard--) { press('ArrowDown'); if (!check()) okDown = false; }
    while (settingsUi.appIdx < big.length - 1 && guard--) { press('ArrowRight'); if (!check()) okDown = false; }
    eq('reached the last tile', settingsUi.appIdx, big.length - 1);
    eq('focused tile visible going down', okDown, true);
    while (settingsUi.appIdx >= 5 && guard--) { press('ArrowUp'); if (!check()) okUp = false; }
    while (settingsUi.appIdx > 0 && guard--) { press('ArrowLeft'); if (!check()) okUp = false; }
    eq('back at tile 0', settingsUi.appIdx, 0);
    eq('focused tile visible coming back up', okUp, true);

    var twelve = [];
    for (k = 0; k < 12; k++) twelve.push({ id: 'test.twelve' + k, title: 'App ' + k });
    state.catalog = twelve; state.favorites = [twelve[0].id];
    renderSettings();
    settingsUi.appIdx = 7; paintFocus(); press('ArrowDown');
    eq('down from 7 reaches the partial last row', settingsUi.appIdx, 11);
    press('ArrowDown');
    eq('then Done', settingsUi.appIdx, 12);

    state.catalog = [];
    renderSettings();
    settingsUi.appIdx = 0; paintFocus();
    press('ArrowUp');
    eq('up on an empty catalog stays valid', settingsUi.appIdx, 0);
    press('ArrowLeft');
    eq('left on an empty catalog stays valid', settingsUi.appIdx, 0);

    state.catalog = keepCat; state.favorites = keepFav;
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // apps found while the apps page is open keep Done focused and appear at once
    var keepCat = state.catalog.slice();
    openSettingsModal();
    press('Enter'); press('Enter'); // category 0, then "Shelf apps"
    var oldLen = state.catalog.length;
    settingsUi.appIdx = oldLen; paintFocus();
    eq('focus on Done before growth', modalEl().querySelector('.sf') === document.getElementById('appsDone'), true);
    addLaunchPoints([{ appId: 'test.grow.one', title: 'Grow One' }, { appId: 'test.grow.two', title: 'Grow Two' }]);
    eq('catalog grew', state.catalog.length, oldLen + 2);
    eq('Done index follows the growth', settingsUi.appIdx, state.catalog.length);
    eq('new tiles shown', !!modalEl().querySelector('.apps-tile[data-i="' + oldLen + '"]'), true);
    paintFocus();
    eq('one focus mark after growth', sfCount(), 1);
    eq('Done still focused after growth', modalEl().querySelector('.sf') === document.getElementById('appsDone'), true);
    state.catalog = keepCat;
    closeSettingsModal();
    renderAppsShelf();
    done();
  });
  steps.push(function (done) { // full-screen settings page: shell, switches, value rows, More options, hint bar
    var MAX_FIVE_ROWS_ENABLED = true; // the four groups hold at most five rows each (More options counts as one; sub-pages are exempt)
    function pageOf(cat, sub) { settingsUi.cat = cat; settingsUi.catFocus = cat; settingsUi.zone = 'rows'; settingsUi.row = 0; settingsUi.sub = sub === true ? 'more' : (sub || ''); renderSettings(); }
    function px(n) { return Math.round(n) + 'px'; }
    openSettingsModal();
    var m = modalEl(), r = m.getBoundingClientRect(), cs = getComputedStyle(m);
    eq('settings root is full viewport', Math.round(r.width) + 'x' + Math.round(r.height) + '@' + Math.round(r.left) + ',' + Math.round(r.top), window.innerWidth + 'x' + window.innerHeight + '@0,0');
    eq('settings background', cs.backgroundColor, 'rgb(15, 17, 21)');
    eq('settings padding', cs.paddingTop + ' ' + cs.paddingRight + ' ' + cs.paddingBottom + ' ' + cs.paddingLeft, '84px 96px 60px 96px');
    eq('no close button', m.querySelectorAll('.settings-close').length, 0);
    eq('no Close text button', [].filter.call(m.querySelectorAll('button'), function (b) { return b.textContent === t('Close'); }).length, 0);
    eq('no header row', m.querySelectorAll('.settings-head').length, 0);
    var title = document.getElementById('settingsTitle');
    eq('title text', title.textContent, t('Settings'));
    eq('title size', getComputedStyle(title).fontSize, '54px');
    var cat0 = m.querySelector('.settings-cat');
    eq('group row height', px(cat0.getBoundingClientRect().height), '84px');
    eq('group row text', getComputedStyle(cat0).fontSize, '30px');
    eq('group list has no count chips', m.querySelectorAll('.sc-count').length, 0);
    eq('current group background', getComputedStyle(cat0).backgroundColor, 'rgba(255, 255, 255, 0.1)');
    eq('left column width', px(m.querySelector('.settings-left').getBoundingClientRect().width), '450px');
    var ver = document.getElementById('appVersion');
    eq('version line', ver.textContent, 'Free My TV ' + APP_VERSION);
    eq('version size', getComputedStyle(ver).fontSize, '21px');
    eq('version sits at the bottom of the left column', Math.abs(ver.getBoundingClientRect().bottom - (window.innerHeight - 60)) <= 2, true);

    // value rows: 114px minimum, 30px label, 22px hint
    pageOf(2, false);
    var idle = m.querySelector('.settings-row[data-id="idleMins"]');
    eq('row min height', getComputedStyle(idle).minHeight, '114px');
    eq('row label size', getComputedStyle(idle.querySelector('.sr-label')).fontSize, '30px');
    pageOf(1, false);
    var hinted = m.querySelector('.settings-row[data-id="homePhotos"] .sr-hint');
    eq('row hint size', hinted && getComputedStyle(hinted).fontSize, '22px');
    eq('choice row shows value and chevron', idle.querySelector('.sr-value').textContent + '|' + (idle.querySelector('.sr-chevron') || {}).textContent, t('3 minutes') + '|›');
    eq('choice row has no switch', idle.querySelectorAll('.sr-switch').length, 0);
    eq('no arrow buttons anywhere', m.querySelectorAll('.sr-arrow').length, 0);

    // every on/off setting is a switch, on every page
    var swCount = 0;
    for (var c = 0; c < 4; c++) {
      ['', 'more', 'people'].forEach(function (more) {
        pageOf(c, more);
        SETTINGS.forEach(function (d) {
          if (d.type !== 'choice' || !d.field || (settingGroup(d) !== c)) return;
          if (d.show && !d.show()) return;
          if ((d.page || (d.more ? 'more' : '')) !== more) return;
          var row = m.querySelector('.settings-row[data-id="' + d.id + '"]');
          var sw = row && row.querySelector('.sr-switch');
          var vals = d.options.map(function (o) { return o[0]; }).sort().join(',');
          if (vals === 'off,on') {
            swCount++;
            if (!sw) { fails.push('switch missing for ' + d.id); return; }
            var kn = sw.querySelector('.sr-knob'), sr = sw.getBoundingClientRect();
            var isOn = state[d.field] === 'on';
            var bg = getComputedStyle(sw).backgroundColor;
            if (Math.round(sr.width) !== 78 || Math.round(sr.height) !== 45 || !kn || Math.round(kn.getBoundingClientRect().width) !== 36) fails.push('switch size ' + d.id);
            if (bg !== (isOn ? 'rgb(60, 130, 246)' : 'rgb(58, 65, 78)')) fails.push('switch colour ' + d.id + ' ' + bg);
            if (row.querySelector('.sr-chevron') || row.querySelector('.sr-arrow')) fails.push('switch row has chevron/arrows ' + d.id);
          } else if (sw) { fails.push('non on/off row rendered as a switch: ' + d.id); }
        });
      });
    }
    eq('switch rows found (ambient, nightDim, keepAwake, ...)', swCount >= 6, true);
    eq('isSwitchSetting helper agrees', isSwitchSetting(findSetting('ambient')) + ':' + isSwitchSetting(findSetting('idleMins')) + ':' + isSwitchSetting(findSetting('homePhotos')), 'true:false:true');

    // OK and Left/Right both flip a switch; a click flips it too
    pageOf(2, false);
    state.ambient = 'on'; renderSettings(); goToRow('ambient');
    press('Enter');
    eq('OK flips the switch', state.ambient + ':' + localStorage.getItem('fmtv_ambient'), 'off:off');
    eq('switch repaints', m.querySelector('.settings-row[data-id="ambient"] .sr-switch').className.indexOf('on') !== -1, false);
    press('ArrowRight');
    eq('Right flips the switch back', state.ambient, 'on');
    press('ArrowLeft');
    eq('Left flips the switch', state.ambient, 'off');
    m.querySelector('.settings-row[data-id="ambient"]').click();
    eq('click flips the switch', state.ambient, 'on');

    // hint bar per row type
    eq('switch hint', document.getElementById('settingsHints').textContent, t('OK switch') + ' · ' + t('Back groups'));
    goToRow('idleMins');
    eq('choice hint', document.getElementById('settingsHints').textContent, t('Left / Right change') + ' · ' + t('Back groups'));
    pageOf(3, false); goToRow('city');
    eq('text hint', document.getElementById('settingsHints').textContent, t('OK edit') + ' · ' + t('Back groups'));
    pageOf(0, false); goToRow('shelf');
    eq('link hint', document.getElementById('settingsHints').textContent, t('OK open') + ' · ' + t('Back groups'));
    pageOf(3, true); goToRow('runSetup');
    eq('run hint', document.getElementById('settingsHints').textContent, t('OK open') + ' · ' + t('Back return'));
    eq('hint bar has no "apply instantly"', document.getElementById('settingsHints').textContent.indexOf('apply instantly'), -1);
    eq('hint bar is one line', document.getElementById('settingsHints').getBoundingClientRect().height < 40, true);

    // More options: a flagged row leaves the group page and a synthetic row opens a sub-page
    eq('keepAwake is flagged more', findSetting('keepAwake').more, true);
    var main4 = settingsRowsFor(2, '').map(function (d) { return d.id; });
    eq('keepAwake not on the group page', main4.indexOf('keepAwake'), -1);
    eq('group page ends with More options', main4[main4.length - 1], 'moreOptions');
    eq('settingsForCategory still lists every row', settingsForCategory(2).some(function (d) { return d.id === 'keepAwake'; }), true);
    eq('groups without more rows get no More options', settingsRowsFor(0, '').some(function (d) { return d.id === 'moreOptions'; }), false);
    settingsUi.zone = 'cats'; settingsUi.cat = 2; settingsUi.catFocus = 2; settingsUi.sub = ''; renderSettings();
    press('Enter');
    goToRow('moreOptions');
    var moreRow = m.querySelector('.settings-row[data-id="moreOptions"]');
    eq('More options hint lists the hidden labels', moreRow.querySelector('.sr-hint').textContent, moreOptionsHint(2));
    eq('hint names the first three hidden rows', moreRow.querySelector('.sr-hint').textContent, [t('Photo length'), t('Motion'), t('Motion speed')].join(', '));
    eq('More options row has a chevron', !!moreRow.querySelector('.sr-chevron'), true);
    eq('More options hint bar', document.getElementById('settingsHints').textContent, t('OK open') + ' · ' + t('Back groups'));
    press('Enter');
    eq('OK opens the sub-page', settingsUi.sub + ':' + settingsUi.zone, 'more:rows');
    var mt = document.getElementById('settingsSubTitle');
    eq('sub-page title', mt && mt.textContent, t('More options'));
    eq('sub-page shows the hidden row', !!m.querySelector('.settings-row[data-id="keepAwake"]'), true);
    eq('sub-page hides the group rows', !!m.querySelector('.settings-row[data-id="ambient"]'), false);
    eq('sub-page focus on the first row', settingsUi.row, 0);
    goToRow('keepAwake');
    press('Enter');
    eq('switch inside the sub-page flips', state.keepAwake, 'off');
    press('Enter');
    eq('and back', state.keepAwake, 'on');
    press('Escape');
    eq('Back returns to the group page', settingsUi.sub + ':' + settingsUi.zone, ':rows');
    eq('Back focuses More options', m.querySelector('.settings-row.sf').getAttribute('data-id'), 'moreOptions');
    eq('modal still open after Back from sub-page', modalOpen, true);
    press('Enter'); press('ArrowUp');
    eq('Up from the first sub-page row goes to the group list', settingsUi.zone + ':' + settingsUi.sub + ':' + settingsUi.catFocus, 'cats::2');
    press('Enter'); goToRow('moreOptions'); press('Enter');
    settingsPointerLive = true;
    m.querySelector('.settings-cat[data-i="1"]').onmouseover();
    eq('hovering another group leaves the sub-page', settingsUi.sub + ':' + settingsUi.cat, ':1');
    closeSettingsModal();
    openSettingsModal();
    eq('reopening starts on the group page', settingsUi.sub, '');
    closeSettingsModal();

    // Erase / Reset still ask twice inside the new page
    openSettingsModal(); pageOf(3, true); goToRow('reset'); press('Enter');
    eq('reset asks', settingsUi.confirmReset, 'reset');
    press('ArrowDown');
    eq('moving away cancels the ask', settingsUi.confirmReset, false);
    closeSettingsModal();

    // five rows per group: switched on by Task 3
    for (var g = 0; g < 4; g++) {
      if (MAX_FIVE_ROWS_ENABLED) eq('group ' + g + ' shows at most five rows', settingsRowsFor(g, '').length <= 5, true);
    }
    eq('max-five check is on', MAX_FIVE_ROWS_ENABLED, true);
    done();
  });
  steps.push(function (done) { // Task 3: four groups, exact rows, sub-pages, LG TV settings, honest hints
    function ids(list) { return list.map(function (d) { return d.id; }).join(','); }
    function hint() { return document.getElementById('settingsHints').textContent; }
    function open(cat, sub) { settingsUi.cat = cat; settingsUi.catFocus = cat; settingsUi.zone = 'rows'; settingsUi.row = 0; settingsUi.sub = sub || ''; renderSettings(); }
    function lastPage(cat, sub) { return settingsRowsFor(cat, sub || ''); }
    var keepProfiles = localStorage.getItem('fmtv_profiles'), keepActive = localStorage.getItem('fmtv_active_profile');
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    openSettingsModal();
    eq('Trending header is translated', document.querySelector('.picks-header').textContent, t('Trending this week'));
    eq('Trending header translation exists outside English', currentLang() === 'en' || t('Trending this week') !== 'Trending this week', true);
    eq('four groups in order', SETTING_CATEGORIES.join('|'), 'Home|Look|Screensaver|You and this TV');
    eq('Home page', ids(lastPage(0)), 'shelf,hdmiNames,pickup,scenes,showTrending');
    eq('Look page', ids(lastPage(1)), 'theme,homePhotos,textSize,clockFormat,moreOptions');
    eq('Look more', ids(lastPage(1, 'more')), 'perfMode');
    eq('Screensaver page', ids(lastPage(2)), 'ambient,idleMins,unsplashKey,nightDim,moreOptions');
    eq('Screensaver more', ids(lastPage(2, 'more')), 'ambientSecs,ambientMotion,ambientSpeed,ambientBright,clockPos,keepAwake');
    eq('You page', ids(lastPage(3)), 'userName,city,lang,people,moreOptions');
    eq('You more', ids(lastPage(3, 'more')), 'ipLocate,tmdbKey,lgTvSettings,runSetup,reset,eraseAll,about');
    eq('People page with one person', ids(lastPage(3, 'people')), 'askWho,addPerson');
    saveProfiles([{ id: 'p1', name: 'Noa', color: '#2a7de1', data: snapshotProfile() }, { id: 'p2', name: 'Kid', color: '#ff9f43', data: snapshotProfile() }]);
    localStorage.setItem('fmtv_active_profile', 'p1');
    eq('People page with two people', ids(lastPage(3, 'people')), 'askWho,switchPerson,addPerson,removePerson');
    eq('HDMI names row shown when HDMI inputs exist', lastPage(0).some(function (d) { return d.id === 'hdmiNames'; }), true);
    eq('HDMI page holds the HDMI rows', ids(lastPage(0, 'hdmi')), ids(hdmiSettings()));
    eq('HDMI names label', settingDef('hdmiNames').label, 'HDMI names');
    eq('no group page has more than five rows', [0, 1, 2, 3].filter(function (g) { return lastPage(g).length > 5; }).length, 0);
    // every setting id lives in exactly one group or sub-page
    var where = {};
    [0, 1, 2, 3].forEach(function (g) {
      ['', 'more', 'people', 'hdmi'].forEach(function (sb) {
        lastPage(g, sb).forEach(function (d) { if (d.id !== 'moreOptions') where[d.id] = (where[d.id] || 0) + 1; });
      });
    });
    var missing = [], twice = [];
    SETTINGS.forEach(function (d) {
      if (d.show && !d.show()) return;
      if (where[d.id] !== 1) (where[d.id] ? twice : missing).push(d.id);
    });
    eq('every setting is in a group or sub-page', missing.join(','), '');
    eq('no setting is in two places', twice.join(','), '');
    eq('storage keys unchanged', ['showTrending:fmtv_show_trending', 'pickup:fmtv_pickup', 'scenes:fmtv_scenes', 'theme:fmtv_theme', 'homePhotos:fmtv_home_photos', 'textSize:fmtv_text_size', 'clockFormat:fmtv_clock_format', 'perfMode:fmtv_perf_mode', 'ambient:fmtv_ambient', 'idleMins:fmtv_idle_mins', 'unsplashKey:fmtv_unsplash_key', 'nightDim:fmtv_night_dim', 'ambientSecs:fmtv_ambient_secs', 'ambientMotion:fmtv_ambient_motion', 'ambientSpeed:fmtv_ambient_speed', 'ambientBright:fmtv_ambient_bright', 'clockPos:fmtv_clock_pos', 'keepAwake:fmtv_keep_awake', 'userName:fmtv_user_name', 'city:fmtv_city', 'lang:fmtv_lang', 'askWho:fmtv_ask_who', 'ipLocate:fmtv_ip_locate', 'tmdbKey:fmtv_tmdb_key'].filter(function (p) { var a = p.split(':'); return findSetting(a[0]).store !== a[1]; }).join(','), '');
    // canvas wording
    eq('labels', ['shelf', 'pickup', 'scenes', 'showTrending', 'theme', 'homePhotos', 'textSize', 'clockFormat', 'perfMode', 'ambient', 'idleMins', 'unsplashKey', 'nightDim', 'ambientSecs', 'ambientMotion', 'ambientSpeed', 'ambientBright', 'clockPos', 'keepAwake', 'userName', 'city', 'lang', 'people', 'ipLocate', 'tmdbKey', 'lgTvSettings'].map(function (i) { return findSetting(i).label; }).join('|'),
      'Apps on Home|Continue where you left off|Scenes|Trending this week|Look|Photos on Home|Text size|Clock format|Performance mode|Photo screensaver|Starts after|Photos from|Dimmer at night|Photo length|Motion|Motion speed|Brightness|Clock position|Keep LG screensaver away|Your name|City|Language|People|Auto-locate by IP|TMDB key|LG TV settings');
    eq('theme keeps all four options', findSetting('theme').options.length, 4);
    eq('pickup hint', findSetting('pickup').hint, 'The apps you opened last, first in the row');
    eq('scenes hint', findSetting('scenes').hint, 'Movie night, Game on, Music');
    eq('screensaver hint', findSetting('ambient').hint, 'Photos and the clock when the TV is idle');
    eq('ip hint', findSetting('ipLocate').hint, 'Off uses your city. On sends your IP to ipapi.co.');
    // values on the link rows
    open(0);
    eq('Apps on Home value', modalEl().querySelector('.settings-row[data-id="shelf"] .sr-value').textContent, state.favorites.length === 1 ? t('1 app') : t('%s apps', String(state.favorites.length)));
    var keepDev = JSON.parse(JSON.stringify(state.hdmiDevices)), hd0 = hdmiSettings();
    state.hdmiDevices = {}; renderSettings();
    eq('HDMI names value when none', modalEl().querySelector('.settings-row[data-id="hdmiNames"] .sr-value').textContent, t('Not set'));
    state.hdmiDevices[hd0[0].hdmi.id] = 'ps5'; state.hdmiDevices[hd0[1].hdmi.id] = 'xbox'; renderSettings();
    eq('HDMI names value lists the names', modalEl().querySelector('.settings-row[data-id="hdmiNames"] .sr-value').textContent, 'PS5, Xbox');
    // HDMI sub-page: opens from the link row, edits persist under the same key, Back returns to the link row
    settingsUi.zone = 'rows'; settingsUi.row = 1; press('Enter');
    eq('HDMI row opens the sub-page', settingsUi.sub + ':' + settingsUi.zone, 'hdmi:rows');
    eq('HDMI sub-page title', document.getElementById('settingsSubTitle').textContent, t('HDMI names'));
    eq('HDMI sub-page shows the HDMI rows', modalEl().querySelectorAll('#settingsRows .settings-row').length, hd0.length);
    eq('sub-page hint says Back return', hint(), t('Left / Right change') + ' · ' + t('Back return'));
    var before = state.hdmiDevices[hd0[0].hdmi.id];
    press('ArrowRight');
    eq('HDMI edit persists', JSON.parse(localStorage.getItem('fmtv_hdmi_devices'))[hd0[0].hdmi.id] !== before, true);
    press('Escape');
    eq('Back from HDMI names focuses its row', settingsUi.sub + ':' + settingsUi.row, ':1');
    state.hdmiDevices = keepDev; localStorage.setItem('fmtv_hdmi_devices', JSON.stringify(keepDev)); renderAppsShelf();
    // People sub-page
    open(3); settingsUi.row = 3; renderSettings(); press('Enter');
    eq('People opens a sub-page', settingsUi.sub, 'people');
    eq('People sub-page title', document.getElementById('settingsSubTitle').textContent, t('People'));
    eq('People rows', ids(settingsRowsFor(3)), 'askWho,switchPerson,addPerson,removePerson');
    press('Escape');
    eq('Back from People focuses People', settingsUi.sub + ':' + settingsRowsFor(3)[settingsUi.row].id, ':people');
    // Photos from never shows the key
    state.unsplashKey = ''; open(2);
    eq('Photos from when empty', modalEl().querySelector('.settings-row[data-id="unsplashKey"] .sr-value').textContent, t('Not set'));
    state.unsplashKey = 'SECRET-KEY-98765'; renderSettings();
    eq('Photos from when set', modalEl().querySelector('.settings-row[data-id="unsplashKey"] .sr-value').textContent, t('Unsplash, connected'));
    eq('Photos from never shows the key', modalEl().textContent.indexOf('SECRET-KEY-98765'), -1);
    settingsUi.row = 2; press('Enter');
    eq('OK on Photos from opens the key editor', settingsUi.zone + ':' + (document.getElementById('settingsEditInput') || {}).type, 'edit:password');
    press('Escape');
    state.unsplashKey = ''; renderSettings();
    // LG TV settings row calls the launch function the old button used
    var realLaunch = window.launchApp, launched = [];
    window.launchApp = function (id) { launched.push(id); };
    open(3, 'more'); settingsUi.row = settingsRowsFor(3).map(function (d) { return d.id; }).indexOf('lgTvSettings'); renderSettings();
    eq('LG TV settings is a run row', settingsRowsFor(3)[settingsUi.row].type, 'run');
    press('Enter');
    window.launchApp = realLaunch;
    eq('LG TV settings launches the LG Settings app', launched.join(','), LG_SETTINGS_APP);
    closeSettingsModal(); openSettingsModal();
    // honest hints per zone and page
    eq('groups hint', hint(), t('OK open') + ' · ' + t('Back close'));
    open(2); eq('rows hint (switch)', hint(), t('OK switch') + ' · ' + t('Back groups'));
    settingsUi.row = 1; paintFocus(); eq('rows hint (choice)', hint(), t('Left / Right change') + ' · ' + t('Back groups'));
    open(3); settingsUi.row = 0; paintFocus(); eq('rows hint (text)', hint(), t('OK edit') + ' · ' + t('Back groups'));
    settingsUi.row = 3; paintFocus(); eq('rows hint (sub-page link)', hint(), t('OK open') + ' · ' + t('Back groups'));
    open(3, 'more'); settingsUi.row = settingsRowsFor(3).length - 1; paintFocus();
    eq('More page hint on an info row', hint(), t('Back return'));
    settingsUi.row = 0; paintFocus(); eq('More page hint on a switch', hint(), t('OK switch') + ' · ' + t('Back return'));
    // armed confirm: hint and Back cancel
    settingsUi.row = settingsRowsFor(3).map(function (d) { return d.id; }).indexOf('reset'); renderSettings(); press('Enter');
    eq('armed Reset', settingsUi.confirmReset, 'reset');
    eq('armed hint', hint(), t('OK confirm') + ' · ' + t('Back cancel'));
    press('Escape');
    eq('Back cancels the armed question and stays on the page', settingsUi.confirmReset + ':' + settingsUi.sub + ':' + settingsUi.zone, 'false:more:rows');
    eq('hint is normal again', hint(), t('OK open') + ' · ' + t('Back return'));
    // switch accessibility
    open(2); var swEl = modalEl().querySelector('.settings-row[data-id="ambient"] .sr-switch');
    eq('switch role', swEl.getAttribute('role'), 'switch');
    state.ambient = 'on'; renderSettings();
    eq('aria-checked on', modalEl().querySelector('.settings-row[data-id="ambient"] .sr-switch').getAttribute('aria-checked'), 'true');
    settingsUi.row = 0; press('Enter');
    eq('aria-checked follows the switch', modalEl().querySelector('.settings-row[data-id="ambient"] .sr-switch').getAttribute('aria-checked'), 'false');
    state.ambient = 'on'; localStorage.setItem('fmtv_ambient', 'on');
    // white focus ring
    renderSettings();
    var fr = modalEl().querySelector('.settings-row.sf'); fr.style.transition = 'none';
    eq('row focus ring is white', getComputedStyle(fr).boxShadow.indexOf('rgb(255, 255, 255)') !== -1 && getComputedStyle(fr).boxShadow.indexOf('rgb(10, 132, 255)') === -1, true);
    // an empty page never throws
    var keepCat = state.catalog; state.catalog = []; open(0, 'hdmi');
    eq('hdmi page empty', settingsRowsFor(0).length, 0);
    eq('HDMI names row hidden without HDMI inputs', settingsRowsFor(0, '').some(function (d) { return d.id === 'hdmiNames'; }), false);
    eq('Home page without HDMI inputs', ids(settingsRowsFor(0, '')), 'shelf,pickup,scenes,showTrending');
    var threw = '';
    ['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Enter'].forEach(function (k) {
      open(0, 'hdmi');
      try { handleSettingsKey({ key: k, keyCode: 0, preventDefault: function () {} }); } catch (err) { threw += k + ':' + err.message + ' '; }
      eq('empty page stays valid after ' + k, settingsUi.row >= 0, true);
    });
    try { open(0, 'hdmi'); settingsHintsFor('rows'); renderSettings(); } catch (err2) { threw += 'hint:' + err2.message; }
    eq('empty More or sub-page does not throw', threw, '');
    state.catalog = keepCat;
    closeSettingsModal();
    if (keepProfiles === null) localStorage.removeItem('fmtv_profiles'); else localStorage.setItem('fmtv_profiles', keepProfiles);
    if (keepActive === null) localStorage.removeItem('fmtv_active_profile'); else localStorage.setItem('fmtv_active_profile', keepActive);
    done();
  });
  steps.push(function (done) { // the greeting shows the name and the part of the day
    state.userName = 'Noa'; updateGreeting();
    eq('greeting title', document.getElementById('greetingTitle').textContent, greetingText(new Date().getHours(), 'Noa'));
    eq('greeting eyebrow set', document.getElementById('greetingEyebrow').textContent.length > 0, true);
    state.userName = ''; updateGreeting();
    eq('greeting no name', document.getElementById('greetingTitle').textContent, t(greetingKey(new Date().getHours())));
    done();
  });
  steps.push(function (done) { // calm home: one headline, logo-only tiles, one caption, quiet corners
    function gearBtn0() { return document.getElementById('customizeBtn'); }
    function vis(el) { return el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden'; }
    var keepFav = state.favorites.slice(), keepPickup = state.pickup, keepFavStore = localStorage.getItem('fmtv_favorites');
    localStorage.removeItem('fmtv_launch_hist'); state.pickup = 'on'; renderAppsShelf();
    ['FPS', 'Instant', 'Curated', 'Favorite Apps', 'No ads', 'Live Feed'].forEach(function (word) {
      var hits = toArray(document.querySelectorAll('.container *')).filter(function (el) {
        if (el.children.length || el.id === 'trustLine' || (el.parentNode && el.parentNode.id === 'trustLine')) return false; // the privacy line stays on Home (decision 5)
        return el.textContent.indexOf(word) !== -1 && vis(el);
      });
      eq('home shows no "' + word + '"', hits.map(function (el) { return el.id || el.className; }).join(','), '');
    });
    ['heroTag', 'heroTitle', 'heroDesc', 'themeBadge', 'greetingSub', 'picksSourceBadge'].forEach(function (id) {
      eq(id + ' hidden', vis(document.getElementById(id)), false);
    });
    var tvBtn = document.getElementById('tvSettingsBtn');
    eq('TV Settings button not in the top bar', !tvBtn || !vis(tvBtn), true);
    var wx = document.getElementById('weatherWidget');
    setMainFocus(gearBtn0());
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
    eq('Right from the gear focuses the weather', document.querySelector('.nav-item.focused'), wx);
    wx.style.transition = 'none';
    eq('weather has a white ring when focused', getComputedStyle(wx).outlineStyle + getComputedStyle(wx).outlineWidth, 'solid3px');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true, cancelable: true }));
    eq('Enter on the weather opens the forecast drawer', drawerOpen, true);
    closeDrawer();
    eq('drawer closes', drawerOpen, false);
    setMainFocus(document.querySelector('#appsGrid .app-tile'));
    var gear = document.getElementById('customizeBtn');
    eq('gear has aria-label', !!gear.getAttribute('aria-label'), true);
    eq('gear is 60px round', gear.getBoundingClientRect().width + 'x' + gear.getBoundingClientRect().height, '60x60');
    var tile = document.querySelector('#appsGrid .app-tile');
    eq('tile is 204px', Math.round(tile.offsetWidth) + 'x' + Math.round(tile.offsetHeight), '204x204');
    var t0 = document.querySelectorAll('#appsGrid .app-tile')[0].getBoundingClientRect(), t1 = document.querySelectorAll('#appsGrid .app-tile')[1].getBoundingClientRect();
    eq('tiles keep 24px apart', Math.round(t1.left - t0.right), 24);
    eq('greeting title 78px', getComputedStyle(document.getElementById('greetingTitle')).fontSize, '78px');
    eq('clock 39px', getComputedStyle(document.getElementById('clockText')).fontSize, '39px');
    eq('greeting eyebrow is the weekday', document.getElementById('greetingEyebrow').textContent, new Date().toLocaleDateString(LANG_LOCALES[currentLang()], { weekday: 'long' }));
    // the corner text beside the clock
    if (currentLang() === 'en') {
      document.getElementById('weatherText').textContent = '17°C • Clear';
      document.getElementById('weatherSub').textContent = 'Tel Aviv • Sunset 18:18';
      state.sunset = '18:18'; updateGreeting();
      eq('weather corner text', /^\d+° .+ · Sunset \d\d:\d\d$/.test(document.getElementById('weatherCorner').textContent), true);
    }
    // one caption, on the focused tile
    var labels = toArray(document.querySelectorAll('.app-tile .app-label')).filter(vis);
    eq('exactly one visible tile caption', labels.length, 1);
    var focused = document.querySelector('.app-tile.focused');
    eq('the focused tile owns the caption', !!focused && labels[0] === focused.querySelector('.app-label'), true);
    eq('caption is the app name', labels[0].textContent, focused.dataset.title);
    focused.style.transition = 'none';
    eq('focused tile scales 1.06', getComputedStyle(focused).transform.indexOf('1.06') !== -1, true);
    // pick-up with an app on the shelf: focus and caption
    var T = Date.now(), id = state.favorites[2], hist = {};
    hist[id] = { t: T - 60000, n: 1 };
    localStorage.setItem('fmtv_launch_hist', JSON.stringify(hist));
    document.querySelectorAll('.nav-item.focused').forEach(function (el) { el.classList.remove('focused'); });
    renderAppsShelf();
    var f2 = document.querySelector('.nav-item.focused');
    eq('pick-up focuses the last opened tile', f2 && f2.dataset.id, id);
    var title = f2.dataset.title, hhmm = pad2(new Date(T - 60000).getHours()) + ':' + pad2(new Date(T - 60000).getMinutes());
    eq('pick-up caption', f2.querySelector('.app-label').textContent, t('%s, opened at %s', title, hhmm));
    eq('pick-up caption mentions the time', f2.querySelector('.app-label').textContent.indexOf(hhmm) !== -1, true);
    eq('shelf order unchanged', toArray(document.querySelectorAll('#appsGrid .app-tile:not(.tile-recent)')).map(function (el) { return el.dataset.id; }).join(','), state.favorites.join(','));
    eq('pick-up section stays hidden', vis(document.getElementById('pickupSection')), false);
    // an earlier day shows the weekday
    hist[id] = { t: T - 3 * 86400000, n: 1 };
    localStorage.setItem('fmtv_launch_hist', JSON.stringify(hist));
    renderAppsShelf();
    eq('earlier caption uses the weekday', document.querySelector('#appsGrid .app-tile[data-id="' + id + '"] .app-label').textContent,
      t('%s, opened %s', title, new Date(T - 3 * 86400000).toLocaleDateString(LANG_LOCALES[currentLang()], { weekday: 'long' })));
    // pick-up off: the first tile has the focus
    state.pickup = 'off';
    document.querySelectorAll('.nav-item.focused').forEach(function (el) { el.classList.remove('focused'); });
    renderAppsShelf();
    eq('pick-up off focuses the first tile', document.querySelector('.nav-item.focused').dataset.id, state.favorites[0]);
    eq('pick-up off: no recent tiles', document.querySelectorAll('#appsGrid .tile-recent').length, 0);
    eq('pick-up off: plain caption', document.querySelector('.app-tile.focused .app-label').textContent, document.querySelector('.app-tile.focused').dataset.title);
    // recent tiles for apps that are not on the shelf
    state.pickup = 'on';
    var off = state.catalog.filter(function (c) { return state.favorites.indexOf(c.id) === -1; }).slice(0, 2);
    hist = {};
    hist[off[0].id] = { t: T - 1000, n: 1 }; hist[off[1].id] = { t: T - 2000, n: 1 }; hist[id] = { t: T - 5000, n: 1 };
    localStorage.setItem('fmtv_launch_hist', JSON.stringify(hist));
    document.querySelectorAll('.nav-item.focused').forEach(function (el) { el.classList.remove('focused'); });
    renderAppsShelf();
    var kids = toArray(document.getElementById('appsGrid').children);
    eq('recent tiles come first', kids.slice(0, 2).map(function (el) { return el.classList.contains('tile-recent'); }).join(), 'true,true');
    eq('a thin divider follows', kids[2].classList.contains('tile-divider') && kids[2].offsetWidth === 2 && kids[2].offsetHeight === 160, true);
    eq('recent order is newest first', kids[0].dataset.id + ',' + kids[1].dataset.id, off[0].id + ',' + off[1].id);
    eq('recent tiles are nav items', mainNavItems.indexOf(kids[0]) !== -1, true);
    eq('recent caption has the time', kids[0].querySelector('.app-label').textContent.indexOf(pad2(new Date(T - 1000).getHours())) !== -1, true);
    eq('recent tiles stay off the shelf', state.favorites.join(','), keepFav.join(','));
    eq('recent tiles are never stored', localStorage.getItem('fmtv_favorites'), keepFavStore);
    var gotId = null, oldWeb = window.webOS, gotReq = null;
    window.webOS = { service: { request: function (uri, o) { gotReq = o; gotId = o.parameters.id; } } };
    kids[0].click();
    eq('a recent tile launches its app', gotId, off[0].id);
    if (gotReq) gotReq.onSuccess({ returnValue: true });
    window.webOS = oldWeb;
    // coming back to the app: focus moves to the pick-up tile when pick-up is on, stays put when it is off
    setMainFocus(document.querySelectorAll('#appsGrid .app-tile:not(.tile-recent)')[4]);
    var parked = document.querySelector('.nav-item.focused').dataset.id;
    onVisibilityChange();
    eq('return to app with pick-up on focuses the last opened tile', document.querySelector('.nav-item.focused').dataset.id, id);
    state.pickup = 'off';
    setMainFocus(document.querySelectorAll('#appsGrid .app-tile')[4]);
    parked = document.querySelector('.nav-item.focused').dataset.id;
    onVisibilityChange();
    eq('return to app with pick-up off keeps the focus', document.querySelector('.nav-item.focused').dataset.id, parked);
    state.pickup = 'on'; renderAppsShelf();
    eq('focus still lands on the last opened shelf tile', document.querySelector('.nav-item.focused').dataset.id, id);
    // dim lower rows
    var scenes = document.getElementById('scenesRow'), picks = document.querySelector('.picks-section');
    state.scenes = 'on'; state.showTrending = 'on'; applyTrendingClass(); renderScenes();
    setMainFocus(document.querySelector('#appsGrid .app-tile:not(.tile-recent)'));
    eq('scenes dim while focus is on the shelf', scenes.classList.contains('row-dim'), true);
    eq('trending dims too', picks.classList.contains('row-dim'), true);
    scenes.style.transition = 'none';
    eq('dim is 55 percent', getComputedStyle(scenes).opacity, '0.55');
    setMainFocus(scenes.querySelector('.scene-chip'));
    eq('scenes full while a chip has focus', scenes.classList.contains('row-dim'), false);
    eq('trending still dim', picks.classList.contains('row-dim'), true);
    eq('full opacity', getComputedStyle(scenes).opacity, '1');
    setMainFocus(document.getElementById('tabMovies'));
    eq('trending full while a tab has focus', picks.classList.contains('row-dim'), false);
    // the old pick-up row stays empty and hidden; its function stays callable
    renderPickup();
    eq('pickup row empty', document.querySelectorAll('#pickupRow .pickup-card').length, 0);
    localStorage.removeItem('fmtv_launch_hist'); state.pickup = keepPickup; renderAppsShelf();
    done();
  });
  steps.push(function (done) { // an app added to the catalog later (discovered on the TV) shows as a recent tile
    localStorage.removeItem('fmtv_launch_hist'); state.pickup = 'on';
    var fake = { id: 'fake.app', title: 'Fake', tag: 'Streaming', desc: 'Watch 4K videos, live streams, music, and coding radio.', color: '#ff0000', badge: 'F', bg: '#000' };
    state.catalog.push(fake);
    recordLaunch('fake.app', Date.now());
    renderAppsShelf();
    eq('recent tile follows catalog', !!document.querySelector('#appsGrid .tile-recent[data-id="fake.app"]'), true);
    state.catalog.pop();
    localStorage.removeItem('fmtv_launch_hist');
    renderAppsShelf();
    eq('recent tile cleared again', document.querySelectorAll('#appsGrid .tile-recent').length, 0);
    done();
  });
  steps.push(function (done) { // arranging apps on Home: hold OK or Settings > Apps on Home; Left/Right move, Down removes, OK/Back save
    var keepFav = state.favorites.slice(), keepStore = localStorage.getItem('fmtv_favorites'), keepPickup = state.pickup, oldWeb = window.webOS;
    var launched = [], lastReq = null;
    window.webOS = { service: { request: function (uri, o) { lastReq = o; launched.push(o.parameters.id); } } };
    function settle() { if (lastReq && lastReq.onSuccess) lastReq.onSuccess({ returnValue: true }); lastReq = null; pendingLaunch = null; }
    function kd(k, repeat) { if (k === 'Enter' && !repeat) document.dispatchEvent(new KeyboardEvent('keyup', { key: k, bubbles: true, cancelable: true })); var ev = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, repeat: !!repeat }); document.dispatchEvent(ev); return ev; }
    function ku(k) { document.dispatchEvent(new KeyboardEvent('keyup', { key: k, bubbles: true, cancelable: true })); }
    function order() { return toArray(document.querySelectorAll('#appsGrid .app-tile[data-id]')).map(function (el) { return el.dataset.id; }); }
    function stored() { return JSON.parse(localStorage.getItem('fmtv_favorites')); }
    function vis(el) { return el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden'; }
    function setFav(list) { state.favorites = list.slice(); localStorage.setItem('fmtv_favorites', JSON.stringify(list)); renderAppsShelf(); }
    function tileOf(id) { return document.querySelector('#appsGrid .app-tile[data-id="' + id + '"]'); }
    var ids = keepFav.slice(0, 5), off = state.catalog.filter(function (c) { return keepFav.indexOf(c.id) === -1; }).slice(0, 2);
    var names = {};
    state.catalog.forEach(function (c) { names[c.id] = c.title; });
    state.pickup = 'off'; localStorage.removeItem('fmtv_launch_hist');
    setFav(ids);
    eq('old Reorder button is gone', !document.getElementById('reorderShelfBtn') && !document.getElementById('saveShelfOrder') && !document.getElementById('cancelShelfOrder'), true);
    eq('Home shows no Add app tile when apps exist', document.querySelectorAll('#appsGrid .tile-add').length, 0);
    // short press launches on release, not on press; a repeated keydown neither relaunches nor restarts the timer
    setMainFocus(tileOf(ids[1]));
    kd('Enter');
    eq('keydown alone does not launch', launched.length, 0);
    kd('Enter', true); kd('Enter', true);
    ku('Enter');
    eq('short press launches the tile once', launched.join(), ids[1]);
    settle();
    eq('short press does not arrange', !shelfEdit && !document.body.classList.contains('arranging'), true);
    // long press: 700 ms virtual wait, then keyup
    setMainFocus(tileOf(ids[2]));
    kd('Enter');
    setTimeout(function () {
      eq('long press enters arranging', !!shelfEdit && document.body.classList.contains('arranging'), true);
      eq('long press lifts the pressed tile', movingTileId, ids[2]);
      eq('long press does not launch', launched.length, 1);
      kd('Enter', true);
      eq('repeated keydown while held does not finish', !!shelfEdit, true);
      ku('Enter');
      eq('the keyup after a long press is swallowed', !!shelfEdit && launched.length === 1, true);
      var lifted = tileOf(ids[2]), other = tileOf(ids[0]);
      lifted.style.transition = 'none'; other.style.transition = 'none';
      var M = window.DOMMatrix || window.WebKitCSSMatrix, m = new M(getComputedStyle(lifted).transform);
      eq('lifted tile scales 1.08', Math.round(m.m11 * 100), 108);
      eq('lifted tile is raised 21px', Math.round(m.m42), -21);
      eq('lifted tile has a white ring', getComputedStyle(lifted).outlineStyle + ' ' + getComputedStyle(lifted).outlineColor, 'solid rgb(255, 255, 255)');
      eq('other tiles are 70 percent', getComputedStyle(other).opacity, '0.7');
      eq('lifted tile is fully opaque', getComputedStyle(lifted).opacity, '1');
      eq('lifted caption', lifted.querySelector('.app-label').textContent, '‹ ' + t('Moving') + ' ›');
      eq('lifted caption visible', vis(lifted.querySelector('.app-label')), true);
      var title = document.getElementById('arrangeTitle'), sub = document.getElementById('arrangeSub');
      eq('arrange title text', title.textContent, t('Arrange your apps'));
      eq('arrange title 60px', getComputedStyle(title).fontSize, '60px');
      eq('arrange sub text', sub.textContent, t('Hold OK on any app on Home to get here.'));
      eq('arrange sub 27px', getComputedStyle(sub).fontSize, '27px');
      eq('greeting hidden while arranging', vis(document.getElementById('greetingTitle')), false);
      eq('hint bar text', document.getElementById('arrangeHint').textContent, t('Left / Right move · Down remove · OK done'));
      eq('hint bar visible', vis(document.getElementById('arrangeHint')), true);
      eq('Add app tile after the last app', document.querySelector('#appsGrid .app-tile:last-child').classList.contains('tile-add'), true);
      eq('Add app tile text', document.querySelector('#appsGrid .tile-add').textContent.indexOf(t('Add app')) !== -1, true);
      eq('Add app tile dashed', getComputedStyle(document.querySelector('#appsGrid .tile-add')).borderTopStyle, 'dashed');
      eq('only shelf items are reachable while arranging', mainNavItems.every(function (el) { return !!el.closest('.shelf-wrapper'); }), true);
      kd('ArrowRight');
      eq('Right moves the lifted app', order().join(), [ids[0], ids[1], ids[3], ids[2], ids[4]].join());
      eq('the move is saved', stored().join(), order().join());
      eq('state follows', state.favorites.join(), order().join());
      kd('ArrowLeft'); kd('ArrowLeft'); kd('ArrowLeft'); kd('ArrowLeft');
      eq('Left moves to the front and stops there', order().join(), [ids[2], ids[0], ids[1], ids[3], ids[4]].join());
      eq('Left persisted', stored().join(), order().join());
      eq('the lifted tile keeps the focus', document.querySelector('.nav-item.focused').dataset.id, ids[2]);
      kd('ArrowDown');
      eq('Down removes the lifted app', order().join(), [ids[0], ids[1], ids[3], ids[4]].join());
      eq('removal persisted', stored().join(), order().join());
      eq('removal toast', document.getElementById('toastMsg').textContent, t('Removed %s from Home', names[ids[2]]));
      eq('the next app is lifted', movingTileId, ids[0]);
      eq('state has no removed app', state.favorites.indexOf(ids[2]), -1);
      // Right past the last app focuses Add app; OK opens the shelf apps picker
      kd('ArrowRight'); kd('ArrowRight'); kd('ArrowRight'); kd('ArrowRight');
      eq('Right at the end reaches the Add app tile', document.querySelector('.nav-item.focused').classList.contains('tile-add'), true);
      eq('nothing is lifted on the Add app tile', document.querySelectorAll('#appsGrid .app-tile.moving').length, 0);
      kd('Enter'); ku('Enter');
      eq('Add app opens the shelf apps picker', modalOpen && settingsUi.zone === 'apps', true);
      eq('arranging paused while the picker is open', !shelfEdit, true);
      var arrRow = document.getElementById('arrangeRow');
      eq('picker has the Arrange on Home row', !!arrRow && arrRow.textContent === t('Arrange on Home'), true);
      eq('and it comes before the apps', !!(arrRow.compareDocumentPosition(document.getElementById('settingsAppsGrid')) & 4), true);
      kd('Escape');
      eq('Back from the picker closes Settings', modalOpen, false);
      eq('and resumes arranging', !!shelfEdit && document.body.classList.contains('arranging'), true);
      eq('with an app lifted', !!movingTileId && !!tileOf(movingTileId), true);
      // OK finishes and saves
      kd('Enter'); ku('Enter');
      eq('OK finishes', !shelfEdit && !document.body.classList.contains('arranging'), true);
      eq('Home is back', vis(document.getElementById('greetingTitle')), true);
      eq('no Add app tile on Home', document.querySelectorAll('#appsGrid .tile-add').length, 0);
      eq('OK kept the order', stored().join(), state.favorites.join());
      eq('saved toast', document.getElementById('toastMsg').textContent, t('Tile order saved'));
      // Back also finishes and saves
      setFav(ids);
      setMainFocus(tileOf(ids[3]));
      kd('Enter');
      setTimeout(function () {
        eq('second long press arranges', movingTileId, ids[3]);
        ku('Enter');
        kd('ArrowLeft');
        kd('Escape');
        eq('Back finishes', !shelfEdit && !document.body.classList.contains('arranging'), true);
        eq('Back saved the move', stored().join(), [ids[0], ids[1], ids[3], ids[2], ids[4]].join());
        eq('Home again after Back', order().join(), stored().join());
        eq('focus stays on the moved tile', document.querySelector('.nav-item.focused').dataset.id, ids[3]);
        // recent tiles and the divider are not part of arranging
        state.pickup = 'on';
        var hist = {}; hist[off[0].id] = { t: Date.now() - 1000, n: 1 }; hist[off[1].id] = { t: Date.now() - 2000, n: 1 };
        localStorage.setItem('fmtv_launch_hist', JSON.stringify(hist));
        setFav(ids);
        eq('recent tiles show on Home', document.querySelectorAll('#appsGrid .tile-recent').length, 2);
        var recent = document.querySelector('#appsGrid .tile-recent');
        setMainFocus(recent);
        launched.length = 0;
        kd('Enter');
        setTimeout(function () {
          eq('holding OK on a recent tile does not arrange', !shelfEdit, true);
          ku('Enter');
          eq('releasing OK on a recent tile launches it', launched.join(), recent.dataset.id);
          settle();
          setMainFocus(tileOf(ids[0]));
          kd('Enter');
          setTimeout(function () {
            eq('long press with recent tiles arranges', !!shelfEdit, true);
            ku('Enter');
            eq('recent tiles are hidden while arranging', document.querySelectorAll('#appsGrid .tile-recent, #appsGrid .tile-divider').length, 0);
            eq('arranging works on shelf apps only', JSON.stringify(shelfEdit), JSON.stringify(ids));
            kd('Enter'); ku('Enter');
            eq('shelf unchanged after arranging with recents', stored().join(), ids.join());
            eq('recent tiles are back on Home', document.querySelectorAll('#appsGrid .tile-recent').length, 2);
            state.pickup = 'off'; localStorage.removeItem('fmtv_launch_hist'); renderAppsShelf();
            // entry from Settings > Home > Apps on Home > Arrange on Home
            openSettingsModal();
            settingsUi.cat = 0; settingsUi.catFocus = 0; renderSettings();
            kd('Enter'); kd('Enter');
            eq('Apps on Home page is open', settingsUi.zone, 'apps');
            kd('ArrowUp');
            eq('Up reaches the Arrange on Home row', settingsUi.appIdx, -1);
            eq('Arrange on Home row has the focus ring', document.getElementById('arrangeRow').classList.contains('sf'), true);
            eq('Arrange row hint', document.getElementById('settingsHints').textContent, t('OK start') + ' · ' + t('Back return'));
            kd('ArrowDown');
            eq('Down returns to the first app', settingsUi.appIdx, 0);
            kd('ArrowUp'); kd('Enter');
            eq('Arrange on Home closes Settings', modalOpen, false);
            eq('Arrange on Home starts arranging', !!shelfEdit && document.body.classList.contains('arranging'), true);
            eq('the first shelf tile is lifted', movingTileId, ids[0]);
            // the last app cannot be removed
            kd('Enter'); ku('Enter');
            setFav([ids[0]]);
            startArranging(ids[0]);
            kd('ArrowDown');
            eq('Down keeps the last app', state.favorites.join() === ids[0] && !!shelfEdit, true);
            eq('last app toast', document.getElementById('toastMsg').textContent, t('Keep at least one app on the shelf.'));
            finishShelfEdit();
            // an empty shelf (from storage) shows the Add app tile
            setFav([]);
            eq('Home shows the Add app tile', document.querySelectorAll('#appsGrid .tile-add').length, 1);
            eq('and no app tiles', document.querySelectorAll('#appsGrid .app-tile[data-id]').length, 0);
            eq('Add app tile has the focus', document.querySelector('.nav-item.focused').classList.contains('tile-add'), true);
            kd('Enter'); ku('Enter');
            eq('OK on the empty-state Add app tile opens the picker', modalOpen && settingsUi.zone === 'apps', true);
            kd('Escape'); kd('Escape'); kd('Escape');
            eq('Back closes Settings to Home', modalOpen, false);
            eq('Home, not arranging', !shelfEdit, true);
            // pointer: clicking the Add app tile while arranging opens the picker too
            setFav(ids);
            startArranging(ids[0]);
            document.querySelector('#appsGrid .tile-add').click();
            eq('clicking Add app opens the picker', modalOpen && settingsUi.zone === 'apps', true);
            closeSettingsModal();
            finishShelfEdit();
            eq('left clean', !shelfEdit && !document.body.classList.contains('arranging'), true);
            function rawDown() { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); }
            // Kids lock: nothing can be arranged or added
            setFav(ids); state.locked = true; renderAppsShelf();
            eq('locked: no Add app tile on an empty shelf', (setFav([]), document.querySelectorAll('#appsGrid .tile-add').length), 0);
            setFav(ids);
            openShelfPicker(false); eq('locked: picker does not open', modalOpen, false);
            arrangeFromSettings(); startArranging(ids[0]);
            eq('locked: no arranging', !shelfEdit && !document.body.classList.contains('arranging'), true);
            launched.length = 0; setMainFocus(tileOf(ids[1]));
            kd('Enter');
            eq('locked: a shelf tile launches on keydown', launched.join(), ids[1]);
            settle(); ku('Enter');
            state.locked = false; renderAppsShelf();
            // a TV that never sends keyup launches on keydown, no timer
            keyupSeen = false; launched.length = 0; setMainFocus(tileOf(ids[2]));
            rawDown();
            eq('no keyup seen: launches on keydown', launched.join(), ids[2]);
            settle();
            eq('and starts no timer', enterTimer, null);
            ku('Enter');
            eq('after a keyup the fallback is off', keyupSeen, true);
            // a lost keyup after a long press must not eat the next short press
            swallowEnterUp = true; swallowAt = Date.now(); guardUntil = 0; launched.length = 0; setMainFocus(tileOf(ids[3]));
            rawDown(); ku('Enter');
            eq('stale swallow: the next short press launches', launched.join(), ids[3]);
            settle();
            // coming back to the app resets the key state
            swallowEnterUp = true; guardUntil = Date.now() + 9999; onVisibilityChange();
            eq('visibility change clears the swallow', swallowEnterUp, false);
            eq('visibility change clears the guard', guardUntil, 0);
            // OK held through the transition: repeats without e.repeat do not finish arranging
            startArranging(ids[0]);
            rawDown(); rawDown(); rawDown();
            eq('held OK (no repeat flag) does not finish arranging', !!shelfEdit, true);
            ku('Enter'); rawDown();
            eq('OK after the keyup finishes', !shelfEdit, true);
            ku('Enter');
            // a press whose tile left the DOM does not launch
            launched.length = 0; setMainFocus(tileOf(ids[1]));
            rawDown(); renderAppsShelf(); ku('Enter');
            eq('keyup on a removed tile launches nothing', launched.length, 0);
            window.webOS = oldWeb; settle();
            state.favorites = keepFav; state.pickup = keepPickup;
            if (keepStore === null) localStorage.removeItem('fmtv_favorites'); else localStorage.setItem('fmtv_favorites', keepStore);
            localStorage.removeItem('fmtv_launch_hist'); renderAppsShelf();
            done();
          }, 700);
        }, 700);
      }, 700);
    }, 700);
  });
  steps.push(function (done) { // D-pad focus draws a white ring on every kind of focusable element
    var ids = ['customizeBtn', 'tabMovies'];
    var els = ids.map(function (id) { return document.getElementById(id); });
    localStorage.removeItem('fmtv_launch_hist'); state.pickup = 'on';
    recordLaunch('com.webos.app.mediadiscovery', Date.now()); renderAppsShelf();
    var tile = document.querySelector('.app-tile:not(.tile-recent)'), card = document.querySelector('.pick-card');
    if (tile) els.push(tile);
    if (card) els.push(card);
    var pc = document.querySelector('#appsGrid .tile-recent');
    if (pc) els.push(pc);
    els.forEach(function (el, i) {
      el.classList.add('focused');
      var cs = getComputedStyle(el);
      eq('ring style ' + i, cs.outlineStyle, 'solid');
      eq('ring width ' + i, cs.outlineWidth, '3px');
      el.classList.remove('focused');
    });
    localStorage.removeItem('fmtv_launch_hist'); renderAppsShelf();
    done();
  });
  steps.push(function (done) { // an HDMI row changes its device with Right and saves at once
    var hd = hdmiSettings()[0];
    if (!hd) { fails.push('no HDMI row in the test catalog'); done(); return; }
    var keepDev = JSON.parse(JSON.stringify(state.hdmiDevices));
    openSettingsModal();
    press('Enter'); // group 0
    goToRow('hdmiNames'); press('Enter'); // the HDMI names sub-page
    goToRow(hd.id);
    var before = settingValue(hd), idx = 0;
    hd.options.forEach(function (o, j) { if (o[0] === before) idx = j; });
    var want = hd.options[(idx + 1) % hd.options.length][0];
    press('ArrowRight');
    eq('hdmi row cycles', state.hdmiDevices[hd.hdmi.id], want);
    eq('hdmi row saved', JSON.parse(localStorage.getItem('fmtv_hdmi_devices'))[hd.hdmi.id], want);
    state.hdmiDevices = keepDev; localStorage.setItem('fmtv_hdmi_devices', JSON.stringify(keepDev));
    closeSettingsModal();
    done();
  });
  steps.push(function (done) { // reset needs a second OK
    state.theme = 'day'; localStorage.setItem('fmtv_theme', 'day');
    openSettingsModal();
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings(); press('Enter');
    goToRow('moreOptions'); press('Enter');
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
  steps.push(function (done) { // four groups; every setting in exactly one place; Down reaches the last row of each; Reset keeps people; Erase wipes fmtv_*
    var seen = {}, dupes = 0;
    SETTINGS.forEach(function (d) { if (seen[d.id]) dupes++; seen[d.id] = true; });
    eq('no setting id twice', dupes, 0);
    eq('every setting is in a group', SETTINGS.filter(function (d) { return !(settingGroup(d) >= 0 && settingGroup(d) < 4); }).length, 0);
    eq('reset label', findSetting('reset').label, 'Reset settings');
    eq('about row shows the version', findSetting('about').value(), APP_VERSION);
    eq('there is no separate version row', !!findSetting('version'), false);

    openSettingsModal();
    eq('four groups in the list', modalEl().querySelectorAll('.settings-cat').length, 4);
    for (var c = 0; c < 4; c++) {
      settingsUi.zone = 'cats'; settingsUi.catFocus = c; settingsUi.cat = c; renderSettings();
      press('ArrowRight');
      var guard = 40; while (guard--) press('ArrowDown');
      var rws = settingsRowsFor(c), lastRow = modalEl().querySelector('.settings-row.sf');
      eq('group ' + c + ' Down reaches the last row', settingsUi.row === rws.length - 1 && !!lastRow && lastRow.getAttribute('data-id') === rws[rws.length - 1].id, true);
      press('Escape');
      settingsUi.cat = c; settingsUi.catFocus = c; press('ArrowRight');
      eq('group ' + c + ' has no back row', modalEl().querySelectorAll('.settings-row[data-id="back"]').length + ':' + rws.some(function (d) { return d.type === 'back'; }), '0:false');
      eq('group ' + c + ' opens on the first setting', settingsUi.row === 0 && modalEl().querySelector('.settings-row.sf').getAttribute('data-id') === rws[0].id, true);
      if (rws.length > 1) {
        press('ArrowDown');
        eq('group ' + c + ' Down from the first row', settingsUi.row === 1 && modalEl().querySelector('.settings-row.sf').getAttribute('data-id') === rws[1].id, true);
        press('ArrowUp');
        eq('group ' + c + ' Up returns to the first row', settingsUi.row === 0 && settingsUi.zone === 'rows', true);
      }
      press('ArrowUp');
      eq('group ' + c + ' Up from the first row leaves for the categories', settingsUi.zone + ':' + settingsUi.catFocus, 'cats:' + c);
    }
    eq('no note in the left column', modalEl().querySelector('#settingsNote') === null && modalEl().querySelectorAll('#settingsCats .settings-note').length, 0);
    var lastGroup = modalEl().querySelectorAll('.settings-cat')[3].getBoundingClientRect(), vr = document.getElementById('appVersion').getBoundingClientRect();
    eq('the version line sits below the last group', lastGroup.bottom <= vr.top, true);
    settingsUi.zone = 'rows'; settingsUi.catFocus = 3; settingsUi.cat = 3; settingsUi.sub = 'more'; renderSettings();
    var aboutRow = modalEl().querySelector('#settingsRows .settings-row[data-id="about"]');
    eq('About row holds the independence note', !!aboutRow && aboutRow.textContent.indexOf(t('Free My TV is an independent app, not affiliated with LG. No ads. No account. Your settings stay on this TV.')) !== -1, true);
    eq('You and this TV More page has 7 rows with About last', settingsRowsFor(3, 'more').length === 7 && settingsRowsFor(3, 'more')[6].id === 'about', true);
    eq('About row is info type (no OK action)', settingsRowsFor(3, 'more')[6].type, 'info');
    eq('About row shows the version', aboutRow.querySelector('.sr-value').textContent, APP_VERSION);
    settingsUi.sub = '';
    closeSettingsModal();

    // Reset keeps people and history
    state.theme = 'day'; localStorage.setItem('fmtv_theme', 'day');
    saveProfiles([{ id: 'p1', name: 'Noa', color: '#2a7de1', data: snapshotProfile() }, { id: 'p2', name: 'Kid', color: '#ff9f43', data: snapshotProfile() }]);
    localStorage.setItem('fmtv_launch_hist', '[{"id":"netflix","t":1}]');
    openSettingsModal();
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings(); press('Enter');
    goToRow('moreOptions'); press('Enter');
    goToRow('reset'); press('Enter'); press('Enter');
    eq('reset settings restores defaults', state.theme, 'auto');
    eq('reset keeps the people', readProfiles().length, 2);
    eq('reset keeps the history', localStorage.getItem('fmtv_launch_hist') !== null, true);
    closeSettingsModal();

    // Erase everything: two presses, every fmtv_ key gone, wizard needed on the next boot
    var saved = {}, i, k;
    for (i = 0; i < localStorage.length; i++) { k = localStorage.key(i); if (k.indexOf('fmtv_') === 0) saved[k] = localStorage.getItem(k); }
    var snapState = {}; SETTINGS.forEach(function (d) { if (d.field) snapState[d.field] = state[d.field]; });
    var keepFav = state.favorites.slice(), keepDev = JSON.parse(JSON.stringify(state.hdmiDevices)), keepLocked = state.locked;
    var realReload = window.reloadApp, reloads = 0, keysAtReload = -1;
    function fmtvKeys() { var n = 0, j, kk; for (j = 0; j < localStorage.length; j++) { kk = localStorage.key(j); if (kk && kk.indexOf('fmtv_') === 0) n++; } return n; }
    window.reloadApp = function () { reloads++; keysAtReload = fmtvKeys(); };
    state.userName = 'Noa'; localStorage.setItem('fmtv_user_name', 'Noa'); localStorage.setItem('fmtv_tmdb_key', 'abc');
    openSettingsModal();
    settingsUi.cat = 3; settingsUi.catFocus = 3; renderSettings(); press('Enter');
    goToRow('moreOptions'); press('Enter');
    goToRow('eraseAll'); press('Enter');
    eq('erase asks first', reloads + ':' + (fmtvKeys() > 0), '0:true');
    eq('erase confirm text', modalEl().querySelector('.settings-row[data-id="eraseAll"]').textContent.indexOf(t('Press OK again to erase everything')) !== -1, true);
    eq('erase confirm text is only on the erase row', modalEl().querySelector('.settings-row[data-id="reset"]').textContent.indexOf(t('Press OK again to confirm')), -1);
    press('Enter');
    eq('erase reloads once', reloads, 1);
    eq('erase leaves no fmtv_ key at reload time', keysAtReload, 0);
    eq('erase leaves no fmtv_ key', fmtvKeys(), 0);
    eq('next boot opens the wizard', wizardNeeded(), true);
    eq('erase resets the in-memory name', state.userName, '');
    window.reloadApp = realReload;
    Object.keys(saved).forEach(function (key) { localStorage.setItem(key, saved[key]); });
    SETTINGS.forEach(function (d) { if (d.field) state[d.field] = snapState[d.field]; });
    state.favorites = keepFav; state.hdmiDevices = keepDev; state.locked = keepLocked;
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile'); localStorage.removeItem('fmtv_launch_hist'); localStorage.removeItem('fmtv_tmdb_key');
    state.theme = 'auto'; localStorage.setItem('fmtv_theme', 'auto');
    closeSettingsModal();
    applyTheme(); renderAppsShelf(); updateGreeting();
    done();
  });
  steps.push(function (done) { // the idle screensaver does not start while the screen is open; hover only moves focus
    openSettingsModal();
    function move(x, y) { document.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: y, bubbles: true })); }
    function over(node) { node.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); }
    var cats = modalEl().querySelectorAll('.settings-cat');
    move(101, 201); over(cats[2]);
    eq('hover focuses without rebuilding', modalEl().querySelectorAll('.settings-cat')[2] === cats[2], true);
    eq('hover focus moved', settingsUi.catFocus, 2);
    var rowsBefore = document.getElementById('settingsRows');
    move(103, 203); over(cats[2].querySelector('.sc-name')); // a child span re-fires mouseover on the same category
    eq('same category hover does not rebuild the rows', document.getElementById('settingsRows') === rowsBefore, true);
    var row = modalEl().querySelector('#settingsRows .settings-row[data-i="1"]');
    move(640, 300); over(row);
    eq('row hover after the categories', settingsUi.zone, 'rows');
    eq('row hover ring', modalEl().querySelector('.sf') === row, true);
    eq('row hover rebuilt nothing', modalEl().querySelector('#settingsRows .settings-row[data-i="1"]') === row && modalEl().querySelectorAll('.settings-cat')[2] === cats[2], true);
    move(120, 900); over(modalEl().querySelectorAll('.settings-cat')[3]);
    eq('last group hover from the rows', settingsUi.zone + ':' + settingsUi.catFocus, 'cats:3');
    press('ArrowUp');
    eq('key moves focus', settingsUi.catFocus, 2);
    over(modalEl().querySelectorAll('.settings-cat')[1]);
    eq('mouseover without a pointer move keeps key focus', settingsUi.catFocus, 2);
    move(120, 900); over(modalEl().querySelectorAll('.settings-cat')[1]);
    eq('mousemove at the same spot is not a move', settingsUi.catFocus, 2);
    cats = modalEl().querySelectorAll('.settings-cat');
    cats[2].click();
    eq('click enters the category', settingsUi.zone, 'rows');
    eq('click selected category', settingsUi.cat, 2);
    closeSettingsModal();
    if (typeof flushSettingsNetwork === 'function') flushSettingsNetwork(); // no debounced fetch fires after the stubs are restored
    ['fetchWeather', 'fetchTrendingPicks', 'ambientRefresh'].forEach(function (n) { window[n] = uiReal[n]; });
    done();
  });

  steps.push(function (done) { // the screen always opens on the category list; hovering away drops a pending reset question
    settingsPointerLive = true;
    openSettingsModal();
    eq('opening resets the pointer flag', settingsPointerLive, false);
    function move(x, y) { document.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: y, bubbles: true })); }
    function over(node) { node.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); }
    var resetIdx = -1, rws = settingsRowsFor(3, 'more'), k;
    for (k = 0; k < rws.length; k++) if (rws[k].id === 'reset') resetIdx = k;
    settingsUi.cat = 3; settingsUi.catFocus = 3; settingsUi.zone = 'rows'; settingsUi.sub = 'more'; settingsUi.row = resetIdx;
    renderSettings();
    press('Enter');
    eq('reset asks for confirmation', settingsUi.confirmReset, 'reset');
    eq('confirmation text shown', modalEl().textContent.indexOf('Press OK again to confirm') >= 0, true);
    move(700, 400); over(modalEl().querySelector('#settingsRows .settings-row[data-i="0"]'));
    eq('hover clears confirmReset', settingsUi.confirmReset, false);
    eq('hover removes the confirmation text', modalEl().textContent.indexOf('Press OK again to confirm'), -1);
    // armed Reset must not arm-and-run Erase: a click straight on Erase only asks
    localStorage.setItem('fmtv_theme', 'day');
    erasing = false; // an earlier step ran the real erase
    settingsUi.row = resetIdx; press('Enter');
    eq('reset armed', settingsUi.confirmReset, 'reset');
    modalEl().querySelector('#settingsRows .settings-row[data-id="eraseAll"]').click();
    eq('erase only asks after Reset was armed', settingsUi.confirmReset, 'eraseAll');
    eq('nothing erased by the first press on Erase', String(erasing) + ':' + localStorage.getItem('fmtv_theme'), 'false:day');
    eq('erase text shows only on Erase', modalEl().querySelector('.settings-row[data-id="reset"]').textContent.indexOf(t('Press OK again to confirm')), -1);
    closeSettingsModal();
    done();
  });

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
    // a restore left in storage (app closed while the scene ran) is applied by the next restoreScene, as at boot
    state.theme = 'oled'; state.homePhotos = 'off';
    localStorage.setItem('fmtv_scene_restore', JSON.stringify({ theme: { from: 'auto', to: 'oled' }, homePhotos: { from: 'on', to: 'off' } }));
    restoreScene();
    eq('boot restore theme', state.theme, 'auto');
    eq('boot restore photos', state.homePhotos, 'on');
    // the user changed the theme themselves before coming back: that choice stays, the untouched field still returns
    state.theme = 'oled'; state.homePhotos = 'off';
    localStorage.setItem('fmtv_scene_restore', JSON.stringify({ theme: { from: 'auto', to: 'oled' }, homePhotos: { from: 'on', to: 'off' } }));
    setSettingValue(settingDef('theme'), 'day');
    restoreScene();
    eq('user theme kept', state.theme, 'day');
    eq('untouched field restored', state.homePhotos, 'on');
    eq('restore key gone again', localStorage.getItem('fmtv_scene_restore'), null);
    state.theme = 'auto';
    var before = calls.length;
    state.hdmiDevices = {};
    runScene('game');
    eq('game scene without a named device launches nothing', calls.length, before);
    var chips = document.querySelectorAll('#scenesRow .scene-chip');
    eq('scene chips', chips.length, SCENES.length);
    eq('scene chip in nav', mainNavItems.indexOf(chips[0]) !== -1, true);
    eq('scene chips fit in a row', chips[0].getBoundingClientRect().height, 44);
    state.scenes = 'off'; renderScenes();
    eq('scenes hidden when off', document.getElementById('scenesRow').hidden, true);
    state.scenes = 'on'; renderScenes();
    window.webOS = oldWebOS;
    done();
  });

  steps.push(function (done) { // a launch that does not happen never leaves the scene look behind
    var oldWebOS = window.webOS, keepPending = pendingLaunch, keepEdit = shelfEdit;
    function reset() { state.theme = 'auto'; state.homePhotos = 'on'; localStorage.removeItem('fmtv_scene_restore'); pendingLaunch = null; shelfEdit = false; }
    function untouched(label) {
      eq(label + ' theme', state.theme, 'auto'); eq(label + ' photos', state.homePhotos, 'on');
      eq(label + ' no restore key', localStorage.getItem('fmtv_scene_restore'), null);
    }
    pendingLaunch = null;
    reset(); window.webOS = { service: { request: function (uri, o) { o.onFailure({ errorText: 'nope' }); } } };
    runScene('movie'); untouched('failed launch (sync)');
    reset(); window.webOS = { service: { request: function (uri, o) { setTimeout(function () { o.onFailure({ errorText: 'nope' }); }, 20); } } };
    runScene('movie');
    eq('look applied while the request is open', state.theme, 'oled');
    setTimeout(function () {
      untouched('failed launch (async)');
      reset(); window.webOS = { service: { request: function () {} } };
      pendingLaunch = { timer: null };
      runScene('movie'); untouched('pending launch');
      pendingLaunch = null; shelfEdit = true;
      runScene('movie'); untouched('shelf edit');
      shelfEdit = false; window.webOS = undefined;
      runScene('movie'); untouched('no webOS');
      var sets = 0, realSet = Storage.prototype.setItem;
      window.webOS = { service: { request: function () {} } };
      Storage.prototype.setItem = function (k, v) { if (k === 'fmtv_scene_restore') throw new Error('full'); return realSet.call(this, k, v); };
      runScene('movie');
      Storage.prototype.setItem = realSet;
      untouched('restore key cannot be saved');
      reset(); window.webOS = oldWebOS; pendingLaunch = keepPending; shelfEdit = keepEdit;
      done();
    }, 150);
  });

  steps.push(function (done) { // chips follow the language and Reset
    var keepLang = state.lang, other = keepLang === 'de' ? 'fr' : 'de';
    state.lang = other; applyStaticTranslations(); renderAppsShelf();
    var first = document.querySelector('#scenesRow .scene-chip span');
    eq('chip text follows language', first && first.textContent, t('Movie night'));
    state.lang = keepLang; applyStaticTranslations(); renderAppsShelf();
    state.scenes = 'off'; renderScenes();
    eq('scenes off hides row', document.getElementById('scenesRow').hidden, true);
    resetAllSettings();
    eq('reset shows the row again', document.getElementById('scenesRow').hidden, false);
    eq('reset chips present', document.querySelectorAll('#scenesRow .scene-chip').length, SCENES.length);
    state.lang = keepLang;
    done();
  });

  steps.push(function (done) { // scenes + pick-up row + shelf + Trending all fit on a 1080p screen
    localStorage.setItem('fmtv_launch_hist', JSON.stringify({ netflix: { t: 3, n: 1 }, 'youtube.leanback.v4': { t: 2, n: 1 }, amazon: { t: 1, n: 1 } }));
    state.pickup = 'on'; state.scenes = 'on'; state.showTrending = 'on'; applyTrendingClass(); renderScenes(); renderAppsShelf();
    var pk = document.querySelector('.picks-section').getBoundingClientRect();
    eq('trending visible', pk.height > 0, true);
    eq('trending bottom inside screen (' + Math.round(pk.bottom) + ')', pk.bottom <= window.innerHeight, true);
    var sh = document.getElementById('appsGrid').getBoundingClientRect();
    eq('shelf row fits the width (' + Math.round(sh.right) + ')', sh.right <= window.innerWidth, true);
    localStorage.removeItem('fmtv_launch_hist'); renderAppsShelf();
    done();
  });

  steps.push(function (done) { // the honest privacy line sits on the home screen
    var tl = document.getElementById('trustLine'), sp = tl && tl.querySelector('span');
    eq('trust line exists', !!tl, true);
    eq('trust line text', sp ? sp.textContent : null, t('No ads. No account. Your settings stay on this TV.'));
    eq('trust line visible', !!tl && tl.getClientRects().length > 0, true);
    done();
  });

  steps.push(function (done) { // the three-step setup walks every step with the remote and saves name, look and photos
    var keepSetup = localStorage.getItem('fmtv_setup_done');
    localStorage.removeItem('fmtv_setup_done');
    var oldTheme = state.theme, oldName = state.userName, oldAmbient = state.ambient, oldFavs = state.favorites.slice();
    function key(k) { handleWizardKey({ key: k, keyCode: 0, preventDefault: function () {} }); }
    var wzq = function (sel) { return document.querySelectorAll('#wizardOverlay ' + sel); };
    function idxOf(cls) { for (var i = 0; i < wizard.items.length; i++) if (wizard.items[i].classList.contains(cls)) return i; return -1; }
    openWizard();
    eq('wizard open', wizard.open && !document.getElementById('wizardOverlay').hidden, true);
    eq('wizard has exactly 3 steps', WIZARD_STEPS.join(','), 'who,apps,look');
    eq('wizard starts on the name step', WIZARD_STEPS[wizard.step], 'who');
    eq('wizard has no left rail', document.getElementById('wizardRail'), null);
    eq('wizard has exactly 3 progress bars', wzq('.wz-bars .wz-bar').length, 3);
    eq('wizard bars are one labelled image', wzq('.wz-bars')[0].getAttribute('role') + '|' + wzq('.wz-bars')[0].getAttribute('aria-label'), 'img|' + t('Step %s of %s', 1, 3));
    var bar0 = wzq('.wz-bar')[0], bar1 = wzq('.wz-bar')[1];
    eq('wizard bar is 42x9', bar0.getBoundingClientRect().width + 'x' + bar0.getBoundingClientRect().height, '42x9');
    eq('wizard current bar is white', getComputedStyle(bar0).backgroundColor, 'rgb(255, 255, 255)');
    eq('wizard upcoming bar is dark grey', getComputedStyle(bar1).backgroundColor, 'rgb(58, 65, 78)');
    eq('wizard name column is 960px', wzq('.wz-main')[0].getBoundingClientRect().width, 960);
    eq('wizard name title', wzq('.wz-title')[0].textContent, t('Hi. What should we call you?'));
    eq('wizard name lead', wzq('.wz-lead')[0].textContent, t('Used for the greeting. You can change it later.'));
    eq('wizard city label', wzq('.wz-label')[1].textContent, t('City, for the weather'));
    eq('wizard city hint keeps the Sao Paulo fallback', wzq('.wz-hint')[0].textContent, t('Leave it empty to use São Paulo, or turn on Auto-locate by IP in Settings.'));
    eq('wizard name step footer: Skip left, Continue right', wzq('.wz-footer .wz-second')[0].textContent + '|' + wzq('.wz-footer .wz-primary')[0].textContent, t('Skip setup') + '|' + t('Continue'));
    var nameInput = document.getElementById('wzName');
    nameInput.value = 'Noa'; nameInput.dispatchEvent(new Event('input'));
    eq('wizard name saved', state.userName, 'Noa');
    nameInput.focus(); wizard.focus = 0; key('ArrowDown');
    eq('wizard Down leaves a closed-keyboard input', wizard.focus === 1 && document.activeElement !== nameInput, true);
    key('Escape');
    eq('wizard Back on step 0 does nothing', wizard.open && WIZARD_STEPS[wizard.step], 'who');
    key('ArrowDown');
    eq('wizard Down from the city reaches Continue', wizard.items[wizard.focus].classList.contains('wz-primary'), true);
    key('ArrowLeft');
    eq('wizard footer Left goes to Skip', wizard.items[wizard.focus].classList.contains('wz-second'), true);
    key('ArrowRight');
    eq('wizard footer Right goes to Continue', wizard.items[wizard.focus].classList.contains('wz-primary'), true);
    key('Enter');
    eq('wizard step apps', WIZARD_STEPS[wizard.step], 'apps');
    eq('wizard apps bars: one done, one current', wzq('.wz-bar.done').length + ':' + wzq('.wz-bar.cur').length + ':' + wzq('.wz-bars')[0].getAttribute('aria-label'), '1:1:' + t('Step %s of %s', 2, 3));
    eq('wizard apps column is 1440px', wzq('.wz-main')[0].getBoundingClientRect().width, 1440);
    eq('wizard apps title', wzq('.wz-title')[0].textContent, t('Pick your apps'));
    eq('wizard apps lead', wzq('.wz-lead')[0].textContent, t('Up to 8. They go on Home in this order.'));
    eq('wizard apps counter', wzq('.wz-count')[0].textContent, t('%s picked', state.favorites.length));
    eq('wizard apps footer', wzq('.wz-footer .wz-second')[0].textContent + '|' + wzq('.wz-footer .wz-primary')[0].textContent, t('Back') + '|' + t('Continue'));
    eq('wizard apps shows 12 logo tiles', wzq('.wz-tile').length, Math.min(12, wizardCatalog().length));
    eq('wizard tile is 156px tall', wzq('.wz-tile')[0].getBoundingClientRect().height, 156);
    eq('wizard picked tiles carry a check badge', wzq('.wz-tile.on .wz-check').length, wzq('.wz-tile.on').length);
    eq('wizard unpicked tiles are dimmed to 55%', getComputedStyle(wzq('.wz-tile:not(.on)')[0]).opacity, '0.55');
    var firstId = wizard.items[0].dataset.id, was = state.favorites.indexOf(firstId) !== -1;
    wizard.focus = 0; key('Enter');
    eq('wizard toggles an app', state.favorites.indexOf(firstId) !== -1, !was);
    eq('wizard counter follows the pick', wzq('.wz-count')[0].textContent, t('%s picked', state.favorites.length));
    wizard.focus = idxOf('wz-primary'); key('Enter');
    eq('wizard step look', WIZARD_STEPS[wizard.step], 'look');
    eq('t substitutes special characters literally', t('How should it look, %s?', "A$&B$'C$`D"), t('How should it look, %s?', 'X').split('X').join("A$&B$'C$`D"));
    eq('wizard look bars', wzq('.wz-bar.done').length + ':' + wzq('.wz-bars')[0].getAttribute('aria-label'), '2:' + t('Step %s of %s', 3, 3));
    eq('wizard look title uses the name', wzq('.wz-title')[0].textContent, t('How should it look, %s?', 'Noa'));
    eq('wizard look lead', wzq('.wz-lead')[0].textContent, t('The screen changes as you move. OK picks.'));
    eq('wizard four look cards in order', [].map.call(wzq('.wz-look'), function (c) { return c.dataset.look; }).join(','), 'auto,night,oled,day');
    eq('wizard look card names', [].map.call(wzq('.wz-look .wz-look-name'), function (c) { return c.textContent; }).join('|'), [t('Follows the sun'), t('Midnight'), t('Pure black'), t('Daylight Blue')].join('|'));
    var c0 = wzq('.wz-look')[0].getBoundingClientRect(), c3 = wzq('.wz-look')[3].getBoundingClientRect();
    eq('wizard four cards share one row', c0.top === c3.top && c3.left > c0.left, true);
    eq('wizard one thumbnail per look card', wzq('.wz-look .wz-thumb').length, WIZARD_LOOKS.length);
    eq('wizard photos switch row', wzq('.wz-toggle')[0].textContent.indexOf(t('Show photos when the TV is idle')), 0);
    eq('wizard look footer', wzq('.wz-footer .wz-second')[0].textContent + '|' + wzq('.wz-footer .wz-primary')[0].textContent, t('Back') + '|' + t('Finish'));
    eq('wizard no hint bar', wzq('.wz-hints').length, 0);
    wizard.focus = 0; key('ArrowRight');
    eq('wizard previews a look', state.theme, 'night');
    key('Enter');
    eq('wizard look confirm moves to Finish', wizard.focus, idxOf('wz-primary'));
    key('ArrowUp');
    eq('wizard Up from Finish lands on the photos switch', wizard.items[wizard.focus].classList.contains('wz-toggle'), true);
    state.ambient = 'on'; renderWizard(); wizard.focus = 4; key('Enter');
    eq('wizard photos switch writes fmtv_ambient', state.ambient + ':' + localStorage.getItem('fmtv_ambient'), 'off:off');
    key('Enter');
    eq('wizard photos switch toggles back', state.ambient + ':' + localStorage.getItem('fmtv_ambient'), 'on:on');
    wizard.focus = idxOf('wz-primary'); key('ArrowLeft');
    eq('wizard Left from Finish goes to Back', wizard.items[wizard.focus].classList.contains('wz-second'), true);
    key('Enter');
    eq('wizard Back button goes to the apps step', WIZARD_STEPS[wizard.step], 'apps');
    wizardGo(2); wizard.focus = idxOf('wz-primary'); key('Enter');
    eq('wizard Finish closes', wizard.open, false);
    eq('wizard Finish toast names the person', document.querySelector('.toast-msg').textContent, t('All set, %s', 'Noa'));
    eq('wizard remembered', localStorage.getItem('fmtv_setup_done'), '1');
    eq('wizard no longer needed', wizardNeeded(), false);
    eq('wizard Finish lands on Home', document.getElementById('wizardOverlay').hidden && !modalOpen && !picker.open, true);
    state.userName = ''; openWizard(); wizardGo(2); wizard.focus = idxOf('wz-primary'); key('Enter');
    eq('wizard Finish toast without a name', document.querySelector('.toast-msg').textContent, t('All set'));
    state.userName = 'Noa';
    openWizard(); wizard.focus = wizard.items.length - 1; key('Enter');
    eq('wizard skip closes', wizard.open, false);
    eq('wizard skip sets flag', localStorage.getItem('fmtv_setup_done'), '1');
    localStorage.removeItem('fmtv_setup_done');
    openWizard(); wizardGo(2); key('Escape');
    eq('wizard back goes one step back', WIZARD_STEPS[wizard.step], 'apps');
    key('Escape');
    eq('wizard back to first step', WIZARD_STEPS[wizard.step], 'who');
    key('Escape');
    eq('wizard Back on the first step stays open', wizard.open, true);
    closeWizard();
    localStorage.removeItem('fmtv_setup_done');
    var keepCat = state.catalog, keepFav = state.favorites.slice();
    state.catalog = keepCat.slice(0, 5); state.favorites = [state.catalog[0].id];
    openWizard(); wizardGo(1);
    eq('wizard grid count', wizard.gridCount, 5);
    eq('wizard short catalog has no Show all button', wzq('.wz-more').length, 0);
    wizard.focus = 0; key('ArrowDown');
    eq('wizard Down from the first row goes to the footer', wizard.items[wizard.focus].classList.contains('wz-primary'), true);
    wizard.focus = 0; key('Enter');
    eq('wizard last app guard keeps it', state.favorites.length, 1);
    eq('wizard last app toast', document.querySelector('.toast-msg').textContent, t('Keep at least one app on the shelf.'));
    state.catalog = keepCat; state.favorites = keepCat.slice(0, 8).map(function (a) { return a.id; });
    if (keepCat.length > 9) {
      wizardGo(1);
      eq('wizard shelf apps come first', wizard.items[0].dataset.id, state.favorites[0]);
      var nonFav = -1; for (var q = 0; q < wizard.appIds.length; q++) if (state.favorites.indexOf(wizard.appIds[q]) === -1) { nonFav = q; break; }
      wizard.focus = nonFav; key('Enter');
      eq('wizard full shelf unchanged', state.favorites.length, 8);
      eq('wizard full shelf toast', document.querySelector('.toast-msg').textContent, t('Max 8 apps on shelf'));
    }
    eq('toast above wizard', parseInt(getComputedStyle(document.querySelector('.toast-msg')).zIndex, 10) > parseInt(getComputedStyle(document.getElementById('wizardOverlay')).zIndex, 10), true);
    wizardGo(2); wizard.focus = idxOf('wz-toggle'); var themeBefore = state.theme; key('ArrowUp');
    eq('wizard Up from the switch lands on a look card', !!wizard.items[wizard.focus].dataset.look, true);
    eq('wizard Up to the cards does not switch theme', state.theme, themeBefore);
    wizard.focus = idxOf('wz-primary'); key('ArrowUp'); key('ArrowUp');
    eq('wizard Up from Finish through the switch does not switch theme', state.theme, themeBefore);
    eq('wizard background follows theme var', getComputedStyle(document.getElementById('wizardOverlay')).backgroundImage.indexOf('radial-gradient') !== -1, true);
    state.catalog = keepCat; state.favorites = keepFav; renderAppsShelf();
    closeWizard(); localStorage.removeItem('fmtv_setup_done');
    var runDef = settingDef('runSetup');
    eq('run setup row', !!runDef && runDef.type === 'run', true);
    state.theme = oldTheme; state.userName = oldName; state.ambient = oldAmbient; state.favorites = oldFavs;
    try { localStorage.setItem('fmtv_theme', oldTheme); localStorage.setItem('fmtv_user_name', oldName); localStorage.setItem('fmtv_ambient', oldAmbient); localStorage.setItem('fmtv_favorites', JSON.stringify(oldFavs)); } catch (e) {}
    applyTheme(); renderAppsShelf(); updateGreeting();
    if (keepSetup === null) localStorage.removeItem('fmtv_setup_done'); else localStorage.setItem('fmtv_setup_done', keepSetup);
    done();
  });

  steps.push(function (done) { // wizard polish: the saved look is marked, Continue stays on screen with 45 apps, this app and duplicates are not listed
    var keepSetup = localStorage.getItem('fmtv_setup_done');
    var oldTheme = state.theme, keepCat = state.catalog, keepFav = state.favorites.slice();
    function key(k) { handleWizardKey({ key: k, keyCode: 0, preventDefault: function () {} }); }
    var wzq = function (sel) { return document.querySelectorAll('#wizardOverlay ' + sel); };
    state.theme = 'oled'; applyTheme();
    openWizard(); wizardGo(2);
    eq('look: one selected badge', wzq('.wz-look .wz-sel').length, 1);
    eq('look: badge sits on the saved theme card', wzq('.wz-look.on')[0].dataset.look + ':' + wzq('.wz-look .wz-sel')[0].parentNode.dataset.look, 'oled:oled');
    eq('look: badge label', wzq('.wz-sel')[0].textContent, t('Selected'));
    var selBox = wzq('.wz-sel')[0].getBoundingClientRect(), selTop = document.elementFromPoint(selBox.left + selBox.width / 2, selBox.top + selBox.height / 2);
    eq('look: the Selected badge is drawn above the thumbnail', !!selTop && !!selTop.closest && !!selTop.closest('.wz-sel'), true);
    eq('look: selected card keeps a blue outline', getComputedStyle(wzq('.wz-look.on')[0]).borderTopColor, 'rgb(77, 163, 255)');
    eq('look: initial focus is the saved card', wizard.items[wizard.focus].dataset.look, 'oled');
    key('ArrowRight');
    eq('look: moving previews the next card', state.theme, 'day');
    eq('look: the badge stays on the saved card', wzq('.wz-look .wz-sel')[0].parentNode.dataset.look, 'oled');
    eq('look: preview is not saved', localStorage.getItem('fmtv_theme') === 'day', false);
    key('Escape');
    eq('look: leaving without choosing restores the saved theme', state.theme, 'oled');
    wizardGo(2); key('ArrowLeft'); key('ArrowLeft');
    eq('look: previewing again', state.theme !== 'oled', true);
    closeWizard();
    eq('look: closing the wizard restores the saved theme', state.theme, 'oled');
    openWizard(); wizardGo(2); key('ArrowRight'); key('Enter');
    eq('look: OK saves the card', state.theme + ':' + localStorage.getItem('fmtv_theme'), 'day:day');
    eq('look: badge moved to the picked card', wzq('.wz-look .wz-sel')[0].parentNode.dataset.look, 'day');
    eq('look: still exactly one badge', wzq('.wz-sel').length, 1);
    closeWizard();
    state.theme = oldTheme; try { localStorage.setItem('fmtv_theme', oldTheme); } catch (e) {} applyTheme();

    var many = [], i;
    for (i = 0; i < 45; i++) many.push({ id: 'app.n' + i, title: 'Application ' + i, tag: 'Installed App', desc: '', color: '#0a84ff', badge: 'APP', bg: '#123' });
    many.push({ id: 'app.n3-copy', title: 'application 3', tag: 'Installed App', desc: '', color: '#0a84ff', badge: 'APP', bg: '#123' });
    many.push({ id: 'app.n4', title: 'Same id again', tag: 'Installed App', desc: '', color: '#0a84ff', badge: 'APP', bg: '#123' });
    many.push({ id: 'org.webos.freemytv', title: 'Free My TV', tag: 'Installed App', desc: '', color: '#0a84ff', badge: 'FMT', bg: '#123' });
    many.push({ id: 'other.id', title: 'free my tv', tag: 'Installed App', desc: '', color: '#0a84ff', badge: 'FMT', bg: '#123' });
    state.catalog = many; state.favorites = ['app.n0'];
    openWizard(); wizardGo(1);
    function tileTitles() { return [].map.call(wzq('.wz-tile'), function (n) { return n.dataset.title.toLowerCase(); }); }
    eq('apps: 12 tiles before Show all', wzq('.wz-tile').length, 12);
    eq('apps: shelf app comes first', wizard.items[0].dataset.id, 'app.n0');
    eq('apps: Show all button names the count', wzq('.wz-more')[0].textContent, t('Show all %s apps and inputs', 45));
    var cont = wzq('.wz-footer .wz-primary')[0].getBoundingClientRect();
    eq('apps: Continue stays on screen', cont.bottom <= 1080 && cont.top >= 0, true);
    wizard.focus = 11; key('ArrowDown');
    eq('apps: Down from the last row reaches Show all', wizard.items[wizard.focus].classList.contains('wz-more'), true);
    key('ArrowDown');
    eq('apps: Down from Show all reaches Continue', wizard.items[wizard.focus].classList.contains('wz-primary'), true);
    wizard.focus = 12; key('Enter');
    eq('apps: Show all lists the 45 de-duplicated apps', wzq('.wz-tile').length, 45);
    eq('apps: Show all button is gone', wzq('.wz-more').length, 0);
    eq('apps: focus lands on the first new tile', wizard.focus, 12);
    eq('apps: no duplicate names', tileTitles().filter(function (n, k, all) { return all.indexOf(n) !== k; }).length, 0);
    eq('apps: this app is not listed', tileTitles().indexOf('free my tv'), -1);
    var scr = document.getElementById('wzScroll');
    eq('apps: expanded list scrolls in the same scroller', scr.scrollHeight > scr.clientHeight && scr.contains(wzq('.wz-tile')[44]), true);
    cont = wzq('.wz-footer .wz-primary')[0].getBoundingClientRect();
    eq('apps: Continue still on screen with 45 apps', cont.bottom <= 1080 && cont.top >= 0, true);
    wizard.focus = 40; paintWizardFocus();
    var tileRect = wizard.items[40].getBoundingClientRect(), scrRect = scr.getBoundingClientRect();
    eq('apps: focused tile is scrolled into view', tileRect.top >= scrRect.top - 1 && tileRect.bottom <= scrRect.bottom + 1, true);
    wizard.focus = 40; key('ArrowDown');
    eq('apps: Down from the last rows reaches Continue', wizard.items[wizard.focus].classList.contains('wz-primary'), true);
    key('ArrowUp');
    eq('apps: Up from Continue returns to a tile', wizard.focus < 45, true);
    wizard.focus = 3; key('ArrowDown'); key('ArrowUp');
    eq('apps: Down then Up by rows returns', wizard.focus, 3);
    wizard.focus = 2; key('ArrowRight');
    eq('apps: Right moves one tile', wizard.focus, 3);
    closeWizard();
    state.catalog = [{ id: 'keep.me', title: 'Keep Me', tag: 'x', desc: '', color: '#000', badge: 'K', bg: '#000' }];
    addLaunchPoints([{ id: 'org.webos.freemytv', title: 'Free My TV' }, { id: 'x.self', title: 'FREE MY TV' }, { id: 'dup.keep', title: 'keep me' }, { id: 'new.one', title: 'New One' }, { id: 'new.two', title: 'new one' }]);
    eq('discovery: skips this app and duplicate names', state.catalog.map(function (c) { return c.id; }).join(','), 'keep.me,new.one');
    state.catalog = keepCat; state.favorites = keepFav; renderAppsShelf();
    if (keepSetup === null) localStorage.removeItem('fmtv_setup_done'); else localStorage.setItem('fmtv_setup_done', keepSetup);
    done();
  });

  steps.push(function (done) { // profiles swap shelf, look and name; a locked profile hides the settings buttons
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    var base = snapshotProfile();
    var kid = snapshotProfile(); kid.userName = 'Kid'; kid.theme = 'day'; kid.favorites = ['youtube.leanback.v4']; kid.locked = true;
    function two() { saveProfiles([{ id: 'p1', name: 'Noa', color: '#2a7de1', data: base }, { id: 'p2', name: 'Kid', color: '#ff9f43', data: kid }]); }
    two();
    eq('profiles read', readProfiles().length, 2);
    localStorage.setItem('fmtv_profiles', '{nope');
    eq('profiles garbage tolerated', readProfiles().length, 0);
    localStorage.setItem('fmtv_profiles', '{"a":1}');
    eq('profiles non-array tolerated', readProfiles().length, 0);
    two();
    localStorage.setItem('fmtv_active_profile', 'p1');
    switchProfile('p2');
    eq('profile switched name', state.userName, 'Kid');
    eq('profile switched shelf', state.favorites.join(','), 'youtube.leanback.v4');
    eq('locked hides Customize', document.getElementById('customizeBtn').offsetParent, null);
    eq('locked leaves nav', mainNavItems.indexOf(document.getElementById('customizeBtn')), -1);
    eq('pill shows for two people', document.getElementById('profileBtn').offsetParent !== null, true);
    eq('pill is in the nav even when locked', mainNavItems.indexOf(document.getElementById('profileBtn')) !== -1, true);
    eq('pill names the active person', document.getElementById('profileBtn').getAttribute('aria-label') === 'Kid' && document.getElementById('profileBtn').textContent.replace(/\s+/g, '') === 'K', true);
    eq('active profile saved', localStorage.getItem('fmtv_active_profile'), 'p2');
    switchProfile('p1');
    eq('profile switched back', state.userName, base.userName);
    eq('unlocked shows Customize', document.getElementById('customizeBtn').offsetParent !== null, true);
    eq('picker needs two profiles', shouldAskWho(), true);
    state.askWho = 'off';
    eq('picker can be turned off', shouldAskWho(), false);
    state.askWho = 'on';
    saveProfiles([{ id: 'p1', name: 'Noa', color: '#2a7de1', data: base }]);
    eq('picker hidden for one profile', shouldAskWho(), false);
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    applyProfile(base);
    eq('pill hidden without profiles', document.getElementById('profileBtn').offsetParent, null);
    done();
  });

  steps.push(function (done) { // Add person: own wizard, Back cancels without a trace, Skip keeps defaults, Kids locks, Remove asks twice
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    var keepSetup = localStorage.getItem('fmtv_setup_done');
    var orig = snapshotProfile(); // the harness state, put back at the end
    var base = snapshotProfile();
    base.userName = 'Noa'; base.theme = 'night'; base.city = 'Lisbon'; base.favorites = ['netflix', 'youtube.leanback.v4'];
    applyProfile(base);
    var before = JSON.stringify(snapshotProfile());
    function key(k) { handleWizardKey({ key: k, keyCode: 0, preventDefault: function () {} }); }
    function itemByText(text) { for (var i = 0; i < wizard.items.length; i++) if (wizard.items[i].textContent.indexOf(text) === 0) return i; return -1; }
    // cancel
    startAddPerson();
    eq('add opens the wizard', wizard.open && !document.getElementById('wizardOverlay').hidden, true);
    eq('add starts on who', WIZARD_STEPS[wizard.step], 'who');
    eq('add creates two people', readProfiles().length, 2);
    eq('add first person keeps their name', readProfiles()[0].name, 'Noa');
    eq('add new person starts from the default shelf', state.favorites.join(','), DEFAULT_FAVORITES.join(','));
    eq('add new person has no name', state.userName, '');
    eq('add new person has the default look', state.theme, settingDef('theme').def);
    eq('add new person has no city', state.city, '');
    eq('add new person is active', activeProfileId() !== readProfiles()[0].id, true);
    eq('add has a kids toggle', itemByText(t('Kids profile (hides settings)')) !== -1, true);
    eq('add keeps the same three bars', document.querySelectorAll('#wizardOverlay .wz-bars .wz-bar').length + ':' + document.querySelector('#wizardOverlay .wz-bars').getAttribute('aria-label'), '3:' + t('Step %s of %s', 1, 3));
    eq('add title asks who this is', document.querySelector('#wizardOverlay .wz-title').textContent, t('Who is this?'));
    eq('add keeps the city field and its hint', !!document.getElementById('wzCity') && document.querySelectorAll('#wizardOverlay .wz-hint').length, 1);
    eq('add pill shows', document.getElementById('profileBtn').offsetParent !== null, true);
    key('Escape');
    eq('add Back on who closes', wizard.open, false);
    eq('add cancel leaves no profiles', readProfiles().length, 0);
    eq('add cancel leaves no active key', localStorage.getItem('fmtv_active_profile'), null);
    eq('add cancel restores everything', JSON.stringify(snapshotProfile()), before);
    eq('add cancel hides the pill', document.getElementById('profileBtn').offsetParent, null);
    // Back from a later step goes back first
    startAddPerson(); wizardGo(1); key('Escape');
    eq('add Back from apps returns to who', wizard.open && WIZARD_STEPS[wizard.step], 'who');
    key('Escape');
    eq('add then cancel again', readProfiles().length, 0);
    // Skip keeps the person with defaults and a numbered name
    startAddPerson();
    wizard.focus = itemByText(t('Skip setup'));
    key('Enter');
    eq('add skip closes', wizard.open, false);
    eq('add skip keeps two people', readProfiles().length, 2);
    eq('add skip names the person', readProfiles()[1].name, t('Person') + ' 2');
    eq('add skip leaves the new person active', activeProfileId(), readProfiles()[1].id);
    eq('add skip is not locked', state.locked, false);
    eq('remove row is offered', settingsRowsFor(3, 'people').some(function (d) { return d.id === 'removePerson'; }), true);
    // remove asks twice, then returns to the first person exactly
    openSettingsModal();
    settingsUi.zone = 'rows'; settingsUi.cat = 3; settingsUi.sub = 'people';
    var rows = settingsRowsFor(3, 'people');
    settingsUi.row = rows.map(function (d) { return d.id; }).indexOf('removePerson');
    eq('remove defaults to another person', removeTargetProfile().id !== activeProfileId(), true);
    cyclePick(1);
    eq('remove can pick the active person', removeTargetProfile().id, activeProfileId());
    activateRow(settingDef('removePerson'));
    eq('remove asks first', settingsUi.confirmReset, 'removePerson');
    eq('remove confirm names the person', document.querySelector('#settingsRows .settings-row[data-id="removePerson"] .sr-value').textContent, t('Press OK again to remove %s', removeTargetProfile().name));
    eq('remove asks and keeps the people', readProfiles().length, 2);
    activateRow(settingDef('removePerson'));
    eq('remove deletes the person', readProfiles().length, 0);
    eq('remove returns to the first person exactly', JSON.stringify(snapshotProfile()), before);
    eq('remove leaves no active key', localStorage.getItem('fmtv_active_profile'), null);
    eq('remove hides the pill', document.getElementById('profileBtn').offsetParent, null);
    eq('remove row hidden again', settingsRowsFor(3, 'people').some(function (d) { return d.id === 'removePerson'; }), false);
    closeSettingsModal();
    // Kids profile: typed name, lock, no remove row, settings buttons hidden
    startAddPerson();
    var nameInput = document.getElementById('wzName');
    nameInput.value = 'Kid'; nameInput.dispatchEvent(new Event('input'));
    wizard.focus = itemByText(t('Kids profile (hides settings)')); key('Enter');
    eq('kids toggle locks', state.locked, true);
    eq('kids toggle hides Customize', document.getElementById('customizeBtn').offsetParent, null);
    wizard.focus = itemByText(t('Skip setup')); key('Enter');
    eq('kids profile kept', readProfiles().length, 2);
    eq('kids profile named', readProfiles()[1].name, 'Kid');
    eq('kids profile saved locked', readProfiles()[1].data.locked, true);
    eq('kids profile has no remove row', settingsRowsFor(3, 'people').some(function (d) { return d.id === 'removePerson'; }), false);
    eq('kids profile can still switch', settingsRowsFor(3, 'people').some(function (d) { return d.id === 'switchPerson'; }), true);
    // the picker: keys route to it, Right/Enter pick, Back keeps the person
    function press(k) { document.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true })); }
    openPicker();
    eq('picker open', picker.open && !document.getElementById('profileOverlay').hidden, true);
    eq('picker lists everyone', document.querySelectorAll('#profileCards .profile-card').length, 2);
    eq('picker starts on the active person', picker.focus, 1);
    eq('picker is above the home screen', parseInt(getComputedStyle(document.getElementById('profileOverlay')).zIndex, 10) >= 2500, true);
    eq('picker focus ring', getComputedStyle(document.querySelector('.profile-card.focused')).outlineStyle, 'solid');
    press('ArrowLeft');
    eq('picker Left moves', picker.focus, 0);
    press('Escape');
    eq('picker Back closes', picker.open, false);
    eq('picker Back keeps the person', state.userName, 'Kid');
    openPicker(); press('ArrowLeft'); press('Enter');
    eq('picker OK switches', state.userName, 'Noa');
    eq('picker OK closes', picker.open, false);
    eq('picker OK restores the first person exactly', JSON.stringify(snapshotProfile()), before);
    eq('picker OK unlocks', document.getElementById('customizeBtn').offsetParent !== null, true);
    // an unlocked person removes the locked Kids person with the pick row
    var kidId = readProfiles()[1].id;
    eq('remove offers the locked person first', removeTargets()[0].id, kidId);
    openSettingsModal();
    settingsUi.zone = 'rows'; settingsUi.cat = 3; settingsUi.sub = 'people';
    settingsUi.row = settingsRowsFor(3, 'people').map(function (d) { return d.id; }).indexOf('removePerson');
    eq('remove targets the locked person by default', removeTargetProfile().id, kidId);
    activateRow(settingDef('removePerson'));
    eq('remove confirm names the Kids person', document.querySelector('#settingsRows .settings-row[data-id="removePerson"] .sr-value').textContent, t('Press OK again to remove %s', 'Kid'));
    activateRow(settingDef('removePerson'));
    eq('remove deletes the locked person', readProfiles().length, 0);
    eq('remove keeps the active person untouched', JSON.stringify(snapshotProfile()), before);
    eq('remove leaves no profile list', localStorage.getItem('fmtv_profiles'), null);
    closeSettingsModal();
    // the row is hidden while a locked person is active
    saveProfiles([{ id: 'p1', name: 'Noa', color: '#2a7de1', data: JSON.parse(before) }, { id: 'p2', name: 'Kid', color: '#ff9f43', data: JSON.parse(before) }]);
    localStorage.setItem('fmtv_active_profile', 'p1');
    eq('remove row offered to an unlocked person', settingsRowsFor(3, 'people').some(function (d) { return d.id === 'removePerson'; }), true);
    state.locked = true;
    eq('remove row hidden while locked', settingsRowsFor(3, 'people').some(function (d) { return d.id === 'removePerson'; }), false);
    state.locked = false;
    // three people: remove the active one, then a non-active one
    function personData(name, locked) { var d = JSON.parse(before); d.userName = name; d.locked = !!locked; return d; }
    saveProfiles([{ id: 'a', name: 'A', color: '#2a7de1', data: personData('A') }, { id: 'b', name: 'B', color: '#1fa05a', data: personData('B') }, { id: 'c', name: 'C', color: '#ff9f43', data: personData('C', true) }]);
    localStorage.setItem('fmtv_active_profile', 'a');
    applyProfile(personData('A'));
    removeProfileById('b');
    eq('non-active removal keeps the active person', activeProfileId() + state.userName, 'aA');
    eq('non-active removal leaves two', readProfiles().length, 2);
    saveProfiles([{ id: 'a', name: 'A', color: '#2a7de1', data: personData('A') }, { id: 'b', name: 'B', color: '#1fa05a', data: personData('B') }, { id: 'c', name: 'C', color: '#ff9f43', data: personData('C', true) }]);
    removeProfileById('a');
    eq('active removal makes the first remaining active', activeProfileId(), 'b');
    eq('active removal applies their settings', state.userName, 'B');
    eq('active removal leaves two', readProfiles().length, 2);
    removeProfileById('c');
    eq('removing down to one drops the list', localStorage.getItem('fmtv_profiles'), null);
    // removing the owner while a locked person is left must not leave the TV locked
    saveProfiles([{ id: 'a', name: 'A', color: '#2a7de1', data: personData('A') }, { id: 'c', name: 'C', color: '#ff9f43', data: personData('C', true) }]);
    localStorage.setItem('fmtv_active_profile', 'a');
    applyProfile(personData('A'));
    removeActiveProfile();
    eq('removing the owner leaves the other person', state.userName, 'C');
    eq('a lone person is never locked', state.locked, false);
    eq('a lone person gets Customize back', document.getElementById('customizeBtn').offsetParent !== null, true);
    eq('a lone person leaves no profile list', localStorage.getItem('fmtv_profiles'), null);
    // the last unlocked person cannot be removed, or nobody could reach Customize or Erase
    saveProfiles([{ id: 'a', name: 'A', color: '#2a7de1', data: personData('A') }, { id: 'b', name: 'B', color: '#1fa05a', data: personData('B', true) }, { id: 'c', name: 'C', color: '#ff9f43', data: personData('C', true) }]);
    localStorage.setItem('fmtv_active_profile', 'a');
    applyProfile(personData('A'));
    eq('last grown-up is not a remove target', removeTargets().map(function (x) { return x.id; }).join(','), 'b,c');
    removeProfileById('a');
    eq('last grown-up cannot be removed', readProfiles().length, 3);
    eq('last grown-up stays active', activeProfileId(), 'a');
    removeProfileById('b');
    eq('a locked person can be removed', readProfiles().map(function (x) { return x.id; }).join(','), 'a,c');
    // moving to a locked person closes Customize
    openSettingsModal();
    eq('customize open before the switch', modalOpen, true);
    switchProfile('c');
    eq('switching to a locked person closes Customize', modalOpen, false);
    eq('and hides the modal', document.getElementById('settingsModal').classList.contains('active'), false);
    switchProfile('a');
    // the screensaver covers the picker and the wizard, and handing back keeps them as they were
    var ssOverlay = document.getElementById('screensaverOverlay');
    openPicker(); picker.focus = 1;
    enterScreensaver();
    eq('screensaver over the picker', screensaverOn && ssOverlay.classList.contains('active') && picker.open, true);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true, cancelable: true }));
    eq('first key only ends the screensaver', screensaverOn, false);
    eq('picker still open with its focus', picker.open && picker.focus, 1);
    eq('picker overlay still shown', document.getElementById('profileOverlay').hidden, false);
    closePicker();
    openWizard(); wizardGo(1); wizard.focus = 0;
    var wzStep = wizard.step;
    enterScreensaver();
    eq('screensaver over the wizard', screensaverOn && wizard.open, true);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }));
    eq('wizard key ended the screensaver only', screensaverOn, false);
    eq('wizard keeps step and focus', wizard.open && wizard.step === wzStep && wizard.focus, 0);
    closeWizard();
    // clean up
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    applyProfile(orig);
    eq('cleanup hides the pill', document.getElementById('profileBtn').offsetParent, null);
    if (keepSetup === null) localStorage.removeItem('fmtv_setup_done'); else localStorage.setItem('fmtv_setup_done', keepSetup);
    done();
  });

  steps.push(function (done) { // boot with profiles, an unknown active id, hdmi isolation, numeric lat/lon
    var orig = snapshotProfile(), keepBoot = wizardAtBoot;
    function person(name, locked, extra) { var d = JSON.parse(JSON.stringify(orig)); d.userName = name; d.locked = !!locked; for (var k in extra) d[k] = extra[k]; return d; }
    function two(da, db) { saveProfiles([{ id: 'a', name: 'A', color: '#2a7de1', data: da }, { id: 'b', name: 'B', color: '#1fa05a', data: db }]); }
    two(person('A'), person('B', true));
    localStorage.setItem('fmtv_active_profile', 'zzz');
    wizardAtBoot = true; bootProfiles();
    eq('boot never opens the picker over the wizard', picker.open, false);
    eq('boot repairs an unknown active id', activeProfileId(), 'a');
    eq('boot lock follows an unlocked person', state.locked, false);
    localStorage.setItem('fmtv_active_profile', 'b');
    wizardAtBoot = false; bootProfiles();
    eq('boot opens the picker', picker.open, true);
    eq('boot lock follows the locked person', state.locked, true);
    eq('boot keeps a valid active id', activeProfileId(), 'b');
    closePicker();
    localStorage.removeItem('fmtv_active_profile');
    bootProfiles(); closePicker();
    eq('boot repairs a missing active id', activeProfileId(), 'a');
    eq('boot lock after repair', state.locked, false);
    // an unknown active id saves nobody
    two(person('A'), person('B'));
    localStorage.setItem('fmtv_active_profile', 'zzz');
    state.userName = 'Stranger';
    saveCurrentProfile();
    eq('unknown active id does not overwrite the first person', readProfiles()[0].data.userName, 'A');
    eq('unknown active id does not rename anybody', (syncProfileName(), readProfiles()[0].name), 'A');
    // hdmi devices are not shared between people
    two(person('A', false, { hdmiDevices: { 'com.webos.app.hdmi1': 'ps5' } }), person('B', false, { hdmiDevices: {} }));
    localStorage.setItem('fmtv_active_profile', 'a');
    applyProfile(person('A', false, { hdmiDevices: { 'com.webos.app.hdmi1': 'ps5' } }));
    switchProfile('b');
    eq('hdmi devices follow the person', JSON.stringify(state.hdmiDevices), '{}');
    state.hdmiDevices['com.webos.app.hdmi2'] = 'xbox';
    switchProfile('a');
    eq('hdmi devices come back', JSON.stringify(state.hdmiDevices), JSON.stringify({ 'com.webos.app.hdmi1': 'ps5' }));
    eq('hdmi devices of the other person were saved', JSON.stringify(readProfiles()[1].data.hdmiDevices), JSON.stringify({ 'com.webos.app.hdmi2': 'xbox' }));
    // lat and lon stay numbers through a profile round trip
    two(person('A', false, { lat: 38.72, lon: -9.14 }), person('B'));
    localStorage.setItem('fmtv_active_profile', 'b');
    switchProfile('a');
    eq('lat is a number', typeof state.lat + state.lat, 'number38.72');
    eq('lon is a number', typeof state.lon + state.lon, 'number-9.14');
    eq('lat is stored', localStorage.getItem('fmtv_lat'), '38.72');
    switchProfile('b');
    switchProfile('a');
    eq('lat survives a round trip', snapshotProfile().lat, 38.72);
    // reset follows into the profile name
    localStorage.setItem('fmtv_active_profile', 'a');
    state.userName = 'Zed'; syncProfileName();
    eq('profile name follows the typed name', readProfiles()[0].name, 'Zed');
    var keepSet = {}; SETTINGS.forEach(function (d) { if (d.field) keepSet[d.field] = state[d.field]; });
    var keepFavs = state.favorites.slice(), keepHdmi = JSON.stringify(state.hdmiDevices);
    resetAllSettings();
    eq('reset renames the stored person', readProfiles()[0].name, t('Person') + ' 1');
    SETTINGS.forEach(function (d) { if (d.field) { state[d.field] = keepSet[d.field]; try { localStorage.setItem(d.store, keepSet[d.field]); } catch (e) {} } });
    state.favorites = keepFavs; state.hdmiDevices = JSON.parse(keepHdmi); applyStaticTranslations();
    // clean up
    wizardAtBoot = keepBoot;
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    applyProfile(orig);
    done();
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
    try { steps[i](function () { setTimeout(function () { run(i + 1); }, 100); }); }
    catch (e) { fails.push('step ' + i + ' threw: ' + String(e && e.stack || e).slice(0, 400)); write(); }
  })(0);
}, 2000);
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
    html = html.replace("<head>", f'<head>{ERROR_HOOK}<script>localStorage.setItem("fmtv_lang","{lang}");localStorage.setItem("fmtv_setup_done","1")</script>', 1)
    html = html.replace("</body>", f"<script>{PROBE}</script><script>{SCENARIO}</script></body>")
    page = os.path.join(workdir, f"app_{lang}.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    shutil.copytree(os.path.join(REPO_DIR, "app", "assets"), os.path.join(workdir, "assets"), dirs_exist_ok=True)
    res = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--window-size=1920,1080",
         "--virtual-time-budget=60000", f"--user-data-dir={os.path.join(workdir, 'profile_' + lang)}",
         "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=120)
    m = re.search(r'<pre id="__result">(.*?)</pre>', res.stdout, re.S)
    if not m:
        return None, res.stderr[-400:]
    import html as htmllib
    result = json.loads(htmllib.unescape(m.group(1)))
    m2 = re.search(r'<pre id="__scenario">(.*?)</pre>', res.stdout, re.S)
    result["scenario"] = json.loads(htmllib.unescape(m2.group(1))) if m2 else None
    return result, ""


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
                failures.append(f"{lang}: expected Settings gear label '{expected}', got '{result['text']}'")
            if lang == "en":  # dictionary checks are language independent; report once
                if result["keyDiff"]:
                    failures.append(f"translation keys differ in: {result['keyDiff']}")
                if result["missing"]:
                    failures.append(f"strings without translations: {result['missing']}")
                if result["ambient"]:
                    failures.append(f"ambient checks: {result['ambient']}")
                if result["scenario"] is None:
                    failures.append("ambient scenario did not finish")
                elif result["scenario"]["fails"]:
                    failures.append(f"ambient scenario: {result['scenario']['fails']}")
            print(f"[*] {lang}: ok" if not any(x.startswith(lang + ":") for x in failures) else f"[!] {lang}: failed")
    for f in failures:
        print(f"[!] {f}")
    print("[+] browser tests passed" if not failures else f"[!] {len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
