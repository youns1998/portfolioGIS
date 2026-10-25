const report = JSON.parse(document.querySelector("#report-data").textContent);
const rows = report.rows;
let shown = rows;
document.querySelector("#total").textContent = report.total;
document.querySelector("#high").textContent = report.high_priority;
document.querySelector("#uncovered").textContent = report.uncovered;
document.querySelector("#basis").textContent =
  `기준일 ${report.as_of} · 지원 반경 ${report.radius_m}m · 가상 시설 ${report.total}개`;
for (const zone of [...new Set(rows.map((r) => r.zone))].sort()) {
  const option = document.createElement("option");
  option.value = zone;
  option.textContent = zone;
  document.querySelector("#zone").append(option);
}
function select(id) {
  const row = rows.find((r) => r.id === id);
  if (!row) return;
  const box = document.querySelector("#detail");
  box.replaceChildren();
  const title = document.createElement("h2");
  title.textContent = row.name;
  box.append(title);
  for (const text of [
    `${row.id} · ${row.kind}`,
    `구역: ${row.zone}`,
    `우선순위: ${row.priority} / ${row.score}점`,
    `최근접 거점: ${row.nearest_center}`,
    `거리: ${row.distance_m.toLocaleString()}m / ${row.covered ? "반경 안" : "반경 밖"}`,
    `최종 점검: ${row.last_inspected}`,
    `점검 근거: ${row.reasons}`,
  ]) {
    const p = document.createElement("p");
    p.textContent = text;
    box.append(p);
  }
  document
    .querySelectorAll(".asset")
    .forEach((e) => e.classList.toggle("selected", e.dataset.id === id));
}
function render() {
  const query = document
    .querySelector("#search")
    .value.trim()
    .toLocaleLowerCase();
  const priority = document.querySelector("#priority").value;
  const zone = document.querySelector("#zone").value;
  shown = rows.filter(
    (r) =>
      (!priority || r.priority === priority) &&
      (!zone || r.zone === zone) &&
      (!query || (r.id + " " + r.name).toLocaleLowerCase().includes(query)),
  );
  document.querySelector("#count").textContent =
    `${shown.length} / ${rows.length}개 시설`;
  const body = document.querySelector("#rows");
  body.replaceChildren();
  const ids = new Set(shown.map((r) => r.id));
  document.querySelectorAll(".asset").forEach((e) => {
    e.toggleAttribute("hidden", !ids.has(e.dataset.id));
  });
  for (const row of shown) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    const button = document.createElement("button");
    button.textContent = row.name + " / " + row.id;
    button.onclick = () => select(row.id);
    td.append(button);
    tr.append(td);
    for (const value of [
      row.zone,
      row.priority,
      row.score,
      row.nearest_center,
      row.distance_m + "m",
      row.reasons,
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.append(cell);
    }
    body.append(tr);
  }
  if (!shown.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "empty";
    td.textContent = "조건에 맞는 시설이 없습니다.";
    tr.append(td);
    body.append(tr);
  }
}
for (const id of ["search", "priority", "zone"])
  document.querySelector("#" + id).addEventListener("input", render);
document.querySelectorAll(".asset").forEach((e) => {
  e.onclick = () => select(e.dataset.id);
  e.onkeydown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(e.dataset.id);
    }
  };
});
document.querySelector("#download").onclick = () => {
  const keys = [
    "id",
    "name",
    "zone",
    "priority",
    "score",
    "distance_m",
    "reasons",
  ];
  const csv = (v) =>
    '"' +
    String(v)
      .replace(/^[\s]*([=+@-])/g, "'$1")
      .replaceAll('"', '""') +
    '"';
  const text =
    "\uFEFF" +
    [keys, ...shown.map((r) => keys.map((k) => r[k]))]
      .map((row) => row.map(csv).join(","))
      .join("\r\n");
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/csv;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "filtered-facilities.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
render();
