/* The work timer: the one widget shipped against the contract in widgets.js.
 *
 * Read that file first; the contract is the artifact here and this is its proof.
 * Everything below is live state in memory, lost on refresh, and nothing it does
 * touches the day plan, the bell schedule, or the offering list.
 *
 * Two decisions worth stating, because they are the ones a second widget will
 * copy:
 *
 *   The timer counts wall time, not class time. A bell ringing underneath it
 *   does not stop it: a teacher who started ten minutes of work at 9:15 wants it
 *   to finish at 9:25. So `onPeriodChange` leaves a running session alone and
 *   only tidies up an idle one, while the rail, the strip, and the panes update
 *   underneath on their own.
 *
 *   Reset is set apart in the tray and asks a second time. Students will touch
 *   this screen, and physical separation plus a confirm means no single tap
 *   throws away a running timer.
 */
(function () {
  "use strict";

  var widgets = window.CE_GLASS_WIDGETS;
  if (!widgets) return;

  var BAR_COUNT = 24;
  var URGENT_SECONDS = 120;
  var TICK_MS = 250;
  var CONFIRM_MS = 4000;

  var view = null;
  var timerId = 0;
  var armTimer = 0;
  var session = null;

  function build() {
    var root = document.createElement("div");
    root.className = "glass-timer";

    var digits = document.createElement("p");
    digits.className = "glass-timer__digits";
    digits.textContent = "0:00";
    root.appendChild(digits);

    var bars = document.createElement("div");
    bars.className = "glass-timer__bars";
    var barEls = [];
    for (var i = 0; i < BAR_COUNT; i += 1) {
      var bar = document.createElement("span");
      bar.className = "glass-timer__bar";
      bars.appendChild(bar);
      barEls.push(bar);
    }
    root.appendChild(bars);

    var state = document.createElement("p");
    state.className = "glass-timer__state";
    root.appendChild(state);

    return { root: root, digits: digits, bars: barEls, state: state };
  }

  function trayButton(action) {
    return document.querySelector('[data-glass-timer="' + action + '"]');
  }

  function presetButtons() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-glass-preset]"));
  }

  /* ------------------------------------------------------------------ state */

  function start(minutes, ctx) {
    var total = Math.max(Math.round(minutes), 1) * 60;
    session = { total: total, remaining: total, running: true, at: Date.now() };
    disarmReset();
    ctx.claimFocus();
    ctx.showTray("running");
    startTicking(ctx);
    render(ctx);
  }

  function stop(ctx) {
    session = null;
    stopTicking();
    disarmReset();
    ctx.releaseFocus();
    ctx.showTray("rest");
    render(ctx);
  }

  function startTicking(ctx) {
    stopTicking();
    timerId = window.setInterval(function () { advance(ctx); }, TICK_MS);
  }

  function stopTicking() {
    if (timerId) window.clearInterval(timerId);
    timerId = 0;
  }

  function advance(ctx) {
    if (!session) return;
    var now = Date.now();
    if (session.running) {
      var elapsed = Math.max(now - session.at, 0);
      session.remaining = Math.max(session.remaining - elapsed / 1000, 0);
      if (session.remaining <= 0) {
        session.remaining = 0;
        session.running = false;
        stopTicking();
      }
    }
    session.at = now;
    render(ctx);
  }

  function pause(ctx) {
    if (!session || !session.running) return;
    advance(ctx);
    session.running = false;
    stopTicking();
    render(ctx);
  }

  function resume(ctx) {
    if (!session || session.running || session.remaining <= 0) return;
    session.running = true;
    session.at = Date.now();
    startTicking(ctx);
    render(ctx);
  }

  /* Plus one minute is also how a custom duration gets built: the Custom preset
     starts a one-minute timer and each tap adds another, so no keypad and no
     typing on a projected surface. */
  function addMinute(ctx) {
    if (!session) return;
    var wasFinished = session.remaining <= 0;
    session.total += 60;
    session.remaining += 60;
    if (wasFinished) {
      session.running = true;
      session.at = Date.now();
      startTicking(ctx);
    }
    render(ctx);
  }

  function armReset(ctx) {
    var button = trayButton("reset");
    if (!button) return;
    button.setAttribute("data-glass-armed", "yes");
    button.textContent = "Tap again to reset";
    armTimer = window.setTimeout(function () { disarmReset(); }, CONFIRM_MS);
    render(ctx);
  }

  function disarmReset() {
    if (armTimer) window.clearTimeout(armTimer);
    armTimer = 0;
    var button = trayButton("reset");
    if (!button) return;
    button.removeAttribute("data-glass-armed");
    button.textContent = "Reset";
  }

  function resetPressed(ctx) {
    var button = trayButton("reset");
    var armed = button && button.getAttribute("data-glass-armed") === "yes";
    if (armed) {
      stop(ctx);
      return;
    }
    armReset(ctx);
  }

  /* --------------------------------------------------------------- rendering */

  function digitsText(seconds) {
    var whole = Math.ceil(seconds);
    var minute = Math.floor(whole / 60);
    var second = whole % 60;
    return minute + ":" + (second < 10 ? "0" : "") + second;
  }

  function render(ctx) {
    var remaining = session ? session.remaining : 0;
    var total = session ? session.total : 0;

    if (view) {
      view.digits.textContent = digitsText(remaining);

      var filled = total > 0 ? Math.ceil((remaining / total) * BAR_COUNT) : 0;
      view.bars.forEach(function (bar, index) {
        bar.classList.toggle("glass-timer__bar--filled", index < filled);
      });

      view.root.classList.toggle(
        "glass-timer--urgent", Boolean(session) && remaining <= URGENT_SECONDS
      );

      var label = "";
      if (session && session.remaining <= 0) {
        label = "Time is up";
      } else if (session && !session.running) {
        label = "Paused";
      } else if (session) {
        label = "Working";
      }
      view.state.textContent = label;
    }

    var pauseButton = trayButton("pause");
    var resumeButton = trayButton("resume");
    if (pauseButton) pauseButton.disabled = !session || !session.running;
    if (resumeButton) {
      resumeButton.disabled = !session || session.running || session.remaining <= 0;
    }
  }

  /* ---------------------------------------------------------------- wiring */

  function wire(ctx) {
    presetButtons().forEach(function (button) {
      button.addEventListener("click", function () {
        start(Number(button.getAttribute("data-glass-preset")) || 1, ctx);
      });
    });
    [
      ["pause", function () { pause(ctx); }],
      ["resume", function () { resume(ctx); }],
      ["add", function () { addMinute(ctx); }],
      ["reset", function () { resetPressed(ctx); }]
    ].forEach(function (pair) {
      var button = trayButton(pair[0]);
      if (button) button.addEventListener("click", pair[1]);
    });
  }

  widgets.register({
    name: "timer",
    launcherLabel: "Work timer",
    claimsFocus: true,
    trayStates: { rest: "glass-tray-rest", running: "glass-tray-running" },
    defaultTrayState: "rest",

    buildFocus: function () {
      view = build();
      return view.root;
    },

    summon: function (ctx) {
      wire(ctx);
      render(ctx);
    },

    dismiss: function (ctx) {
      stop(ctx);
    },

    /* The bell rang. A running session is wall time and keeps going; an idle one
       gets out of the way so the new period's learning goal comes back. */
    onPeriodChange: function (ctx) {
      if (session) {
        render(ctx);
        return;
      }
      if (ctx.hasFocus()) ctx.releaseFocus();
      ctx.showTray("rest");
    }
  });
})();
