/* The Glass runtime: one clock ticking against one static day.
 *
 * The whole resolved day arrives in #glass-data as JSON, written once by the
 * route. Nothing here fetches, polls, or asks the server to recompute anything
 * at a period boundary. The plan and the bell schedule are fixed for the day;
 * only the clock moves, so the clock is the only thing that runs.
 *
 * That is also how the rail, the progress line, the day strip, the panes, and
 * the banner keep updating underneath a running widget: they are painted from
 * the same static structure on every tick, and the focus slot is the only thing
 * a widget can take.
 *
 * All live state is in memory and is lost on refresh, deliberately.
 */
(function () {
  "use strict";

  var source = document.getElementById("glass-data");
  if (!source) return;

  var day;
  try {
    day = JSON.parse(source.textContent);
  } catch (err) {
    return;
  }

  var TICK_MS = 1000;
  var BANNER_MS = 12000;
  /* Not a multiple or a factor of the banner's interval, so the two do not come
     round together and make the screen pulse. At 12 and 17 seconds they line up
     once every 204 seconds instead of every minute. */
  var BOBCAT_ROTATE_MS = 17000;

  var el = {
    dayType: document.getElementById("glass-day-type"),
    nowLabel: document.getElementById("glass-now-label"),
    remaining: document.getElementById("glass-remaining"),
    clock: document.getElementById("glass-clock"),
    progress: document.getElementById("glass-progress"),
    progressFill: document.getElementById("glass-progress-fill"),
    focusRest: document.getElementById("glass-focus-rest"),
    focusPassing: document.getElementById("glass-focus-passing"),
    focusWidget: document.getElementById("glass-focus-widget"),
    widgetHost: document.getElementById("glass-widget-host"),
    goal: document.getElementById("glass-goal"),
    goalLine: document.getElementById("glass-goal-line"),
    criteria: document.getElementById("glass-criteria"),
    passingCountdown: document.getElementById("glass-passing-countdown"),
    passingNext: document.getElementById("glass-passing-next"),
    work: document.getElementById("glass-work"),
    bobcatHeading: document.getElementById("glass-bobcat-heading"),
    bobcatWhen: document.getElementById("glass-bobcat-when"),
    bobcatList: document.getElementById("glass-bobcat-list"),
    bobcatMore: document.getElementById("glass-bobcat-more"),
    bobcatNote: document.getElementById("glass-bobcat-note"),
    events: document.getElementById("glass-events"),
    eventsPane: document.getElementById("glass-events-pane"),
    strip: document.getElementById("glass-strip"),
    banner: document.getElementById("glass-banner"),
    bannerText: document.getElementById("glass-banner-text")
  };

  var blocks = day.blocks || [];
  var lastBlockKey = null;
  var bannerItems = [];
  var bannerIndex = 0;
  var bobcatShown = "";
  var bobcatPage = 0;
  var bobcatPages = 1;
  var bobcatRotatedAt = 0;

  /* ------------------------------------------------------------- resolution */

  /* A small mirror of the server resolver, over the static day. Same two
     conventions: remaining minutes round up and elapsed minutes round down, so
     the rail never says "0 min" while a class is still in session. */
  function stateAt(seconds) {
    if (!day.is_school_day || !blocks.length) {
      return blank("no_school", "No school");
    }
    var first = blocks[0];
    var last = blocks[blocks.length - 1];

    if (seconds < first.start_seconds) {
      var toBell = Math.max(first.start_seconds - seconds, 0);
      return {
        placement: "before_school",
        label: "Before school",
        block: null,
        subBlock: null,
        nextBlock: first,
        elapsedMinutes: 0,
        remainingMinutes: Math.ceil(toBell / 60),
        remainingSeconds: toBell,
        percent: 0
      };
    }
    if (seconds >= last.end_seconds) {
      return blank("after_school", "After school");
    }

    for (var i = 0; i < blocks.length; i += 1) {
      var block = blocks[i];
      if (seconds >= block.start_seconds && seconds < block.end_seconds) {
        return inBlock(block, blocks[i + 1] || null, seconds);
      }
    }
    return passing(seconds);
  }

  function blank(placement, label) {
    return {
      placement: placement,
      label: label,
      block: null,
      subBlock: null,
      nextBlock: null,
      elapsedMinutes: 0,
      remainingMinutes: 0,
      remainingSeconds: 0,
      percent: 0
    };
  }

  function inBlock(block, nextBlock, seconds) {
    var subBlock = activeSubBlock(block, seconds);
    var span = subBlock || block;
    var elapsed = Math.max(seconds - span.start_seconds, 0);
    var remaining = Math.max(span.end_seconds - seconds, 0);
    var whole = elapsed + remaining;
    return {
      placement: "in_block",
      label: span.label,
      block: block,
      subBlock: subBlock,
      nextBlock: nextBlock,
      elapsedMinutes: Math.floor(elapsed / 60),
      remainingMinutes: Math.ceil(remaining / 60),
      remainingSeconds: remaining,
      percent: whole > 0 ? Math.round((elapsed / whole) * 100) : 0
    };
  }

  function activeSubBlock(block, seconds) {
    var sub = block.sub_blocks;
    if (!sub || sub.mode !== "sequential") return null;
    for (var i = 0; i < sub.blocks.length; i += 1) {
      var child = sub.blocks[i];
      if (seconds >= child.start_seconds && seconds < child.end_seconds) return child;
    }
    return null;
  }

  function passing(seconds) {
    var previous = blocks[0];
    var upcoming = blocks[blocks.length - 1];
    for (var i = 0; i + 1 < blocks.length; i += 1) {
      if (blocks[i].end_seconds <= seconds && seconds < blocks[i + 1].start_seconds) {
        previous = blocks[i];
        upcoming = blocks[i + 1];
        break;
      }
    }
    var elapsed = Math.max(seconds - previous.end_seconds, 0);
    var remaining = Math.max(upcoming.start_seconds - seconds, 0);
    var whole = elapsed + remaining;
    return {
      placement: "passing",
      label: "Passing",
      block: null,
      subBlock: null,
      nextBlock: upcoming,
      elapsedMinutes: Math.floor(elapsed / 60),
      remainingMinutes: Math.ceil(remaining / 60),
      remainingSeconds: remaining,
      percent: whole > 0 ? Math.round((elapsed / whole) * 100) : 0
    };
  }

  /* --------------------------------------------------------------- painting */

  function secondsNow() {
    if (day.clock_frozen) return day.at_seconds;
    var now = new Date();
    return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
  }

  function clockText(seconds) {
    var hour = Math.floor(seconds / 3600) % 12;
    var minute = Math.floor(seconds / 60) % 60;
    return (hour === 0 ? 12 : hour) + ":" + (minute < 10 ? "0" : "") + minute;
  }

  function countdownText(seconds) {
    var minute = Math.floor(seconds / 60);
    var second = seconds % 60;
    return minute + ":" + (second < 10 ? "0" : "") + second;
  }

  function remainingText(state) {
    if (state.placement === "in_block") {
      return state.remainingMinutes ? state.remainingMinutes + " min left" : "ending now";
    }
    if (state.placement === "passing") {
      return state.nextBlock
        ? state.remainingMinutes + " min to " + state.nextBlock.label
        : state.remainingMinutes + " min";
    }
    if (state.placement === "before_school") {
      return state.remainingMinutes + " min to first bell";
    }
    return "";
  }

  function setText(node, value) {
    if (node) node.textContent = value == null ? "" : String(value);
  }

  function paintRail(state, seconds) {
    setText(el.nowLabel, state.label);
    setText(el.remaining, remainingText(state));
    setText(el.clock, clockText(seconds));
  }

  function paintProgress(state) {
    if (el.progress) el.progress.setAttribute("data-percent", String(state.percent));
    if (el.progressFill) el.progressFill.style.width = state.percent + "%";
  }

  function paintStrip(state) {
    if (!el.strip) return;
    var wanted = state.block ? state.block.id : "";
    var items = el.strip.children;
    for (var i = 0; i < items.length; i += 1) {
      var item = items[i];
      var isNow = item.getAttribute("data-glass-block") === wanted && wanted !== "";
      item.classList.toggle("glass-strip__item--now", isNow);
    }
  }

  function currentPlan(state) {
    if (state.block && state.block.plan) return state.block.plan;
    return { learning_goal: "", success_criteria: [], work: [], banner: [] };
  }

  function paintFocus(state, changed) {
    var plan = currentPlan(state);
    var owner = window.CE_GLASS_WIDGETS ? window.CE_GLASS_WIDGETS.focusOwner() : "";
    if (changed) {
      setText(el.goal, plan.learning_goal);
      setText(el.goalLine, plan.learning_goal);
      renderTextList(el.criteria, plan.success_criteria);
    }
    setText(el.passingCountdown, countdownText(state.remainingSeconds));
    setText(el.passingNext, state.nextBlock ? "until " + state.nextBlock.label : "");

    var widgetOwns = Boolean(owner);
    if (el.focusWidget) el.focusWidget.hidden = !widgetOwns;
    if (el.focusPassing) {
      el.focusPassing.hidden = widgetOwns || state.placement !== "passing";
    }
    if (el.focusRest) {
      el.focusRest.hidden = widgetOwns || state.placement === "passing";
    }
  }

  function renderTextList(list, texts) {
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    (texts || []).forEach(function (text) {
      var li = document.createElement("li");
      li.textContent = text;
      list.appendChild(li);
    });
  }

  function renderList(list, items, itemClass) {
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    (items || []).forEach(function (item) {
      var li = document.createElement("li");
      li.className = itemClass || "";
      var name = document.createElement("span");
      name.className = "glass-pane__name";
      name.textContent = item.name || "";
      li.appendChild(name);
      if (item.detail) {
        var detail = document.createElement("span");
        detail.className = "glass-pane__detail";
        detail.textContent = item.detail;
        li.appendChild(detail);
      }
      list.appendChild(li);
    });
  }

  function paintWork(state) {
    renderList(el.work, currentPlan(state).work, "glass-pane__item");
  }

  /* The pane always shows the next Bobcat Hour that has not ended yet. Both
     candidates were rendered into the blob, so the flip from today to tomorrow
     happens here on the clock rather than on a request.
     Returns true when it rebuilt the list, because a different offering count
     changes how much rail the pane needs and the caller has to re-shed. */
  function paintBobcat(seconds) {
    var pane = day.bobcat_hour || {};
    var after = day.bobcat_hour_after || {};
    if (pane.is_today && after.available && seconds >= pane.end_seconds) {
      pane = after;
    }
    var key = (pane.heading || "") + "|" + (pane.on || "");
    if (key === bobcatShown) return false;
    bobcatShown = key;
    // A new list starts at its first page rather than wherever the old one was.
    bobcatPage = 0;
    bobcatRotatedAt = 0;

    setText(el.bobcatHeading, pane.heading || "Bobcat Hour");
    if (el.bobcatWhen) {
      var when = pane.available ? pane.start_text + " to " + pane.end_text : "";
      setText(el.bobcatWhen, when);
      el.bobcatWhen.hidden = !pane.available;
    }
    var items = [];
    if (pane.here && pane.here.label) {
      items.push({
        name: pane.here.label,
        detail: "in this room" + (pane.here.location ? ", " + pane.here.location : ""),
        here: true
      });
    }
    (pane.offerings || []).forEach(function (offering) {
      items.push({ name: offering.label, detail: offering.location });
    });
    if (el.bobcatList) {
      while (el.bobcatList.firstChild) el.bobcatList.removeChild(el.bobcatList.firstChild);
      items.forEach(function (item) {
        var li = document.createElement("li");
        li.className = item.here
          ? "glass-pane__item glass-pane__item--here"
          : "glass-pane__item";
        var name = document.createElement("span");
        name.className = "glass-pane__name";
        name.textContent = item.name || "";
        li.appendChild(name);
        if (item.detail) {
          var detail = document.createElement("span");
          detail.className = "glass-pane__detail";
          detail.textContent = item.detail;
          li.appendChild(detail);
        }
        el.bobcatList.appendChild(li);
      });
    }
    if (el.bobcatNote) {
      setText(el.bobcatNote, pane.note || "");
      el.bobcatNote.hidden = !pane.note;
    }
    return true;
  }

  /* The banner keeps its line whether or not there is anything to say, so the
     content above it does not shift every time a period without banner text
     comes around. */
  function paintBanner() {
    if (!el.bannerText) return;
    if (!bannerItems.length) {
      setText(el.bannerText, "");
      return;
    }
    setText(el.bannerText, bannerItems[bannerIndex % bannerItems.length]);
  }

  /* When the rail runs short of vertical room, whole items go rather than half a
     line, and which items go is decided by priority rather than by whichever
     list happens to notice its own overflow first.
     Events yield until the Bobcat Hour pane fits its offerings, then work
     yields, and the Bobcat Hour list is never shed. Driving this off each pane's
     own overflow instead looked right at moderate pressure and inverted at high
     pressure: with a long offering list, events was never itself overflowing, so
     it never gave anything up and the Bobcat Hour pane absorbed the whole
     shortfall by clipping.
     If events and work have both yielded everything and the offering list still
     does not fit, clipping the tail of that list is the floor. No cap, no
     scroller, and no "more" affordance: how many offerings a lunch hour may
     carry is a product decision that has not been made. */
  var LAYOUT_SLACK_PX = 1;

  function itemsOf(list) {
    return list ? Array.prototype.slice.call(list.children) : [];
  }

  function showAll(list) {
    itemsOf(list).forEach(function (item) { item.hidden = false; });
  }

  function fits(list) {
    if (!list) return true;
    return list.scrollHeight <= list.clientHeight + LAYOUT_SLACK_PX;
  }

  /* Hide trailing items from `list`, last first, until `enough` is satisfied.
     Reading a layout property between hides is what makes each step measured
     against the room the previous one actually freed. */
  function yieldItems(list, enough) {
    var items = itemsOf(list);
    for (var i = items.length - 1; i >= 0; i -= 1) {
      if (enough()) return;
      items[i].hidden = true;
    }
  }

  function shedPanes() {
    if (el.eventsPane) el.eventsPane.hidden = false;
    showAll(el.events);
    showAll(el.work);

    var bobcatFits = function () { return fits(el.bobcatList); };
    yieldItems(el.events, bobcatFits);
    yieldItems(el.work, bobcatFits);

    // A pane that still cuts its own last line loses that item too, so no pane
    // ever shows half a row.
    yieldItems(el.events, function () { return fits(el.events); });
    yieldItems(el.work, function () { return fits(el.work); });

    collapseEvents();
    applyBobcatPage();
  }

  /* Events is the pane that gives way, so once it has nothing left to show the
     whole section goes rather than leaving a heading over an empty list. */
  function collapseEvents() {
    if (!el.eventsPane || !el.events) return;
    var items = itemsOf(el.events);
    var showing = items.filter(function (item) { return !item.hidden; });
    el.eventsPane.hidden = items.length > 0 && showing.length === 0;
  }

  /* ------------------------------------------------- rotating a long list */

  /* Shedding decides how much rail the Bobcat Hour pane gets. This decides what
     the pane does with an offering list longer than that: it shows a page of
     rows and cycles, the way the banner cycles its text. A screen at the front
     of a room is not a static page, so a list too long to show is a list that
     moves rather than a list that is quietly cut off.
     Nothing here rotates when everything fits, because motion with nothing to
     reveal is only noise, and most days fit. */

  /* How many leading rows sit fully inside the list as it stands right now.
     Every item has to be visible for this to mean anything, which is why the
     caller shows them all first. */
  function fittedRowCount() {
    if (!el.bobcatList) return 0;
    var bounds = el.bobcatList.getBoundingClientRect();
    var items = itemsOf(el.bobcatList);
    var count = 0;
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].getBoundingClientRect().bottom > bounds.bottom + LAYOUT_SLACK_PX) {
        break;
      }
      count += 1;
    }
    return count;
  }

  function applyBobcatPage() {
    if (!el.bobcatList) return;
    var items = itemsOf(el.bobcatList);
    showAll(el.bobcatList);
    if (el.bobcatMore) el.bobcatMore.hidden = true;

    var capacity = fittedRowCount();
    if (!items.length || capacity >= items.length) {
      bobcatPages = 1;
      bobcatPage = 0;
      return;
    }

    // The page line takes room of its own, so capacity is measured again with it
    // in place. It only ever costs rows, so this cannot flip the decision back.
    // It has to carry its text before that measurement: an empty line is a line
    // of no height, which is how the first page came to hold one row more than
    // it could actually show.
    if (el.bobcatMore) {
      el.bobcatMore.hidden = false;
      setText(el.bobcatMore, pageLabel(1, capacity, items.length));
    }
    capacity = Math.max(fittedRowCount(), 1);

    bobcatPages = Math.ceil(items.length / capacity);
    // A period change can reshape the rail underneath a rotation, so the page
    // is clamped rather than assumed still to exist.
    if (bobcatPage >= bobcatPages) bobcatPage = 0;

    var start = bobcatPage * capacity;
    var end = Math.min(start + capacity, items.length);
    items.forEach(function (item, index) {
      item.hidden = index < start || index >= end;
    });
    if (el.bobcatMore) {
      setText(el.bobcatMore, pageLabel(start + 1, end, items.length));
    }
  }

  function pageLabel(first, last, total) {
    return first + " to " + last + " of " + total;
  }

  /* Advanced from the runtime's own tick, so there is no second loop racing the
     clock. A frozen clock parks the pane on its first page: `?at=` exists so a
     state can be looked at and measured, and a pane that kept moving under it
     would make every measurement of this page a different answer. */
  function rotateBobcatIfDue() {
    if (day.clock_frozen || bobcatPages <= 1) return;
    var now = Date.now();
    if (!bobcatRotatedAt) {
      bobcatRotatedAt = now;
      return;
    }
    if (now - bobcatRotatedAt < BOBCAT_ROTATE_MS) return;
    bobcatRotatedAt = now;
    advanceBobcat();
  }

  function advanceBobcat() {
    if (bobcatPages <= 1) return false;
    bobcatPage = (bobcatPage + 1) % bobcatPages;
    applyBobcatPage();
    return true;
  }

  /* ------------------------------------------------------------------ frame */

  function blockKey(state) {
    return state.block ? state.block.id : state.placement;
  }

  function paint() {
    var seconds = secondsNow();
    var state = stateAt(seconds);
    var key = blockKey(state);
    var changed = key !== lastBlockKey;

    paintRail(state, seconds);
    paintProgress(state);
    paintStrip(state);
    paintFocus(state, changed);
    var bobcatRebuilt = paintBobcat(seconds);

    if (changed) {
      lastBlockKey = key;
      paintWork(state);
      bannerItems = currentPlan(state).banner || [];
      bannerIndex = 0;
      paintBanner();
    }
    // Either a new period's work list or a new offering list changes what the
    // rail has to fit, so the priority is settled again before rotation picks a
    // page inside whatever room the Bobcat Hour pane ended up with.
    if (changed || bobcatRebuilt) shedPanes();
    rotateBobcatIfDue();

    if (changed) {
      if (window.CE_GLASS_WIDGETS) {
        window.CE_GLASS_WIDGETS.notifyPeriodChange({
          placement: state.placement,
          blockId: state.block ? state.block.id : "",
          subBlockId: state.subBlock ? state.subBlock.id : "",
          label: state.label,
          plan: currentPlan(state)
        });
      }
    }
    return state;
  }

  window.CE_GLASS = {
    day: day,
    secondsNow: secondsNow,
    stateAt: stateAt,
    state: function () { return stateAt(secondsNow()); },
    countdownText: countdownText,
    repaint: paint,
    /* Which page of a long offering list is showing, and a way to step it. Read
       state plus one step, so the rotation can be watched and driven without a
       test having to wait 17 seconds for it. Nothing here is persisted. */
    bobcatRotation: function () {
      return { page: bobcatPage, pages: bobcatPages, interval: BOBCAT_ROTATE_MS };
    },
    advanceBobcat: advanceBobcat
  };

  if (window.CE_GLASS_WIDGETS) {
    window.CE_GLASS_WIDGETS.setHost({
      widgetHost: el.widgetHost,
      goalLine: el.goalLine,
      restPane: el.focusRest,
      passingPane: el.focusPassing,
      widgetPane: el.focusWidget
    });
    window.CE_GLASS_WIDGETS.onFocusChange(function () { paint(); });
  }

  paint();

  if (!day.clock_frozen) {
    window.setInterval(paint, TICK_MS);
    window.setInterval(function () {
      if (!bannerItems.length) return;
      bannerIndex = (bannerIndex + 1) % bannerItems.length;
      paintBanner();
    }, BANNER_MS);
  }

  var shedTimer = 0;
  window.addEventListener("resize", function () {
    window.clearTimeout(shedTimer);
    shedTimer = window.setTimeout(shedPanes, 150);
  });

  /* The runtime summons the resting widget once every widget module has had a
     chance to register. With one widget this is the timer; with a launcher row
     it would be whichever the teacher taps.
     Waiting for the parser rather than for a zero timeout matters: widget
     modules load after this one, and a timeout can fire between two scripts,
     which leaves the tray with no owner and every tap doing nothing. */
  function bootWidgets() {
    if (!window.CE_GLASS_WIDGETS) return;
    var launchers = window.CE_GLASS_WIDGETS.launchers();
    if (launchers.length && !window.CE_GLASS_WIDGETS.trayOwner()) {
      window.CE_GLASS_WIDGETS.summon(launchers[0].name);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootWidgets);
  } else {
    window.setTimeout(bootWidgets, 0);
  }
})();
