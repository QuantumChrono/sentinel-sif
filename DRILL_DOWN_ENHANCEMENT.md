# Drill-Down Enhancement: Show Full Report Context with Precursor Highlighting

## Problem

The initial drill-down modal showed only a list of reports but **did not display the original report text** or **highlighted precursor entities** that explain **why** each report is marked as SIF (Serious-Injury-and-Fatality) potential.

Users clicking a density ranking row couldn't see:
- The actual incident narrative
- Which precursor spans (activity, agent, barrier failure, location) were extracted
- The colored entity highlighting that shows why the classification was made
- The IOGP rule tags that were assigned

## Solution

Changed the drill-down modal to display **full `ReportDetail`** objects (including `cleaned_text` and `precursors`) instead of just `ReportSummary` stubs. This reuses the existing `ReportResult` component, which already renders:
- Verdict badge (SIF potential yes/no + confidence %)
- IOGP Life-Saving Rule tags
- **Highlighted report text** with colored entity spans
- Precursor legend showing all four entity types

## Changes Made

### 1. Backend: `backend/routes/reports.py`

**Changed:** The `GET /api/v1/reports` endpoint now returns `list[ReportDetail]` instead of `list[ReportSummary]`.

**Why:** `ReportDetail` extends `ReportSummary` and adds:
- `cleaned_text: string` — the preprocessed narrative (used for span indexing)
- `precursors: PrecursorOut[]` — the extracted entity spans with types and offsets

**Implementation:**
```python
@router.get("", response_model=list[ReportDetail])  # Changed from list[ReportSummary]
def list_reports(...) -> list[ReportDetail]:
    # ... filtering logic unchanged ...
    rows = query.order("submitted_at", desc=True).limit(limit).execute().data or []
    return [_detail(row) for row in rows]  # Use _detail() helper instead of ReportSummary()
```

The `_detail()` helper already existed (used by the single-report endpoint), so this is a **reuse of existing logic**, not new code.

### 2. Frontend API Client: `frontend/lib/api_client.ts`

**Changed:** The `listReports()` function return type from `ReportSummary[]` to `ReportDetail[]`.

**Implementation:**
```typescript
function listReports(filters: ReportFilters = {}): Promise<ApiResult<ReportDetail[]>> {
  // ... URL construction unchanged ...
  return request<ReportDetail[]>(`/api/v1/reports${suffix ? `?${suffix}` : ""}`);
}
```

### 3. Frontend Modal: `frontend/app/dashboard/drill_down_modal.tsx`

**Changed:** Simplified the modal to pass `ReportDetail` objects directly to the `ReportResult` component.

**Before:**
```typescript
// Manually constructing a partial ReportDetail with precursors=[]
ReportResult report={{
  id: summary.id,
  site: summary.site,
  raw_text: summary.raw_text,
  cleaned_text: "",  // EMPTY - no highlighting possible
  // ... other fields ...
  precursors: [],    // EMPTY - no entity spans
}}
```

**After:**
```typescript
// Pass the full ReportDetail from the API
ReportResult report={report}
```

## What Users Will See Now

### Before (drill-down showed):
❌ Report ID and site name  
❌ A few metadata fields  
❌ No text content  
❌ No entity highlighting  
❌ No context for the SIF verdict  

### After (drill-down shows):
✅ **Verdict card** — SIF yes/no + confidence %  
✅ **IOGP rule tags** — which Life-Saving Rules were triggered (e.g., Energy Isolation, Line of Fire)  
✅ **Full report text** with **colored entity highlighting**:
   - 🔴 Red underlines = Activity (what was the worker doing?)
   - 🟡 Yellow underlines = Agent (what tool/object was involved?)
   - 🟠 Orange underlines = Barrier failure (what safety control failed?)
   - 🟢 Green underlines = Location (where did it happen?)  
✅ **Precursor legend** — lists all extracted entities by type

### Example

**Incident:** "A worker was welding on a platform 12 feet high. He fell through a gap in the guard rail."

**Drill-down now shows:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VERDICT
SIF potential   Confidence 89.2%   model interim-keyword-0.1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IOGP LIFE-SAVING RULES
Working at Height 84%   Energy Isolation 65%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REPORT TEXT WITH PRECURSORS
A worker was 🔴welding🔴 on a 🟢platform 12 feet high🟢.
He fell through a gap in the 🟠guard rail🟠.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRECURSOR ENTITIES
Activity:         welding
Agent:            (none in this report)
Barrier failure:  guard rail
Location:         platform
```

## Data Flow

```
User clicks density row
       ↓
density_table.tsx setSelectedRow(rowData)
       ↓
<DrillDownModal groupId={rowData.group_id} groupName={rowData.group_name} />
       ↓
DrillDownModal calls listReports({ site_id: groupId, limit: 200 })
       ↓
GET /api/v1/reports?site_id=<uuid> (backend uses _detail() helper)
       ↓
Backend returns ReportDetail[] with precursors and cleaned_text
       ↓
Frontend maps over reports:
  report => <ReportResult report={report} />
       ↓
ReportResult renders:
  - Verdict card
  - IOGP rule tags
  - buildReportSegments(cleaned_text, precursors)
  - Colored entity highlighting
```

## Backwards Compatibility

✅ **No breaking changes** — the API response shape is **extended**, not changed:
- Old clients that ignored `cleaned_text` and `precursors` still work
- The endpoint still accepts all the same filter parameters
- Existing code that calls `GET /api/v1/reports` without these fields runs unchanged

## Testing

1. **Backend self-check:** `python analytics/density.py` — verify no changes to ranking
2. **TypeScript:** `npx tsc --noEmit` — verify modal and api_client changes compile
3. **Live test:** Log in, click a density row, verify:
   - Modal opens and shows "Loading reports…"
   - Reports appear with colored entity highlighting
   - IOGP tags visible
   - Precursor legend shows all 4 entity types
   - Modal dismisses on close/backdrop click

## Files Modified

| File | Change | Reason |
|------|--------|--------|
| `backend/routes/reports.py` | Return `ReportDetail[]` instead of `ReportSummary[]` | Include precursors and cleaned_text |
| `frontend/lib/api_client.ts` | Update `listReports()` return type | Match backend response |
| `frontend/app/dashboard/drill_down_modal.tsx` | Pass full `ReportDetail` to `ReportResult` | Remove manual object construction |

## Decision Log

**Decision:** Include full report details in the drill-down modal instead of showing only metadata.

**Context:** Users couldn't understand why a report was classified as SIF potential without seeing the incident narrative and entity highlighting.

**Alternatives:**
1. Fetch each report individually via `GET /api/v1/reports/{id}` after listing (adds latency per report)
2. Keep showing only summary data (incomplete feature)

**Rationale:** The backend already had `cleaned_text` and `precursors` in the response template; we just needed to include them in the list endpoint. This reuses the proven `_detail()` helper and the existing `ReportResult` renderer, so the modal now shows the same rich context as the full report detail page.
