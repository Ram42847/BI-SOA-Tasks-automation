# Weekly SOA Report — n8n Workflow Documentation

**Workflow file:** `n8n_workflow.json`  
**Total nodes:** 27 (including 1 Merge node)  
**Trigger:** Manual or Scheduled (every Sunday at 8:00 PM)  
**Output:** HTML email via Gmail + rows written to Google Sheets

## Cache persistence (fixed)

The rolling 4-week cache used to live in n8n's in-memory `$getWorkflowStaticData`,
seeded with 3 hardcoded historical weeks. Every time this workflow file got
regenerated/re-imported into n8n, that in-memory data reset to the hardcoded
seed, silently losing any week that had rolled past it — that's what caused the
"21 Jun - 27 Jun" column to render as all zeros (and cascade into a wrong current
week too).

The cache now lives in `weekly_data_cache.json` on disk — the **same file**
`report.py` already reads/writes — via two new `Read/Write Files from Disk`
nodes (`Read/Write File: Load Cache` / `Read/Write File: Save Cache`). This
survives workflow re-imports because the data no longer lives inside the
workflow object at all.

**Setup requirement:** n8n must be able to read/write
`/home/ramlal/mycode/open_project/soa-weekly-report/weekly_data_cache.json` on
disk. If self-hosted n8n has `N8N_RESTRICT_FILE_ACCESS_TO` set, add this
directory to that allow-list (n8n Cloud doesn't support disk access at all —
this workflow requires self-hosted n8n on the same host as this repo).

---

## Flow Overview

```
[Manual Trigger] ──┐
                   ├──→ [1] Code: Setup
[Schedule Trigger]─┘         │
                              │  (fans out — 8 HTTP calls + 1 cache-file read, all in parallel)
                    ┌─────────┴───────────────────────────────────────────────┐
                    ↓         ↓         ↓        ↓        ↓    ...   ↓        ↓
              [2] HTTP:  [3] HTTP:  [4] HTTP: [5] HTTP: [6] HTTP: [7] HTTP: [8] HTTP: [9] HTTP:  [10] Read/Write File:
              Merp       Merp       Bugs      Bugs      Dev       Todo      Tasks     Bugs            Load Cache
              Opened     Open End   Opened    Open End  Tasks     Tasks     Detail    Detail           │
                    │         │         │        │        │         │         │         │       [11] Code: Parse Cache
                    └─────────┴─────────┴────────┴────────┴─────────┴─────────┴─────────┴──────────────┘
                                              │
                                    [12] Merge (waits for all 9)
                                              │
                                   [13] Code: Build Report
                                              │
                    ┌───────────────────┬─────┴─────────────┬───────────────────┐
                    │                   │                   │                   │
              Tasks path           Bugs path          Email path         Cache-save path
                    │                   │                   │                   │
        [14] HTTP: Create   [18] HTTP: Create   [22] Code: Restore   [24] Code: Prepare
             Tasks Tab           Bugs Tab             Email                Cache File
                    │                   │                   │                   │
        [15] GSheets:         [19] GSheets:       [23] Send Email    [25] Read/Write File:
             Clear Tasks           Clear Bugs           via Gmail          Save Cache
                    │                   │
        [16] Code:            [20] Code:
             To Task Rows          To Bug Rows
                          │                   │
              [15] GSheets:         [19] GSheets:
                   Append Tasks          Append Bugs
```

---

## Why Parallel?

None of the 8 HTTP nodes need each other's output — they all independently read `authHeader` and their filter string from `Code: Setup`. Running them sequentially was just wasted wait time.

After `Code: Build Report`, the Tasks sheet operations, Bugs sheet operations, and email sending are completely independent — no data flows between them.

**Execution time improvement:** 8 sequential API calls (~8s) → 8 parallel API calls (~1s for the slowest one).

---

## Node-by-Node Details

---

### Node 1 — `Code: Setup`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Encodes API token as `Basic base64("apikey:<token>")` for the Authorization header
- Calculates the **most recently completed week** (Sunday to Saturday)
  - `weekStart (ws)` = last Sunday (e.g. `2026-06-22`)
  - `weekEnd (we)` = last Saturday (e.g. `2026-06-28`)
- Calculates `cutoff` = weekStart minus 365 days (year-lookback window start)
- Builds 8 filter JSON strings — one for each parallel API call

**Output (passed to all 8 HTTP nodes simultaneously):**

| Field | Example | Purpose |
|---|---|---|
| `authHeader` | `Basic YXBpa2V5...` | Authorization header for all HTTP nodes |
| `weekStart` | `2026-06-22` | Sunday of the report week |
| `weekEnd` | `2026-06-28` | Saturday of the report week |
| `merpOpenedFilter` | JSON string | Filter for Node 2 |
| `merpOpenEndFilter` | JSON string | Filter for Node 3 |
| `bugsOpenedFilter` | JSON string | Filter for Node 4 |
| `bugsOpenEndFilter` | JSON string | Filter for Node 5 |
| `devTasksFilter` | JSON string | Filter for Node 6 |
| `todoFilter` | JSON string | Filter for Node 7 |
| `tasksDetailFilter` | JSON string | Filter for Node 8 |
| `bugsDetailFilter` | JSON string | Filter for Node 9 |

---

### Nodes 2–9 — HTTP API Calls (run in parallel)

All 8 nodes fire simultaneously after Setup. Each reads `authHeader` and its own filter from `Code: Setup`. None of them need each other's output.

---

### Node 2 — `HTTP: Merp Opened`
**Purpose:** Non-bug tasks **created this week** → count = **B value** for Merp SOA Tasks

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Authorization: Basic <authHeader>
pageSize=1000  offset=1
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = all | Created this week | Type is not API Bug  
**Output → Merge (input 0)**

---

### Node 3 — `HTTP: Merp Open End`
**Purpose:** Non-bug tasks in **open status** within last 365 days → count = **total open tasks at end of week**

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
  { "status":    { "operator": "o",   "values": [] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = open (built-in group) | Created last 365 days | Type is not API Bug  
**Output → Merge (input 1)**

---

### Node 4 — `HTTP: Bugs Opened`
**Purpose:** Bug tickets **created this week** → count = **B value** for SOA Bugs

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
  { "type":      { "operator": "=",   "values": ["19"] } }
]
```
- Status = all | Created this week | Type is API Bug  
**Output → Merge (input 2)**

---

### Node 5 — `HTTP: Bugs Open End`
**Purpose:** Open bugs excluding STAGE → count = **total open bugs at end of week**

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
  { "status":       { "operator": "o",   "values": [] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```
- Status = open | Created last 365 days | Type is API Bug | Environment is not STAGE  
**Output → Merge (input 3)**

---

### Node 6 — `HTTP: Dev Tasks`
**Purpose:** All tickets **updated this week** within last year → used to build the **Developer Activity table**

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
  { "updatedAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } }
]
```
- Status = all | Created last 365 days | Updated this week | Type = all (no type filter)  
**Output → Merge (input 4)**

---

### Node 7 — `HTTP: Todo Tasks`
**Purpose:** Non-bug tasks with status **"To Do"** (ID=1) → count = **Backlog** metric

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
  { "status":    { "operator": "=",   "values": ["1"] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = exactly "To Do" (not the open group) | Created last 365 days | Type is not API Bug  
- `merpBacklog = todoEls.length` ; `merpWip = merpOpenEnd − merpBacklog`  
**Output → Merge (input 5)**

---

### Node 8 — `HTTP: Tasks Detail`
**Purpose:** Full records of non-bug tasks **updated this week** → rows for **`Tasks 22Jun-28Jun`** sheet tab

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
  { "updatedAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = all | Created last 365 days | Updated this week | Type is not API Bug  
**Output → Merge (input 6)**

---

### Node 9 — `HTTP: Bugs Detail`
**Purpose:** Full records of bug tickets **updated this week** → rows for **`Bugs 22Jun-28Jun`** sheet tab

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
  { "updatedAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
  { "type":      { "operator": "=",   "values": ["19"] } }
]
```
- Status = all | Created last 365 days | Updated this week | Type is API Bug  
**Output → Merge (input 7)**

---

### Node 10 — `Merge`
**Type:** Merge (mode: append)

**What it does:**
- Waits until **all 8 HTTP nodes + the cache-file read** have completed (each connects to a separate input index 0–8, `numberInputs: 9`)
- Combines all their output items into one batch
- Fires once to trigger `Code: Build Report`

**Why needed:** With 9 parallel branches, Build Report must not start until all of them have finished. The Merge node is the synchronisation point.

**Output → Code: Build Report**

---

### Node 11 — `Code: Build Report`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
Reads all 8 HTTP node responses (via `$('HTTP: ...')` references) and computes all report metrics.

**Metrics calculated:**

| Variable | Source | Calculation | Report Row |
|---|---|---|---|
| `merpB` | HTTP: Merp Opened | `.length` | Opened During this week (B) |
| `merpOpenEnd` | HTTP: Merp Open End | `.length` | Open: End of this week |
| `merpBacklog` | HTTP: Todo Tasks | `.length` | Backlog (Yet to align) |
| `merpWip` | — | `merpOpenEnd − merpBacklog` | Items in Under Development (WIP) |
| `bugsB` | HTTP: Bugs Opened | `.length` | Bug Opened During this week (B) |
| `bugsOpenEnd` | HTTP: Bugs Open End | `.length` | Bug Open: End of this week |
| `business` | HTTP: Merp Opened | count where type = Story (ID 15) | Business Tickets (B) |
| `internal` | — | `merpB − business` | Internally Opened Tickets (C) |

**Rolling 4-week cache** (persisted to `weekly_data_cache.json` on disk, read via `Code: Parse Cache` / written via `Code: Prepare Cache File` → `Read/Write File: Save Cache`):
- Key format: `"2026-06-22_2026-06-28"`
- Saves current week; reads prior 3 weeks to build the 4-column table
- Derives `merp_A` (open at week start) and calculates `merp_C` (closed = A + B − open_end)
- If the cache file is empty/missing (brand-new deployment), falls back to a one-time hardcoded seed of 3 historical weeks

**Developer table:** Groups HTTP: Dev Tasks results by Assignee + Accountable, deduplicates, sorts alphabetically.

**Sheet rows extracted:**
- `tasksRows[]` from HTTP: Tasks Detail — `{ ID, Subject, Type, Status, Author, Assignee, Accountable, "Updated on", "Created on", "Week Of" }`
- `bugsRows[]` from HTTP: Bugs Detail — same shape

**Output (fans out to 3 parallel paths simultaneously):**

| Field | Description |
|---|---|
| `html` | Complete HTML email body |
| `subject` | Email subject line |
| `tasksRows` | Array of task rows for Google Sheets |
| `bugsRows` | Array of bug rows for Google Sheets |

---

## Path A — Tasks Sheet (Nodes 12–15)

Runs in parallel with Path B and Path C after Build Report.

### Node 12 — `HTTP: Create Tasks Tab`
**Type:** HTTP Request (Google Sheets API) | `continueOnFail: true`

**Purpose:** Create a week-specific tasks tab (e.g. `Tasks 22Jun-28Jun`) in the Google Sheet. Each week gets its own tab. Silently skips if it already exists.

```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2
Body: (value of sheetBodyTasks from Build Report)
  e.g. {"requests":[{"addSheet":{"properties":{"title":"Tasks 22Jun-28Jun"}}}]}
```

**Note:** Tab name and request body are pre-built in `Code: Build Report` as `sheetBodyTasks` to avoid n8n expression issues with nested braces.

**Output → GSheets: Clear Tasks**

---

### Node 13 — `GSheets: Clear Tasks`
**Type:** Google Sheets (clear) | `continueOnFail: true`

**Purpose:** Wipe all rows in the current week's tasks tab before writing fresh data (safe to re-run).

**Sheet target:** Dynamic — `sheetTabTasks` from Build Report (e.g. `Tasks 22Jun-28Jun`)

**Output → Code: To Task Rows**

---

### Node 14 — `Code: To Task Rows`
**Type:** Code (JavaScript, runOnceForAllItems)

**Purpose:** Reads `tasksRows[]` from `Code: Build Report` and fans it out into N separate items (one per row). If empty → returns `[{ _noop: true }]` to keep chain alive.

**Output → GSheets: Append Tasks** (N items)

---

### Node 15 — `GSheets: Append Tasks`
**Type:** Google Sheets (append) | `continueOnFail: true`

**Purpose:** Appends N task rows to the current week's tasks tab. Each item = one row. Uses `autoMapInputData` — field names become column headers automatically.

**Sheet target:** Dynamic — `sheetTabTasks` (e.g. `Tasks 22Jun-28Jun`)

---

## Path B — Bugs Sheet (Nodes 16–19)

Runs in parallel with Path A and Path C after Build Report.

### Node 16 — `HTTP: Create Bugs Tab`
**Type:** HTTP Request (Google Sheets API) | `continueOnFail: true`

**Purpose:** Create a week-specific bugs tab (e.g. `Bugs 22Jun-28Jun`) in the Google Sheet.

```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2
Body: (value of sheetBodyBugs from Build Report)
  e.g. {"requests":[{"addSheet":{"properties":{"title":"Bugs 22Jun-28Jun"}}}]}
```

**Output → GSheets: Clear Bugs**

---

### Node 17 — `GSheets: Clear Bugs`
**Type:** Google Sheets (clear) | `continueOnFail: true`

**Purpose:** Wipe all rows in the current week's bugs tab before writing fresh data.

**Sheet target:** Dynamic — `sheetTabBugs` from Build Report (e.g. `Bugs 22Jun-28Jun`)

**Output → Code: To Bug Rows**

---

### Node 18 — `Code: To Bug Rows`
**Type:** Code (JavaScript, runOnceForAllItems)

**Purpose:** Reads `bugsRows[]` from `Code: Build Report` and fans it out into M items. If empty → `[{ _noop: true }]`.

**Output → GSheets: Append Bugs** (M items)

---

### Node 19 — `GSheets: Append Bugs`
**Type:** Google Sheets (append) | `continueOnFail: true`

**Purpose:** Appends M bug rows to the current week's bugs tab.

**Sheet target:** Dynamic — `sheetTabBugs` (e.g. `Bugs 22Jun-28Jun`)

---

## Path C — Email (Nodes 20–21)

Runs in parallel with Path A and Path B after Build Report. Does not wait for sheet writes.

### Node 20 — `Code: Restore Email`
**Type:** Code (JavaScript, runOnceForAllItems)

**Purpose:** Re-reads `html` and `subject` from `Code: Build Report` and returns exactly 1 item for Gmail.

**Output → Send Email via Gmail**
```json
{ "html": "<!DOCTYPE html>...", "subject": "BI Weekly Report : BI SOA Task Status Report : 22 Jun - 28 Jun 2026" }
```

---

### Node 21 — `Send Email via Gmail`
**Type:** Gmail (send)

- **To:** `bireports@indiamart.com`
- **CC:** `puneet.agarwal@indiamart.com`, `vipul.bansal1@indiamart.com`
- **Subject:** `={{ $json.subject }}`
- **Body (HTML):** `={{ $json.html }}`

**End of workflow.**

---

## API Filter Quick Reference

| Node | Status | Created On | Updated On | Type | Environment |
|---|---|---|---|---|---|
| Merp Opened | all | this week | — | is not Bug | — |
| Merp Open End | **open** | last 365 days | — | is not Bug | — |
| Bugs Opened | all | this week | — | is Bug | — |
| Bugs Open End | **open** | last 365 days | — | is Bug | is not STAGE |
| Dev Tasks | all | last 365 days | this week | — (all types) | — |
| Todo Tasks | **= To Do** | last 365 days | — | is not Bug | — |
| Tasks Detail | all | last 365 days | this week | is not Bug | — |
| Bugs Detail | all | last 365 days | this week | is Bug | — |

---

## Constants Reference

| Constant | Value | Meaning |
|---|---|---|
| `PROJECT_ID` | `75` | MERP Services OpenProject project ID |
| `API_BUG_TYPE_ID` | `19` | Work package type ID for "API Bug" |
| `API_STORY_TYPE_ID` | `15` | Work package type ID for "Story" (business tickets) |
| `ENV_STAGE_OPTION_ID` | `22` | customField9 (Environment) option for "STAGE" |
| `TODO_STATUS_ID` | `1` | Status ID for "To Do" |
| `YEAR_LOOKBACK_DAYS` | `365` | Year-lookback window length |
| `operator: 'o'` | built-in | OpenProject "Status is open" group |
| `operator: '<>d'` | built-in | OpenProject "between dates" |
| `operator: '!'` | built-in | OpenProject "is not" |
| `operator: '='` | built-in | OpenProject "is" (exact match) |

---

## Cache Structure

Stored in `weekly_data_cache.json` on disk (the same file `report.py` uses) —
**not** in n8n's workflow static data, which resets on every re-import/redeploy.

```json
{
  "2026-06-08_2026-06-14": {
    "merp_B": 20, "merp_C": 21, "merp_open": 123,
    "merp_wip": 101, "merp_backlog": 22,
    "bugs_B": 9, "bugs_C": 13, "bugs_open": 12,
    "biz_opened": 10, "int_opened": 10,
    "dev_tasks": { "John Smith": [{ "id": 1234, "subject": "Fix login bug" }] }
  }
}
```

Every run reads the file (`Read/Write File: Load Cache` → `Code: Parse Cache`),
adds/overwrites the current week's key, and writes the whole thing back
(`Code: Prepare Cache File` → `Read/Write File: Save Cache`). Old weeks are
never deleted, so the file grows slowly over time — the report itself only
ever displays the 4 most recent weeks.
