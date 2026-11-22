/* ACMS Admin - plain JavaScript, no build step. Serve through the FastAPI app.
   Sections: 1 Config | 2 MOCK DATA | 3 API layer | 4 Helpers | 5 Pages | 6 Events | 7 Router
   Matches app/api/dashboardapi.py (routes under /api: products + orders). */

/* ===== 1. CONFIG ===== */
const USE_MOCK = false;                   // true = fake data in the browser, false = use the FastAPI backend
const LOW_STOCK = 10;                     // dashboard "Low Stock Alerts" = products with stock at or below this

/* ===== 2. MOCK DATA (fake, development only; same shapes as the backend returns) ===== */
const STATUSES = ['pending', 'paid', 'cancelled'];   // the only statuses the backend accepts
const SIZES = ['S', 'M', 'L', 'XL', 'XXL'];          // sizes you can pick when adding an order

const pad2 = (n) => String(n).padStart(2, '0');
const fmtDate = (d) => pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear() + ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());

let mockProducts = [
  ['Wireless Earbuds 2', 320, 79.99, 'Electronics'], ['Yoga Mat', 0, 25, 'Fitness'], ['Ceramic Coffee Mug', 120, 12.5, 'Home'],
  ['Smart Watch', 210, 199.99, 'Electronics'], ['Running Shoes', 80, 120, 'Footwear'], ['Leather Backpack', 55, 95.5, 'Accessories'],
  ['Dumbbell Set', 40, 89, 'Fitness'], ['Air Fryer', 0, 110, 'Home'], ['Denim Jacket', 65, 70, 'Clothing'],
  ['Bluetooth Speaker', 150, 45, 'Electronics'], ['Sunglasses', 90, 60, 'Accessories'], ['Water Bottle', 8, 18, 'Fitness'],
].map((p, i) => ({ id: i + 1, name: p[0], stock: p[1], price: p[2], category: p[3] }));

const people = ['Sophia Clark', 'Liam Johnson', 'Olivia Brown', 'Noah Davis', 'Emma Wilson', 'Walk-in'];
const cycle = ['paid', 'pending', 'paid', 'cancelled', 'paid'];
const mockSizes = ['S', 'M', 'L', 'XL', 'XXL', ''];
let mockOrders = Array.from({ length: 24 }, (_, i) => {
  const d = new Date(); d.setDate(d.getDate() - i); d.setHours(9 + (i % 8), (i * 7) % 60, 0);
  return { id: 12368 - i, customer: people[i % 6], phone: '555-010' + (i % 6), items: mockProducts[i % mockProducts.length].name,
    size: mockSizes[i % 6], quantity: 1 + (i % 4), status: cycle[i % 5], date: fmtDate(d) };
});

/* ===== 3. API LAYER (pages only call `api`) ===== */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clone = (x) => JSON.parse(JSON.stringify(x));
const nextId = (list) => Math.max(0, ...list.map((x) => x.id)) + 1;

const mockApi = {
  async getProducts() { await sleep(400); return clone(mockProducts); },
  async saveProduct(p) {
    await sleep(300);
    const item = { name: p.name, category: p.category, price: p.price, stock: p.stock };
    if (p.id) mockProducts = mockProducts.map((x) => (x.id === p.id ? { ...x, ...item } : x));
    else mockProducts.push({ ...item, id: nextId(mockProducts) });
  },
  async deleteProduct(id) { await sleep(300); mockProducts = mockProducts.filter((x) => x.id !== id); },
  async getOrders() { await sleep(400); return clone(mockOrders); },
  async createOrder(o) {
    await sleep(300);
    const p = mockProducts.find((x) => x.name === o.product_name);
    if (!p) throw new Error('Product not found');
    mockOrders.push({ id: nextId(mockOrders), customer: o.customer, phone: o.phone, items: p.name, size: o.size || '', quantity: o.quantity, status: 'pending', date: fmtDate(new Date()) });
  },
  async setOrderStatus(id, status) { await sleep(300); mockOrders = mockOrders.map((o) => (o.id === id ? { ...o, status } : o)); },
  async deleteOrder(id) { await sleep(300); mockOrders = mockOrders.filter((o) => o.id !== id); },
};

// HTTP version - routes taken from dashboardapi.py
async function http(path, options = {}) {
  const headers = options.body ? { 'Content-Type': 'application/json' } : {};   // no header on GET = no CORS preflight
  let r;
  try { r = await fetch(path, { ...options, headers }); }
  catch (e) { throw new Error('Cannot reach the API. Make sure FastAPI is running and open the dashboard from the same server URL.'); }
  if (!r.ok) {
    let msg = 'API error ' + r.status + ' on ' + path;
    try {
      const b = await r.json();   // FastAPI sends {detail: "text"} or {detail: [{loc, msg}, ...]}
      if (typeof b.detail === 'string') msg = b.detail;
      else if (Array.isArray(b.detail)) msg = b.detail.map((d) => (d.loc || []).slice(1).join('.') + ': ' + d.msg).join('; ');
    } catch (e) { /* body was not JSON, keep the default message */ }
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
}
const send = (method, body) => ({ method, body: JSON.stringify(body) });
const httpApi = {
  getProducts: () => http('/api/products'),
  saveProduct: (p) => {
    const body = { name: p.name, category: p.category, price: p.price, stock: p.stock };
    return p.id ? http('/api/products/' + p.id, send('PUT', body)) : http('/api/products', send('POST', body));
  },
  deleteProduct: (id) => http('/api/products/' + id, { method: 'DELETE' }),
  getOrders: () => http('/api/orders'),
  createOrder: (o) => http('/api/orders', send('POST', o)),   // o = { customer, phone, product_name, size, quantity }
  setOrderStatus: (id, status) => http('/api/orders/' + id, send('PATCH', { status })),
  deleteOrder: (id) => http('/api/orders/' + id, { method: 'DELETE' }),
};
const api = USE_MOCK ? mockApi : httpApi;

/* ===== 4. HELPERS ===== */
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cap = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);
const money = (n) => '৳' + Number(n).toLocaleString('en-BD', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const badge = (t) => '<span class="badge b-' + t.replace(/\s/g, '').toLowerCase() + '">' + esc(t) + '</span>';
const empty = (t) => '<div class="state empty">' + esc(t) + '</div>';
const stat = (label, value, red) => '<div class="card stat"><div class="label">' + label + '</div><div class="value' + (red ? ' red' : '') + '">' + value + '</div></div>';
const uniq = (a) => [...new Set(a)];
const options = (list, current, first) =>
  '<option value="">' + first + '</option>' + list.map((o) => {
    const [v, t] = Array.isArray(o) ? o : [o, o];
    return '<option value="' + esc(v) + '"' + (String(current) === String(v) ? ' selected' : '') + '>' + esc(t) + '</option>';
  }).join('');
const table = (heads, rows) =>
  '<div class="table-wrap"><table><thead><tr>' + heads.map((h) => '<th>' + h + '</th>').join('') + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
function pager(page, pages, action) {
  if (pages <= 1) return '';
  return '<div class="pager"><button class="btn" data-action="' + action + '" data-page="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '>Previous</button>' +
    '<span>Page ' + page + ' of ' + pages + '</span><button class="btn" data-action="' + action + '" data-page="' + (page + 1) + '"' + (page >= pages ? ' disabled' : '') + '>Next</button></div>';
}
function openDialog(title, body) {
  $('#dialog').innerHTML = '<div class="dialog-head"><h2>' + esc(title) + '</h2><button class="icon-btn" data-action="close-dialog" aria-label="Close">×</button></div>' + body;
  $('#overlay').hidden = false;
}
const closeDialog = () => { $('#overlay').hidden = true; $('#dialog').innerHTML = ''; };

// The backend sends dates as "dd/mm/yyyy hh:mm:ss"
function parseDate(s) {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})(?: (\d{2}):(\d{2}):(\d{2}))?/.exec(s || '');
  return m ? new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)) : null;
}

// Newest first, so a product/order you just added shows on page 1
const loadProducts = async () => (await api.getProducts()).sort((a, b) => b.id - a.id);
const loadOrders = async () => (await api.getOrders()).sort((a, b) => b.id - a.id);

// The backend orders have no price/total. Total = quantity x the product's CURRENT price (matched by product name).
let priceCache = { ref: null, map: null };
function priceOf(name) {
  if (priceCache.ref !== data.products) {
    const map = new Map();
    data.products.forEach((p) => { if (!map.has(p.name)) map.set(p.name, p.price); });   // backend uses the first match too
    priceCache = { ref: data.products, map };
  }
  return priceCache.map.get(name);
}
const totalOf = (o) => { const p = priceOf(o.items); return p === undefined ? null : p * o.quantity; };   // null = product no longer exists
const moneyOrDash = (n) => (n === null ? '—' : money(n));

function areaChart(data) {
  const W = 600, H = 220, min = Math.min(...data), max = Math.max(...data);
  const pts = data.map((v, i) => [(i * W) / (data.length - 1), H - 10 - ((v - min) / (max - min || 1)) * (H - 20)]);
  let d = 'M' + pts[0];
  for (let i = 1; i < pts.length; i++) { const cx = (pts[i - 1][0] + pts[i][0]) / 2; d += ' C' + cx + ',' + pts[i - 1][1] + ' ' + cx + ',' + pts[i][1] + ' ' + pts[i]; }
  return '<svg class="area" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="Sales trend"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0096ff"/><stop offset="1" stop-color="#0096ff" stop-opacity="0"/></linearGradient></defs><path d="' + d + ' L' + W + ',' + H + ' L0,' + H + ' Z" fill="url(#g)"/></svg>';
}
function donut(parts, total) {
  const r = 40, c = 2 * Math.PI * r; let off = 0;
  const circles = parts.map((p) => {
    const len = (p.value / (total || 1)) * c;
    const s = '<circle cx="50" cy="50" r="40" fill="none" stroke="' + p.color + '" stroke-width="12" stroke-dasharray="' + len + ' ' + (c - len) + '" stroke-dashoffset="' + -off + '"/>';
    off += len; return s;
  }).join('');
  const legend = parts.map((p) => '<li><span class="dot" style="background:' + p.color + '"></span><span><b>' + p.label + '</b><br><span class="small">' + p.value + ' (' + Math.round((p.value / (total || 1)) * 100) + '%)</span></span></li>').join('');
  return '<div class="donut-wrap"><div class="donut"><svg viewBox="0 0 100 100">' + circles + '</svg><div class="center"><b class="big">' + total + '</b><span class="small">Total Orders</span></div></div><ul class="legend">' + legend + '</ul></div>';
}

/* ===== 5. PAGES ===== */
const data = { products: [], orders: [] };
const view = {
  prod: { q: '', stock: '', price: '', sort: '', page: 1 },
  ord: { tab: 'summary', q: '', status: '', product: '', page: 1 },
};

/* --- Dashboard (the backend has no dashboard route, so everything is calculated from products + orders) --- */
function dashboardStats() {
  const o = data.orders, N = 30, DAY = 864e5;
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const today = startOfDay(new Date());
  const paid = o.filter((x) => x.status === 'paid');
  const trend = Array(N).fill(0); let prev = 0;
  paid.forEach((x) => {
    const d = parseDate(x.date); if (!d) return;
    const ago = Math.round((today - startOfDay(d)) / DAY), t = totalOf(x) || 0;
    if (ago >= 0 && ago < N) trend[N - 1 - ago] += t;          // last 30 days, one point per day
    else if (ago >= N && ago < 2 * N) prev += t;               // the 30 days before that
  });
  const last30 = trend.reduce((a, b) => a + b, 0);
  const sold = new Map();
  o.filter((x) => x.status !== 'cancelled').forEach((x) => sold.set(x.items, (sold.get(x.items) || 0) + x.quantity));
  return {
    totalSales: paid.reduce((s, x) => s + (totalOf(x) || 0), 0),
    pendingOrders: o.filter((x) => x.status === 'pending').length,
    lowStock: data.products.filter((p) => p.stock <= LOW_STOCK).length,
    trend, last30, trendPct: prev > 0 ? Math.round(((last30 - prev) / prev) * 100) : null,
    bestSellers: Array.from(sold, ([name, units]) => ({ name, units })).sort((a, b) => b.units - a.units).slice(0, 4),
  };
}
const dashboardPage = {
  load: async () => { [data.products, data.orders] = await Promise.all([loadProducts(), loadOrders()]); },
  draw() {
    const d = dashboardStats();
    const best = d.bestSellers.length ? '<ul class="list">' + d.bestSellers.map((b) =>
      '<li><span class="thumb">' + esc(b.name.charAt(0) || '?') + '</span><span><b>' + esc(b.name) + '</b><br>' + b.units.toLocaleString() + ' units sold</span></li>').join('') + '</ul>' : empty('No sales yet');
    const recent = data.orders.length ? table(['Order ID', 'Customer', 'Date', 'Status', 'Total'], data.orders.slice(0, 5).map((o) =>
      '<tr><td class="strong">#' + o.id + '</td><td>' + esc(o.customer) + '</td><td>' + esc(o.date) + '</td><td>' + badge(cap(o.status)) + '</td><td class="strong">' + moneyOrDash(totalOf(o)) + '</td></tr>').join('')) : empty('No orders yet');
    const headline = d.trendPct === null ? money(d.last30) : (d.trendPct >= 0 ? '+' : '') + d.trendPct + '%';
    $('#app').innerHTML = '<h1>Dashboard</h1>' + (USE_MOCK ? '<p class="mock-note">Showing mock data</p>' : '') +
      '<div class="grid g3">' + stat('Total Sales', money(d.totalSales), false) + stat('Pending Orders', d.pendingOrders, false) + stat('Low Stock Alerts', d.lowStock, true) + '</div>' +
      '<div class="grid g-main"><div class="card flush"><div class="pad"><h2>Sales Trends</h2><span class="big">' + headline + '</span> <span class="small">in the last 30 days</span></div>' + areaChart(d.trend) + '</div>' +
      '<div class="card"><h2>Best sellers</h2>' + best + '</div></div><div class="card"><h2>Recent Orders</h2>' + recent + '</div>';
  },
};

/* --- Products --- */
const PER_PAGE = 6;
const productsPage = {
  load: async () => { data.products = await loadProducts(); },
  draw() {
    const v = view.prod, p = data.products;
    $('#app').innerHTML = '<h1>Products</h1>' + (USE_MOCK ? '<p class="mock-note">Showing mock data</p>' : '') + '<div class="grid g3">' + stat('Total Products', p.length) + stat('Active Products', p.filter((x) => x.stock > 0).length) + stat('Out of Stock', p.filter((x) => x.stock === 0).length) + '</div>' +
      '<div class="toolbar"><input data-scope="prod" data-key="q" placeholder="Search name or category…" aria-label="Search products" value="' + esc(v.q) + '">' +
      '<select data-scope="prod" data-key="stock" aria-label="Stock status">' + options([['in', 'In stock'], ['out', 'Out of stock']], v.stock, 'Stock Status') + '</select>' +
      '<select data-scope="prod" data-key="price" aria-label="Price range">' + options([['lt50', 'Under $50'], ['50-100', '$50 – $100'], ['gt100', 'Over $100']], v.price, 'Price Range') + '</select>' +
      '<select data-scope="prod" data-key="sort" aria-label="Sort by">' + options([['name', 'Name'], ['price-asc', 'Price: low to high'], ['price-desc', 'Price: high to low'], ['stock', 'Stock']], v.sort, 'Sort by') + '</select>' +
      '<button class="btn primary" data-action="add-product">+ Add Product</button></div><div class="card" id="results"></div>';
    updateProducts();
  },
};
function updateProducts() {
  const v = view.prod, q = v.q.toLowerCase();
  let r = data.products.filter((p) => p.name.toLowerCase().includes(q) || (p.category || '').toLowerCase().includes(q));
  if (v.stock === 'in') r = r.filter((p) => p.stock > 0);
  if (v.stock === 'out') r = r.filter((p) => p.stock === 0);
  if (v.price === 'lt50') r = r.filter((p) => p.price < 50);
  if (v.price === '50-100') r = r.filter((p) => p.price >= 50 && p.price <= 100);
  if (v.price === 'gt100') r = r.filter((p) => p.price > 100);
  const sorts = { name: (a, b) => a.name.localeCompare(b.name), 'price-asc': (a, b) => a.price - b.price, 'price-desc': (a, b) => b.price - a.price, stock: (a, b) => b.stock - a.stock };
  if (sorts[v.sort]) r = r.slice().sort(sorts[v.sort]);
  const pages = Math.max(1, Math.ceil(r.length / PER_PAGE));
  v.page = Math.min(v.page, pages);
  const rows = r.slice((v.page - 1) * PER_PAGE, v.page * PER_PAGE).map((p) =>
    '<tr><td><div class="cell-flex"><span class="thumb">' + esc(p.name.charAt(0) || '?') + '</span>' + esc(p.name) + '</div></td><td>' + (esc(p.category || '') || '—') + '</td><td>' + p.stock + '</td><td>' + money(p.price) + '</td>' +
    '<td>' + badge(p.stock > 0 ? 'Active' : 'Out of Stock') + '</td><td><button class="icon-btn" data-action="edit-product" data-id="' + p.id + '" aria-label="Edit ' + esc(p.name) + '" title="Edit">✎</button> ' +
    '<button class="icon-btn" data-action="delete-product" data-id="' + p.id + '" aria-label="Delete ' + esc(p.name) + '" title="Delete">🗑</button></td></tr>').join('');
  $('#results').innerHTML = (r.length ? table(['Product', 'Category', 'Stock', 'Price', 'Status', 'Actions'], rows) : empty('No products match your filters.')) + pager(v.page, pages, 'prod-page');
}
// The backend now returns and saves category on both create and update, so the field is always shown.
function productForm(p) {
  p = p || { name: '', category: '', stock: '', price: '' };
  openDialog(p.id ? 'Edit Product' : 'Add Product',
    '<div class="form" data-id="' + (p.id || '') + '"><label>Name<input id="f-name" maxlength="200" value="' + esc(p.name) + '"></label>' +
    '<label>Category<input id="f-cat" maxlength="200" value="' + esc(p.category || '') + '"></label>' +
    '<div class="two"><label>Stock<input id="f-stock" type="number" min="0" step="1" value="' + p.stock + '"></label><label>Price ($)<input id="f-price" type="number" min="0" max="99999999.99" step="0.01" value="' + p.price + '"></label></div>' +
    '<p class="error-text" id="f-err" role="alert"></p><div class="actions"><button class="btn" data-action="close-dialog">Cancel</button><button class="btn primary" data-action="save-product">Save</button></div></div>');
}
async function saveProduct(btn) {
  const err = $('#f-err'), name = $('#f-name').value.trim(), category = $('#f-cat').value.trim(), stockS = $('#f-stock').value, priceS = $('#f-price').value;
  const stock = Number(stockS), price = Number(priceS);
  if (!name) { err.textContent = 'Name is required.'; return; }
  if (name.length > 200) { err.textContent = 'Name must be 200 characters or fewer.'; return; }
  if (!category) { err.textContent = 'Category is required.'; return; }
  if (stockS === '' || !Number.isInteger(stock) || stock < 0) { err.textContent = 'Stock must be a whole number, 0 or more.'; return; }
  if (priceS === '' || !(price >= 0)) { err.textContent = 'Price must be 0 or more.'; return; }
  if (Math.abs(price * 100 - Math.round(price * 100)) > 1e-6) { err.textContent = 'Price can have at most 2 decimal places.'; return; }
  if (price >= 1e8) { err.textContent = 'Price must be below $100,000,000.'; return; }
  const id = Number($('.form').dataset.id) || undefined;
  btn.disabled = true; btn.textContent = 'Saving…';
  try { await api.saveProduct({ id, name, category, stock, price }); closeDialog(); data.products = await loadProducts(); productsPage.draw(); }
  catch (e) { err.textContent = e.message; btn.disabled = false; btn.textContent = 'Save'; }
}

/* --- Orders --- */
const COLORS = { paid: '#34d399', pending: '#facc15', cancelled: '#f87171' };
const VERBS = { paid: 'paid', pending: 'received', cancelled: 'cancelled' };
const ORD_PER_PAGE = 8;
const ordersPage = {
  load: async () => { [data.orders, data.products] = await Promise.all([loadOrders(), loadProducts()]); },
  draw() {
    const t = view.ord.tab;
    $('#app').innerHTML = '<h1>Orders</h1>' + (USE_MOCK ? '<p class="mock-note">Showing mock data</p>' : '') +
      '<div class="toolbar"><button class="btn primary" data-action="add-order">+ Add Order</button></div>' +
      '<div class="tabs" role="tablist"><button role="tab" class="' + (t === 'summary' ? 'on' : '') + '" data-action="tab" data-tab="summary">Order Summary</button>' +
      '<button role="tab" class="' + (t === 'list' ? 'on' : '') + '" data-action="tab" data-tab="list">Order List</button></div><div id="ord-body"></div>';
    t === 'summary' ? drawOrderSummary() : drawOrderList();
  },
};
function drawOrderSummary() {
  const o = data.orders, n = (s) => o.filter((x) => x.status === s).length;
  const activity = o.length ? '<ul class="list">' + o.slice(0, 5).map((x) => '<li><span class="dot" style="background:' + (COLORS[x.status] || '#94a3b8') + '"></span><span>Order #' + x.id + ' ' + esc(VERBS[x.status] || x.status) + '<br><span class="small">' + esc(x.date) + '</span></span></li>').join('') + '</ul>' : empty('No activity yet');
  $('#ord-body').innerHTML = '<div class="grid g4">' + stat('Total Orders', o.length) + stat('Pending', n('pending')) + stat('Paid', n('paid')) + stat('Cancelled', n('cancelled')) + '</div>' +
    '<div class="grid g2"><div class="card"><h2>Recent Activity</h2>' + activity + '</div><div class="card"><h2>Order Status Overview</h2>' +
    donut(STATUSES.map((s) => ({ label: cap(s), value: n(s), color: COLORS[s] })), o.length) + '</div></div>';
}
function drawOrderList() {
  const f = view.ord, o = data.orders;
  const sel = (label, key, list) => '<label>' + label + '<select data-scope="ord" data-key="' + key + '">' + options(list, f[key], 'All') + '</select></label>';
  $('#ord-body').innerHTML = '<div class="grid g-side"><div class="card filters"><h2>Filters</h2>' +
    '<label>Search<input data-scope="ord" data-key="q" placeholder="Customer, phone or order #" value="' + esc(f.q) + '"></label>' +
    sel('Order Status', 'status', STATUSES.map((s) => [s, cap(s)])) + sel('Product', 'product', uniq(o.map((x) => x.items)).sort()) +
    '<button class="btn" data-action="clear-filters">Clear filters</button></div><div class="card" id="results"></div></div>';
  updateOrders();
}
function updateOrders() {
  const f = view.ord, q = f.q.trim().toLowerCase();
  const r = data.orders.filter((o) => (!f.status || o.status === f.status) && (!f.product || o.items === f.product) &&
    (!q || [o.customer, o.phone, o.items, '#' + o.id].some((s) => String(s).toLowerCase().includes(q))));
  const pages = Math.max(1, Math.ceil(r.length / ORD_PER_PAGE));
  f.page = Math.min(f.page, pages);
  const rows = r.slice((f.page - 1) * ORD_PER_PAGE, f.page * ORD_PER_PAGE).map((o) =>
    '<tr class="click" data-action="open-order" data-id="' + o.id + '"><td class="strong">#' + o.id + '</td><td>' + esc(o.customer) + '</td><td>' + esc(o.items) + '</td><td>' + (esc(o.size || '') || '—') + '</td><td>' + o.quantity + '</td><td>' + esc(o.date) + '</td><td>' + badge(cap(o.status)) + '</td><td>' + moneyOrDash(totalOf(o)) + '</td></tr>').join('');
  $('#results').innerHTML = (r.length ? table(['Order ID', 'Customer', 'Product', 'Size', 'Qty', 'Date', 'Status', 'Total'], rows) : empty('No orders match your filters.')) + pager(f.page, pages, 'ord-page');
}
function orderDialog(id) {
  const o = data.orders.find((x) => x.id === id); if (!o) return;
  openDialog('Order #' + o.id, '<dl class="dl"><dt>Customer</dt><dd>' + esc(o.customer) + '</dd><dt>Phone</dt><dd>' + (esc(o.phone) || '—') + '</dd>' +
    '<dt>Product</dt><dd>' + esc(o.items) + '</dd><dt>Size</dt><dd>' + (esc(o.size || '') || '—') + '</dd><dt>Quantity</dt><dd>' + o.quantity + '</dd><dt>Total</dt><dd>' + moneyOrDash(totalOf(o)) + '</dd><dt>Date</dt><dd>' + esc(o.date) + '</dd>' +
    '<dt>Status</dt><dd><select data-action="set-status" data-id="' + o.id + '" aria-label="Order status">' +
    STATUSES.map((s) => '<option value="' + s + '"' + (s === o.status ? ' selected' : '') + '>' + cap(s) + '</option>').join('') + '</select></dd></dl>' +
    '<p class="error-text" id="f-err" role="alert"></p><div class="actions" style="margin-top:16px"><button class="btn" data-action="delete-order" data-id="' + o.id + '">Delete order</button><button class="btn primary" data-action="close-dialog">Close</button></div>');
}
function orderForm() {
  if (!data.products.length) { openDialog('Add Order', empty('Add a product first, then you can create orders.')); return; }
  const prods = data.products.slice().sort((a, b) => a.name.localeCompare(b.name)).map((p) =>
    '<option value="' + esc(p.name) + '">' + esc(p.name) + (p.stock === 0 ? ' (out of stock)' : '') + '</option>').join('');
  openDialog('Add Order',
    '<div class="form"><label>Customer<input id="f-cust" maxlength="200" placeholder="Walk-in"></label><label>Phone<input id="f-phone" type="tel" maxlength="40"></label>' +
    '<label>Product<select id="f-prod">' + prods + '</select></label>' +
    '<div class="two"><label>Size<select id="f-size">' + options(SIZES, '', 'No size') + '</select></label>' +
    '<label>Quantity<input id="f-qty" type="number" min="1" max="10000" step="1" value="1"></label></div>' +
    '<p class="error-text" id="f-err" role="alert"></p><div class="actions"><button class="btn" data-action="close-dialog">Cancel</button><button class="btn primary" data-action="save-order">Save</button></div></div>');
}
async function saveOrder(btn) {
  const err = $('#f-err'), qtyS = $('#f-qty').value, quantity = Number(qtyS);
  const customer = $('#f-cust').value.trim() || 'Walk-in', phone = $('#f-phone').value.trim(), product_name = $('#f-prod').value, size = $('#f-size').value;
  if (!product_name) { err.textContent = 'Choose a product.'; return; }
  if (qtyS === '' || !Number.isInteger(quantity) || quantity < 1 || quantity > 10000) { err.textContent = 'Quantity must be a whole number from 1 to 10,000.'; return; }
  btn.disabled = true; btn.textContent = 'Saving…';
  try { await api.createOrder({ customer, phone, product_name, size, quantity }); closeDialog(); data.orders = await loadOrders(); ordersPage.draw(); }
  catch (e) { err.textContent = e.message; btn.disabled = false; btn.textContent = 'Save'; }
}

/* ===== 6. EVENTS (one listener per event type) ===== */
document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-action]'); if (!el) {
    if (e.target.id === 'overlay') closeDialog();   // click on dark background
    return;
  }
  const a = el.dataset.action, id = Number(el.dataset.id), page = Number(el.dataset.page);
  if (a === 'toggle-menu') { $('#sidebar').classList.toggle('open'); $('.backdrop').classList.toggle('show'); }
  else if (a === 'retry') route();
  else if (a === 'close-dialog') closeDialog();
  else if (a === 'add-product') productForm();
  else if (a === 'edit-product') productForm(data.products.find((p) => p.id === id));
  else if (a === 'save-product') saveProduct(el);
  else if (a === 'delete-product') {
    const p = data.products.find((x) => x.id === id);
    if (!confirm('Delete "' + p.name + '"?')) return;
    try { await api.deleteProduct(id); data.products = await loadProducts(); productsPage.draw(); } catch (err) { alert(err.message); }
  }
  else if (a === 'prod-page') { view.prod.page = page; updateProducts(); }
  else if (a === 'ord-page') { view.ord.page = page; updateOrders(); }
  else if (a === 'tab') { view.ord.tab = el.dataset.tab; ordersPage.draw(); }
  else if (a === 'clear-filters') { Object.assign(view.ord, { q: '', status: '', product: '', page: 1 }); drawOrderList(); }
  else if (a === 'open-order') orderDialog(id);
  else if (a === 'add-order') orderForm();
  else if (a === 'save-order') saveOrder(el);
  else if (a === 'delete-order') {
    if (!confirm('Delete order #' + id + '?')) return;
    try { await api.deleteOrder(id); closeDialog(); data.orders = await loadOrders(); ordersPage.draw(); }
    catch (err) { $('#f-err').textContent = err.message; }
  }
});

// Filters/search: update only the results area so the typing cursor is not lost.
document.addEventListener('input', (e) => {
  const el = e.target; if (!el.dataset.scope) return;
  view[el.dataset.scope][el.dataset.key] = el.value; view[el.dataset.scope].page = 1;
  el.dataset.scope === 'prod' ? updateProducts() : updateOrders();
});

document.addEventListener('change', async (e) => {
  const el = e.target; if (el.dataset.action !== 'set-status') return;
  const id = Number(el.dataset.id);
  try {
    await api.setOrderStatus(id, el.value);
    data.orders = await loadOrders();
    if (view.ord.tab === 'list') updateOrders(); else drawOrderSummary();
  } catch (err) { orderDialog(id); $('#f-err').textContent = err.message; }   // redraw the dialog so the dropdown shows the real status again
});

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDialog(); });

/* ===== 7. ROUTER (#/dashboard, #/products, #/orders) ===== */
const pages = { dashboard: dashboardPage, products: productsPage, orders: ordersPage };
let routeId = 0;
async function route() {
  let name = location.hash.replace('#/', '');
  if (!pages[name]) name = 'dashboard';
  document.querySelectorAll('.sidebar nav a').forEach((a) => a.classList.toggle('active', a.dataset.page === name));
  $('#sidebar').classList.remove('open'); $('.backdrop').classList.remove('show'); closeDialog();
  const id = ++routeId;
  $('#app').innerHTML = '<div class="state" role="status">Loading…</div>';
  try { await pages[name].load(); if (id === routeId) pages[name].draw(); }
  catch (err) { if (id === routeId) $('#app').innerHTML = '<div class="errbox" role="alert"><p>Something went wrong: ' + esc(err.message) + '</p><button data-action="retry">Try again</button></div>'; }
}
window.addEventListener('hashchange', route);
route();