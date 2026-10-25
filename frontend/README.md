# Clutch frontend

The React + Vite app for Clutch. See the [main README](../README.md) for what Clutch does,
the system requirements and setup, and [`docs/database.md`](../docs/database.md#frontend-files)
for what each file in `src/` does.

```bash
npm install        # Node.js 20.19+ or 22.13+ (24 LTS recommended)
npm run dev        # http://localhost:5173 (needs the Flask backend on port 5001)
npm run lint
npm run build      # production build in dist/
```

The dev server sends `/api/*` requests to Flask at http://127.0.0.1:5001 (see `vite.config.js`).
