/* ── CanvasExpert panel kit ──────────────────────────────────────────────
   Row-count logic for Classroomscreen embed panels.

   CSS can make rows fill the available height, but it cannot decide how many
   rows SHOULD be there. That is the call that actually makes these panels
   responsive: a short wide panel wants three large rows paging quickly, a
   tall one wants eight. This module measures the box and makes that call,
   then re-makes it whenever the teacher drags a corner.
   ──────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* How many rows fit in `bodyEl` at a readable size?
     targetRow scales with the panel so big panels get big rows rather than
     simply more of them, but never drops below minRow (illegible on a
     projector) or above maxRow (comically large). */
  function rowsThatFit(bodyEl, opts) {
    opts = opts || {};
    var bodyH  = bodyEl.clientHeight;
    var panelH = document.documentElement.clientHeight;
    var panelW = document.documentElement.clientWidth;
    if (!bodyH) return opts.fallback || 3;

    /* Row height is bounded by BOTH dimensions. Height alone is not enough:
       in a tall narrow panel the text ends up width-limited, so tall rows
       just add padding around small type. Roughly, text renders at 36% of
       row height but no more than ~6.5% of row width, so rows stop paying
       for themselves past about 0.19 x width. */
    var target = clamp(Math.min(panelH / (opts.divisor || 4.5), panelW * 0.19),
                       opts.minRow || 52,
                       /* Raising this starves the row of columns: text is
                          sized against ROW width but constrained to its own
                          column, so very tall rows clip rather than fill. */
                       opts.maxRow || 100);
    var n = Math.floor(bodyH / target);

    /* Legibility floor. Text renders at roughly 36% of row height, so past
       a point adding rows only buys smaller type. Never trade below this;
       show fewer items and page instead. (When the panel is narrow the
       binding constraint is width, not height, and the CSS tiers drop
       content rather than shrink it.) */
    var byFloor = Math.floor(bodyH * 0.36 / (opts.floor || 15));
    n = Math.min(n, byFloor);

    return clamp(n, 1, opts.max || 99);
  }

  /* Size watcher.

     ResizeObserver is the fast path, but it is delivered as part of the
     rendering lifecycle, and some embedding contexts never run that
     lifecycle: the observer simply never fires while layout genuinely
     changes underneath it. A projector panel that silently stops adapting
     is worse than a cheap poll, so we run both. `check` is a no-op when the
     box has not moved, and the caller no-ops again if the row count is
     unchanged, so the steady-state cost is two integer reads. */
  function onResize(el, fn) {
    var lastW = -1, lastH = -1;

    function check() {
      var w = el.clientWidth, h = el.clientHeight;
      if (w === lastW && h === lastH) return;
      lastW = w; lastH = h;
      fn();
    }

    var t = null;
    try {
      new ResizeObserver(function () {
        clearTimeout(t);
        t = setTimeout(check, 60);      /* settle mid-drag */
      }).observe(el);
    } catch (e) { /* no RO: the poll carries it */ }

    setInterval(check, 400);
    check();
    return check;
  }

  function fade(el) {
    el.classList.remove("p-in");
    void el.offsetWidth;           /* force reflow so the animation replays */
    el.classList.add("p-in");
  }

  /* Return the delay until a local minute-past-midnight boundary, just after
     the bell. Presentation text is deliberately not an input here: the
     server's numeric field is the timer contract. */
  function msUntilMinutes(minutes, now) {
    if (typeof minutes !== "number" || !Number.isFinite(minutes) ||
        minutes < 0 || minutes > 1439) return null;
    now = now || new Date();
    var when = new Date(now.getTime());
    when.setHours(0, minutes, 20, 0);  /* just past the bell */
    var wait = when - now;
    return wait > 0 && Number.isFinite(wait) ? wait : null;
  }

  /* ── paginated list ───────────────────────────────────────────────────
     cfg = { body, dots, items, render(item, rowEl), every, divisor,
             minRow, maxRow }                                            */
  function List(cfg) {
    this.cfg = cfg;
    this.page = 0;
    this.visible = 0;
    this.pages = [];
    this.timer = null;

    var self = this;
    onResize(cfg.body, function () { self.measure(); });
    this.measure();
  }

  List.prototype.measure = function () {
    var n = rowsThatFit(this.cfg.body, {
      divisor: this.cfg.divisor,
      minRow:  this.cfg.minRow,
      maxRow:  this.cfg.maxRow,
      max:     this.cfg.items.length,
      fallback: Math.min(3, this.cfg.items.length)
    });
    if (n === this.visible) return;      /* nothing structural changed */
    this.visible = n;
    this.repaginate();
  };

  List.prototype.repaginate = function () {
    var items = this.cfg.items, n = this.visible;
    this.pages = [];
    for (var i = 0; i < items.length; i += n) this.pages.push(items.slice(i, i + n));
    if (this.page >= this.pages.length) this.page = 0;

    var dots = this.cfg.dots;
    if (dots) {
      dots.innerHTML = "";
      for (var p = 0; p < this.pages.length; p++) {
        var d = document.createElement("span");
        d.className = "p-dot";
        dots.appendChild(d);
      }
    }
    this.show(true);
    this.restart();
  };

  List.prototype.show = function (skipFade) {
    var cfg = this.cfg;
    var rows = this.pages[this.page] || [];

    cfg.body.innerHTML = "";
    rows.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "p-row";
      cfg.render(item, row);
      cfg.body.appendChild(row);
    });
    /* keep row height stable when the last page is short */
    for (var i = rows.length; i < this.visible; i++) {
      var ghost = document.createElement("div");
      ghost.className = "p-row p-row--ghost";
      cfg.body.appendChild(ghost);
    }

    if (cfg.dots) {
      for (var d = 0; d < cfg.dots.children.length; d++) {
        cfg.dots.children[d].classList.toggle("on", d === this.page);
      }
    }
    if (!skipFade) fade(cfg.body);
  };

  List.prototype.restart = function () {
    var self = this;
    clearInterval(this.timer);
    if (this.pages.length > 1) {
      this.timer = setInterval(function () {
        self.page = (self.page + 1) % self.pages.length;
        self.show();
      }, this.cfg.every || 9000);
    }
  };

  global.Panel = {
    clamp: clamp,
    rowsThatFit: rowsThatFit,
    onResize: onResize,
    fade: fade,
    msUntilMinutes: msUntilMinutes,
    list: function (cfg) { return new List(cfg); }
  };
})(window);
