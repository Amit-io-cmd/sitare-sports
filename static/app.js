const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ROLE = document.body.dataset.role, SUSPENDED = document.body.dataset.suspended === "1";
const LABEL = { available: "Available", issued: "Issued", maintenance: "Maintenance", condemned: "Condemned" };
const COLOR = { available: "green", issued: "amber", maintenance: "grey", condemned: "red" };
let items = [];

// ---------- DATE FORMATTING HELPER ----------
function fmtDt(str) {
  if (!str) return "–";
  try {
    const parts = String(str).trim().split(" ");
    if (parts.length >= 2 && parts[0].includes("-")) {
      const [y, m, d] = parts[0].split("-");
      const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      const monthName = months[parseInt(m, 10) - 1] || m;
      const dayNum = parseInt(d, 10);
      const timeStr = parts[1].substring(0, 5);
      return `${dayNum} ${monthName} ${y}<br>${timeStr}`;
    }
  } catch (e) {}
  return esc(str);
}

// ---------- TAB NAVIGATION & SIDEBAR ----------
function switchTab(tabId) {
  if (!tabId) return;
  if (tabId.startsWith('#')) tabId = tabId.substring(1);
  
  const panels = document.querySelectorAll('.tab-panel');
  let found = false;
  
  panels.forEach(panel => {
    if (panel.id === tabId) {
      panel.style.display = 'block';
      found = true;
    } else {
      panel.style.display = 'none';
    }
  });

  if (!found && panels.length > 0) {
    panels[0].style.display = 'block';
    tabId = panels[0].id;
  }

  // Update nav item highlights
  const navItems = document.querySelectorAll('.side-nav .nav-item');
  navItems.forEach(item => {
    const href = item.getAttribute('href');
    if (href === '#' + tabId) {
      item.classList.add('active');
      const titleEl = document.getElementById('active-tab-title');
      const textEl = item.querySelector('.nav-text');
      if (titleEl && textEl) titleEl.textContent = textEl.textContent;
    } else {
      item.classList.remove('active');
    }
  });

  // Save history and localStorage
  try {
    history.replaceState(null, null, '#' + tabId);
    localStorage.setItem('activeTab', tabId);
  } catch (e) {}
  
  // Close drawer on mobile
  toggleSidebar(false);
}

function toggleSidebar(show) {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  if (show === undefined) {
    sidebar.classList.toggle('open');
  } else if (show) {
    sidebar.classList.add('open');
  } else {
    sidebar.classList.remove('open');
  }
}

function openResetPwDlg(userId, userName) {
  const d = $("#dlg-admin-reset-pw");
  if (!d) return;
  $("#reset-user-id").value = userId;
  $("#reset-user-name").textContent = `Resetting password for user #${userId} (${userName})`;
  d.showModal();
}

// ---------- CATALOG & EQUIPMENT ----------
async function loadCatalog() {
  const tbody = $("#catalog");
  if (!tbody) return;
  const qEl = $("#q"), sEl = $("#sport");
  const qVal = qEl ? qEl.value : "";
  const sVal = sEl ? sEl.value : "";
  const url = `/api/equipment?q=${encodeURIComponent(qVal)}&sport=${encodeURIComponent(sVal)}`;
  try {
    const data = await (await fetch(url)).json();
    items = data.items;
    for (const k in data.stats) { const el = $("#st-" + k); if (el) el.textContent = data.stats[k]; }
    tbody.innerHTML = items.length ? items.map(row).join("") : `<tr><td colspan="7">No equipment matches. Try another keyword.</td></tr>`;
  } catch (err) {
    console.error("Failed to load catalog:", err);
  }
}

function row(e) {
  const badge = `<span class="badge ${COLOR[e.status]}">${LABEL[e.status]}</span>` + (e.due_at ? ` <span class="badge amber" style="margin-left:0.3rem;">due<br>${fmtDt(e.due_at)}</span>` : "");
  let act = "";
  if (ROLE === "coordinator" || ROLE === "admin") {
    act = `<button class="btn small" data-edit="${e.id}">Edit</button>
           <button class="btn small" data-hist="${e.id}">History</button>
           <a class="btn small" href="/coord/label/${e.id}" target="_blank">Label</a>`;
  } else if (e.status === "available" && !e.reserved) {
    act = `<button class="btn small primary" data-req="${e.id}" ${SUSPENDED ? "disabled" : ""}>Request</button>`;
  } else if (e.reserved) act = `<small>Requested</small>`;
  return `<tr><td><b>${esc(e.name)}</b> <small>${esc(e.brand)}</small></td><td>${esc(e.sport)}</td>
    <td><code>${esc(e.sku)}</code></td><td>${esc(e.rack)}</td><td>Grade ${esc(e.grade)}</td><td>${badge}</td><td>${act}</td></tr>`;
}

function openDlg(name, title, action, mode) {
  const d = $("#dlg-" + name);
  if (!d) return;
  const t = $(".dlg-title", d); if (t) t.textContent = title;
  const f = $("form", d); if (f && action) f.action = action;
  d.classList.remove("adding", "editing"); if (mode) d.classList.add(mode);
  d.showModal();
  return d;
}

document.addEventListener("click", async ev => {
  const b = ev.target.closest("button, a");
  if (!b) return;
  if (b.dataset.close !== undefined) {
    const dialog = b.closest("dialog");
    if (dialog) dialog.close();
  }
  if (b.dataset.dlg) {
    const d = openDlg(b.dataset.dlg, b.dataset.title, b.dataset.action, b.dataset.dlg === "equip" ? "adding" : "");
    if (b.dataset.dlg === "equip" && d) { $("form", d).reset(); $("[name=id]", d).value = ""; }
  }
  if (b.dataset.req) {
    const e = items.find(i => i.id == b.dataset.req);
    if (e) {
      $("#req-id").value = e.id; $("#req-name").textContent = `${e.name} (${e.sku})`;
      $("#dlg-request").showModal();
    }
  }
  if (b.dataset.edit) {
    const e = items.find(i => i.id == b.dataset.edit);
    if (e) {
      const d = openDlg("equip", `Edit ${e.sku}`, "/coord/equipment", "editing");
      for (const k of ["id", "name", "sport", "brand", "rack", "grade", "status"]) {
        const el = $(`[name=${k}]`, d); if (el) el.value = e[k] === "issued" ? "available" : e[k];
      }
    }
  }
  if (b.dataset.hist) {
    const e = items.find(i => i.id == b.dataset.hist);
    if (e) {
      const d = openDlg("history", `${e.name} · ${e.sku}`);
      const h = await (await fetch(`/coord/history/${e.id}`)).json();
      $("#hist").innerHTML = h.length ? `<table><thead><tr><th>Group</th><th>Out</th><th>Back</th><th>Wear</th><th>Fine</th></tr></thead>` +
        h.map(x => `<tr><td>${esc(x.group)}</td><td>${fmtDt(x.issued_at || x.status)}</td><td>${fmtDt(x.returned_at || "–")}</td>
        <td>${esc(x.issue_grade || "–")} → ${esc(x.return_grade || "–")}</td><td>₹${x.fine.toFixed(2)}</td></tr>`).join("") + "</table>"
        : `<p class="empty" style="padding:1rem">This unit has not been borrowed yet.</p>`;
    }
  }
});

// Initialization
window.addEventListener("DOMContentLoaded", () => {
  let initialTab = location.hash ? location.hash.substring(1) : localStorage.getItem('activeTab');
  if (!initialTab) {
    if (ROLE === 'student') initialTab = 'tab-catalog';
    else initialTab = 'tab-dashboard';
  }
  switchTab(initialTab);

  // Live Clock
  setInterval(() => {
    const clockEl = document.getElementById('live-clock');
    if (clockEl) {
      const now = new Date();
      const days = now.getDate();
      const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      const month = months[now.getMonth()];
      const year = now.getFullYear();
      const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      clockEl.innerHTML = `<span style="font-size:0.75rem; display:block; text-align:right;">${days} ${month} ${year}</span><span style="font-size:0.85rem; font-weight:700; display:block; text-align:right;">${time}</span>`;
    }
  }, 1000);
});

let timer;
$("#q")?.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(loadCatalog, 200); });
$("#sport")?.addEventListener("change", loadCatalog);
loadCatalog();
setInterval(loadCatalog, 20000);

// ---------- PWA SERVICE WORKER & INSTALL PROMPT ----------
let deferredPrompt;
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  deferredPrompt = e;
  const btn = document.getElementById('pwa-install-btn');
  if (btn) btn.style.display = 'inline-flex';
});

async function installPWA() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
      console.log('User accepted PWA installation');
    }
    deferredPrompt = null;
  } else {
    const d = document.getElementById('dlg-install-guide');
    if (d) d.showModal();
  }
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js')
      .then(reg => console.log('PWA ServiceWorker registered:', reg.scope))
      .catch(err => console.log('ServiceWorker registration failed:', err));
  });
}

// ---------- NOTIFICATIONS SYSTEM ----------
async function loadNotifications() {
  if (!document.body.dataset.role) return;
  try {
    const res = await fetch('/api/notifications');
    if (!res.ok) return;
    const data = await res.json();
    const badge = $('#notif-badge');
    if (badge) {
      if (data.unread > 0) {
        badge.textContent = data.unread;
        badge.style.display = 'flex';
      } else {
        badge.style.display = 'none';
      }
    }
    const list = $('#notif-list');
    if (list) {
      if (data.items.length) {
        list.innerHTML = data.items.map(n => `
          <div class="notif-item ${n.read ? 'read' : 'unread'} ${n.type}">
            <div class="notif-title"><strong>${esc(n.title)}</strong> <small>${fmtDt(n.created_at)}</small></div>
            <div class="notif-body">${esc(n.message)}</div>
          </div>
        `).join('');
      } else {
        list.innerHTML = `<p class="empty" style="padding: 1rem; text-align: center;">No notifications yet.</p>`;
      }
    }
  } catch (err) {
    console.error('Failed to fetch notifications:', err);
  }
}

function toggleNotifPanel() {
  const popover = $('#notif-popover');
  if (!popover) return;
  const isHidden = popover.style.display === 'none';
  popover.style.display = isHidden ? 'block' : 'none';
  if (isHidden) markNotifsRead();
}

async function markNotifsRead() {
  try {
    await fetch('/api/notifications/read', { method: 'POST' });
    const badge = $('#notif-badge');
    if (badge) badge.style.display = 'none';
  } catch (e) {}
}

document.addEventListener('click', ev => {
  const wrapper = ev.target.closest('.notif-wrapper');
  if (!wrapper) {
    const popover = $('#notif-popover');
    if (popover) popover.style.display = 'none';
  }
});

// ---------- QR & BARCODE CAMERA SCANNER ----------
let html5QrCode = null;

async function openQRScanner() {
  const d = $('#dlg-qr-scanner');
  if (!d) return;
  d.showModal();
  
  const statusMsg = $('#qr-status-msg');
  if (statusMsg) {
    statusMsg.innerHTML = 'Point your camera at an equipment SKU barcode or loan request label.';
    statusMsg.style.color = 'var(--grey)';
  }

  if (window.Html5Qrcode) {
    try {
      if (!html5QrCode) html5QrCode = new Html5Qrcode("qr-reader");
      await html5QrCode.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 220, height: 220 } },
        onScanSuccess
      );
    } catch (err) {
      console.warn("Camera video stream restricted:", err);
      if (statusMsg) {
        statusMsg.innerHTML = '💡 <strong>Live camera stream blocked by browser security (HTTP).</strong> Click <strong>📸 Snap Photo of Barcode</strong> below to scan instantly!';
        statusMsg.style.color = 'var(--court)';
      }
    }
  }
}

async function handleQRFileScan(event) {
  const file = event.target.files[0];
  if (!file) return;
  const statusMsg = $('#qr-status-msg');
  if (statusMsg) statusMsg.textContent = 'Scanning photo...';

  try {
    if (!html5QrCode) html5QrCode = new Html5Qrcode("qr-reader");
    const decodedText = await html5QrCode.scanFile(file, true);
    closeQRScanner();
    processScanCode(decodedText);
  } catch (err) {
    console.warn("File QR scan error:", err);
    if (statusMsg) {
      statusMsg.innerHTML = '⚠️ Could not read barcode/QR from photo. Please snap closer or type SKU below.';
      statusMsg.style.color = 'var(--red)';
    }
  }
}

async function closeQRScanner() {
  if (html5QrCode) {
    try { await html5QrCode.stop(); } catch (e) {}
  }
  const d = $('#dlg-qr-scanner');
  if (d) d.close();
}

async function onScanSuccess(decodedText) {
  closeQRScanner();
  processScanCode(decodedText);
}

function handleManualScan(ev) {
  ev.preventDefault();
  const val = $('#manual-sku').value ? $('#manual-sku').value.trim() : '';
  closeQRScanner();
  processScanCode(val);
}

async function processScanCode(code) {
  if (!code) return;
  try {
    const res = await (await fetch(`/api/scan/${encodeURIComponent(code)}`)).json();
    if (res.type === 'loan') {
      const l = res.data;
      if (l.status === 'requested') {
        openDlg('issue', `Issue Request #REQ-${String(l.id).padStart(4, '0')} (${l.ename})`, `/coord/issue/${l.id}`);
      } else if (l.status === 'issued') {
        openDlg('return', `Return Loan #REQ-${String(l.id).padStart(4, '0')} (${l.ename})`, `/coord/return/${l.id}`);
      } else {
        alert(`Loan #REQ-${String(l.id).padStart(4, '0')} is currently ${l.status}.`);
      }
    } else if (res.type === 'equipment') {
      const e = res.data, active = res.active_loan;
      if (active && active.status === 'requested') {
        openDlg('issue', `Issue Request #REQ-${String(active.id).padStart(4, '0')} (${e.name})`, `/coord/issue/${active.id}`);
      } else if (active && active.status === 'issued') {
        openDlg('return', `Return Loan #REQ-${String(active.id).padStart(4, '0')} (${e.name})`, `/coord/return/${active.id}`);
      } else {
        openDlg('equip', `Edit ${e.sku}`, '/coord/equipment', 'editing');
        for (const k of ['id', 'name', 'sport', 'brand', 'rack', 'grade', 'status']) {
          const el = $(`[name=${k}]`, $('#dlg-equip'));
          if (el) el.value = e[k] === 'issued' ? 'available' : e[k];
        }
      }
    } else {
      alert(res.error || `No match found for code '${code}'`);
    }
  } catch (err) {
    alert(`Lookup failed for scanned code: ${code}`);
  }
}

// Start notification polling
loadNotifications();
setInterval(loadNotifications, 12000);
