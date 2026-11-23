ACMS Admin - plain HTML/CSS/JavaScript. No install needed.
Double-click index.html to open it.

index.html  = page structure (sidebar, empty <main>, dialog)
styles.css  = all styling
scripts.js  = all logic. Sections: config, MOCK DATA, API layer, helpers, pages, events, router.

Backend: app/api/dashboardapi.py (FastAPI, routes under /api).
  - Start the backend (default http://localhost:8000), then open index.html.
  - API address is API_URL at the top of scripts.js. USE_MOCK = true runs with fake data instead.
  - The backend must allow CORS if you open index.html as a file (see CORSMiddleware in FastAPI docs).
Dashboard numbers (sales, trend, best sellers, low stock) are calculated in the browser from /api/products and /api/orders.
