(function(){
  var setupConfig = window.POWERGRADER_SETUP_CONFIG || {};
  var defaultModel = setupConfig.defaultModel || '';
  var modelPresets = setupConfig.modelPresets || [];
  var modelOptions = [];

  var form = document.getElementById('pg-start-form');
  var courseEl = document.getElementById('pg-course');
  var asnEl = document.getElementById('pg-assignment');
  var modeInput = document.getElementById('pg-mode');
  var modeChoices = Array.from(document.querySelectorAll('input[name="pg-mode-choice"]'));
  var routeCards = Array.from(document.querySelectorAll('.pg-route-card'));
  var aiOptions = document.getElementById('pg-ai-options');
  var rubricFast = document.getElementById('pg-rubric-fast');
  var apiOnly = Array.from(document.querySelectorAll('.pg-api-only'));
  var modelPicker = document.getElementById('pg-model-picker');
  var modelEl = document.getElementById('pg-model');
  var modelPanel = document.getElementById('pg-model-panel');
  var modelList = document.getElementById('pg-model-listbox');
  var modelCost = document.getElementById('pg-model-cost');
  var btnModelMenu = document.getElementById('pg-model-menu-button');
  var btnModelDefault = document.getElementById('pg-model-default');
  var btnLoadModels = document.getElementById('pg-load-models');
  var modelStatus = document.getElementById('pg-model-status');
  var sourceFiles = document.getElementById('pg-source-files');
  var sourceFilesJson = document.getElementById('pg-source-files-json');
  var responseKind = document.getElementById('pg-response-kind');
  var btnEstimate = document.getElementById('pg-estimate');
  var estimateStatus = document.getElementById('pg-estimate-status');
  var estimatePanel = document.getElementById('pg-estimate-panel');
  var startBtn = document.getElementById('pg-start-btn');
  var status = document.getElementById('pg-start-status');
  var privacyRun = document.getElementById('pg-privacy-run');
  var privacyList = document.getElementById('pg-privacy-list');
  var aiLabel = document.getElementById('pg-ai-label');

  function modelScenarioText(m) {
    if (m.scenario_cost === null || m.scenario_cost === undefined || isNaN(Number(m.scenario_cost))) return '';
    var n = Number(m.scenario_cost);
    return '30 essays est. ' + (n < 0.01 ? '<$0.01' : '$' + n.toFixed(2));
  }

  function priceText(v) {
    if (v === null || v === undefined || isNaN(Number(v))) return 'n/a';
    var n = Number(v);
    if (n === 0) return '$0';
    if (n < 1) return '$' + n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
    return '$' + n.toFixed(2);
  }

  function whole(n) {
    var x = Number(n || 0);
    return x.toLocaleString();
  }

  function modelCostText(m) {
    if (!m) return '';
    var price = 'Input ' + priceText(m.input_per_mtok) + '/M · Output ' + priceText(m.output_per_mtok) + '/M';
    var scenario = modelScenarioText(m);
    var tier = m.cost_tier || costTier(scenario);
    return price + (scenario ? ' · ' + scenario : '');
  }

  function normalizeModelOption(m, source) {
    var input = m.input_per_mtok;
    var output = m.output_per_mtok;
    var scenario = m.scenario_cost;
    var tier = m.cost_tier || costTier(scenario);
    return {
      id: m.id || '',
      label: m.label || m.name || m.id || '',
      note: m.note || (source === 'live' ? 'Current OpenRouter listing' : ''),
      input_per_mtok: input,
      output_per_mtok: output,
      scenario_cost: scenario,
      cost_tier: tier,
      source: source || m.source || 'preset'
    };
  }

  function costTier(cost) {
    var n = Number(cost);
    if (isNaN(n)) return '$?';
    if (n < 0.10) return '$';
    if (n < 0.50) return '$$';
    return '$$$';
  }

  function tierClass(tier) {
    return tier === '$$$' ? ' high' : (tier === '$$' ? ' mid' : (tier === '$?' ? ' unknown' : ''));
  }

  function resetModelOptions() {
    modelOptions = (modelPresets || []).map(function(m){ return normalizeModelOption(m, 'preset'); });
    modelOptions.push({
      id: 'openrouter/auto',
      label: 'Auto Router',
      note: 'Advanced; variable cost; exact estimate unavailable',
      input_per_mtok: null,
      output_per_mtok: null,
      scenario_cost: null,
      cost_tier: '$?',
      source: 'special'
    });
  }

  function mergeModelOptions(rows, source) {
    var byId = {};
    modelOptions.forEach(function(m){ byId[m.id] = m; });
    (rows || []).forEach(function(row){
      if (!row || !row.id) return;
      var live = normalizeModelOption(row, source || 'live');
      if (byId[live.id]) {
        Object.assign(byId[live.id], {
          input_per_mtok: live.input_per_mtok,
          output_per_mtok: live.output_per_mtok,
          scenario_cost: live.scenario_cost,
          cost_tier: live.cost_tier
        });
      } else {
        modelOptions.push(live);
        byId[live.id] = live;
      }
    });
    modelOptions.sort(function(a, b){
      var aLatest = a.id.indexOf('latest') !== -1 ? 0 : 1;
      var bLatest = b.id.indexOf('latest') !== -1 ? 0 : 1;
      if (a.source === 'preset' && b.source !== 'preset') return -1;
      if (b.source === 'preset' && a.source !== 'preset') return 1;
      if (aLatest !== bLatest) return aLatest - bLatest;
      return a.label.localeCompare(b.label);
    });
  }

  function findModelOption(id) {
    return modelOptions.find(function(m){ return m.id === id; }) || null;
  }

  function updateModelCost() {
    if (!modelCost || !modelEl) return;
    var m = findModelOption(modelEl.value);
    if (!m) {
      modelCost.textContent = 'Custom model ID. Cost guard will verify live pricing before sending.';
      return;
    }
    modelCost.textContent = m.cost_tier + ' · ' + modelCostText(m) +
      (m.cost_tier === '$$$' ? ' · premium; review before class-scale scoring' : '');
  }

  function renderModelOptions(query) {
    if (!modelList) return;
    var q = String(query || '').trim().toLowerCase();
    var rows = modelOptions.filter(function(m){
      if (!q) return true;
      return (m.id + ' ' + m.label + ' ' + m.note).toLowerCase().indexOf(q) !== -1;
    }).slice(0, 80);
    if (!rows.length) {
      modelList.innerHTML = '<div class="pg-model-empty">No preset matches. You can still type an exact OpenRouter model ID.</div>';
      return;
    }
    modelList.innerHTML = rows.map(function(m){
      var selected = modelEl && modelEl.value === m.id;
      var tier = m.cost_tier || costTier(m.scenario_cost);
      var pill = '<span class="pg-model-pill' + tierClass(tier) + '">' + _esc(tier) + '</span>';
      return '<button type="button" class="pg-model-row' + (selected ? ' is-selected' : '') + '" role="option" data-model-id="' + _esc(m.id) + '">' +
        '<strong>' + _esc(m.label || m.id) + pill + '</strong>' +
        '<div class="pg-model-id">' + _esc(m.id) + '</div>' +
        '<div class="pg-model-meta">' + _esc(modelCostText(m)) + '</div>' +
        (m.note ? '<div class="pg-model-meta">' + _esc(m.note) + '</div>' : '') +
        '</button>';
    }).join('');
  }

  function setModelPanel(open, query) {
    if (!modelPanel || !modelEl) return;
    if (open) renderModelOptions(query || '');
    modelPanel.hidden = !open;
    modelEl.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  resetModelOptions();
  updateModelCost();

  var aiPacketPrivacyPlan = [
    {id:'download', label:'Download submitted work from Canvas', status:'running', detail:'Fetching only this assignment.'},
    {id:'source_context', label:'Load shared source material', status:'pending', detail:'Excerpts are sent once as shared context for the batch.'},
    {id:'pseudonymize', label:'Assign pseudonyms and separate identities', status:'pending', detail:'Real names stay in the local vault.'},
    {id:'safety_scan', label:'Scan for real names before any LLM call', status:'pending', detail:'Hard matches become yellow or red before sending.'},
    {id:'safe_private', label:'Write Safe AI Packet and Private decoder', status:'pending', detail:'The packet uses fake names. The decoder stays local.'},
    {id:'safe_ai_packet', label:'Create Safe AI Packet ZIP', status:'pending', detail:'Ready for your AI chat or the API route.'}
  ];

  var apiPrivacyTail = [
    {id:'safe_payload', label:'Load the Safe AI Packet for scoring', status:'pending', detail:'The inspected packet is the LLM payload.'},
    {id:'price_check', label:'Verify model price estimate', status:'pending', detail:'Premium models are allowed when pricing is known.'},
    {id:'llm_send', label:'Send only the Safe AI Packet to OpenRouter', status:'pending', detail:'No real names are included.'},
    {id:'reidentify', label:'Reattach real names locally', status:'pending', detail:'Results are joined back on this machine before review.'}
  ];

  function privacyPlanForMode(mode) {
    if (mode === 'assisted') return aiPacketPrivacyPlan.concat(apiPrivacyTail);
    if (mode === 'packet') {
      return aiPacketPrivacyPlan.concat([
        {id:'manual_ai_chat', label:'Ready for your AI chat', status:'pending', detail:'Nothing is sent automatically.'}
      ]);
    }
    return [{id:'download', label:'Download submitted work from Canvas', status:'running', detail:'Grade Myself stays local and skips AI packet creation.'}];
  }

  function renderPrivacySteps(steps) {
    if (!privacyRun || !privacyList) return;
    privacyRun.hidden = false;
    privacyList.innerHTML = (steps || []).map(function(step){
      var status = step.status || 'pending';
      var light = status === 'ok' ? 'ok' : (status === 'warn' ? 'warn' : (status === 'failed' ? 'failed' : (status === 'running' ? 'running' : '')));
      var pathButton = step.path
        ? '<div class="pg-privacy-actions-inline"><button type="button" class="small" data-open-path="' + _esc(step.path) + '">' + _esc(step.action_label || 'Open file') + '</button></div>'
        : '';
      return '<div class="pg-privacy-step">' +
        '<span class="pg-light ' + light + '"></span>' +
        '<div><div class="pg-privacy-label">' + _esc(step.label || step.id || 'Step') + '</div>' +
        (step.detail ? '<div class="pg-privacy-detail">' + _esc(step.detail) + '</div>' : '') +
        pathButton +
        '</div></div>';
    }).join('');
  }

  function selectedSourceFiles() {
    if (!sourceFiles) return [];
    return Array.from(sourceFiles.selectedOptions || []).map(function(o){ return o.value; }).filter(Boolean);
  }

  function syncSourceFilesJson() {
    if (sourceFilesJson) sourceFilesJson.value = JSON.stringify(selectedSourceFiles());
  }

  function renderEstimate(d) {
    if (!estimatePanel) return;
    var t = d.tokens || {};
    var cost = d.estimated_cost_label || 'unavailable';
    var materials = (d.materials || []).map(function(m){
      return '<div>' + _esc(m.title || m.source || 'Source') + ': ~' + whole(m.tokens_est) + ' tokens</div>';
    }).join('');
    var warnings = (d.warnings || []).map(function(w){ return '<li>' + _esc(w) + '</li>'; }).join('');
    estimatePanel.innerHTML =
      '<div class="pg-estimate-grid">' +
        '<div><strong>Students</strong><br>' + whole(d.student_count) + ' <span class="hint">(' + _esc(d.count_basis || 'estimate') + ')</span></div>' +
        '<div><strong>Estimated cost</strong><br>' + _esc(cost) + '</div>' +
        '<div><strong>Input tokens</strong><br>' + whole(t.estimated_input) + '</div>' +
        '<div><strong>Output tokens</strong><br>' + whole(t.estimated_output) + '</div>' +
        '<div><strong>Source material</strong><br>' + whole(t.source_materials) + '</div>' +
        '<div><strong>Student preset</strong><br>' + _esc(d.response_label || '') + '</div>' +
      '</div>' +
      (materials ? '<div class="pg-estimate-materials">' + materials + '</div>' : '') +
      '<p class="hint" style="margin:8px 0 0">' + _esc(d.caching_note || '') + '</p>' +
      (warnings ? '<ul class="pg-estimate-warnings">' + warnings + '</ul>' : '');
    estimatePanel.hidden = false;
  }

  btnEstimate && btnEstimate.addEventListener('click', function(){
    var cid = courseEl.value;
    var aid = asnEl.value;
    if (!cid || !aid) {
      if (estimateStatus) estimateStatus.textContent = 'Select a course and assignment first.';
      return;
    }
    syncSourceFilesJson();
    btnEstimate.disabled = true;
    if (estimateStatus) estimateStatus.textContent = 'Estimating...';
    var fd = new FormData(form);
    fd.set('course_id', cid);
    fd.set('assignment_id', aid);
    fd.set('model_id', (modelEl && modelEl.value) || defaultModel);
    fd.set('persona_id', document.getElementById('pg-persona')?.value || 'sage');
    fd.set('response_kind', responseKind?.value || 'scr');
    fetch('/api/powergrader/estimate', {method:'POST', body: fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          if (estimateStatus) estimateStatus.textContent = d.error || 'Estimate failed.';
          return;
        }
        renderEstimate(d);
        if (estimateStatus) estimateStatus.textContent = 'Estimate ready.';
      })
      .catch(function(e){ if (estimateStatus) estimateStatus.textContent = String(e); })
      .finally(function(){ btnEstimate.disabled = false; });
  });

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

  modeChoices.forEach(function(el){ el.addEventListener('change', updateRouteMode); });
  updateRouteMode();

  modelEl && modelEl.addEventListener('input', function(){
    if (currentMode() === 'assisted') {
      if (aiLabel) aiLabel.textContent = 'Auto-Score With API — OpenRouter · ' + (modelEl.value || defaultModel);
    }
    setModelPanel(true, modelEl.value);
    updateModelCost();
  });

  modelEl && modelEl.addEventListener('focus', function(){
    setModelPanel(true, '');
  });

  btnModelMenu && btnModelMenu.addEventListener('click', function(){
    if (!modelPanel) return;
    var shouldOpen = modelPanel.hidden;
    setModelPanel(shouldOpen, '');
    if (shouldOpen && modelEl) modelEl.focus();
  });

  modelList && modelList.addEventListener('click', function(e){
    var btn = e.target.closest('[data-model-id]');
    if (!btn || !modelEl) return;
    modelEl.value = btn.getAttribute('data-model-id') || '';
    setModelPanel(false, '');
    updateModelCost();
    if (currentMode() === 'assisted' && aiLabel) aiLabel.textContent = 'Auto-Score With API — OpenRouter · ' + (modelEl.value || defaultModel);
    modelEl.focus();
  });

  document.addEventListener('click', function(e){
    if (modelPicker && !modelPicker.contains(e.target)) setModelPanel(false, '');
  });

  modelEl && modelEl.addEventListener('keydown', function(e){
    if (e.key === 'Escape') setModelPanel(false, '');
  });

  btnModelDefault && btnModelDefault.addEventListener('click', function(){
    if (modelEl) modelEl.value = defaultModel;
    if (modelStatus) modelStatus.textContent = 'Default selected.';
    if (currentMode() === 'assisted' && aiLabel) aiLabel.textContent = 'Auto-Score With API — OpenRouter · ' + defaultModel;
    updateModelCost();
  });

  btnLoadModels && btnLoadModels.addEventListener('click', function(){
    if (!modelList) return;
    btnLoadModels.disabled = true;
    btnLoadModels.textContent = 'Loading…';
    if (modelStatus) modelStatus.textContent = 'Loading OpenRouter models and latest aliases…';
    Promise.all([
      fetch('/settings/openrouter/models?q=latest&limit=300').then(function(r){ return r.json(); }).catch(function(e){ return {ok:false,error:String(e)}; }),
      fetch('/settings/openrouter/models?limit=300').then(function(r){ return r.json(); }).catch(function(e){ return {ok:false,error:String(e)}; })
    ])
      .then(function(results){
        var latest = results[0], all = results[1];
        if (!latest.ok && !all.ok) {
          if (modelStatus) modelStatus.textContent = 'Could not load models.';
          return;
        }
        resetModelOptions();
        mergeModelOptions((latest.models || []), 'live');
        mergeModelOptions((all.models || []), 'live');
        renderModelOptions('');
        updateModelCost();
        if (modelStatus) modelStatus.textContent = 'Loaded ' + (((latest.models || []).length) + ((all.models || []).length)) + ' searchable model rows with prices.';
        modelEl && modelEl.focus();
      })
      .catch(function(){ if (modelStatus) modelStatus.textContent = 'Could not load models.'; })
      .finally(function(){
        btnLoadModels.disabled = false;
        btnLoadModels.textContent = 'Load latest model list';
      });
  });

  // Load assignments when course changes
  courseEl && courseEl.addEventListener('change', function(){
    var cid = courseEl.value;
    if (!cid) { asnEl.disabled = true; asnEl.innerHTML = '<option value="">— select course first —</option>'; loadSessions(); return; }
    asnEl.disabled = true;
    asnEl.innerHTML = '<option value="">Loading…</option>';
    fetch('/api/assignments-full?course_id=' + encodeURIComponent(cid))
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok || !d.assignments) {
          asnEl.innerHTML = '<option value="">— failed to load —</option>';
          return;
        }
        // Only gradeable submission types
        var gradeable = d.assignments.filter(function(a){
          var t = a.submission_types || [];
          return t.some(function(x){ return ['online_text_entry','online_upload','online_url','media_recording','student_annotation'].indexOf(x) > -1; });
        });
        asnEl.innerHTML = '<option value="">— select an assignment —</option>' +
          gradeable.map(function(a){ return '<option value="' + a.id + '">' + _esc(a.name) + '</option>'; }).join('');
        asnEl.disabled = false;
        loadSessions(cid);
      })
      .catch(function(){ asnEl.innerHTML = '<option value="">Error loading assignments</option>'; });
  });

  // Sync fast-mode rubric to AI rubric select so only one is submitted
  document.getElementById('pg-rubric-fast-sel') && document.getElementById('pg-rubric-fast-sel').addEventListener('change', function(){
    var aiRubric = document.getElementById('pg-rubric');
    if (aiRubric) aiRubric.value = this.value;
  });
  document.getElementById('pg-rubric') && document.getElementById('pg-rubric').addEventListener('change', function(){
    var fastRubric = document.getElementById('pg-rubric-fast-sel');
    if (fastRubric) fastRubric.value = this.value;
  });

  // Start session
  form && form.addEventListener('submit', function(ev){
    ev.preventDefault();
    var cid = courseEl.value;
    var aid = asnEl.value;
    if (!cid || !aid) { setStatus('Select a course and assignment first.', true); return; }
    startBtn.disabled = true;
    var mode = modeInput.value;
    renderPrivacySteps(privacyPlanForMode(mode));
    setStatus(mode === 'assisted'
      ? 'Fetching submissions, building a Safe AI Packet, then scoring with ' + ((modelEl && modelEl.value) || defaultModel) + '…'
      : (mode === 'packet'
        ? 'Fetching submissions and building a Safe AI Packet…'
        : 'Fetching submissions…'), false);
    syncSourceFilesJson();
    var fd = new FormData(form);
    // Ensure rubric_name comes from whichever picker is visible
    fetch('/api/powergrader/start', {method:'POST', body: fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d.ok) {
          setStatus((d.mode_label || 'Session') + ' created (' + d.student_count + ' students)…', false);
          window.location.href = '/powergrader/session/' + d.session_id;
        } else {
          if (d.privacy_steps) renderPrivacySteps(d.privacy_steps);
          setStatus(d.error || 'Failed to start session.', true);
          startBtn.disabled = false;
        }
      })
      .catch(function(e){ setStatus(String(e), true); startBtn.disabled = false; });
  });

  function setStatus(msg, err){
    status.textContent = msg;
    status.style.color = err ? 'var(--ce-red, #c0392b)' : '';
  }

  function _esc(s){ var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

  // Load existing sessions for selected course
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
          var pct = s.total ? Math.round((s.posted / s.total) * 100) : 0;
          var dt = s.created ? s.created.replace('T', ' ').slice(0,16) : '';
          return '<tr>' +
            '<td><strong>' + _esc(s.assignment_name || '—') + '</strong></td>' +
            '<td>' + _esc(s.mode_label || modeLabel(s.mode)) + '</td>' +
            '<td style="text-align:center">' + s.posted + ' / ' + s.total + ' posted</td>' +
            '<td style="color:var(--ce-text-muted,#888)">' + dt + '</td>' +
            '<td><a href="/powergrader/session/' + s.session_id + '" class="button small">Resume →</a></td>' +
            '</tr>';
        }).join('');
      })
      .catch(function(){});
  }

  // Load sessions on page load
  loadSessions('');
})();
