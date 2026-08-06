(function(){
  "use strict";

  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});
  var sessionId = queue.getSessionId ? queue.getSessionId() : document.querySelector('meta[name="session-id"]').content;

  var lateStrip = document.getElementById('pg-late-strip');
  var lateSummary = document.getElementById('pg-late-summary');
  var lateActions = document.getElementById('pg-late-actions');
  var lateDetail = document.getElementById('pg-late-detail');
  var latePreviewBtn = document.getElementById('pg-late-preview');
  var lateScoreBtn = document.getElementById('pg-late-score');

  function esc(s) {
    if (queue.esc) return queue.esc(s);
    var d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }

  function getSession() {
    return queue.getSession ? queue.getSession() : null;
  }

  function currentMode() {
    var s = getSession();
    return s ? (s.mode || 'fast') : 'fast';
  }

  function renderLateWatch(s) {
    if (!lateStrip || !lateSummary || !lateActions || !lateDetail) return;
    var late = (s && s.late_watch) || null;
    if (!late) {
      lateStrip.hidden = true;
      lateDetail.innerHTML = '';
      lateActions.innerHTML = '';
      return;
    }
    lateStrip.hidden = false;
    var enabled = !!late.enabled && !!late.supported;
    var mode = s ? s.mode : 'fast';
    var isPacket = mode === 'packet';
    var summaryBits = [];
    if (late.reason && !enabled) {
      summaryBits.push(late.reason);
    } else if (enabled) {
      summaryBits.push(isPacket ? 'Generating' : 'Watching');
    } else {
      summaryBits.push('Not watching');
    }
    if (late.last_summary) summaryBits.push(late.last_summary);
    lateSummary.textContent = summaryBits.join(' · ');
    latePreviewBtn.disabled = !enabled;
    lateScoreBtn.hidden = true;
    lateScoreBtn.disabled = true;
    // Relabel for packet mode
    lateScoreBtn.textContent = isPacket ? 'Generate Late AI Chat Batch' : 'Score New Late Work';
    var initialMissing = (late.initial_missing_user_ids || []).length;
    var knownCount = (late.known_user_ids || []).length;
    var scoredCount = (late.scored_user_ids || []).length;
    var generatedCount = (late.generated_user_ids || []).length;
    var details = [
      '<div class="pg-late-detail-row">Initial missing: ' + initialMissing + '</div>',
      '<div class="pg-late-detail-row">Known in queue: ' + knownCount + '</div>',
    ];
    if (isPacket) {
      details.push('<div class="pg-late-detail-row">AI chat batches generated: ' + generatedCount + '</div>');
    } else {
      details.push('<div class="pg-late-detail-row">Already appended: ' + scoredCount + '</div>');
    }
    if (late.last_checked) details.push('<div class="pg-late-detail-row">Last checked: ' + esc(late.last_checked) + '</div>');
    if (late.last_scored) details.push('<div class="pg-late-detail-row">Last scored: ' + esc(late.last_scored) + '</div>');
    if (late.last_generated) details.push('<div class="pg-late-detail-row">Last generated: ' + esc(late.last_generated) + '</div>');
    lateDetail.innerHTML = details.join('');
  }

  function showLateScoreButton(show) {
    if (!lateScoreBtn) return;
    lateScoreBtn.hidden = !show;
    lateScoreBtn.disabled = !show;
  }

  function refreshAfterLateScore(appendedCount) {
    appendedCount = Number(appendedCount) || 0;
    var currentIndex = queue.getIndex ? queue.getIndex() : 0;
    if (queue.reloadSession) {
      return queue.reloadSession({
        indexOverride: currentIndex,
        onSuccess: function() {
          if (queue.showStatus) {
            queue.showStatus('Late catch-up added ' + appendedCount + ' student(s) to review.', false);
          }
        },
      });
    }
    return fetch('/api/powergrader/session/' + sessionId)
      .then(function(r){ return r.json(); })
      .then(function(fresh){
        if (!fresh.ok) return false;
        if (queue.setSession) queue.setSession(fresh.session);
        if (queue.setStudents) queue.setStudents(fresh.session.students || []);
        if (queue.updateProgress) queue.updateProgress();
        if (queue.renderPrivacyAudit) queue.renderPrivacyAudit(fresh.session);
        renderLateWatch(fresh.session);
        if (queue.renderPacketPanel) queue.renderPacketPanel(fresh.session);
        if (queue.renderStudent) {
          var students = queue.getStudents ? queue.getStudents() : [];
          queue.renderStudent(Math.min(currentIndex, Math.max(0, students.length - 1)));
        }
        if (queue.showStatus) {
          queue.showStatus('Late catch-up added ' + appendedCount + ' student(s) to review.', false);
        }
        return true;
      });
  }

  queue.renderLateWatch = renderLateWatch;

  if (getSession()) renderLateWatch(getSession());

  latePreviewBtn && latePreviewBtn.addEventListener('click', function(){
    latePreviewBtn.disabled = true;
    if (lateSummary) lateSummary.textContent = 'Checking for late submissions…';
    fetch('/api/powergrader/session/' + sessionId + '/late-preview', {method:'POST'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          if (lateSummary) lateSummary.textContent = d.error || 'Late preview failed.';
          if (queue.showStatus) queue.showStatus(d.error || 'Late preview failed.', true);
          return;
        }
        if (lateSummary) lateSummary.textContent = d.message || (d.new_count + ' late submission(s) found.');
        if (lateDetail) {
          lateDetail.innerHTML = (d.students || []).map(function(st){
            return '<div class="pg-late-detail-row">' + esc(st.name || st.user_id || '') +
              (st.submitted_at ? ' · ' + esc(st.submitted_at) : '') + '</div>';
          }).join('');
        }
        showLateScoreButton((d.new_count || 0) > 0);
      })
      .catch(function(e){
        if (lateSummary) lateSummary.textContent = String(e);
        if (queue.showStatus) queue.showStatus(String(e), true);
      })
      .finally(function(){
        latePreviewBtn.disabled = false;
      });
  });

  lateScoreBtn && lateScoreBtn.addEventListener('click', function(){
    lateScoreBtn.disabled = true;
    var mode = currentMode();
    var label = mode === 'packet' ? 'Generating late AI chat batch…' : 'Scoring new late submissions…';
    if (lateSummary) lateSummary.textContent = label;
    fetch('/api/powergrader/session/' + sessionId + '/late-score', {method:'POST'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          if (lateSummary) lateSummary.textContent = d.error || (mode === 'packet' ? 'Late generation failed.' : 'Late scoring failed.');
          if (queue.showStatus) queue.showStatus(d.error || (mode === 'packet' ? 'Late generation failed.' : 'Late scoring failed.'), true);
          return;
        }
        return refreshAfterLateScore(d.appended);
      })
      .catch(function(e){
        if (lateSummary) lateSummary.textContent = String(e);
        if (queue.showStatus) queue.showStatus(String(e), true);
      })
      .finally(function(){
        var session = getSession();
        if (session && session.late_watch && session.late_watch.enabled && session.late_watch.supported) {
          lateScoreBtn.disabled = false;
        }
      });
  });
})();
