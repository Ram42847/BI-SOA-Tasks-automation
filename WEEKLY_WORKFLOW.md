# Weekly SOA Report — n8n Workflow Documentation

**Workflow file:** `n8n_workflow.json`  
**Total nodes:** 22  
**Trigger:** Manual or Scheduled (every Monday)  
**Output:** HTML email via Gmail + rows written to Google Sheets

---

## Flow Overview

```
[1]  Code: Setup
         ↓  authHeader, weekStart, weekEnd, 8 filter JSON strings
[2]  HTTP: Merp Opened          ← API call #1
         ↓  raw work packages JSON
[3]  HTTP: Merp Open End        ← API call #2
         ↓  raw work packages JSON
[4]  HTTP: Bugs Opened          ← API call #3
         ↓  raw work packages JSON
[5]  HTTP: Bugs Open End        ← API call #4
         ↓  raw work packages JSON
[6]  HTTP: Dev Tasks            ← API call #5
         ↓  raw work packages JSON
[7]  HTTP: Todo Tasks           ← API call #6
         ↓  raw work packages JSON
[8]  HTTP: Tasks Detail         ← API call #7
         ↓  raw work packages JSON
[9]  HTTP: Bugs Detail          ← API call #8
         ↓  raw work packages JSON
[10] Code: Build Report
         ↓  { html, subject, tasksRows[], bugsRows[] }
[11] HTTP: Create Tasks Tab     ← Sheets API — create tab if missing
         ↓  pass-through (continueOnFail=true)
[12] HTTP: Create Bugs Tab      ← Sheets API — create tab if missing
         ↓  pass-through (continueOnFail=true)
[13] GSheets: Clear Tasks       ← clear TasksDetails tab
         ↓  pass-through (continueOnFail=true)
[14] GSheets: Clear Bugs        ← clear BugsDetails tab
         ↓  pass-through (continueOnFail=true)
[15] Code: To Task Rows         ← explode tasksRows[] → N items
         ↓  N individual task row items
[16] GSheets: Append Tasks      ← append N rows to TasksDetails
         ↓  N items (pass-through)
[17] Code: To Bug Rows          ← explode bugsRows[] → M items (runOnceForAllItems)
         ↓  M individual bug row items
[18] GSheets: Append Bugs       ← append M rows to BugsDetails
         ↓  M items (pass-through)
[19] Code: Restore Email        ← collapse back to 1 item (runOnceForAllItems)
         ↓  { html, subject }
[20] Send Email via Gmail
```

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
- Builds and serialises 8 filter JSON strings — one for each API call

**Output passed to next node:**

| Field | Example | Purpose |
|---|---|---|
| `authHeader` | `Basic YXBpa2V5...` | Used in Authorization header by all HTTP nodes |
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

### Node 2 — `HTTP: Merp Opened`
**Type:** HTTP Request (OpenProject API, call #1)  
**Purpose:** Fetch non-bug tasks **created this week** → count becomes the **B value** for Merp SOA Tasks

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
    { "createdAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `project = 75` — MERP Services project only
- `createdAt between weekStart and weekEnd` — created this week (Status = all)
- `type is not 19 (API Bug)` — exclude bug tickets

**Output passed to next node:** Raw OpenProject JSON response (work packages with `_embedded.elements`)

---

### Node 3 — `HTTP: Merp Open End`
**Type:** HTTP Request (OpenProject API, call #2)  
**Purpose:** Fetch all non-bug tasks currently in **open status** within last 365 days → count is **total open tasks at end of week**

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
    { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
    { "status":    { "operator": "o",   "values": [] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `createdAt between cutoff and weekEnd` — tickets created within last 365 days
- `status = o` — **open status group** (built-in OpenProject filter, covers all "open" statuses)
- `type is not 19 (API Bug)` — exclude bugs

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 4 — `HTTP: Bugs Opened`
**Type:** HTTP Request (OpenProject API, call #3)  
**Purpose:** Fetch bug tickets **created this week** → count becomes the **B value** for SOA Bugs

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
    { "createdAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
    { "type":      { "operator": "=",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `createdAt between weekStart and weekEnd` — created this week (Status = all)
- `type = 19 (API Bug)` — bugs only

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 5 — `HTTP: Bugs Open End`
**Type:** HTTP Request (OpenProject API, call #4)  
**Purpose:** Fetch all open bugs (excluding STAGE environment) → count is **total open bugs at end of week**

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
    { "createdAt":    { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
    { "status":       { "operator": "o",   "values": [] } },
    { "type":         { "operator": "=",   "values": ["19"] } },
    { "customField9": { "operator": "!",   "values": ["22"] } }
  ]
```

**Filter breakdown:**
- `status = o` — open status group
- `type = 19 (API Bug)` — bugs only
- `customField9 is not 22` — Environment field is not STAGE (excludes test/staging bugs)

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 6 — `HTTP: Dev Tasks`
**Type:** HTTP Request (OpenProject API, call #5)  
**Purpose:** Fetch all tickets (any type) **updated this week** within the last year → used to build the **Developer Activity table** in the email

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
    { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
    { "updatedAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } }
  ]
```

**Filter breakdown:**
- `createdAt between cutoff and weekEnd` — created within last 365 days
- `updatedAt between weekStart and weekEnd` — updated this week
- No type filter — includes all ticket types (tasks, bugs, stories, etc.)

**Output passed to next node:** Raw OpenProject JSON response (grouped by developer in Build node)

---

### Node 7 — `HTTP: Todo Tasks`
**Type:** HTTP Request (OpenProject API, call #6)  
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
    { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
    { "status":    { "operator": "=",   "values": ["1"] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `status = 1 (To Do)` — exact status match (not the open group)
- `type is not 19 (API Bug)` — exclude bugs

**How result is used in Node 10:**
- `merpBacklog = todoEls.length` (count of To Do tickets)
- `merpWip = merpOpenEnd − merpBacklog`

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 8 — `HTTP: Tasks Detail`
**Type:** HTTP Request (OpenProject API, call #7)  
**Purpose:** Fetch full work package records for non-bug tasks **updated this week** → rows written to **TasksDetails** Google Sheet

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
    { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
    { "updatedAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
    { "type":      { "operator": "!",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `createdAt between cutoff and weekEnd` — created within last 365 days
- `updatedAt between weekStart and weekEnd` — updated this week
- `type is not 19 (API Bug)` — tasks only, no bugs

**Output passed to next node:** Raw OpenProject JSON response (full work package fields)

---

### Node 9 — `HTTP: Bugs Detail`
**Type:** HTTP Request (OpenProject API, call #8)  
**Purpose:** Fetch full work package records for bug tickets **updated this week** → rows written to **BugsDetails** Google Sheet

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
    { "createdAt": { "operator": "<>d", "values": ["2025-06-22", "2026-06-28"] } },
    { "updatedAt": { "operator": "<>d", "values": ["2026-06-22", "2026-06-28"] } },
    { "type":      { "operator": "=",   "values": ["19"] } }
  ]
```

**Filter breakdown:**
- `updatedAt between weekStart and weekEnd` — updated this week
- `type = 19 (API Bug)` — bugs only
- No Environment filter (detail view includes all environments)

**Output passed to next node:** Raw OpenProject JSON response

---

### Node 10 — `Code: Build Report`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
Reads responses from all 8 HTTP nodes and computes every metric in the report.

**Metrics calculated:**

| Variable | Source Node | Calculation | Report Row |
|---|---|---|---|
| `merpB` | HTTP: Merp Opened | `.length` | Opened During this week (B) |
| `merpOpenEnd` | HTTP: Merp Open End | `.length` | Open: End of this week |
| `merpBacklog` | HTTP: Todo Tasks | `.length` | Backlog (Yet to align) |
| `merpWip` | — | `merpOpenEnd − merpBacklog` | Items in Under Development (WIP) |
| `bugsB` | HTTP: Bugs Opened | `.length` | Bug Opened During this week (B) |
| `bugsOpenEnd` | HTTP: Bugs Open End | `.length` | Bug Open: End of this week |
| `business` | HTTP: Merp Opened | count where type = Story (ID 15) | Business Tickets (B) |
| `internal` | — | `merpB − business` | Internally Opened Tickets (C) |

**Rolling 4-week cache** (`$getWorkflowStaticData('global').cache`):
- Cache key: `"2026-06-22_2026-06-28"` (weekStart_weekEnd)
- Saves current week's metrics to cache
- Reads last 3 weeks from cache to build the 4-column table
- Derives `merp_A` = open at week beginning = previous week's `merp_open`
- Calculates `merp_C` = A + B − open_end (closed this week)

**Developer table** (built from HTTP: Dev Tasks):
- Groups work packages by Assignee and Accountable (responsible) person
- Deduplicates same person + same ticket
- Sorted alphabetically by developer name

**Sheet rows extracted:**
- `tasksRows[]` = each record from HTTP: Tasks Detail flattened to:
  `{ ID, Subject, Type, Status, Author, Assignee, Accountable, "Updated on", "Created on", "Week Of" }`
- `bugsRows[]` = same shape from HTTP: Bugs Detail

**Output passed to next node:**

| Field | Type | Description |
|---|---|---|
| `html` | string | Complete HTML email body |
| `subject` | string | e.g. `BI Weekly Report : BI SOA Task Status Report : 22 Jun - 28 Jun 2026` |
| `tasksRows` | array | Flat task rows for Google Sheets |
| `bugsRows` | array | Flat bug rows for Google Sheets |

---

### Node 11 — `HTTP: Create Tasks Tab`
**Type:** HTTP Request (Google Sheets API)  
**continueOnFail: true** (silently skips if tab already exists)

**Purpose:** Creates the `TasksDetails` tab in the Google Sheet the first time the workflow runs

**API Call:**
```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2 (googleSheetsOAuth2Api credential)
Content-Type: application/json

Body: {"requests":[{"addSheet":{"properties":{"title":"TasksDetails"}}}]}
```

**Output passed to next node:** Same single item (pass-through)

---

### Node 12 — `HTTP: Create Bugs Tab`
**Type:** HTTP Request (Google Sheets API)  
**continueOnFail: true**

**Purpose:** Creates the `BugsDetails` tab in the Google Sheet the first time the workflow runs

**API Call:**
```
POST https://sheets.googleapis.com/v4/spreadsheets/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q:batchUpdate
Authorization: Google OAuth2
Content-Type: application/json

Body: {"requests":[{"addSheet":{"properties":{"title":"BugsDetails"}}}]}
```

**Output passed to next node:** Same single item (pass-through)

---

### Node 13 — `GSheets: Clear Tasks`
**Type:** Google Sheets (operation: clear)  
**continueOnFail: true**

**Purpose:** Wipes all existing rows in `TasksDetails` before writing fresh data. Prevents duplicates on re-run.

**Sheet target:** Tab `TasksDetails` in spreadsheet `1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q`

**Output passed to next node:** Same single item (pass-through)

---

### Node 14 — `GSheets: Clear Bugs`
**Type:** Google Sheets (operation: clear)  
**continueOnFail: true**

**Purpose:** Wipes all existing rows in `BugsDetails` before writing fresh data

**Sheet target:** Tab `BugsDetails`

**Output passed to next node:** Same single item (pass-through)

---

### Node 15 — `Code: To Task Rows`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Reads `tasksRows[]` directly from `Code: Build Report` (bypasses its own 1-item input)
- If the array is empty → returns `[{ json: { _noop: true } }]` to keep the chain alive
- If non-empty → returns N separate items, one per task row

**Why this node is needed:** GSheets Append needs one item per row. Build Report outputs one item with an array inside. This node fans the array out into N separate items.

**Output passed to next node:** N items, each shaped as:
```json
{ "ID": 1234, "Subject": "Task title", "Type": "Task", "Status": "In Progress",
  "Author": "John", "Assignee": "Jane", "Accountable": "Bob",
  "Updated on": "2026-06-25 14:30", "Created on": "2026-05-10 09:00", "Week Of": "22 Jun - 28 Jun" }
```

---

### Node 16 — `GSheets: Append Tasks`
**Type:** Google Sheets (operation: append)  
**continueOnFail: true**

**Purpose:** Appends all N task rows into `TasksDetails`. Each input item becomes one new row.

**Sheet target:** Tab `TasksDetails`  
**Mode:** `autoMapInputData` — uses JSON field names as column headers automatically

**Output passed to next node:** N items (pass-through; next node ignores this count)

---

### Node 17 — `Code: To Bug Rows`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Runs **once** regardless of how many items came from Node 16
- Reads `bugsRows[]` directly from `Code: Build Report`
- If empty → `[{ json: { _noop: true } }]`; otherwise fans out into M items

**Output passed to next node:** M items, each a flat bug row (same shape as task rows but with `"Week Of"` label)

---

### Node 18 — `GSheets: Append Bugs`
**Type:** Google Sheets (operation: append)  
**continueOnFail: true**

**Purpose:** Appends all M bug rows into `BugsDetails`

**Sheet target:** Tab `BugsDetails`

**Output passed to next node:** M items (pass-through)

---

### Node 19 — `Code: Restore Email`
**Type:** Code (JavaScript, runOnceForAllItems)

**What it does:**
- Runs **once** regardless of how many items came from Node 18
- Re-reads `html` and `subject` from `Code: Build Report`
- Returns exactly **1 item** with just the email fields

**Why this node is needed:** After Append Bugs emits M items, Gmail node needs exactly 1 item to send one email. This node resets item count to 1 and discards the sheet row data.

**Output passed to next node:**
```json
{ "html": "<!DOCTYPE html>...", "subject": "BI Weekly Report : BI SOA Task Status Report : 22 Jun - 28 Jun 2026" }
```

---

### Node 20 — `Send Email via Gmail`
**Type:** Gmail (send)

**What it does:**
- Sends the weekly HTML report email
- **To:** `rlc42847@gmail.com`
- **Subject:** value of `{{ $json.subject }}`
- **Body (HTML):** value of `{{ $json.html }}`

**End of workflow.**

---

## API Filter Quick Reference

| Node | Status | Created On | Updated On | Type | Environment |
|---|---|---|---|---|---|
| Merp Opened | all | this week | — | is not Bug | — |
| Merp Open End | **open** | last 365 days | — | is not Bug | — |
| Bugs Opened | all | this week | — | is Bug | — |
| Bugs Open End | **open** | last 365 days | — | is Bug | is not STAGE |
| Dev Tasks | all | last 365 days | this week | — (all) | — |
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
  "2026-06-08_2026-06-14": {
    "merp_B": 20, "merp_C": 21, "merp_open": 123,
    "merp_wip": 101, "merp_backlog": 22,
    "bugs_B": 9, "bugs_C": 13, "bugs_open": 12,
    "biz_opened": 10, "int_opened": 10,
    "dev_tasks": { "John Smith": [{ "id": 1234, "subject": "Fix login bug" }] }
  },
  "2026-06-15_2026-06-21": { ... },
  "2026-06-22_2026-06-28": { ... }
}
```

The cache keeps data for the **4 most recent weeks**. Each run adds the current week and the 4-week window slides forward automatically.
