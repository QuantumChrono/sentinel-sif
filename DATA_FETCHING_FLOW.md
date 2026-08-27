# Frontend Data Fetching Flow

Complete trace of where data is fetched, how it flows through components, and where it's rendered.

---

## Overview: Dashboard Page Data Fetching

```
DashboardPage (app/dashboard/page.tsx)
    ↓
    useEffect() → Promise.all() [parallel fetches]
    ├─ getDensity() → GET /api/v1/analytics/density
    ├─ getRuleDistribution() → GET /api/v1/analytics/rules
    ├─ getReviewQueue() → GET /api/v1/analytics/review-queue
    └─ listReports() → GET /api/v1/reports?sif_potential=true&limit=10
    ↓
    [DashboardData state]
    ├─ DensityTable (renders density.by_site + density.by_activity)
    ├─ KpiCards (sums from density)
    ├─ RuleDistributionChart (renders rules)
    └─ HighRiskFeed (renders highRisk reports)
```

---

## 1. Initial Dashboard Load

### File: `frontend/app/dashboard/page.tsx` (lines 37-63)

```typescript
export default function DashboardPage() {
  const [load, setLoad] = useState<Load>({ name: "loading" });

  useEffect(() => {
    // Four parallel HTTP calls
    Promise.all([
      getDensity(),                                    // ← #1
      getRuleDistribution(),                           // ← #2
      getReviewQueue(QUEUE_LIMIT),                     // ← #3
      listReports({ sif_potential: true, limit: FEED_LIMIT }), // ← #4
    ]).then(([density, rules, queue, highRisk]) => {
      // All 4 responses combined into DashboardData
      setLoad({
        name: "loaded",
        data: { 
          density: density.data,      // Used by DensityTable
          rules: rules.data,          // Used by RuleDistributionChart
          queue: queue.data,          // Used by KpiCards
          highRisk: highRisk.data,    // Used by HighRiskFeed
        },
      });
    });
  }, []);
}
```

### The Four Fetches

| # | Function | Endpoint | Purpose | Response Type |
|---|----------|----------|---------|---------------|
| 1 | `getDensity()` | `GET /api/v1/analytics/density` | Density rankings by site & activity | `DensityResponse` |
| 2 | `getRuleDistribution()` | `GET /api/v1/analytics/rules` | IOGP rule distribution (9 rules) | `RuleCount[]` |
| 3 | `getReviewQueue()` | `GET /api/v1/analytics/review-queue` | Low-confidence reports waiting for review | `ReviewQueueRow[]` |
| 4 | `listReports()` | `GET /api/v1/reports?sif_potential=true&limit=10` | 10 most recent SIF-potential reports | `ReportDetail[]` |

---

## 2. Rendering the Density Table & Drill-Down

### File: `frontend/app/dashboard/page.tsx` (lines 155-175)

```typescript
<DensityTable
  rows={density.by_site}           // ← Data from getDensity() call
  groupLabel="Site"
  showRegion
  emptyMessage="..."
/>
```

Data passed to DensityTable:
- `rows` = array of `DensityRow` objects (each has `group_name`, `group_id`, `total_reports`, `sif_reports`, `rank_score`, etc.)

### File: `frontend/app/dashboard/density_table.tsx`

```typescript
export function DensityTable({ rows, groupLabel, ... }: DensityTableProps) {
  const [selectedRow, setSelectedRow] = useState<DensityRow | null>(null);

  return (
    <>
      <table>
        <tbody>
          {rows.map((row) => (
            <tr 
              key={row.group_name}
              onClick={() => setSelectedRow(row)}  // ← Click opens drill-down
              className="cursor-pointer hover:bg-slate-50"
            >
              <td>{row.group_name}</td>
              <td>{row.total_reports}</td>
              <td>{row.sif_reports}</td>
              <td>{(row.density * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>

      {selectedRow && (
        <DrillDownModal
          groupType="site"
          groupName={selectedRow.group_name}
          groupId={selectedRow.group_id}  // ← Passed to modal
          onClose={() => setSelectedRow(null)}
        />
      )}
    </>
  );
}
```

---

## 3. Drill-Down Modal Data Fetching

### File: `frontend/app/dashboard/drill_down_modal.tsx` (lines 30-59)

```typescript
export function DrillDownModal({
  groupType,      // "site" or "activity"
  groupName,      // "Ramgarh" or "welding"
  groupId,        // UUID for the site (e.g., "8ab...")
  onClose,
}) {
  const [load, setLoad] = useState<Load>({ name: "loading" });

  useEffect(() => {
    (async () => {
      try {
        // Build filter query based on groupType
        const filters =
          groupType === "site" && groupId
            ? { site_id: groupId, limit: 200 }      // ← Fetch by site UUID
            : groupType === "activity"
              ? { activity: groupName, limit: 200 }  // ← Fetch by activity verb
              : {};

        // ← THIS IS WHERE THE FETCH HAPPENS
        const result = await listReports(filters);
        
        if (!result.ok) {
          setLoad({ name: "failed", error: result.error });
        } else {
          setLoad({ name: "loaded", reports: result.data });
        }
      } catch (error) {
        setLoad({ name: "failed", error: { ... } });
      }
    })();
  }, [groupType, groupName, groupId]);
}
```

### The Drill-Down Fetch

```
User clicks "Ramgarh" row in density table
    ↓
DensityTable: setSelectedRow({ group_name: "Ramgarh", group_id: "8ab...", ... })
    ↓
DrillDownModal opens with props:
    groupType = "site"
    groupName = "Ramgarh"
    groupId = "8ab..."
    ↓
useEffect runs:
    listReports({ site_id: "8ab...", limit: 200 })
    ↓
GET /api/v1/reports?site_id=8ab...&limit=200
    ↓
Backend returns ReportDetail[] (with cleaned_text + precursors)
    ↓
Modal renders ReportResult for each report
    ↓
User sees colored entity highlighting and verdict badge
```

---

## 4. The HTTP Request Path (api_client.ts)

### File: `frontend/lib/api_client.ts` (lines 268-280)

```typescript
/**
 * BASE_URL is defined as:
 * const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8001";
 * 
 * So in production: https://api.sentinel-sif.com
 * Locally: http://127.0.0.1:8001
 */

function listReports(filters: ReportFilters = {}): Promise<ApiResult<ReportDetail[]>> {
  const query = new URLSearchParams();
  
  // Convert filter object to query string
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) query.set(key, String(value));
  }
  
  const suffix = query.toString();
  
  // Final URL: /api/v1/reports?site_id=8ab...&limit=200
  return request<ReportDetail[]>(
    `/api/v1/reports${suffix ? `?${suffix}` : ""}`
  );
}
```

### The `request()` function (lines 170-225)

```typescript
async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  // ← Line 208: Actual HTTP fetch
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    signal: AbortSignal.timeout(TIMEOUT_MS),  // 30 second timeout
    cache: "no-store",                        // Never cache API responses
  });

  // Parse response
  const body: unknown = await response.json().catch(() => null);

  if (response.ok) {
    return { ok: true, data: body as T };  // ← Success
  } else {
    return { ok: false, error: { ... } };   // ← Error with details
  }
}
```

---

## 5. Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ DashboardPage (app/dashboard/page.tsx)                              │
│                                                                     │
│  useEffect() → Promise.all(4 parallel fetches)                     │
│  ├─ getDensity()                 ─→ /api/v1/analytics/density      │
│  ├─ getRuleDistribution()        ─→ /api/v1/analytics/rules        │
│  ├─ getReviewQueue()             ─→ /api/v1/analytics/review-queue │
│  └─ listReports({...})           ─→ /api/v1/reports?...            │
│                                                                     │
│  ↓ (all responses collected)                                       │
│                                                                     │
│  setLoad({ name: "loaded", data: DashboardData })                  │
└─────────────────────────────────────────────────────────────────────┘
          ↓
          ├─────────────────────────────────────────┐
          ↓                                         ↓
    ┌─────────────────┐                  ┌──────────────────┐
    │ DensityTable    │                  │ KpiCards         │
    │ density.by_site │                  │ density.by_site  │
    │ density.by_act  │                  │ queue.length     │
    └─────────────────┘                  └──────────────────┘
          ↓ (on row click)
    ┌─────────────────────────────────────┐
    │ DrillDownModal                      │
    │                                     │
    │  useEffect() runs when:            │
    │  - groupType = "site"              │
    │  - groupName = "Ramgarh"           │
    │  - groupId = "8ab..."              │
    │                                     │
    │  ↓                                  │
    │  listReports({site_id: groupId})   │
    │  ↓                                  │
    │  GET /api/v1/reports?site_id=8ab...│
    │  ↓                                  │
    │  ReportDetail[] (with precursors)  │
    │  ↓                                  │
    │  map over reports:                 │
    │    ReportResult (colored text)     │
    └─────────────────────────────────────┘
```

---

## 6. Key Files & Their Roles

| File | Lines | Role |
|------|-------|------|
| `frontend/app/dashboard/page.tsx` | 37-63 | Initial dashboard data fetching (Promise.all) |
| `frontend/app/dashboard/density_table.tsx` | 20-50 | Display table & track selectedRow state |
| `frontend/app/dashboard/drill_down_modal.tsx` | 30-59 | Drill-down fetching via useEffect |
| `frontend/lib/api_client.ts` | 268-280 | `listReports()` function |
| `frontend/lib/api_client.ts` | 170-225 | `request()` - actual HTTP fetch |
| `frontend/app/report_result.tsx` | - | Render individual ReportDetail |

---

## 7. Environment Variables (Where BASE_URL Comes From)

### File: `frontend/lib/api_client.ts` (line 20)

```typescript
const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8001";
```

### Local Development
```
NEXT_PUBLIC_API_BASE_URL = http://127.0.0.1:8001
```

### Production (Vercel)
```
NEXT_PUBLIC_API_BASE_URL = https://api.sentinel-sif.com  (or the real Render URL)
```

---

## 8. Response Types (What Gets Returned)

### DensityRow (from getDensity)
```typescript
{
  group_name: "Ramgarh",
  group_id: "8ab...",           // UUID for drill-down
  site_id: "8ab...",            // Same as group_id for sites
  total_reports: 8,
  sif_reports: 4,
  rank_score: 0.2152,           // Wilson lower bound
  activity: null,               // null for site rows
  density: 0.5
}
```

### ReportDetail (from listReports in drill-down modal)
```typescript
{
  id: "report-uuid",
  site: { id: "8ab...", name: "Ramgarh", ... },
  raw_text: "Worker was welding...",
  cleaned_text: "Worker was welding...",  // Preprocessed
  language_detected: "en",
  reporter_role: "hse_manager",
  submitted_at: "2026-08-26T10:15:00Z",
  status: "processed",
  classification: {
    sif_potential: true,
    confidence: 0.89,
    model_version: "interim-keyword-0.1",
    review_status: "auto",
    reviewed_by: null
  },
  iogp_tags: [
    { rule_name: "Energy Isolation", confidence: 0.75 },
    { rule_name: "Working at Height", confidence: 0.84 }
  ],
  precursors: [
    { entity_type: "activity", entity_text: "welding", span_start: 10, span_end: 17 },
    { entity_type: "location", entity_text: "platform", span_start: 21, span_end: 29 }
  ]
}
```

---

## Summary

**Where data is fetched:**
1. **Dashboard page** → `getDensity()` (initial load)
2. **User clicks density row** → Modal opens
3. **Modal useEffect** → `listReports()` (drill-down fetch)
4. **Both use** → `request()` function in `api_client.ts`
5. **Both make HTTP calls** → `fetch()` with `BASE_URL` + path + query params
6. **Backend** → Returns typed response (`DensityResponse`, `ReportDetail[]`)
7. **Frontend** → Renders in components (`DensityTable`, `ReportResult`)

**The flow is unidirectional:** data flows DOWN from api_client.ts → components, never up (no direct setState calls from api_client).
