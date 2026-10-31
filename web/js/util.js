const $ = (sel, root = document) => root.querySelector(sel);
const el = (id) => document.getElementById(id);
const content = () => el('content');
const won = (n) => n.toLocaleString('ko-KR') + '원';
const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, (c) => ESC_MAP[c]); }
const KST = 'Asia/Seoul';

function parseWhen(value) {
  if (value == null || value === '') return null;
  if (typeof value === 'number' || /^\d+$/.test(String(value).trim())) {
    const n = Number(value);
    const d = new Date(n < 1e12 ? n * 1000 : n);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const raw = String(value).trim();
  const naive = raw.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)$/);
  if (naive) {
    const clock = naive[2].length === 5 ? `${naive[2]}:00` : naive[2];
    const d = new Date(`${naive[1]}T${clock}+09:00`);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

function kstParts(d) {
  const parts = {};
  for (const p of new Intl.DateTimeFormat('en-GB', {
    timeZone: KST, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  }).formatToParts(d)) {
    if (p.type !== 'literal') parts[p.type] = p.value;
  }
  return parts;
}

function fmtTime(value) {
  const d = parseWhen(value);
  if (!d) return '-';
  const p = kstParts(d);
  const now = kstParts(new Date());
  const yday = kstParts(new Date(Date.now() - 86400000));
  const hm = `${p.hour}:${p.minute}`;
  if (p.year === now.year && p.month === now.month && p.day === now.day) return `오늘 ${hm}`;
  if (p.year === yday.year && p.month === yday.month && p.day === yday.day) return `어제 ${hm}`;
  if (p.year === now.year) return `${Number(p.month)}월 ${Number(p.day)}일 ${hm}`;
  return `${p.year}. ${p.month}. ${p.day}. ${hm}`;
}

const TOAST_ICONS = {
  success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7fae82" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
  error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#cc7d76" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg>',
  info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7fa0b8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>'
};
function toast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.innerHTML = (TOAST_ICONS[type] || '') + '<span>' + esc(msg) + '</span>';
  el('toast-wrap').appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, 2600);
}

function loadingBlock(rows = 4) {
  return '<div style="padding:20px">' + '<div class="skeleton-row"></div>'.repeat(rows) + '</div>';
}
function spinnerBlock(text = '불러오는 중...') {
  return `<div class="state"><div class="spinner"></div><div class="state-desc">${esc(text)}</div></div>`;
}
function emptyBlock(title, desc) {
  return `<div class="state">
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
    <div class="state-title">${esc(title)}</div>
    <div class="state-desc">${esc(desc || '')}</div>
  </div>`;
}
function errorBlock(msg, retryFn) {
  return `<div class="state">
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
    <div class="state-title text-danger">문제가 발생했습니다</div>
    <div class="state-desc">${esc(msg)}</div>
    ${retryFn ? `<button class="btn btn-sm" onclick="${retryFn}">다시 시도</button>` : ''}
  </div>`;
}

function enableDragReorder(container, itemSelector, onReorder) {
  let dragEl = null;
  const getAfter = (y) => {
    const items = container.querySelectorAll(itemSelector + ':not(.dragging)');
    let closest = null, closestOffset = -Infinity;
    for (let i = 0; i < items.length; i++) {
      const box = items[i].getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closestOffset) { closestOffset = offset; closest = items[i]; }
    }
    return closest;
  };
  container.querySelectorAll(itemSelector).forEach((item) => {
    const handle = item.querySelector('.drag-handle') || item;
    handle.addEventListener('mousedown', () => { item.setAttribute('draggable', 'true'); });
    handle.addEventListener('mouseup', () => { item.removeAttribute('draggable'); });
    item.addEventListener('dragstart', (e) => { dragEl = item; item.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; });
    item.addEventListener('dragend', () => {
      item.classList.remove('dragging'); item.removeAttribute('draggable'); container.classList.remove('drag-over');
      onReorder([...container.querySelectorAll(itemSelector)].map((n) => n.dataset.id));
    });
  });
  container.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (!dragEl) return;
    container.classList.add('drag-over');
    const after = getAfter(e.clientY);
    if (after == null) container.appendChild(dragEl);
    else container.insertBefore(dragEl, after);
  });
}

const VAL_CDN = 'https://media.valorant-api.com/competitivetiers/03621f52-342b-cf4e-4f86-9350a49c6d04';
const VAL_RANKS = [
  { key: 'iron', label: '아이언', names: ['아이언', 'iron'], color: '#8B8B8B', icon: VAL_CDN + '/3/largeicon.png' },
  { key: 'bronze', label: '브론즈', names: ['브론즈', 'bronze'], color: '#CD7F32', icon: VAL_CDN + '/6/largeicon.png' },
  { key: 'silver', label: '실버', names: ['실버', 'silver'], color: '#C0C4CC', icon: VAL_CDN + '/9/largeicon.png' },
  { key: 'gold', label: '골드', names: ['골드', 'gold'], color: '#FFD166', icon: VAL_CDN + '/12/largeicon.png' },
  { key: 'platinum', label: '플래티넘', names: ['플래티넘', '플레', 'platinum', 'plat'], color: '#46D6C6', icon: VAL_CDN + '/15/largeicon.png' },
  { key: 'diamond', label: '다이아', names: ['다이아', '다이아몬드', 'diamond'], color: '#6ECBFF', icon: VAL_CDN + '/18/largeicon.png' },
  { key: 'ascendant', label: '초월', names: ['초월', '어센던트', 'ascendant'], color: '#3BE37A', icon: VAL_CDN + '/21/largeicon.png' },
  { key: 'immortal', label: '불멸', names: ['불멸', 'immortal'], color: '#E84A5F', icon: VAL_CDN + '/24/largeicon.png' },
  { key: 'radiant', label: '레디언트', names: ['레디언트', '레디', 'radiant'], color: '#F4E285', icon: VAL_CDN + '/27/largeicon.png' }
];

function vipRankMeta(name, iconUrl) {
  const url = String(iconUrl || '').trim();
  if (url) {
    const hit = VAL_RANKS.find((r) => r.icon === url);
    return { icon: url, color: hit ? hit.color : '', key: hit ? hit.key : '', label: hit ? hit.label : '' };
  }
  const n = String(name || '').replace(/\s/g, '').toLowerCase();
  return VAL_RANKS.find((r) => r.names.some((x) => n.includes(x))) || null;
}

function vipIconUrl(t) {
  if (!t) return '';
  return String(t.iconUrl || '').trim() || (vipRankMeta(t.name) || {}).icon || '';
}

function vipIconHtml(t, cls) {
  const url = vipIconUrl(t);
  if (url) return `<img class="${esc(cls || 'vip-icon')}" src="${esc(url)}" alt="" decoding="async" draggable="false" />`;
  return `<span class="${esc(cls || 'vip-icon')} vip-icon-fallback">${esc((t && t.emoji) || '★')}</span>`;
}

let currentServer = '';
