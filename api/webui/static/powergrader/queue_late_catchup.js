(function(){
  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});
  var SESSION_ID = queue.getSessionId ? queue.getSessionId() : document.querySelector('meta[name="session-id"]').content;

  var lateStrip = document.getElementById('pg-late-strip');
  var lateSummary = document.getElementById('pg-late-summary');
  var lateActions = document.getElementById('pg-late-actions');
  var lateDetail = document.getElementById('pg-late-detail');
  var latePreviewBtn = document.getElementById('pg-late-preview');
  var lateScoreBtn = document.getElementById('pg-late-score');

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }

  function getSession() {
    return queue.getSession ? queue.getSession() : null;
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
    var summaryBits = [];
    if (late.reason && !enabled) {
      summaryBits.push(late.reason);
    } else if (enabled) {
      summaryBits.push('Watching');
    } else {
      summaryBits.push('Not watching');
    }
    if (late.last_summary) summaryBits.push(late.last_summary);
    lateSummary.textContent = summaryBits.join(' · ');
    latePreviewBtn.disabled = !enabled;
    lateScoreBtn.hidden = true;
    lateScoreBtn.disabled = true;
    var initialMissing = (late.initial_missing_user_ids || []).length;
    var knownCount = (late.known_user_ids || []).length;
    var scoredCount = (late.scored_user_ids || []).length;
    var details = [
      '<div class="pg-late-detail-row">Initial missing: ' + initialMissing + '</div>',
      '<div class="pg-late-detail-row">Known in queue: ' + knownCount + '</div>',
      '<div class="pg-late-detail-row">Already appended: ' + scoredCount + '</div>'
    ];
    if (late.last_checked) details.push('<div class="pg-late-detail-row">Last checked: ' + esc(late.last_checked) + '</div>');
    if (late.last_scored) details.push('<div class="pg-late-detail-row">Last scored: ' + esc(late.last_scored) + '</div>');
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
    return fetch('/api/powergrader/session/' + SESSION_ID)
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
    fetch('/api/powergrader/session/' + SESSION_ID + '/late-preview', {method:'POST'})
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
    if (lateSummary) lateSummary.textContent = 'Scoring new late submissions…';
    fetch('/api/powergrader/session/' + SESSION_ID + '/late-score', {method:'POST'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          if (lateSummary) lateSummary.textContent = d.error || 'Late scoring failed.';
          if (queue.showStatus) queue.showStatus(d.error || 'Late scoring failed.', true);
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
