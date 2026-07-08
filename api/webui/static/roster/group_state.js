(function () {
  "use strict";

  var roster = window.CE_ROSTER || {};
  var ready = [
    "getGroupState",
    "getCurrentCourseId",
    "onCourseLoaded",
    "setSelectedGroupCategoryId",
    "postForm"
  ].every(function (name) { return typeof roster[name] === "function"; });

  if (!ready) {
    window.alert("Roster group-state tools need a page refresh.");
    return;
  }

  var groupSetPicker = document.getElementById("roster-group-set-picker");
  var groupCategoryChangeHooks = [];
  if (!groupSetPicker) {
    return;
  }

  function syncGroupPicker() {
    var state = roster.getGroupState() || {};
    var groups = state.groups || [];
    var selected = state.selectedGroupCategoryId == null ? "" : String(state.selectedGroupCategoryId);

    groupSetPicker.innerHTML = "";
    if (!groups.length) {
      groupSetPicker.innerHTML = '<option value="">- no group sets -</option>';
      return;
    }

    for (var i = 0; i < groups.length; i++) {
      var g = groups[i];
      var option = document.createElement("option");
      option.value = String(g.category_id);
      option.textContent = g.category_name;
      if (String(g.category_id) === selected) {
        option.selected = true;
      }
      groupSetPicker.appendChild(option);
    }
  }

  function saveGroupSetPreference() {
    roster.postForm("/api/roster/group-set-preference", {
      course_id: roster.getCurrentCourseId(),
      category_id: groupSetPicker.value || ""
    }).catch(function () { /* silent fail */ });
  }

  function notifyGroupCategoryChanged() {
    for (var i = 0; i < groupCategoryChangeHooks.length; i++) {
      try {
        groupCategoryChangeHooks[i]();
      } catch (err) {
        // Ignore hook failures so picker changes still apply.
      }
    }
  }

  groupSetPicker.addEventListener("change", function () {
    roster.setSelectedGroupCategoryId(this.value);
    notifyGroupCategoryChanged();
    saveGroupSetPreference();
  });

  roster.onCourseLoaded(syncGroupPicker);
  roster.onGroupCategoryChanged = function (fn) {
    if (typeof fn !== "function") return function () {};
    groupCategoryChangeHooks.push(fn);
    return function () {
      for (var i = groupCategoryChangeHooks.length - 1; i >= 0; i--) {
        if (groupCategoryChangeHooks[i] === fn) {
          groupCategoryChangeHooks.splice(i, 1);
        }
      }
    };
  };
  syncGroupPicker();
})();
