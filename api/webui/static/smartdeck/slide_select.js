/**
 * SmartDeck slide selection: the decision half of the display page.
 *
 * Pure by construction. No DOM, no timers, no module state, no globals read or written.
 * Given the resolved Slides, a wall-clock reading, and the two manual-override flags,
 * decide what the projector should show. Everything subtle about which Slide is right
 * lives here so it can be tested without a browser; display.js keeps the DOM and the
 * widget lifecycle, which need one.
 *
 * Loaded as a plain script before display.js. Read directly, as text, by
 * api/tests/smartdeck/slide_select.test.mjs -- keep it free of browser globals.
 */

/**
 * Decide what to show right now.
 *
 * @param {object} state
 * @param {Array}  state.slides   resolved Slides in authored order. windows is the ordered
 *                                list of "HH:MM" start/end windows, or an empty list when
 *                                the Slide's block did not resolve against today's schedule.
 *                                Legacy Slides may carry only start/end strings.
 * @param {string} state.nowHHMM  the wall clock as "HH:MM", zero padded.
 * @param {boolean} state.shuffleOn
 * @param {number} state.shuffleIndex        only read when shuffleOn.
 * @param {boolean} state.homeFallbackActive set by Home, see the "home_fallback" reason.
 * @returns {{reason: string, slide: object|null, nextSlide: object|null}} where reason is
 *   "shuffle"       manual rotation is driving; slide is the one to show
 *   "clock"         a block is current; slide is the one to show
 *   "home_fallback" Home was pressed and nothing is current; slide is Slide 1
 *   "empty"         the Deck has no Slides at all
 *   "none"          nothing to show; nextSlide is the next Slide due today, or null
 */
function chooseSlide(state) {
  const slides = (state && state.slides) || [];
  if (!slides.length) {
    return { reason: "empty", slide: null, nextSlide: null };
  }

  if (state.shuffleOn) {
    // Tolerate an index that has drifted out of range rather than showing nothing.
    const count = slides.length;
    const index = ((state.shuffleIndex % count) + count) % count;
    return { reason: "shuffle", slide: slides[index], nextSlide: null };
  }

  // Authored order breaks ties: two Slides on the same block show the earlier one.
  const current = slides.find((slide) => windowsOf(slide).some(
    (window) => window.start <= state.nowHHMM && state.nowHHMM < window.end));
  if (current) {
    return { reason: "clock", slide: current, nextSlide: null };
  }

  if (state.homeFallbackActive) {
    return { reason: "home_fallback", slide: slides[0], nextSlide: null };
  }

  return { reason: "none", slide: null, nextSlide: nextSlideAfter(slides, state.nowHHMM) };
}

/**
 * The next Slide due after nowHHMM, by earliest start time rather than by authored
 * position, with authored order breaking ties between equal starts. A Deck whose Slides
 * are not authored in time order used to advertise whichever one came first in the array.
 */
function nextSlideAfter(slides, nowHHMM) {
  let best = null;
  for (const slide of slides) {
    for (const window of windowsOf(slide)) {
      if (window.start <= nowHHMM) continue;
      if (best === null || window.start < best.start) best = { slide, start: window.start };
    }
  }
  return best ? { ...best.slide, start: best.start } : null;
}

/** Every time window a Slide occupies today, newest shape first, legacy shape second. */
function windowsOf(slide) {
  if (!slide) return [];
  if (Array.isArray(slide.windows) && slide.windows.length) {
    return slide.windows.filter(
      (window) => window && typeof window.start === "string" && typeof window.end === "string");
  }
  return hasTime(slide) ? [{ start: slide.start, end: slide.end }] : [];
}

/** A Slide whose block resolved against today's schedule, so it has a real time window. */
function hasTime(slide) {
  return Boolean(slide) && typeof slide.start === "string" && typeof slide.end === "string";
}
