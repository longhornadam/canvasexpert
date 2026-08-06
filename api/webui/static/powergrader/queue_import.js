(function(){
  "use strict";

  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});
  var sessionId = queue.getSessionId ? queue.getSessionId() : document.querySelector('meta[name="session-id"]').content;

  var packetStrip = document.getElementById('pg-packet-strip');
  var packetActions = document.getElementById('pg-packet-actions');
  var copilotBatches = document.getElementById('pg-copilot-batches');
  var legacyImportBox = document.getElementById('pg-legacy-import-box');
  var importJson = document.getElementById('pg-import-json');
  var importFile = document.getElementById('pg-import-result-file');
  var importBtn = document.getElementById('pg-import-results');
  var importStatus = document.getElementById('pg-import-status');

  function esc(s) {
    if (queue.esc) return queue.esc(s);
    var d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }

  function cssEscape(value) {
    if (window.CSS && CSS.escape) return CSS.escape(value);
    return String(value || '').replace(/"/g, '\\"');
  }

  function titleCase(text) {
    text = String(text || 'pending');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function readNote(d) {
    if (!d || d.parsed_count === undefined || d.parsed_count === null) return '';
    return ' Read ' + d.parsed_count + ' result(s) total.';
  }

  function getSession() {
    return queue.getSession ? queue.getSession() : null;
  }

  function getStudents() {
    return queue.getStudents ? queue.getStudents() : [];
  }

  function getCurrentIndex() {
    return queue.getIndex ? queue.getIndex() : 0;
  }

  function renderPacketPanel(s) {
    var artifacts = (s && s.privacy_artifacts) || {};
    var copilot = (s && s.copilot_packet) || {};
    var batches = Array.isArray(copilot.batches) ? copilot.batches : [];
    if (!packetStrip || !packetActions) return;
    if (!artifacts.packet_zip && !batches.length) return;
    packetStrip.hidden = false;
    var buttons = [];
    if (artifacts.packet_folder) {
      buttons.push('<button type="button" class="small" data-open-path="' + esc(artifacts.packet_folder) + '">Open packet folder</button>');
    }
    if (copilot.packet_folder) {
      buttons.push('<button type="button" class="small" data-open-path="' + esc(copilot.packet_folder) + '">Open AI chat batch folder</button>');
    }
    buttons.push('<a class="small" href="/api/powergrader/session/' + encodeURIComponent(sessionId) + '/packet" style="padding:4px 10px;border:1px solid var(--ce-rule);border-radius:var(--r-sm);text-decoration:none;background:var(--card);color:var(--ink)">Download packet ZIP</a>');
    packetActions.innerHTML = buttons.join('');
    if (batches.length) {
      if (legacyImportBox) legacyImportBox.hidden = true;
      if (copilotBatches) {
        copilotBatches.hidden = false;
        copilotBatches.innerHTML = renderCopilotBatches(copilot, batches);
      }
    } else {
      if (legacyImportBox) legacyImportBox.hidden = false;
      if (copilotBatches) {
        copilotBatches.hidden = true;
        copilotBatches.innerHTML = '';
      }
    }
  }

  function renderCopilotBatches(copilot, batches) {
    var imported = batches.filter(function(batch){ return batch.status === 'imported'; }).length;
    var loaded = getStudents().filter(function(st){
      return st.ai_score !== null && st.ai_score !== undefined || !!(st.ai_feedback || '').trim();
    }).length;
    var total = copilot.student_count || getStudents().length || 0;
    return '<div class="pg-copilot-note">' +
      'This is one PowerGrader session. Do not start a new PowerGrader session for later batches.<br>' +
      'For each batch, start a new AI chat, upload files 01, 02, and 03, paste the batch prompt, then paste your AI chat&apos;s JSON back here.<br>' +
      '<span>These files use pseudonyms and remove obvious student identifiers before you upload them. Review the files before sending them to your AI chat.</span>' +
      '</div>' +
      '<div class="pg-copilot-summary">Imported ' + imported + ' of ' + batches.length + ' batches. AI suggestions loaded for ' + loaded + ' of ' + total + ' students.</div>' +
      batches.map(renderCopilotBatch).join('');
  }

  function renderCopilotBatch(batch) {
    var status = batch.status || 'pending';
    var label = batch.label || batch.batch_id || 'Batch';
    var warningHtml = (batch.warnings || []).map(function(w){
      return '<div class="pg-copilot-warning">' + esc(w) + '</div>';
    }).join('');
    var meta = (batch.student_count || 0) + ' students';
    if (batch.token_estimate) meta += ' · ~' + Number(batch.token_estimate).toLocaleString() + ' tokens';
    var lateBadge = batch.late_catchup ? ' <span class="pg-late-label">Late</span>' : '';
    return '<div class="pg-copilot-batch" data-batch-id="' + esc(batch.batch_id || '') + '">' +
      '<div class="pg-copilot-batch-head">' +
        '<strong>' + esc(label) + '</strong>' + lateBadge +
        '<span class="pg-batch-status ' + esc(status) + '">' + esc(titleCase(status)) + '</span>' +
      '</div>' +
      '<div class="pg-copilot-batch-meta">' + esc(meta) + '</div>' +
      '<div class="pg-copilot-batch-meta">Start a new AI chat for this batch. Upload files 01, 02, and 03 from this folder.</div>' +
      warningHtml +
      '<div class="pg-copilot-batch-actions">' +
        '<button type="button" class="small" data-open-path="' + esc(batch.folder || '') + '">Open batch folder</button>' +
        '<button type="button" class="small" data-copy-batch-prompt="' + esc(batch.batch_id || '') + '">Copy AI chat prompt</button>' +
      '</div>' +
      '<details class="pg-import-box">' +
        '<summary>Paste JSON for ' + esc(label) + '</summary>' +
        '<label>Or choose a compatible result file ' +
          '<input type="file" accept=".json,.txt,.md" data-batch-result-file="' + esc(batch.batch_id || '') + '">' +
        '</label>' +
        '<textarea data-batch-results="' + esc(batch.batch_id || '') + '" rows="5" placeholder="[{&quot;pseudonym&quot;:&quot;...&quot;,&quot;item_id&quot;:&quot;...&quot;,&quot;score&quot;:2,&quot;feedback&quot;:&quot;...&quot;}]"></textarea>' +
        '<div class="pg-import-actions">' +
          '<button type="button" class="primary small" data-import-batch="' + esc(batch.batch_id || '') + '">Import this batch</button>' +
          '<span class="hint" data-batch-status-text="' + esc(batch.batch_id || '') + '"></span>' +
        '</div>' +
      '</details>' +
    '</div>';
  }

  function findBatch(batchId) {
    var session = getSession();
    var batches = session && session.copilot_packet && Array.isArray(session.copilot_packet.batches)
      ? session.copilot_packet.batches
      : [];
    return batches.find(function(batch){ return batch.batch_id === batchId; });
  }

  function batchStatusEl(batchId) {
    return document.querySelector('[data-batch-status-text="' + cssEscape(batchId) + '"]');
  }

  function refreshSessionAfterImport(onSuccess) {
    if (queue.reloadSession) {
      return queue.reloadSession({
        indexOverride: getCurrentIndex(),
        onSuccess: onSuccess,
      });
    }
    return fetch('/api/powergrader/session/' + sessionId)
      .then(function(r){ return r.json(); })
      .then(function(fresh){
        if (!fresh.ok) return false;
        if (queue.setSession) queue.setSession(fresh.session);
        if (queue.setStudents) queue.setStudents(fresh.session.students || []);
        if (queue.updateProgress) queue.updateProgress();
        if (queue.renderLateWatch) queue.renderLateWatch(fresh.session);
        if (queue.renderAutoPost) queue.renderAutoPost(fresh.session);
        renderPacketPanel(fresh.session);
        if (queue.renderStudent) queue.renderStudent(getCurrentIndex());
        if (onSuccess) onSuccess(fresh.session);
        return true;
      });
  }

  function importLegacyResults() {
    var text = importJson ? importJson.value.trim() : '';
    if (!text) {
      if (importStatus) importStatus.textContent = 'Paste AI JSON first.';
      return;
    }
    importBtn.disabled = true;
    if (importStatus) importStatus.textContent = 'Validating and importing...';
    var fd = new FormData();
    fd.append('results', text);
    fetch('/api/powergrader/session/' + sessionId + '/import-results', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          if (importStatus) {
            var details = d.validation && d.validation.errors ? ' ' + d.validation.errors.slice(0, 2).join(' ') : '';
            importStatus.textContent = (d.error || 'Import failed.') + details;
          }
          return;
        }
        return refreshSessionAfterImport(function(){
          if (importStatus) {
            var warnings = d.validation && d.validation.warnings ? d.validation.warnings.length : 0;
            importStatus.textContent = 'Imported ' + d.updated + ' AI suggestion(s)' + (warnings ? ' with ' + warnings + ' warning(s).' : '.') + readNote(d);
          }
          if (queue.showStatus) queue.showStatus('AI suggestions imported for review.', false);
        });
      })
      .catch(function(e){ if (importStatus) importStatus.textContent = String(e); })
      .finally(function(){ importBtn.disabled = false; });
  }

  queue.renderPacketPanel = renderPacketPanel;
  queue.renderCopilotBatches = renderCopilotBatches;
  queue.renderCopilotBatch = renderCopilotBatch;
  queue.findBatch = findBatch;
  queue.batchStatusEl = batchStatusEl;
  queue.cssEscape = cssEscape;
  if (getSession()) renderPacketPanel(getSession());

  importBtn && importBtn.addEventListener('click', importLegacyResults);
  importFile && importFile.addEventListener('change', function () {
    var file = importFile.files && importFile.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      if (importJson) importJson.value = String(reader.result || '');
      if (importStatus) importStatus.textContent = 'Result file loaded locally. Validate and import it into this session.';
    };
    reader.onerror = function () { if (importStatus) importStatus.textContent = 'Could not read that result file.'; };
    reader.readAsText(file, 'utf-8');
  });

  document.addEventListener('change', function (e) {
    var fileInput = e.target.closest('[data-batch-result-file]');
    if (!fileInput) return;
    var batchId = fileInput.getAttribute('data-batch-result-file') || '';
    var file = fileInput.files && fileInput.files[0];
    if (!file) return;
    var textarea = document.querySelector('[data-batch-results="' + cssEscape(batchId) + '"]');
    var status = batchStatusEl(batchId);
    var reader = new FileReader();
    reader.onload = function () {
      if (textarea) textarea.value = String(reader.result || '');
      if (status) status.textContent = 'Result file loaded locally. Validate and import it into this session.';
    };
    reader.onerror = function () { if (status) status.textContent = 'Could not read that result file.'; };
    reader.readAsText(file, 'utf-8');
  });

  document.addEventListener('click', function(e) {
    var copyBtn = e.target.closest('[data-copy-batch-prompt]');
    if (copyBtn) {
      var batchId = copyBtn.getAttribute('data-copy-batch-prompt') || '';
      var batch = findBatch(batchId);
      var status = batchStatusEl(batchId);
      if (!batch || !batch.prompt) {
        if (status) status.textContent = 'Prompt not found for this batch.';
        return;
      }
      navigator.clipboard.writeText(batch.prompt)
        .then(function(){
          if (status) status.textContent = 'Prompt copied.';
        })
        .catch(function(){
          var card = copyBtn.closest('.pg-copilot-batch');
          if (card && !card.querySelector('.pg-batch-prompt-fallback')) {
            var fallback = document.createElement('textarea');
            fallback.className = 'pg-batch-prompt-fallback';
            fallback.rows = 4;
            fallback.value = batch.prompt;
            card.appendChild(fallback);
            fallback.focus();
            fallback.select();
          }
          if (status) status.textContent = 'Clipboard failed. Copy the prompt text shown below.';
        });
      return;
    }

    var importBatchBtn = e.target.closest('[data-import-batch]');
    if (!importBatchBtn) return;
    var batchId = importBatchBtn.getAttribute('data-import-batch') || '';
    var textarea = document.querySelector('[data-batch-results="' + cssEscape(batchId) + '"]');
    var status = batchStatusEl(batchId);
    var text = textarea ? textarea.value.trim() : '';
    if (!text) {
      if (status) status.textContent = 'Paste AI JSON first.';
      return;
    }
    importBatchBtn.disabled = true;
    if (status) status.textContent = 'Validating and importing...';
    var fd = new FormData();
    fd.append('results', text);
    fd.append('batch_id', batchId);
    fetch('/api/powergrader/session/' + sessionId + '/import-results', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          var details = d.validation && d.validation.errors ? ' ' + d.validation.errors.slice(0, 2).join(' ') : '';
          if (status) status.textContent = (d.error || 'Import failed.') + details;
          return;
        }
        return refreshSessionAfterImport(function(){
          var batch = findBatch(batchId);
          var label = batch && batch.label ? batch.label : batchId;
          var freshStatus = batchStatusEl(batchId);
          if (freshStatus) freshStatus.textContent = label + ' imported: ' + d.updated + ' AI suggestion(s).' + readNote(d);
          if (queue.showStatus) queue.showStatus(label + ' imported for review.', false);
        });
      })
      .catch(function(err){ if (status) status.textContent = String(err); })
      .finally(function(){ importBatchBtn.disabled = false; });
  });
})();
