(function(){
  "use strict";

  var pg = window.CE_POWERGRADER_SETUP = window.CE_POWERGRADER_SETUP || {};
  var lastCourseId = '';

  function esc(value) {
    var node = document.createElement('div');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML;
  }

  function modeLabel(mode) {
    if (mode === 'packet') return 'Prepare for my AI chat';
    if (mode === 'assisted') return 'Draft-score with OpenRouter';
    return 'Grade myself';
  }

  function createdLabel(value) {
    return value ? String(value).replace('T', ' ').slice(0, 16) : 'Date unavailable';
  }

  function laneFor(session) {
    var approved = Number(session.approved) || 0;
    var total = Number(session.total) || 0;
    var posted = Number(session.posted) || 0;
    if (approved > 0) return 'attention';
    if (total > 0 && posted >= total) return 'completed';
    return 'continue';
  }

  function sessionCard(session, lane) {
    var approved = Number(session.approved) || 0;
    var total = Number(session.total) || 0;
    var posted = Number(session.posted) || 0;
    var attention = lane === 'attention'
      ? '<p class="pg-session-attention">' + approved + ' approved ' + (approved === 1 ? 'grade is' : 'grades are') + ' ready for reviewed posting.</p>'
      : '';
    return '<article class="pg-session-item">' +
      '<div class="pg-session-main">' +
        '<strong class="pg-session-name">' + esc(session.assignment_name || 'Untitled assignment') + '</strong>' +
        '<div class="pg-session-meta">' +
          '<span>' + esc(session.mode_label || modeLabel(session.mode)) + '</span>' +
          '<span>' + esc(createdLabel(session.created)) + '</span>' +
          '<span>' + posted + ' / ' + total + ' posted</span>' +
        '</div>' + attention +
      '</div>' +
      '<a href="/powergrader/session/' + encodeURIComponent(String(session.session_id || '')) + '" class="button small pg-session-resume">Resume</a>' +
    '</article>';
  }

  function emptyState(lane) {
    return 'None.';
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = String(value);
  }

  function renderLane(lane, sessions) {
    var target = document.getElementById('pg-' + lane + '-list');
    if (!target) return;
    target.innerHTML = sessions.length
      ? sessions.map(function(session){ return sessionCard(session, lane); }).join('')
      : '<p class="pg-session-empty">' + esc(emptyState(lane)) + '</p>';
  }

  function renderSessions(sessions, courseId) {
    var filtered = courseId
      ? sessions.filter(function(session){ return String(session.course_id) === String(courseId); })
      : sessions;
    var lanes = {attention: [], continue: [], completed: []};
    filtered.forEach(function(session){ lanes[laneFor(session)].push(session); });

    renderLane('attention', lanes.attention);
    renderLane('continue', lanes.continue);
    renderLane('completed', lanes.completed);
    setText('pg-attention-count', lanes.attention.length);
    setText('pg-continue-count', lanes.continue.length);
    setText('pg-completed-count', lanes.completed.length);
    setText('pg-completed-summary-count', lanes.completed.length);
    setText('pg-rail-attention-count', lanes.attention.length);
    setText('pg-rail-continue-count', lanes.continue.length);
    setText('pg-sessions-status', courseId
      ? filtered.length + (filtered.length === 1 ? ' local session in this course' : ' local sessions in this course')
      : filtered.length + (filtered.length === 1 ? ' local session' : ' local sessions'));
  }

  function renderError() {
    ['attention', 'continue', 'completed'].forEach(function(lane){
      var target = document.getElementById('pg-' + lane + '-list');
      if (target) target.innerHTML = '<p class="pg-session-empty pg-session-error">Sessions could not be loaded. Try refreshing this page.</p>';
    });
    ['pg-attention-count', 'pg-continue-count', 'pg-completed-count', 'pg-completed-summary-count', 'pg-rail-attention-count', 'pg-rail-continue-count'].forEach(function(id){ setText(id, 0); });
    setText('pg-sessions-status', 'Could not load sessions');
  }

  function loadSessions(courseId) {
    lastCourseId = courseId || '';
    setText('pg-sessions-status', 'Loading sessions…');
    return fetch('/api/powergrader/sessions')
      .then(function(response){
        if (!response.ok) throw new Error('Session request failed');
        return response.json();
      })
      .then(function(data){
        if (data.ok === false) throw new Error(data.error || 'Session request failed');
        renderSessions(data.sessions || [], lastCourseId);
      })
      .catch(function(){ renderError(); });
  }

  pg.loadSessions = loadSessions;
})();
