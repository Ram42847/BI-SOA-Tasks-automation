# Monthly SOA Report — n8n Workflow Documentation

**Workflow file:** `n8n_monthly_workflow.json`  
**Total nodes:** 26 (including 1 Merge node)  
**Trigger:** Manual or Scheduled (1st of every month at 8:00 PM)  
**Output:** HTML email via Gmail + rows written to Google Sheets (dynamic tab per month)

## Cache persistence (fixed)

The rolling 4-month cache used to live in n8n's in-memory `$getWorkflowStaticData`,
seeded with 3 hardcoded historical months. Every time this workflow file got
regenerated/re-imported into n8n, that in-memory data reset to the hardcoded
seed, silently losing any month that had rolled past it — the same bug fixed in
the weekly report workflow, just on a monthly cadence.

The cache now lives in `monthly_data_cache.json` on disk via two new
`Read/Write Files from Disk` nodes (`Read/Write File: Load Cache (M)` /
`Read/Write File: Save Cache (M)`). This survives workflow re-imports because
the data no longer lives inside the workflow object at all.

**Setup requirement:** n8n must be able to read/write
`/home/ramlal/mycode/open_project/soa-weekly-report/monthly_data_cache.json` on
disk. If self-hosted n8n has `N8N_RESTRICT_FILE_ACCESS_TO` set, add this
directory to that allow-list (n8n Cloud doesn't support disk access at all —
this workflow requires self-hosted n8n on the same host as this repo).

---

## Flow Overview

```
[Manual Trigger] ──┐
                   ├──→ [1] Code: Setup Monthly
[Schedule Trigger]─┘         │
                              │  (fans out — 7 HTTP calls + 1 cache-file read, all in parallel)
                    ┌─────────┴──────────────────────────────────────────┐
                    ↓         ↓         ↓        ↓        ↓    ↓    ↓    ↓
              [2] HTTP:  [3] HTTP:  [4] HTTP: [5] HTTP: [6] HTTP: [7] HTTP: [8] HTTP: [9] Read/Write File:
              Merp       Merp       Bugs      Bugs      Todo      Tasks     Bugs          Load Cache (M)
              Opened     Open End   Opened    Open End  Tasks(M)  Detail    Detail          │
                    │         │         │        │        │         │         │       [10] Code: Parse Cache (M)
                    └─────────┴─────────┴────────┴────────┴─────────┴─────────┴──────────────┘
                                              │
                                   [11] Merge (waits for all 8)
                                              │
                              [12] Code: Build Report Monthly
                                              │
                    ┌───────────────────┬─────┴─────────────┬───────────────────┐
                    │                   │                   │                   │
              Tasks path           Bugs path          Email path         Cache-save path
                    │                   │                   │                   │
        [13] HTTP: Create     [17] HTTP: Create   [21] Code: Restore   [23] Code: Prepare
             Tasks Tab             Bugs Tab             Email (M)            Cache File (M)
                    │                   │                   │                   │
        [14] GSheets:         [18] GSheets:       [22] Send Email    [24] Read/Write File:
             Clear Tasks(M)        Clear Bugs(M)        via Gmail          Save Cache (M)
                    │                   │
        [15] Code:            [19] Code:
             To Task Rows(M)       To Bug Rows(M)
                          │                   │
              [14] GSheets:         [18] GSheets:
                   Append Tasks(M)       Append Bugs(M)
```

---

## Why Parallel?

None of the 7 HTTP nodes need each other's output — they all independently read `authHeader` and their own filter from `Code: Setup Monthly`. Running them sequentially was wasted wait time.

After `Code: Build Report Monthly`, the Tasks sheet operations, Bugs sheet operations, and email sending are completely independent — no data flows between these three paths.

**Execution time improvement:** 7 sequential API calls (~7s) → 7 parallel API calls (~1s for the slowest one).

---

## Node-by-Node Details

---

### Node 1 — `Code: Setup Monthly`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Encodes API token as `Basic base64("apikey:<token>")` for the Authorization header
- Calculates the **most recently completed calendar month**
  - `monthStart (ms)` = 1st of previous month (e.g. `2026-06-01`)
  - `monthEnd (me)` = last day of previous month (e.g. `2026-06-30`)
- Calculates `cutoff` = monthStart minus 365 days (year-lookback start, e.g. `2025-06-01`)
- Builds 7 filter JSON strings — one for each parallel API call

**Output (passed to all 7 HTTP nodes simultaneously):**

| Field | Example | Purpose |
|---|---|---|
| `authHeader` | `Basic YXBpa2V5...` | Authorization header for all HTTP nodes |
| `monthStart` | `2026-06-01` | First day of the report month |
| `monthEnd` | `2026-06-30` | Last day of the report month |
| `merpOpenedFilter` | JSON string | Filter for Node 2 |
| `merpOpenEndFilter` | JSON string | Filter for Node 3 |
| `bugsOpenedFilter` | JSON string | Filter for Node 4 |
| `bugsOpenEndFilter` | JSON string | Filter for Node 5 |
| `todoFilter` | JSON string | Filter for Node 6 |
| `tasksDetailFilter` | JSON string | Filter for Node 7 |
| `bugsDetailFilter` | JSON string | Filter for Node 8 |

---

### Nodes 2–8 — HTTP API Calls (run in parallel)

All 7 nodes fire simultaneously after Setup Monthly. Each reads `authHeader` and its own filter from `Code: Setup Monthly`. None need each other's output.

---

### Node 2 — `HTTP: Merp Opened`
**Purpose:** Non-bug tasks **created this month** → count = **B value** for Merp SOA Tasks

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Authorization: Basic <authHeader>
pageSize=1000  offset=1
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = all | Created this month | Type is not API Bug  
**Output → Merge (input 0)**

---

### Node 3 — `HTTP: Merp Open End`
**Purpose:** Non-bug tasks in **open status** within last 365 days → count = **total open tasks at end of month**

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
  { "status":    { "operator": "o",   "values": [] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = open (built-in group) | Created last 365 days | Type is not API Bug  
**Output → Merge (input 1)**

---

### Node 4 — `HTTP: Bugs Opened`
**Purpose:** Bug tickets **created this month**, excluding STAGE → count = **B value** for SOA Bugs

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```
- Status = all | Created this month | Type is API Bug | Environment is not STAGE  
**Output → Merge (input 2)**

---

### Node 5 — `HTTP: Bugs Open End`
**Purpose:** Open bugs excluding STAGE within last 365 days → count = **total open bugs at end of month**

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
  { "status":       { "operator": "o",   "values": [] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```
- Status = open | Created last 365 days | Type is API Bug | Environment is not STAGE  
**Output → Merge (input 3)**

---

### Node 6 — `HTTP: Todo Tasks (M)`
**Purpose:** Non-bug tasks with status exactly **"To Do"** (ID=1) → count = **Backlog** metric

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
  { "status":    { "operator": "=",   "values": ["1"] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = exactly "To Do" | Created last 365 days | Type is not API Bug  
- `merpBacklog = todoEls.length` ; `merpWip = merpOpenEnd − merpBacklog`  
**Output → Merge (input 4)**

---

### Node 7 — `HTTP: Tasks Detail`
**Purpose:** Full records of non-bug tasks **updated this month** → rows for **`Tasks Jun2026`** sheet

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
  { "updatedAt": { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```
- Status = all | Created last 365 days | Updated this month | Type is not API Bug  
**Output → Merge (input 5)**

---

### Node 8 — `HTTP: Bugs Detail`
**Purpose:** Full records of bug tickets **updated this month**, excluding STAGE → rows for **`Bugs Jun2026`** sheet

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
filters = [
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
  { "updatedAt":    { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```
- Status = all | Created last 365 days | Updated this month | Type is API Bug | Environment is not STAGE  
**Output → Merge (input 6)**

---

### Node 11 — `Merge`
**Type:** Merge (mode: append)

**What it does:**
- Waits until **all 7 HTTP nodes + the cache-file read** have completed (each connects to a separate input index 0–7, `numberInputs: 8`)
- Combines all their output items into one batch
- Fires once to trigger `Code: Build Report Monthly`

**Why needed:** With 7 parallel HTTP calls plus the disk cache read, Build Report must not start until all 8 have finished. The Merge node is the synchronisation point.

**Output → Code: Build Report Monthly**

---

### Node 12 — `Code: Build Report Monthly`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
Reads all 7 HTTP node responses (via `$('HTTP: ...')` references) and computes all report metrics.

**Metrics calculated:**

| Variable | Source | Calculation | Report Row |
|---|---|---|---|
| `merpB` | HTTP: Merp Opened | `.length` | Opened During this month (B) |
| `merpOpenEnd` | HTTP: Merp Open End | `.length` | Open: End of this month |
| `merpBacklog` | HTTP: Todo Tasks (M) | `.length` | Backlog (Yet to align) |
| `merpWip` | — | `merpOpenEnd − merpBacklog` | Items in Under Development (WIP) |
| `bugsB` | HTTP: Bugs Opened | `.length` | Bug Opened During this month (B) |
| `bugsOpenEnd` | HTTP: Bugs Open End | `.length` | Bug Open: End of this month |
| `business` | HTTP: Merp Opened | count where type = Story (ID 15) | Business Tickets (B) |
| `internal` | — | `merpB − business` | Internally Opened Tickets (C) |

**Rolling 4-month cache** (persisted on disk in `monthly_data_cache.json`, read via `Code: Parse Cache (M)`):
- Key format: `"2026-06"` (YYYY-MM)
- Saves current month; reads prior 3 months to build the 4-column table
- Derives `merp_A` (open at month start) and calculates `merp_C` (closed = A + B − open_end)
- Falls back to a hardcoded Mar/Apr/May 2026 seed only if the disk cache file is completely empty (first-ever run)
- Also emits `cacheOut` (the updated cache as a JSON string), consumed by `Code: Prepare Cache File (M)` → `Read/Write File: Save Cache (M)` to persist it back to disk

**Dynamic sheet tab names (change every month):**
- `sheetTabTasks` = e.g. `"Tasks Jun2026"`
- `sheetTabBugs` = e.g. `"Bugs Jun2026"`
- `sheetBodyTasks` = pre-built JSON for Sheets API batchUpdate (tasks tab)
- `sheetBodyBugs` = pre-built JSON for Sheets API batchUpdate (bugs tab)

**Sheet rows extracted:**
- `tasksRows[]` from HTTP: Tasks Detail — `{ ID, Subject, Type, Status, Author, Assignee, Accountable, "Updated on", "Created on", "Month Of" }`
- `bugsRows[]` from HTTP: Bugs Detail — same shape

**Output (fans out to 3 parallel paths simultaneously):**

| Field | Description |
|---|---|
| `html` | Complete HTML email body |
| `subject` | Email subject line |
| `tasksRows` | Array of task rows for Google Sheets |
| `bugsRows` | Array of bug rows for Google Sheets |
| `sheetTabTasks` | Dynamic tab name e.g. `Tasks Jun2026` |
| `sheetTabBugs` | Dynamic tab name e.g. `Bugs Jun2026` |
| `sheetBodyTasks` | Pre-built Sheets API request body (tasks) |
| `sheetBodyBugs` | Pre-built Sheets API request body (bugs) |

---

## Path A — Tasks Sheet (Nodes 11–14)

Runs in parallel with Path B and Path C after Build Report.

### Node 11 — `HTTP: Create Tasks Tab`
**Type:** HTTP Request (Google Sheets API) | `continueOnFail: true`

**Purpose:** Create a new month-specific tasks tab (e.g. `Tasks Jun2026`) in the Google Sheet. Silently skips if it already exists.

```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2
Body: value of sheetBodyTasks from Build Report
  e.g. {"requests":[{"addSheet":{"properties":{"title":"Tasks Jun2026"}}}]}
```

**Note:** The body is the pre-built `sheetBodyTasks` string from Build Report (built in JavaScript to avoid n8n expression parser issues with nested braces).

**Output → GSheets: Clear Tasks (M)**

---

### Node 12 — `GSheets: Clear Tasks (M)`
**Type:** Google Sheets (clear) | `continueOnFail: true`

**Purpose:** Wipe all rows in the current month's tasks tab before writing fresh data.

**Sheet target:** Dynamic — `sheetTabTasks` from Build Report (e.g. `Tasks Jun2026`)

**Output → Code: To Task Rows (M)**

---

### Node 13 — `Code: To Task Rows (M)`
**Type:** Code (JavaScript, runOnceForAllItems)

**Purpose:** Reads `tasksRows[]` from `Code: Build Report Monthly` and fans it out into N separate items. If empty → returns `[{ _noop: true }]` to keep chain alive.

**Output → GSheets: Append Tasks (M)** (N items)

---

### Node 14 — `GSheets: Append Tasks (M)`
**Type:** Google Sheets (append) | `continueOnFail: true`

**Purpose:** Appends N task rows to the month's tasks tab. Each input item = one new row. Uses `autoMapInputData`.

**Sheet target:** Dynamic — `sheetTabTasks` (e.g. `Tasks Jun2026`)

---

## Path B — Bugs Sheet (Nodes 15–18)

Runs in parallel with Path A and Path C after Build Report.

### Node 15 — `HTTP: Create Bugs Tab`
**Type:** HTTP Request (Google Sheets API) | `continueOnFail: true`

**Purpose:** Create a new month-specific bugs tab (e.g. `Bugs Jun2026`) in the Google Sheet.

```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2
Body: value of sheetBodyBugs from Build Report
  e.g. {"requests":[{"addSheet":{"properties":{"title":"Bugs Jun2026"}}}]}
```

**Output → GSheets: Clear Bugs (M)**

---

### Node 16 — `GSheets: Clear Bugs (M)`
**Type:** Google Sheets (clear) | `continueOnFail: true`

**Purpose:** Wipe all rows in the current month's bugs tab before writing fresh data.

**Sheet target:** Dynamic — `sheetTabBugs` (e.g. `Bugs Jun2026`)

**Output → Code: To Bug Rows (M)**

---

### Node 17 — `Code: To Bug Rows (M)`
**Type:** Code (JavaScript, runOnceForAllItems)

**Purpose:** Reads `bugsRows[]` from `Code: Build Report Monthly` and fans it out into M items. If empty → `[{ _noop: true }]`.

**Output → GSheets: Append Bugs (M)** (M items)

---

### Node 18 — `GSheets: Append Bugs (M)`
**Type:** Google Sheets (append) | `continueOnFail: true`

**Purpose:** Appends M bug rows to the month's bugs tab.

**Sheet target:** Dynamic — `sheetTabBugs` (e.g. `Bugs Jun2026`)

---

## Path C — Email (Nodes 19–20)

Runs in parallel with Path A and Path B after Build Report. Does not wait for sheet writes — email content comes entirely from Build Report.

### Node 19 — `Code: Restore Email (M)`
**Type:** Code (JavaScript, runOnceForAllItems)

**Purpose:** Re-reads `html` and `subject` from `Code: Build Report Monthly` and returns exactly 1 item for Gmail.

**Output → Send Email via Gmail**
```json
{ "html": "<!DOCTYPE html>...", "subject": "BI Monthly Report : BI SOA Task Status Report : June 2026" }
```

---

### Node 20 — `Send Email via Gmail`
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
| Merp Opened | all | **this month** | — | is not Bug | — |
| Merp Open End | **open** | last 365 days | — | is not Bug | — |
| Bugs Opened | all | **this month** | — | is Bug | is not STAGE |
| Bugs Open End | **open** | last 365 days | — | is Bug | is not STAGE |
| Todo Tasks (M) | **= To Do** | last 365 days | — | is not Bug | — |
| Tasks Detail | all | last 365 days | **this month** | is not Bug | — |
| Bugs Detail | all | last 365 days | **this month** | is Bug | is not STAGE |

---

## Sheet Tab Naming Convention

A new pair of tabs is created automatically each month. Tab names include the month and year so it's immediately clear which period the data covers:

| Month | Tasks Tab | Bugs Tab |
|---|---|---|
| March 2026 | `Tasks Mar2026` | `Bugs Mar2026` |
| April 2026 | `Tasks Apr2026` | `Bugs Apr2026` |
| May 2026 | `Tasks May2026` | `Bugs May2026` |
| June 2026 | `Tasks Jun2026` | `Bugs Jun2026` |

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

Persisted on disk at `monthly_data_cache.json` (read/written by the
`Read/Write File: Load Cache (M)` / `Read/Write File: Save Cache (M)` nodes),
**not** `$getWorkflowStaticData` — that in-memory store resets on every
workflow re-import/redeploy, which used to silently drop months from the
rolling window.

```json
{
  "2026-03": { "merp_B": 64, "merp_C": 29, "merp_open": 206, "merp_wip": 124, "merp_backlog": 82,
               "bugs_B": 24, "bugs_C": 10, "bugs_open": 30,  "biz_opened": 11, "int_opened": 53 },
  "2026-04": { ... },
  "2026-05": { ... },
  "2026-06": { ... }
}
```

Every month a new key is appended (nothing is pruned). The workflow only ever
reads the last 4 keys it needs to build the table. Seeded with the Mar/Apr/May
2026 values matching the manual ground-truth report; the in-code hardcoded
seed is only a bootstrap fallback used if the disk file is ever completely
empty.
