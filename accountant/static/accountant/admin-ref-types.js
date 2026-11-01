(() => {
  "use strict";
  const selector = 'select[name="ref_type"], select[name$="-ref_type"]';

  function nameField(select) {
    return document.getElementsByName(select.name.replace(/ref_type$/, "display_name"))[0];
  }

  function initialize(root) {
    root.querySelectorAll(selector).forEach(select => {
      select.dataset.previousDisplayName = select.selectedOptions[0]?.dataset.displayName || "";
      const field = nameField(select);
      if (field && !field.value) field.value = select.dataset.previousDisplayName;
    });
  }

  document.addEventListener("change", event => {
    const select = event.target;
    if (!select.matches(selector)) return;
    const field = nameField(select);
    const displayName = select.selectedOptions[0]?.dataset.displayName || "";
    if (field && (!field.value.trim() || field.value === select.dataset.previousDisplayName)) {
      field.value = displayName;
    }
    select.dataset.previousDisplayName = displayName;
  });

  document.addEventListener("DOMContentLoaded", () => initialize(document));
  document.addEventListener("formset:added", event => initialize(event.target));
})();
