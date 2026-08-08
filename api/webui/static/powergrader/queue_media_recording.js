(function(){
  'use strict';
  var q = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});
  var active = null;
  function esc(value) { var node=document.createElement('div'); node.textContent=String(value || ''); return node.innerHTML; }
  function duration(seconds) {
    seconds = Number(seconds || 0); if (!Number.isFinite(seconds) || seconds <= 0) return '';
    var minutes=Math.floor(seconds / 60), remainder=Math.round(seconds % 60);
    return minutes + ':' + String(remainder).padStart(2, '0');
  }
  q.stopMediaRecording = function(){
    if (active) { try { active.pause(); active.removeAttribute('src'); active.load(); } catch(e) {} active=null; }
  };
  q.renderMediaRecordings = function(student) {
    var pane = document.getElementById('pg-submission-pane');
    if (!pane || !student) return;
    var rows=(student.attachments || []).filter(function(item){ return item && item.media_recording; });
    if (!rows.length) return;
    var sessionId=q.getSessionId ? q.getSessionId() : '';
    rows.forEach(function(item){
      var section=document.createElement('section'); section.className='pg-sub-section pg-media-recording';
      var label=document.createElement('div'); label.className='pg-sub-label'; label.textContent='Media recording'; section.appendChild(label);
      var ready=(item.download_status === 'downloaded' || item.download_status === 'reused') && item.extraction_status === 'validated';
      if (!ready) {
        var held=document.createElement('p'); held.className='pg-no-text'; held.textContent='Recording held: ' + (item.error_message || 'Local media review is unavailable.'); section.appendChild(held);
      } else {
        var audio=document.createElement('audio'); audio.controls=true; audio.preload='metadata';
        audio.src='/api/powergrader/session/' + encodeURIComponent(sessionId) + '/media/' + encodeURIComponent(item.stream_key || '');
        audio.addEventListener('play', function(){ if(active && active !== audio) active.pause(); active=audio; });
        section.appendChild(audio);
        var note=document.createElement('p'); note.className='pg-no-text'; note.textContent=(item.filename || 'Recording') + (duration(item.duration_seconds) ? ' · ' + duration(item.duration_seconds) : '') + ' · local playback only'; section.appendChild(note);
        var report=item.oral_reading;
        if (report) {
          var evidence=document.createElement('div'); evidence.className='pg-media-evidence';
          var status=document.createElement('p'); status.className='pg-no-text';
          status.textContent=report.status === 'complete' ? 'Local read-aloud evidence — teacher review, not a score.' : 'Read-aloud evidence needs review: ' + ((report.uncertainty || []).join(', ') || report.error_message || 'analysis unavailable.');
          evidence.appendChild(status);
          if (report.passage) { var passage=document.createElement('p'); passage.textContent='Confirmed passage: ' + report.passage; evidence.appendChild(passage); }
          if (report.transcript) { var transcript=document.createElement('p'); transcript.textContent='Observed transcript: ' + report.transcript; evidence.appendChild(transcript); }
          if (report.metrics) { var metrics=document.createElement('p'); metrics.textContent='Exact-word accuracy: ' + Math.round(Number(report.metrics.accuracy || 0) * 100) + '% · WCPM: ' + Number(report.metrics.wcpm || 0).toFixed(1); evidence.appendChild(metrics); }
          (report.difference_candidates || []).forEach(function(candidate){
            var button=document.createElement('button'); button.type='button'; button.className='small';
            button.textContent=(candidate.kind || 'difference') + ': expected ' + (candidate.expected || '—') + ', observed ' + (candidate.observed || '—');
            button.addEventListener('click', function(){ if (Number.isFinite(Number(candidate.start_seconds))) { audio.currentTime=Number(candidate.start_seconds); audio.play(); } });
            evidence.appendChild(button);
          });
          section.appendChild(evidence);
        }
      }
      pane.appendChild(section);
    });
    if (student.analysis_unavailable) {
      var notice=document.createElement('p'); notice.className='pg-no-text'; notice.textContent=student.analysis_unavailable; pane.appendChild(notice);
    }
  };
})();
