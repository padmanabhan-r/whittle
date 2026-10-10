# Whittle web UI

Vite, React and TypeScript. Two surfaces: the landing page at `/` and the app
at `/app`. It talks to the backend in `../api` as set out in
`../docs/api-contract.md`.

```bash
../start.sh          # API and UI together, from the repo root
npm run dev          # UI only; set VITE_API_URL if the API is not on :8787
npm run build        # type-check and build
npm run lint
```

Types in `src/lib/api.ts` mirror `api/costcutter/contract.py`. Change them
together.
