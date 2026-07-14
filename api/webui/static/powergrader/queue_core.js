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
  var aiPanel = document.getElementById('pg-ai-panel');
  var aiScoreVal = document.getElementById('pg-ai-score-val');
  var aiFeedTxt = document.getElementById('pg-ai-feedback-text');
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
  if (kbdAHint) { kbdAHint.style.display = isAiMode() ? '' : 'none'; }

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
        rubricText = session.rubric_name || '';
        if (rubricText) {
          rubricPanel.style.display = '';
          rubricPre.textContent = '(Rubric: ' + rubricText + ' — open via workspace Rubrics folder)';
        }

        updateProgress();
        if (queue.renderPrivacyAudit) queue.renderPrivacyAudit(session);
        if (queue.renderLateWatch) queue.renderLateWatch(session);
        if (queue.renderPacketPanel) queue.renderPacketPanel(session);
        renderStudent(Math.min(currentIndex, Math.max(0, students.length - 1)));
        if (options.onSuccess) options.onSuccess(session);
        return true;
      });
  }
  queue.reloadSession = reloadSession;

  function renderStudent(i) {
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
      pb.textContent = '✓ Posted';
      badgesEl.appendChild(pb);
    }
    var noWrite = session && session.canvas_writeback_supported === false;
    var pushOne = document.getElementById('pg-push-one');
    if (pushOne) { pushOne.hidden = noWrite; }
    if (bulkPushBtn) { bulkPushBtn.hidden = noWrite; }

    ptsEl.textContent = '/ ' + (session.points_possible || '?');
    scoreEl.max = session.points_possible || 100;

    var hasAiScore = st.ai_score !== null && st.ai_score !== undefined;
    var hasAiFeed = !!(st.ai_feedback && st.ai_feedback.trim());

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

    aiPanel.style.display = 'none';
    aiScoreVal.textContent = hasAiScore ? st.ai_score : 'No AI score';
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

    var nonTextAtts = (st.attachments || []).filter(function(a){
      var ext = (a.filename || '').split('.').pop().toLowerCase();
      return ['py','html','htm','css','js','txt','md','json','csv'].indexOf(ext) === -1;
    });
    if (nonTextAtts.length) {
      subHtml += '<div class="pg-sub-section"><div class="pg-sub-label">Attachments</div>' +
        '<ul class="pg-att-list">' +
        nonTextAtts.map(function(a){ return '<li>📎 ' + esc(a.filename) + (a.size ? ' (' + Math.round(a.size/1024) + ' KB)' : '') + '</li>'; }).join('') +
        '</ul></div>';
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
    progressFill.style.width = pct + '%';
    progressLbl.textContent = posted + ' posted, ' + approved + ' approved — ' + total + ' total';
    var readyToPush = students.filter(function(s){ return s.status === 'approved' && !s.posted; }).length;
    bulkPushBtn.disabled = readyToPush === 0;
    bulkPushBtn.textContent = 'Push approved to Canvas (' + readyToPush + ')';
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

  loadSession();
})();
