(function(){
  var SESSION_ID   = document.querySelector('meta[name="session-id"]').content;
  var MODE         = document.querySelector('meta[name="grading-mode"]').content;
  var MODE_LABEL   = document.querySelector('meta[name="mode-label"]').content || MODE;
  var CANVAS_BASE  = document.querySelector('meta[name="canvas-base"]').content;

  var session      = null;
  var students     = [];
  var idx          = 0;    // current student index
  var rubricText   = '';

  // ── DOM refs ────────────────────────────────────────────────────────
  var subPane      = document.getElementById('pg-submission-pane');
  var scoreEl      = document.getElementById('pg-score');
  var ptsEl        = document.getElementById('pg-pts-possible');
  var feedbackEl   = document.getElementById('pg-feedback');
  var badgesEl     = document.getElementById('pg-badges');
  var aiPanel      = document.getElementById('pg-ai-panel');
  var aiScoreVal   = document.getElementById('pg-ai-score-val');
  var aiFeedTxt    = document.getElementById('pg-ai-feedback-text');
  var useAiScore   = document.getElementById('pg-use-ai-score');
  var useAiFeed    = document.getElementById('pg-use-ai-feedback');
  var emojiBtn     = document.getElementById('pg-emoji-btn');
  var emojiPalette = document.getElementById('pg-emoji-palette');
  var saveNextBtn  = document.getElementById('pg-save-next');
  var skipBtn      = document.getElementById('pg-skip');
  var pushOneBtn   = document.getElementById('pg-push-one');
  var bulkPushBtn  = document.getElementById('pg-bulk-push');
  var prevBtn      = document.getElementById('pg-prev');
  var nextBtn      = document.getElementById('pg-next');
  var navCounter   = document.getElementById('pg-nav-counter');
  var progressFill = document.getElementById('pg-progress-fill');
  var progressLbl  = document.getElementById('pg-progress-label');
  var privacyStrip = document.getElementById('pg-privacy-strip');
  var privacySummary = document.getElementById('pg-privacy-summary');
  var privacySteps = document.getElementById('pg-privacy-steps');
  var privacyActions = document.getElementById('pg-privacy-actions');
  var packetStrip = document.getElementById('pg-packet-strip');
  var packetActions = document.getElementById('pg-packet-actions');
  var copilotBatches = document.getElementById('pg-copilot-batches');
  var legacyImportBox = document.getElementById('pg-legacy-import-box');
  var importJson = document.getElementById('pg-import-json');
  var importBtn = document.getElementById('pg-import-results');
  var importStatus = document.getElementById('pg-import-status');
  var statusBar    = document.getElementById('pg-status-bar');
  var rubricPanel  = document.getElementById('pg-rubric-details');
  var rubricPre    = document.getElementById('pg-rubric-text');
  var kbdAHint     = document.getElementById('pg-kbd-a-hint');

  function isAiMode() {
    return MODE === 'assisted' || MODE === 'packet';
  }
  if (kbdAHint) { kbdAHint.style.display = isAiMode() ? '' : 'none'; }

  // ── Load session ────────────────────────────────────────────────────
  fetch('/api/powergrader/session/' + SESSION_ID)
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (!d.ok) { showStatus('Failed to load session: ' + (d.error || 'unknown'), true); return; }
      session  = d.session;
      students = session.students || [];
      rubricText = session.rubric_name || '';

      // Try to show rubric text if we have a rubric name
      if (rubricText) {
        // We'll fetch rubric via a dedicated endpoint if it exists, otherwise skip
        rubricPanel.style.display = '';
        rubricPre.textContent = '(Rubric: ' + rubricText + ' — open via workspace Rubrics folder)';
      }

      updateProgress();
      renderPrivacyAudit(session);
      renderPacketPanel(session);
      renderStudent(idx);
    })
    .catch(function(e){ showStatus('Load error: ' + e, true); });

  // ── Render one student ──────────────────────────────────────────────
  function renderStudent(i) {
    if (!students.length) { subPane.innerHTML = '<p class="pg-no-text">No students in session.</p>'; return; }
    idx = Math.max(0, Math.min(i, students.length - 1));
    var st = students[idx];

    // Progress
    updateProgress();

    // Nav counter
    navCounter.textContent = (idx + 1) + ' / ' + students.length;
    prevBtn.disabled = idx === 0;
    nextBtn.disabled = idx === students.length - 1;

    // Badges
    badgesEl.innerHTML = '';
    if (st.tier_alias) {
      var tb = document.createElement('span');
      tb.className = 'pg-badge pg-badge--tier';
      tb.textContent = (st.tier_label || st.tier_alias) + (st.tier_alias && st.tier_alias !== st.tier_label ? ' / ' + st.tier_alias : '');
      badgesEl.appendChild(tb);
    }
    if (st.is_monitored) {
      var mb = document.createElement('span');
      mb.className = 'pg-badge pg-badge--mon';
      mb.textContent = '★ Monitored';
      mb.title = st.monitored_note || 'Monitored student';
      badgesEl.appendChild(mb);
    }
    if (st.extra_time_days) {
      var eb = document.createElement('span');
      eb.className = 'pg-badge pg-badge--extra';
      eb.textContent = '⏱ +' + st.extra_time_days + 'd';
      badgesEl.appendChild(eb);
    }
    if (st.posted) {
      var pb = document.createElement('span');
      pb.className = 'pg-badge pg-badge--posted';
      pb.textContent = '✓ Posted';
      badgesEl.appendChild(pb);
    }

    // Points possible
    ptsEl.textContent = '/ ' + (session.points_possible || '?');
    scoreEl.max = session.points_possible || 100;

    var hasAiScore = st.ai_score !== null && st.ai_score !== undefined;
    var hasAiFeed  = !!(st.ai_feedback && st.ai_feedback.trim());

    // Pre-fill score/feedback from saved grade, otherwise from the AI draft.
    if (st.teacher_score !== null && st.teacher_score !== undefined) {
      scoreEl.value = st.teacher_score;
    } else if (isAiMode() && hasAiScore) {
      scoreEl.value = st.ai_score;
    } else {
      scoreEl.value = '';
    }

    var usedAiDraft = false;
    if (st.teacher_feedback) {
      feedbackEl.value = st.teacher_feedback;
    } else if (isAiMode() && (hasAiScore || hasAiFeed)) {
      feedbackEl.value = buildAiDraft(st);
      usedAiDraft = true;
    } else {
      feedbackEl.value = '';
    }
    if (usedAiDraft && feedbackEl.setSelectionRange) {
      setTimeout(function(){ try { feedbackEl.setSelectionRange(0, 0); } catch(e){} }, 0);
    }

    // AI draft is now loaded into the editable feedback box, so the separate
    // suggestion panel stays out of the way and the textarea can use the space.
    aiPanel.style.display = 'none';
    aiScoreVal.textContent = hasAiScore ? st.ai_score : 'No AI score';
    aiFeedTxt.textContent  = hasAiFeed ? formatAiFeedback(st.ai_feedback) : '(No AI feedback)';
    useAiScore.disabled    = !hasAiScore;
    useAiFeed.disabled     = !hasAiFeed;

    // Already-graded note
    var alreadyHtml = '';
    if (st.current_score !== null && st.current_score !== undefined) {
      alreadyHtml = '<div class="pg-already-graded">Canvas current score: <strong>' + st.current_score + '</strong></div>';
    }

    // Submission content
    var subHtml = '<h3 class="pg-student-name">' + _esc(st.real_name) + '</h3>' + alreadyHtml;
    var bodyIsHtml = st.body && /<[a-z][\s\S]*>/i.test(st.body);

    if (st.body && st.body.trim()) {
      subHtml += '<div class="pg-sub-section"><div class="pg-sub-label">Submission</div>';
      if (bodyIsHtml) {
        // Rendered in a styled iframe (see buildSrcdoc) so the student's HTML —
        // code chips, lists, emoji, bold — looks like Canvas, not bare Times.
        subHtml += '<iframe class="pg-body-frame" sandbox="allow-same-origin" id="pg-body-frame"></iframe>';
      } else {
        subHtml += '<div class="pg-body-plain">' + _esc(st.body) + '</div>';
      }
      subHtml += '</div>';
    } else {
      subHtml += '<div class="pg-sub-section"><p class="pg-no-text">No text entry body.</p></div>';
    }

    // Code files — rendered as styled code blocks
    if (st.code_files && st.code_files.length) {
      st.code_files.forEach(function(cf){
        subHtml += '<div class="pg-sub-section">' +
          '<div class="pg-sub-label pg-code-fname">' + _esc(cf.filename) + '</div>' +
          '<pre class="pg-code-block">' + _esc(cf.text) + '</pre></div>';
      });
    }

    // Attachments (non-text)
    var nonTextAtts = (st.attachments || []).filter(function(a){
      var ext = (a.filename || '').split('.').pop().toLowerCase();
      return ['py','html','htm','css','js','txt','md','json','csv'].indexOf(ext) === -1;
    });
    if (nonTextAtts.length) {
      subHtml += '<div class="pg-sub-section"><div class="pg-sub-label">Attachments</div>' +
        '<ul class="pg-att-list">' +
        nonTextAtts.map(function(a){ return '<li>📎 ' + _esc(a.filename) + (a.size ? ' (' + Math.round(a.size/1024) + ' KB)' : '') + '</li>'; }).join('') +
        '</ul></div>';
    }

    subPane.innerHTML = subHtml;

    // Inject the HTML body into the iframe via a styled document (srcdoc set after
    // innerHTML so encoding is reliable; auto-sizes to content height on load).
    if (bodyIsHtml) {
      var frame = document.getElementById('pg-body-frame');
      if (frame) {
        frame.addEventListener('load', function(){
          try { frame.style.height = (frame.contentDocument.body.scrollHeight + 28) + 'px'; } catch(e){}
        });
        frame.srcdoc = buildSrcdoc(st.body);
      }
    }
  }

  // Wrap the student's submission HTML in a styled document so it renders like a
  // modern page (Canvas-style system font + code chips), theme-aware, instead of
  // the browser's default serif. Sandboxed: same-origin only, no scripts.
  function buildSrcdoc(bodyHtml) {
    var dark   = document.documentElement.getAttribute('data-theme') === 'dark';
    var bg     = dark ? '#1f1f23' : '#ffffff';
    var fg     = dark ? '#e8e8ea' : '#1a1a1a';
    var codeBg = dark ? '#2d2d33' : '#f4f4f5';
    var codeFg = dark ? '#f0abfc' : '#be185d';
    var linkFg = dark ? '#7ab8ff' : '#2563eb';
    return '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
      'html,body{margin:0;padding:14px;background:' + bg + ';color:' + fg + ';' +
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;' +
      'font-size:15px;line-height:1.6;}' +
      'code,kbd,tt,samp{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;' +
      'font-size:.88em;background:' + codeBg + ';color:' + codeFg + ';padding:2px 6px;border-radius:4px;}' +
      'pre{background:' + codeBg + ';padding:12px;border-radius:6px;overflow:auto;}' +
      'pre code{background:none;padding:0;color:inherit;}' +
      'p{margin:0 0 12px;}ul,ol{margin:0 0 12px;padding-left:24px;}' +
      'img{max-width:100%;height:auto;}a{color:' + linkFg + ';}' +
      'table{border-collapse:collapse;}td,th{border:1px solid ' + (dark?'#444':'#ddd') + ';padding:4px 8px;}' +
      '</style></head><body>' + bodyHtml + '</body></html>';
  }

  function renderPrivacyAudit(s) {
    var steps = (s && s.privacy_steps) || [];
    if (!steps.length || !privacyStrip || !privacySteps) return;
    privacyStrip.hidden = false;
    var ok = steps.filter(function(st){ return st.status === 'ok'; }).length;
    var warn = steps.filter(function(st){ return st.status === 'warn'; }).length;
    var fail = steps.filter(function(st){ return st.status === 'failed'; }).length;
    privacySummary.textContent = ok + ' green' + (warn ? ', ' + warn + ' yellow' : '') + (fail ? ', ' + fail + ' red' : '');
    privacySteps.innerHTML = steps.map(function(step){
      var status = step.status || '';
      var light = status === 'ok' ? 'ok' : (status === 'warn' ? 'warn' : (status === 'failed' ? 'failed' : ''));
      var pathButton = step.path
        ? '<div class="pg-privacy-actions-inline"><button type="button" class="small" data-open-path="' + _esc(step.path) + '">' + _esc(step.action_label || 'Open file') + '</button></div>'
        : '';
      return '<div class="pg-privacy-step">' +
        '<span class="pg-light ' + light + '"></span>' +
        '<div><div class="pg-privacy-label" title="' + _esc(step.label || '') + '">' + _esc(step.label || step.id || 'Step') + '</div>' +
        (step.detail ? '<div class="pg-privacy-detail">' + _esc(step.detail) + '</div>' : '') +
        pathButton +
        '</div></div>';
    }).join('');
    var artifacts = s.privacy_artifacts || {};
    var buttons = [];
    if (artifacts.safe_folder) buttons.push('<button type="button" class="small" data-open-path="' + _esc(artifacts.safe_folder) + '">Open Safe AI Packet folder</button>');
    if (artifacts.private_folder) buttons.push('<button type="button" class="small" data-open-path="' + _esc(artifacts.private_folder) + '">Open Private decoder folder</button>');
    privacyActions.innerHTML = buttons.join('');
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
      buttons.push('<button type="button" class="small" data-open-path="' + _esc(artifacts.packet_folder) + '">Open packet folder</button>');
    }
    if (copilot.packet_folder) {
      buttons.push('<button type="button" class="small" data-open-path="' + _esc(copilot.packet_folder) + '">Open Copilot batch folder</button>');
    }
    buttons.push('<a class="small" href="/api/powergrader/session/' + encodeURIComponent(SESSION_ID) + '/packet" style="padding:4px 10px;border:1px solid var(--line);border-radius:var(--r-sm);text-decoration:none;background:var(--card);color:var(--ink)">Download packet ZIP</a>');
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
    var loaded = students.filter(function(st){
      return st.ai_score !== null && st.ai_score !== undefined || !!(st.ai_feedback || '').trim();
    }).length;
    var total = copilot.student_count || students.length || 0;
    return '<div class="pg-copilot-note">' +
      'This is one PowerGrader session. Do not start a new PowerGrader session for later batches.<br>' +
      'For each batch, start a new Copilot chat, upload files 01, 02, and 03, paste the batch prompt, then paste Copilot&apos;s JSON back here.<br>' +
      '<span>These files use pseudonyms and remove obvious student identifiers before you upload them. Review the files before sending them to Copilot.</span>' +
      '</div>' +
      '<div class="pg-copilot-summary">Imported ' + imported + ' of ' + batches.length + ' batches. AI suggestions loaded for ' + loaded + ' of ' + total + ' students.</div>' +
      batches.map(renderCopilotBatch).join('');
  }

  function renderCopilotBatch(batch) {
    var status = batch.status || 'pending';
    var label = batch.label || batch.batch_id || 'Batch';
    var warningHtml = (batch.warnings || []).map(function(w){
      return '<div class="pg-copilot-warning">' + _esc(w) + '</div>';
    }).join('');
    var meta = (batch.student_count || 0) + ' students';
    if (batch.token_estimate) meta += ' · ~' + Number(batch.token_estimate).toLocaleString() + ' tokens';
    return '<div class="pg-copilot-batch" data-batch-id="' + _esc(batch.batch_id || '') + '">' +
      '<div class="pg-copilot-batch-head">' +
        '<strong>' + _esc(label) + '</strong>' +
        '<span class="pg-batch-status ' + _esc(status) + '">' + _esc(titleCase(status)) + '</span>' +
      '</div>' +
      '<div class="pg-copilot-batch-meta">' + _esc(meta) + '</div>' +
      '<div class="pg-copilot-batch-meta">Start a new Copilot chat for this batch. Upload files 01, 02, and 03 from this folder.</div>' +
      warningHtml +
      '<div class="pg-copilot-batch-actions">' +
        '<button type="button" class="small" data-open-path="' + _esc(batch.folder || '') + '">Open batch folder</button>' +
        '<button type="button" class="small" data-copy-batch-prompt="' + _esc(batch.batch_id || '') + '">Copy Copilot prompt</button>' +
      '</div>' +
      '<details class="pg-import-box">' +
        '<summary>Paste JSON for ' + _esc(label) + '</summary>' +
        '<textarea data-batch-results="' + _esc(batch.batch_id || '') + '" rows="5"></textarea>' +
        '<div class="pg-import-actions">' +
          '<button type="button" class="primary small" data-import-batch="' + _esc(batch.batch_id || '') + '">Import this batch</button>' +
          '<span class="hint" data-batch-status-text="' + _esc(batch.batch_id || '') + '"></span>' +
        '</div>' +
      '</details>' +
    '</div>';
  }

  function titleCase(text) {
    text = String(text || 'pending');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function findBatch(batchId) {
    var batches = session && session.copilot_packet && Array.isArray(session.copilot_packet.batches)
      ? session.copilot_packet.batches
      : [];
    return batches.find(function(batch){ return batch.batch_id === batchId; });
  }

  function batchStatusEl(batchId) {
    return document.querySelector('[data-batch-status-text="' + cssEscape(batchId) + '"]');
  }

  function cssEscape(value) {
    if (window.CSS && CSS.escape) return CSS.escape(value);
    return String(value || '').replace(/"/g, '\\"');
  }

  importBtn && importBtn.addEventListener('click', function(){
    var text = importJson ? importJson.value.trim() : '';
    if (!text) {
      if (importStatus) importStatus.textContent = 'Paste AI JSON first.';
      return;
    }
    importBtn.disabled = true;
    if (importStatus) importStatus.textContent = 'Validating and importing...';
    var fd = new FormData();
    fd.append('results', text);
    fetch('/api/powergrader/session/' + SESSION_ID + '/import-results', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          if (importStatus) {
            var details = d.validation && d.validation.errors ? ' ' + d.validation.errors.slice(0, 2).join(' ') : '';
            importStatus.textContent = (d.error || 'Import failed.') + details;
          }
          return;
        }
        return fetch('/api/powergrader/session/' + SESSION_ID)
          .then(function(r){ return r.json(); })
          .then(function(fresh){
            if (fresh.ok) {
              session = fresh.session;
              students = session.students || [];
              updateProgress();
              renderPacketPanel(session);
              renderStudent(idx);
              if (importStatus) {
                var warnings = d.validation && d.validation.warnings ? d.validation.warnings.length : 0;
                importStatus.textContent = 'Imported ' + d.updated + ' AI suggestion(s)' + (warnings ? ' with ' + warnings + ' warning(s).' : '.');
              }
              showStatus('AI suggestions imported for review.', false);
            }
          });
      })
      .catch(function(e){ if (importStatus) importStatus.textContent = String(e); })
      .finally(function(){ importBtn.disabled = false; });
  });

  document.addEventListener('click', function(e) {
    var copyBtn = e.target.closest('[data-copy-batch-prompt]');
    if (!copyBtn) return;
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
  });

  document.addEventListener('click', function(e) {
    var importBatchBtn = e.target.closest('[data-import-batch]');
    if (!importBatchBtn) return;
    var batchId = importBatchBtn.getAttribute('data-import-batch') || '';
    var textarea = document.querySelector('[data-batch-results="' + cssEscape(batchId) + '"]');
    var status = batchStatusEl(batchId);
    var text = textarea ? textarea.value.trim() : '';
    if (!text) {
      if (status) status.textContent = 'Paste Copilot JSON first.';
      return;
    }
    importBatchBtn.disabled = true;
    if (status) status.textContent = 'Validating and importing...';
    var fd = new FormData();
    fd.append('results', text);
    fd.append('batch_id', batchId);
    fetch('/api/powergrader/session/' + SESSION_ID + '/import-results', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          var details = d.validation && d.validation.errors ? ' ' + d.validation.errors.slice(0, 2).join(' ') : '';
          if (status) status.textContent = (d.error || 'Import failed.') + details;
          return;
        }
        return fetch('/api/powergrader/session/' + SESSION_ID)
          .then(function(r){ return r.json(); })
          .then(function(fresh){
            if (fresh.ok) {
              session = fresh.session;
              students = session.students || [];
              updateProgress();
              renderPacketPanel(session);
              renderStudent(idx);
              var batch = findBatch(batchId);
              var label = batch && batch.label ? batch.label : batchId;
              var freshStatus = batchStatusEl(batchId);
              if (freshStatus) freshStatus.textContent = label + ' imported: ' + d.updated + ' AI suggestion(s).';
              showStatus(label + ' imported for review.', false);
            }
          });
      })
      .catch(function(err){ if (status) status.textContent = String(err); })
      .finally(function(){ importBatchBtn.disabled = false; });
  });

  function buildAiDraft(st) {
    var parts = [];
    var hasScore = st.ai_score !== null && st.ai_score !== undefined;
    if (hasScore) {
      parts.push('AI score: ' + st.ai_score + (session && session.points_possible ? ' / ' + session.points_possible : ''));
    }
    if (st.ai_feedback && st.ai_feedback.trim()) {
      parts.push(formatAiFeedback(st.ai_feedback));
    }
    return parts.length ? '---------- AI draft ----------\n' + parts.join('\n\n') : '';
  }

  function formatAiFeedback(raw) {
    var text = formatFeedbackLinebreaks(raw);
    var match = text.match(/Drafted by [^.\n]+?\(AI\), reviewed by your teacher\.?/i);
    if (!match) return text;

    var disclosure = match[0];
    var persona = (disclosure.match(/Drafted by\s+(.+?)\s+\(AI\),\s*reviewed by your teacher\.?/i) || [])[1] || '';
    text = removePhrase(text, disclosure)
      .replace(/^\s*(?:[-\u2013\u2014]\s*)?[\w .,'&-]{1,100}\s+\((?:AI|AI teaching assistant)\)\.?\s*$/gim, '');
    if (persona) {
      text = text.replace(new RegExp('(?:[-\u2013\u2014]\\s*)?' + escapeRegExp(persona) + '\\s+\\((?:AI|AI teaching assistant)\\)\\.?', 'ig'), '');
    }
    text = formatFeedbackLinebreaks(text);
    return text ? text + '\n\n' + disclosure : disclosure;
  }

  function formatFeedbackLinebreaks(raw) {
    var text = String(raw || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
    if (!text) return '';
    text = text.replace(/[ \t]+/g, ' ');
    text = text.replace(/\s+(?=(Score|Glows?|Grows?|Next(?:\s+step| steps?)?|Strategy|Overall|Evidence|Try this|Revision target|Why this score)\s*:)/gi, '\n\n');
    text = text.replace(/\s+(?=Drafted by [^.\n]+?\(AI\), reviewed by your teacher\.?)/gi, '\n\n');
    text = text.replace(/\s+(?=[-*]\s+(Glow|Grow|Next|Evidence|Try)\b)/gi, '\n');
    text = text.split('\n').map(function(line){ return line.trim(); }).join('\n');
    return text.replace(/\n{3,}/g, '\n\n').trim();
  }

  function removePhrase(text, phrase) {
    if (!phrase) return text;
    var pattern = escapeRegExp(phrase).replace(/\s+/g, '\\s+');
    return text.replace(new RegExp(pattern, 'ig'), '').trim();
  }

  function escapeRegExp(text) {
    return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // ── Progress ────────────────────────────────────────────────────────
  function updateProgress() {
    if (!students.length) return;
    var posted   = students.filter(function(s){ return s.posted; }).length;
    var approved = students.filter(function(s){ return s.status === 'approved'; }).length;
    var total    = students.length;
    var pct      = Math.round((posted / total) * 100);
    progressFill.style.width = pct + '%';
    progressLbl.textContent  = posted + ' posted, ' + approved + ' approved — ' + total + ' total';
    var readyToPush = students.filter(function(s){ return s.status === 'approved' && !s.posted; }).length;
    bulkPushBtn.disabled     = readyToPush === 0;
    bulkPushBtn.textContent  = 'Push approved to Canvas (' + readyToPush + ')';
  }

  // ── Save grade ──────────────────────────────────────────────────────
  function saveGrade(statusVal, advance, after) {
    var st = students[idx];
    if (!st) return;
    var fd = new FormData();
    fd.append('user_id', st.user_id);
    fd.append('teacher_score', scoreEl.value);
    fd.append('teacher_feedback', feedbackEl.value);
    fd.append('status', statusVal);
    fetch('/api/powergrader/session/' + SESSION_ID + '/grade', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d.ok) {
          st.teacher_score    = scoreEl.value ? parseFloat(scoreEl.value) : null;
          st.teacher_feedback = feedbackEl.value;
          st.status           = statusVal;
          showStatus(statusVal === 'skipped' ? 'Skipped.' : (statusVal === 'approved' ? 'Approved.' : 'Saved.'), false);
          updateProgress();
          if (after) after(true);
          if (advance && idx < students.length - 1) renderStudent(idx + 1);
        } else {
          showStatus('Save failed: ' + (d.error || 'unknown'), true);
          if (after) after(false);
        }
      })
      .catch(function(e){ showStatus('Error: ' + e, true); if (after) after(false); });
  }

  // ── Push one student ────────────────────────────────────────────────
  function pushOne() {
    var st = students[idx];
    if (!st) return;
    var userId = st.user_id;
    pushOneBtn.disabled = true;
    saveGrade('approved', false, function(ok){
      if (!ok) { pushOneBtn.disabled = false; return; }
      pushSavedOne(userId);
    });
  }

  function pushSavedOne(userId) {
    var fd = new FormData();
    fd.append('user_ids', JSON.stringify([userId]));
    fetch('/api/powergrader/session/' + SESSION_ID + '/push', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        var pushedStudent = students.find(function(s){ return s.user_id === userId; });
        if (d.pushed) {
          if (pushedStudent) {
            pushedStudent.posted = true;
            pushedStudent.status = 'posted';
          }
          showStatus('Pushed to Canvas.', false);
          updateProgress();
          renderStudent(idx);
        } else {
          showStatus((d.errors && d.errors[0]) || 'Push failed.', true);
        }
        pushOneBtn.disabled = false;
      })
      .catch(function(e){ showStatus('Error: ' + e, true); pushOneBtn.disabled = false; });
  }

  // ── Bulk push ───────────────────────────────────────────────────────
  function bulkPush() {
    bulkPushBtn.disabled = true;
    var fd = new FormData();  // empty = push all approved
    fetch('/api/powergrader/session/' + SESSION_ID + '/push', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        // Sync local state
        students.forEach(function(s){ if (d.pushed > 0 && s.status === 'approved') { s.posted = true; s.status = 'posted'; } });
        var msg = 'Pushed ' + d.pushed + ' student(s).';
        if (d.errors && d.errors.length) msg += ' ' + d.errors.length + ' error(s).';
        showStatus(msg, d.errors && d.errors.length > 0);
        updateProgress();
        renderStudent(idx);
      })
      .catch(function(e){ showStatus('Error: ' + e, true); bulkPushBtn.disabled = false; });
  }

  // ── Use AI score / feedback (separate so the teacher controls each) ──
  // The AI score is a structured field from the scoring contract (not parsed out
  // of the feedback text), so pulling a clean number in is exact.
  function applyAiScore(){
    var st = students[idx];
    if (!st || st.ai_score === null || st.ai_score === undefined) return;
    scoreEl.value = st.ai_score;
    showStatus("Used AI's score — edit if needed, then Save.", false);
  }
  function applyAiFeedback(){
    var st = students[idx];
    if (!st || (!st.ai_feedback && st.ai_score === null && st.ai_score === undefined)) return;
    feedbackEl.value = buildAiDraft(st);
    showStatus("Restored the AI draft — edit if needed, then approve.", false);
  }
  useAiScore && useAiScore.addEventListener('click', applyAiScore);
  useAiFeed  && useAiFeed.addEventListener('click', applyAiFeedback);

  // ── Emoji picker (Canvas comments are plain text but render unicode emoji) ──
  var EMOJI = ['✅','👍','🎯','⭐','💡','📝','🔥','👏','✨','🙌','💪','❤️','😊','🚀','⚠️','❓','💯','🧠','📈','🎉'];
  if (emojiPalette) {
    emojiPalette.innerHTML = EMOJI.map(function(e){
      return '<button type="button" data-emoji="' + e + '">' + e + '</button>';
    }).join('');
  }
  emojiBtn && emojiBtn.addEventListener('click', function(){
    emojiPalette.hidden = !emojiPalette.hidden;
  });
  emojiPalette && emojiPalette.addEventListener('click', function(e){
    var b = e.target.closest('button[data-emoji]');
    if (!b) return;
    insertAtCursor(feedbackEl, b.getAttribute('data-emoji'));
    emojiPalette.hidden = true;
    feedbackEl.focus();
  });
  function insertAtCursor(el, text){
    var start = el.selectionStart || 0, end = el.selectionEnd || 0;
    el.value = el.value.slice(0, start) + text + el.value.slice(end);
    var pos = start + text.length;
    el.setSelectionRange(pos, pos);
  }

  // ── Button listeners ────────────────────────────────────────────────
  saveNextBtn.addEventListener('click', function(){ saveGrade('approved', true); });
  skipBtn.addEventListener('click', function(){ saveGrade('skipped', true); });
  pushOneBtn.addEventListener('click', pushOne);
  bulkPushBtn.addEventListener('click', bulkPush);
  prevBtn.addEventListener('click', function(){ renderStudent(idx - 1); });
  nextBtn.addEventListener('click', function(){ renderStudent(idx + 1); });

  // ── Keyboard shortcuts ──────────────────────────────────────────────
  document.addEventListener('keydown', function(e){
    if (e.target.matches('textarea, input, select, button')) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key.toLowerCase()) {
      case 'arrowleft':  renderStudent(idx - 1); e.preventDefault(); break;
      case 'arrowright': renderStudent(idx + 1); e.preventDefault(); break;
      case 'arrowdown':  saveGrade('skipped', true); e.preventDefault(); break;
      case 'arrowup':    saveGrade('approved', true); e.preventDefault(); break;
      case 'j': renderStudent(idx + 1); e.preventDefault(); break;
      case 'k': renderStudent(idx - 1); e.preventDefault(); break;
      case 's': saveGrade('approved', true); e.preventDefault(); break;
      case 'x': saveGrade('skipped', true);  e.preventDefault(); break;
      case 'a':
        if (isAiMode()) { applyAiScore(); e.preventDefault(); }
        break;
      case 'b': bulkPush(); e.preventDefault(); break;
    }
  });

  // ── Status toast ────────────────────────────────────────────────────
  var _statusTimer;
  function showStatus(msg, isErr) {
    statusBar.textContent = msg;
    statusBar.className   = 'pg-status-bar' + (isErr ? ' err' : '');
    statusBar.hidden      = false;
    clearTimeout(_statusTimer);
    _statusTimer = setTimeout(function(){ statusBar.hidden = true; }, 2800);
  }

  function _esc(s){ var d=document.createElement('div'); d.textContent=String(s||''); return d.innerHTML; }
})();
