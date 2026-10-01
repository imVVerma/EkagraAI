#!/usr/bin/env node
/* Static contract check between index.html, app.js and styles.css.
 *
 * Catches the class of bug a stubbed-DOM harness cannot: an element id or
 * class name that app.js references but the page does not define, and CSS
 * rules that target classes nothing ever renders. Both only fail in a real
 * browser, which is exactly where they are expensive.
 */

import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIR = resolve(ROOT, 'frontend');
const html = readFileSync(`${DIR}/index.html`, 'utf8');
const js = readFileSync(`${DIR}/app.js`, 'utf8');
const css = readFileSync(`${DIR}/styles.css`, 'utf8');

const problems = [];
const note = (m) => problems.push(m);
const uniq = (a) => [...new Set(a)];

/* ── ids: HTML is the source of truth ─────────────────────────── */

const htmlIds = uniq([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
const jsIds = uniq([...js.matchAll(/\bel\(\s*'([^']+)'\s*\)/g)].map((m) => m[1]));

const missingIds = jsIds.filter((id) => !htmlIds.includes(id));
if (missingIds.length) note(`app.js references ids absent from index.html: ${missingIds.join(', ')}`);

// Ids that exist only as accessibility anchors are legitimately never read by
// script, so they are not a defect.
const a11yIds = new Set(
  [...html.matchAll(/\s(?:aria-labelledby|aria-controls|aria-describedby|for)="([^"]+)"/g)]
    .flatMap((m) => m[1].split(/\s+/))
);

// Ids app.js creates at runtime (rather than reading from the page).
const runtimeIds = new Set(['response-input', 'btn-submit']);

const orphanIds = htmlIds.filter(
  (id) => !jsIds.includes(id) && !a11yIds.has(id) && !runtimeIds.has(id)
);
if (orphanIds.length) {
  note(`index.html defines ids nothing reads (dead markup?): ${orphanIds.join(', ')}`);
}

/* ── classes: CSS must only target what is rendered ───────────── */

const renderedClasses = new Set([
  // className assigned from a literal
  ...[...js.matchAll(/className\s*=\s*[`'"]([^`'"]+)[`'"]/g)]
    .flatMap((m) => m[1].split(/\s+/))
    .filter(Boolean),
  // className assigned from a template literal: `btn ${className}`
  ...[...js.matchAll(/className\s*=\s*`([^`]*)`/g)]
    .flatMap((m) => m[1].split(/\s+/))
    .filter(Boolean),
  // the node() helper: node('p', 'entry__eyebrow', ...) — second argument
  ...[...js.matchAll(/\bnode\(\s*'[a-zA-Z][\w-]*'\s*,\s*[`'"]([^`'"]+)[`'"]/g)]
    .flatMap((m) => m[1].split(/\s+/))
    .filter(Boolean),
  ...[...js.matchAll(/\bnode\(\s*'[a-zA-Z][\w-]*'\s*,\s*`([^`]*)`/g)]
    .flatMap((m) => m[1].split(/\s+/))
    .filter(Boolean),
  // html class attributes
  ...[...html.matchAll(/\sclass="([^"]+)"/g)].flatMap((m) => m[1].split(/\s+/)),
  // classList calls
  ...[...js.matchAll(/classList\.(?:add|remove|toggle)\(\s*'([^']+)'/g)].map((m) => m[1]),
  // dataset values assigned in app.js
  ...[...js.matchAll(/dataset\.\w+\s*=\s*'([^']+)'/g)].map((m) => m[1]),
  // the second argument of button(), which builds `btn ${className}`
  ...[...js.matchAll(/\bbutton\(\s*'[^']*'\s*,\s*[`'"]([^`'"]+)[`'"]/g)]
    .flatMap((m) => m[1].split(/\s+/))
    .filter(Boolean),
]);
renderedClasses.delete('${kind}');
renderedClasses.delete('${className}');

// Entry kinds are built as `entry--${kind}` from a literal kind argument.
const kindLiterals = uniq(
  [...js.matchAll(/\bentry\('([a-z-]+)'\)/g)].map((m) => m[1])
);
kindLiterals.forEach((k) => renderedClasses.add(`entry--${k}`));

// Modifier values assigned via dataset.outcome.
uniq([...js.matchAll(/dataset\.outcome\s*=\s*'([^']+)'/g)].map((m) => m[1])).forEach((o) =>
  renderedClasses.add(o)
);
// and the pass/not-yet pairing used in selectors like [data-outcome="pass"]
['pass', 'not-yet'].forEach((o) => renderedClasses.add(o));

const cssClasses = uniq(
  [...css.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1])
).filter((c) => !['5', '75'].includes(c));

const deadCss = cssClasses.filter((c) => !renderedClasses.has(c));
if (deadCss.length) note(`styles.css targets classes nothing renders: ${deadCss.join(', ')}`);

/* ── the learner-facing surface must stay free of mechanism ───── */

const forbidden = [
  [/learning-path/, 'app.js still requests the removed learning-path endpoint'],
  [/Recognize[\s\S]{0,40}Connect[\s\S]{0,40}Relate/i, 'the four-step learning path appears in the UI'],
  [/Target signature met:\s*true/i, 'raw scoring output shown to the learner'],
];
forbidden.forEach(([re, why]) => {
  if (re.test(js) || re.test(html)) note(why);
});

// The research view is the one place technical vocabulary is allowed.
const learnerSide = js.split('renderResearch')[0];
if (/assigned_solo_level/.test(learnerSide)) {
  note('SOLO level is referenced in the learner-facing half of app.js');
}

/* ── assets ───────────────────────────────────────────────────── */

['index.html', 'app.js', 'styles.css'].forEach((f) => {
  if (!existsSync(resolve(DIR, f))) note(`missing frontend file: ${f}`);
});

/* ── report ───────────────────────────────────────────────────── */

console.log(`html ids: ${htmlIds.length}   js id reads: ${jsIds.length}   css classes: ${cssClasses.length}`);
if (problems.length) {
  console.log(`\n${problems.length} PROBLEM(S):`);
  problems.forEach((p) => console.log('  - ' + p));
  process.exit(1);
}
console.log('Contract check passed: ids, classes and the learner-facing surface all line up.');
