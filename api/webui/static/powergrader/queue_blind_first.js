/* PowerGrader blind-first scoring.
 *
 * Score the student yourself, then reveal what the AI said. The suggestion is
 * withheld by the server until reveal (see api/powergrader/blind_first.py), so
 * this module never has an unrevealed AI score to leak — it renders the reveal
 * control, then reports whether the two scores actually disagreed.
 *
 * The panel only expands when the disagreement is past the teacher's threshold.
 * Agreement is reported as a one-line "nothing to review" so a session where the
 * model tracks the teacher costs no attention at all.
 */
(function(){
  "use strict";

  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});
  var sessionId = queue.getSessionId
    ? queue.getSessionId()
    : document.querySelector('meta[name="session-id"]').content;

  var strip = document.getElementById('pg-blind-strip');
  var stripSummary = document.getElementById('pg-blind-summary');
  var toggleBtn = document.getElementById('pg-blind-toggle');
  var thresholdInput = document.getElementById('pg-blind-threshold');
  var box = document.getElementById('pg-blind-box');
  var noteEl = document.getElementById('pg-blind-note');
  var revealBtn = document.getElementById('pg-blind-reveal');
  var showAnywayBtn = document.getElementById('pg-blind-show-anyway');
  var aiPanel = document.getElementById('pg-ai-panel');
  var aiFeedDetails = document.getElementById('pg-ai-feedback-details');
  var scoreEl = document.getElementById('pg-score');
  var feedbackEl = document.getElementById('pg-feedback');
  var kbdHint = document.getElementById('pg-kbd-r-hint');

  // "Show it anyway" is per-student and per-visit: an agreement the teacher chose
  // to open once should not stay open for everyone after it.
  var forceShow = {};

  function getStudents(){ return queue.getStudents ? queue.getStudents() : []; }
  function getIndex(){ return queue.getIndex ? queue.getIndex() : 0; }
  function currentStudent(){ return getStudents()[getIndex()] || null; }
  function isAiMode(){ return !!(queue.isAiMode && queue.isAiMode()); }
  function showStatus(msg, isErr){ if (queue.showStatus) queue.showStatus(msg, isErr); }

  function active(){
    return !!(queue.blindFirstActive && queue.blindFirstActive());
  }

  function summary(){
    return queue.blindFirstSummary || null;
  }

  function threshold(){
    var s = summary();
    var value = s ? Number(s.threshold) : NaN;
    return isFinite(value) && value >= 0 ? value : 1;
  }

  function num(value){
    if (value === null || value === undefined || value === '') return null;
    var parsed = Number(value);
    return isFinite(parsed) ? parsed : null;
  }

  function fmt(value){
    var parsed = num(value);
    return parsed === null ? '—' : String(parsed);
  }

  function hasSuggestion(st){
    if (!st) return false;
    if (st.blind_withheld === true) return st.blind_has_ai_suggestion === true;
    if (st.ai_score !== null && st.ai_score !== undefined) return true;
    return !!(st.ai_feedback && String(st.ai_feedback).trim());
  }

  /* ── Session strip ─────────────────────────────────────────────────── */

  function renderBlindFirst(session) {
    if (!strip) return;
    if (!session || !isAiMode()) { strip.hidden = true; if (kbdHint) kbdHint.hidden = true; return; }
    strip.hidden = false;

    var s = summary() || {};
    var on = active();
    if (kbdHint) kbdHint.hidden = !on;

    if (toggleBtn) {
      toggleBtn.textContent = on ? 'Turn off blind-first' : 'Turn on blind-first';
      toggleBtn.disabled = false;
    }
    if (thresholdInput && document.activeElement !== thresholdInput) {
      thresholdInput.value = threshold();
    }

    if (!stripSummary) return;
    if (!on) {
      stripSummary.textContent =
        "Off — the AI's score pre-fills your box. Turn on to record your own score first.";
      return;
    }
    var bits = [];
    if (s.withheld) bits.push(s.withheld + ' of ' + s.ai_scored + ' AI scores still hidden');
    else if (s.ai_scored) bits.push('all ' + s.ai_scored + ' AI scores revealed');
    if (s.compared) {
      bits.push(s.compared + ' compared');
      bits.push(s.disagreements + ' past ' + fmt(threshold()) + ' pt');
    }
    stripSummary.textContent = 'On — ' + (bits.length ? bits.join(', ') + '.' : 'no AI scores in this session yet.');
  }

  function postSettings(enabled, thresholdValue) {
    if (toggleBtn) toggleBtn.disabled = true;
    var fd = new FormData();
    fd.append('enabled', enabled ? 'true' : 'false');
    fd.append('threshold', String(thresholdValue));
    return fetch('/api/powergrader/session/' + sessionId + '/blind-first', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          showStatus(d.error || 'Blind-first could not be changed.', true);
          if (toggleBtn) toggleBtn.disabled = false;
          return;
        }
        queue.blindFirstSummary = d.blind_first || null;
        // A full reload is required when turning blind-first ON: the AI scores the
        // browser already holds have to be surrendered, and only the server can
        // decide which of them are still withheld.
        if (queue.reloadSession) {
          queue.reloadSession({ indexOverride: getIndex() })
            .then(function(){ showStatus(enabled ? 'Blind-first on.' : 'Blind-first off.', false); });
        } else {
          window.location.reload();
        }
      })
      .catch(function(e){
        showStatus('Blind-first error: ' + e, true);
        if (toggleBtn) toggleBtn.disabled = false;
      });
  }

  /* ── Per-student reveal ────────────────────────────────────────────── */

  function renderBlindFirstStudent(st) {
    if (!box) return;
    if (!active() || !st || !hasSuggestion(st)) {
      box.hidden = true;
      box.removeAttribute('data-blind-state');
      return;
    }
    box.hidden = false;

    if (st.ai_revealed !== true) {
      box.setAttribute('data-blind-state', 'withheld');
      noteEl.textContent = "AI suggestion hidden. Enter your own score, then reveal.";
      revealBtn.hidden = false;
      revealBtn.disabled = false;
      showAnywayBtn.hidden = true;
      if (aiPanel) aiPanel.hidden = true;
      return;
    }

    revealBtn.hidden = true;
    var delta = num(st.blind_delta);
    var committed = st.blind_committed === true && delta !== null;
    var verdict = !committed ? 'uncommitted' : (delta <= threshold() ? 'agrees' : 'disagrees');
    box.setAttribute('data-blind-state', verdict);

    if (verdict === 'agrees') {
      var opened = forceShow[st.user_id] === true;
      noteEl.textContent = '✓ AI agreed within ' + fmt(threshold()) + ' pt of your '
        + fmt(st.blind_score) + '. Nothing to review.';
      showAnywayBtn.hidden = opened;
      if (aiPanel) aiPanel.hidden = !opened;
      // Opening it was a deliberate ask, so show the text, not another disclosure.
      if (aiFeedDetails) aiFeedDetails.open = opened;
      return;
    }

    showAnywayBtn.hidden = true;
    if (aiPanel) aiPanel.hidden = false;
    // Past the threshold the AI's reasoning is the thing being judged, not a reference.
    if (aiFeedDetails) aiFeedDetails.open = true;
    if (verdict === 'disagrees') {
      noteEl.textContent = '⚠ You scored ' + fmt(st.blind_score) + ', AI scored '
        + fmt(st.ai_score) + ' — ' + fmt(delta) + ' pt apart.';
    } else {
      noteEl.textContent = 'Revealed without your own score first — not counted toward agreement.';
    }
  }

  function reveal() {
    var st = currentStudent();
    if (!active() || !st || st.ai_revealed === true || !hasSuggestion(st)) return;
    revealBtn.disabled = true;
    var fd = new FormData();
    fd.append('user_id', st.user_id);
    fd.append('blind_score', scoreEl ? scoreEl.value : '');
    fd.append('blind_feedback', feedbackEl ? feedbackEl.value : '');
    fetch('/api/powergrader/session/' + sessionId + '/blind-reveal', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          showStatus(d.error || 'Reveal failed.', true);
          revealBtn.disabled = false;
          return;
        }
        st.ai_score = d.ai_score;
        st.ai_feedback = d.ai_feedback;
        st.blind_score = d.blind_score;
        st.blind_committed = d.blind_committed;
        st.blind_delta = d.delta;
        st.ai_revealed = true;
        st.blind_withheld = false;
        queue.blindFirstSummary = d.blind_first || queue.blindFirstSummary;
        // Re-render through the ordinary path so the AI panel picks up the
        // now-available suggestion; renderStudent calls back into this module.
        if (queue.renderStudent) queue.renderStudent(getIndex());
        renderBlindFirst(queue.getSession ? queue.getSession() : null);
        showStatus(d.verdict === 'disagrees'
          ? 'Revealed — ' + fmt(d.delta) + ' pt apart.'
          : (d.verdict === 'agrees' ? 'Revealed — AI agrees.' : 'Revealed.'), false);
      })
      .catch(function(e){
        showStatus('Reveal error: ' + e, true);
        revealBtn.disabled = false;
      });
  }

  /* ── Wiring ────────────────────────────────────────────────────────── */

  toggleBtn && toggleBtn.addEventListener('click', function(){
    postSettings(!active(), thresholdInput ? thresholdInput.value : threshold());
  });

  thresholdInput && thresholdInput.addEventListener('change', function(){
    var value = num(thresholdInput.value);
    if (value === null || value < 0) {
      thresholdInput.value = threshold();
      showStatus('The agreement threshold must be zero or more.', true);
      return;
    }
    postSettings(active(), value);
  });

  revealBtn && revealBtn.addEventListener('click', reveal);

  showAnywayBtn && showAnywayBtn.addEventListener('click', function(){
    var st = currentStudent();
    if (!st) return;
    forceShow[st.user_id] = true;
    renderBlindFirstStudent(st);
  });

  document.addEventListener('keydown', function(e){
    if (e.target.matches('textarea, input, select, button')) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key.toLowerCase() !== 'r') return;
    if (!active()) return;
    reveal();
    e.preventDefault();
  });

  queue.renderBlindFirst = renderBlindFirst;
  queue.renderBlindFirstStudent = renderBlindFirstStudent;
})();
