# Monthly SOA Report — n8n Workflow Documentation

**Workflow file:** `n8n_monthly_workflow.json`  
**Total nodes:** 21  
**Trigger:** Manual or Scheduled (1st of every month)  
**Output:** HTML email via Gmail + rows written to Google Sheets (dynamic tab per month)

---

## Flow Overview

```
[1]  Code: Setup Monthly
         ↓  authHeader, monthStart, monthEnd, 7 filter JSON strings
[2]  HTTP: Merp Opened          ← API call #1
         ↓  raw work packages JSON
[3]  HTTP: Merp Open End        ← API call #2
         ↓  raw work packages JSON
[4]  HTTP: Bugs Opened          ← API call #3
         ↓  raw work packages JSON
[5]  HTTP: Bugs Open End        ← API call #4
         ↓  raw work packages JSON
[6]  HTTP: Todo Tasks (M)       ← API call #5
         ↓  raw work packages JSON
[7]  HTTP: Tasks Detail         ← API call #6
         ↓  raw work packages JSON
[8]  HTTP: Bugs Detail          ← API call #7
         ↓  raw work packages JSON
[9]  Code: Build Report Monthly
         ↓  { html, subject, tasksRows[], bugsRows[], sheetTabTasks, sheetTabBugs, sheetBodyTasks, sheetBodyBugs }
[10] HTTP: Create Tasks Tab     ← Sheets API — create "<Month>MonthsTasksDetails" tab if missing
         ↓  pass-through (continueOnFail=true)
[11] HTTP: Create Bugs Tab      ← Sheets API — create "<Month>MonthsBugsDetails" tab if missing
         ↓  pass-through (continueOnFail=true)
[12] GSheets: Clear Tasks (M)   ← clear the tasks tab for this month
         ↓  pass-through (continueOnFail=true)
[13] GSheets: Clear Bugs (M)    ← clear the bugs tab for this month
         ↓  pass-through (continueOnFail=true)
[14] Code: To Task Rows (M)     ← explode tasksRows[] → N items (runOnceForAllItems)
         ↓  N individual task row items
[15] GSheets: Append Tasks (M)  ← append N rows to tasks tab
         ↓  N items (pass-through)
[16] Code: To Bug Rows (M)      ← explode bugsRows[] → M items (runOnceForAllItems)
         ↓  M individual bug row items
[17] GSheets: Append Bugs (M)   ← append M rows to bugs tab
         ↓  M items (pass-through)
[18] Code: Restore Email (M)    ← collapse back to 1 item (runOnceForAllItems)
         ↓  { html, subject }
[19] Send Email via Gmail
```

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
- Calculates `cutoff` = monthStart minus 365 days (year-lookback window start, e.g. `2025-06-01`)
- Builds and serialises 7 filter JSON strings — one for each API call

**Output passed to next node:**

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

### Node 2 — `HTTP: Merp Opened`
**Type:** HTTP Request (OpenProject API, call #1)  
**Purpose:** Fetch non-bug tasks **created this month** → count becomes the **B value** for Merp SOA Tasks

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Headers:
  Authorization: Basic <authHeader>
Query params:
  pageSize = 1000
  offset   = 1
  filters  = [
    { "project":   { "operator": "=",   "values": ["75"] } },
    { "createdAt": { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `project = 75` — MERP Services project only
- `createdAt between monthStart and monthEnd` — created this month (Status = all)
- `type is not 19 (API Bug)` — exclude bugs

**Output passed to next node:** Raw OpenProject JSON response (`_embedded.elements` array of work packages)

---

### Node 3 — `HTTP: Merp Open End`
**Type:** HTTP Request (OpenProject API, call #2)  
**Purpose:** Fetch all non-bug tasks currently in **open status** within last 365 days → count is **total open tasks at end of month**

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Headers:
  Authorization: Basic <authHeader>
Query params:
  pageSize = 1000
  offset   = 1
  filters  = [
    { "project":   { "operator": "=",   "values": ["75"] } },
    { "createdAt": { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
    { "status":    { "operator": "o",   "values": [] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `createdAt between cutoff and monthEnd` — tickets created within last 365 days
- `status = o` — **open status group** (built-in OpenProject filter, all open statuses)
- `type is not 19 (API Bug)` — exclude bugs

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 4 — `HTTP: Bugs Opened`
**Type:** HTTP Request (OpenProject API, call #3)  
**Purpose:** Fetch bug tickets **created this month**, excluding STAGE environment → count becomes the **B value** for SOA Bugs

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Headers:
  Authorization: Basic <authHeader>
Query params:
  pageSize = 1000
  offset   = 1
  filters  = [
    { "project":      { "operator": "=",   "values": ["75"] } },
    { "createdAt":    { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
    { "type":         { "operator": "=",   "values": ["19"] } },
    { "customField9": { "operator": "!",   "values": ["22"] } }
  ]
```

**Filter breakdown:**
- `createdAt between monthStart and monthEnd` — created this month (Status = all)
- `type = 19 (API Bug)` — bugs only
- `customField9 is not 22 (STAGE)` — exclude STAGE environment bugs

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 5 — `HTTP: Bugs Open End`
**Type:** HTTP Request (OpenProject API, call #4)  
**Purpose:** Fetch all open bugs (excluding STAGE) within last 365 days → count is **total open bugs at end of month**

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Headers:
  Authorization: Basic <authHeader>
Query params:
  pageSize = 1000
  offset   = 1
  filters  = [
    { "project":      { "operator": "=",   "values": ["75"] } },
    { "createdAt":    { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
    { "status":       { "operator": "o",   "values": [] } },
    { "type":         { "operator": "=",   "values": ["19"] } },
    { "customField9": { "operator": "!",   "values": ["22"] } }
  ]
```

**Filter breakdown:**
- `status = o` — open status group only
- `type = 19 (API Bug)` — bugs only
- `customField9 is not 22 (STAGE)` — exclude STAGE environment bugs

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 6 — `HTTP: Todo Tasks (M)`
**Type:** HTTP Request (OpenProject API, call #5)  
**Purpose:** Fetch non-bug tasks with status exactly **"To Do"** (ID=1) → count is the **Backlog** metric

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Headers:
  Authorization: Basic <authHeader>
Query params:
  pageSize = 1000
  offset   = 1
  filters  = [
    { "project":   { "operator": "=",   "values": ["75"] } },
    { "createdAt": { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
    { "status":    { "operator": "=",   "values": ["1"] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `status = 1 (To Do)` — exact status match (not the "open" group)
- `type is not 19 (API Bug)` — exclude bugs

**How result is used in Node 9:**
- `merpBacklog = todoEls.length`
- `merpWip = merpOpenEnd − merpBacklog`

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 7 — `HTTP: Tasks Detail`
**Type:** HTTP Request (OpenProject API, call #6)  
**Purpose:** Fetch full work package records for non-bug tasks **updated this month** within the last year → rows written to **`<Month>MonthsTasksDetails`** Google Sheet tab

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Headers:
  Authorization: Basic <authHeader>
Query params:
  pageSize = 1000
  offset   = 1
  filters  = [
    { "project":   { "operator": "=",   "values": ["75"] } },
    { "createdAt": { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
    { "updatedAt": { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `createdAt between cutoff and monthEnd` — created within last 365 days
- `updatedAt between monthStart and monthEnd` — updated this month (Status = all)
- `type is not 19 (API Bug)` — tasks only

**Output passed to next node:** Raw OpenProject JSON response (full work package records)

---

### Node 8 — `HTTP: Bugs Detail`
**Type:** HTTP Request (OpenProject API, call #7)  
**Purpose:** Fetch full work package records for bug tickets **updated this month**, excluding STAGE → rows written to **`<Month>MonthsBugsDetails`** Google Sheet tab

**API Call:**
```
GET https://project.intermesh.net/api/v3/work_packages
Headers:
  Authorization: Basic <authHeader>
Query params:
  pageSize = 1000
  offset   = 1
  filters  = [
    { "project":      { "operator": "=",   "values": ["75"] } },
    { "createdAt":    { "operator": "<>d", "values": ["2025-06-01", "2026-06-30"] } },
    { "updatedAt":    { "operator": "<>d", "values": ["2026-06-01", "2026-06-30"] } },
    { "type":         { "operator": "=",   "values": ["19"] } },
    { "customField9": { "operator": "!",   "values": ["22"] } }
  ]
```

**Filter breakdown:**
- `updatedAt between monthStart and monthEnd` — updated this month (Status = all)
- `type = 19 (API Bug)` — bugs only
- `customField9 is not 22 (STAGE)` — exclude STAGE environment bugs

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 9 — `Code: Build Report Monthly`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
Reads all 7 HTTP node responses and computes every metric shown in the report.

**Metrics calculated:**

| Variable | Source Node | Calculation | Report Row |
|---|---|---|---|
| `merpB` | HTTP: Merp Opened | `.length` | Opened During this month (B) |
| `merpOpenEnd` | HTTP: Merp Open End | `.length` | Open: End of this month |
| `merpBacklog` | HTTP: Todo Tasks (M) | `.length` | Backlog (Yet to align) |
| `merpWip` | — | `merpOpenEnd − merpBacklog` | Items in Under Development (WIP) |
| `bugsB` | HTTP: Bugs Opened | `.length` | Bug Opened During this month (B) |
| `bugsOpenEnd` | HTTP: Bugs Open End | `.length` | Bug Open: End of this month |
| `business` | HTTP: Merp Opened | count where type = Story (ID 15) | Business Tickets (B) |
| `internal` | — | `merpB − business` | Internally Opened Tickets (C) |

**Rolling 4-month cache** (`$getWorkflowStaticData('global').mcache`):
- Cache key: `"2026-06"` (YYYY-MM format)
- Saves current month's metrics to cache
- Reads last 3 months from cache to build the 4-column report table
- Derives `merp_A` (open at month start) = previous month's `merp_open`
- Calculates `merp_C` (closed) = A + B − open_end
- Pre-seeded with Mar, Apr, May 2026 historical values

**Sheet tab names (dynamic, per month):**
- `sheetTabTasks` = e.g. `"JuneMonthsTasksDetails"`
- `sheetTabBugs` = e.g. `"JuneMonthsBugsDetails"`

**Pre-built Sheets API request bodies:**
- `sheetBodyTasks` = `{"requests":[{"addSheet":{"properties":{"title":"JuneMonthsTasksDetails"}}}]}`
- `sheetBodyBugs` = `{"requests":[{"addSheet":{"properties":{"title":"JuneMonthsBugsDetails"}}}]}`
  (Built here in JS to avoid n8n expression syntax issues with nested braces)

**Sheet rows extracted:**
- `tasksRows[]` = each record from HTTP: Tasks Detail flattened to:
  `{ ID, Subject, Type, Status, Author, Assignee, Accountable, "Updated on", "Created on", "Month Of" }`
- `bugsRows[]` = same shape from HTTP: Bugs Detail

**Builds HTML email** with summary table (4-month rolling) and bifurcation table.

**Output passed to next node:**

| Field | Type | Description |
|---|---|---|
| `html` | string | Complete HTML email body |
| `subject` | string | e.g. `BI Monthly Report : BI SOA Task Status Report : June 2026` |
| `tasksRows` | array | Flat task rows for Google Sheets |
| `bugsRows` | array | Flat bug rows for Google Sheets |
| `sheetTabTasks` | string | Dynamic tab name, e.g. `JuneMonthsTasksDetails` |
| `sheetTabBugs` | string | Dynamic tab name, e.g. `JuneMonthsBugsDetails` |
| `sheetBodyTasks` | string | Pre-built JSON body for Sheets batchUpdate (tasks tab) |
| `sheetBodyBugs` | string | Pre-built JSON body for Sheets batchUpdate (bugs tab) |

---

### Node 10 — `HTTP: Create Tasks Tab`
**Type:** HTTP Request (Google Sheets API)  
**continueOnFail: true** (silently skips if tab already exists)

**Purpose:** Creates a new month-specific sheet tab (e.g. `JuneMonthsTasksDetails`) in the Google Sheet. This creates a new tab every month automatically.

**API Call:**
```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2 (googleSheetsOAuth2Api credential)
Content-Type: application/json

Body: (value of sheetBodyTasks from Node 9)
  e.g. {"requests":[{"addSheet":{"properties":{"title":"JuneMonthsTasksDetails"}}}]}
```

**Note:** The body is taken from `sheetBodyTasks` (pre-built in Node 9) via:
`={{ $('Code: Build Report Monthly').first().json.sheetBodyTasks }}`

**Output passed to next node:** Same single item (pass-through)

---

### Node 11 — `HTTP: Create Bugs Tab`
**Type:** HTTP Request (Google Sheets API)  
**continueOnFail: true**

**Purpose:** Creates a new month-specific sheet tab (e.g. `JuneMonthsBugsDetails`) in the Google Sheet

**API Call:**
```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2
Content-Type: application/json

Body: (value of sheetBodyBugs from Node 9)
  e.g. {"requests":[{"addSheet":{"properties":{"title":"JuneMonthsBugsDetails"}}}]}
```

**Output passed to next node:** Same single item (pass-through)

---

### Node 12 — `GSheets: Clear Tasks (M)`
**Type:** Google Sheets (operation: clear)  
**continueOnFail: true**

**Purpose:** Wipes all rows in the current month's tasks tab before writing fresh data (safe to re-run)

**Sheet target:** Dynamic tab name from `sheetTabTasks` (e.g. `JuneMonthsTasksDetails`)

**Output passed to next node:** Same single item (pass-through)

---

### Node 13 — `GSheets: Clear Bugs (M)`
**Type:** Google Sheets (operation: clear)  
**continueOnFail: true**

**Purpose:** Wipes all rows in the current month's bugs tab

**Sheet target:** Dynamic tab name from `sheetTabBugs` (e.g. `JuneMonthsBugsDetails`)

**Output passed to next node:** Same single item (pass-through)

---

### Node 14 — `Code: To Task Rows (M)`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Reads `tasksRows[]` directly from `Code: Build Report Monthly` (bypasses its own 1-item input)
- If the array is empty → returns `[{ json: { _noop: true } }]` to keep the chain alive
- If non-empty → returns N separate items, one per task row

**Why this node is needed:** GSheets Append expects one item per row. Build Report outputs a single item containing an array. This node fans the array out into N items.

**Output passed to next node:** N items, each shaped as:
```json
{ "ID": 1234, "Subject": "Task title", "Type": "Task", "Status": "In Progress",
  "Author": "John", "Assignee": "Jane", "Accountable": "Bob",
  "Updated on": "2026-06-25 14:30", "Created on": "2026-05-10 09:00", "Month Of": "01 Jun - 30 Jun" }
```

---

### Node 15 — `GSheets: Append Tasks (M)`
**Type:** Google Sheets (operation: append)  
**continueOnFail: true**

**Purpose:** Appends all N task rows into the month's tasks tab. Each input item becomes one new row.

**Sheet target:** Dynamic tab `JuneMonthsTasksDetails` (from `sheetTabTasks`)  
**Mode:** `autoMapInputData` — JSON field names become column headers automatically

**Output passed to next node:** N items (pass-through; next node ignores count)

---

### Node 16 — `Code: To Bug Rows (M)`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Runs **once** regardless of how many items came from Node 15
- Reads `bugsRows[]` directly from `Code: Build Report Monthly`
- If empty → `[{ json: { _noop: true } }]`; otherwise fans out into M items

**Output passed to next node:** M items, each a flat bug row (same shape, `"Month Of"` instead of `"Week Of"`)

---

### Node 17 — `GSheets: Append Bugs (M)`
**Type:** Google Sheets (operation: append)  
**continueOnFail: true**

**Purpose:** Appends all M bug rows into the month's bugs tab

**Sheet target:** Dynamic tab `JuneMonthsBugsDetails` (from `sheetTabBugs`)

**Output passed to next node:** M items (pass-through)

---

### Node 18 — `Code: Restore Email (M)`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Runs **once** regardless of how many items came from Node 17
- Re-reads `html` and `subject` from `Code: Build Report Monthly`
- Returns exactly **1 item** with only the email fields

**Why this node is needed:** After Append Bugs emits M items, Gmail needs exactly 1 item. This collapses item count back to 1.

**Output passed to next node:**
```json
{ "html": "<!DOCTYPE html>...", "subject": "BI Monthly Report : BI SOA Task Status Report : June 2026" }
```

---

### Node 19 — `Send Email via Gmail`
**Type:** Gmail (send)

**What it does:**
- Sends the monthly HTML report email
- **To:** `rlc42847@gmail.com`
- **Subject:** value of `{{ $json.subject }}`
- **Body (HTML):** value of `{{ $json.html }}`

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

Each month gets its own pair of tabs, created automatically:

| Month | Tasks Tab | Bugs Tab |
|---|---|---|
| March 2026 | `MarchMonthsTasksDetails` | `MarchMonthsBugsDetails` |
| April 2026 | `AprilMonthsTasksDetails` | `AprilMonthsBugsDetails` |
| May 2026 | `MayMonthsTasksDetails` | `MayMonthsBugsDetails` |
| June 2026 | `JuneMonthsTasksDetails` | `JuneMonthsBugsDetails` |

---

## Constants Reference

| Constant | Value | Meaning |
|---|---|---|
| `PROJECT_ID` | `75` | MERP Services OpenProject project ID |
| `API_BUG_TYPE_ID` | `19` | Work package type ID for "API Bug" |
| `API_STORY_TYPE_ID` | `15` | Work package type ID for "Story" (business tickets) |
| `ENV_STAGE_OPTION_ID` | `22` | customField9 (Environment) option value for "STAGE" |
| `TODO_STATUS_ID` | `1` | Status ID for "To Do" |
| `YEAR_LOOKBACK_DAYS` | `365` | Year-lookback window length |
| `operator: 'o'` | built-in | OpenProject "Status is open" group |
| `operator: '<>d'` | built-in | OpenProject "between dates" |
| `operator: '!'` | built-in | OpenProject "is not" |
| `operator: '='` | built-in | OpenProject "is" (exact match) |

---

## Cache Structure

```json
{
  "2026-03": {
    "merp_B": 64, "merp_C": 29, "merp_open": 206,
    "merp_wip": 124, "merp_backlog": 82,
    "bugs_B": 24, "bugs_C": 10, "bugs_open": 30,
    "biz_opened": 11, "int_opened": 53
  },
  "2026-04": { ... },
  "2026-05": { ... },
  "2026-06": { ... }
}
```

The cache keeps data for the **4 most recent months**. Each run adds the current month and the 4-month window slides forward. Pre-seeded with Mar, Apr, May 2026 so the 4-column table is populated from the first run.
