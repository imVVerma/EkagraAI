/* ══════════════════════════════════════════════════════════════════
   Ekagra — Adaptive Learning through AI
   Learner interface logic

   The session is an accumulating journal. Each attempt appends entries below
   the previous ones and nothing is ever replaced, so the learner can scroll
   back through how their reasoning developed. The adaptive machinery —
   transitions, the pedagogy pool, SOLO levels — stays in the research view.
   ══════════════════════════════════════════════════════════════════ */

'use strict';

/* ── State ────────────────────────────────────────────────────────── */

const state = {
  transition: null,      // /api/transition payload
  session: null,         // /api/session payload
  transitionId: null,    // the topic the journal is currently on
  currentApproach: null, // approach used for the teaching turn on screen
  awaiting: false,       // a checkpoint is open and unanswered
  busy: false,           // a request is in flight
  complete: false,       // the session has ended; no further attempts
  lastResult: null,
  lastStep: null,        // the step kind the server last served
};

const el = (id) => document.getElementById(id);
const log = () => el('log');

/* ── API helper ───────────────────────────────────────────────────── */

async function api(path) {
  const res = await fetch(`/api${path}`, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(await describeFailure(path, res));
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await describeFailure(path, res));
  return res.json();
}

/**
 * Turn a failed request into something the reader can act on.
 *
 * A missing endpoint almost always means the server is an older process than
 * this page was written against, so that is said plainly rather than leaving a
 * bare status code in the journal.
 */
async function describeFailure(path, res) {
  let detail = '';
  try {
    const body = await res.json();
    detail = body.error || '';
  } catch (_) {
    /* a non-JSON error body is not worth reporting */
  }
  if (res.status === 404) {
    return (
      `The server has no endpoint for ${path}. It is probably an older process ` +
      'than this page — restart the server and reload.'
    );
  }
  return detail || `Request failed (${res.status})`;
}

/* ── DOM construction ─────────────────────────────────────────────── */

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function entry(kind) {
  const li = document.createElement('li');
  li.className = `entry entry--${kind}`;
  li.dataset.kind = kind;
  return li;
}

/** Append an entry to the journal and keep the newest one in view. */
function append(li) {
  log().append(li);
  li.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  return li;
}

function actions(...buttons) {
  const wrap = node('div', 'entry__actions');
  buttons.forEach((b) => wrap.append(b));
  return wrap;
}

function button(label, className, onClick) {
  const b = node('button', `btn ${className}`, label);
  b.type = 'button';
  b.addEventListener('click', onClick);
  return b;
}

/* ── Topic + goal ─────────────────────────────────────────────────── */

function renderTopic() {
  const { transition } = state;
  if (!transition) return;
  el('topic-heading').textContent = transition.concept_to_master;
  el('topic-goal').textContent = transition.prerequisite || '';
}

/* ── Research view ────────────────────────────────────────────────── */

// Level names arrive from the knowledge bank (e.g. "extended_abstract"), so
// they are formatted for display rather than enumerated here.
const levelLabel = (lvl) =>
  lvl ? lvl.charAt(0).toUpperCase() + lvl.slice(1).replace(/_/g, ' ') : '—';

function renderResearch() {
  const { transition, session, lastResult } = state;
  if (!transition || !session) return;

  // Each approach is drawn immediately before an attempt starts, so the number
  // of draws on this topic is the attempt number. (The session's own counter is
  // global to the whole session, so it cannot be used for this.)
  const used = session.used_pool || [];
  const attempts = Math.max(1, used.length);

  el('rv-transition').textContent =
    `${transition.transition_id} (${transition.transition_idx + 1} of ${session.transition_count})`;
  el('rv-solo').textContent =
    [transition.solo_from, transition.solo_to].filter(Boolean).join(' → ') || '—';
  el('rv-pedagogy').textContent = state.currentApproach || session.current_pedagogy || 'not yet selected';
  el('rv-attempt').textContent = String(attempts);
  el('rv-previous').textContent = used.slice(0, -1).join(', ') || 'none';
  el('rv-case').textContent = session.case_id
    ? `${session.case_id}${transition.case_count > 1 ? ` (${transition.case_count} available)` : ''}`
    : '—';
  el('rv-level').textContent = lastResult ? levelLabel(lastResult.assigned_solo_level) : '—';
  el('rv-met').textContent = lastResult ? String(lastResult.target_signature_met) : '—';
  el('rv-interventions').textContent = String(session.interventions || 0);
  el('rv-pool').textContent = (session.pedagogy_pool || []).join(', ') || '—';
}

/* ── Journal entries ──────────────────────────────────────────────── */

/**
 * One attempt's opening: what is being taught, and the quiet note of how.
 *
 * The approach is a single subdued line. It is deliberately not a title — the
 * teaching content is what the learner is reading, and the approach is part of
 * the tutor's manner rather than a topic of its own.
 */
function appendTeaching({ label, anchor, blocks, attempt, topicChanged }) {
  const li = entry('teaching');

  const head = node('div', 'entry__head');
  head.append(node('p', 'entry__eyebrow', topicChanged ? 'New topic' : 'Teaching'));
  if (attempt) head.append(node('span', 'entry__ordinal', `Attempt ${attempt}`));
  li.append(head);

  if (label) li.append(node('p', 'entry__approach', label));
  if (anchor) li.append(node('p', 'entry__anchor', `Doctrinal anchor · ${anchor}`));

  const body = node('div', 'prose');
  blocks.forEach((b) => body.append(renderBlock(b)));
  li.append(body);

  return append(li);
}

function renderBlock(block) {
  if (block.type === 'question') return node('p', 'prose__question', block.text);
  if (block.type === 'aside') return node('p', 'prose__aside', block.text);
  if (block.type === 'contrast') return node('p', 'prose__contrast', block.text);
  return node('p', 'prose__para', block.text);
}

/** The checkpoint: the scenario, the question, and somewhere to answer it. */
function appendCheckpoint(caseData) {
  const li = entry('checkpoint');

  const head = node('div', 'entry__head');
  head.append(node('p', 'entry__eyebrow', 'Question'));
  li.append(head);

  li.append(node('h3', 'case__title', caseData.title));
  li.append(node('blockquote', 'case__scenario', caseData.scenario_text));
  li.append(node('p', 'case__question', caseData.question));

  const form = document.createElement('form');
  form.className = 'response';

  const label = node('label', 'response__label', 'Your response');
  const input = document.createElement('textarea');
  input.className = 'response__input';
  input.id = 'response-input';
  input.rows = 5;
  input.placeholder = 'Write your response…';
  input.setAttribute('aria-label', 'Your response');
  label.setAttribute('for', 'response-input');

  const submit = node('button', 'btn btn--primary', 'Submit response');
  submit.type = 'submit';
  submit.id = 'btn-submit';

  form.append(label, input, actions(submit));
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    submitResponse(input, li).catch(showError);
  });

  li.append(form);
  append(li);
  input.focus();
  return { entry: li, input, submit };
}

/**
 * The review of what the learner just submitted, appended below their answer.
 *
 * Their own words are echoed first and left unedited, so scrolling back shows
 * the reasoning as it was actually given rather than a summary of it.
 */
function appendReview(result, responseText) {
  const li = entry('review');
  const passed = result.target_signature_met;
  const feedback = result.feedback || {};

  li.dataset.outcome = passed ? 'pass' : 'not-yet';

  const head = node('div', 'entry__head');
  head.append(node('p', 'entry__eyebrow', 'Response review'));
  li.append(head);

  const said = node('div', 'said');
  said.append(node('p', 'said__label', 'Your response'));
  said.append(node('p', 'said__text', responseText));
  li.append(said);

  const saidByTutor = node('div', 'tutor');
  saidByTutor.append(node('p', 'said__label', 'Tutor'));
  saidByTutor.append(node('p', 'said__text', feedback.headline || ''));
  // The level definition comes from the knowledge bank, and the note on what
  // would strengthen the answer. Neither names a SOLO level.
  if (feedback.detail) saidByTutor.append(node('p', 'said__note', feedback.detail));
  if (feedback.note) saidByTutor.append(node('p', 'said__aside', feedback.note));
  li.append(saidByTutor);

  return append(li);
}

/* ── Journal flow ─────────────────────────────────────────────────── */

async function refreshMeta() {
  state.session = await api('/session');
  state.transition = await api('/transition');
  state.transitionId = state.transition.transition_id;
  renderTopic();
  renderResearch();
}

/**
 * Load the next attempt from the server, which decides what it is.
 *
 * The server returns a teaching turn and the checkpoint that follows it, or a
 * tutor intervention, or a review. Asking rather than deciding is what keeps a
 * reload mid-session working: the session lives on the server, so reloading
 * resumes the step the tutor had already decided on instead of starting over
 * or hitting an exhausted approach pool.
 */
async function nextStep() {
  const data = await api('/next');
  state.lastStep = data.step;
  return data;
}

/** Render whatever the server decided, then its checkpoint if there is one. */
function renderStep(step, previousTopic) {
  if (step.step === 'intervention') {
    appendIntervention(step);
  } else if (step.step === 'manual_review') {
    appendManualReview(step);
    state.complete = true;
    return;
  } else if (step.step === 'complete') {
    appendComplete(step);
    state.complete = true;
    return;
  } else {
    state.currentApproach = step.pedagogy || null;
    appendTeaching({
      label: step.label,
      anchor: (step.teaching_turn_blocks || []).find((b) => b.type === 'anchor')?.text,
      blocks: (step.teaching_turn_blocks || []).filter((b) => b.type !== 'anchor'),
      attempt: step.attempt_number,
      topicChanged: step.transition_id !== previousTopic,
    });
  }
  if (step.checkpoint) openCheckpoint(step.checkpoint);
}

async function submitResponse(input, checkpointEntry) {
  const text = input.value.trim();
  if (!text || state.busy) return;
  if (!state.awaiting) return;

  state.busy = true;
  input.disabled = true;
  const submit = checkpointEntry.querySelector('#btn-submit');
  if (submit) submit.disabled = true;

  try {
    const result = await post('/respond', {
      response: text,
      participant_id: 'demo-user',
    });
    state.lastResult = result;
    state.awaiting = false;

    // The learner's answer stays in place; the review is added beneath it.
    appendReview(result, text);

    if (result.session_complete && result.status !== 'pass') {
      // Terminal recovery: the server holds the step, and it says so again on
      // every ask, so a reload still lands on the review.
      await refreshMeta();
      renderStep(await nextStep(), state.transitionId);
      return;
    }

    if (result.status === 'pass') {
      const fromTopic = state.transitionId;   // captured before the topic moves
      appendNext(result);
      await refreshMeta();
      renderStep(await nextStep(), fromTopic);
      return;
    }

    // Not yet: the review carries on into the next attempt's teaching.
    appendNext(result);
    await refreshMeta();
    renderStep(await nextStep(), state.transitionId);
  } catch (err) {
    showError(err);
  } finally {
    state.busy = false;
  }
}

/** Reveal a checkpoint. Only ever called after its teaching turn is in the log. */
function openCheckpoint(caseData) {
  if (!caseData || !caseData.question) return;
  const { input } = appendCheckpoint(caseData);
  state.awaiting = true;
  input.focus();
}
/** The hand-off line between one attempt and the next. */
function appendNext(result) {
  const li = entry('next');
  const passed = result.target_signature_met;
  li.append(
    node(
      'p',
      'entry__eyebrow',
      passed ? 'Next' : 'What happens next'
    )
  );

  if (passed && result.next_concept) {
    li.append(node('p', 'next__text', `Next up: ${result.next_concept}`));
    li.dataset.outcome = 'pass';
  } else {
    li.append(
      node(
        'p',
        'next__text',
        "We'll come at this from a different angle. New teaching follows."
      )
    );
  }

  return append(li);
}

/**
 * The tutor stepping in after every approach has been exhausted.
 *
 * This is a recovery, not a reset: the journal above is untouched, the pool is
 * refilled, and a fresh case from the bank is presented below.
 */
async function appendIntervention(step) {
  const li = entry('intervention');

  const head = node('div', 'entry__head');
  head.append(node('p', 'entry__eyebrow', 'Tutor intervention'));
  if (step.attempt_number) head.append(node('span', 'entry__ordinal', `Attempt ${step.attempt_number}`));
  li.append(head);

  li.append(node('h3', 'intervention__headline', step.headline || 'Let us approach this differently.'));
  if (step.label) li.append(node('p', 'entry__approach', step.label));

  (step.explanation || []).forEach((line) => {
    if (line) li.append(node('p', 'prose__para', line));
  });

  if ((step.worked_example_blocks || []).length) {
    const worked = node('div', 'worked');
    worked.append(node('p', 'worked__label', 'Worked example'));
    const body = node('div', 'prose');
    (step.worked_example_blocks || [])
      .filter((b) => b.type !== 'anchor')
      .forEach((b) => body.append(renderBlock(b)));
    worked.append(body);
    li.append(worked);
  }

  if (step.fresh_case) {
    li.append(node('p', 'intervention__next', `A new case follows: ${step.fresh_case}.`));
  }

  return append(li);
}

/** Terminal state when the bank holds no further case. Nothing is discarded. */
async function appendManualReview(step) {
  const li = entry('manual-review');
  const head = node('div', 'entry__head');
  head.append(node('p', 'entry__eyebrow', 'Tutor review'));
  li.append(head);
  li.append(node('h3', 'intervention__headline', step.headline || 'This one is worth a human tutor.'));
  if (step.message) li.append(node('p', 'prose__para', step.message));
  if (step.suggestion) li.append(node('p', 'prose__aside', step.suggestion));
  return append(li);
}

async function appendComplete(step) {
  const li = entry('complete');
  const head = node('div', 'entry__head');
  head.append(node('p', 'entry__eyebrow', 'Session complete'));
  li.append(head);
  li.append(node('h3', 'intervention__headline', step.headline || 'You have worked through the whole topic.'));
  li.append(
    node(
      'p',
      'prose__para',
      'Scroll back through the session to see how each approach changed your reasoning.'
    )
  );
  return append(li);
}

/** Surface an unexpected failure without pretending it was learner feedback. */
function showError(err) {
  const li = entry('error');
  li.append(node('p', 'entry__eyebrow', 'Something went wrong'));
  li.append(node('p', 'prose__para', err.message || String(err)));
  append(li);
  state.awaiting = false;
}

/* ── Boot ─────────────────────────────────────────────────────────── */

async function init() {
  state.busy = true;
  try {
    const sub = await api('/subtopic');
    el('domain').textContent = sub.domain || '';
    el('subtopic').textContent = sub.subtopic || '';

    await refreshMeta();
    // The server decides the opening step, and always sends a teaching turn (or
    // a recovery) ahead of the first checkpoint.
    renderStep(await nextStep(), null);
  } catch (err) {
    showError(err);
  } finally {
    state.busy = false;
  }
}

init();
