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
    localStorage.setItem('fmtv_launch_hist', JSON.stringify({ netflix: 5, youtube: { t: 'x' }, ok: { t: 1, n: 1 } }));
    eq('hist malformed dropped', Object.keys(readLaunchHist()).join(','), 'ok');
    localStorage.removeItem('fmtv_launch_hist');
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
  if (!Object.prototype.hasOwnProperty.call(I18N.pt, 'Keep LG Screensaver Away')) out.ambient.push('no translation: Keep LG Screensaver Away');
  eq('state home photos', state.homePhotos, 'off');
  if (!document.getElementById('homePhotos')) out.ambient.push('missing #homePhotos');
  if (!Object.prototype.hasOwnProperty.call(I18N.pt, 'Photos on Home Screen')) out.ambient.push('no translation: Photos on Home Screen');
  if (typeof SETTINGS !== 'object' || !SETTINGS.length) {
    out.ambient.push('SETTINGS missing');
  } else {
    SETTINGS.forEach(function (d) {
      if (d.field && d.id !== 'lang' && state[d.field] !== d.def) out.ambient.push('default mismatch: ' + d.id + ' state=' + JSON.stringify(state[d.field]) + ' def=' + JSON.stringify(d.def));
      if (d.type === 'choice' && !d.options) out.ambient.push('no options: ' + d.id);
    });
  }
  ['Screensaver Starts After', '1 minute', '3 minutes', '5 minutes', '10 minutes', '30 minutes',
   'Ambient Photo Screensaver', 'Off', 'Photo Duration', '30 seconds', '90 seconds', 'Photo Motion',
   'Ken Burns (zoom & drift)', 'Drift only', 'None', 'Unsplash Access Key (Optional)',
   'Optional for photo screensaver', 'Photo by %s on Unsplash',
   'Shelf & Inputs', 'Look & Feel', 'Weather & Location', 'Photos & Screensaver', 'Accounts & Keys', 'Close', 'Categories',
   'Shelf apps', 'OK to edit', 'OK to open', 'Not set', 'Saved', 'Reset to defaults', 'Press OK again to confirm',
   'Up / Down: move', 'Left / Right: change value', 'OK: select or edit', 'Back: close', 'Changes apply instantly',
   'Up / Down: move one row', 'OK: add or remove', 'Back: return', 'Enter: save', 'Back: cancel', '%s of 8 selected',
   'Keep at least one app on the shelf.', 'Previous value', 'Next value',
   'Dimmed, slowly moving photos behind the dashboard', 'Photos behind the clock when the TV is idle',
   'Plays a hidden video so LG does not cover ours', 'For the photos. Stored on this TV only',
   'Optional, for weekly trending movies and shows', 'Back: categories', 'OK or Right: open'].forEach(function (k) {
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
  steps.push(function (done) { // the TV Settings button launches the LG Settings app
    var btn = document.getElementById('tvSettingsBtn'), got = null, oldWebOS = window.webOS;
    eq('tv settings button', !!btn, true);
    window.webOS = { service: { request: function (uri, o) { got = { uri: uri, o: o }; } } };
    btn.click();
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
      eq('engine cat0 hdmi follow', cat0.length, 1 + hd.length);

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
    eq('fr key hint feminine', I18N.fr['For the photos. Stored on this TV only'].indexOf('Stockée uniquement sur cette TV') !== -1, true);
    eq('es shelf apps says estante', I18N.es['Shelf apps'].indexOf('estante') !== -1 && I18N.es['Shelf apps'].indexOf('estantería') === -1, true);
    eq('es keep one says estante', I18N.es['Keep at least one app on the shelf.'].indexOf('estante') !== -1 && I18N.es['Keep at least one app on the shelf.'].indexOf('estantería') === -1, true);
    eq('de not set', I18N.de['Not set'], 'Nicht festgelegt');
    eq('de confirm', I18N.de['Press OK again to confirm'], 'Zum Bestätigen erneut OK drücken');
    press('ArrowLeft');
    eq('left in categories is a no-op', settingsUi.zone + ':' + settingsUi.catFocus, 'cats:0');
    eq('cats hints', document.getElementById('settingsHints').textContent.indexOf(t('OK or Right: open')) !== -1, true);
    var catNode = modalEl().querySelectorAll('.settings-cat')[1];
    press('ArrowDown');
    eq('category keys do not rebuild the category list', modalEl().querySelectorAll('.settings-cat')[1] === catNode, true);
    eq('category keys still show that category', settingsUi.cat === 1 && modalEl().querySelector('#settingsRows').getAttribute('data-cat') === '1', true);
    press('ArrowUp');
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
    eq('rows hints', document.getElementById('settingsHints').textContent.indexOf(t('Back: categories')) !== -1, true);
    modalEl().querySelector('.settings-row[data-id="idleMins"] .sr-arrow[data-dir="1"]').click();
    eq('arrow click changes once', state.idleMins, '5');
    modalEl().querySelector('.settings-row[data-id="idleMins"] .sr-value').click();
    eq('clicking the value acts like OK', state.idleMins, '10');
    setSettingValue(findSetting('idleMins'), '3');
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
    eq('Categories row focuses its category', settingsUi.catFocus, 3);
    press('ArrowDown'); press('ArrowDown');
    eq('arrows reach Close', settingsUi.catFocus, 5);
    press('Enter');
    eq('Close item closes', modalOpen, false);
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
  steps.push(function (done) { // background renders (shelf, picks) do not steal focus from an open editor
    var keepCity = state.city;
    openSettingsModal();
    settingsUi.cat = 2; settingsUi.catFocus = 2; renderSettings(); press('Enter'); // first setting: City
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
  steps.push(function (done) { // the greeting shows the name and the part of the day
    state.userName = 'Noa'; updateGreeting();
    eq('greeting title', document.getElementById('greetingTitle').textContent, greetingText(new Date().getHours(), 'Noa'));
    eq('greeting eyebrow set', document.getElementById('greetingEyebrow').textContent.length > 0, true);
    state.userName = ''; updateGreeting();
    eq('greeting no name', document.getElementById('greetingTitle').textContent, t(greetingKey(new Date().getHours())));
    done();
  });
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
  steps.push(function (done) { // an app added to the catalog later (discovered on the TV) shows in the pick-up row
    localStorage.removeItem('fmtv_launch_hist'); state.pickup = 'on';
    var fake = { id: 'fake.app', title: 'Fake', tag: 'Streaming', desc: 'Watch 4K videos, live streams, music, and coding radio.', color: '#ff0000', badge: 'F', bg: '#000' };
    state.catalog.push(fake);
    recordLaunch('fake.app', Date.now());
    renderAppsShelf();
    eq('pickup follows catalog', !!document.querySelector('#pickupRow .pickup-card[data-id="fake.app"]'), true);
    state.catalog.pop();
    localStorage.removeItem('fmtv_launch_hist');
    renderAppsShelf();
    eq('pickup cleared again', document.getElementById('pickupSection').hidden, true);
    done();
  });
  steps.push(function (done) { // D-pad focus draws a white ring on every kind of focusable element
    var ids = ['customizeBtn', 'tvSettingsBtn', 'weatherWidget', 'tabMovies'];
    var els = ids.map(function (id) { return document.getElementById(id); });
    var tile = document.querySelector('.app-tile'), card = document.querySelector('.pick-card');
    if (tile) els.push(tile);
    if (card) els.push(card);
    localStorage.removeItem('fmtv_launch_hist'); state.pickup = 'on';
    recordLaunch('netflix', Date.now()); renderPickup();
    var pc = document.querySelector('#pickupRow .pickup-card');
    if (pc) els.push(pc);
    els.forEach(function (el, i) {
      el.classList.add('focused');
      var cs = getComputedStyle(el);
      eq('ring style ' + i, cs.outlineStyle, 'solid');
      eq('ring width ' + i, cs.outlineWidth, '3px');
      el.classList.remove('focused');
    });
    localStorage.removeItem('fmtv_launch_hist'); renderPickup();
    done();
  });
  steps.push(function (done) { // an HDMI row changes its device with Right and saves at once
    var hd = hdmiSettings()[0];
    if (!hd) { fails.push('no HDMI row in the test catalog'); done(); return; }
    var keepDev = JSON.parse(JSON.stringify(state.hdmiDevices));
    openSettingsModal();
    press('Enter'); // category 0
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
    move(120, 900); over(modalEl().querySelector('.settings-close'));
    eq('Close hover from the rows', settingsUi.zone + ':' + settingsUi.catFocus, 'cats:5');
    press('ArrowUp');
    eq('key moves focus', settingsUi.catFocus, 4);
    over(modalEl().querySelectorAll('.settings-cat')[1]);
    eq('mouseover without a pointer move keeps key focus', settingsUi.catFocus, 4);
    move(120, 900); over(modalEl().querySelectorAll('.settings-cat')[1]);
    eq('mousemove at the same spot is not a move', settingsUi.catFocus, 4);
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
    var resetIdx = -1, rws = settingsRowsFor(4), k;
    for (k = 0; k < rws.length; k++) if (rws[k].id === 'reset') resetIdx = k;
    settingsUi.cat = 4; settingsUi.catFocus = 4; settingsUi.zone = 'rows'; settingsUi.row = resetIdx;
    renderSettings();
    press('Enter');
    eq('reset asks for confirmation', settingsUi.confirmReset, true);
    eq('confirmation text shown', modalEl().textContent.indexOf('Press OK again to confirm') >= 0, true);
    move(700, 400); over(modalEl().querySelector('#settingsRows .settings-row[data-i="1"]'));
    eq('hover clears confirmReset', settingsUi.confirmReset, false);
    eq('hover removes the confirmation text', modalEl().textContent.indexOf('Press OK again to confirm'), -1);
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
    state.pickup = 'on'; state.scenes = 'on'; state.showTrending = 'on'; applyTrendingClass(); renderScenes(); renderPickup();
    var pk = document.querySelector('.picks-section').getBoundingClientRect();
    eq('trending visible', pk.height > 0, true);
    eq('trending bottom inside screen (' + Math.round(pk.bottom) + ')', pk.bottom <= window.innerHeight, true);
    localStorage.removeItem('fmtv_launch_hist'); renderPickup();
    done();
  });

  steps.push(function (done) { // the honest privacy line sits on the home screen
    var tl = document.getElementById('trustLine'), sp = tl && tl.querySelector('span');
    eq('trust line exists', !!tl, true);
    eq('trust line text', sp ? sp.textContent : null, t('No ads. No account. Your settings stay on this TV.'));
    eq('trust line visible', !!tl && tl.getClientRects().length > 0, true);
    done();
  });

  steps.push(function (done) { // the setup wizard walks every step with the remote and saves name, look and photos
    var keepSetup = localStorage.getItem('fmtv_setup_done');
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
    nameInput.focus(); wizard.focus = 0; key('ArrowDown');
    eq('wizard Down leaves a closed-keyboard input', wizard.focus === 1 && document.activeElement !== nameInput, true);
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
    openWizard(); wizard.focus = 1; key('Enter');
    eq('wizard skip closes', wizard.open, false);
    eq('wizard skip sets flag', localStorage.getItem('fmtv_setup_done'), '1');
    localStorage.removeItem('fmtv_setup_done');
    openWizard(); wizardGo(3); key('Escape');
    eq('wizard back goes one step back', WIZARD_STEPS[wizard.step], 'apps');
    key('Escape'); key('Escape');
    eq('wizard back to first step', WIZARD_STEPS[wizard.step], 'welcome');
    key('Escape');
    eq('wizard closed by back on first', wizard.open, false);
    localStorage.removeItem('fmtv_setup_done');
    var keepCat = state.catalog, keepFav = state.favorites.slice();
    state.catalog = keepCat.slice(0, 6); state.favorites = [state.catalog[0].id];
    openWizard(); wizardGo(2);
    eq('wizard grid count', wizard.gridCount, 6);
    wizard.focus = 1; key('ArrowDown');
    eq('wizard down inside a short last row', wizard.focus, 5);
    wizard.focus = 2; key('ArrowDown');
    eq('wizard down lands on the button after the grid', wizard.focus, 6);
    wizard.focus = 0; key('Enter');
    eq('wizard last app guard keeps it', state.favorites.length, 1);
    eq('wizard last app toast', document.querySelector('.toast-msg').textContent, t('Keep at least one app on the shelf.'));
    state.catalog = keepCat; state.favorites = keepCat.slice(0, 8).map(function (a) { return a.id; });
    if (keepCat.length > 8) {
      wizardGo(2); wizard.focus = 8; key('Enter');
      eq('wizard full shelf unchanged', state.favorites.length, 8);
      eq('wizard full shelf toast', document.querySelector('.toast-msg').textContent, t('Max 8 apps on shelf'));
    }
    eq('toast above wizard', parseInt(getComputedStyle(document.querySelector('.toast-msg')).zIndex, 10) > parseInt(getComputedStyle(document.getElementById('wizardOverlay')).zIndex, 10), true);
    wizardGo(3); wizard.focus = WIZARD_LOOKS.length; var themeBefore = state.theme; key('ArrowUp');
    eq('wizard Up from Continue does not switch theme', state.theme, themeBefore);
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
    eq('locked hides TV Settings', document.getElementById('tvSettingsBtn').offsetParent, null);
    eq('locked leaves nav', mainNavItems.indexOf(document.getElementById('customizeBtn')), -1);
    eq('pill shows for two people', document.getElementById('profileBtn').offsetParent !== null, true);
    eq('pill is in the nav even when locked', mainNavItems.indexOf(document.getElementById('profileBtn')) !== -1, true);
    eq('pill names the active person', document.getElementById('profileBtn').textContent.indexOf('Kid') !== -1, true);
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
    eq('add hides the welcome row', document.querySelectorAll('#wizardRail .wz-rail-row').length, 4);
    eq('add pill shows', document.getElementById('profileBtn').offsetParent !== null, true);
    key('Escape');
    eq('add Back on who closes', wizard.open, false);
    eq('add cancel leaves no profiles', readProfiles().length, 0);
    eq('add cancel leaves no active key', localStorage.getItem('fmtv_active_profile'), null);
    eq('add cancel restores everything', JSON.stringify(snapshotProfile()), before);
    eq('add cancel hides the pill', document.getElementById('profileBtn').offsetParent, null);
    // Back from a later step goes back first
    startAddPerson(); wizardGo(2); key('Escape');
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
    eq('remove row is offered', settingsRowsFor(1).some(function (d) { return d.id === 'removePerson'; }), true);
    // remove asks twice, then returns to the first person exactly
    openSettingsModal();
    settingsUi.zone = 'rows'; settingsUi.cat = 1;
    var rows = settingsRowsFor(1);
    settingsUi.row = rows.map(function (d) { return d.id; }).indexOf('removePerson');
    activateRow(settingDef('removePerson'));
    eq('remove asks first', settingsUi.confirmReset, true);
    eq('remove asks and keeps the people', readProfiles().length, 2);
    activateRow(settingDef('removePerson'));
    eq('remove deletes the person', readProfiles().length, 0);
    eq('remove returns to the first person exactly', JSON.stringify(snapshotProfile()), before);
    eq('remove leaves no active key', localStorage.getItem('fmtv_active_profile'), null);
    eq('remove hides the pill', document.getElementById('profileBtn').offsetParent, null);
    eq('remove row hidden again', settingsRowsFor(1).some(function (d) { return d.id === 'removePerson'; }), false);
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
    eq('kids profile hides TV Settings', document.getElementById('tvSettingsBtn').offsetParent, null);
    eq('kids profile has no remove row', settingsRowsFor(1).some(function (d) { return d.id === 'removePerson'; }), false);
    eq('kids profile can still switch', settingsRowsFor(1).some(function (d) { return d.id === 'switchPerson'; }), true);
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
    // removing the owner while a locked person is left must not leave the TV locked
    removeActiveProfile();
    eq('removing the owner leaves the other person', state.userName, 'Kid');
    eq('a lone person is never locked', state.locked, false);
    eq('a lone person gets Customize back', document.getElementById('customizeBtn').offsetParent !== null, true);
    eq('a lone person leaves no profile list', localStorage.getItem('fmtv_profiles'), null);
    // clean up
    localStorage.removeItem('fmtv_profiles'); localStorage.removeItem('fmtv_active_profile');
    applyProfile(JSON.parse(before));
    eq('cleanup hides the pill', document.getElementById('profileBtn').offsetParent, null);
    if (keepSetup === null) localStorage.removeItem('fmtv_setup_done'); else localStorage.setItem('fmtv_setup_done', keepSetup);
    done();
  });

  (function run(i) {
    if (i >= steps.length) { write(); return; }
    steps[i](function () { setTimeout(function () { run(i + 1); }, 100); });
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
         "--virtual-time-budget=25000", f"--user-data-dir={os.path.join(workdir, 'profile_' + lang)}",
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
                failures.append(f"{lang}: expected Customize button '{expected}', got '{result['text']}'")
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
