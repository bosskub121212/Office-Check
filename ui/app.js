/* ตรวจบิล — หน้าจอ (vanilla JS) เรียก Python ผ่าน window.pywebview.api หรือ /api/<name> ตอนเปิดใน dev server */
"use strict";

const api = new Proxy({}, {
  get: (_, name) => async (...args) => {
    if (window.pywebview && window.pywebview.api && window.pywebview.api[name]) {
      return window.pywebview.api[name](...args);
    }
    const r = await fetch("/api/" + name, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(args)});
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  },
});

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const svg = (d, size = 16, sw = 2) => `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const I = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  warn: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  dl: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  up: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  minus: '<path d="M5 12h14"/>',
};
const LV_ICON = {ok: I.check, red: I.warn, yellow: I.warn, blue: I.info, drop: I.minus, skip: I.minus};
const LV_TXT = {ok: "ตรงกัน", red: "ต้องแก้", yellow: "ข้อสังเกต", blue: "แจ้งให้ทราบ", drop: "ทิ้ง", skip: "ข้าม"};
const status = (lv, txt) => `<span class="st ${lv}">${svg(LV_ICON[lv] || I.info, 13, 2.4)}${esc(txt || LV_TXT[lv] || "")}</span>`;

const S = {boot: null, month: "", view: "overview", q: "", popOpen: false, upd: null, filter: "all", data: null};
const VIEWS = {
  overview: {title: () => S.boot && S.month ? `สรุปเดือน${monthLabel(S.month)}` : "ภาพรวม", month: true, search: true},
  bills: {title: () => "บิลทั้งหมด", month: false, search: true},
  billing: {title: () => `ใบวางบิล & ครบกำหนด · ${monthLabel(S.month, true)}`, month: true, search: false},
  problems: {title: () => "ต้องตรวจ", month: false, search: false},
  customers: {title: () => "ลูกค้า", month: false, search: false},
  settings: {title: () => "ตั้งค่า", month: false, search: false},
};

function monthLabel(key, short) {
  const m = (S.boot?.months || []).find((x) => x.key === key);
  return m ? (short ? m.short : m.label) : "";
}
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

/* ---------------------------------------------------------------- render */
async function go(view, opts = {}) {
  S.view = view;
  if (opts.month) S.month = opts.month;
  document.querySelectorAll(".nav").forEach((b) => b.dataset.view === view ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  const v = VIEWS[view];
  $("#pager").hidden = !v.month || !S.boot.months.length;
  $("#searchBox").hidden = !v.search;
  $("#title").textContent = v.title();
  updatePager();
  const box = $("#view");
  if (!opts.keepScroll) $("#main").scrollTop = 0;
  try {
    box.innerHTML = await RENDER[view]();
  } catch (e) {
    console.error(e);
    box.innerHTML = `<div class="panel"><div class="iss red">${svg(I.warn, 20)}<div><strong>เกิดข้อผิดพลาด</strong>${esc(e.message || e)}<br>ลองกด "ส่งรายงานปัญหา" ในหน้าตั้งค่า</div></div></div>`;
  }
  applySearch();
}

function updatePager() {
  const ms = (S.boot?.months || []).map((m) => m.key);
  const i = ms.indexOf(S.month);
  $("#monthLbl").textContent = monthLabel(S.month, true) || "-";
  $("#prevM").disabled = i <= 0;
  $("#nextM").disabled = i < 0 || i >= ms.length - 1;
}

function applySearch() {
  const q = S.q.trim().toLowerCase();
  document.querySelectorAll("[data-search]").forEach((r) => { r.hidden = q && !r.dataset.search.includes(q); });
}

function docsCell(docs) {
  return `<div class="docs">${docs.map((d) => `<span class="doc ${d.on ? "" : d.warn ? "warn" : "off"}" title="${d.on ? "มี" : d.warn ? "มี sheet แต่ไม่นับ (ดูต้องตรวจ)" : "ไม่มี"}${esc(d.t)}">${esc(d.t)}</span>`).join("")}</div>`;
}

function billRow(b, showMonth) {
  const search = [b.iv, b.customer_full, b.items, b.filename, b.tax_id].join(" ").toLowerCase();
  return `<tr class="${b.countable ? "" : "dim"}" data-search="${esc(search)}">
    <td class="nowrap"><div class="b num">${esc(b.iv)}</div><div class="m">${esc(b.date)}</div></td>
    <td class="items"><div class="b">${esc(b.customer)}</div><div class="m">${esc(b.items)}</div></td>
    <td class="r num">${b.sub}</td>
    <td class="r num m">${b.vat}</td>
    <td class="r num b">${b.total}${b.countable ? "" : '<div class="m">ไม่นับยอด</div>'}</td>
    <td>${docsCell(b.docs)}</td>
    <td class="nowrap">${status(b.level, b.level_txt)}${b.paid ? `<div class="m">รับเงิน ${esc(b.paid)}</div>` : b.bi ? `<div class="m">ครบ ${esc(b.due)}</div>` : ""}</td>
    <td class="r"><button class="ibtn rm" type="button" data-act="remove" data-id="${b.file_id}" data-name="${esc(b.filename)}" aria-label="ลบไฟล์ ${esc(b.iv)} ออกจากระบบ" title="ลบไฟล์นี้ออก (อัพผิด)">${svg(I.trash, 17)}</button></td>
  </tr>`;
}

const billHead = `<thead><tr><th scope="col">เลขที่ / วันที่</th><th scope="col">ลูกค้า · สินค้า</th><th scope="col" class="r">ก่อน VAT</th><th scope="col" class="r">VAT</th><th scope="col" class="r">รวม</th><th scope="col">เอกสาร</th><th scope="col">สถานะ</th><th scope="col"><span class="sr">ลบ</span></th></tr></thead>`;

function emptyState() {
  return `<div class="panel" style="align-items:center;text-align:center;padding:56px 24px">
    <div class="kpi lav" style="min-height:auto;width:72px;height:72px;border-radius:24px;padding:0;align-items:center;justify-content:center">${svg(I.up, 30)}</div>
    <h2>ยังไม่มีบิลในระบบ</h2>
    <p class="m" style="max-width:460px;margin:0">ลากไฟล์บิล .xlsx ของเดือนนั้นมาวางที่หน้าต่างนี้ หรือกดปุ่มด้านล่าง โปรแกรมจะอ่านใบกำกับ ใบวางบิล และใบเสร็จ แล้วตรวจให้ก่อนบันทึก</p>
    <button class="btn" type="button" data-act="upload">${svg(I.up, 18)}เลือกไฟล์บิล</button></div>`;
}

const RENDER = {
  async overview() {
    if (!S.month) { $("#subtitle").textContent = ""; return emptyState(); }
    const d = await api.summary(S.month);
    S.data = d;
    const k = d.kpi;
    $("#subtitle").textContent = `ใบกำกับภาษี ${k.count} ใบ · ใบวางบิล ${k.billed_count} ใบ${d.problem_count ? ` · ต้องตรวจ ${d.problem_count}` : ""}`;
    const kpis = `<section class="kpis" aria-label="ตัวเลขสรุป">
      <div class="kpi lav"><div class="deco hatch" style="right:-24px;bottom:-24px;width:120px;height:120px;border-radius:30px;transform:rotate(12deg)"></div>
        <span class="label">ยอดขายก่อน VAT</span><span class="value">฿${k.sub}</span><span class="sub">จากใบกำกับภาษี ${k.countable} ใบ${k.countable < k.count ? ` (ไม่นับ ${k.count - k.countable})` : ""}</span></div>
      <div class="kpi sky"><div class="deco dots" style="right:-10px;bottom:-10px;width:120px;height:90px;border-radius:24px"></div>
        <span class="label">ภาษีขาย 7%</span><span class="value">฿${k.vat}</span><span class="sub">รวมทั้งสิ้น ฿${k.total}</span></div>
      <div class="kpi pink"><div class="deco hatch" style="right:-30px;top:-30px;width:110px;height:110px;border-radius:55px"></div>
        <span class="label">วางบิลเดือนนี้</span><span class="value">${k.billed_customers} ที่</span><span class="sub">${k.billed_count} ใบ · ยอด ฿${k.billed_total}</span></div>
      <div class="kpi dark"><span class="label">รอรับเงินจากใบวางบิลเดือนนี้</span><span class="value">฿${k.unpaid_total}</span>
        <span class="sub">${k.unpaid_customers ? `ยังไม่ได้รับ ${k.unpaid_customers} บริษัท · ครบ ${esc(k.due_range)}` : k.billed_count ? "ได้รับครบแล้ว" : "ไม่มีใบวางบิล"}</span></div>
    </section>`;
    const nBilled = d.bills.filter((b) => b.bi).length, nProb = d.bills.filter((b) => ["red", "drop", "yellow"].includes(b.level)).length;
    const f = S.filter;
    const rows = d.bills.filter((b) => f === "all" || (f === "billed" && b.bi) || (f === "prob" && ["red", "drop", "yellow"].includes(b.level)));
    const table = `<section class="panel table" style="flex:2.4 1 660px" aria-labelledby="hBills">
      <div class="head"><h2 id="hBills">บิลในเดือนนี้</h2>
        <div class="chips" role="group" aria-label="กรองบิล">
          <button class="chip" type="button" data-act="filter" data-f="all" aria-pressed="${f === "all"}">ทั้งหมด ${d.bills.length}</button>
          <button class="chip" type="button" data-act="filter" data-f="billed" aria-pressed="${f === "billed"}">มีใบวางบิล ${nBilled}</button>
          <button class="chip" type="button" data-act="filter" data-f="prob" aria-pressed="${f === "prob"}">ต้องตรวจ ${nProb}</button>
          <button class="btn ghost sm" type="button" data-act="openMonth">${svg(I.folder, 16)}เปิดโฟลเดอร์เดือนนี้</button>
          <button class="btn ghost sm" type="button" data-act="export">${svg(I.dl, 16)}ส่งออก Excel</button>
        </div></div>
      <div class="tw"><table style="min-width:700px">${billHead}<tbody>${rows.map((b) => billRow(b)).join("") || `<tr><td colspan="8" class="empty">ไม่มีบิลในกลุ่มนี้</td></tr>`}</tbody></table></div>
    </section>`;
    const cust = `<section class="panel" aria-labelledby="hCust"><h2 id="hCust">ยอดขายตามลูกค้า <small>(ก่อน VAT)</small></h2>
      ${d.customers.map((c, i) => `<div class="bar-row"><div class="t"><span>${esc(c.name)}</span><span class="num b">${c.amt}</span></div>
        <div class="track"><div class="fill hatch" style="width:${c.pct.toFixed(1)}%;animation-delay:${i * 60}ms"></div></div></div>`).join("") || '<p class="m">-</p>'}</section>`;
    const probs = `<section class="panel" aria-labelledby="hProb"><h2 id="hProb">ผลตรวจเอกสาร</h2>
      ${d.problems.length ? d.problems.map((p) => issueCard(p.iv, p.level, p.issues)).join("") : `<div class="iss blue" style="background:var(--ok-bg)">${svg(I.check, 20)}<div><strong style="color:var(--ok)">ไม่พบปัญหาที่ต้องแก้</strong>เอกสารทุกใบในเดือนนี้ตรงกัน</div></div>`}
      ${d.problems.length ? `<button class="btn ghost sm" type="button" data-act="nav" data-v="problems">ดูทั้งหมดในหน้าต้องตรวจ</button>` : ""}</section>`;
    const alerts = d.alerts.length ? `<section class="alert" role="alert" aria-labelledby="hAlert" style="margin-bottom:22px">${svg(I.warn, 24)}
      <div><h2 id="hAlert">พบเลขเอกสารซ้ำกันระหว่างบิลจริงคนละบริษัท ${d.alerts.length} รายการ</h2>
      <ul>${d.alerts.map((a) => `<li><b>${esc(a.iv)}</b> · ${esc(a.message)}</li>`).join("")}</ul>
      <p class="m" style="margin:0">ยอดของทุกใบถูกนับแล้ว ตรวจกับผู้ออกบิล แก้เลขที่ให้ถูกต้อง และแจ้งสรรพากรตามขั้นตอน</p></div></section>` : "";
    return alerts + kpis + `<div class="split" style="margin-top:22px">${table}<div style="flex:1 1 280px;min-width:0;display:flex;flex-direction:column;gap:20px">${cust}${probs}</div></div>`;
  },

  async bills() {
    const d = await api.all_bills();
    $("#subtitle").textContent = `${d.bills.length} ใบ จากทุกเดือน`;
    if (!d.bills.length) return emptyState();
    return `<section class="panel table"><div class="tw"><table style="min-width:700px">${billHead}<tbody>${d.bills.map((b) => billRow(b)).join("")}</tbody></table></div></section>`;
  },

  async billing() {
    if (!S.month) return emptyState();
    const d = await api.billing(S.month);
    $("#subtitle").textContent = `ใบวางบิลที่ออก ฿${d.issued_total} · ครบกำหนดเดือนนี้ ฿${d.due_total} (ยังไม่ได้รับ ฿${d.due_unpaid})`;
    const tbl = (rows, emptyTxt) => `<div class="tw"><table style="min-width:720px"><thead><tr><th scope="col">ใบวางบิล</th><th scope="col">ลูกค้า</th><th scope="col" class="r">ยอด</th><th scope="col">ครบกำหนด</th><th scope="col">คาดว่าได้รับ</th><th scope="col">รับเงิน</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td class="nowrap"><div class="b">${esc(r.bi)}</div><div class="m">${esc(r.iv)}</div></td><td>${esc(r.customer)}</td>
        <td class="r num b">${r.amount}</td><td class="nowrap ${r.late && !r.paid ? "late" : ""}">${esc(r.due)}</td><td class="nowrap">${esc(r.expected)}</td><td>${payCtl(r)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">${emptyTxt}</td></tr>`}</tbody></table></div>`;
    return `<div class="grid2" style="grid-template-columns:1fr">
      <section class="panel table" aria-labelledby="hIss"><div class="head"><h2 id="hIss">ใบวางบิลที่ออกเดือน${esc(d.label)} <small>฿${d.issued_total}</small></h2>
        <button class="btn ghost sm" type="button" data-act="export">${svg(I.dl, 16)}ส่งออก Excel</button></div>${tbl(d.issued, "ไม่มีใบวางบิลในเดือนนี้")}</section>
      <section class="panel table" aria-labelledby="hDue"><div class="head"><h2 id="hDue">ครบกำหนดชำระในเดือน${esc(d.label)} <small>฿${d.due_total}</small></h2></div>${tbl(d.due, "ไม่มีใบวางบิลที่ครบกำหนดในเดือนนี้")}</section></div>`;
  },

  async problems() {
    const d = await api.problems();
    const n = d.rows.filter((r) => ["red", "drop"].includes(r.level)).length;
    $("#subtitle").textContent = n ? `ต้องแก้ / ทิ้ง ${n} ไฟล์ · ข้อสังเกตและแจ้งให้ทราบ ${d.rows.length - n}` : "ไม่มีไฟล์ที่ต้องแก้";
    if (!d.rows.length) return `<div class="panel"><div class="iss blue" style="background:var(--ok-bg)">${svg(I.check, 20)}<div><strong style="color:var(--ok)">ไม่พบปัญหา</strong>เอกสารทุกไฟล์ตรงกัน</div></div></div>`;
    return `<div style="display:flex;flex-direction:column;gap:14px">${d.rows.map((r) => `<article class="probcard">
      <header><div><div class="b">${esc(r.iv || "อ่านไม่ได้")} ${r.customer ? `· ${esc(r.customer)}` : ""}</div><div class="m">${esc(r.date)} · ${esc(r.filename)}</div></div>
        <div style="display:flex;gap:8px;align-items:center">${status(r.level, r.level_txt)}
        <button class="btn danger sm" type="button" data-act="remove" data-id="${r.file_id}" data-name="${esc(r.filename)}">${svg(I.trash, 15)}ลบไฟล์นี้ออก</button></div></header>
      ${r.issues.map((i) => `<div class="iss ${i.level}">${svg(LV_ICON[i.level], 18)}<div><strong>${esc(LV_TXT[i.level])} · ${esc(i.doc)}</strong>${esc(i.message)}</div></div>`).join("")}
    </article>`).join("")}</div>`;
  },

  async customers() {
    const d = await api.customers();
    $("#subtitle").textContent = `${d.rows.length} ราย`;
    if (!d.rows.length) return emptyState();
    return `<section class="panel table"><div class="tw"><table style="min-width:760px"><thead><tr><th scope="col">ลูกค้า</th><th scope="col">เลขผู้เสียภาษี</th><th scope="col" class="r">บิล</th><th scope="col" class="r">ยอดขายก่อน VAT</th><th scope="col" class="r">รอรับเงิน</th><th scope="col">จ่ายจริงเทียบเครดิต</th><th scope="col">บิลล่าสุด</th></tr></thead><tbody>
      ${d.rows.map((c) => `<tr><td><div style="display:flex;gap:10px;align-items:center"><span class="ava" style="background:${c.tint}">${esc(c.code)}</span><div><div class="b">${esc(c.name)}</div><div class="m">${esc(c.full)}</div></div></div></td>
        <td class="num">${esc(c.tax_id)}</td><td class="r">${c.count}</td><td class="r num b">${c.sub}</td><td class="r num">${c.unpaid_v ? c.unpaid : "-"}</td>
        <td>${c.delay == null ? '<span class="m">ยังไม่มีประวัติ</span>' : c.delay > 0 ? `ช้ากว่ากำหนดเฉลี่ย ${c.delay} วัน` : c.delay < 0 ? `เร็วกว่ากำหนดเฉลี่ย ${-c.delay} วัน` : "ตรงกำหนด"}</td><td class="nowrap">${esc(c.last)}</td></tr>`).join("")}</tbody></table></div></section>`;
  },

  async settings() {
    $("#subtitle").textContent = `เวอร์ชัน ${S.boot.version}`;
    const u = S.upd;
    const upd = u && u.available ? `<div class="banner"><div><div class="b">มีเวอร์ชันใหม่ ${esc(u.latest)}</div><div class="m" style="white-space:pre-line">${esc(u.notes || "")}</div></div>
      <button class="btn" type="button" data-act="doUpdate">${svg(I.dl, 18)}อัพเดทตอนนี้</button></div>`
      : `<p class="m" id="updMsg">${u ? esc(u.error || `ใช้เวอร์ชันล่าสุดแล้ว (${u.current})`) : ""}</p>`;
    return `<div class="grid2">
      <section class="panel" aria-labelledby="hUp"><h2 id="hUp">อัพเดทโปรแกรม</h2>
        <dl class="kv"><dt>เวอร์ชันที่ใช้</dt><dd>${esc(S.boot.version)}</dd></dl>${upd}
        <div><button class="btn ghost sm" type="button" data-act="checkUpdate">เช็คเวอร์ชันใหม่</button></div>
        <p class="m" style="margin:0">ก่อนอัพเดท โปรแกรมสำรองฐานข้อมูลให้อัตโนมัติ ข้อมูลบิลและการรับเงินไม่หาย</p></section>
      <section class="panel" aria-labelledby="hBug"><h2 id="hBug">ส่งรายงานปัญหา</h2>
        <p class="m" style="margin:0">รวบรวมบันทึกการทำงาน และไฟล์บิลที่อ่านไม่ได้หรือมีปัญหาแดง เป็นไฟล์ .zip ไว้ส่งให้ผู้ดูแลโปรแกรมทาง LINE หรืออีเมล</p>
        <label for="bugNote" class="b" style="font-size:14px">เล่าปัญหาสั้น ๆ (ไม่บังคับ)</label>
        <textarea id="bugNote" placeholder="เช่น อัพโหลดบิล NNCIV-260101 แล้วยอดไม่ขึ้น"></textarea>
        <div><button class="btn sm" type="button" data-act="bug">สร้างไฟล์รายงานปัญหา</button></div><div id="bugOut"></div></section>
      <section class="panel" aria-labelledby="hArc"><h2 id="hArc">โฟลเดอร์เก็บไฟล์บิล</h2>
        <p class="m" style="margin:0">ไฟล์ที่นำเข้าจะถูกคัดลอกไปไว้ที่นี่ แยกเป็น ปี / เดือน ตามวันที่บนใบกำกับ ไฟล์ต้นฉบับไม่ถูกย้าย</p>
        <dl class="kv"><dt>โฟลเดอร์</dt><dd id="arcPath">${esc(S.boot.archive_dir)}</dd></dl>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
          <button class="btn ghost sm" type="button" data-act="open" data-path="${esc(S.boot.archive_dir)}">${svg(I.folder, 16)}เปิดโฟลเดอร์</button>
          <button class="btn ghost sm" type="button" data-act="chooseArc">เปลี่ยนโฟลเดอร์</button>
          <button class="btn ghost sm" type="button" data-act="syncArc">จัดไฟล์ให้ตรงอีกครั้ง</button>
        </div><div id="arcOut"></div>
        <p class="m" style="margin:0">ไฟล์เลขซ้ำอยู่ใน <b>_ทิ้ง-เลขซ้ำ</b> ของแต่ละเดือน · ไฟล์ที่อ่านไม่ได้อยู่ใน <b>_อ่านไม่ได้</b> · ไฟล์ที่กดลบอยู่ใน <b>_ลบออกแล้ว</b></p></section>
      <section class="panel" aria-labelledby="hData"><h2 id="hData">ข้อมูล</h2>
        <dl class="kv"><dt>ไฟล์ในระบบ</dt><dd>${S.boot.file_count} ไฟล์</dd><dt>โฟลเดอร์ข้อมูล</dt><dd>${esc(S.boot.data_dir)}</dd></dl>
        <div><button class="btn ghost sm" type="button" data-act="open" data-path="${esc(S.boot.data_dir)}">${svg(I.folder, 16)}เปิดโฟลเดอร์ข้อมูล</button></div>
        <p class="m" style="margin:0">ฐานข้อมูลสำรองอยู่ในโฟลเดอร์ backups (เก็บ 10 ชุดล่าสุด)</p></section></div>`;
  },
};

function issueCard(title, level, issues) {
  return `<div class="iss ${level}">${svg(LV_ICON[level] || I.info, 20)}<div><strong>${esc(title)} · ${esc(LV_TXT[level])}</strong>
    ${issues.length === 1 ? esc(issues[0].message) : `<ul>${issues.map((i) => `<li>${esc(i.message)}</li>`).join("")}</ul>`}</div></div>`;
}

/* ---------------------------------------------------------------- payments */
function payCtl(r) {
  if (r.paid) return `<span class="payctl"><button class="paid" type="button" data-act="unpay" data-bi="${esc(r.bi)}" data-date="${esc(r.paid_iso)}" title="กดเพื่อยกเลิก">${svg(I.check, 15, 2.6)}รับแล้ว ${esc(r.paid)}</button></span>`;
  return `<span class="payctl"><button class="btn line sm" type="button" data-act="pay" data-bi="${esc(r.bi)}">ได้รับเงินแล้ว</button></span>`;
}

async function savePaid(bi, iso, msg) {
  await api.set_paid(bi, iso);
  await refreshAll();
  toast(msg, iso ? {label: "เลิกทำ", fn: () => savePaid(bi, null, `ยกเลิกการรับเงิน ${bi} แล้ว`)} : null);
}

/* ---------------------------------------------------------------- popup */
async function renderPop() {
  const d = await api.payables();
  const pop = $("#pop");
  $("#bellCount").hidden = !d.companies;
  $("#bellCount").textContent = d.companies;
  if (!d.companies) {
    pop.innerHTML = `<div class="hd"><div><span class="kicker">รอรับเงินจากใบวางบิล</span><div class="big">฿0.00</div><span class="m">ได้รับเงินครบทุกใบวางบิลแล้ว</span></div>
      <button class="ibtn" type="button" data-act="pop" aria-label="ปิด" style="background:var(--soft)">${svg(I.x, 18)}</button></div>`;
    return d;
  }
  pop.innerHTML = `<div class="hd"><div><span class="kicker">รอรับเงินจากใบวางบิล · ${d.companies} บริษัท</span><div class="big">฿${d.total}</div><span class="m">${d.count} ใบวางบิลที่ยังไม่ได้บันทึกรับเงิน</span></div>
    <button class="ibtn" type="button" data-act="pop" aria-label="ปิดการแจ้งเตือน" style="background:var(--soft)">${svg(I.x, 18)}</button></div>
    ${d.groups.map((g) => `<div class="co"><div class="row1"><span class="ava" style="background:${g.tint}" aria-hidden="true">${esc(g.code)}</span>
      <div class="name"><b title="${esc(g.full)}">${esc(g.name)}</b><span class="m">${g.rows.length} ใบ${g.delay ? ` · จ่ายช้ากว่ากำหนดเฉลี่ย ${g.delay} วัน` : ""}</span></div><span class="num b">${g.total}</span></div>
      ${g.rows.map((r) => `<div class="payline"><div class="info"><b>${esc(r.bi)} · ฿${r.amount}</b>
        <span class="${r.late ? "late" : ""}">ครบกำหนด ${esc(r.due)}${r.late ? " (เลยกำหนดแล้ว)" : ""}</span><span>คาดว่าได้รับ ${esc(r.expected)}</span></div>${payCtl(r)}</div>`).join("")}</div>`).join("")}
    <p class="m" style="margin:0">วันที่คาดว่าได้รับคิดจากเครดิตตามบิล และปรับตามรอบจ่ายจริงของแต่ละบริษัทเมื่อมีประวัติการรับเงิน</p>`;
  return d;
}

function setPop(open) {
  S.popOpen = open;
  $("#pop").hidden = !open;
  $("#bell").setAttribute("aria-expanded", String(open));
}

/* ---------------------------------------------------------------- import */
function readB64(file) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(",")[1] || "");
    fr.onerror = () => rej(fr.error);
    fr.readAsDataURL(file);
  });
}

function openImport(files) {
  const root = $("#modalRoot");
  root.innerHTML = `<div class="scrim" data-act="closeModal-bg"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="mTitle">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px"><h2 id="mTitle">นำเข้าบิล</h2>
      <button class="ibtn" type="button" data-act="closeModal" aria-label="ปิด">${svg(I.x, 18)}</button></div>
    <div id="mBody"><button class="dropbox" id="dropBox" type="button" data-act="pick" style="width:100%">${svg(I.up, 34, 1.6)}<b>ลากไฟล์บิล .xlsx มาวางที่นี่</b><span>หรือคลิกเพื่อเลือกไฟล์ (เลือกได้หลายไฟล์พร้อมกัน)</span></button></div>
    <div class="foot" id="mFoot"></div></div></div>`;
  if (files && files.length) analyze(files);
}

async function analyze(fileList) {
  const files = [...fileList].filter((f) => /\.xlsx$/i.test(f.name));
  const skipped = fileList.length - files.length;
  if (!files.length) { toast("เลือกได้เฉพาะไฟล์ .xlsx"); return; }
  if (!$("#mBody")) openImport();
  $("#mBody").innerHTML = `<div class="skeleton" style="height:90px"></div><p class="m">กำลังอ่าน ${files.length} ไฟล์…</p>`;
  $("#mFoot").innerHTML = "";
  const payload = [];
  for (const f of files) payload.push({name: f.name, b64: await readB64(f)});
  const res = await api.analyze(payload);
  S.token = res.token;
  const ok = res.results.filter((r) => r.status === "new").length;
  const bad = res.results.filter((r) => ["red", "drop"].includes(r.level)).length;
  $("#mBody").innerHTML = `<p style="margin:0">อ่านแล้ว ${res.results.length} ไฟล์${skipped ? ` (ข้ามไฟล์ที่ไม่ใช่ .xlsx ${skipped} ไฟล์)` : ""} · ${bad ? `<span class="late">ต้องแก้/ทิ้ง ${bad} ไฟล์</span> จะบันทึกไว้แต่ไม่นับยอดส่วนที่ผิด` : "ไม่พบปัญหาที่ต้องแก้"}</p>
    <div class="res">${res.results.map((r, i) => `<div class="resrow" style="animation-delay:${i * 40}ms"><div class="l1"><div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      ${r.status === "new" ? `<label class="pick"><input type="checkbox" data-idx="${i}" checked> นำเข้า</label>` : ""}<span class="b">${esc(r.iv || "-")}</span> ${r.customer ? `· ${esc(r.customer)}` : ""} ${r.total ? `· <span class="num">฿${r.total}</span>` : ""} ${r.billed ? '<span class="doc" style="margin-left:6px">วางบิล</span>' : ""}</div>
      ${status(r.level, r.headline)}</div><div class="fn">${esc(r.name)}${r.date ? ` · ${esc(r.date)}` : ""}</div>
      ${r.issues.filter((x) => x.level !== "blue" || r.level === "blue").length ? `<ul>${r.issues.map((x) => `<li>${esc(x.doc)}: ${esc(x.message)}</li>`).join("")}</ul>` : ""}</div>`).join("")}</div>`;
  $("#mFoot").innerHTML = `<button class="btn ghost" type="button" data-act="closeModal">ยกเลิก</button>
    <button class="btn" type="button" data-act="commit" id="commitBtn" ${ok ? "" : "disabled"}>${svg(I.check, 18, 2.4)}บันทึก <span id="commitN">${ok}</span> ไฟล์</button>`;
  $("#mBody").addEventListener("change", (e) => {
    if (!e.target.matches("input[data-idx]")) return;
    e.target.closest(".resrow").classList.toggle("off", !e.target.checked);
    const n = document.querySelectorAll("#mBody input[data-idx]:checked").length;
    $("#commitN").textContent = n;
    $("#commitBtn").disabled = !n;
  });
}

async function commit(btn) {
  btn.disabled = true;
  btn.innerHTML = `<span class="spin"></span>กำลังบันทึก`;
  const skip = [...document.querySelectorAll("#mBody input[data-idx]")].filter((c) => !c.checked).map((c) => Number(c.dataset.idx));
  const r = await api.commit(S.token, skip);
  closeModal(false);
  if (!r.ok) { toast(r.error); return; }
  S.boot = await api.bootstrap();
  if (r.month) S.month = r.month;
  await refreshAll("overview");
  const a = r.archive || {};
  if (a.ok === false) toast(`บันทึก ${r.saved} ไฟล์แล้ว แต่คัดลอกลงโฟลเดอร์ไม่สำเร็จ ดูหน้าตั้งค่า`);
  else toast(`บันทึก ${r.saved} ไฟล์แล้ว · คัดลอกลงโฟลเดอร์ ${a.root || ""}`, {label: "เปิดโฟลเดอร์", fn: () => api.open_month_folder(S.month)});
}

function closeModal(cancel = true) {
  if (cancel && S.token) api.cancel(S.token);
  S.token = null;
  $("#modalRoot").innerHTML = "";
}

/* ---------------------------------------------------------------- misc */
let toastTimer;
function toast(msg, action) {
  clearTimeout(toastTimer);
  $("#toastRoot").innerHTML = `<div class="toast" role="status"><span>${esc(msg)}</span>${action ? `<button type="button" id="toastAct">${esc(action.label)}</button>` : ""}</div>`;
  if (action) $("#toastAct").onclick = () => { $("#toastRoot").innerHTML = ""; action.fn(); };
  toastTimer = setTimeout(() => { $("#toastRoot").innerHTML = ""; }, action ? 6000 : 4000);
}

async function refreshCounts() {
  const [p] = await Promise.all([api.problems()]);
  const n = p.rows.filter((r) => ["red", "drop"].includes(r.level)).length;
  $("#navBadge").hidden = !n;
  $("#navBadge").textContent = n;
}

async function refreshAll(view) {
  S.boot = await api.bootstrap();
  if (!S.month || !S.boot.months.some((m) => m.key === S.month)) S.month = S.boot.current;
  await Promise.all([go(view || S.view, {keepScroll: !view}), renderPop(), refreshCounts()]);
}

async function checkUpdate(manual) {
  try {
    S.upd = await api.check_update();
  } catch (e) { S.upd = {error: String(e)}; }
  const chip = $("#updChip");
  chip.hidden = !(S.upd && S.upd.available);
  if (S.upd && S.upd.available) chip.textContent = `มีเวอร์ชันใหม่ ${S.upd.latest}`;
  if (manual) go("settings", {keepScroll: true});
}

/* ---------------------------------------------------------------- events */
document.addEventListener("click", async (e) => {
  const nav = e.target.closest(".nav");
  if (nav) { go(nav.dataset.view); return; }
  const t = e.target.closest("[data-act]");
  if (!t) return;
  const act = t.dataset.act;
  if (act === "closeModal-bg") { if (e.target === t) closeModal(); return; }
  try {
    switch (act) {
      case "upload": case "pick": $("#fileInput").click(); break;
      case "filter": S.filter = t.dataset.f; go("overview", {keepScroll: true}); break;
      case "nav": go(t.dataset.v); break;
      case "pop": setPop(false); break;
      case "pay": {
        const box = t.closest(".payctl");
        box.innerHTML = `<span class="payform"><label class="sr" for="pd-${esc(t.dataset.bi)}">วันที่ได้รับเงิน</label>
          <input type="date" id="pd-${esc(t.dataset.bi)}" value="${today()}" max="${today()}">
          <button class="btn sm" type="button" data-act="paySave" data-bi="${esc(t.dataset.bi)}">บันทึก</button>
          <button class="ibtn" type="button" data-act="payCancel" aria-label="ยกเลิก">${svg(I.x, 16)}</button></span>`;
        box.querySelector("input").focus();
        break;
      }
      case "payCancel": await refreshAll(); break;
      case "paySave": {
        const iso = t.closest(".payform").querySelector("input").value || today();
        t.disabled = true;
        await savePaid(t.dataset.bi, iso, `บันทึกว่าได้รับเงิน ${t.dataset.bi} แล้ว`);
        break;
      }
      case "unpay": {
        const bi = t.dataset.bi, d = t.dataset.date;
        await api.set_paid(bi, null);
        await refreshAll();
        toast(`ยกเลิกการรับเงิน ${bi} แล้ว`, {label: "เลิกทำ", fn: () => savePaid(bi, d, `บันทึกว่าได้รับเงิน ${bi} แล้ว`)});
        break;
      }
      case "closeModal": closeModal(); break;
      case "commit": await commit(t); break;
      case "export": {
        t.disabled = true;
        const r = await api.export(S.month);
        t.disabled = false;
        if (r.ok) toast(`บันทึกรายงานที่ ${r.path}`, {label: "เปิดไฟล์", fn: () => api.open_path(r.path)});
        break;
      }
      case "remove": {
        if (!confirm(`ลบไฟล์ "${t.dataset.name}" ออกจากระบบ?\n- ไฟล์ต้นฉบับในเครื่องไม่ถูกลบ\n- สำเนาในโฟลเดอร์ตรวจบิลจะย้ายไปไว้ที่ _ลบออกแล้ว\n- ระบบสำรองข้อมูลไว้ก่อนลบ`)) break;
        await api.remove_file(Number(t.dataset.id));
        await refreshAll();
        toast("ลบไฟล์ออกจากระบบแล้ว");
        break;
      }
      case "checkUpdate": t.disabled = true; await checkUpdate(true); break;
      case "doUpdate": {
        t.disabled = true;
        t.innerHTML = `<span class="spin"></span>กำลังดาวน์โหลด`;
        const r = await api.start_update();
        if (r.ok) toast("ดาวน์โหลดเสร็จ โปรแกรมจะปิดและเปิดใหม่เป็นเวอร์ชันล่าสุด");
        else { toast(r.error); t.disabled = false; t.textContent = "อัพเดทตอนนี้"; }
        break;
      }
      case "bug": {
        t.disabled = true;
        const r = await api.bug_report($("#bugNote").value || "");
        t.disabled = false;
        $("#bugOut").innerHTML = `<div class="iss blue">${svg(I.check, 18)}<div><strong>สร้างไฟล์แล้ว</strong>${esc(r.path)}<br>
          <button class="btn ghost sm" type="button" data-act="open" data-path="${esc(r.folder)}" style="margin-top:8px">${svg(I.folder, 16)}เปิดโฟลเดอร์</button></div></div>`;
        break;
      }
      case "open": api.open_path(t.dataset.path); break;
      case "openMonth": await api.open_month_folder(S.month); break;
      case "chooseArc": case "syncArc": {
        t.disabled = true;
        const r = act === "chooseArc" ? await api.choose_archive(null) : await api.sync_archive();
        t.disabled = false;
        if (r.cancelled) break;
        if (r.root && r.root !== S.boot.archive_dir) { S.boot.archive_dir = r.root; await go("settings", {keepScroll: true}); }
        $("#arcOut").innerHTML = r.ok
          ? `<div class="iss blue" style="background:var(--ok-bg)">${svg(I.check, 18)}<div><strong style="color:var(--ok)">เรียบร้อย</strong>คัดลอกใหม่ ${r.copied} · ย้าย ${r.moved} · อยู่ถูกที่แล้ว ${r.unchanged} ไฟล์</div></div>`
          : `<div class="iss red">${svg(I.warn, 18)}<div><strong>ไม่สำเร็จบางไฟล์</strong>${esc(r.error || (r.errors || []).join(" · "))}</div></div>`;
        break;
      }
    }
  } catch (err) {
    console.error(err);
    toast("เกิดข้อผิดพลาด: " + (err.message || err));
  }
});

$("#bell").addEventListener("click", async () => { if (!S.popOpen) await renderPop(); setPop(!S.popOpen); });
$("#uploadBtn").addEventListener("click", () => openImport());
$("#updChip").addEventListener("click", () => go("settings"));
$("#prevM").addEventListener("click", () => step(-1));
$("#nextM").addEventListener("click", () => step(1));
$("#q").addEventListener("input", (e) => { S.q = e.target.value; applySearch(); });
$("#fileInput").addEventListener("change", (e) => { const f = [...e.target.files]; e.target.value = ""; if (f.length) { if (!$("#mBody")) openImport(); analyze(f); } });
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if ($("#modalRoot").innerHTML) closeModal();
  else if (S.popOpen) { setPop(false); $("#bell").focus(); }
});

function step(dir) {
  const ms = S.boot.months.map((m) => m.key);
  const i = ms.indexOf(S.month) + dir;
  if (i >= 0 && i < ms.length) go(S.view, {month: ms[i]});
}

let dragDepth = 0;
window.addEventListener("dragenter", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) { dragDepth++; $("#dropOverlay").hidden = false; } });
window.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $("#dropOverlay").hidden = true; });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  $("#dropOverlay").hidden = true;
  const files = [...(e.dataTransfer?.files || [])];
  if (!files.length) return;
  if (!$("#mBody")) openImport();
  analyze(files);
});

/* ---------------------------------------------------------------- start */
async function start() {
  S.boot = await api.bootstrap();
  S.month = S.boot.current;
  await go("overview");
  const pay = await renderPop();
  await refreshCounts();
  if (pay.companies) setPop(true);       // แจ้งเตือนตอนเปิดโปรแกรม ถ้ามียอดรอรับ
  setTimeout(() => checkUpdate(false), 1200);
}

if (location.protocol === "file:") window.addEventListener("pywebviewready", start, {once: true});
else start();
