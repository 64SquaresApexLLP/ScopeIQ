# ScopeIQ mobile app

This is an Expo (SDK 57) React Native app in TypeScript, using Expo Router. One codebase runs on iOS, Android and the web.

```
npm install
npm run web          # browser
npx expo start       # QR code for Expo Go on a phone
npm run typecheck
```

The environment is chosen outside the code. `APP_ENV=dev|test|prod` selects `config/<env>.json` (API address, log level,
remote log level, network logging, environment banner), and `SCOPEIQ_API_URL` overrides the API address. On a phone,
use your PC's LAN IP, for example `SCOPEIQ_API_URL=http://192.168.1.20:8000`, and start the API with `--host 0.0.0.0`.

| Path | What |
|---|---|
| `src/app/login.tsx` | mock login: pick a persona |
| `src/app/(tabs)/` | dashboard, sites, work queue (per persona), inbox, more |
| `src/app/site/[id].tsx` | site workbench: overview and workflow, discrepancies, delta, BOM, redlines and RFIs, drivers and estimate, drone evidence, documents |
| `src/app/discrepancy/[id].tsx` | expected vs found, governing source, evidence, actions with reason codes, comments, history |
| `src/app/bom/[revId].tsx` | lines by sector with rule traceability, edits (DRAFT only, reason-coded), changes vs REV 0, approvals, Excel export |
| `src/app/upload/[siteId].tsx` | optional artifact upload (CD, RFDS, MA/SA, REV 0, drone files) |
| `src/app/audit.tsx`, `reference.tsx`, `logs.tsx` | audit trail, reference data, logs and configuration (admin) |
| `src/components/WorkflowActions.tsx` | reusable action bar: the server decides which actions each role has; prompts for a reason and comment |
| `src/lib/logger.ts` | reusable logger: console level per environment, warnings and errors forwarded to the API |
| `src/lib/api.ts` | API client: bearer token, correlation id per request, one `ApiError` type |
