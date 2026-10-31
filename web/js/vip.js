let _vipTiers = [];

function vipHex(t) {
  return normalizeHex(t?.color || (vipRankMeta(t?.name, t?.iconUrl) || {}).color || '#CD7F32');
}

function nInt(n) { return parseInt(n, 10) || 0; }

function vipSorted() {
  return [..._vipTiers].sort((a, b) =>
    (nInt(b.unlockSpent) - nInt(a.unlockSpent)) ||
    (nInt(b.position) - nInt(a.position)) ||
    (nInt(b.id) - nInt(a.id))
  );
}

async function renderVip() {
  content().innerHTML = spinnerBlock('VIP 티어를 불러오는 중...');
  try {
    _vipTiers = await apiListVipTiers();
    content().innerHTML = `
      <div class="card">
        <div class="card-header">
          <div class="card-title">VIP 티어</div>
          <button class="btn btn-sm btn-primary" onclick="openVipModal()">티어 추가</button>
        </div>
        <div class="card-pad">
          <p class="card-sub" style="margin:0 0 16px">등급마다 구매 할인과 충전 보너스를 따로 정할 수 있습니다. 총 구매액이 개방 금액에 도달하면 자동으로 열립니다.</p>
          ${_vipTiers.length ? `<div class="vip-ladder">${vipSorted().map(vipCard).join('')}</div>` : emptyBlock('티어가 없습니다', '티어 추가로 등급을 만드세요.')}
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><div class="card-title">유저에게 수동 부여</div></div>
        <div class="card-pad">
          <div class="settings-grid">
            <div class="field"><label>디스코드 유저 ID</label><input class="input mono" id="vip-user-id" placeholder="1438856..." /></div>
            <div class="field"><label>티어</label><select class="select" id="vip-grant-tier">${vipTierOpts('')}</select></div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" onclick="grantVip()">부여</button>
            <button class="btn btn-ghost" onclick="clearVip()">해제</button>
          </div>
        </div>
      </div>`;
  } catch {
    content().innerHTML = errorBlock('VIP 티어를 불러오지 못했습니다.', "renderVip()");
  }
}

function vipCard(t) {
  const hex = vipHex(t);
  const buy = nInt(t.purchaseDiscountPct ?? t.discountPct);
  const charge = nInt(t.chargeBonusPct);
  const unlock = nInt(t.unlockSpent);
  return `<div class="vip-row" style="--vip:${hex}">
    ${vipIconHtml(t, 'vip-icon')}
    <div class="vip-row-main">
      <div class="vip-name">${esc(t.name)}</div>
      <div class="vip-unlock">${unlock ? won(unlock) + ' 구매 시 개방' : '수동 부여만'}</div>
    </div>
    <div class="vip-row-perks">
      <span class="vip-chip vip-chip-buy">${buy ? '구매 -' + buy + '%' : '구매 할인 없음'}</span>
      <span class="vip-chip vip-chip-charge">${charge ? '충전 +' + charge + '%' : '충전 보너스 없음'}</span>
    </div>
    <div class="vip-row-actions">
      <button class="btn btn-sm" onclick="openVipModal('${esc(t.id)}')">수정</button>
      <button class="btn btn-sm btn-danger" onclick="deleteVipTier('${esc(t.id)}')">삭제</button>
    </div>
  </div>`;
}

function vipTierOpts(sel) {
  const selected = String(sel || '');
  return `<option value="">티어 없음</option>` + _vipTiers.map((t) =>
    `<option value="${esc(t.id)}" ${String(t.id) === selected ? 'selected' : ''}>${esc(t.name)}</option>`
  ).join('');
}

function vipRankPicks(t) {
  const cur = (vipRankMeta(t?.name, t?.iconUrl) || {}).key || '';
  return `<div class="vip-rank-picks" id="vip-rank-picks">
    ${VAL_RANKS.map((r) => `<button type="button" class="vip-rank-pick${r.key === cur ? ' on' : ''}" data-key="${esc(r.key)}" style="--vip:${r.color}" onclick="vipPickRank('${esc(r.key)}')">
      <img src="${esc(r.icon)}" alt="" decoding="async" draggable="false" />
      <span>${esc(r.label)}</span>
    </button>`).join('')}
  </div>`;
}

function vipPickRank(key) {
  const r = VAL_RANKS.find((x) => x.key === key);
  if (!r) return;
  const nameEl = el('vip-name');
  const cur = (nameEl?.value || '').trim();
  if (!cur || VAL_RANKS.some((x) => x.label === cur)) nameEl.value = r.label;
  if (el('vip-icon')) el('vip-icon').value = r.icon;
  if (el('vip-icon-prev')) el('vip-icon-prev').src = r.icon;
  setColorValue('vip-color', r.color);
  document.querySelectorAll('.vip-rank-pick').forEach((b) => b.classList.toggle('on', b.dataset.key === key));
}

function vipSyncIconPrev() {
  const url = (el('vip-icon')?.value || '').trim();
  const img = el('vip-icon-prev');
  if (!img) return;
  if (url) { img.src = url; img.classList.remove('hidden'); }
  else img.classList.add('hidden');
}

function openVipModal(id) {
  const t = id ? _vipTiers.find((x) => String(x.id) === String(id)) : null;
  const icon = t ? vipIconUrl(t) : '';
  openModal({
    title: t ? '티어 수정' : '티어 추가',
    body: `
      <div class="field"><label>발로란트 랭크 아이콘</label>${vipRankPicks(t)}<div class="hint">아이콘을 누르면 이름·색상·CDN 이미지가 채워집니다. 이름은 나중에 바꿔도 됩니다.</div></div>
      <div class="field"><label>등급 이름</label><input class="input" id="vip-name" value="${esc(t ? t.name : '')}" placeholder="골드" /></div>
      <div class="field"><label>아이콘 URL</label>
        <div class="vip-icon-edit">
          ${icon ? `<img id="vip-icon-prev" class="vip-icon-sm" src="${esc(icon)}" alt="" />` : '<img id="vip-icon-prev" class="vip-icon-sm hidden" alt="" />'}
          <input class="input" id="vip-icon" value="${esc(icon)}" placeholder="https://media.valorant-api.com/..." oninput="vipSyncIconPrev()" />
        </div>
      </div>
      <div class="settings-grid">
        <div class="field"><label>구매 할인율 (%)</label><input class="input" type="number" min="0" max="100" id="vip-buy" value="${t ? nInt(t.purchaseDiscountPct ?? t.discountPct) : 10}" /><div class="hint">상품 살 때 가격에서 깎습니다. 0이면 구매 할인 없음.</div></div>
        <div class="field"><label>충전 보너스 (%)</label><input class="input" type="number" min="0" max="100" id="vip-charge" value="${t ? nInt(t.chargeBonusPct) : 0}" /><div class="hint">충전할 때 잔액에 추가로 붙습니다. 0이면 충전 보너스 없음.</div></div>
      </div>
      <div class="field"><label>총 구매액 (이 금액부터 자동 개방, 0이면 수동만)</label><input class="input" type="number" min="0" id="vip-unlock" value="${t ? nInt(t.unlockSpent) : 100000}" placeholder="100000" /></div>
      <div class="field"><label>색상</label>${colorField('vip-color', t ? vipHex(t) : '#FFD166', '')}</div>`,
    confirmText: '저장',
    onConfirm: async () => {
      const name = el('vip-name')?.value.trim();
      const buy = parseInt(el('vip-buy')?.value, 10);
      const charge = parseInt(el('vip-charge')?.value, 10);
      const unlock = parseInt(el('vip-unlock')?.value, 10);
      const iconUrl = (el('vip-icon')?.value || '').trim();
      if (!name) { toast('이름을 입력하세요.', 'error'); return false; }
      if ([buy, charge, unlock].some((n) => isNaN(n)) || buy < 0 || buy > 100 || charge < 0 || charge > 100 || unlock < 0) {
        toast('할인/보너스는 0~100, 개방 금액은 0 이상입니다.', 'error');
        return false;
      }
      if (iconUrl && !iconUrl.startsWith('https://')) {
        toast('아이콘은 https:// URL만 사용할 수 있습니다.', 'error');
        return false;
      }
      const data = {
        name,
        iconUrl,
        color: el('vip-color')?.value || '#FFD166',
        purchaseDiscountPct: buy,
        chargeBonusPct: charge,
        unlockSpent: unlock
      };
      if (t) await apiUpdateVipTier(t.id, data);
      else await apiCreateVipTier(data);
      toast('티어를 저장했습니다.');
      closeModal();
      renderVip();
    }
  });
}

async function deleteVipTier(id) {
  confirmDialog('티어 삭제', '이 티어를 삭제하면 부여된 유저의 VIP도 해제됩니다.', async () => {
    await apiDeleteVipTier(id);
    toast('티어를 삭제했습니다.');
    closeModal();
    renderVip();
  });
}

async function grantVip() {
  const id = el('vip-user-id')?.value.trim();
  const tid = el('vip-grant-tier')?.value || '';
  if (!/^\d+$/.test(id)) { toast('디스코드 유저 ID를 입력하세요.', 'error'); return; }
  if (!tid) { toast('부여할 티어를 선택하세요.', 'error'); return; }
  try {
    await apiSetUserField(id, 'vipTierId', tid);
    toast('VIP 티어를 수동 부여했습니다.');
  } catch { toast('부여에 실패했습니다.', 'error'); }
}

async function clearVip() {
  const id = el('vip-user-id')?.value.trim();
  if (!/^\d+$/.test(id)) { toast('디스코드 유저 ID를 입력하세요.', 'error'); return; }
  try {
    await apiSetUserField(id, 'vipTierId', '');
    toast('VIP 티어를 해제했습니다. 구매액 조건이 되면 다시 자동 개방됩니다.');
  } catch { toast('해제에 실패했습니다.', 'error'); }
}
