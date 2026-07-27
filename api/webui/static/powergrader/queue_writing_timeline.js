(function(){
  "use strict";

  var queue = window.CE_POWERGRADER_QUEUE || (window.CE_POWERGRADER_QUEUE = {});

  function esc(s) {
    if (queue.esc) return queue.esc(s);
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ── Central time ───────────────────────────────────────────────────── */

  // Every timeline clock the teacher reads is Central, with the CST/CDT marker
  // spelled out. The backend already normalizes to Central, but rendering through
  // an explicit time zone means even a stray UTC value displays correctly rather
  // than turning an evening writing session into apparent overnight work.
  var CENTRAL_FORMAT = {
    timeZone: 'America/Chicago',
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short'
  };

  function formatCentral(value) {
    var raw = String(value || '');
    if (!raw) return '';
    var parsed = new Date(raw);
    if (isNaN(parsed.getTime())) return raw;
    try {
      return parsed.toLocaleString('en-US', CENTRAL_FORMAT);
    } catch (e) {
      return raw;
    }
  }
  queue.formatWritingTimelineTime = formatCentral;

  /* ── Signal derivation ──────────────────────────────────────────────── */

  function isOtherAuthorCategory(value) {
    return value === 'other_roster_author' || value === 'unrecognized_author_present';
  }

  function writingTimelineSignals(students) {
    var result = {
      examined: [],
      noTrail: [],
      lockAbsent: [],
      otherName: [],
      unreadable: [],
      noDocument: []
    };
    var list = Array.isArray(students) ? students : [];
    list.forEach(function(st, i){
      var atts = (st && Array.isArray(st.attachments)) ? st.attachments : [];
      var reports = [];
      atts.forEach(function(a){
        if (a && typeof a === 'object' && a.writing_timeline) reports.push(a.writing_timeline);
      });
      if (!reports.length) {
        result.noDocument.push(i);
        return;
      }

      var hasUnreadable = false;
      var available = [];
      reports.forEach(function(r){
        var status = (r && typeof r === 'object') ? r.status : undefined;
        if (status === 'available') available.push(r);
        else hasUnreadable = true;
      });
      if (hasUnreadable) result.unreadable.push(i);
      if (!available.length) return;

      result.examined.push(i);
      var noTrail = false, lockAbsent = false, otherName = false;
      available.forEach(function(r){
        if (r.trail_present === false) noTrail = true;
        if (r.tracking_lock_present === false) lockAbsent = true;
        var props = (r.properties && typeof r.properties === 'object') ? r.properties : {};
        var blocks = Array.isArray(r.blocks) ? r.blocks : [];
        // `creator_category` is deliberately NOT a trigger. Creator is whatever tool
        // or template produced the file -- "Microsoft Office User", a district
        // template, a lab image -- so it reads as an unrecognized author on nearly
        // every honest document. A count that fires on everything is not triage; it
        // just points at innocent students. It is still shown on the document card
        // as a fact. Who actually edited the text is the signal worth surfacing.
        if (isOtherAuthorCategory(props.last_modified_by_category)) otherName = true;
        blocks.forEach(function(b){
          if (b && isOtherAuthorCategory(b.author_category)) otherName = true;
        });
      });
      if (noTrail) result.noTrail.push(i);
      if (lockAbsent) result.lockAbsent.push(i);
      if (otherName) result.otherName.push(i);
    });
    return result;
  }
  queue.writingTimelineSignals = writingTimelineSignals;

  /* ── Summary strip ──────────────────────────────────────────────────── */

  var lastStripSignals = null;
  var SIGNAL_BUTTONS = [
    { key: 'noTrail',    suffix: ' with no revision trail' },
    { key: 'otherName',  suffix: ' with another name on the file' },
    { key: 'lockAbsent', suffix: ' with tracking lock absent' },
    { key: 'unreadable', suffix: ' could not be read' },
    { key: 'noDocument', suffix: ' with no document' }
  ];

  function bindStripClicksOnce(strip) {
    if (strip.dataset.timelineBound) return;
    strip.dataset.timelineBound = 'true';
    strip.addEventListener('click', function(e){
      var btn = e.target.closest ? e.target.closest('[data-timeline-signal]') : null;
      if (!btn || !strip.contains(btn)) return;
      var key = btn.getAttribute('data-timeline-signal');
      var indices = lastStripSignals && lastStripSignals[key];
      if (!indices || !indices.length) return;
      var cur = queue.getIndex ? queue.getIndex() : 0;
      var next;
      for (var n = 0; n < indices.length; n++) {
        if (indices[n] > cur) { next = indices[n]; break; }
      }
      if (next === undefined) next = indices[0];
      if (queue.renderStudent) queue.renderStudent(next);
    });
  }

  function renderWritingTimelineStrip(session) {
    var strip = document.getElementById('pg-timeline-strip');
    if (!strip) return;
    if (!session || session.writing_timeline_tracked !== true) {
      strip.hidden = true;
      return;
    }
    strip.hidden = false;

    var students = queue.getStudents ? queue.getStudents() : [];
    var signals = writingTimelineSignals(students);
    lastStripSignals = signals;

    var buttonsHtml = SIGNAL_BUTTONS.map(function(b){
      var n = signals[b.key].length;
      if (!n) return '';
      return '<button type="button" class="small" data-timeline-signal="' + b.key + '">' +
        n + esc(b.suffix) + '</button>';
    }).join('');

    strip.innerHTML =
      '<div class="pg-privacy-head">' +
        '<span class="pg-sub-label">Writing Timeline</span>' +
        // "of N submissions", not "of N documents": a student who uploaded no DOCX
        // has a submission but no document, and the headline must not imply otherwise.
        '<span class="pg-privacy-summary">' + signals.examined.length + ' of ' + students.length + ' submissions examined</span>' +
        '<div class="pg-privacy-actions">' + buttonsHtml + '</div>' +
      '</div>' +
      '<p class="pg-no-text">Counts describe editing process, not authorship or intent.</p>';

    bindStripClicksOnce(strip);
  }
  queue.renderWritingTimelineStrip = renderWritingTimelineStrip;

  /* ── Arrival sparkline + per-student timeline card ──────────────────── */

  function authorCategoryLabel(value) {
    if (value === 'submission_author') return 'submission author';
    if (value === 'other_roster_author') return 'other roster author';
    if (value === 'unrecognized_author_present') return 'unrecognized author present';
    return 'not available';
  }

  function considerBlocks(report) {
    var blocks = Array.isArray(report.blocks) ? report.blocks : [];
    var considered = [];
    blocks.forEach(function(b){
      if (!b || typeof b !== 'object') return;
      if (!b.timestamp) return;
      var t = Date.parse(b.timestamp);
      if (isNaN(t)) return;
      var cc = Number(b.character_count);
      if (!(cc > 0)) return;
      considered.push({ time: t, timestamp: b.timestamp, character_count: cc, type: b.type });
    });
    return considered;
  }

  function renderTimelineSparkline(report) {
    var considered = considerBlocks(report);
    if (!considered.length) return '';

    var times = considered.map(function(b){ return b.time; });
    var minT = Math.min.apply(null, times);
    var maxT = Math.max.apply(null, times);
    var maxChars = Math.max.apply(null, considered.map(function(b){ return b.character_count; }));

    var bars = considered.map(function(b){
      var x = (minT === maxT) ? 150 : 4 + (b.time - minT) / (maxT - minT) * (296 - 4);
      var h = Math.max(3, Math.min(32, (b.character_count / maxChars) * 32));
      var y = 36 - h;
      var isDeletion = b.type === 'deletion';
      var fill = isDeletion ? 'var(--ce-ink-muted)' : 'var(--ce-prepared)';
      var opacityAttr = isDeletion ? ' opacity="0.55"' : '';
      return '<rect x="' + (x - 1.5).toFixed(2) + '" y="' + y.toFixed(2) +
        '" width="3" height="' + h.toFixed(2) + '" fill="' + fill + '"' + opacityAttr + '></rect>';
    }).join('');

    var svg = '<svg aria-hidden="true" height="40" viewBox="0 0 300 40" class="pg-timeline-spark">' +
      bars +
      '<line x1="0" y1="36.5" x2="300" y2="36.5" stroke="var(--ce-rule)" stroke-width="1"></line>' +
      '</svg>';

    var sorted = considered.slice().sort(function(a, b){ return a.time - b.time; });
    var first = sorted[0].timestamp;
    var last = sorted[sorted.length - 1].timestamp;
    var k = considered.length;

    var insertionSum = 0;
    var largestInsertion = 0;
    considered.forEach(function(b){
      if (b.type === 'insertion') {
        insertionSum += b.character_count;
        if (b.character_count > largestInsertion) largestInsertion = b.character_count;
      }
    });

    var text = (k === 1 ? '1 revision block' : k + ' revision blocks') +
      ' from ' + esc(formatCentral(first)) + ' to ' + esc(formatCentral(last)) + '.';
    if (insertionSum > 0) {
      var pct = Math.round(100 * largestInsertion / insertionSum);
      text += ' Largest single insertion is ' + largestInsertion + ' characters, ' + pct + '% of inserted text.';
    }

    return svg + '<p class="pg-no-text">' + text + '</p>';
  }

  function renderWritingTimeline(report) {
    var html = '<div class="pg-sub-section"><div class="pg-sub-label">Writing Timeline</div>';
    if (!report || report.status !== 'available') {
      html += '<p class="pg-no-text">Timeline unavailable for this document.</p>';
      html += '<p class="pg-no-text">This timeline describes editing process, not authorship or intent.</p></div>';
      return html;
    }

    var properties = report.properties || {};
    html += '<ul class="pg-att-list">';
    html += '<li>Revision trail: <strong>' + (report.trail_present ? 'present' : 'absent') + '</strong></li>';
    html += '<li>Tracking lock: <strong>' + (report.tracking_lock_present ? 'present' : 'absent') + '</strong></li>';
    if (typeof properties.total_time_minutes === 'number') {
      html += '<li>Editing time: ' + properties.total_time_minutes + ' minute' +
        (properties.total_time_minutes === 1 ? '' : 's') + '</li>';
    }
    if (typeof properties.revision === 'number') {
      html += '<li>Document revision: ' + properties.revision + '</li>';
    }
    if (properties.creator_category) {
      html += '<li>Creator match: ' + esc(authorCategoryLabel(properties.creator_category)) + '</li>';
    }
    if (properties.last_modified_by_category) {
      html += '<li>Last modified by match: ' + esc(authorCategoryLabel(properties.last_modified_by_category)) + '</li>';
    }
    html += '</ul>';

    if (!report.trail_present) {
      html += '<p class="pg-no-text">No revision history — did the student write in the provided file?</p>';
    }

    html += renderTimelineSparkline(report);

    var largest = (report.largest_insertions || []).filter(function(block){
      return block && Number(block.character_count) > 0;
    }).slice(0, 3);
    html += '<div class="pg-sub-label">Three largest insertion blocks</div>';
    if (largest.length) {
      html += '<ol class="pg-att-list">';
      largest.forEach(function(block){
        var words = Number(block.word_count) || 0;
        var chars = Number(block.character_count) || 0;
        var when = block.timestamp ? ' at ' + esc(formatCentral(block.timestamp)) : '';
        var author = block.author_category
          ? ' · ' + esc(authorCategoryLabel(block.author_category))
          : '';
        html += '<li><strong>' + words + ' word' + (words === 1 ? '' : 's') +
          '</strong> (' + chars + ' characters) inserted as one block' + when + author + '</li>';
      });
      html += '</ol>';
    } else {
      html += '<p class="pg-no-text">No non-empty insertion blocks recorded.</p>';
    }
    html += '<p class="pg-no-text">This timeline describes editing process, not authorship or intent.</p></div>';
    return html;
  }
  queue.renderWritingTimeline = renderWritingTimeline;

  var currentSession = queue.getSession ? queue.getSession() : null;
  if (currentSession) renderWritingTimelineStrip(currentSession);
})();
