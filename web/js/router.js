let SERVERS = [];
let navItems = [];
let activeView = 'dashboard';
const mqMobile = window.matchMedia('(max-width: 760px)');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let _charts = [];

const VIEW_META = {
  dashboard: { title: '대시보드', sub: '오늘의 판매 현황을 확인하세요' },
  products: { title: '상품 관리', sub: '카테고리와 상품, 재고를 관리합니다' },
  orders: { title: '주문 내역', sub: '판매된 주문과 지급 내역을 확인합니다' },
  users: { title: '유저 / 잔액', sub: '유저 잔액과 구매 이력을 관리합니다' },
  charges: { title: '충전 관리', sub: '충전 요청 승인과 입금 계좌를 관리합니다' },
  panel: { title: '자판기 패널 설정', sub: '디스코드에 표시되는 자판기 임베드를 설정합니다' },
  logs: { title: '로그 설정', sub: '구매/충전/후기/입고 로그 채널과 문구를 설정합니다' },
  loginlogs: { title: '로그인 로그', sub: '웹패널 로그인 IP와 시각을 확인합니다' },
  announce: { title: '공지 / DM', sub: '채널 공지와 특정 유저·역할 개인메시지를 보냅니다' },
  vip: { title: 'VIP 티어', sub: '구매액으로 열리는 등급과 구매/충전 혜택을 설정합니다' },
  user: { title: '유저 상세', sub: '잔액과 구매 내역을 수정합니다' }
};

const VIEW_PATH = {
  dashboard: '/', products: '/products', orders: '/orders', users: '/users',
  charges: '/charges', panel: '/panel', logs: '/logs', loginlogs: '/login-logs', announce: '/announce', vip: '/vip'
};
const PATH_VIEW = Object.fromEntries(Object.entries(VIEW_PATH).map(([k, v]) => [v, k]));

function userIdFromPath() {
  const m = (location.pathname || '').match(/^\/users\/(\d+)/);
  return m ? m[1] : '';
}

function viewFromPath() {
  const path = (location.pathname.replace(/\/+$/, '') || '/');
  if (userIdFromPath()) return 'user';
  return PATH_VIEW[path] || 'dashboard';
}

function isMobile() { return mqMobile.matches; }
function toggleSidebar() {
  if (isMobile()) {
    const open = el('sidebar').classList.toggle('open');
    el('sidebar-overlay').classList.toggle('show', open);
  } else {
    el('app').classList.toggle('sidebar-collapsed');
  }
}
function closeMobileSidebar() {
  el('sidebar').classList.remove('open');
  el('sidebar-overlay').classList.remove('show');
}

function killCharts() {
  _charts.forEach((c) => { try { c.destroy(); } catch {} });
  _charts = [];
}

function startRouteBar() {
  const bar = el('route-bar');
  if (!bar) return;
  bar.classList.add('on');
  bar.style.width = '28%';
  requestAnimationFrame(() => { bar.style.width = '68%'; });
}
function endRouteBar() {
  const bar = el('route-bar');
  if (!bar) return;
  bar.style.width = '100%';
  setTimeout(() => { bar.classList.remove('on'); bar.style.width = '0'; }, 160);
}
function playViewEnter() {
  const root = content();
  if (!root) return;
  root.classList.remove('view-leave');
  root.style.opacity = '1';
  root.style.transform = 'none';
  if (reduceMotion || !window.anime) {
    root.classList.add('view-enter');
    return;
  }
  const items = root.querySelectorAll('.stat-card, .card, .section-head');
  if (!items.length) {
    anime({ targets: root, opacity: [0, 1], translateY: [10, 0], duration: 220, easing: 'easeOutCubic' });
    return;
  }
  anime.set(items, { opacity: 0, translateY: 12 });
  anime({ targets: items, opacity: 1, translateY: 0, delay: anime.stagger(28), duration: 280, easing: 'easeOutCubic' });
}

async function populateServers() {
  const slot = el('server-select-slot');
  SERVERS = await apiListServers();
  if (!SERVERS.length) {
    currentServer = '';
    if (slot) slot.innerHTML = '<select id="server-select" class="select" onchange="onServerChange()"><option value="">서버 DB 없음</option></select>';
    enhanceSelects(slot || document);
    return;
  }
  if (!currentServer || !SERVERS.some((s) => s.id === currentServer)) {
    currentServer = SERVERS[0].id;
  }
  if (slot) {
    slot.innerHTML = `<select id="server-select" class="select" onchange="onServerChange()">${SERVERS.map((s) => `<option value="${s.id}">${esc(s.name)} · ${s.id}</option>`).join('')}</select>`;
    const sel = slot.querySelector('select');
    if (sel) sel.value = currentServer;
  }
  enhanceSelects(slot || document);
}

function onServerChange() {
  currentServer = el('server-select').value;
  toast('서버를 전환했습니다.', 'info');
  showView(activeView);
}

async function showView(view, { replace = false, skipBar = false, userId = '' } = {}) {
  if (view === 'user' && !(userId || userIdFromPath())) view = 'users';
  const renderers = window.VIEW_RENDERERS || {};
  if (!renderers[view]) view = 'dashboard';
  const uid = userId || userIdFromPath();
  const path = view === 'user' ? `/users/${uid}` : (VIEW_PATH[view] || '/');
  if (replace) history.replaceState({ view, userId: uid }, '', path);
  else if (location.pathname !== path) history.pushState({ view, userId: uid }, '', path);
  activeView = view;
  for (let i = 0; i < navItems.length; i++) {
    const key = navItems[i].dataset.view;
    navItems[i].classList.toggle('active', key === view || (view === 'user' && key === 'users'));
  }
  const meta = VIEW_META[view];
  el('header-title').textContent = view === 'user' ? '유저 상세' : meta.title;
  el('header-sub').textContent = view === 'user' ? uid : meta.sub;
  document.title = (view === 'user' ? '유저 상세' : meta.title) + ' · 자판기 봇';
  closeMobileSidebar();
  if (!skipBar) startRouteBar();
  const root = content();
  if (root) root.classList.add('view-leave');
  killCharts();
  const render = (window.VIEW_RENDERERS || {})[view];
  if (typeof render !== 'function') throw new Error('화면을 찾을 수 없습니다.');
  await render();
  try { enhanceSelects(root || document); } catch (err) { console.error(err); }
  if (root) {
    root.dataset.view = view;
    root.classList.remove('view-leave');
    root.style.opacity = '1';
    root.style.transform = 'none';
  }
  try { playViewEnter(); } catch (err) { console.error(err); }
  endRouteBar();
}

async function refreshChargeBadge() {
  const list = await apiListChargeRequests();
  const n = list.filter((c) => c.status === 'pending').length;
  const badge = el('nav-charge-badge');
  badge.textContent = n;
  badge.style.display = n > 0 ? '' : 'none';
}
