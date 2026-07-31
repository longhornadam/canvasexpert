(function () {
  "use strict";

  var links = Array.prototype.slice.call(document.querySelectorAll('[data-rail-link]'));
  if (!links.length || !window.IntersectionObserver) return;

  var linkTargets = links
    .map(function (link) { return document.querySelector(link.getAttribute('href')); })
    .filter(Boolean);

  var highlightFor = new Map();
  linkTargets.forEach(function (el) { highlightFor.set(el, el.id); });

  var extraTargets = [];
  Array.prototype.forEach.call(document.querySelectorAll('[data-rail-covered-by]'), function (el) {
    var coveringId = el.getAttribute('data-rail-covered-by');
    if (!coveringId || !document.getElementById(coveringId)) return;
    highlightFor.set(el, coveringId);
    extraTargets.push(el);
  });

  var targets = linkTargets.concat(extraTargets);

  function setActive(id) {
    links.forEach(function (link) {
      link.classList.toggle('is-active', link.getAttribute('href') === '#' + id);
    });
  }

  // A short final section can never reach the observer's mid-viewport band once
  // the page runs out of room to scroll further, so bottom-of-page always wins
  // over whatever the observer's band-based check would otherwise pick.
  var lastId = linkTargets[linkTargets.length - 1].id;
  function atBottom() {
    return window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
  }

  var observer = new IntersectionObserver(function (entries) {
    if (atBottom()) { setActive(lastId); return; }
    var visible = entries
      .filter(function (entry) { return entry.isIntersecting; })
      .sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; });
    if (visible.length) setActive(highlightFor.get(visible[0].target));
  }, { rootMargin: '-15% 0px -70% 0px', threshold: 0 });

  targets.forEach(function (target) { observer.observe(target); });

  window.addEventListener('scroll', function () {
    if (atBottom()) setActive(lastId);
  }, { passive: true });

  if (!location.hash) setActive(linkTargets[0].id);
})();
