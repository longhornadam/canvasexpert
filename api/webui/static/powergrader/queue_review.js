(function(){
  "use strict";

  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});
  var sessionId = queue.getSessionId ? queue.getSessionId() : document.querySelector('meta[name="session-id"]').content;

  var scoreEl = document.getElementById('pg-score');
  var feedbackEl = document.getElementById('pg-feedback');
  var useAiScore = document.getElementById('pg-use-ai-score');
  var useAiFeed = document.getElementById('pg-use-ai-feedback');
  var emojiBtn = document.getElementById('pg-emoji-btn');
  var emojiPalette = document.getElementById('pg-emoji-palette');
  var saveNextBtn = document.getElementById('pg-save-next');
  var skipBtn = document.getElementById('pg-skip');
  var pushOneBtn = document.getElementById('pg-push-one');
  var bulkPushBtn = document.getElementById('pg-bulk-push');
  var prevBtn = document.getElementById('pg-prev');
  var nextBtn = document.getElementById('pg-next');

  function getStudents() {
    return queue.getStudents ? queue.getStudents() : [];
  }

  function getIndex() {
    return queue.getIndex ? queue.getIndex() : 0;
  }

  function currentStudent() {
    return getStudents()[getIndex()] || null;
  }

  function saveGrade(statusVal, advance, after) {
    var st = currentStudent();
    if (!st) return;
    var fd = new FormData();
    fd.append('user_id', st.user_id);
    fd.append('teacher_score', scoreEl.value);
    fd.append('teacher_feedback', feedbackEl.value);
    fd.append('status', statusVal);
    fetch('/api/powergrader/session/' + sessionId + '/grade', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d.ok) {
          st.teacher_score = scoreEl.value ? parseFloat(scoreEl.value) : null;
          st.teacher_feedback = feedbackEl.value;
          st.status = statusVal;
          if (queue.showStatus) queue.showStatus(statusVal === 'skipped' ? 'Skipped.' : (statusVal === 'approved' ? 'Approved.' : 'Saved.'), false);
          if (queue.updateProgress) queue.updateProgress();
          if (after) after(true);
          if (advance && getIndex() < getStudents().length - 1 && queue.renderStudent) queue.renderStudent(getIndex() + 1);
        } else {
          if (queue.showStatus) queue.showStatus('Save failed: ' + (d.error || 'unknown'), true);
          if (after) after(false);
        }
      })
      .catch(function(e){ if (queue.showStatus) queue.showStatus('Error: ' + e, true); if (after) after(false); });
  }

  function pushSavedOne(userId) {
    var fd = new FormData();
    fd.append('user_ids', JSON.stringify([userId]));
    fetch('/api/powergrader/session/' + sessionId + '/push', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        var pushedStudent = getStudents().find(function(s){ return s.user_id === userId; });
        if (d.pushed) {
          if (pushedStudent) {
            pushedStudent.posted = true;
            pushedStudent.status = 'posted';
          }
          if (queue.showStatus) queue.showStatus('Pushed to Canvas.', false);
          if (queue.updateProgress) queue.updateProgress();
          if (queue.renderStudent) queue.renderStudent(getIndex());
        } else {
          if (queue.showStatus) queue.showStatus((d.errors && d.errors[0]) || 'Push failed.', true);
        }
        pushOneBtn.disabled = false;
      })
      .catch(function(e){ if (queue.showStatus) queue.showStatus('Error: ' + e, true); pushOneBtn.disabled = false; });
  }

  function pushOne() {
    var st = currentStudent();
    if (!st) return;
    var userId = st.user_id;
    pushOneBtn.disabled = true;
    saveGrade('approved', false, function(ok){
      if (!ok) { pushOneBtn.disabled = false; return; }
      pushSavedOne(userId);
    });
  }

  function bulkPush() {
    bulkPushBtn.disabled = true;
    var fd = new FormData();
    fetch('/api/powergrader/session/' + sessionId + '/push', {method:'POST', body:fd})
      .then(function(r){ return r.json(); })
      .then(function(d){
        getStudents().forEach(function(s){ if (d.pushed > 0 && s.status === 'approved') { s.posted = true; s.status = 'posted'; } });
        var msg = 'Pushed ' + d.pushed + ' student(s).';
        if (d.errors && d.errors.length) msg += ' ' + d.errors.length + ' error(s).';
        if (queue.showStatus) queue.showStatus(msg, d.errors && d.errors.length > 0);
        if (queue.updateProgress) queue.updateProgress();
        if (queue.renderStudent) queue.renderStudent(getIndex());
      })
      .catch(function(e){ if (queue.showStatus) queue.showStatus('Error: ' + e, true); bulkPushBtn.disabled = false; });
  }

  function applyAiScore(){
    var st = currentStudent();
    if (!st || st.ai_score === null || st.ai_score === undefined) return;
    scoreEl.value = st.ai_score;
    if (queue.showStatus) queue.showStatus("Used AI's score — edit if needed, then Save.", false);
  }

  function applyAiFeedback(){
    var st = currentStudent();
    if (!st || (!st.ai_feedback && st.ai_score === null && st.ai_score === undefined)) return;
    feedbackEl.value = queue.buildAiDraft ? queue.buildAiDraft(st) : '';
    if (queue.showStatus) queue.showStatus("Restored the AI draft — edit if needed, then approve.", false);
  }

  function insertAtCursor(el, text){
    var start = el.selectionStart || 0, end = el.selectionEnd || 0;
    el.value = el.value.slice(0, start) + text + el.value.slice(end);
    var pos = start + text.length;
    el.setSelectionRange(pos, pos);
  }

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

  saveNextBtn && saveNextBtn.addEventListener('click', function(){ saveGrade('approved', true); });
  skipBtn && skipBtn.addEventListener('click', function(){ saveGrade('skipped', true); });
  pushOneBtn && pushOneBtn.addEventListener('click', pushOne);
  bulkPushBtn && bulkPushBtn.addEventListener('click', bulkPush);
  prevBtn && prevBtn.addEventListener('click', function(){ if (queue.renderStudent) queue.renderStudent(getIndex() - 1); });
  nextBtn && nextBtn.addEventListener('click', function(){ if (queue.renderStudent) queue.renderStudent(getIndex() + 1); });

  document.addEventListener('keydown', function(e){
    if (e.target.matches('textarea, input, select, button')) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key.toLowerCase()) {
      case 'arrowleft':  if (queue.renderStudent) queue.renderStudent(getIndex() - 1); e.preventDefault(); break;
      case 'arrowright': if (queue.renderStudent) queue.renderStudent(getIndex() + 1); e.preventDefault(); break;
      case 'arrowdown':  saveGrade('skipped', true); e.preventDefault(); break;
      case 'arrowup':    saveGrade('approved', true); e.preventDefault(); break;
      case 'j': if (queue.renderStudent) queue.renderStudent(getIndex() + 1); e.preventDefault(); break;
      case 'k': if (queue.renderStudent) queue.renderStudent(getIndex() - 1); e.preventDefault(); break;
      case 's': saveGrade('approved', true); e.preventDefault(); break;
      case 'x': saveGrade('skipped', true); e.preventDefault(); break;
      case 'a':
        if (queue.isAiMode && queue.isAiMode()) { applyAiScore(); e.preventDefault(); }
        break;
      case 'b': bulkPush(); e.preventDefault(); break;
    }
  });
})();