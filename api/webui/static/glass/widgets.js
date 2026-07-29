/* The Glass widget contract.
 *
 * This file is the contract, and the contract is the point. One widget ships
 * with it; the value is that the second one costs almost nothing.
 *
 * ---------------------------------------------------------------------------
 * What a widget declares
 * ---------------------------------------------------------------------------
 *   name              short id, unique. Used as the tray owner key.
 *   launcherLabel     the words a launcher row would show. No launcher exists
 *                     yet, because with one widget it is pointless indirection.
 *                     Declared now so the second widget does not have to
 *                     retrofit one.
 *   claimsFocus       whether this widget may take over the focus slot. A
 *                     widget that only lives in the tray declares false.
 *   trayStates        { stateKey: elementId }. The widget's tray markup lives
 *                     in the page template, one element per state, and the
 *                     runtime shows exactly one of them. Every state element
 *                     sits inside the fixed-height tray, so a state change can
 *                     never move anything above it.
 *   defaultTrayState  which state key the widget rests in.
 *   buildFocus(ctx)   returns the element to place in the focus slot. Called
 *                     once, lazily, only if the widget ever claims focus.
 *   summon(ctx)       the widget is now the tray owner. Wire listeners here.
 *   dismiss(ctx)      the widget is no longer the tray owner. Stop everything
 *                     live and release the focus slot.
 *   onPeriodChange(ctx, period)   the bell rang underneath it. See below.
 *
 * ---------------------------------------------------------------------------
 * How it is summoned and dismissed
 * ---------------------------------------------------------------------------
 * The runtime summons the default widget on load. `summon(name)` makes a widget
 * the tray owner and shows its default tray state; `dismiss(name)` reverses
 * that and releases the focus slot. Exactly one widget owns the tray at a time,
 * which is the seam a launcher row would drive when a second widget arrives.
 *
 * ---------------------------------------------------------------------------
 * How it reads and writes live state
 * ---------------------------------------------------------------------------
 * `ctx.state` is a plain object, created per widget, held in memory, and lost
 * on refresh. There is no endpoint that accepts it and nothing writes it to
 * disk. Touch mutates live state and never the plan, the schedule, or the
 * offering list. A widget that wants to persist something is a stop condition,
 * not a feature request to absorb here.
 *
 * ---------------------------------------------------------------------------
 * What happens when the period changes underneath a running widget
 * ---------------------------------------------------------------------------
 * The runtime repaints the rail, the progress line, the day strip, the panes,
 * and the banner on its own, underneath whatever holds the focus slot, and then
 * calls `onPeriodChange(ctx, period)` on every registered widget. The widget
 * decides. The rule for anything that counts down: keep running, because it
 * counts wall time and a teacher who started ten minutes of work at 9:15 wants
 * it to finish at 9:25 whether or not a bell rang. A widget that is idle should
 * release the focus slot so the new period's learning goal comes back.
 */
(function () {
  "use strict";

  var registered = [];
  var host = null;
  var trayOwnerName = "";
  var focusOwnerName = "";
  var focusListeners = [];

  function find(name) {
    for (var i = 0; i < registered.length; i += 1) {
      if (registered[i].widget.name === name) return registered[i];
    }
    return null;
  }

  function trayElements(entry) {
    var out = [];
    var states = entry.widget.trayStates || {};
    Object.keys(states).forEach(function (key) {
      var el = document.getElementById(states[key]);
      if (el) out.push(el);
    });
    return out;
  }

  function hideAllTrayStates() {
    registered.forEach(function (entry) {
      trayElements(entry).forEach(function (el) { el.hidden = true; });
    });
  }

  /* Show one tray state belonging to one widget. Everything else in the tray
     goes away, so the tray always presents exactly one state. */
  function showTray(name, stateKey) {
    var entry = find(name);
    if (!entry) return false;
    var id = (entry.widget.trayStates || {})[stateKey];
    var wanted = id ? document.getElementById(id) : null;
    if (!wanted) return false;
    hideAllTrayStates();
    wanted.hidden = false;
    entry.trayState = stateKey;
    return true;
  }

  function focusElement(entry) {
    if (entry.focusEl) return entry.focusEl;
    if (typeof entry.widget.buildFocus !== "function") return null;
    entry.focusEl = entry.widget.buildFocus(entry.ctx) || null;
    if (entry.focusEl && host && host.widgetHost) {
      host.widgetHost.appendChild(entry.focusEl);
      entry.focusEl.hidden = true;
    }
    return entry.focusEl;
  }

  function claimFocus(name) {
    var entry = find(name);
    if (!entry || !entry.widget.claimsFocus || !host) return false;
    var el = focusElement(entry);
    if (!el) return false;
    el.hidden = false;
    focusOwnerName = name;
    announceFocus();
    return true;
  }

  function releaseFocus(name) {
    var entry = find(name);
    if (!entry) return false;
    if (entry.focusEl) entry.focusEl.hidden = true;
    if (focusOwnerName === name) focusOwnerName = "";
    announceFocus();
    return true;
  }

  function announceFocus() {
    focusListeners.forEach(function (fn) {
      try { fn(focusOwnerName); } catch (err) { /* one listener cannot break the screen */ }
    });
  }

  function makeContext(widget) {
    var name = widget.name;
    return {
      name: name,
      state: {},
      claimFocus: function () { return claimFocus(name); },
      releaseFocus: function () { return releaseFocus(name); },
      hasFocus: function () { return focusOwnerName === name; },
      showTray: function (stateKey) { return showTray(name, stateKey); },
      trayState: function () { var e = find(name); return e ? e.trayState : ""; },
      goalLine: function () { return host ? host.goalLine : null; },
      day: function () { return window.CE_GLASS ? window.CE_GLASS.day : null; }
    };
  }

  function register(widget) {
    if (!widget || !widget.name) return false;
    if (find(widget.name)) return false;
    var entry = {
      widget: widget,
      ctx: null,
      focusEl: null,
      trayState: widget.defaultTrayState || ""
    };
    entry.ctx = makeContext(widget);
    registered.push(entry);
    return true;
  }

  function summon(name) {
    var entry = find(name);
    if (!entry) return false;
    if (trayOwnerName && trayOwnerName !== name) dismiss(trayOwnerName);
    trayOwnerName = name;
    showTray(name, entry.widget.defaultTrayState || entry.trayState);
    if (typeof entry.widget.summon === "function") entry.widget.summon(entry.ctx);
    return true;
  }

  function dismiss(name) {
    var entry = find(name);
    if (!entry) return false;
    if (typeof entry.widget.dismiss === "function") entry.widget.dismiss(entry.ctx);
    releaseFocus(name);
    if (trayOwnerName === name) trayOwnerName = "";
    return true;
  }

  function notifyPeriodChange(period) {
    registered.forEach(function (entry) {
      if (typeof entry.widget.onPeriodChange !== "function") return;
      try {
        entry.widget.onPeriodChange(entry.ctx, period);
      } catch (err) { /* a widget must not be able to stop the clock */ }
    });
  }

  window.CE_GLASS_WIDGETS = {
    /* Called once by the runtime with the page's focus-slot elements. */
    setHost: function (elements) { host = elements || null; },
    register: register,
    summon: summon,
    dismiss: dismiss,
    showTray: showTray,
    notifyPeriodChange: notifyPeriodChange,
    onFocusChange: function (fn) { if (typeof fn === "function") focusListeners.push(fn); },
    focusOwner: function () { return focusOwnerName; },
    trayOwner: function () { return trayOwnerName; },
    launchers: function () {
      return registered.map(function (entry) {
        return { name: entry.widget.name, label: entry.widget.launcherLabel || entry.widget.name };
      });
    }
  };
})();
