(function(){
  'use strict';
  var q = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});
  var region = document.getElementById('pg-new-quiz-items');
  var finalBtn = document.getElementById('pg-new-quiz-finalize');
  var speed = document.getElementById('pg-new-quiz-speedgrader');
  var scoreRow = document.querySelector('.pg-score-row');
  var feedback = document.getElementById('pg-feedback');
  var sessionId = q.getSessionId ? q.getSessionId() : '';
  function esc(value) { var el=document.createElement('div'); el.textContent=String(value || ''); return el.innerHTML; }
  function current() { return (q.getStudents ? q.getStudents() : [])[q.getIndex ? q.getIndex() : 0] || null; }
  function isNewQuiz() { var s=q.getSession && q.getSession(); return !!(s && s.new_quiz_item_finalization_supported); }
  function speedgraderUrl(st) { return (q.getCanvasBase ? q.getCanvasBase() : '') + '/courses/' + encodeURIComponent((q.getSession() || {}).course_id || '') + '/gradebook/speed_grader?assignment_id=' + encodeURIComponent((q.getSession() || {}).assignment_id || '') + '&student_id=' + encodeURIComponent(st.user_id || ''); }
  function manualItems(st) { return (st.new_quiz_items || []).filter(function(item){ return String(item.type || '').toLowerCase() === 'essay'; }); }
  function autoItems(st) { return (st.new_quiz_items || []).filter(function(item){ return String(item.type || '').toLowerCase() !== 'essay'; }); }
  function draftFor(st, item) { return (st.ai_item_results || []).find(function(row){ return String(row.item_id) === String(item.item_id); }) || {}; }
  function taText(draft, item) {
    if (!draft.feedback) return '';
    var score = draft.score === null || draft.score === undefined ? 'not scored' : draft.score;
    return 'Teaching Assistant preliminary score: ' + score + ' / ' + (item.possible || '?') + '\n\n' + draft.feedback;
  }
  q.renderNewQuizItems = function(st) {
    if (!region || !finalBtn || !speed) return;
    if (!isNewQuiz() || !st || !(st.new_quiz_items || []).length) { region.hidden=true; finalBtn.hidden=true; speed.style.display='none'; return; }
    if (scoreRow) scoreRow.hidden=true;
    if (feedback) feedback.placeholder='Optional whole-assignment feedback. This uses the separate comment-only lane.';
    if (st.speedgrader_required) {
      region.hidden=false; region.innerHTML='<div class="pg-ai-header"><span class="pg-ai-badge-sm">Canvas review required</span></div><p>This student has file/media or unsupported manual evidence. Keep the full grading decision in SpeedGrader; PowerGrader will not split authority across items.</p>';
      finalBtn.hidden=true; speed.href=speedgraderUrl(st); speed.style.display='block'; return;
    }
    var items=manualItems(st);
    if (!items.length) { region.hidden=false; region.innerHTML='<p>All New Quiz items are auto-graded and read-only.</p>'; finalBtn.hidden=true; speed.style.display='none'; return; }
    region.hidden=false; speed.style.display='none'; finalBtn.hidden=false;
    region.innerHTML='<div class="pg-ai-header"><span class="pg-ai-badge-sm">New Quiz item finalization</span></div>' + items.map(function(item){
      var ta=taText(draftFor(st,item),item);
      return '<div class="pg-sub-section" data-nq-item="' + esc(item.item_id) + '"><div class="pg-sub-label">Manual text item · ' + esc(item.possible) + ' points</div><label>Teacher score <input class="nq-score" type="number" min="0" max="' + esc(item.possible) + '" step="0.5" placeholder="Required"></label><label>My feedback<textarea class="nq-feedback" rows="3" placeholder="Optional teacher feedback"></textarea></label><pre class="pg-ai-feedback-text">' + esc(ta || 'No Teaching Assistant proposal is available for this item.') + '</pre></div>';
    }).join('') + autoItems(st).map(function(item){
      return '<div class="pg-sub-section"><div class="pg-sub-label">Auto-graded item · read-only</div><p>Canvas earned score: <strong>' + esc(item.earned_score) + ' / ' + esc(item.possible) + '</strong></p></div>';
    }).join('');
  };
  function decisions(st) {
    return manualItems(st).map(function(item){
      var card=region.querySelector('[data-nq-item="' + CSS.escape(String(item.item_id)) + '"]');
      var score=card && card.querySelector('.nq-score'); var teacher=card && card.querySelector('.nq-feedback');
      return {item_id:String(item.item_id),score:score ? Number(score.value) : NaN,teacher_feedback:teacher ? teacher.value : '',ta_feedback:taText(draftFor(st,item),item)};
    });
  }
  finalBtn && finalBtn.addEventListener('click', function(){
    var st=current(); if (!st) return; var rows=decisions(st);
    if (rows.some(function(row){ return !Number.isFinite(row.score) || !row.ta_feedback; })) { if(q.showStatus) q.showStatus('Enter every teacher score; each item needs a Teaching Assistant proposal.',true); return; }
    finalBtn.disabled=true; var body=new FormData(); body.append('user_id',st.user_id); body.append('item_decisions',JSON.stringify(rows));
    fetch('/api/powergrader/session/'+sessionId+'/new-quiz-review',{method:'POST',body:body}).then(function(r){return r.json();}).then(function(review){
      if(!review.ok) throw new Error(review.error || 'Could not freeze the New Quiz result.');
      return window.CE_WRITE_REVIEW.confirm({title:'Finalize New Quiz student',action:'Write the entered item scores and composed item feedback',details:['Canvas will re-check the complete item result set before one write.'],warnings:['Auto-graded items and fudge points stay unchanged.'],confirmText:'Finalize student'}).then(function(yes){if(!yes)return null; var apply=new FormData();apply.append('user_id',st.user_id);apply.append('review_token',review.review_token);apply.append('item_decisions',JSON.stringify(rows));return fetch('/api/powergrader/session/'+sessionId+'/new-quiz-finalize',{method:'POST',body:apply}).then(function(r){return r.json();});});
    }).then(function(result){ if(!result)return; if(!result.ok) throw new Error(result.error || 'Finalization was not verified.'); st.new_quiz_finalized=true; if(q.showStatus)q.showStatus('New Quiz item scores and feedback finalized.',false); }).catch(function(err){if(q.showStatus)q.showStatus(String(err.message || err),true);}).finally(function(){finalBtn.disabled=false;});
  });
})();
