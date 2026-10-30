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
  eq('state home photos', state.homePhotos, 'off');
  if (!document.getElementById('cfgHomePhotos')) out.ambient.push('missing #cfgHomePhotos');
  if (!document.getElementById('homePhotos')) out.ambient.push('missing #homePhotos');
  if (!Object.prototype.hasOwnProperty.call(I18N.pt, 'Photos on Home Screen')) out.ambient.push('no translation: Photos on Home Screen');
  var keyField = document.getElementById('cfgUnsplashKey');
  eq('unsplash key field masked', keyField && keyField.type, 'password');
  ['Screensaver Starts After', '1 minute', '3 minutes', '5 minutes', '10 minutes', '30 minutes',
   'Ambient Photo Screensaver', 'Off', 'Photo Duration', '30 seconds', '90 seconds', 'Photo Motion',
   'Ken Burns (zoom & drift)', 'Drift only', 'None', 'Unsplash Access Key (Optional)',
   'Optional for photo screensaver', 'Photo by %s on Unsplash'].forEach(function (k) {
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
    html = html.replace("<head>", f'<head>{ERROR_HOOK}<script>localStorage.setItem("fmtv_lang","{lang}")</script>', 1)
    html = html.replace("</body>", f"<script>{PROBE}</script><script>{SCENARIO}</script></body>")
    page = os.path.join(workdir, f"app_{lang}.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    shutil.copytree(os.path.join(REPO_DIR, "app", "assets"), os.path.join(workdir, "assets"), dirs_exist_ok=True)
    res = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--window-size=1920,1080",
         "--virtual-time-budget=15000", f"--user-data-dir={os.path.join(workdir, 'profile_' + lang)}",
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
