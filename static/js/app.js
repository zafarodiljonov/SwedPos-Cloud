// SwedPos Cloud: sort a table by clicking a column, open a waiter's tables by clicking a row.
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var th = event.target.closest("table.report th");
    if (th) { sortBy(th); return; }
    var row = event.target.closest("table.report[data-drill] tr.click");
    if (row) { openDetail(row); }
  });

  function sortBy(th) {
    var table = th.closest("table");
    var index = Array.prototype.indexOf.call(th.parentNode.children, th);
    var numeric = th.dataset.numeric === "1";
    var desc = th.dataset.dir ? th.dataset.dir === "asc" : numeric;   // numbers start biggest first
    table.querySelectorAll("th").forEach(function (h) { h.removeAttribute("data-dir"); h.classList.remove("sorted"); });
    th.dataset.dir = desc ? "desc" : "asc";
    th.classList.add("sorted");
    var body = table.tBodies[0];
    var rows = Array.prototype.slice.call(body.rows);
    rows.sort(function (a, b) {
      var x = a.cells[index].dataset.v, y = b.cells[index].dataset.v;
      if (x === "" && y !== "") return 1;
      if (y === "" && x !== "") return -1;
      var r = numeric ? parseFloat(x) - parseFloat(y) : x.localeCompare(y);
      return desc ? -r : r;
    });
    rows.forEach(function (r) { body.appendChild(r); });
  }

  function openDetail(row) {
    var blocks = row.closest(".blocks");
    var table = row.closest("table");
    table.querySelectorAll("tr.picked").forEach(function (r) { r.classList.remove("picked"); });
    row.classList.add("picked");
    var url = "/r/" + blocks.dataset.rid + "/detail/" + table.dataset.drill + "/" + row.dataset.key + "/?" + blocks.dataset.query;
    var target = document.getElementById("detail");
    target.classList.add("loading");
    fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.text() : ""; })
      .then(function (html) {
        target.innerHTML = html;
        target.classList.remove("loading");
        target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
  }
})();
