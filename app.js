const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ROLE = document.body.dataset.role, SUSPENDED = document.body.dataset.suspended === "1";
const LABEL = { available: "Available", issued: "Issued", maintenance: "Maintenance", condemned: "Condemned" };
const COLOR = { available: "green", issued: "amber", maintenance: "grey", condemned: "red" };
let items = [];

async function loadCatalog() {
  const tbody = $("#catalog");
  if (!tbody) return;
  const url = `/api/equipment?q=${encodeURIComponent($("#q").value)}&sport=${encodeURIComponent($("#sport").value)}`;
  const data = await (await fetch(url)).json();
  items = data.items;
  for (const k in data.stats) { const el = $("#st-" + k); if (el) el.textContent = data.stats[k]; }
  tbody.innerHTML = items.length ? items.map(row).join("") : `<tr><td colspan="7">No equipment matches. Try another keyword.</td></tr>`;
}

function row(e) {
  const badge = `<span class="badge ${COLOR[e.status]}">${LABEL[e.status]}</span>` + (e.due_at ? ` <small>back ${esc(e.due_at)}</small>` : "");
  let act = "";
  if (ROLE === "coordinator") {
    act = `<button class="btn small" data-edit="${e.id}">Edit</button>
           <button class="btn small" data-hist="${e.id}">History</button>
           <a class="btn small" href="/coord/label/${e.id}" target="_blank">Label</a>`;
  } else if (e.status === "available" && !e.reserved) {
    act = `<button class="btn small primary" data-req="${e.id}" ${SUSPENDED ? "disabled" : ""}>Request</button>`;
  } else if (e.reserved) act = `<small>Requested</small>`;
  const photoThumb = e.photo ? `<img src="${esc(e.photo)}" style="width:32px;height:32px;object-fit:cover;border-radius:4px;margin-right:6px;vertical-align:middle;">` : '';
  return `<tr><td>${photoThumb}<b>${esc(e.name)}</b> <small>${esc(e.brand)}</small></td><td>${esc(e.sport)}</td>
    <td><code>${esc(e.sku)}</code></td><td>${esc(e.rack)}</td><td>Grade ${esc(e.grade)}</td><td>${badge}</td><td>${act}</td></tr>`;
}

function openDlg(name, title, action, mode) {
  const d = $("#dlg-" + name);
  const t = $(".dlg-title", d); if (t) t.textContent = title;
  const f = $("form", d); if (f && action) f.action = action;
  d.classList.remove("adding", "editing"); if (mode) d.classList.add(mode);
  d.showModal();
  return d;
}

document.addEventListener("click", async ev => {
  const b = ev.target.closest("button, a");
  if (!b) return;
  if (b.dataset.close !== undefined) b.closest("dialog").close();
  if (b.dataset.dlg) {
    const d = openDlg(b.dataset.dlg, b.dataset.title, b.dataset.action, b.dataset.dlg === "equip" ? "adding" : "");
    if (b.dataset.dlg === "equip") { $("form", d).reset(); $("[name=id]", d).value = ""; }
  }
  if (b.dataset.req) {
    const e = items.find(i => i.id == b.dataset.req);
    $("#req-id").value = e.id; $("#req-name").textContent = `${e.name} (${e.sku})`;
    $("#dlg-request").showModal();
  }
  if (b.dataset.edit) {
    const e = items.find(i => i.id == b.dataset.edit);
    const d = openDlg("equip", `Edit ${e.sku}`, "/coord/equipment", "editing");
    for (const k of ["id", "name", "sport", "brand", "rack", "grade", "status"]) {
      const el = $(`[name=${k}]`, d); if (el) el.value = e[k] === "issued" ? "available" : e[k];
    }
  }
  if (b.dataset.hist) {
    const e = items.find(i => i.id == b.dataset.hist);
    const d = openDlg("history", `${e.name} · ${e.sku}`);
    const h = await (await fetch(`/coord/history/${e.id}`)).json();
    $("#hist").innerHTML = h.length ? `<table><thead><tr><th>Request ID</th><th>Group</th><th>Out</th><th>Back</th><th>Wear & Photos</th><th>Fine</th></tr></thead>` +
      h.map(x => {
        const reqId = `#REQ-${String(x.id).padStart(4, '0')}`;
        const photos = [
          x.issue_photo ? `<a href="${esc(x.issue_photo)}" target="_blank" title="Handover Condition Photo"><img src="${esc(x.issue_photo)}" style="width:36px;height:36px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-left:6px;border:1px solid #ccc;"></a>` : '',
          x.return_photo ? `<a href="${esc(x.return_photo)}" target="_blank" title="Return Condition Photo"><img src="${esc(x.return_photo)}" style="width:36px;height:36px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-left:4px;border:1px solid #ccc;"></a>` : ''
        ].join('');
        return `<tr><td><code>${reqId}</code></td><td>${esc(x.group)}</td><td>${esc(x.issued_at || x.status)}</td><td>${esc(x.returned_at || "–")}</td>
        <td><b>${esc(x.issue_grade || "–")} → ${esc(x.return_grade || "–")}</b> ${photos}</td><td>₹${x.fine.toFixed(2)}</td></tr>`;
      }).join("") + "</table>"
      : `<p class="empty" style="padding:1rem">This unit has not been borrowed yet.</p>`;
  }
});

let timer;
$("#q")?.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(loadCatalog, 200); });
$("#sport")?.addEventListener("change", loadCatalog);
loadCatalog();
setInterval(loadCatalog, 20000); // keep stock counters live
