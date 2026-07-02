# SOA Weekly Report — n8n Workflow Documentation

**File:** `n8n_workflow.json` (21 nodes)  
**Generator:** `generate_n8n_workflow.py`  
**Schedule:** Every Sunday at 8:00 PM (`0 20 * * 0`)  
**Report period:** Sun–Sat of the most recently completed week

---

## 1. Node Chain (Sequential)

Every node passes its output to the next in a single linear chain. This ensures any downstream Code node can reach any upstream node via `$('Node Name')`.

```
Manual Trigger ──┐
                 ├──→  Code: Setup
Schedule Trigger ┘
                         │
                         ▼
                  HTTP: Merp Opened          [API call 1]
                         │
                         ▼
                  HTTP: Merp Open End        [API call 2]
                         │
                         ▼
                  HTTP: Bugs Opened          [API call 3]
                         │
                         ▼
                  HTTP: Bugs Open End        [API call 4]
                         │
                         ▼
                  HTTP: Dev Tasks            [API call 5]
                         │
                         ▼
                  HTTP: Tasks Detail         [API call 6]
                         │
                         ▼
                  HTTP: Bugs Detail          [API call 7]
                         │
                         ▼
                  Code: Build Report
                         │
                         ▼
                  HTTP: Create Tasks Tab     [Sheets API — continueOnFail]
                         │
                         ▼
                  HTTP: Create Bugs Tab      [Sheets API — continueOnFail]
                         │
                         ▼
                  GSheets: Clear Tasks       [continueOnFail]
                         │
                         ▼
                  GSheets: Clear Bugs        [continueOnFail]
                         │
                         ▼
                  Code: To Task Rows
                         │
                         ▼
                  GSheets: Append Tasks
                         │
                         ▼
                  Code: To Bug Rows
                         │
                         ▼
                  GSheets: Append Bugs
                         │
                         ▼
                  Code: Restore Email
                         │
                         ▼
                  Send Email via Gmail
```

---

## 2. OpenProject API — Common Parameters

**Endpoint:** `GET https://project.intermesh.net/api/v3/work_packages`  
**Auth:** `Authorization: Basic base64("apikey:<token>")`  
**Fixed query params on every call:**

| Param      | Value  |
|------------|--------|
| `pageSize` | `1000` |
| `offset`   | `1`    |
| `filters`  | JSON array (varies per node — see Section 3) |

**Project constants:**

| Constant             | Value | Meaning |
|----------------------|-------|---------|
| `PROJECT_ID`         | `75`  | MERP Services project |
| `API_BUG_TYPE_ID`    | `19`  | Work package type = "API Bug" |
| `API_STORY_TYPE_ID`  | `15`  | Work package type = "Story" (used for Business ticket count) |
| `ENV_STAGE_OPTION_ID`| `22`  | Custom Field 9 option = "STAGE" environment |
| `YEAR_LOOKBACK_DAYS` | `365` | How far back "open end of week" looks for created tickets |

---

## 3. Filter Building Blocks

All filters are combined as a JSON array: `[proj, ...extras]`

| Variable      | Field         | Operator | Value(s)                        | Meaning |
|---------------|---------------|----------|---------------------------------|---------|
| `proj`        | `project`     | `=`      | `["75"]`                        | Only MERP Services project |
| `open`        | `status`      | `=`      | 54 open status IDs (see below)  | Work package is open |
| `notBug`      | `type`        | `!`      | `["19"]`                        | Exclude API Bug type |
| `bug`         | `type`        | `=`      | `["19"]`                        | Only API Bug type |
| `noStage`     | `customField9`| `!`      | `["22"]`                        | Exclude tickets with env = STAGE |
| `created`     | `createdAt`   | `<>d`    | `[weekStart, weekEnd]`          | Created within this week (Sun–Sat) |
| `yr`          | `createdAt`   | `<>d`    | `[weekEnd − 365 days, weekEnd]` | Created any time in the last year |
| `updated`     | `updatedAt`   | `<>d`    | `[weekStart, weekEnd]`          | Last updated within this week |

**Week boundaries** (computed at runtime, Sunday to Saturday):
```
weekStart (Sun) = most recent Sunday before today
weekEnd   (Sat) = weekStart + 6 days
```

**54 Open Status IDs:**
```
39, 44, 88, 36, 97, 42, 37, 40, 43, 46, 96, 59, 60, 61, 62, 63,
47, 98, 93, 94, 95, 64, 89, 90, 91, 92, 82, 48, 49, 52, 50, 51,
53, 65, 54, 66, 67, 68, 57, 69, 71, 72, 73, 74, 75, 76, 77, 78,
79, 80, 81, 1, 38, 99, 100, 101
```

**Backlog Status ID:** `1` (used to split WIP vs Backlog from Open End count)

---

## 4. API Calls — Node-by-Node Breakdown

### API Call 1 — `HTTP: Merp Opened`
**Filter field:** `merpOpenedFilter`  
**Filters applied:** `proj` + `created` + `open` + `notBug`

```json
[
  { "project":   { "operator": "=",    "values": ["75"] } },
  { "createdAt": { "operator": "<>d",  "values": ["<weekStart>", "<weekEnd>"] } },
  { "status":    { "operator": "=",    "values": ["39","44","88",...] } },
  { "type":      { "operator": "!",    "values": ["19"] } }
]
```

**What it fetches:** Non-bug work packages created this week that are currently open  
**Used to calculate:**
- `merp_B` = `response.count` → **"Opened During this week (B)"** for Merp SOA Tasks
- `business` = count where `_links.type` ID = 15 (Story) → **"Business Tickets (B)"**
- `internal` = `merp_B − business` → **"Internally Opened Tickets (C)"**

---

### API Call 2 — `HTTP: Merp Open End`
**Filter field:** `merpOpenEndFilter`  
**Filters applied:** `proj` + `yr` + `open` + `notBug`

```json
[
  { "project":   { "operator": "=",    "values": ["75"] } },
  { "createdAt": { "operator": "<>d",  "values": ["<weekEnd−365d>", "<weekEnd>"] } },
  { "status":    { "operator": "=",    "values": ["39","44","88",...] } },
  { "type":      { "operator": "!",    "values": ["19"] } }
]
```

**What it fetches:** All non-bug work packages that are open at end of week (created within last year)  
**Used to calculate:**
- `merpOpenEnd` = `response.count` → **"Open: End of this week (A + B − C)"**
- `merpBacklog` = count where `_links.status` ID = 1 → **"Backlog (Yet to align)"**
- `merpWip` = `merpOpenEnd − merpBacklog` → **"Items in Under Development (WIP)"**

---

### API Call 3 — `HTTP: Bugs Opened`
**Filter field:** `bugsOpenedFilter`  
**Filters applied:** `proj` + `created` + `open` + `bug` + `noStage`

```json
[
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["<weekStart>", "<weekEnd>"] } },
  { "status":       { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```

**What it fetches:** API Bug tickets created this week, open, and NOT in STAGE environment  
**Used to calculate:**
- `bugsB` = `response.count` → **"Opened During this week (B)"** for SOA Bugs

---

### API Call 4 — `HTTP: Bugs Open End`
**Filter field:** `bugsOpenEndFilter`  
**Filters applied:** `proj` + `yr` + `open` + `bug` + `noStage`

```json
[
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["<weekEnd−365d>", "<weekEnd>"] } },
  { "status":       { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```

**What it fetches:** All open API Bug tickets (non-STAGE) created in the last year  
**Used to calculate:**
- `bugsOpenEnd` = `response.count` → **"Open: End of this week (A + B − C)"** for SOA Bugs

---

### API Call 5 — `HTTP: Dev Tasks`
**Filter field:** `devTasksFilter`  
**Filters applied:** `proj` + `open` + `yr` + `updated`

```json
[
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "status":    { "operator": "=",   "values": ["39","44","88",...] } },
  { "createdAt": { "operator": "<>d", "values": ["<weekEnd−365d>", "<weekEnd>"] } },
  { "updatedAt": { "operator": "<>d", "values": ["<weekStart>", "<weekEnd>"] } }
]
```

**What it fetches:** Any open work package (any type, including bugs) updated this week  
**Used to calculate:**
- Developer Tasks table in email — grouped by `assignee` and `responsible` person
- Each person shows: `<Type> #<ID>: <Subject>`
- A ticket appearing on both assignee and responsible person's list is intentional

---

### API Call 6 — `HTTP: Tasks Detail`
**Filter field:** `tasksDetailFilter`  
**Filters applied:** `proj` + `open` + `yr` + `notBug` + `updated`

```json
[
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "status":    { "operator": "=",   "values": ["39","44","88",...] } },
  { "createdAt": { "operator": "<>d", "values": ["<weekEnd−365d>", "<weekEnd>"] } },
  { "type":      { "operator": "!",   "values": ["19"] } },
  { "updatedAt": { "operator": "<>d", "values": ["<weekStart>", "<weekEnd>"] } }
]
```

**What it fetches:** Open non-bug tasks updated this week (last year's scope)  
**Used for:** Rows written to the **`TasksDetails`** Google Sheet tab

---

### API Call 7 — `HTTP: Bugs Detail`
**Filter field:** `bugsDetailFilter`  
**Filters applied:** `proj` + `open` + `yr` + `bug` + `noStage` + `updated`

```json
[
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "status":       { "operator": "=",   "values": ["39","44","88",...] } },
  { "createdAt":    { "operator": "<>d", "values": ["<weekEnd−365d>", "<weekEnd>"] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } },
  { "updatedAt":    { "operator": "<>d", "values": ["<weekStart>", "<weekEnd>"] } }
]
```

**What it fetches:** Open API Bug tickets (non-STAGE) updated this week  
**Used for:** Rows written to the **`BugsDetails`** Google Sheet tab

---

## 5. Metrics Calculation (Code: Build Report)

### Direct from API Responses

| Metric         | Source Node           | How Calculated |
|----------------|-----------------------|----------------|
| `merp_B`       | HTTP: Merp Opened     | `response.elements.length` |
| `merpOpenEnd`  | HTTP: Merp Open End   | `response.elements.length` |
| `merpBacklog`  | HTTP: Merp Open End   | count where `_links.status` ID = `1` |
| `merpWip`      | HTTP: Merp Open End   | `merpOpenEnd − merpBacklog` |
| `bugsB`        | HTTP: Bugs Opened     | `response.elements.length` |
| `bugsOpenEnd`  | HTTP: Bugs Open End   | `response.elements.length` |
| `business`     | HTTP: Merp Opened     | count where `_links.type` ID = `15` (Story) |
| `internal`     | HTTP: Merp Opened     | `merp_B − business` |

### Derived via Rolling 4-Week Cache

The workflow maintains a cache in `$getWorkflowStaticData('global').cache` keyed by `"YYYY-MM-DD_YYYY-MM-DD"` (weekStart_weekEnd).

```
Cache key example: "2026-06-22_2026-06-28"
Cache value: {
  merp_B, merp_C, merp_open, merp_wip, merp_backlog,
  bugs_B,  bugs_C,  bugs_open,
  biz_opened, int_opened,
  dev_tasks: { "PersonName": [{id, subject, type}, ...] }
}
```

**Before HTML generation**, the 4-week window `[week-3, week-2, week-1, current]` is built from cache.

For each row in the window:

| Metric         | How Calculated |
|----------------|----------------|
| `merp_A`       | Oldest row: `merp_open − merp_B + merp_C` (back-calculate). All others: previous row's `merp_open` |
| `merp_C`       | Current week only (i=3): `merp_A + merp_B − merp_open`. Then stored back to cache |
| `bugs_A`       | Same logic as `merp_A` |
| `bugs_C`       | Current week only (i=3): `bugs_A + bugs_B − bugs_open`. Then stored back to cache |

**Pre-seeded cache values** (so first run produces a valid 4-week table):

| Week                  | merp_B | merp_C | merp_open | merp_wip | merp_backlog | bugs_B | bugs_C | bugs_open | biz | int |
|-----------------------|--------|--------|-----------|----------|--------------|--------|--------|-----------|-----|-----|
| 2026-05-31–2026-06-06 | 32     | 15     | 124       | 103      | 21           | 13     | 18     | 16        | 17  | 15  |
| 2026-06-07–2026-06-13 | 20     | 21     | 123       | 101      | 22           | 9      | 13     | 12        | 10  | 10  |
| 2026-06-14–2026-06-20 | 22     | 38     | 107       | 92       | 15           | 7      | 5      | 14        | 13  | 9   |

---

## 6. Email Report Structure

**To:** `bireports@indiamart.com`  
**CC:** `puneet.agarwal@indiamart.com`, `vipul.bansal1@indiamart.com`  
**Subject:** `BI Weekly Report :BI SOA Task Status Report : 22 Jun - 28 Jun 2026`

### Section 1 — Key Highlights (auto-generated bullets)
- Closed tasks change vs previous week
- Open bugs change vs previous week

### Section 2 — Report Summary Table (6 columns: 4 weeks + +/- Last Week)

**Merp SOA Tasks rows:**

| Row Label                         | Value Source |
|-----------------------------------|--------------|
| Open: Beginning of this week (A)  | Cache: prev week's `merp_open` |
| Opened During this week (B)       | Live: `merp_B` from HTTP: Merp Opened |
| Closed During this week (C)       | Derived: `merp_A + merp_B − merp_open` |
| Open: End of this week (A + B − C)| Live: `merpOpenEnd` from HTTP: Merp Open End |
| Items in Under Development (WIP)  | Live: `merpWip` (open end minus backlog) |
| Backlog (Yet to align)            | Live: `merpBacklog` (status ID = 1) |

**SOA Bugs rows:**

| Row Label                         | Value Source |
|-----------------------------------|--------------|
| Open: Beginning of this week (A)  | Cache: prev week's `bugs_open` |
| Opened During this week (B)       | Live: `bugsB` from HTTP: Bugs Opened |
| Closed During this week (C)       | Derived: `bugs_A + bugs_B − bugs_open` |
| Open: End of this week (A + B − C)| Live: `bugsOpenEnd` from HTTP: Bugs Open End |

### Section 3 — Bifurcation Table (6 columns: 4 weeks + +/- Last Week)

| Row Label                             | Value Source |
|---------------------------------------|--------------|
| Total Opened Tickets this week (A=B+C)| `merp_B` (same as Opened During week) |
| Business Tickets (B)                  | `business` = Story-type tickets from HTTP: Merp Opened |
| Internally Opened Tickets (C)         | `internal` = `merp_B − business` |

### Section 4 — Developer Tasks Table
- One row per developer per ticket
- Grouped by person (assignee OR responsible)
- Shows: `<Type> #<ID>: <Subject>`
- Source: HTTP: Dev Tasks (any open ticket updated this week)

### Color Coding for % Change Column

| Color  | Condition | Meaning |
|--------|-----------|---------|
| Yellow | `|%| ≤ 5%` | Negligible change |
| Green  | `|%| > 5%` and direction is good | Improvement |
| Red    | `|%| > 5%` and direction is bad | Degradation |

**"Good" direction per row:**
- Higher is better (green ▲): Closed (C), WIP, Business, Internal
- Lower is better (green ▼): Open Beginning (A), Open End, Backlog, Open Bugs

---

## 7. Google Sheets Integration

**Spreadsheet ID:** `1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q`  
**URL:** `https://docs.google.com/spreadsheets/d/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q`

### Sheet Tabs

| Tab Name       | Content |
|----------------|---------|
| `TasksDetails` | Open non-bug tickets updated this week |
| `BugsDetails`  | Open API Bug tickets (env ≠ STAGE) updated this week |

### Columns (both tabs)

| Column       | Source Field |
|--------------|-------------|
| `ID`         | `wp.id` |
| `Subject`    | `wp.subject` |
| `Type`       | `_links.type.title` |
| `Status`     | `_links.status.title` |
| `Author`     | `_links.author.title` |
| `Assignee`   | `_links.assignee.title` |
| `Accountable`| `_links.responsible.title` |
| `Updated on` | `wp.updatedAt` (first 16 chars, `T` → space) |
| `Created on` | `wp.createdAt` (first 16 chars, `T` → space) |
| `Week Of`    | Label like `"22 Jun - 28 Jun"` |

### Sheet Operation Flow per Run

1. **HTTP: Create Tasks Tab** — calls `POST https://sheets.googleapis.com/v4/spreadsheets/<ID>:batchUpdate`  
   Body: `{"requests":[{"addSheet":{"properties":{"title":"TasksDetails"}}}]}`  
   `continueOnFail: true` — if tab already exists, API returns error but workflow continues

2. **HTTP: Create Bugs Tab** — same for `BugsDetails`

3. **GSheets: Clear Tasks** — clears all existing data from `TasksDetails` (`continueOnFail: true`)

4. **GSheets: Clear Bugs** — clears all existing data from `BugsDetails` (`continueOnFail: true`)

5. **Code: To Task Rows** — expands `tasksRows` array into individual items

6. **GSheets: Append Tasks** — appends all task rows (auto-maps JSON keys to column names)

7. **Code: To Bug Rows** — expands `bugsRows` array into individual items

8. **GSheets: Append Bugs** — appends all bug rows

---

## 8. Credential Setup (One-Time)

| Credential | Where Used | What to Set |
|------------|-----------|-------------|
| OpenProject API Token | `Code: Setup` node → replace `YOUR_OP_TOKEN_HERE` | Your OP personal access token |
| Google Sheets OAuth2 | All `GSheets:*` nodes + `HTTP: Create *` nodes → credential named `"Google Sheets account"` with ID `GOOGLE_SHEETS_CREDENTIAL_ID` | OAuth2 with Sheets + Drive scopes |

---

## 9. API Call Summary

| # | Node                   | Method | Target                          | Data Purpose |
|---|------------------------|--------|---------------------------------|--------------|
| 1 | HTTP: Merp Opened      | GET    | OpenProject work_packages       | Opened this week (non-bug) |
| 2 | HTTP: Merp Open End    | GET    | OpenProject work_packages       | Open end of week (non-bug) |
| 3 | HTTP: Bugs Opened      | GET    | OpenProject work_packages       | Bug tickets opened this week |
| 4 | HTTP: Bugs Open End    | GET    | OpenProject work_packages       | Open bugs end of week |
| 5 | HTTP: Dev Tasks        | GET    | OpenProject work_packages       | All open tickets updated this week |
| 6 | HTTP: Tasks Detail     | GET    | OpenProject work_packages       | Non-bug tickets for Sheets |
| 7 | HTTP: Bugs Detail      | GET    | OpenProject work_packages       | Bug tickets for Sheets |
| 8 | HTTP: Create Tasks Tab | POST   | Google Sheets batchUpdate API   | Create TasksDetails tab |
| 9 | HTTP: Create Bugs Tab  | POST   | Google Sheets batchUpdate API   | Create BugsDetails tab |

**Total: 9 external API calls per execution**
