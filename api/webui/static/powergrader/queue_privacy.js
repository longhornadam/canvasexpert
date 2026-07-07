(function(){
  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});

  var privacyStrip = document.getElementById('pg-privacy-strip');
  var privacySummary = document.getElementById('pg-privacy-summary');
  var privacySteps = document.getElementById('pg-privacy-steps');
  var privacyActions = document.getElementById('pg-privacy-actions');

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }

  function getSession() {
    return queue.getSession ? queue.getSession() : null;
  }

  function renderPrivacyAudit(s) {
    if (!privacyStrip || !privacySummary || !privacySteps || !privacyActions) return;
    var steps = (s && s.privacy_steps) || [];
    if (!steps.length) {
      privacyStrip.hidden = true;
      privacySummary.textContent = '';
      privacySteps.innerHTML = '';
      privacyActions.innerHTML = '';
      return;
    }

    privacyStrip.hidden = false;
    var ok = steps.filter(function(st){ return st.status === 'ok'; }).length;
    var warn = steps.filter(function(st){ return st.status === 'warn'; }).length;
    var fail = steps.filter(function(st){ return st.status === 'failed'; }).length;
    privacySummary.textContent = ok + ' green' + (warn ? ', ' + warn + ' yellow' : '') + (fail ? ', ' + fail + ' red' : '');
    privacySteps.innerHTML = steps.map(function(step){
      var status = step.status || '';
      var light = status === 'ok' ? 'ok' : (status === 'warn' ? 'warn' : (status === 'failed' ? 'failed' : ''));
      var pathButton = step.path
        ? '<div class="pg-privacy-actions-inline"><button type="button" class="small" data-open-path="' + esc(step.path) + '">' + esc(step.action_label || 'Open file') + '</button></div>'
        : '';
      return '<div class="pg-privacy-step">' +
        '<span class="pg-light ' + light + '"></span>' +
        '<div><div class="pg-privacy-label" title="' + esc(step.label || '') + '">' + esc(step.label || step.id || 'Step') + '</div>' +
        (step.detail ? '<div class="pg-privacy-detail">' + esc(step.detail) + '</div>' : '') +
        pathButton +
        '</div></div>';
    }).join('');

    var artifacts = s.privacy_artifacts || {};
    var buttons = [];
    if (artifacts.safe_folder) buttons.push('<button type="button" class="small" data-open-path="' + esc(artifacts.safe_folder) + '">Open Safe AI Packet folder</button>');
    if (artifacts.private_folder) buttons.push('<button type="button" class="small" data-open-path="' + esc(artifacts.private_folder) + '">Open Private decoder folder</button>');
    privacyActions.innerHTML = buttons.join('');
  }

  queue.renderPrivacyAudit = renderPrivacyAudit;

  var currentSession = getSession();
  if (currentSession) renderPrivacyAudit(currentSession);
})();
