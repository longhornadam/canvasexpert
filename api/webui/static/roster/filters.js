(function () {
  "use strict";

  var roster = window.CE_ROSTER || {};
  var ready = [
    "getStudents",
    "getGroupState",
    "setFilteredStudents",
    "renderTable",
    "hasLoadedCourse"
  ].every(function (name) { return typeof roster[name] === "function"; });

  if (!ready) {
    window.alert("Roster filter tools need a page refresh.");
    return;
  }

  var searchInput = document.getElementById("roster-search");
  var filterBtns = document.querySelectorAll(".roster-filter-btn");
  if (!searchInput || !filterBtns.length) {
    return;
  }

  function filterStudents() {
    var students = roster.getStudents() || [];
    var q = (searchInput.value || "").toLowerCase().trim();
    var activeFilter = document.querySelector(".roster-filter-btn.active");
    var filter = activeFilter ? activeFilter.dataset.filter : "all";
    var filtered = [];

    for (var i = 0; i < students.length; i++) {
      var s = students[i];
      if (q) {
        var haystack = (s.name + " " + s.display_name + " " + s.short_name + " " +
          (s.nicknames || []).join(" ") + " " + (s.pseudonym || "") + " " +
          ((s.monitored && s.monitored.note) || "")).toLowerCase();
        if (haystack.indexOf(q) === -1) {
          continue;
        }
      }
      if (filter === "extra_time" && !s.extra_time.enabled) continue;
      if (filter === "monitored" && !s.monitored.enabled) continue;
      if (filter === "group_unset" && s.canvas_group && s.canvas_group.group_id) continue;
      if (filter === "warnings" && (!s.warnings || s.warnings.length === 0)) continue;
      filtered.push(s);
    }

    roster.setFilteredStudents(filtered);
    roster.renderTable();
    return filtered;
  }

  function setActiveFilter(btn) {
    for (var i = 0; i < filterBtns.length; i++) {
      filterBtns[i].classList.remove("active");
    }
    if (btn) {
      btn.classList.add("active");
    }
  }

  function applyFocusParam() {
    var params = new URLSearchParams(window.location.search);
    if (params.get("focus") === "extra-time") {
      for (var i = 0; i < filterBtns.length; i++) {
        if (filterBtns[i].dataset.filter === "extra_time") {
          setActiveFilter(filterBtns[i]);
          break;
        }
      }
    }
  }

  searchInput.addEventListener("input", filterStudents);

  for (var i = 0; i < filterBtns.length; i++) {
    filterBtns[i].addEventListener("click", function () {
      setActiveFilter(this);
      filterStudents();
    });
  }

  roster.applyFilters = filterStudents;
  applyFocusParam();
  if (roster.hasLoadedCourse()) {
    filterStudents();
  }
})();
