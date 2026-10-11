"use strict";
const rows = [...document.querySelectorAll(".case-row")];
const search = document.getElementById("search");
const state = document.getElementById("state-filter");
const category = document.getElementById("category-filter");
function filterCases() {
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  for (const row of rows) {
    const match = row.dataset.search.includes(query)
      && (state.value === "all" || row.dataset.state === state.value)
      && (category.value === "all" || row.dataset.category === category.value);
    row.hidden = !match;
    visible += Number(match);
  }
  document.getElementById("visible-count").textContent = `${visible} / ${rows.length}개`;
  document.getElementById("empty-filter").hidden = visible !== 0;
}
if (search) {
  search.addEventListener("input", filterCases);
  state.addEventListener("change", filterCases);
  category.addEventListener("change", filterCases);
}
const canvas = document.querySelector(".canvas");
if (canvas) {
  document.getElementById("boxes").addEventListener("change", event => {
    canvas.classList.toggle("hide-boxes", !event.target.checked);
  });
  document.getElementById("zoom").addEventListener("change", event => {
    const zoom = event.target.value;
    canvas.style.width = zoom === "fit" ? "100%" : `${Number(canvas.dataset.width) * Number(zoom)}px`;
    canvas.style.maxWidth = zoom === "fit" ? `${canvas.dataset.width}px` : "none";
  });
}
