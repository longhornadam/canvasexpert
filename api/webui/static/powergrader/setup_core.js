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
  var automaticRefreshStarted = {};
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
  var refreshBtn = document.getElementById('pg-refresh-assignment');
  var folderBtn = document.getElementById('pg-open-assignment-folder');
  var evidenceStatus = document.getElementById('pg-evidence-status');
  var syncCourseBtn = document.getElementById('pg-sync-course-list');
  var catalogStatus = document.getElementById('pg-course-catalog-status');

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
    aiOptions.hidden = !isAi;
    rubricFast.hidden = isAi;
    apiOnly.forEach(function(el){ el.hidden = mode !== 'assisted'; });
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
    if (ackWrap) ackWrap.hidden = !isAi;
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
    if (refreshBtn) refreshBtn.disabled = !(setupConfig.hasWorkspace && cid && aid);
    if (folderBtn) folderBtn.disabled = !(setupConfig.hasWorkspace && cid && aid);
    if (syncCourseBtn && !syncCourseBtn.dataset.syncing) syncCourseBtn.disabled = !(setupConfig.hasWorkspace && cid);
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
    return a.due_at ? " (due " + String(a.due_at).slice(0, 10) + ")" : "";
  }

  function assignmentMatchesSearch(a, query) {
    if (!query) return true;
    var moduleNames = loadedModules.filter(function(module){
      return assignmentBelongsToModule(a, module);
    }).map(function(module){ return module.name || ""; });
    var text = [a.name || "", a.description_text || ""].concat(moduleNames).join(" ").toLowerCase();
    return text.indexOf(query.toLowerCase()) > -1;
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

  function fillModulePicker(preferredValue) {
    if (!asnGroupByEl) return;
    asnGroupByEl.innerHTML = '<option value="last_three">Last 3 modules</option>' +
      loadedModules.map(function(module){
        return '<option value="' + esc(module.id) + '">' + esc(module.name) + '</option>';
      }).join('');
    var wanted = preferredValue || 'last_three';
    asnGroupByEl.value = Array.from(asnGroupByEl.options).some(function(option){ return option.value === wanted; })
      ? wanted : 'last_three';
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
          return '<option value="" disabled>' + esc(a.name) + ' (' + unsupportedQuizLabel(a) + ' - not supported)</option>';
        }).join('');
        html += '</optgroup>';
      }
    } else if (activeModules.length) {
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
          return '<option value="" disabled>' + esc(a.name) + ' (' + unsupportedQuizLabel(a) + ' - not supported)</option>';
        }).join('');
        html += '</optgroup>';
      });
    } else if (loadedAssignments.length || unsupportedQuizAssignments.length) {
      groupCount = 1;
      visibleQuizCount = unsupportedQuizAssignments.length;
      html += '<optgroup label="All assignments — module list unavailable">';
      html += loadedAssignments.map(function(a){
        var sel = a.id === selectedVal ? ' selected' : '';
        return '<option value="' + esc(a.id) + '"' + sel + '>' + esc(a.name) + esc(assignmentDueLabel(a)) + '</option>';
      }).join('');
      html += unsupportedQuizAssignments.map(function(a){
        return '<option value="" disabled>' + esc(a.name) + ' (' + unsupportedQuizLabel(a) + ' - not supported)</option>';
      }).join('');
      html += '</optgroup>';
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
    activeModules = cached || [];
    renderAssignmentOptions();
    syncStartEnabled();
  }

  function catalogTimestamp(data) {
    var scopes = data && data.scopes || {};
    return (scopes.assignments && scopes.assignments.last_success_at) ||
      (scopes.modules && scopes.modules.last_success_at) || data.updated_at || "";
  }

  function shortTimestamp(value) {
    if (!value) return "an earlier sync";
    var parsed = new Date(value);
    return isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  }

  function catalogStateMessage(data, prefix) {
    var scopes = data && data.scopes || {};
    var states = [scopes.assignments && scopes.assignments.state, scopes.modules && scopes.modules.state].filter(Boolean);
    var imperfect = states.filter(function(value){ return value !== 'current'; });
    var message = prefix || (imperfect.length ? 'Using local course list' : 'Course list synced');
    message += ' from ' + shortTimestamp(catalogTimestamp(data)) + '.';
    if (imperfect.length) message += ' Some catalog data is ' + imperfect.join('/') + '.';
    if ((data.warnings || []).indexOf('competing_catalog_files') > -1) message += ' A competing OneDrive catalog copy needs review.';
    return message;
  }

  function setCatalogStatus(message, isError) {
    if (!catalogStatus) return;
    catalogStatus.textContent = message || '';
    catalogStatus.classList.toggle('is-error', !!isError);
  }

  function applyCatalog(data, options) {
    options = options || {};
    var selectedAssignment = options.selectedAssignment !== undefined ? options.selectedAssignment : asnEl.value;
    var selectedModule = options.selectedModule !== undefined
      ? options.selectedModule : (asnGroupByEl ? asnGroupByEl.value : 'last_three');
    var searchValue = options.searchValue !== undefined
      ? options.searchValue : (asnSearchEl ? asnSearchEl.value : '');
    var loaded = data.assignments || [];
    loadedAssignments = loaded.filter(function(a){ return isPowerGraderStartable(a) || a.is_quiz_lti_assignment === true; });
    unsupportedQuizAssignments = loaded.filter(function(a){
      return isQuizAssignment(a) && a.is_quiz_lti_assignment !== true && !isPowerGraderStartable(a);
    });
    loadedModules = data.modules || [];
    moduleCache = {};
    cacheSelectedModules(loadedModules);
    fillModulePicker(selectedModule);
    activeModules = cachedModulesForSelection(asnGroupByEl ? asnGroupByEl.value : 'last_three') || [];
    if (asnSearchEl) asnSearchEl.value = searchValue;
    asnEl.value = selectedAssignment || '';
    renderAssignmentOptions();
    if (asnToolsEl) asnToolsEl.hidden = !(loadedModules.length || loadedAssignments.length || unsupportedQuizAssignments.length);
    syncStartEnabled();
  }

  function refreshCourseCatalog(cid, version, explicit) {
    if (!cid || !setupConfig.hasWorkspace) return Promise.resolve();
    if (!explicit) {
      if (automaticRefreshStarted[cid]) return Promise.resolve();
      automaticRefreshStarted[cid] = true;
    }
    if (syncCourseBtn) {
      syncCourseBtn.dataset.syncing = 'true';
      syncCourseBtn.disabled = true;
    }
    setCatalogStatus(explicit ? 'Syncing course list from Canvas…' : 'Checking Canvas for course-list updates…', false);
    return fetch('/api/course-catalog/refresh', {
      method: 'POST',
      body: new URLSearchParams({course_id: cid})
    }).then(function(r){ return r.json(); }).then(function(data){
      if (version !== loadVersion || activeCourseId !== cid) return;
      if (!data.ok || !data.available) {
        if (loadedAssignments.length || loadedModules.length) {
          setCatalogStatus('Using the local course list; Canvas sync failed. You can retry with Sync course list.', true);
          asnEl.disabled = false;
        } else {
          asnEl.disabled = true;
          asnEl.innerHTML = '<option value="">— course list unavailable —</option>';
          setCatalogStatus((data && data.error) || 'The course list is unavailable. Try Sync course list.', true);
        }
        return;
      }
      applyCatalog(data);
      setCatalogStatus(catalogStateMessage(data, data.source === 'previous' ? 'Using previous local course list' : ''), false);
      if (typeof pg.loadSessions === 'function') pg.loadSessions(cid);
    }).catch(function(){
      if (version !== loadVersion || activeCourseId !== cid) return;
      if (loadedAssignments.length || loadedModules.length) {
        asnEl.disabled = false;
        setCatalogStatus('Using the local course list; Canvas sync failed. You can retry with Sync course list.', true);
      } else {
        asnEl.disabled = true;
        asnEl.innerHTML = '<option value="">— course list unavailable —</option>';
        setCatalogStatus('The course list is unavailable. Try Sync course list.', true);
      }
    }).finally(function(){
      if (version === loadVersion && activeCourseId === cid) {
        if (syncCourseBtn) delete syncCourseBtn.dataset.syncing;
        syncStartEnabled();
      }
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
      setCatalogStatus('', false);
      if (typeof pg.loadSessions === 'function') pg.loadSessions('');
      return;
    }
    if (!setupConfig.hasWorkspace) {
      asnEl.disabled = true;
      asnEl.innerHTML = '<option value="">— configure workspace first —</option>';
      setCatalogStatus('Finish workspace setup in Settings before building a local course list.', true);
      if (typeof pg.loadSessions === 'function') pg.loadSessions(cid);
      return;
    }
    asnEl.disabled = true;
    asnEl.innerHTML = '<option value="">Opening local course list…</option>';
    setCatalogStatus('Opening the last local course list…', false);
    if (asnToolsEl) asnToolsEl.hidden = true;
    if (unsupportedHintEl) unsupportedHintEl.hidden = true;
    loadedAssignments = [];
    unsupportedQuizAssignments = [];
    loadedModules = [];
    activeModules = [];
    moduleCache = {};
    fetch('/api/course-catalog?course_id=' + encodeURIComponent(cid))
      .then(function(r){ return r.json(); })
      .then(function(data){
        if (version !== loadVersion || activeCourseId !== cid) return;
        if (!data.ok) {
          asnEl.innerHTML = '<option value="">— course list unavailable —</option>';
          setCatalogStatus(data.error || 'The local course list could not be opened.', true);
          return;
        }
        if (data.available) {
          applyCatalog(data, {selectedAssignment: '', selectedModule: 'last_three', searchValue: ''});
          setCatalogStatus(catalogStateMessage(data, data.source === 'previous' ? 'Using previous local course list' : 'Using local course list'), false);
          if (typeof pg.loadSessions === 'function') pg.loadSessions(cid);
          refreshCourseCatalog(cid, version, false);
          return;
        }
        asnEl.disabled = true;
        asnEl.innerHTML = '<option value="">Syncing first course list…</option>';
        setCatalogStatus('No local course list yet. Syncing from Canvas…', false);
        refreshCourseCatalog(cid, version, false);
      })
      .catch(function(){
        if (version !== loadVersion || activeCourseId !== cid) return;
        asnEl.innerHTML = '<option value="">Syncing first course list…</option>';
        setCatalogStatus('The local course list could not be opened. Trying Canvas once…', true);
        refreshCourseCatalog(cid, version, false);
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

  function bindEvidenceActions() {
    function values(){ return { course_id: courseEl.value, assignment_id: asnEl.value }; }
    if (refreshBtn) refreshBtn.addEventListener('click', function(){
      refreshBtn.disabled = true;
      if (evidenceStatus) evidenceStatus.textContent = 'Refreshing assignment evidence…';
      fetch('/api/powergrader/refresh', {method: 'POST', body: new URLSearchParams(values())})
        .then(function(r){ return r.json(); }).then(function(data){
          if (evidenceStatus) evidenceStatus.textContent = data.ok ? 'Assignment evidence is ' + (data.status || 'incomplete') + '.' : (data.error || 'The focused refresh could not be completed.');
        }).catch(function(){ if (evidenceStatus) evidenceStatus.textContent = 'The focused refresh could not be completed.'; })
        .finally(syncStartEnabled);
    });
    if (folderBtn) folderBtn.addEventListener('click', function(){
      fetch('/api/powergrader/open-assignment-folder', {method: 'POST', body: new URLSearchParams(values())})
        .then(function(r){ return r.json(); }).then(function(data){
          if (evidenceStatus) evidenceStatus.textContent = data.ok ? 'Opened the local assignment folder.' : (data.error || 'The local assignment folder could not be opened.');
        }).catch(function(){ if (evidenceStatus) evidenceStatus.textContent = 'The local assignment folder could not be opened.'; });
    });
  }

  function bindCourseCatalogActions() {
    if (!syncCourseBtn) return;
    syncCourseBtn.addEventListener('click', function(){
      var cid = courseEl ? courseEl.value : '';
      if (!cid) return;
      refreshCourseCatalog(cid, loadVersion, true);
    });
  }

  pg.esc = esc;
  pg.currentMode = currentMode;
  pg.defaultModel = function(){ return defaultModel; };
  pg.getForm = function(){ return form; };
  pg.getElement = function(id){ return document.getElementById(id); };
  pg.setStatus = setStatus;
  pg.setAiLabelText = updateRouteMode;
  pg.syncStartEnabled = syncStartEnabled;
  pg.loadCourseCatalog = loadAssignments;
  pg.syncCourseCatalog = function(){
    return refreshCourseCatalog(activeCourseId, loadVersion, true);
  };

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
  bindEvidenceActions();
  bindCourseCatalogActions();
  if (typeof pg.loadSessions === 'function') pg.loadSessions('');
})();
