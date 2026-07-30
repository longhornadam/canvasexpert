(function () {
  'use strict';
  var form = document.getElementById('pg-new-quiz-csv-form');
  if (!form) return;
  var status = document.getElementById('pg-new-quiz-csv-status');
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var course = document.getElementById('pg-course');
    var assignment = document.getElementById('pg-assignment');
    if (!course.value || !assignment.value) {
      status.textContent = 'Choose the original course and assignment first.';
      return;
    }
    var data = new FormData(form);
    data.append('course_id', course.value);
    data.append('assignment_id', assignment.value);
    data.append('assignment_name', assignment.options[assignment.selectedIndex].text || assignment.value);
    status.textContent = 'Creating private review session…';
    fetch('/api/powergrader/new-quiz-csv', {method: 'POST', body: data})
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (!payload.ok) throw new Error(payload.error || 'CSV session was not created.');
        window.location.assign('/powergrader/session/' + encodeURIComponent(payload.session_id));
      })
      .catch(function (error) { status.textContent = String(error.message || error); });
  });

  function byId(id) { return document.getElementById(id); }
  function request(url, options) {
    return fetch(url, options).then(function (response) { return response.json(); });
  }
  function slug(value, prefix) {
    var stem=String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    return prefix + (stem || 'custom');
  }
  function refreshPersonas() {
    request('/api/feedback/personas').then(function (payload) {
      var remove=byId('pg-custom-persona-delete');
      if (!remove) return;
      remove.innerHTML='<option value="">— none —</option>' + (payload.personas || []).filter(function(p){return !p.builtin;}).map(function(p){
        return '<option value="' + String(p.id).replace(/"/g, '&quot;') + '">' + String(p.name) + '</option>';
      }).join('');
    });
  }
  var personaForm=byId('pg-custom-persona-form');
  if (personaForm) personaForm.addEventListener('submit', function(event) {
    event.preventDefault(); var status=byId('pg-custom-persona-status');
    var name=byId('pg-custom-persona-name').value.trim(); var personality=byId('pg-custom-persona-personality').value.trim();
    if (status) status.textContent='Saving…';
    request('/api/feedback/personas/custom',{method:'POST',body:new URLSearchParams({persona_id:slug(name,'custom_'),name:name,personality:personality})})
      .then(function(payload){if(!payload.ok)throw new Error(payload.error || 'Could not save persona.'); if(status)status.textContent='Saved.'; refreshPersonas(); window.setTimeout(function(){window.location.reload();},300);})
      .catch(function(error){if(status)status.textContent=String(error.message || error);});
  });
  var removePersona=byId('pg-custom-persona-remove');
  if (removePersona) removePersona.addEventListener('click',function(){
    var select=byId('pg-custom-persona-delete'); if(!select.value)return;
    request('/api/feedback/personas/custom',{method:'DELETE',body:new URLSearchParams({persona_id:select.value})})
      .then(function(payload){if(!payload.ok)throw new Error(payload.error || 'Could not remove persona.'); window.location.reload();})
      .catch(function(error){byId('pg-custom-persona-status').textContent=String(error.message || error);});
  });

  var patterns=[];
  function numberValue(id) { return Number(byId(id).value); }
  function fillPattern(pattern) {
    byId('pg-pattern-name').value=pattern.name || '';
    byId('pg-pattern-glows-min').value=(pattern.glows || {}).min;
    byId('pg-pattern-glows-max').value=(pattern.glows || {}).max;
    byId('pg-pattern-grows-min').value=(pattern.grows || {}).min;
    byId('pg-pattern-grows-max').value=(pattern.grows || {}).max;
    byId('pg-pattern-strategy-min').value=(pattern.strategy_sentences || {}).min;
    byId('pg-pattern-strategy-max').value=(pattern.strategy_sentences || {}).max;
    byId('pg-pattern-score').checked=!!pattern.score_from_rubric;
    byId('pg-pattern-sign').checked=!!pattern.sign_with_persona;
  }
  function refreshPatterns() {
    request('/api/feedback/patterns').then(function(payload){
      patterns=payload.patterns || []; var select=byId('pg-pattern-edit'); if(!select)return;
      select.innerHTML=patterns.map(function(pattern){return '<option value="' + String(pattern.id).replace(/"/g, '&quot;') + '">' + String(pattern.name) + '</option>';}).join('');
      if(patterns[0])fillPattern(patterns[0]);
    });
  }
  var patternSelect=byId('pg-pattern-edit');
  if(patternSelect) patternSelect.addEventListener('change',function(){
    var selected=patterns.find(function(pattern){return String(pattern.id)===patternSelect.value;}); if(selected)fillPattern(selected);
  });
  var patternForm=byId('pg-feedback-pattern-form');
  if(patternForm) patternForm.addEventListener('submit',function(event){
    event.preventDefault(); var status=byId('pg-pattern-status'); var selected=patterns.find(function(pattern){return String(pattern.id)===patternSelect.value;}) || {};
    var pattern={id:selected.id || slug(byId('pg-pattern-name').value,'pattern_'),name:byId('pg-pattern-name').value.trim(),score_from_rubric:byId('pg-pattern-score').checked,glows:{min:numberValue('pg-pattern-glows-min'),max:numberValue('pg-pattern-glows-max')},grows:{min:numberValue('pg-pattern-grows-min'),max:numberValue('pg-pattern-grows-max')},strategy_sentences:{min:numberValue('pg-pattern-strategy-min'),max:numberValue('pg-pattern-strategy-max')},sign_with_persona:byId('pg-pattern-sign').checked};
    var next=patterns.map(function(value){return String(value.id)===String(pattern.id) ? pattern : value;});
    if(!next.some(function(value){return String(value.id)===String(pattern.id);})){next.push(pattern);}
    if(status)status.textContent='Saving…';
    request('/api/feedback/patterns',{method:'POST',body:new URLSearchParams({patterns:JSON.stringify(next)})})
      .then(function(payload){if(!payload.ok)throw new Error(payload.error || 'Could not save pattern.'); patterns=payload.patterns || []; if(status)status.textContent='Saved.'; refreshPatterns(); window.setTimeout(function(){window.location.reload();},300);})
      .catch(function(error){if(status)status.textContent=String(error.message || error);});
  });
  refreshPersonas(); refreshPatterns();
}());
