let _products = [], _categories = [], _productRoles = [], _purchaseRole = '', _productSearch = '';

async function renderProducts() {
  content().innerHTML = spinnerBlock('상품 정보를 불러오는 중...');
  try {
    const [categories, products, roles, purchaseRole] = await Promise.all([apiListCategories(), apiListProducts(), apiListRoles(), apiGetPurchaseRole()]);
    _categories = categories;
    _products = products;
    _productRoles = roles;
    _purchaseRole = purchaseRole.roleId || '';
    content().innerHTML = `
      <div class="card" style="margin-bottom:20px">
        <div class="card-header">
          <div><div class="card-title">구매 시 역할 지급</div><div class="card-sub">없음을 선택하면 구매 후 역할을 지급하지 않습니다</div></div>
        </div>
        <div class="card-pad">
          <div class="field" style="margin:0"><label>지급 역할</label><select class="select" id="purchase-role" onchange="savePurchaseRole(this.value)">${productRoleOpts(_productRoles, _purchaseRole)}</select></div>
        </div>
      </div>

      <div class="card" style="margin-bottom:20px">
        <div class="card-header">
          <div><div class="card-title">카테고리</div><div class="card-sub">왼쪽 손잡이를 끌어 순서를 바꿀 수 있습니다</div></div>
          <button class="btn btn-sm btn-primary" onclick="openCategoryModal()">+ 추가</button>
        </div>
        <div class="card-pad" id="category-list"></div>
      </div>

      <div class="section-head">
        <div><h2 style="font-size:15px">상품 목록</h2></div>
        <button class="btn btn-primary" onclick="openProductModal()">+ 상품 추가</button>
      </div>
      <div class="toolbar">
        <div class="search-box">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4-4"/></svg>
          <input class="input" type="text" placeholder="상품명 검색..." value="${esc(_productSearch)}" oninput="onProductSearch(this.value)" />
        </div>
      </div>
      <div id="product-table"></div>`;
    renderCategoryList();
    renderProductTable();
  } catch (err) {
    content().innerHTML = errorBlock('상품 정보를 불러오지 못했습니다.', "renderProducts()");
  }
}

const DRAG_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="18" r="1"/></svg>';

function renderCategoryList() {
  const wrap = el('category-list');
  if (!_categories.length) { wrap.innerHTML = emptyBlock('카테고리가 없습니다', '새 카테고리를 추가하세요'); return; }
  wrap.innerHTML = `<div class="cat-list" id="cat-drag-list">` + _categories.map((c) => `
    <div class="cat-row" data-id="${c.id}">
      <span class="drag-handle" title="드래그하여 순서 변경" aria-label="순서 변경 손잡이">${DRAG_ICON}</span>
      <div><div class="cat-name">${esc(c.name)}</div><div class="cat-count">${_products.filter((p) => p.categoryId === c.id).length}개 상품</div></div>
      <div class="cat-actions">
        <button class="btn btn-sm btn-ghost" onclick="openCategoryModal('${c.id}')">수정</button>
        <button class="btn btn-sm btn-ghost text-danger" onclick="deleteCategory('${c.id}')">삭제</button>
      </div>
    </div>`).join('') + `</div>`;
  enableDragReorder(el('cat-drag-list'), '.cat-row', async (ids) => {
    _categories.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
    await apiReorderCategories(ids);
    toast('카테고리 순서를 변경했습니다.', 'info');
  });
}

function onProductSearch(v) { _productSearch = v; renderProductTable(); }

function productRoleOpts(list, sel) {
  const selected = String(sel || '');
  const rows = Array.isArray(list) ? list : [];
  const hasSelected = !selected || rows.some((r) => String(r.id) === selected);
  return `<option value="">없음</option>`
    + (!hasSelected ? `<option value="${esc(selected)}" selected>@ ${esc(selected)} · ${esc(selected)}</option>` : '')
    + rows.map((r) => {
      const id = String(r.id || '');
      return `<option value="${esc(id)}" ${id === selected ? 'selected' : ''}>@ ${esc(r.name)} · ${esc(id)}</option>`;
    }).join('');
}

async function savePurchaseRole(roleId) {
  try {
    await apiSavePurchaseRole(roleId);
    _purchaseRole = roleId || '';
    toast('구매 시 지급 역할을 저장했습니다.');
  } catch (err) {
    toast('역할 설정을 저장하지 못했습니다.', 'error');
  }
}

function renderProductTable() {
  const q = _productSearch.trim().toLowerCase();
  const canReorder = !q;
  const rows = _products.filter((p) => !q || p.name.toLowerCase().includes(q));
  const catName = (id) => (_categories.find((c) => c.id === id) || {}).name || '-';
  if (!rows.length) {
    el('product-table').innerHTML = emptyBlock('상품이 없습니다', q ? '검색 결과가 없습니다' : '새 상품을 추가하세요');
    return;
  }
  el('product-table').innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th style="width:36px"></th><th>상품명</th><th>카테고리</th><th>가격</th><th>재고 수량</th><th>관리</th></tr></thead>
    <tbody id="product-tbody">${rows.map((p) => `<tr data-id="${p.id}">
      <td class="drag-cell">${canReorder ? `<span class="drag-handle" title="드래그하여 순서 변경" aria-label="순서 변경 손잡이">${DRAG_ICON}</span>` : ''}</td>
      <td data-label="상품명"><div style="font-weight:500">${esc(p.name)}</div></td>
      <td data-label="카테고리"><span class="badge badge-muted">${esc(catName(p.categoryId))}</span></td>
      <td data-label="가격" class="amount">${won(p.price)}</td>
      <td data-label="재고 수량"><span class="badge ${p.stock === 0 ? 'badge-danger' : p.stock <= 5 ? 'badge-warning' : 'badge-muted'}">${p.stock}개</span></td>
      <td data-label="관리"><div class="cell-actions">
        <button class="btn btn-sm" onclick="openStockModal('${p.id}')">재고</button>
        <button class="btn btn-sm btn-ghost" onclick="openProductModal('${p.id}')">수정</button>
        <button class="btn btn-sm btn-ghost text-danger" onclick="deleteProduct('${p.id}')">삭제</button>
      </div></td>
    </tr>`).join('')}</tbody></table></div>`;
  if (canReorder) {
    enableDragReorder(el('product-tbody'), 'tr', async (ids) => {
      _products.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      await apiReorderProducts(ids);
      toast('상품 순서를 변경했습니다.', 'info');
    });
  }
}

function openCategoryModal(id) {
  const cat = id ? _categories.find((c) => c.id === id) : null;
  openModal({
    title: cat ? '카테고리 수정' : '카테고리 추가',
    body: `<div class="field"><label>카테고리 이름</label><input class="input" id="cat-name" value="${esc(cat ? cat.name : '')}" placeholder="예: 게임 아이템" /></div>`,
    confirmText: '저장',
    onConfirm: async () => {
      const name = el('cat-name').value.trim();
      if (!name) { toast('이름을 입력하세요.', 'error'); return false; }
      if (cat) await apiUpdateCategory(id, name); else await apiCreateCategory(name);
      toast('카테고리를 저장했습니다.');
      closeModal(); renderProducts();
    }
  });
}
async function deleteCategory(id) {
  confirmDialog('카테고리 삭제', '이 카테고리를 삭제하시겠습니까? 연결된 상품은 미분류로 남습니다.', async () => {
    await apiDeleteCategory(id); toast('카테고리를 삭제했습니다.'); closeModal(); renderProducts();
  });
}

function openProductModal(id) {
  const p = id ? _products.find((x) => x.id === id) : null;
  const opts = _categories.map((c) => `<option value="${c.id}" ${p && p.categoryId === c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
  openModal({
    title: p ? '상품 수정' : '상품 추가',
    body: `
      <div class="field"><label>카테고리</label><select class="select" id="prd-cat">${opts}</select></div>
      <div class="field"><label>상품명</label><input class="input" id="prd-name" value="${esc(p ? p.name : '')}" placeholder="상품 이름" /></div>
      <div class="field"><label>가격 (원)</label><input class="input" type="number" id="prd-price" value="${p ? p.price : ''}" placeholder="5000" /></div>
      <div class="field"><label>이미지 URL</label><input class="input" id="prd-img" value="${esc(p ? (p.imageUrl || '') : '')}" placeholder="https://..." /></div>`,
    confirmText: '저장',
    onConfirm: async () => {
      const data = {
        categoryId: el('prd-cat').value,
        name: el('prd-name').value.trim(),
        price: parseInt(el('prd-price').value, 10) || 0,
        imageUrl: el('prd-img').value.trim()
      };
      if (!data.name) { toast('상품명을 입력하세요.', 'error'); return false; }
      if (p) await apiUpdateProduct(id, data); else await apiCreateProduct(data);
      toast('상품을 저장했습니다.'); closeModal(); renderProducts();
    }
  });
}
async function deleteProduct(id) {
  confirmDialog('상품 삭제', '이 상품을 삭제하시겠습니까? 되돌릴 수 없습니다.', async () => {
    await apiDeleteProduct(id); toast('상품을 삭제했습니다.'); closeModal(); renderProducts();
  });
}

async function openStockModal(id) {
  const p = _products.find((x) => x.id === id);
  if (!p) return;
  openModal({
    title: '재고 관리',
    sub: esc(p.name),
    body: spinnerBlock('재고를 불러오는 중...'),
    hideConfirm: true,
  });
  let items = Array.isArray(p.stockItems) ? p.stockItems : null;
  if (!items) {
    try {
      const full = await apiGetProduct(id);
      items = Array.isArray(full.stockItems) ? full.stockItems : [];
      p.stock = full.stock;
      p.stockItems = items;
    } catch (err) {
      toast('재고를 불러오지 못했습니다.', 'error');
      closeModal();
      return;
    }
  }
  const current = items.join('\n');
  openModal({
    title: '재고 관리',
    sub: esc(p.name),
    body: `
      <div class="field">
        <label>재고 목록 <span style="color:var(--text-dim);font-weight:400">· 한 줄에 하나씩 입력합니다</span></label>
        <textarea class="textarea" id="stock-input" style="min-height:200px;font-family:'IBM Plex Mono',monospace;font-size:12px" spellcheck="false" placeholder="STEAM-XXXX-YYYY-ZZZZ&#10;STEAM-AAAA-BBBB-CCCC">${esc(current)}</textarea>
        <div class="hint">저장 시 입력된 내용으로 재고가 설정됩니다. 현재 <span id="stock-count" style="color:var(--accent)">${items.length}</span>개</div>
      </div>
      ${switchRow('stock-notify', '모든 사람에게 재고 알림 보내기', false)}
      <div class="hint">켜면 구매자에게 입고 DM을 보냅니다. 기본은 꺼짐입니다.</div>`,
    confirmText: '저장',
    onConfirm: async () => {
      const next = el('stock-input').value.split('\n').map((l) => l.trim()).filter(Boolean);
      const notifyBuyers = !!el('stock-notify')?.checked;
      const saved = await apiSaveStock(id, next, { notifyBuyers });
      const idx = _products.findIndex((x) => String(x.id) === String(id));
      if (idx >= 0) {
        _products[idx] = {
          ..._products[idx],
          stock: saved && saved.stock != null ? saved.stock : next.length,
          stockItems: saved && Array.isArray(saved.stockItems) ? saved.stockItems : next,
        };
      }
      toast(`재고 ${next.length}개를 저장했습니다.`);
      closeModal();
      renderProductTable();
    }
  });
  const ta = el('stock-input');
  ta.addEventListener('input', () => {
    el('stock-count').textContent = ta.value.split('\n').map((l) => l.trim()).filter(Boolean).length;
  });
}
