let _auth = undefined;

function readCookie(name) {
  const hit = document.cookie.split('; ').find((row) => row.startsWith(name + '='));
  return hit ? decodeURIComponent(hit.slice(name.length + 1)) : '';
}
function getAuth() {
  if (_auth !== undefined) return _auth;
  try { _auth = JSON.parse(readCookie('vm_user') || 'null'); }
  catch { _auth = null; }
  if (_auth && !_auth.user) _auth = { user: _auth, token: null };
  return _auth;
}
function setAuth(data) {
  _auth = data && data.user ? data : (data ? { user: data, token: data.token || null } : null);
}
function clearAuth() {
  _auth = null;
}

function syncRememberHint() {
  const box = el('remember-me');
  const hint = el('remember-hint');
  if (!box || !hint) return;
  hint.textContent = box.checked ? '7일 동안 로그인 상태가 유지됩니다' : '브라우저를 닫으면 로그아웃됩니다';
}

async function login(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const username = el('login-id').value.trim();
  const password = el('login-pw').value;
  const btn = el('login-btn');
  const errBox = el('login-error');

  errBox.classList.add('hidden');
  if (!username || !password) {
    el('login-error-text').textContent = '아이디와 비밀번호를 모두 입력해주세요.';
    errBox.classList.remove('hidden');
    return false;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span> 로그인 중...';

  try {
    const res = await apiLogin(username, password, true);
    if (res && res.ok && res.user) {
      setAuth({ token: res.token || null, user: res.user });
      location.replace('/');
      return false;
    }
    el('login-error-text').textContent = (res && res.error) || '아이디 또는 비밀번호가 올바르지 않습니다.';
    errBox.classList.remove('hidden');
  } catch (err) {
    el('login-error-text').textContent = '로그인 처리 중 오류가 발생했습니다.';
    errBox.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = '로그인';
  }
  return false;
}

function askLogout() {
  confirmAsk({
    title: '로그아웃',
    message: '로그아웃 하시겠습니까?',
    yes: '예',
    no: '아니요',
    danger: true,
    onYes: async () => {
      await logout();
      closeModal();
    }
  });
}

async function logout() {
  await apiLogout();
  clearAuth();
  location.replace('/');
}

async function enterApp(opts = {}) {
  el('login-screen').classList.add('hidden');
  el('app').classList.remove('hidden');
  try {
    await populateServers();
    await showView(opts.view || viewFromPath() || 'dashboard', { replace: true });
  } catch (err) {
    console.error(err);
    const root = content();
    if (root) root.innerHTML = errorBlock('화면을 불러오지 못했습니다.', "showView('dashboard')");
  }
  refreshChargeBadge().catch(() => {});
}

function renderBeams(hostId) {
  const host = el(hostId);
  if (!host || host.dataset.rendered) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const count = 10;
  const step = 336 / count;
  let strokes = '', defs = '', beams = '';
  for (let i = 0; i < count; i++) {
    const o = i * step;
    const d = `M${-380 + o} ${-189 - o}C${-380 + o} ${-189 - o} ${-312 + o} ${216 - o} ${152 + o} ${343 - o}C${616 + o} ${470 - o} ${684 + o} ${875 - o} ${684 + o} ${875 - o}`;
    strokes += `<path d="${d}" stroke="#3a4652" stroke-opacity="0.5" stroke-width="0.5"/>`;
    if (!reduce) {
      const dur = (9 + i * 0.7).toFixed(1);
      defs += `<linearGradient id="lb-${i}" gradientUnits="userSpaceOnUse" x1="0" x2="0" y1="0" y2="0">
        <animate attributeName="y1" values="0;316" dur="${dur}s" begin="${i * 0.4}s" repeatCount="indefinite"/>
        <animate attributeName="y2" values="0;310" dur="${dur}s" begin="${i * 0.4}s" repeatCount="indefinite"/>
        <stop stop-color="#5b7d94" stop-opacity="0"/><stop stop-color="#8fb4cc"/><stop offset="100%" stop-color="#eef3f6" stop-opacity="0"/>
      </linearGradient>`;
      beams += `<path class="beam" d="${d}" stroke="url(#lb-${i})" stroke-opacity="0.7" stroke-width="0.9"/>`;
    }
  }
  host.innerHTML = `<svg viewBox="0 0 696 316" fill="none" preserveAspectRatio="xMidYMid slice">${strokes}${beams}<defs>${defs}</defs></svg>`;
  host.dataset.rendered = '1';
}
