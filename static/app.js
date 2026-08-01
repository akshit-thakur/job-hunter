(function () {
  var body = document.body;

  var selectAll = document.querySelector("[data-select-all]");
  var applicationChecks = document.querySelectorAll("input[name='application_ids']");
  var bulkSelectCells = document.querySelectorAll("[data-bulk-select]");
  var rowActionCells = document.querySelectorAll("[data-row-actions]");
  var bulkPanel = document.getElementById("bulk-edit-panel");
  var bulkCancel = document.getElementById("bulk-mode-cancel");
  function setBulkMode(enabled) {
    document.body.classList.toggle("bulk-mode", enabled);
    bulkSelectCells.forEach(function (cell) { cell.hidden = !enabled; });
    rowActionCells.forEach(function (cell) { cell.hidden = enabled; });
    if (!enabled) {
      applicationChecks.forEach(function (checkbox) { checkbox.checked = false; });
      if (selectAll) { selectAll.checked = false; }
    }
  }
  if (bulkPanel) {
    bulkPanel.addEventListener("toggle", function () {
      setBulkMode(bulkPanel.open);
    });
  }
  if (bulkCancel) {
    bulkCancel.addEventListener("click", function () {
      if (bulkPanel) { bulkPanel.open = false; }
      setBulkMode(false);
    });
  }
  if (selectAll) {
    selectAll.addEventListener("change", function () {
      applicationChecks.forEach(function (checkbox) {
        checkbox.checked = selectAll.checked;
      });
    });
  }

  function refreshColorSelect(select) {
    var kind = select.dataset.colorKind;
    var currentPrefix = kind + "-";
    select.className = select.className
      .split(/\s+/)
      .filter(function (className) {
        return className.indexOf(currentPrefix) !== 0;
      })
      .join(" ");
    if (select.value) {
      select.classList.add(currentPrefix + select.value);
    }
  }

  document.querySelectorAll(".color-coded-select[data-color-kind]").forEach(function (select) {
    refreshColorSelect(select);
    select.addEventListener("change", function () {
      refreshColorSelect(select);
    });
  });

  document.querySelectorAll(".application-row[data-view-url]").forEach(function (row) {
    function openDetails(event) {
      if (document.body.classList.contains("bulk-mode")) {
        return;
      }
      if (event.target.closest("a, button, form, input, select, textarea, details")) {
        return;
      }
      window.location.href = row.dataset.viewUrl;
    }

    row.addEventListener("click", openDetails);
    row.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDetails(event);
      }
    });
  });

  var url = body && body.dataset.duplicateLastUrl;
  if (!url) {
    return;
  }

  document.addEventListener("keydown", function (event) {
    if (event.key.toLowerCase() !== "d") {
      return;
    }
    if (!event.shiftKey || !(event.metaKey || event.ctrlKey)) {
      return;
    }
    event.preventDefault();
    var form = document.createElement("form");
    form.method = "post";
    form.action = url;
    form.hidden = true;
    document.body.appendChild(form);
    form.submit();
  });
})();
