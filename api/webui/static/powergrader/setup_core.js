(function(){
  "use strict";

  var pg = window.CE_POWERGRADER_SETUP = window.CE_POWERGRADER_SETUP || {};
  var setupConfig = window.POWERGRADER_SETUP_CONFIG || {};
  var defaultModel = setupConfig.defaultModel || '';

  var form = document.getElementById('pg-start-form');
  var courseEl = document.getElementById('pg-course');
  var asnEl = document.getElementById('pg-assignment');
  var asnSearchEl = document.getElementById('pg-assignment-search');
  var asnGroupByEl = document.getElementById('pg-assignment-group-by');
  var asnToolsEl = document.getElementById('pg-assignment-tools');
  var loadedAssignments = [];
  var unsupportedQuizAssignments = [];
  var loadedModules = [];
  var activeModules = [];
  var moduleCache = {};
  var activeCourseId = '';
  var loadVersion = 0;
  var moduleSelectionVersion = 0;
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
  var unsupportedHintEl = document.getElementById('pg-assignment-unsupported-hint');

  function modeLabel(mode) {
    if (mode === 'packet') return 'Prepare for my AI chat';
    if (mode === 'assisted') return 'Draft-score with OpenRouter';
    return 'Grade myself';
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
      if (aiLabel) aiLabel.textContent = 'Prepare for my AI chat — create a pseudonymized SAFE packet, then paste AI JSON back into PowerGrader.';
    } else if (mode === 'assisted') {
      if (aiLabel) aiLabel.textContent = 'Draft-score with OpenRouter — ' + ((modelEl && modelEl.value) || defaultModel);
    } else {
      if (aiLabel) aiLabel.textContent = 'Grade myself — no AI packet or API call.';
    }
    // Show/hide AI acknowledgement checkbox
    var ackWrap = document.getElementById('pg-ai-check-wrap');
    var ackBox = document.getElementById('pg-ai-check');
    if (ackWrap) ackWrap.style.display = isAi ? '' : 'none';
    if (ackBox && !isAi) ackBox.checked = false;
    // Programmatically expand safety details for AI routes
    var safetyPopout = document.getElementById('pg-safety-popout');
    if (safetyPopout) safetyPopout.open = isAi;
    syncStartEnabled();
  }

  function syncStartEnabled() {
    var cid = courseEl ? courseEl.value : '';
    var aid = asnEl ? asnEl.value : '';
    var mode = currentMode();
    var isAi = mode === 'packet' || mode === 'assisted';
    var ackBox = document.getElementById('pg-ai-check');
    var ackOk = !isAi || (ackBox && ackBox.checked);
    startBtn.disabled = !(setupConfig.hasWorkspace && cid && aid && ackOk);
  }

  function setStatus(msg, err){
    status.textContent = msg;
    status.style.color = err ? 'var(--ce-red, #c0392b)' : '';
  }

  function esc(s){ var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

  /* ── Assignment picker helpers ────────────────────────────────────── */
  function isPowerGraderStartable(a) {
    var t = a.submission_types || [];
    return t.some(function(x){ return ['online_text_entry','online_upload','online_url','media_recording','student_annotation'].indexOf(x) > -1; });
  }

  function isQuizAssignment(a) {
    if (a.is_quiz) return true;
    // Client-side fallback
    var t = a.submission_types || [];
    return t.indexOf('online_quiz') > -1 || a.quiz_id || a.quiz_type || a.is_quiz_lti_assignment;
  }

  function unsupportedQuizLabel(a) {
    var kind = a.quiz_kind || "";
    if (kind === "new_quiz") return "New Quiz";
    if (kind === "classic_quiz") return "Classic Quiz";
    return "Quiz";
  }

  function assignmentDueLabel(a) {
    return a.due_at ? " (due " + a.due_at + ")" : "";
  }

  function assignmentMatchesSearch(a, query) {
    if (!query) return true;
    return String(a.name || "").toLowerCase().indexOf(query.toLowerCase()) > -1;
  }

  function assignmentBelongsToModule(a, module) {
    var assignmentIds = module.assignment_ids || [];
    var quizIds = module.quiz_ids || [];
    return assignmentIds.indexOf(String(a.id)) > -1 ||
      (!!a.quiz_id && quizIds.indexOf(String(a.quiz_id)) > -1);
  }

  function cacheSelectedModules(modules) {
    (modules || []).forEach(function(module){ moduleCache[module.id] = module; });
  }

  function fillModulePicker() {
    if (!asnGroupByEl) return;
    asnGroupByEl.innerHTML = '<option value="last_three">Last 3 modules</option>' +
      loadedModules.map(function(module){
        return '<option value="' + esc(module.id) + '">' + esc(module.name) + '</option>';
      }).join('');
    asnGroupByEl.value = 'last_three';
  }

  function cachedModulesForSelection(value) {
    var ids = value === 'last_three'
      ? loadedModules.slice(-3).map(function(module){ return module.id; })
      : [value];
    if (!ids.every(function(id){ return !!moduleCache[id]; })) return null;
    return ids.map(function(id){ return moduleCache[id]; });
  }

  function renderAssignmentOptions() {
    if (!asnEl) return;
    var query = asnSearchEl ? asnSearchEl.value : "";
    var selectedVal = asnEl.value;
    var html = '<option value="">— select an assignment —</option>';
    var groupCount = 0;
    var visibleQuizCount = 0;
    var seenAssignmentIds = {};
    var seenQuizIds = {};

    if (query) {
      var searchAssignments = loadedAssignments.filter(function(a){ return assignmentMatchesSearch(a, query); });
      var searchQuizzes = unsupportedQuizAssignments.filter(function(a){ return assignmentMatchesSearch(a, query); });
      if (searchAssignments.length || searchQuizzes.length) {
        groupCount = 1;
        visibleQuizCount = searchQuizzes.length;
        html += '<optgroup label="Search results — all modules">';
        html += searchAssignments.map(function(a){
          var sel = a.id === selectedVal ? ' selected' : '';
          return '<option value="' + esc(a.id) + '"' + sel + '>' + esc(a.name) + esc(assignmentDueLabel(a)) + '</option>';
        }).join('');
        html += searchQuizzes.map(function(a){
          return '<option value="" disabled>' + esc(a.name) + ' (' + unsupportedQuizLabel(a) + ' - not supported yet)</option>';
        }).join('');
        html += '</optgroup>';
      }
    } else {
      activeModules.forEach(function(module){
        var assignments = loadedAssignments.filter(function(a){
          return !seenAssignmentIds[a.id] && assignmentBelongsToModule(a, module);
        });
        var quizzes = unsupportedQuizAssignments.filter(function(a){
          return !seenQuizIds[a.id] && assignmentBelongsToModule(a, module);
        });
        if (!assignments.length && !quizzes.length) return;

        groupCount += 1;
        visibleQuizCount += quizzes.length;
        html += '<optgroup label="' + esc(module.name) + '">';
        html += assignments.map(function(a){
          seenAssignmentIds[a.id] = true;
          var sel = a.id === selectedVal ? ' selected' : '';
          return '<option value="' + esc(a.id) + '"' + sel + '>' + esc(a.name) + esc(assignmentDueLabel(a)) + '</option>';
        }).join('');
        html += quizzes.map(function(a){
          seenQuizIds[a.id] = true;
          return '<option value="" disabled>' + esc(a.name) + ' (' + unsupportedQuizLabel(a) + ' - not supported yet)</option>';
        }).join('');
        html += '</optgroup>';
      });
    }

    if (unsupportedHintEl) unsupportedHintEl.hidden = visibleQuizCount === 0;
    if (groupCount === 0) {
      var emptyMessage = query
        ? 'No matching assignments or quizzes in this course'
        : (activeModules.length === 0 ? 'No course modules found' : 'No gradeable assignments in selected module(s)');
      html = '<option value="">' + emptyMessage + '</option>';
    }

    asnEl.innerHTML = html;
    asnEl.disabled = false;

    // If the previously selected value no longer appears, clear it
    if (selectedVal && !Array.from(asnEl.options).some(function(o){ return o.value === selectedVal; })) {
      asnEl.value = "";
    }
  }

  function loadSelectedModules() {
    if (!asnGroupByEl || !activeCourseId) return;
    var value = asnGroupByEl.value || 'last_three';
    var cached = cachedModulesForSelection(value);
    if (cached) {
      activeModules = cached;
      renderAssignmentOptions();
      syncStartEnabled();
      return;
    }

    var version = ++moduleSelectionVersion;
    var url = '/api/powergrader/modules?course_id=' + encodeURIComponent(activeCourseId);
    if (value !== 'last_three') url += '&module_id=' + encodeURIComponent(value);
    asnEl.disabled = true;
    asnEl.innerHTML = '<option value="">Loading module…</option>';
    fetch(url)
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (version !== moduleSelectionVersion || value !== asnGroupByEl.value) return;
        if (!d.ok) {
          asnEl.innerHTML = '<option value="">— failed to load module —</option>';
          return;
        }
        cacheSelectedModules(d.selected_modules);
        activeModules = d.selected_modules || [];
        renderAssignmentOptions();
        syncStartEnabled();
      })
      .catch(function(){
        if (version === moduleSelectionVersion) asnEl.innerHTML = '<option value="">Error loading module</option>';
      });
  }

  function renderStartError(d) {
    if (d.privacy_steps && typeof pg.renderPrivacySteps === 'function') {
      pg.renderPrivacySteps(d.privacy_steps);
    }
    setStatus(d.error || 'Failed to start session.', true);
    startBtn.disabled = false;
  }

  function loadAssignments(cid) {
    if (!asnEl) return;
    var version = ++loadVersion;
    moduleSelectionVersion += 1;
    activeCourseId = cid || '';
    if (!cid) {
      asnEl.disabled = true;
      asnEl.innerHTML = '<option value="">— select course first —</option>';
      loadedAssignments = [];
      unsupportedQuizAssignments = [];
      loadedModules = [];
      activeModules = [];
      moduleCache = {};
      if (asnGroupByEl) asnGroupByEl.innerHTML = '<option value="last_three">Last 3 modules</option>';
      if (asnToolsEl) asnToolsEl.hidden = true;
      if (asnSearchEl) asnSearchEl.value = "";
      if (unsupportedHintEl) unsupportedHintEl.hidden = true;
      loadSessions();
      return;
    }
    asnEl.disabled = true;
    asnEl.innerHTML = '<option value="">Loading…</option>';
    if (asnToolsEl) asnToolsEl.hidden = true;
    if (unsupportedHintEl) unsupportedHintEl.hidden = true;
    loadedAssignments = [];
    unsupportedQuizAssignments = [];
    loadedModules = [];
    activeModules = [];
    moduleCache = {};
    Promise.all([
      fetch('/api/assignments-full?course_id=' + encodeURIComponent(cid)).then(function(r){ return r.json(); }),
      fetch('/api/powergrader/modules?course_id=' + encodeURIComponent(cid)).then(function(r){ return r.json(); })
    ])
      .then(function(results){
        if (version !== loadVersion) return;
        var assignmentsResponse = results[0];
        var modulesResponse = results[1];
        if (!assignmentsResponse.ok || !assignmentsResponse.assignments || !modulesResponse.ok) {
          asnEl.innerHTML = '<option value="">— failed to load —</option>';
          return;
        }
        var loaded = assignmentsResponse.assignments || [];

        var gradeable = loaded.filter(isPowerGraderStartable);
        var quizzes = loaded.filter(function(a){ return isQuizAssignment(a) && !isPowerGraderStartable(a); });
        loadedAssignments = gradeable;
        unsupportedQuizAssignments = quizzes;
        loadedModules = modulesResponse.modules || [];
        cacheSelectedModules(modulesResponse.selected_modules);
        activeModules = modulesResponse.selected_modules || [];
        fillModulePicker();
        if (asnSearchEl) asnSearchEl.value = "";
        renderAssignmentOptions();
        if (asnToolsEl && loadedModules.length > 0) asnToolsEl.hidden = false;
        loadSessions(cid);
      })
      .catch(function(){
        if (version === loadVersion) asnEl.innerHTML = '<option value="">Error loading assignments</option>';
      });
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
  pg.syncStartEnabled = syncStartEnabled;

  modeChoices.forEach(function(el){ el.addEventListener('change', updateRouteMode); });
  updateRouteMode();
  courseEl && courseEl.addEventListener('change', function(){ loadAssignments(courseEl.value); syncStartEnabled(); });
  asnEl && asnEl.addEventListener('change', syncStartEnabled);
  asnSearchEl && asnSearchEl.addEventListener('input', renderAssignmentOptions);
  asnGroupByEl && asnGroupByEl.addEventListener('change', loadSelectedModules);
  var ackBox = document.getElementById('pg-ai-check');
  if (ackBox) ackBox.addEventListener('change', syncStartEnabled);
  bindRubricSync();
  bindStartSession();
  loadSessions('');
})();
