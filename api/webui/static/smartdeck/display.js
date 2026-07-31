/**
 * SmartDeck classroom display page.
 *
 * Interaction model:
 * - Fetch payload once on load from /smartdeck/display/{deck_id}/data
 * - Zero further network requests after initial load
 * - Two independent slide-selection mechanisms:
 *   A) Wall-clock auto-advance (runs every 5s, matches slides by time)
 *   B) Manual Shuffle (toggle, runs every 29s, cycles through all slides)
 * - Home returns control to A and shows what is current, falling back to Slide 1
 *   for as long as the clock has no answer
 * - Widget lifecycle: deck-scoped widgets persist, slide-scoped widgets reset each slide
 * - Timer widget: 1s interval (never rAF), wall-clock based
 */

let payload = null;
let shuffleIndex = 0;
let currentSlideId = null;
let shuffleOn = false;

let wallClockInterval = null;
let shuffleInterval = null;

// Set by Home, consumed by the wall-clock check. Home asks for whatever is current;
// when nothing is, this holds the deck on Slide 1 instead of blanking the stage, until
// the schedule has an answer. Without a flag the 5s tick would undo it immediately.
let homeFallbackActive = false;

// Widget lifecycle state
const mountedDeckWidgetIds = new Set();
// Teardown callbacks for the slide-scoped widgets currently on the stage. Clearing
// the stage removes their DOM but not their timers, so every slide change has to run
// these first: this page runs unattended all day, and Shuffle remounts on a 29s cycle.
let mountedSlideWidgetTeardowns = [];

/**
 * Unmount the slide-scoped widgets currently on the stage. Deck-scoped widgets are
 * deliberately left alone -- they persist for the life of the page.
 */
function teardownSlideWidgets() {
  for (const teardown of mountedSlideWidgetTeardowns) {
    try {
      teardown();
    } catch (err) {
      console.error("Widget teardown failed:", err);
    }
  }
  mountedSlideWidgetTeardowns = [];
}

/**
 * Initialize on page load: fetch payload, check clocks, set up initial display.
 */
document.addEventListener("DOMContentLoaded", async () => {
  const root = document.getElementById("sd-display-root");
  const deckId = root.dataset.deckId;

  // Fetch the display payload
  try {
    const response = await fetch(`/smartdeck/display/${deckId}/data`);
    if (!response.ok) {
      document.getElementById("sd-slide-stage").textContent = "Deck not found";
      return;
    }
    payload = await response.json();
    if (!payload.ok) {
      document.getElementById("sd-slide-stage").textContent = "Error loading deck";
      return;
    }
  } catch (err) {
    console.error("Failed to fetch display payload:", err);
    document.getElementById("sd-slide-stage").textContent = "Error loading deck";
    return;
  }

  // Clock skew check
  checkClockSkew(payload.server_time);

  // Date banner check
  checkDateBanner(payload.date);

  // Set up UI controls
  setupControls();

  // Initialize and start wall-clock auto-advance
  startWallClockAutoAdvance();
});

/**
 * Check for clock skew > 2 minutes between server and client.
 */
function checkClockSkew(serverTimeIso) {
  const serverTime = new Date(serverTimeIso).getTime();
  const clientTime = Date.now();
  const diffMs = Math.abs(serverTime - clientTime);
  const diffMinutes = diffMs / (1000 * 60);

  if (diffMinutes > 2) {
    const warning = document.getElementById("sd-clock-skew-warning");
    warning.textContent = "Warning: Your device clock appears to be off. The slide timing may not match.";
    warning.hidden = false;
  }
}

/**
 * Local (not UTC) YYYY-MM-DD, matching the deck's own date field.
 */
function localDateString(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/**
 * Show date banner if deck date is not today.
 */
function checkDateBanner(deckDate) {
  const today = localDateString(new Date());
  if (deckDate && deckDate !== today) {
    const banner = document.getElementById("sd-date-banner");
    banner.textContent = `Showing a SmartDeck for ${deckDate} — not today`;
    banner.hidden = false;
  }
}

/**
 * Mechanism A: Wall-clock auto-advance (runs every 5s).
 * Scans slides in array order for first match against current time window.
 */
function startWallClockAutoAdvance() {
  // Run check immediately
  performWallClockCheck();

  // Then set up interval
  if (wallClockInterval) clearInterval(wallClockInterval);
  wallClockInterval = setInterval(performWallClockCheck, 5000);
}

/** The wall clock as "HH:MM", the form chooseSlide compares against. */
function nowHHMM() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

function performWallClockCheck() {
  if (shuffleOn) return; // Suspended while Shuffle is on

  const decision = chooseSlide({
    slides: payload.slides,
    nowHHMM: nowHHMM(),
    shuffleOn: false,
    shuffleIndex,
    homeFallbackActive,
  });

  if (decision.reason === "clock") {
    // The clock has an answer, so any pending Home fallback is spent and normal
    // between-blocks behavior resumes from here.
    homeFallbackActive = false;
  }

  if (decision.slide) {
    showSlide(decision.slide);
  } else {
    showNotScheduled(decision.nextSlide);
  }
}

/**
 * Show the "not scheduled" message. nextSlide comes from chooseSlide and may be null
 * when nothing further is due today.
 */
function showNotScheduled(nextSlide) {
  const notScheduled = document.getElementById("sd-not-scheduled");
  const stage = document.getElementById("sd-slide-stage");

  if (nextSlide) {
    notScheduled.textContent = `Next: ${nextSlide.block} at ${nextSlide.start}`;
  } else {
    notScheduled.textContent = "Nothing else scheduled today";
  }

  teardownSlideWidgets();
  stage.innerHTML = "";
  notScheduled.hidden = false;
  currentSlideId = null;
}

/**
 * Mechanism B: Manual Shuffle toggle.
 */
function setupControls() {
  const shuffleBtn = document.getElementById("sd-shuffle");
  const homeBtn = document.getElementById("sd-home");
  const maximizeBtn = document.getElementById("sd-maximize");
  const minimizeBtn = document.getElementById("sd-minimize");
  const closeBtn = document.getElementById("sd-close");

  // Disable shuffle if <= 1 slide
  if (payload.slides.length <= 1) {
    shuffleBtn.disabled = true;
  }

  shuffleBtn.addEventListener("click", () => {
    if (shuffleOn) {
      // Turn OFF shuffle
      turnOffShuffle();
    } else {
      // Turn ON shuffle
      turnOnShuffle();
    }
  });

  homeBtn.addEventListener("click", () => {
    // Home hands control back to the clock and shows whatever is current right now.
    // performWallClockCheck falls back to Slide 1 when nothing is.
    homeFallbackActive = true;
    if (shuffleOn) {
      turnOffShuffle();  // already re-arms the wall-clock check
    } else {
      startWallClockAutoAdvance();
    }
  });

  maximizeBtn.addEventListener("click", () => {
    document.documentElement.requestFullscreen().then(() => {
      maximizeBtn.hidden = true;
      minimizeBtn.hidden = false;
    }).catch(err => {
      console.error("Fullscreen request failed:", err);
    });
  });

  minimizeBtn.addEventListener("click", () => {
    document.exitFullscreen().then(() => {
      minimizeBtn.hidden = true;
      maximizeBtn.hidden = false;
    }).catch(err => {
      console.error("Exit fullscreen failed:", err);
    });
  });

  // Sync buttons on browser fullscreen change
  document.addEventListener("fullscreenchange", () => {
    if (document.fullscreenElement) {
      maximizeBtn.hidden = true;
      minimizeBtn.hidden = false;
    } else {
      minimizeBtn.hidden = true;
      maximizeBtn.hidden = false;
    }
  });

  closeBtn.addEventListener("click", () => {
    window.location.href = "/smartdeck";
  });
}

function turnOnShuffle() {
  if (wallClockInterval) clearInterval(wallClockInterval);

  shuffleOn = true;
  homeFallbackActive = false;  // a new manual choice supersedes an earlier Home
  // Set index to current slide or 0
  if (currentSlideId !== null) {
    shuffleIndex = payload.slides.findIndex(s => s.id === currentSlideId);
    if (shuffleIndex < 0) shuffleIndex = 0;
  } else {
    shuffleIndex = 0;
  }

  const shuffleBtn = document.getElementById("sd-shuffle");
  shuffleBtn.setAttribute("aria-pressed", "true");

  // Show current slide
  showSlide(payload.slides[shuffleIndex]);

  // Update hint and start interval
  updateShuffleHint();

  if (shuffleInterval) clearInterval(shuffleInterval);
  shuffleInterval = setInterval(() => {
    shuffleIndex = (shuffleIndex + 1) % payload.slides.length;
    const decision = chooseSlide({
      slides: payload.slides,
      nowHHMM: nowHHMM(),
      shuffleOn: true,
      shuffleIndex,
      homeFallbackActive: false,
    });
    if (decision.slide) showSlide(decision.slide);
    updateShuffleHint();
  }, 29000);
}

function turnOffShuffle() {
  if (shuffleInterval) clearInterval(shuffleInterval);

  shuffleOn = false;
  const shuffleBtn = document.getElementById("sd-shuffle");
  shuffleBtn.setAttribute("aria-pressed", "false");

  const shuffleHint = document.getElementById("sd-shuffle-hint");
  shuffleHint.textContent = "";

  // Restart wall-clock check immediately
  startWallClockAutoAdvance();
}

function updateShuffleHint() {
  const hint = document.getElementById("sd-shuffle-hint");
  hint.textContent = `on · ${shuffleIndex + 1} of ${payload.slides.length}`;
}

/**
 * showSlide: the ONE function that changes the displayed slide.
 * Handles widget lifecycle, layout rendering, and state tracking.
 */
function showSlide(slide) {
  if (slide.id === currentSlideId) return; // Already showing

  currentSlideId = slide.id;

  const stage = document.getElementById("sd-slide-stage");
  const notScheduled = document.getElementById("sd-not-scheduled");

  // Hide "not scheduled" if visible
  notScheduled.hidden = true;

  // Clear and rebuild the slide content
  teardownSlideWidgets();
  stage.innerHTML = "";

  // Build slide DOM based on layout
  const slideDiv = document.createElement("div");
  slideDiv.className = "sd-slide";

  // Title (all layouts have title)
  if (slide.title) {
    const title = document.createElement("h1");
    title.textContent = slide.title;
    slideDiv.appendChild(title);
  }

  // Body (depending on layout)
  if (slide.layout === "title_only") {
    // No body
  } else if (slide.layout === "bulleted") {
    // Body as bulleted list
    if (slide.body) {
      const ul = document.createElement("ul");
      const lines = slide.body.split("\n").filter(line => line.trim());
      for (const line of lines) {
        const li = document.createElement("li");
        li.textContent = line;
        ul.appendChild(li);
      }
      slideDiv.appendChild(ul);
    }
  } else {
    // title_body (default)
    if (slide.body) {
      const p = document.createElement("p");
      p.textContent = slide.body;
      slideDiv.appendChild(p);
    }
  }

  // Slide-scoped widgets container (rebuilt each showSlide)
  const slideWidgetsDiv = document.createElement("div");
  slideWidgetsDiv.id = "sd-slide-widgets";

  // Widget lifecycle
  for (const widget of slide.widgets) {
    if (widget.scope === "slide") {
      // Create fresh instance, and remember how to stop it when this slide goes away
      const widgetEl = createWidget(widget);
      if (widgetEl) {
        slideWidgetsDiv.appendChild(widgetEl);
        if (widgetEl.teardown) {
          mountedSlideWidgetTeardowns.push(widgetEl.teardown);
        }
      }
    } else if (widget.scope === "deck") {
      // Deck-scoped: only create if not already mounted
      if (!mountedDeckWidgetIds.has(widget.id)) {
        const widgetEl = createWidget(widget);
        if (widgetEl) {
          document.getElementById("sd-deck-widgets").appendChild(widgetEl);
          mountedDeckWidgetIds.add(widget.id);
        }
      }
    }
  }

  slideDiv.appendChild(slideWidgetsDiv);
  stage.appendChild(slideDiv);
}

/**
 * Create a widget DOM element based on kind and params.
 */
function createWidget(widget) {
  if (widget.kind === "timer") {
    return createTimerWidget(widget);
  }
  // Add other widget types here as needed
  return null;
}

/**
 * Format a count of seconds as MM:SS.
 */
function formatRemaining(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Timer widget: wall-clock based, 1s interval.
 */
function createTimerWidget(widget) {
  const params = widget.params || {};

  const container = document.createElement("div");
  container.className = "sd-timer";
  container.dataset.widgetId = widget.id;

  // Display: MM:SS
  const display = document.createElement("div");
  display.className = "sd-timer-display";
  display.textContent = formatRemaining(params.duration_seconds || 0);
  container.appendChild(display);

  // Label
  if (params.label) {
    const label = document.createElement("p");
    label.className = "sd-timer-label";
    label.textContent = params.label;
    container.appendChild(label);
  }

  // Controls
  const controlsDiv = document.createElement("div");
  controlsDiv.className = "sd-timer-controls";

  const startBtn = document.createElement("button");
  startBtn.className = "sd-timer-btn";
  startBtn.type = "button";
  startBtn.textContent = "Start";
  startBtn.style.minWidth = "44px";
  startBtn.style.minHeight = "44px";

  const pauseBtn = document.createElement("button");
  pauseBtn.className = "sd-timer-btn";
  pauseBtn.type = "button";
  pauseBtn.textContent = "Pause";
  pauseBtn.style.minWidth = "44px";
  pauseBtn.style.minHeight = "44px";
  pauseBtn.disabled = true;

  const resetBtn = document.createElement("button");
  resetBtn.className = "sd-timer-btn";
  resetBtn.type = "button";
  resetBtn.textContent = "Reset";
  resetBtn.style.minWidth = "44px";
  resetBtn.style.minHeight = "44px";

  controlsDiv.appendChild(startBtn);
  controlsDiv.appendChild(pauseBtn);
  controlsDiv.appendChild(resetBtn);
  container.appendChild(controlsDiv);

  // Timer state
  let endTimestamp = null;
  let interval = null;
  let paused = false;
  let remainingWhenPaused = params.duration_seconds || 0;

  function updateDisplay() {
    let remaining;
    if (paused) {
      remaining = remainingWhenPaused;
    } else {
      remaining = Math.max(0, Math.round((endTimestamp - Date.now()) / 1000));
    }

    display.textContent = formatRemaining(remaining);

    if (remaining <= 0) {
      display.classList.add("sd-timer-done");
      if (interval) clearInterval(interval);
      interval = null;
      startBtn.disabled = false;
      pauseBtn.disabled = true;
    }
  }

  startBtn.addEventListener("click", () => {
    if (!endTimestamp || paused) {
      // Starting fresh or resuming
      if (paused) {
        // Resume: recompute endTimestamp from remaining
        endTimestamp = Date.now() + remainingWhenPaused * 1000;
        paused = false;
      } else {
        // Fresh start
        endTimestamp = Date.now() + (params.duration_seconds || 0) * 1000;
        display.classList.remove("sd-timer-done");
      }

      startBtn.disabled = true;
      pauseBtn.disabled = false;

      if (interval) clearInterval(interval);
      interval = setInterval(updateDisplay, 1000);
      updateDisplay();
    }
  });

  pauseBtn.addEventListener("click", () => {
    if (!paused) {
      paused = true;
      remainingWhenPaused = Math.max(0, Math.round((endTimestamp - Date.now()) / 1000));
      if (interval) clearInterval(interval);
      startBtn.disabled = false;
      pauseBtn.disabled = true;
      updateDisplay();
    }
  });

  resetBtn.addEventListener("click", () => {
    if (interval) clearInterval(interval);
    endTimestamp = null;
    paused = false;
    remainingWhenPaused = params.duration_seconds || 0;
    display.classList.remove("sd-timer-done");
    startBtn.disabled = false;
    pauseBtn.disabled = true;
    display.textContent = formatRemaining(remainingWhenPaused);
  });

  // Stop the countdown when this widget is unmounted. Without this the interval
  // outlives the removed DOM and keeps ticking against a detached node forever.
  container.teardown = () => {
    if (interval) clearInterval(interval);
    interval = null;
  };

  // If autostart, begin immediately
  if (params.autostart) {
    endTimestamp = Date.now() + (params.duration_seconds || 0) * 1000;
    startBtn.disabled = true;
    pauseBtn.disabled = false;
    if (interval) clearInterval(interval);
    interval = setInterval(updateDisplay, 1000);
    updateDisplay();
  }

  return container;
}
