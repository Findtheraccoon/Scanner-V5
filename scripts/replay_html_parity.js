#!/usr/bin/env node
/**
 * Replay parity harness — JS standalone para validar scanner_v5_standalone.html
 * vs el motor V5 backend (replay_canonical_parity.py).
 *
 * Flujo:
 *   1. Carga el HTML standalone, extrae el <script>, lo evalúa en un VM
 *      context con stubs DOM-mínimos. Esto da acceso a FIXTURE, METRICS,
 *      analyzeAll, calcInd, detect, layeredScore, resolveBand, etc.
 *      sin duplicar código (cualquier cambio al HTML se propaga
 *      automáticamente al harness).
 *   2. Reproduce el loop del replay Python: itera qqq_1min.json,
 *      construye velas 15m + 1h con CandleBuilder JS (port literal del
 *      Python), slicing daily sin look-ahead, invoca el motor JS por
 *      cada cierre 15m.
 *   3. Persiste cada output a JSON: (sim_datetime, sim_date, score,
 *      conf, dir, signal, blocked, price). Mismo schema que la SQLite
 *      del replay Python para facilitar el diff.
 *
 * Uso:
 *   node scripts/replay_html_parity.js [--end-date YYYY-MM-DD] [--out PATH]
 *
 * Output default: /tmp/replay_html_parity.json
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// ─────────────────────────────────────────────────────────────────
// CLI args (matchea defaults del replay Python).
// ─────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
function getArg(name, def) {
  const idx = args.indexOf(name);
  return idx >= 0 && args[idx + 1] ? args[idx + 1] : def;
}
const END_DATE = getArg('--end-date', '2026-04-14');
const OUT_PATH = getArg('--out', '/tmp/replay_html_parity.json');

const REPO = path.resolve(__dirname, '..');
const HTML_PATH = path.join(REPO, 'scanner_v5_standalone.html');
const DATA_DIR = path.join(REPO, 'docs/specs/Observatory/Current');

// Mismos warmup mins que el replay Python (engine constants).
const MIN_15M = 50;
const MIN_1H = 80;
const MIN_DAILY = 210;

// ─────────────────────────────────────────────────────────────────
// Carga del HTML + extracción del <script> + ejecución en VM.
// ─────────────────────────────────────────────────────────────────
function loadEngineFromHtml(htmlPath) {
  const html = fs.readFileSync(htmlPath, 'utf-8');
  const m = html.match(/<script>([\s\S]+?)<\/script>/);
  if (!m) throw new Error('no <script> block in ' + htmlPath);

  // Stubs DOM-mínimos: el script top-level usa $('etT').textContent y
  // setInterval(updET). Ambos toleran fallos silenciosos vía try/catch.
  const stubEl = new Proxy({}, {
    get: (_, prop) => {
      if (prop === 'classList') return { add: () => {}, remove: () => {} };
      if (prop === 'style') return new Proxy({}, { get: () => '', set: () => true });
      if (prop === 'querySelector') return () => stubEl;
      if (prop === 'appendChild') return () => {};
      if (prop === 'innerHTML' || prop === 'textContent' || prop === 'value' || prop === 'className') return '';
      if (typeof prop === 'string' && prop.startsWith('on')) return null;
      return '';
    },
    set: () => true,
  });

  const ctx = {
    console,
    setInterval: () => 0,
    clearInterval: () => {},
    setTimeout: (fn, ms) => 0,
    clearTimeout: () => {},
    document: {
      getElementById: () => stubEl,
      querySelector: () => stubEl,
      createElement: () => stubEl,
      addEventListener: () => {},
    },
    window: {},
    navigator: { clipboard: { writeText: () => Promise.resolve() } },
    fetch: () => Promise.reject(new Error('fetch disabled in replay')),
    Date: Date,
    Math: Math,
    Object: Object,
    Array: Array,
    JSON: JSON,
    Promise: Promise,
    parseInt: parseInt,
    parseFloat: parseFloat,
    Number: Number,
    String: String,
    Boolean: Boolean,
    Map: Map,
    Set: Set,
    Symbol: Symbol,
    Error: Error,
    isNaN: isNaN,
    isFinite: isFinite,
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  // Trailer: expone las refs que necesitamos al ctx. const/let no se vuelven
  // propiedades automáticamente (solo var top-level + function declarations).
  const trailer = `
;globalThis.__engine = {
  FIXTURE: FIXTURE,
  METRICS: METRICS,
  BENCH: BENCH,
  analyzeAll: analyzeAll,
  setWL: function(v) { WL = v; },
  getWL: function() { return WL; },
};
`;
  vm.runInContext(m[1] + trailer, ctx, { filename: htmlPath });
  return ctx.__engine;
}

// ─────────────────────────────────────────────────────────────────
// CandleBuilder JS — port literal del replay_canonical_parity.py:CandleBuilder.
// Reset al cambio de día (gotcha #16). Bucket 15m = (minute // 15) * 15.
// Bucket 1h = hour. dt = dt de la primera 1min del bucket.
// ─────────────────────────────────────────────────────────────────
function parseTime(dt) {
  const date = dt.slice(0, 10);
  const hour = parseInt(dt.slice(11, 13), 10);
  const minute = parseInt(dt.slice(14, 16), 10);
  return [date, hour, minute];
}

class CandleBuilder {
  constructor(max15 = 300, max1h = 200) {
    this.currentDate = null;
    this.candles15m = [];
    this.candles1h = [];
    this.building15m = null;
    this.building1h = null;
    this.bucket15m = null;
    this.bucket1h = null;
    this.max15 = max15;
    this.max1h = max1h;
  }
  resetDay() {
    this.building15m = null;
    this.building1h = null;
    this.bucket15m = null;
    this.bucket1h = null;
  }
  mergeInto(target, c) {
    if (target === null) {
      return { o: c.o, h: c.h, l: c.l, c: c.c, v: c.v, dt: c.dt };
    }
    target.h = Math.max(target.h, c.h);
    target.l = Math.min(target.l, c.l);
    target.c = c.c;
    target.v += c.v;
    return target;
  }
  add(c) {
    const [date, hour, minute] = parseTime(c.dt);
    const result = { newDay: false, completed15m: null, completed1h: null };
    if (date !== this.currentDate) {
      if (this.currentDate !== null) result.newDay = true;
      this.currentDate = date;
      this.resetDay();
    }
    const b15 = Math.floor(minute / 15) * 15;
    if (this.bucket15m !== null && b15 !== this.bucket15m) {
      if (this.building15m !== null) {
        result.completed15m = this.building15m;
        this.candles15m.push(this.building15m);
        if (this.candles15m.length > this.max15) {
          this.candles15m = this.candles15m.slice(-this.max15);
        }
      }
      this.building15m = null;
    }
    this.bucket15m = b15;
    this.building15m = this.mergeInto(this.building15m, c);
    const b1h = hour;
    if (this.bucket1h !== null && b1h !== this.bucket1h) {
      if (this.building1h !== null) {
        result.completed1h = this.building1h;
        this.candles1h.push(this.building1h);
        if (this.candles1h.length > this.max1h) {
          this.candles1h = this.candles1h.slice(-this.max1h);
        }
      }
      this.building1h = null;
    }
    this.bucket1h = b1h;
    this.building1h = this.mergeInto(this.building1h, c);
    return result;
  }
  get15m() {
    return this.building15m ? this.candles15m.concat([this.building15m]) : this.candles15m.slice();
  }
  get1h() {
    return this.building1h ? this.candles1h.concat([this.building1h]) : this.candles1h.slice();
  }
}

// ─────────────────────────────────────────────────────────────────
// Main.
// ─────────────────────────────────────────────────────────────────
function main() {
  console.log(`Loading engine from ${HTML_PATH}…`);
  const eng = loadEngineFromHtml(HTML_PATH);

  if (typeof eng.analyzeAll !== 'function') {
    throw new Error('analyzeAll not found in engine context');
  }
  console.log(`  FIXTURE: ${eng.FIXTURE.fixture_id} v${eng.FIXTURE.fixture_version}`);
  console.log(`  bands: ${eng.FIXTURE.score_bands.map(b => b.label).join(' · ')}`);

  console.log('\nLoading datasets…');
  const t0 = Date.now();
  const qqq1m = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'qqq_1min.json'), 'utf-8'));
  const qqqDaily = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'qqq_daily.json'), 'utf-8'));
  const spyDaily = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'spy_daily.json'), 'utf-8'));
  console.log(`  qqq_1m   : ${qqq1m.length.toLocaleString()}`);
  console.log(`  qqq_daily: ${qqqDaily.length.toLocaleString()}`);
  console.log(`  spy_daily: ${spyDaily.length.toLocaleString()}`);
  console.log(`  load time: ${((Date.now() - t0) / 1000).toFixed(1)}s`);

  // Hack: monkey-patch WL del HTML para que solo procesemos QQQ con bench SPY.
  // El HTML por default tiene 6 tickers; el harness corre 1 por scan.
  eng.setWL([{ t: 'QQQ', n: 'Nasdaq 100 ETF', s: 'TECH' }]);

  console.log(`\nReplay loop · end_date=${END_DATE}`);
  const builder = new CandleBuilder();
  const results = [];
  let scanCount = 0;
  let warmupDone = false;
  const tStart = Date.now();

  for (let i = 0; i < qqq1m.length; i++) {
    const c = qqq1m[i];
    const simDate = c.dt.slice(0, 10);
    if (simDate > END_DATE) break;

    const r = builder.add(c);
    if (r.completed15m === null) continue;

    const cM = builder.get15m();
    const cH = builder.get1h();
    if (cM.length < MIN_15M || cH.length < MIN_1H) continue;

    if (!warmupDone) {
      warmupDone = true;
      console.log(`  warmup done at ${c.dt} (${cM.length} x15m, ${cH.length} x1h)`);
    }

    const cD = qqqDaily.filter(d => d.dt <= simDate);
    const spyD = spyDaily.filter(d => d.dt <= simDate);
    if (cD.length < MIN_DAILY) continue;

    // analyzeAll itera WL (= [QQQ]). raw = {D, H, M} con dict por ticker.
    const raw = {
      D: { QQQ: cD, SPY: spyD },
      H: { QQQ: cH },
      M: { QQQ: cM },
    };
    let R;
    try {
      R = eng.analyzeAll(raw);
    } catch (e) {
      console.log(`  [ERR] ${c.dt}: ${e.message}`);
      continue;
    }
    const d = R.QQQ;
    if (!d || d.error) continue;

    scanCount++;
    const s = d.scoring;
    const blocked = s.blocked ? 1 : 0;
    const isSig = (s.signal === 'SETUP' || s.signal === 'REVISAR') ? 1 : 0;
    results.push({
      sim_datetime: c.dt,
      sim_date: simDate,
      score: s.score,
      conf: s.conf,
      dir: s.dir || '',
      signal: isSig,
      blocked: blocked,
      price: d.ind?.price ?? 0,
    });

    if (scanCount % 200 === 0) {
      const elapsed = (Date.now() - tStart) / 1000;
      const pct = ((i + 1) / qqq1m.length * 100).toFixed(1);
      console.log(`  [${(i + 1).toLocaleString()}/${qqq1m.length.toLocaleString()} · ${pct}%] ${c.dt} · scans=${scanCount.toLocaleString()} · ${elapsed.toFixed(1)}s`);
    }
  }

  const elapsed = (Date.now() - tStart) / 1000;
  console.log(`\nDONE · scans=${scanCount.toLocaleString()} · elapsed=${elapsed.toFixed(1)}s`);
  console.log(`Saving ${results.length} rows to ${OUT_PATH}…`);
  fs.writeFileSync(OUT_PATH, JSON.stringify(results, null, 0));
  console.log('Done.');

  // Distribución por banda — sanity check pre-diff.
  const bands = {};
  for (const r of results) {
    if (r.blocked) continue;
    bands[r.conf] = (bands[r.conf] || 0) + 1;
  }
  console.log('\nDistribución por banda (no bloqueadas):');
  for (const b of ['S+', 'S', 'A+', 'A', 'B', 'REVISAR', '—']) {
    if (bands[b] !== undefined) console.log(`  ${b.padEnd(8)} ${bands[b].toLocaleString()}`);
  }
}

main();
