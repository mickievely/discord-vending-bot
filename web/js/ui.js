const MODAL_CLOSE_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';

function statCard(label, value, meta, icon, colorVar) {
  return `<div class="stat-card">
    <div class="stat-top">
      <span class="stat-label">${esc(label)}</span>
      <div class="stat-icon" style="background:var(${colorVar}-soft);color:var(${colorVar})">${icon}</div>
    </div>
    <div class="stat-value">${value}</div>
    <div class="stat-meta">${esc(meta)}</div>
  </div>`;
}

function vipBadge(vip) {
  if (!vip || !vip.name) return '<span class="text-muted">-</span>';
  const hex = normalizeHex(vip.color || '#CD7F32');
  const bits = [];
  const buy = parseInt(vip.purchaseDiscountPct ?? vip.discountPct, 10) || 0;
  const charge = parseInt(vip.chargeBonusPct, 10) || 0;
  if (buy) bits.push(`구매 -${buy}%`);
  if (charge) bits.push(`충전 +${charge}%`);
  return `<span class="vip-badge" style="--vip:${hex}">${vipIconHtml(vip, 'vip-icon-sm')} ${esc(vip.name)}${bits.length ? ` <em>${esc(bits.join(' · '))}</em>` : ''}</span>`;
}

function statusBadge(status) {
  const map = {
    completed: ['badge-success', '완료'], pending: ['badge-warning', '대기'],
    refunded: ['badge-muted', '환불'], approved: ['badge-success', '승인됨'],
    rejected: ['badge-danger', '거절됨']
  };
  const [cls, label] = map[status] || ['badge-muted', status];
  return `<span class="badge ${cls}"><span class="dot"></span>${label}</span>`;
}

function channelOpts(list, sel) {
  const selected = String(sel || '');
  const rows = Array.isArray(list) ? list : [];
  const hasSelected = !selected || rows.some((c) => String(c.id) === selected);
  return `<option value="">채널 선택 안 함</option>`
    + (!hasSelected ? `<option value="${esc(selected)}" selected># ${esc(selected)} · ${esc(selected)}</option>` : '')
    + rows.map((c) => {
      const id = String(c.id || '');
      return `<option value="${esc(id)}" ${id === selected ? 'selected' : ''}># ${esc(c.name)} · ${esc(id)}</option>`;
    }).join('');
}

function roleOpts(list, sel) {
  const selected = String(sel || '');
  const rows = Array.isArray(list) ? list : [];
  const hasSelected = !selected || rows.some((r) => String(r.id) === selected);
  return `<option value="">역할 선택 안 함</option>`
    + (!hasSelected ? `<option value="${esc(selected)}" selected>@ ${esc(selected)} · ${esc(selected)}</option>` : '')
    + rows.map((r) => {
      const id = String(r.id || '');
      return `<option value="${esc(id)}" ${id === selected ? 'selected' : ''}>@ ${esc(r.name)} · ${esc(id)}</option>`;
    }).join('');
}

const COLOR_PRESETS = ['#5865F2', '#A449FF', '#EB459E', '#ED4245', '#FEE75C', '#57F287', '#57C2F2', '#7FA0B8', '#F4F3F1', '#232428'];

function normalizeHex(value, fallback = '#5865F2') {
  let raw = String(value || '').trim();
  if (!raw.startsWith('#')) raw = '#' + raw;
  if (/^#[0-9a-fA-F]{3}$/.test(raw)) raw = '#' + raw[1] + raw[1] + raw[2] + raw[2] + raw[3] + raw[3];
  return /^#[0-9a-fA-F]{6}$/.test(raw) ? raw.toUpperCase() : fallback;
}

function hexToRgb(hex) {
  const h = normalizeHex(hex).slice(1);
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function rgbToHex(r, g, b) {
  const to = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
  return ('#' + to(r) + to(g) + to(b)).toUpperCase();
}

function rgbToHsv(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s: max === 0 ? 0 : d / max, v: max };
}

function hsvToRgb(h, s, v) {
  const c = v * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = v - c;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; }
  else if (h < 300) { r = x; b = c; }
  else { r = c; b = x; }
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

function hsvToHex(h, s, v) {
  return rgbToHex(...hsvToRgb(h, s, v));
}

function colorField(id, value, oninput = 'updateBuyPreviews()') {
  const hex = normalizeHex(value || '#5865F2');
  return `<div class="color-field" data-color-for="${esc(id)}" data-oninput="${esc(oninput)}">
    <button type="button" class="color-swatch" data-open-color="${esc(id)}" aria-label="색상 선택" style="--swatch:${hex}">
      <span class="color-swatch-fill"></span>
    </button>
    <label class="color-hex">
      <span>#</span>
      <input class="input mono" id="${id}-text" value="${hex.slice(1)}" maxlength="6" spellcheck="false" autocomplete="off" />
    </label>
    <input type="hidden" id="${id}" value="${hex}" />
  </div>`;
}

let _colorPick = { id: '', h: 250, s: 0.7, v: 1 };

function ensureColorPopover() {
  if (el('color-popover')) return el('color-popover');
  const box = document.createElement('div');
  box.id = 'color-popover';
  box.className = 'color-popover hidden';
  box.innerHTML = `
    <div class="color-sv" id="color-sv">
      <div class="color-sv-knob" id="color-sv-knob"></div>
    </div>
    <div class="color-hue" id="color-hue">
      <div class="color-hue-knob" id="color-hue-knob"></div>
    </div>
    <div class="color-presets">${COLOR_PRESETS.map((c) => `<button type="button" class="color-chip" data-hex="${c}" style="--chip:${c}" aria-label="${c}"></button>`).join('')}</div>
    <div class="color-popover-foot">
      <span class="color-preview" id="color-preview"></span>
      <span class="mono" id="color-hex-live">#5865F2</span>
    </div>`;
  document.body.appendChild(box);
  bindColorPad(el('color-sv'), (x, y) => {
    _colorPick.s = x;
    _colorPick.v = 1 - y;
    applyColorPick();
  });
  bindColorPad(el('color-hue'), (x) => {
    _colorPick.h = x * 360;
    applyColorPick();
  });
  box.addEventListener('click', (e) => {
    const chip = e.target.closest('.color-chip');
    if (!chip) return;
    const hsv = rgbToHsv(...hexToRgb(chip.dataset.hex));
    _colorPick.h = hsv.h; _colorPick.s = hsv.s; _colorPick.v = hsv.v;
    applyColorPick();
  });
  return box;
}

function bindColorPad(node, onMove) {
  const read = (ev) => {
    const r = node.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height));
    onMove(x, y);
  };
  const start = (ev) => {
    ev.preventDefault();
    node.setPointerCapture(ev.pointerId);
    read(ev);
  };
  node.addEventListener('pointerdown', start);
  node.addEventListener('pointermove', (ev) => { if (ev.buttons) read(ev); });
}

function applyColorPick() {
  const hex = hsvToHex(_colorPick.h, _colorPick.s, _colorPick.v);
  const hueHex = hsvToHex(_colorPick.h, 1, 1);
  const sv = el('color-sv');
  const knob = el('color-sv-knob');
  const hueKnob = el('color-hue-knob');
  if (sv) sv.style.setProperty('--hue', hueHex);
  if (knob) {
    knob.style.left = (_colorPick.s * 100) + '%';
    knob.style.top = ((1 - _colorPick.v) * 100) + '%';
    knob.style.background = hex;
  }
  if (hueKnob) hueKnob.style.left = ((_colorPick.h / 360) * 100) + '%';
  if (el('color-preview')) el('color-preview').style.background = hex;
  if (el('color-hex-live')) el('color-hex-live').textContent = hex;
  if (_colorPick.id) setColorValue(_colorPick.id, hex);
}

function setColorValue(id, hex, fromText) {
  hex = normalizeHex(hex);
  const hidden = el(id);
  const text = el(id + '-text');
  if (hidden) hidden.value = hex;
  if (text && !fromText) text.value = hex.slice(1);
  const field = document.querySelector(`[data-color-for="${id}"]`);
  const swatch = field?.querySelector('.color-swatch');
  if (swatch) swatch.style.setProperty('--swatch', hex);
  const fn = field?.getAttribute('data-oninput');
  if (fn) {
    try { new Function(fn)(); } catch {}
  }
}

function openColorPicker(id, anchor) {
  const pop = ensureColorPopover();
  _colorPick.id = id;
  const hex = normalizeHex(el(id)?.value || '#5865F2');
  const hsv = rgbToHsv(...hexToRgb(hex));
  _colorPick.h = hsv.h; _colorPick.s = hsv.s; _colorPick.v = hsv.v;
  applyColorPick();
  pop.classList.remove('hidden');
  const rect = anchor.getBoundingClientRect();
  const top = rect.bottom + 10;
  const left = Math.min(rect.left, window.innerWidth - 276);
  pop.style.top = Math.min(top, window.innerHeight - 320) + 'px';
  pop.style.left = Math.max(12, left) + 'px';
}

function closeColorPicker() {
  el('color-popover')?.classList.add('hidden');
  _colorPick.id = '';
}

document.addEventListener('click', (e) => {
  const openBtn = e.target.closest('[data-open-color]');
  if (openBtn) {
    e.preventDefault();
    e.stopPropagation();
    const id = openBtn.dataset.openColor;
    if (_colorPick.id === id && !el('color-popover')?.classList.contains('hidden')) closeColorPicker();
    else openColorPicker(id, openBtn);
    return;
  }
  if (!e.target.closest('#color-popover')) closeColorPicker();
});

document.addEventListener('input', (e) => {
  const text = e.target;
  if (!text.id || !text.id.endsWith('-text')) return;
  const field = text.closest('.color-field');
  if (!field) return;
  const id = field.dataset.colorFor;
  const hex = normalizeHex(text.value, el(id)?.value || '#5865F2');
  if (text.value.length < 6 && !/^#?[0-9a-fA-F]{6}$/.test(text.value)) return;
  setColorValue(id, hex, true);
  if (_colorPick.id === id) {
    const hsv = rgbToHsv(...hexToRgb(hex));
    _colorPick.h = hsv.h; _colorPick.s = hsv.s; _colorPick.v = hsv.v;
    applyColorPick();
  }
});

function switchRow(id, label, checked) {
  return `<label class="switch-row">
    <span class="switch-copy">${esc(label)}</span>
    <input type="checkbox" id="${id}" ${checked ? 'checked' : ''} />
    <span class="switch" aria-hidden="true"><span class="switch-knob"></span></span>
  </label>`;
}

function pickSwitch({ value, cls, label, meta, extra = '' }) {
  return `<label class="pick-item" ${extra}>
    <span class="pick-copy">${esc(label)}</span>
    ${meta ? `<span class="mono">${esc(meta)}</span>` : ''}
    <input type="checkbox" class="${esc(cls || '')}" value="${esc(value)}" />
    <span class="switch" aria-hidden="true"><span class="switch-knob"></span></span>
  </label>`;
}

function copyText(text, btn) {
  navigator.clipboard?.writeText(text).then(() => {
    toast('재고 내용을 복사했습니다.');
    if (btn) { btn.classList.add('copied'); setTimeout(() => btn.classList.remove('copied'), 900); }
  }).catch(() => toast('복사에 실패했습니다.', 'error'));
}

function openModal({ title, sub, body, confirmText = '확인', cancelText = '취소', onConfirm, hideConfirm = false, danger = false, compact = false }) {
  const root = el('modal-root');
  root.innerHTML = `<div class="overlay">
    <div class="modal${compact ? ' modal-confirm' : ''}" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div><h3 id="modal-title">${esc(title)}</h3><div class="m-sub" id="modal-sub" ${sub ? '' : 'style="display:none"'}>${sub || ''}</div></div>
        <button type="button" class="modal-close" onclick="closeModal()" aria-label="닫기">${MODAL_CLOSE_ICON}</button>
      </div>
      <div class="modal-body" id="modal-body">${body}</div>
      <div class="modal-footer">
        <button type="button" class="btn" onclick="closeModal()">${hideConfirm ? '닫기' : esc(cancelText)}</button>
        ${hideConfirm ? '' : `<button type="button" class="btn ${danger ? 'btn-danger-solid' : 'btn-primary'}" id="modal-confirm">${esc(confirmText)}</button>`}
      </div>
    </div>
  </div>`;
  if (hideConfirm) return;
  const btn = el('modal-confirm');
  btn.onclick = async () => {
    btn.disabled = true; const orig = btn.textContent; btn.textContent = '처리 중...';
    try { const r = await onConfirm(); if (r === false) { btn.disabled = false; btn.textContent = orig; } }
    catch (e) { toast('처리 중 오류가 발생했습니다.', 'error'); btn.disabled = false; btn.textContent = orig; }
  };
}

function setModalTitle(title, sub) {
  const t = el('modal-title'), s = el('modal-sub');
  if (t) t.textContent = title;
  if (s) { s.textContent = sub || ''; s.style.display = sub ? '' : 'none'; }
}

function closeModal() { el('modal-root').innerHTML = ''; }

function confirmDialog(title, message, onConfirm) {
  openModal({
    title,
    body: `<p class="confirm-msg">${esc(message)}</p>`,
    confirmText: '삭제',
    cancelText: '취소',
    danger: true,
    compact: true,
    onConfirm
  });
}

function confirmAsk({ title, message, yes = '예', no = '아니요', danger = false, onYes }) {
  openModal({
    title,
    body: `<p class="confirm-msg">${esc(message)}</p>`,
    confirmText: yes,
    cancelText: no,
    danger,
    compact: true,
    onConfirm: onYes
  });
}

function openDrawer({ title, body }) {
  el('modal-root').innerHTML = `<div class="overlay drawer-overlay">
    <div class="drawer" role="dialog" aria-modal="true">
      <div class="modal-header">
        <h3>${esc(title)}</h3>
        <button type="button" class="modal-close" onclick="closeModal()" aria-label="닫기">${MODAL_CLOSE_ICON}</button>
      </div>
      <div class="modal-body" id="drawer-body">${body}</div>
    </div>
  </div>`;
}

function closeMenuSelects(except) {
  document.querySelectorAll('.menu-select.open').forEach((box) => {
    if (box !== except) box.classList.remove('open');
  });
}

function placeMenuSelect(box) {
  const btn = box.querySelector('.menu-select-btn');
  const pop = box.querySelector('.menu-select-pop');
  if (!btn || !pop) return;
  const r = btn.getBoundingClientRect();
  pop.style.minWidth = Math.max(r.width, 168) + 'px';
  pop.style.left = Math.min(r.left, window.innerWidth - 200) + 'px';
  const below = window.innerHeight - r.bottom;
  if (below < 240 && r.top > below) {
    pop.style.top = 'auto';
    pop.style.bottom = (window.innerHeight - r.top + 6) + 'px';
  } else {
    pop.style.bottom = 'auto';
    pop.style.top = (r.bottom + 6) + 'px';
  }
}

function setMenuSelectValue(box, value, fire) {
  const hidden = box.querySelector('input[type="hidden"]');
  const label = box.querySelector('.menu-select-label');
  const opt = box.querySelector(`.menu-select-opt[data-value="${CSS.escape(String(value))}"]`);
  if (hidden) hidden.value = value;
  if (label) label.textContent = opt ? opt.textContent : (value || '선택');
  box.querySelectorAll('.menu-select-opt').forEach((n) => n.classList.toggle('on', n.dataset.value === String(value)));
  box.classList.remove('open');
  if (!fire) return;
  const raw = box.dataset.onchange || '';
  if (raw) {
    try { new Function(raw).call({ value: hidden ? hidden.value : value }); } catch {}
  }
  hidden?.dispatchEvent(new Event('change', { bubbles: true }));
}

function enhanceSelects(root = document) {
  root.querySelectorAll('select.select, #server-select').forEach((sel) => {
    if (sel.dataset.enhanced === '1' || sel.closest('.menu-select')) return;
    const options = [...sel.options].map((o) => ({ value: o.value, label: o.textContent }));
    const box = document.createElement('div');
    const searchable = options.length > 8;
    box.className = 'menu-select' + (sel.id === 'server-select' ? ' menu-select-server' : '');
    box.dataset.onchange = sel.getAttribute('onchange') || '';
    box.innerHTML = `
      <input type="hidden" id="${esc(sel.id || '')}" value="${esc(sel.value)}" />
      <button type="button" class="menu-select-btn" aria-haspopup="listbox">
        <span class="menu-select-label">${esc((sel.selectedOptions[0] && sel.selectedOptions[0].textContent) || '선택')}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
      </button>
      <div class="menu-select-pop">
        ${searchable ? '<input class="menu-select-q" type="search" placeholder="검색..." />' : ''}
        <div class="menu-select-list">${options.map((o) => `<button type="button" class="menu-select-opt${String(o.value) === String(sel.value) ? ' on' : ''}" data-value="${esc(o.value)}" data-label="${esc(o.label.toLowerCase())}">${esc(o.label)}</button>`).join('')}</div>
      </div>`;
    sel.dataset.enhanced = '1';
    sel.replaceWith(box);
  });
}

document.addEventListener('click', (e) => {
  const opt = e.target.closest('.menu-select-opt');
  if (opt) {
    e.preventDefault();
    setMenuSelectValue(opt.closest('.menu-select'), opt.dataset.value, true);
    return;
  }
  const btn = e.target.closest('.menu-select-btn');
  if (btn) {
    e.preventDefault();
    const box = btn.closest('.menu-select');
    const open = !box.classList.contains('open');
    closeMenuSelects(box);
    box.classList.toggle('open', open);
    if (open) {
      placeMenuSelect(box);
      box.querySelector('.menu-select-q')?.focus();
    }
    return;
  }
  if (!e.target.closest('.menu-select')) closeMenuSelects();
});

document.addEventListener('input', (e) => {
  const q = e.target.closest('.menu-select-q');
  if (!q) return;
  const needle = q.value.trim().toLowerCase();
  q.closest('.menu-select').querySelectorAll('.menu-select-opt').forEach((opt) => {
    opt.hidden = !!(needle && !opt.dataset.label.includes(needle));
  });
});
