window.VIEW_RENDERERS = {
  dashboard: typeof renderDashboard === 'function' ? renderDashboard : null,
  products: typeof renderProducts === 'function' ? renderProducts : null,
  orders: typeof renderOrders === 'function' ? renderOrders : null,
  users: typeof renderUsers === 'function' ? renderUsers : null,
  user: typeof renderUserDetail === 'function' ? renderUserDetail : null,
  charges: typeof renderCharges === 'function' ? renderCharges : null,
  panel: typeof renderPanel === 'function' ? renderPanel : null,
  logs: typeof renderLogs === 'function' ? renderLogs : null,
  loginlogs: typeof renderLoginLogs === 'function' ? renderLoginLogs : null,
  announce: typeof renderAnnounce === 'function' ? renderAnnounce : null,
  vip: typeof renderVip === 'function' ? renderVip : null
};

function bindShellEvents() {
  navItems = document.querySelectorAll('.nav-item[data-view]');
  navItems.forEach((btn) => btn.addEventListener('click', (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button) return;
    e.preventDefault();
    showView(btn.dataset.view);
  }));
  el('sidebar-overlay')?.addEventListener('click', toggleSidebar);
  document.querySelector('.menu-toggle')?.addEventListener('click', toggleSidebar);
  document.querySelector('[data-action="logout"]')?.addEventListener('click', askLogout);
  window.addEventListener('popstate', () => {
    const st = history.state || {};
    showView(st.view || viewFromPath(), { replace: true, userId: st.userId || userIdFromPath() });
  });
}

el('login-form')?.addEventListener('submit', (e) => { e.preventDefault(); login(e); });
el('login-btn')?.addEventListener('click', (e) => { e.preventDefault(); login(e); });
el('login-id')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); login(e); } });
el('login-pw')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); login(e); } });

(async function init() {
  try {
    bindShellEvents();
    const bootUser = window.__BOOT__ && window.__BOOT__.user;
    if (bootUser) {
      setAuth({ user: bootUser });
      await enterApp();
      return;
    }
    el('login-screen')?.classList.remove('hidden');
    el('app')?.classList.add('hidden');
    if (viewFromPath() !== 'dashboard') history.replaceState({ view: 'dashboard' }, '', '/');
    requestAnimationFrame(() => renderBeams('login-beams'));
  } catch (err) {
    console.error(err);
    const root = content();
    if (root) root.innerHTML = errorBlock('화면을 불러오지 못했습니다.', "showView('dashboard')");
  }
})();
