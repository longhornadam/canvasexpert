(function(){
  "use strict";

  var pg = window.CE_POWERGRADER_SETUP = window.CE_POWERGRADER_SETUP || {};
  var setupConfig = window.POWERGRADER_SETUP_CONFIG || {};
  var defaultModel = setupConfig.defaultModel || '';

  var form = document.getElementById('pg-start-form');
  var courseEl = document.getElementById('pg-course');
  var asnEl = document.getElementById('pg-assignment');
  var modeInput = document.getElementById('pg-mode');
  var modeChoices = Array.from(document.querySelectorAll('input[name="pg-mode-choice"]'));
  var routeCards = Array.from(document.querySelectorAll('.pg-route-card'));
  var aiOptions = document.getElementById('pg-ai-options');
  var rubricFast = document.getElementById('pg-rubric-fast');
  var apiOnly = Array.from(document.querySelectorAll('.pg-api-only'));
  var modelEl = document.getElementById('pg-model');
  var startBtn = document.getElementById('pg-start-btn');
  var status = document.getElementById('pg-start-status');
  var aiLabel = document.getElementById('pg-ai-label');

  function modeLabel(mode) {
    if (mode === 'packet') return 'Use My AI Chat';
    if (mode === 'assisted') return 'Auto-Score With API';
    return 'Grade Myself';
  }

  function currentMode() {
    var checked = modeChoices.find(function(el){ return el.checked; });
    return checked ? checked.value : 'fast';
  }

  function updateRouteMode() {
    var mode = currentMode();
    modeInput.value = mode;
    routeCards.forEach(function(card){
      var input = card.querySelector('input[type="radio"]');
      card.classList.toggle('is-selected', !!input && input.checked);
    });
    var isAi = mode === 'packet' || mode === 'assisted';
    aiOptions.style.display = isAi ? '' : 'none';
    rubricFast.style.display = isAi ? 'none' : '';
    apiOnly.forEach(function(el){ el.style.display = mode === 'assisted' ? '' : 'none'; });
    if (mode === 'packet') {
      if (aiLabel) aiLabel.textContent = 'Use My AI Chat — create a Safe AI Packet, then paste AI JSON back into PowerGrader.';
    } else if (mode === 'assisted') {
      if (aiLabel) aiLabel.textContent = 'Auto-Score With API — OpenRouter · ' + ((modelEl && modelEl.value) || defaultModel);
    } else {
      if (aiLabel) aiLabel.textContent = 'Grade Myself — no AI packet or API call.';
    }
  }

  function setStatus(msg, err){
    status.textContent = msg;
    status.style.color = err ? 'var(--ce-red, #c0392b)' : '';
  }

  function esc(s){ var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

  function renderStartError(d) {
    if (d.privacy_steps && typeof pg.renderPrivacySteps === 'function') {
      pg.renderPrivacySteps(d.privacy_steps);
    }
    setStatus(d.error || 'Failed to start session.', true);
    startBtn.disabled = false;
  }

  function loadAssignments(cid) {
    if (!asnEl) return;
    if (!cid) {
      asnEl.disabled = true;
      asnEl.innerHTML = '<option value="">— select course first —</option>';
      loadSessions();
      return;
    }
    asnEl.disabled = true;
    asnEl.innerHTML = '<option value="">Loading…</option>';
    fetch('/api/assignments-full?course_id=' + encodeURIComponent(cid))
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok || !d.assignments) {
          asnEl.innerHTML = '<option value="">— failed to load —</option>';
          return;
        }
        var gradeable = d.assignments.filter(function(a){
          var t = a.submission_types || [];
          return t.some(function(x){ return ['online_text_entry','online_upload','online_url','media_recording','student_annotation'].indexOf(x) > -1; });
        });
        asnEl.innerHTML = '<option value="">— select an assignment —</option>' +
          gradeable.map(function(a){ return '<option value="' + a.id + '">' + esc(a.name) + '</option>'; }).join('');
        asnEl.disabled = false;
        loadSessions(cid);
      })
      .catch(function(){ asnEl.innerHTML = '<option value="">Error loading assignments</option>'; });
  }

  function bindRubricSync() {
    document.getElementById('pg-rubric-fast-sel') && document.getElementById('pg-rubric-fast-sel').addEventListener('change', function(){
      var aiRubric = document.getElementById('pg-rubric');
      if (aiRubric) aiRubric.value = this.value;
    });
    document.getElementById('pg-rubric') && document.getElementById('pg-rubric').addEventListener('change', function(){
      var fastRubric = document.getElementById('pg-rubric-fast-sel');
      if (fastRubric) fastRubric.value = this.value;
    });
  }

  function bindStartSession() {
    form && form.addEventListener('submit', function(ev){
      ev.preventDefault();
      var cid = courseEl.value;
      var aid = asnEl.value;
      if (!cid || !aid) { setStatus('Select a course and assignment first.', true); return; }
      startBtn.disabled = true;
      var mode = modeInput.value;
      if (typeof pg.renderPrivacySteps === 'function' && typeof pg.privacyPlanForMode === 'function') {
        pg.renderPrivacySteps(pg.privacyPlanForMode(mode));
      }
      setStatus(mode === 'assisted'
        ? 'Fetching submissions, building a Safe AI Packet, then scoring with ' + ((modelEl && modelEl.value) || defaultModel) + '…'
        : (mode === 'packet'
          ? 'Fetching submissions and building a Safe AI Packet…'
          : 'Fetching submissions…'), false);
      if (typeof pg.syncSourceFilesJson === 'function') {
        pg.syncSourceFilesJson();
      }
      var fd = new FormData(form);
      var watchLate = document.getElementById('pg-watch-late');
      fd.set('watch_late', watchLate && watchLate.checked ? 'true' : 'false');
      fetch('/api/powergrader/start', {method:'POST', body: fd})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d.ok) {
            setStatus((d.mode_label || 'Session') + ' created (' + d.student_count + ' students)…', false);
            window.location.href = '/powergrader/session/' + d.session_id;
          } else {
            renderStartError(d);
          }
        })
        .catch(function(e){ setStatus(String(e), true); startBtn.disabled = false; });
    });
  }

  function loadSessions(cid){
    fetch('/api/powergrader/sessions')
      .then(function(r){ return r.json(); })
      .then(function(d){
        var all = d.sessions || [];
        var filtered = cid ? all.filter(function(s){ return s.course_id === cid; }) : all;
        var card = document.getElementById('pg-sessions-card');
        var tbody = document.getElementById('pg-sessions-tbody');
        if (!filtered.length) { card.style.display = 'none'; return; }
        card.style.display = '';
        tbody.innerHTML = filtered.map(function(s){
          var dt = s.created ? s.created.replace('T', ' ').slice(0,16) : '';
          return '<tr>' +
            '<td><strong>' + esc(s.assignment_name || '—') + '</strong></td>' +
            '<td>' + esc(s.mode_label || modeLabel(s.mode)) + '</td>' +
            '<td style="text-align:center">' + s.posted + ' / ' + s.total + ' posted</td>' +
            '<td style="color:var(--ce-text-muted,#888)">' + dt + '</td>' +
            '<td><a href="/powergrader/session/' + s.session_id + '" class="button small">Resume →</a></td>' +
            '</tr>';
        }).join('');
      })
      .catch(function(){});
  }

  pg.esc = esc;
  pg.currentMode = currentMode;
  pg.defaultModel = function(){ return defaultModel; };
  pg.getForm = function(){ return form; };
  pg.getElement = function(id){ return document.getElementById(id); };
  pg.modeLabel = modeLabel;
  pg.loadSessions = loadSessions;
  pg.setStatus = setStatus;
  pg.setAiLabelText = updateRouteMode;

  modeChoices.forEach(function(el){ el.addEventListener('change', updateRouteMode); });
  updateRouteMode();
  courseEl && courseEl.addEventListener('change', function(){ loadAssignments(courseEl.value); });
  bindRubricSync();
  bindStartSession();
  loadSessions('');
})();