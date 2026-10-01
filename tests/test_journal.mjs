/* Frontend integration test for the accumulating session journal.
 *
 * Loads the real app.js in a VM against a DOM stub and the real backend, then
 * drives the learner flow and asserts what the journal accumulates — in
 * particular that nothing is ever replaced.
 *
 * Run: node tests/test_journal.mjs
 */

import { readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const APP = resolve(ROOT, 'frontend/app.js');
const BASE = 'http://localhost:8124';

const failures = [];
let checks = 0;

function check(label, cond, detail = '') {
  checks++;
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? `   [${detail}]` : ''}`);
  if (!cond) failures.push(label);
}

/* ── DOM stub ─────────────────────────────────────────────────────
 * Enough of the DOM for app.js: element creation with attributes,
 * className/textContent, an append-only child list, and event
 * dispatch. The child list is what the assertions inspect — it is the
 * journal itself.
 * ──────────────────────────────────────────────────────────────── */

function makeClassList() {
  const set = new Set();
  return {
    add: (...c) => c.forEach((x) => set.add(x)),
    remove: (...c) => c.forEach((x) => set.delete(x)),
    contains: (c) => set.has(c),
    toggle: (c, on) => (on ? set.add(c) : set.delete(c)),
    _set: set,
  };
}

function makeEl(tag = 'div') {
  const el = {
    tagName: tag.toUpperCase(),
    children: [],
    attributes: {},
    _text: '',
    className: '',
    dataset: {},
    style: {},
    hidden: false,
    value: '',
    disabled: false,
    classList: makeClassList(),
    _handlers: {},

    get textContent() {
      if (this._text) return this._text;
      return this.children.map((c) => c.textContent).join(' ');
    },
    set textContent(v) {
      this._text = v;
      this.children = [];
    },
    get id() { return this.attributes.id || ''; },
    set id(v) { this.attributes.id = v; },

    append(...n) { this.children.push(...n); },
    appendChild(n) { this.children.push(n); return n; },
    addEventListener(t, fn) { (this._handlers[t] ||= []).push(fn); },
    setAttribute(k, v) { this.attributes[k] = v; },
    getAttribute(k) { return this.attributes[k] ?? null; },
    scrollIntoView() {},
    focus() {},
    querySelector(sel) { return findOne(this, sel); },

    dispatch(type, event = {}) {
      (this._handlers[type] || []).forEach((fn) => fn({ preventDefault() {}, ...event }));
    },
  };
  return el;
}

function walk(node, out = []) {
  out.push(node);
  node.children.forEach((c) => walk(c, out));
  return out;
}

function findOne(root, sel) {
  const [tag, cls] = sel.split('.');
  return walk(root).find(
    (n) => (!tag || n.tagName === tag.toUpperCase()) && (!cls || n.className.includes(cls))
  ) || null;
}

function makeDocument() {
  const ids = ['log', 'topic-heading', 'topic-goal', 'subtopic', 'domain',
               'rv-transition', 'rv-solo', 'rv-pedagogy', 'rv-previous', 'rv-attempt',
               'rv-case', 'rv-level', 'rv-met', 'rv-interventions', 'rv-pool',
               'research', 'response-input', 'btn-submit'];
  const registry = {};
  ids.forEach((id) => { registry[id] = makeEl('div'); registry[id].id = id; });
  return {
    getElementById: (id) => (registry[id] ||= (() => { const e = makeEl('div'); e.id = id; return e; })()),
    createElement: (tag) => makeEl(tag),
    querySelector: (sel) => findOne(documentStub.getElementById('log'), sel),
    querySelectorAll: () => [],
  };
}

/* ── Load app.js into a sandbox ────────────────────────────────────── */

async function loadApp() {
  const vm = await import('node:vm');
  const documentStub = makeDocument();
  const calls = [];

  const fetchStub = async (url, opts) => {
    calls.push({ url, method: opts?.method || 'GET' });
    let body;
    if (opts?.method === 'POST') body = JSON.parse(opts.body);
    const res = await realFetch(BASE + url, opts);
    const json = await res.json();
    return { ok: res.ok, status: res.status, json: async () => json };
  };

  const source = readFileSync(APP, 'utf8');
  const context = {
    document: documentStub,
    fetch: fetchStub,
    console,
    setTimeout,
    clearTimeout,
    URLSearchParams,
    JSON,
    Promise,
    Object,
    Array,
    String,
    Number,
    Math,
    Error,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'app.js' });
  return { document: documentStub, log: documentStub.getElementById('log'), calls, context };
}

const realFetch = globalThis.fetch;

/* ── Journal assertions ────────────────────────────────────────────── */

const kinds = (log) => log.children.map((c) => c.dataset.kind);
const ofKind = (log, kind) => log.children.filter((c) => c.dataset.kind === kind);
const textOf = (log) => log.textContent;
const hasClass = (node, cls) => walk(node).some((n) => n.className.includes(cls));
const ordinal = (node) =>
  (walk(node).find((n) => n.className.includes('entry__ordinal')) || {}).textContent || '';

async function settle(ms = 900) { await sleep(ms); }

let PROC = null;

function startServer() {
  PROC = spawn('python3', ['backend/server.py'], {
    cwd: ROOT,
    env: { ...process.env, TUTOR_PORT: '8124' },
    stdio: 'ignore',
  });
  return new Promise((res, rej) => {
    let tries = 0;
    const poll = async () => {
      tries++;
      try { await realFetch(BASE + '/api/session'); res(); }
      catch { if (tries > 60) rej(new Error('no server')); else setTimeout(poll, 250); }
    };
    poll();
  });
}

async function submit(log, text) {
  const form = walk(log).find((n) => n.tagName === 'FORM');
  const input = walk(log).find((n) => n.tagName === 'TEXTAREA');
  input.value = text;
  form.dispatch('submit');
  await settle();
}

async function main() {
  await startServer();
  const WEAK = 'The king should just wait and see what happens.';
  const STRONG = 'The king should send spies to gather intelligence, then hold danda (force) in reserve while pursuing sandhi (conciliation).';

  const { log, document: doc } = await loadApp();
  await settle(1400);

  console.log('\n[1] First attempt');
  check('journal exists', !!log);
  check('teaching is appended before any question',
        kinds(log)[0] === 'teaching', kinds(log).join(','));
  check('a question follows the teaching', kinds(log)[1] === 'checkpoint', kinds(log).join(','));

  const teaching0 = ofKind(log, 'teaching')[0];
  check('the approach is shown as a quiet line, not a heading',
        hasClass(teaching0, 'entry__approach'));
  // Attempts are numbered from 1 (REV1 §6), and the count restarts on a new
  // topic, so the numbering is per-topic rather than per-session.
  check('attempts are numbered from 1',
        ordinal(teaching0) === 'Attempt 1', ordinal(teaching0));
  const questionText = ofKind(log, 'checkpoint')[0].textContent;
  check('the question is rendered from the API', questionText.length > 40, questionText.slice(0, 60));

  console.log('\n[2] A failed attempt is kept in the journal');
  await submit(log, WEAK);
  check('a response review is appended', ofKind(log, 'review').length === 1, kinds(log).join(','));
  check('the learner\'s own words are echoed back',
        ofKind(log, 'review')[0].textContent.includes(WEAK.slice(0, 30)));
  check('the review does not name a SOLO level',
        !/prestructural|unistructural|multistructural|relational|extended abstract/i
          .test(ofKind(log, 'review')[0].textContent));
  check('a hand-off to the next attempt is appended', ofKind(log, 'next').length === 1);
  check('a second teaching turn is appended below the review',
        kinds(log).indexOf('teaching', 1) > kinds(log).indexOf('review'),
        kinds(log).join(','));
  check('the second teaching turn is labelled as an attempt',
        hasClass(ofKind(log, 'teaching')[1], 'entry__ordinal'),
        ordinal(ofKind(log, 'teaching')[1]));
  check('a second checkpoint is appended', ofKind(log, 'checkpoint').length === 2);
  check('the FIRST checkpoint is still in the journal', textOf(log).includes(questionText.slice(0, 40)));
  check('the first teaching turn is still in the journal', ofKind(log, 'teaching').length === 2);

  console.log('\n[3] The learner can scroll back');
  check('every earlier entry is still present', log.children.length === 6, kinds(log).join(','));

  console.log('\n[4] A pass advances without discarding history');
  await submit(log, STRONG);
  check('a third review is appended', ofKind(log, 'review').length === 2);
  check('the new topic is announced', ofKind(log, 'teaching')[2].textContent.includes('New topic'),
        ofKind(log, 'teaching')[2].children.map((c) => c.textContent).join(' | ').slice(0, 70));
  check('the previous attempts are all still present',
        ofKind(log, 'teaching').length === 3 && ofKind(log, 'review').length === 2 &&
        ofKind(log, 'checkpoint').length === 3, kinds(log).join(','));
  check('the topic heading now shows the new goal',
        doc.getElementById('topic-heading').textContent.length > 10,
        doc.getElementById('topic-heading').textContent.slice(0, 50));

  console.log('\n[5] Exhausting every approach intervenes instead of restarting');
  for (let i = 0; i < 4; i++) await submit(log, WEAK);

  check('a tutor intervention is appended', ofKind(log, 'intervention').length >= 1,
        kinds(log).join(','));
  const inter = ofKind(log, 'intervention')[0];
  if (inter) {
    const t = inter.textContent;
    check('the intervention has a plain-language headline',
          /approach this differently/i.test(t), t.slice(0, 60));
    check('the intervention includes a worked example', /worked example/i.test(t));
    check('the intervention is not styled as an error',
          !inter.className.includes('error'));
  }
  check('the session was not restarted — earlier entries survive',
        ofKind(log, 'teaching').length >= 4 && ofKind(log, 'review').length >= 4,
        `${ofKind(log, 'teaching').length} teaching / ${ofKind(log, 'review').length} review`);
  check('the original question from attempt 1 is still readable',
        textOf(log).includes(questionText.slice(0, 40)));
  check('no error entry was produced', ofKind(log, 'error').length === 0,
        ofKind(log, 'error').map((e) => e.textContent).join(' | ').slice(0, 80));

  console.log('\n[6] Reloading mid-session (the reported bug)');
  // The server keeps the session across page loads, so a reload starts with an
  // exhausted approach pool. A fresh page must still get a usable step.
  {
    const fresh = await loadApp();
    await settle(1400);
    const freshLog = fresh.log;
    const freshKinds = kinds(freshLog);
    check('a fresh page load renders entries', freshKinds.length > 0, freshKinds.join(','));
    check('a fresh page load shows no error entry',
          ofKind(freshLog, 'error').length === 0,
          ofKind(freshLog, 'error').map((e) => e.textContent).join(' | ').slice(0, 90));
    check('a fresh page load never says the approaches ran out',
          !/all pedagogies|all approaches|no learning approach available/i.test(textOf(freshLog)));
    check('a fresh page load gets teaching or a recovery or a review',
          ['teaching', 'intervention', 'manual-review', 'complete']
            .some((k) => freshKinds.includes(k)), freshKinds.join(','));
    const hasAnswer = ofKind(freshLog, 'checkpoint').length > 0;
    const terminal = freshKinds.includes('manual-review') || freshKinds.includes('complete');
    check('a fresh page load either offers a question or is clearly finished',
          hasAnswer || terminal, hasAnswer ? 'question offered' : freshKinds.join(','));
    check('the reloaded page still shows the topic', doc.getElementById('topic-heading').textContent.length > 10);
  }

  console.log('\n[7] The hidden machinery stays hidden');
  const all = textOf(log);
  check('the four-step learning path is never shown',
        !/recognize.*connect.*relate.*generalize/i.test(all));
  check('the approach pool is not shown to the learner',
        !/pedagogy pool/i.test(all));
  check('technical scoring fields are not shown',
        !/target signature met|assigned solo level|solo transition/i.test(all));
  check('research view is not part of the journal',
        !log.textContent.includes('Target signature met'));
}

try {
  await main();
} catch (e) {
  check('harness ran without throwing', false, String(e && e.message));
} finally {
  if (PROC) PROC.kill();
}

console.log(`\n${'='.repeat(62)}\n  ${checks} checks run`);
if (failures.length) {
  console.log(`\n${failures.length} FAILURE(S):`);
  failures.forEach((f) => console.log('  - ' + f));
  process.exit(1);
}
console.log('All journal checks passed.');
