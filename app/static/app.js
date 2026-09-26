let orders = [];
let selectedOrderId = null;

const $ = (id) => document.getElementById(id);

function showMessage(text, type = 'success') {
  const el = $('message');
  el.textContent = text;
  el.className = `message ${type}`;
  setTimeout(() => el.classList.add('hidden'), 4500);
}

function statusBadge(status) {
  const cls = status === 'DISPATCHED' ? 'dispatched' : status === 'REJECTED' ? 'rejected' : status === 'PENDING_REVIEW' ? 'review' : 'new';
  return `<span class="badge ${cls}">${status}</span>`;
}

function riskBadge(risk) {
  const cls = risk === 'LOW' ? 'low' : risk === 'HIGH' ? 'high' : 'new';
  return `<span class="badge ${cls}">${risk || '-'}</span>`;
}

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

async function loadOrders() {
  orders = await api('/orders');
  renderStats();
  renderOrders();
  if (selectedOrderId) {
    try { await loadDetails(selectedOrderId); } catch (_) { }
  }
}

function renderStats() {
  const total = orders.length;
  const review = orders.filter(x => x.status === 'PENDING_REVIEW').length;
  const dispatched = orders.filter(x => x.status === 'DISPATCHED').length;
  const rejected = orders.filter(x => x.status === 'REJECTED').length;
  $('stats').innerHTML = `
    <div class="stat"><div class="number">${total}</div><span class="label">Total Orders</span></div>
    <div class="stat"><div class="number">${review}</div><span class="label">Pending Review</span></div>
    <div class="stat"><div class="number">${dispatched}</div><span class="label">Dispatched</span></div>
    <div class="stat"><div class="number">${rejected}</div><span class="label">Rejected</span></div>`;
}

function renderOrders() {
  const query = $('search').value.toLowerCase().trim();
  const filtered = orders.filter(o =>
    `${o.order_id} ${o.client_name} ${o.client_type} ${o.status}`.toLowerCase().includes(query)
  );
  if (!filtered.length) {
    $('ordersBody').innerHTML = '<tr><td colspan="7" class="empty">No orders found.</td></tr>';
    return;
  }
  $('ordersBody').innerHTML = filtered.map(o => `
    <tr>
      <td><strong>${escapeHtml(o.order_id)}</strong></td>
      <td>${escapeHtml(o.client_name)}</td>
      <td>${escapeHtml(o.client_type)}</td>
      <td>${statusBadge(o.status)}</td>
      <td>${riskBadge(o.risk_level)}</td>
      <td>${Number(o.total_value || 0).toFixed(2)}</td>
      <td><div class="actions"><button class="view" onclick="loadDetails('${escapeAttr(o.order_id)}')">View</button>${o.status !== 'DISPATCHED' ? `<button class="primary" onclick="processOrder('${escapeAttr(o.order_id)}')">Process</button>` : ''}</div></td>
    </tr>`).join('');
}

async function loadDetails(orderId) {
  selectedOrderId = orderId;
  const data = await api(`/orders/${encodeURIComponent(orderId)}`);
  const o = data.order;
  $('detailsCard').classList.remove('hidden');
  $('detailTitle').textContent = `Order ${o.order_id}`;
  $('detailSummary').textContent = o.decision_summary || 'No decision summary yet.';
  $('detailClient').textContent = o.client_name;
  $('detailType').textContent = o.client_type;
  $('detailStatus').innerHTML = statusBadge(o.status);
  $('detailRisk').innerHTML = riskBadge(o.risk_level);
  $('detailTotal').textContent = Number(o.total_value || 0).toFixed(2);

  const lineEvents = data.decision_trace.filter(e => e.event_type === 'LINE_DECISION');
  $('lines').innerHTML = lineEvents.length ? lineEvents.map(e => {
    const d = e.details || {};
    return `<div class="line-card">
      <strong>${escapeHtml(d.raw_text || '')}</strong>
      <div>SKU: ${escapeHtml(d.sku || '-')} | Quantity: ${d.quantity ?? '-'} | Catalog: ${escapeHtml(d.catalog_name || '-')}</div>
      <div>Warehouse: ${escapeHtml(d.inventory_source || '-')} | Decision: <strong>${escapeHtml(d.decision || '-')}</strong></div>
      <div>Confidence: ${d.reconciliation_confidence ?? '-'} | ${escapeHtml(d.reason || '')}</div>
    </div>`;
  }).join('') : '<div class="empty">No line decisions yet. Process this order first.</div>';

  $('trace').innerHTML = data.decision_trace.length ? data.decision_trace.map(e => `
    <div class="trace-item">
      <div class="event">${escapeHtml(e.event_type)}</div>
      <div>${escapeHtml(e.created_at || '')}</div>
      <pre>${escapeHtml(JSON.stringify(e.details, null, 2))}</pre>
    </div>`).join('') : '<div class="empty">No events yet.</div>';

  const buttons = $('overrideButtons');
  if (o.status === 'PENDING_REVIEW') {
    buttons.innerHTML = `<button class="approve" onclick="overrideOrder('${escapeAttr(orderId)}', 'APPROVE')">Approve &amp; Dispatch</button>
                         <button class="reject" onclick="overrideOrder('${escapeAttr(orderId)}', 'REJECT')">Reject</button>`;
  } else {
    buttons.innerHTML = '';
  }
  $('detailsCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function processOrder(orderId) {
  try {
    await api(`/orders/${encodeURIComponent(orderId)}/process`, { method: 'POST' });
    showMessage(`${orderId} processed successfully.`);
    await loadOrders();
    await loadDetails(orderId);
  } catch (e) { showMessage(e.message, 'error'); }
}

async function overrideOrder(orderId, decision) {
  const reason = prompt(`Reason for ${decision.toLowerCase()}ing ${orderId}:`, 'Reviewed by operations');
  if (reason === null) return;
  try {
    await api(`/orders/${encodeURIComponent(orderId)}/override`, {
      method: 'POST',
      body: JSON.stringify({ decision, reason })
    });
    showMessage(`${orderId}: ${decision} completed.`);
    await loadOrders();
    await loadDetails(orderId);
  } catch (e) { showMessage(e.message, 'error'); }
}

async function ingest() {
  try {
    const result = await api('/ingest', { method: 'POST' });
    showMessage(`CSV loaded. ${result.orders_inserted} new orders inserted.`);
    await loadOrders();
  } catch (e) { showMessage(e.message, 'error'); }
}

async function processAll() {
  if (!confirm('Process all orders that are not already dispatched?')) return;
  try {
    const result = await api('/process-all', { method: 'POST' });
    showMessage(`Processed ${result.processed} orders.`);
    await loadOrders();
  } catch (e) { showMessage(e.message, 'error'); }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#96;'); }

$('refreshBtn').addEventListener('click', () => loadOrders().catch(e => showMessage(e.message, 'error')));
$('ingestBtn').addEventListener('click', ingest);
$('processAllBtn').addEventListener('click', processAll);
$('search').addEventListener('input', renderOrders);

loadOrders().catch(e => showMessage(e.message, 'error'));
