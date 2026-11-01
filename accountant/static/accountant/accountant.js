(() => {
  "use strict";
  const rows = [...document.querySelectorAll("[data-row-id]")];
  const children = key => rows.filter(row => row.dataset.parent === key);
  function collapse(row) {
    const button = row.querySelector("[data-toggle-row]");
    if (button) button.setAttribute("aria-expanded", "false");
    children(row.dataset.rowId).forEach(child => {
      child.hidden = true;
      collapse(child);
    });
  }
  document.querySelectorAll("[data-toggle-row]").forEach(button => {
    button.addEventListener("click", () => {
      const row = button.closest("tr");
      if (button.getAttribute("aria-expanded") === "true") collapse(row);
      else {
        button.setAttribute("aria-expanded", "true");
        children(row.dataset.rowId).forEach(child => { child.hidden = false; });
      }
    });
  });
  document.querySelector("[data-expand-all]")?.addEventListener("click", () => {
    rows.forEach(row => { row.hidden = false; });
    document.querySelectorAll("[data-toggle-row]").forEach(b => b.setAttribute("aria-expanded", "true"));
  });
  document.querySelector("[data-collapse-all]")?.addEventListener("click", () => {
    rows.filter(row => !row.dataset.parent).forEach(collapse);
  });
})();

