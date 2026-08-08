(function(){
  "use strict";

  var SESSION_ID = document.querySelector('meta[name="session-id"]').content;
  var MODE = document.querySelector('meta[name="grading-mode"]').content;
  var CANVAS_BASE = document.querySelector('meta[name="canvas-base"]').content;

  var session = null;
  var students = [];
  var idx = 0;
  var rubricText = '';
  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});

  var subPane = document.getElementById('pg-submission-pane');
  var scoreEl = document.getElementById('pg-score');
  var ptsEl = document.getElementById('pg-pts-possible');
  var feedbackEl = document.getElementById('pg-feedback');
  var badgesEl = document.getElementById('pg-badges');
  var aiDraftBadge = document.getElementById('pg-ai-draft-badge');
  var aiPanel = document.getElementById('pg-ai-panel');
  var aiScoreVal = document.getElementById('pg-ai-score-val');
  var aiFeedTxt = document.getElementById('pg-ai-feedback-text');
  var aiFeedDetails = document.getElementById('pg-ai-feedback-details');
  var useAiScore = document.getElementById('pg-use-ai-score');
  var useAiFeed = document.getElementById('pg-use-ai-feedback');
  var bulkPushBtn = document.getElementById('pg-bulk-push');
  var prevBtn = document.getElementById('pg-prev');
  var nextBtn = document.getElementById('pg-next');
  var navCounter = document.getElementById('pg-nav-counter');
  var progressFill = document.getElementById('pg-progress-fill');
  var progressLbl = document.getElementById('pg-progress-label');
  var statusBar = document.getElementById('pg-status-bar');
  var rubricPanel = document.getElementById('pg-rubric-details');
  var rubricPre = document.getElementById('pg-rubric-text');
  var kbdAHint = document.getElementById('pg-kbd-a-hint');

  queue.getSession = function(){ return session; };
  queue.writebackMode = function(){
    if (!session || session.canvas_writeback_supported !== false) return 'full';
    return session.comment_writeback_supported === true ? 'comments' : 'none';
  };
  queue.setSession = function(nextSession){
    session = nextSession || null;
    queue.session = session;
  };
  queue.getStudents = function(){ return students; };
  queue.setStudents = function(nextStudents){
    students = Array.isArray(nextStudents) ? nextStudents : [];
    queue.students = students;
  };
  queue.getIndex = function(){ return idx; };
  queue.setIndex = function(nextIndex){
    idx = Math.max(0, Number(nextIndex) || 0);
    queue.index = idx;
  };
  queue.getSessionId = function(){ return SESSION_ID; };
  queue.getCanvasBase = function(){ return CANVAS_BASE; };
  queue.isAiMode = isAiMode;
  queue.setAiDraftState = setAiDraftState;
  queue.esc = esc;
  queue.showStatus = showStatus;
  queue.updateProgress = updateProgress;
  queue.renderStudent = renderStudent;
  queue.session = session;
  queue.students = students;
  queue.index = idx;

  function isAiMode() {
    return MODE === 'assisted' || MODE === 'packet';
  }
  function blindFirstActive() {
    var settings = session && session.blind_first;
    return isAiMode() && !!(settings && settings.enabled);
  }
  queue.blindFirstActive = blindFirstActive;
  function setAiDraftState(active) {
    var value = active ? 'true' : 'false';
    if (aiDraftBadge) {
      aiDraftBadge.hidden = !active;
      aiDraftBadge.setAttribute('data-aiDraft', value);
    }
    if (feedbackEl) feedbackEl.setAttribute('data-aiDraft', value);
  }
  feedbackEl && feedbackEl.addEventListener('input', function(){
    if (feedbackEl.getAttribute('data-aiDraft') === 'true') setAiDraftState(false);
  });
  if (kbdAHint) { kbdAHint.hidden = !isAiMode(); }

  function loadSession() {
    reloadSession({
      onError: function(error) {
        showStatus('Failed to load session: ' + error, true);
      }
    }).catch(function(e){ showStatus('Load error: ' + e, true); });
  }

  function reloadSession(options) {
    options = options || {};
    var currentIndex = typeof options.indexOverride === 'number' ? options.indexOverride : idx;
    return fetch('/api/powergrader/session/' + SESSION_ID)
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.ok) {
          if (options.onError) options.onError(d.error || 'unknown');
          return false;
        }
        queue.setSession(d.session);
        queue.setStudents(session.students || []);
        queue.blindFirstSummary = d.blind_first || null;
        rubricText = session.rubric_name || '';
        if (rubricText) {
          rubricPanel.hidden = false;
          rubricPre.textContent = '(Rubric: ' + rubricText + ' — open via workspace Rubrics folder)';
        }

        updateProgress();
        var timelineBadge = document.getElementById('pg-timeline-badge');
        if (timelineBadge) timelineBadge.hidden = session.writing_timeline_tracked !== true;
        if (queue.renderPrivacyAudit) queue.renderPrivacyAudit(session);
        if (queue.renderWritingTimelineStrip) queue.renderWritingTimelineStrip(session);
        if (queue.renderLateWatch) queue.renderLateWatch(session);
        if (queue.renderPacketPanel) queue.renderPacketPanel(session);
        if (queue.renderAutoPost) queue.renderAutoPost(session);
        if (queue.renderBlindFirst) queue.renderBlindFirst(session);
        renderStudent(Math.min(currentIndex, Math.max(0, students.length - 1)));
        if (options.onSuccess) options.onSuccess(session);
        return true;
      });
  }
  queue.reloadSession = reloadSession;

  function renderStudent(i) {
    if (queue.stopMediaRecording) queue.stopMediaRecording();
    if (!students.length) { subPane.innerHTML = '<p class="pg-no-text">No students in session.</p>'; return; }
    idx = Math.max(0, Math.min(i, students.length - 1));
    queue.setIndex(idx);
    var st = students[idx];

    updateProgress();
    navCounter.textContent = (idx + 1) + ' / ' + students.length;
    prevBtn.disabled = idx === 0;
    nextBtn.disabled = idx === students.length - 1;

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
    if (st.late_catchup && st.late_catchup.is_late_catchup) {
      var lb = document.createElement('span');
      lb.className = 'pg-badge pg-badge--late';
      if (typeof st.late_catchup.school_days_late === 'number') {
        lb.textContent = 'Late catch-up · ' + st.late_catchup.school_days_late + ' school day' + (st.late_catchup.school_days_late === 1 ? '' : 's') + ' late';
      } else {
        lb.textContent = 'Late catch-up';
      }
      badgesEl.appendChild(lb);
    }
    if (st.new_quiz_attempt !== undefined) {
      var nq = document.createElement('span'); nq.className = 'pg-badge pg-badge--tier';
      nq.textContent = 'New Quiz · Attempt ' + st.new_quiz_attempt; badgesEl.appendChild(nq);
      if (st.canvas_late) { var late = document.createElement('span'); late.className = 'pg-badge pg-badge--late'; late.textContent = 'Late in Canvas'; badgesEl.appendChild(late); }
    }
    if (st.posted) {
      var pb = document.createElement('span');
      pb.className = 'pg-badge pg-badge--posted';
      if (st.status === 'auto_pushed') {
        pb.textContent = '✓ Auto-posted';
        pb.title = 'To change this grade, edit it in Canvas SpeedGrader.';
      } else {
        pb.textContent = '✓ Posted';
      }
      badgesEl.appendChild(pb);
    }
    var writeMode = queue.writebackMode();
    var pushOne = document.getElementById('pg-push-one');
    if (pushOne) {
      pushOne.hidden = writeMode === 'none';
      pushOne.disabled = !!st.posted;
      pushOne.title = st.status === 'auto_pushed'
        ? 'To change this grade, edit it in Canvas SpeedGrader.'
        : '';
      pushOne.textContent = writeMode === 'comments' ? 'Post feedback comment now' : 'Push this student now';
    }
    if (bulkPushBtn) { bulkPushBtn.hidden = writeMode === 'none'; }

    ptsEl.textContent = '/ ' + (session.points_possible || '?');
    scoreEl.max = session.points_possible || 100;

    var hasAiScore = st.ai_score !== null && st.ai_score !== undefined;
    var hasAiFeed = !!(st.ai_feedback && st.ai_feedback.trim());

    if (st.teacher_score !== null && st.teacher_score !== undefined) {
      scoreEl.value = st.teacher_score;
    } else if (st.blind_score !== null && st.blind_score !== undefined) {
      // Once a blind score exists it outranks the model's, including on the
      // re-render straight after a reveal. Pre-filling from ai_score here would
      // overwrite the number the teacher just committed to.
      scoreEl.value = st.blind_score;
    } else if (isAiMode() && hasAiScore && !blindFirstActive()) {
      scoreEl.value = st.ai_score;
    } else {
      scoreEl.value = '';
    }

    var usedAiDraft = false;
    setAiDraftState(false);
    if (st.teacher_feedback) {
      feedbackEl.value = st.teacher_feedback;
    } else if (blindFirstActive() && st.blind_feedback) {
      feedbackEl.value = st.blind_feedback;
    } else if (isAiMode() && (hasAiScore || hasAiFeed) && !blindFirstActive()) {
      feedbackEl.value = buildAiDraft(st);
      usedAiDraft = true;
    } else {
      feedbackEl.value = '';
    }
    setAiDraftState(usedAiDraft);
    if (usedAiDraft && feedbackEl.setSelectionRange) {
      setTimeout(function(){ try { feedbackEl.setSelectionRange(0, 0); } catch(e){} }, 0);
    }

    // The panel is a "what did the AI say / put it back" reference. In an ordinary AI
    // session both boxes already hold the AI's values on first render, so the feedback
    // text stays collapsed until asked for; blind-first re-decides all of this at the
    // end of the render, and opens the text on a disagreement.
    aiPanel.hidden = blindFirstActive() || !(isAiMode() && (hasAiScore || hasAiFeed));
    if (aiFeedDetails) aiFeedDetails.open = false;
    aiScoreVal.textContent = hasAiScore
      ? st.ai_score
      : (st.blind_withheld === true ? 'Hidden until you reveal' : 'No AI score');
    aiFeedTxt.textContent = hasAiFeed ? formatAiFeedback(st.ai_feedback) : '(No AI feedback)';
    useAiScore.disabled = !hasAiScore;
    useAiFeed.disabled = !hasAiFeed;

    var alreadyHtml = '';
    if (st.current_score !== null && st.current_score !== undefined) {
      alreadyHtml = '<div class="pg-already-graded">Canvas current score: <strong>' + st.current_score + '</strong></div>';
    }

    var subHtml = '<h3 class="pg-student-name">' + esc(st.real_name) + '</h3>' + alreadyHtml;
    var bodyIsHtml = st.body && /<[a-z][\s\S]*>/i.test(st.body);

    if (st.body && st.body.trim()) {
      subHtml += '<div class="pg-sub-section"><div class="pg-sub-label">Submission</div>';
      if (bodyIsHtml) {
        subHtml += '<iframe class="pg-body-frame" sandbox="allow-same-origin" id="pg-body-frame"></iframe>';
      } else {
        subHtml += '<div class="pg-body-plain">' + esc(st.body) + '</div>';
      }
      subHtml += '</div>';
    } else {
      subHtml += '<div class="pg-sub-section"><p class="pg-no-text">No text entry body.</p></div>';
    }

    if (st.code_files && st.code_files.length) {
      st.code_files.forEach(function(cf){
        subHtml += '<div class="pg-sub-section">' +
          '<div class="pg-sub-label pg-code-fname">' + esc(cf.filename) + '</div>' +
          '<pre class="pg-code-block">' + esc(cf.text) + '</pre></div>';
      });
    }

    var allAtts = st.attachments || [];
    if (allAtts.length) {
      subHtml += '<div class="pg-sub-section"><div class="pg-sub-label">Attachments and evidence status</div>' +
        '<ul class="pg-att-list">' +
        allAtts.map(function(a){
          var status = a.download_status === 'downloaded'
            ? (a.extraction_status === 'extracted' || a.extraction_status === 'validated' ? ' · AI-ready locally' : ' · held locally')
            : (a.download_status ? ' · ' + a.download_status : ' · local review needed');
          var open = a.local_path
            ? ' <button type="button" class="small" data-open-path="' + esc(a.local_path) + '">Open file</button>'
            : '';
          var size = a.actual_size || a.size || a.declared_size;
          return '<li>📎 ' + esc(a.filename || 'attachment') + (size ? ' (' + Math.round(size/1024) + ' KB)' : '') + esc(status) + open + '</li>';
        }).join('') +
        '</ul>' +
        (st.attachment_eligibility && st.attachment_eligibility.held
          ? '<p class="pg-no-text">Held from automated scoring: ' + esc((st.attachment_eligibility.reasons || []).join('; ')) + '</p>' : '') +
        '</div>';
    }
    if (session && session.writing_timeline_tracked === true) {
      var timelined = allAtts.filter(function(a){ return a && a.writing_timeline; });
      if (timelined.length) {
        timelined.forEach(function(a){
          subHtml += (queue.renderWritingTimeline ? queue.renderWritingTimeline(a.writing_timeline) : '');
        });
      } else {
        // "Not examined" must never be mistaken for "no revision trail".
        subHtml += '<div class="pg-sub-section"><div class="pg-sub-label">Writing Timeline</div>' +
          '<p class="pg-no-text">No DOCX document was examined for this submission, so there is ' +
          'nothing to report either way.</p>' +
          '<p class="pg-no-text">This timeline describes editing process, not authorship or intent.</p></div>';
      }
    }
    if (st.writing_process_observations && st.writing_process_observations.trim()) {
      subHtml += '<div class="pg-sub-section">' +
        '<div class="pg-sub-label">AI writing-process observation (teacher only)</div>' +
        '<div class="pg-body-plain">' + esc(st.writing_process_observations) + '</div>' +
        '</div>';
    }
    if (st.new_quiz_files_error) {
      subHtml += '<div class="pg-sub-section"><p class="pg-no-text">New Quiz upload retrieval is unavailable; written responses remain available. ' + esc(st.new_quiz_files_error.message || '') + '</p></div>';
    }
    if (st.ai_scoring_error) {
      subHtml += '<div class="pg-sub-section"><p class="pg-no-text">AI draft unavailable; manual grading is required.</p></div>';
    }

    subPane.innerHTML = subHtml;

    if (bodyIsHtml) {
      var frame = document.getElementById('pg-body-frame');
      if (frame) {
        frame.addEventListener('load', function(){
          try { frame.style.height = (frame.contentDocument.body.scrollHeight + 28) + 'px'; } catch(e){}
        });
        frame.srcdoc = buildSrcdoc(st.body);
      }
    }
    if (queue.renderNewQuizItems) queue.renderNewQuizItems(st);
    if (queue.renderMediaRecordings) queue.renderMediaRecordings(st);
    if (queue.renderBlindFirstStudent) queue.renderBlindFirstStudent(st);
  }

  function buildSrcdoc(bodyHtml) {
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    var bg = dark ? '#1f1f23' : '#ffffff';
    var fg = dark ? '#e8e8ea' : '#1a1a1a';
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

  function buildAiDraft(st) {
    return formatAiFeedback(st.ai_feedback);
  }
  queue.buildAiDraft = buildAiDraft;

  function formatAiFeedback(raw) {
    var text = formatFeedbackLinebreaks(raw);
    var match = text.match(/Drafted by [^.\n]+?\(AI\), reviewed by your teacher\.?/i);
    if (!match) return text;

    var disclosure = match[0];
    var persona = (disclosure.match(/Drafted by\s+(.+?)\s+\(AI\),\s*reviewed by your teacher\.?/i) || [])[1] || '';
    text = removePhrase(text, disclosure)
      .replace(/^\s*(?:[-\u2013\u2014]\s*)?[\w .,'&-]{1,100}\s+\((?:AI|AI teaching assistant)\)\.?\s*$/gim, '');
    if (persona) {
      text = text.replace(new RegExp('(?:[-\\u2013\\u2014]\\s*)?' + escapeRegExp(persona) + '\\s+\\((?:AI|AI teaching assistant)\\)\\.?', 'ig'), '');
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

  function updateProgress() {
    if (!students.length) return;
    var posted = students.filter(function(s){ return s.posted; }).length;
    var approved = students.filter(function(s){ return s.status === 'approved'; }).length;
    var total = students.length;
    var pct = Math.round((posted / total) * 100);
    progressFill.style.setProperty('--ce-progress', pct + '%');
    progressLbl.textContent = posted + ' posted, ' + approved + ' approved — ' + total + ' total';
    var commentsOnly = queue.writebackMode() === 'comments';
    var readyToPush = students.filter(function(s){
      if (s.status !== 'approved' || s.posted) return false;
      return commentsOnly ? !!(s.teacher_feedback && s.teacher_feedback.trim()) : true;
    }).length;
    bulkPushBtn.disabled = readyToPush === 0;
    bulkPushBtn.textContent = (commentsOnly ? 'Post approved feedback comments (' : 'Push approved to Canvas (') + readyToPush + ')';
  }

  var _statusTimer;
  function showStatus(msg, isErr) {
    statusBar.textContent = msg;
    statusBar.className = 'pg-status-bar' + (isErr ? ' err' : '');
    statusBar.hidden = false;
    clearTimeout(_statusTimer);
    _statusTimer = setTimeout(function(){ statusBar.hidden = true; }, 2800);
  }

  function esc(s){ var d=document.createElement('div'); d.textContent=String(s||''); return d.innerHTML; }

  /* ── Auto-post banner ────────────────────────────────────────────── */
  function renderAutoPost(s) {
    var strip = document.getElementById('pg-autopost-strip');
    var summaryEl = document.getElementById('pg-autopost-summary');
    var actionsEl = document.getElementById('pg-autopost-actions');
    if (!strip || !summaryEl || !actionsEl) return;
    var autoPost = (s && s.auto_post) || {};
    var autoPostSummary = (s && s.auto_post_summary) || null;
    if (!autoPost.enabled && !autoPostSummary) {
      if (autoPost.disabled_at) {
        strip.hidden = false;
        summaryEl.textContent = 'Automatic posting is off.';
        if (autoPostSummary) {
          var bits = buildAutoPostSummaryText(autoPostSummary);
          if (bits) summaryEl.textContent += ' ' + bits;
        }
        actionsEl.innerHTML = '';
      } else {
        strip.hidden = true;
      }
      return;
    }
    strip.hidden = false;
    if (autoPost.enabled) {
      var disableBtn = document.createElement('button');
      disableBtn.type = 'button';
      disableBtn.className = 'small';
      disableBtn.textContent = 'Stop automatic posting';
      disableBtn.addEventListener('click', function(){
        fetch('/api/powergrader/session/' + SESSION_ID + '/auto-post-disable', {method:'POST'})
          .then(function(r){ return r.json(); })
          .then(function(d){
            if (d.ok) {
              if (queue.reloadSession) queue.reloadSession({ indexOverride: idx });
              else window.location.reload();
            } else {
              showStatus('Could not disable automatic posting: ' + (d.error || 'unknown'), true);
            }
          })
          .catch(function(e){ showStatus('Disable error: ' + e, true); });
      });
      actionsEl.innerHTML = '';
      actionsEl.appendChild(disableBtn);
    } else {
      // Disabled: show off status without the disable action
      actionsEl.innerHTML = '';
    }
    var bits = buildAutoPostSummaryText(autoPostSummary);
    summaryEl.textContent = autoPost.enabled ? (bits || 'Automatic posting is on.') : ('Automatic posting is off.' + (bits ? ' ' + bits : ''));
  }

  function buildAutoPostSummaryText(autoPostSummary) {
    if (!autoPostSummary) return '';
    var bits = [];
    if (autoPostSummary.evaluated !== undefined) {
      bits.push('Latest automatic-post run: ' + autoPostSummary.pushed + ' of ' + autoPostSummary.evaluated + ' evaluated results posted');
    }
    if (autoPostSummary.needs_review) {
      bits.push(autoPostSummary.needs_review + ' held for review');
    }
    if (autoPostSummary.blocked) {
      bits.push(autoPostSummary.blocked + ' blocked');
    }
    if (autoPostSummary.reason_counts) {
      var reasons = Object.keys(autoPostSummary.reason_counts)
        .filter(function(k){ return k !== 'pushed'; })
        .map(function(k){ return k.replace(/_/g, ' ') + ': ' + autoPostSummary.reason_counts[k]; })
        .join('; ');
      if (reasons) bits.push('(' + reasons + ')');
    }
    if (autoPostSummary.skipped_reason) {
      bits.push('Skipped: ' + autoPostSummary.skipped_reason.replace(/_/g, ' '));
    }
    return bits.join('; ');
  }
  queue.renderAutoPost = renderAutoPost;

  loadSession();
})();
