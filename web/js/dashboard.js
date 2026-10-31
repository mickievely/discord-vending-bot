const DASH_PERIODS = [
  [1, '1일'],
  [7, '7일'],
  [30, '30일'],
  [90, '90일'],
  [0, '전체']
];

let _dashDays = 7;
let _dashBusy = false;

function readDashDays() {
  const raw = sessionStorage.getItem('vm_dash_days');
  if (raw == null || raw === '') return 7;
  const n = Number(raw);
  return [1, 7, 30, 90, 0].includes(n) ? n : 7;
}

function periodLabel(days) {
  return ({ 1: '1일', 7: '7일', 30: '30일', 90: '90일', 0: '전체' })[days] || '7일';
}

function salesTitle(days) {
  return ({ 1: '오늘 매출', 7: '최근 7일 매출', 30: '최근 30일 매출', 90: '최근 90일 매출', 0: '전체 매출' })[days] || '매출';
}

function periodTabs(active) {
  return `<div class="period-tabs" role="tablist">
    ${DASH_PERIODS.map(([d, label]) => `<button type="button" class="period-tab${d === active ? ' on' : ''}" data-days="${d}" onclick="setDashPeriod(${d})">${label}</button>`).join('')}
  </div>`;
}

function destroyDashCharts() {
  _charts.forEach((c) => { try { c.destroy(); } catch {} });
  _charts = [];
}

function mountDashCharts(d) {
  if (!window.Chart) return;
  const muted = '#a6a29c';
  const grid = 'rgba(52,54,58,.7)';
  Chart.defaults.color = muted;
  Chart.defaults.font.family = "'IBM Plex Sans KR', system-ui, sans-serif";
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  const series = d.series || [];
  const salesEl = el('chart-sales');
  if (salesEl) {
    _charts.push(new Chart(salesEl, {
      type: 'line',
      data: {
        labels: series.map((x) => x.label),
        datasets: [{
          label: '매출',
          data: series.map((x) => x.sales),
          borderColor: '#8fb4cc',
          backgroundColor: (ctx) => {
            const { chart } = ctx;
            const { ctx: c, chartArea } = chart;
            if (!chartArea) return 'rgba(127,160,184,.18)';
            const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            g.addColorStop(0, 'rgba(143,180,204,.35)');
            g.addColorStop(1, 'rgba(143,180,204,0)');
            return g;
          },
          fill: true,
          tension: 0.35,
          pointRadius: series.length > 20 ? 0 : 3,
          pointHoverRadius: 5,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (it) => ' ' + won(it.parsed.y) } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: muted, maxRotation: 0, autoSkip: true, maxTicksLimit: series.length > 14 ? 8 : 12 } },
          y: { grid: { color: grid }, ticks: { color: muted, callback: (v) => Number(v).toLocaleString('ko-KR') }, beginAtZero: true }
        }
      }
    }));
  }
  const split = d.chargeSplit || { aos: 0, ios: 0 };
  const chargeEl = el('chart-charge');
  if (chargeEl) {
    const aos = split.aos || 0, ios = split.ios || 0;
    _charts.push(new Chart(chargeEl, {
      type: 'doughnut',
      data: {
        labels: ['AOS', 'IOS'],
        datasets: [{ data: [aos, ios], backgroundColor: ['#7fa0b8', '#d1a866'], borderWidth: 0, hoverOffset: 4 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (it) => ` ${it.label} ${it.parsed}건` } } }
      }
    }));
  }
  const top = d.topProducts || [];
  const topEl = el('chart-top');
  if (topEl && top.length) {
    _charts.push(new Chart(topEl, {
      type: 'bar',
      data: {
        labels: top.map((p) => p.name.length > 10 ? p.name.slice(0, 10) + '…' : p.name),
        datasets: [{ label: '매출', data: top.map((p) => p.sales), backgroundColor: '#7fae82', borderRadius: 6, maxBarThickness: 28 }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (it) => ' ' + won(it.parsed.x) } } },
        scales: {
          x: { grid: { color: grid }, ticks: { color: muted, callback: (v) => Number(v).toLocaleString('ko-KR') }, beginAtZero: true },
          y: { grid: { display: false }, ticks: { color: muted } }
        }
      }
    }));
  }
}

function applyDashCharts(d, days) {
  destroyDashCharts();
  if (el('dash-sales-title')) el('dash-sales-title').textContent = salesTitle(days);
  if (el('dash-sales-sub')) el('dash-sales-sub').textContent = '완료 주문 · ' + periodLabel(days);
  if (el('dash-charge-title')) el('dash-charge-title').textContent = '충전 구성';
  if (el('dash-charge-sub')) el('dash-charge-sub').textContent = `${Number(d.chargeCount || 0)}건 · ${periodLabel(days)}`;
  if (el('dash-top-sub')) el('dash-top-sub').textContent = days === 0 ? '누적' : periodLabel(days);
  if (el('chart-sales-box')) el('chart-sales-box').innerHTML = '<canvas id="chart-sales"></canvas>';
  if (el('chart-charge-box')) el('chart-charge-box').innerHTML = '<canvas id="chart-charge"></canvas>';
  if (el('chart-top-box')) {
    el('chart-top-box').innerHTML = (d.topProducts || []).length ? '<canvas id="chart-top"></canvas>' : emptyBlock('데이터가 없습니다', '');
  }
  mountDashCharts(d);
}

async function setDashPeriod(days) {
  if (_dashBusy || days === _dashDays) return;
  _dashDays = days;
  sessionStorage.setItem('vm_dash_days', String(days));
  document.querySelectorAll('.period-tab').forEach((btn) => btn.classList.toggle('on', Number(btn.dataset.days) === days));
  const box = el('dash-charts');
  box?.classList.add('is-loading');
  _dashBusy = true;
  try {
    applyDashCharts(await apiGetDashboard(days), days);
  } catch {
    toast('기간별 통계를 불러오지 못했습니다.', 'error');
  } finally {
    _dashBusy = false;
    box?.classList.remove('is-loading');
  }
}

async function renderDashboard() {
  content().innerHTML = spinnerBlock('대시보드를 불러오는 중...');
  _dashDays = readDashDays();
  try {
    const d = await apiGetDashboard(_dashDays);
    const icons = {
      sales: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>',
      orders: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/></svg>',
      charge: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>',
      stock: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/></svg>'
    };
    content().innerHTML = `
      <div class="stat-grid">
        ${statCard('오늘 매출', won(d.todaySales), '완료된 주문 기준', icons.sales, '--success')}
        ${statCard('총 주문 수', d.totalOrders + '건', '누적 주문', icons.orders, '--info')}
        ${statCard('충전 대기', d.pendingCharges + '건', '승인 대기 중', icons.charge, '--warning')}
        ${statCard('재고 부족', d.lowStock + '개', '5개 이하 상품', icons.stock, '--danger')}
      </div>

      <div class="dash-toolbar">
        <div>
          <div class="card-title">기간별 통계</div>
          <div class="card-sub">매출 · 충전 · TOP 상품을 같은 기간으로 봅니다</div>
        </div>
        ${periodTabs(_dashDays)}
      </div>
      <div class="dash-charts" id="dash-charts">
        <div class="card chart-card">
          <div class="card-header"><div><div class="card-title" id="dash-sales-title">${esc(salesTitle(_dashDays))}</div><div class="card-sub" id="dash-sales-sub">완료 주문 · ${esc(periodLabel(_dashDays))}</div></div></div>
          <div class="chart-box" id="chart-sales-box"><canvas id="chart-sales"></canvas></div>
        </div>
        <div class="card chart-card">
          <div class="card-header"><div><div class="card-title" id="dash-charge-title">충전 구성</div><div class="card-sub" id="dash-charge-sub">${Number(d.chargeCount || 0)}건 · ${esc(periodLabel(_dashDays))}</div></div></div>
          <div class="chart-box chart-box-sm" id="chart-charge-box"><canvas id="chart-charge"></canvas></div>
        </div>
        <div class="card chart-card">
          <div class="card-header"><div><div class="card-title">매출 TOP 5</div><div class="card-sub" id="dash-top-sub">${_dashDays === 0 ? '누적' : esc(periodLabel(_dashDays))}</div></div></div>
          <div class="chart-box" id="chart-top-box">${(d.topProducts || []).length ? '<canvas id="chart-top"></canvas>' : emptyBlock('데이터가 없습니다', '')}</div>
        </div>
      </div>

      <div class="dash-lower">
        <div class="card">
          <div class="card-header">
            <div class="card-title">최근 주문</div>
            <button class="btn btn-sm btn-ghost" onclick="showView('orders')">전체 보기</button>
          </div>
          <div class="table-wrap" style="border:none;border-radius:0">
            <table>
              <thead><tr><th>주문 ID</th><th>상품</th><th>금액</th><th>상태</th></tr></thead>
              <tbody>
                ${(d.recentOrders || []).map((o) => `<tr>
                  <td data-label="주문 ID" class="mono">${esc(o.id)}</td>
                  <td data-label="상품">${esc(o.productName)}</td>
                  <td data-label="금액" class="amount">${won(o.total)}</td>
                  <td data-label="상태">${statusBadge(o.status)}</td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">충전 대기 요청</div>
            <button class="btn btn-sm btn-ghost" onclick="showView('charges')">전체 보기</button>
          </div>
          <div class="dash-charge-list">
            ${d.pendingChargeList.length ? d.pendingChargeList.map((c) => `
              <button type="button" class="dash-charge-row" onclick="showView('charges')">
                <span class="badge ${c.platform === 'AOS' ? 'badge-info' : 'badge-muted'}">${c.platform}</span>
                <div class="dash-charge-meta">
                  <div class="dash-charge-name">${esc(c.depositor || '-')}</div>
                  <div class="mono">${esc(c.userId)}</div>
                </div>
                <span class="amount text-success">+${won(c.amount)}</span>
              </button>`).join('') : emptyBlock('대기 중인 요청이 없습니다', '')}
          </div>
        </div>
      </div>

      <div class="card dash-stock">
        <div class="card-header"><div class="card-title">재고 부족 상품</div><span class="card-sub">재고 5개 이하 · 상위 8개</span></div>
        <div class="table-wrap" style="border:none;border-radius:0">
          <table>
            <thead><tr><th>상품명</th><th>가격</th><th>남은 재고</th></tr></thead>
            <tbody>
              ${d.lowStockProducts.length ? d.lowStockProducts.map((p) => `<tr>
                <td data-label="상품명">${esc(p.name)}</td>
                <td data-label="가격" class="amount">${won(p.price)}</td>
                <td data-label="남은 재고"><span class="badge ${p.stock === 0 ? 'badge-danger' : 'badge-warning'}">${p.stock}개</span></td>
              </tr>`).join('') : `<tr><td colspan="3">${emptyBlock('재고 부족 상품이 없습니다', '')}</td></tr>`}
            </tbody>
          </table>
        </div>
      </div>`;
    mountDashCharts(d);
  } catch (err) {
    content().innerHTML = errorBlock('대시보드를 불러오지 못했습니다.', "renderDashboard()");
  }
}
