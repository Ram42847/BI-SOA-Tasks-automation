# SOA Monthly Report — n8n Workflow Documentation

**File:** `n8n_monthly_workflow.json` (20 nodes)  
**Generator:** `generate_n8n_monthly_workflow.py`  
**Schedule:** 1st of every month at 8:00 PM (`0 20 1 * *`)  
**Report period:** Full previous calendar month (e.g., runs July 1 → reports June 1–30)

---

## 1. Node Chain (Sequential)

```
Manual Trigger ──┐
                 ├──→  Code: Setup Monthly
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
                  HTTP: Tasks Detail         [API call 5]
                         │
                         ▼
                  HTTP: Bugs Detail          [API call 6]
                         │
                         ▼
                  Code: Build Report Monthly
                         │
                         ▼
                  HTTP: Create Tasks Tab     [Sheets API — continueOnFail]
                         │
                         ▼
                  HTTP: Create Bugs Tab      [Sheets API — continueOnFail]
                         │
                         ▼
                  GSheets: Clear Tasks (M)   [continueOnFail]
                         │
                         ▼
                  GSheets: Clear Bugs (M)    [continueOnFail]
                         │
                         ▼
                  Code: To Task Rows (M)
                         │
                         ▼
                  GSheets: Append Tasks (M)
                         │
                         ▼
                  Code: To Bug Rows (M)
                         │
                         ▼
                  GSheets: Append Bugs (M)
                         │
                         ▼
                  Code: Restore Email (M)
                         │
                         ▼
                  Send Email via Gmail
```

> **Difference vs Weekly:** No `HTTP: Dev Tasks` node — monthly report has no Developer Tasks table.

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

| Constant              | Value | Meaning |
|-----------------------|-------|---------|
| `PROJECT_ID`          | `75`  | MERP Services project |
| `API_BUG_TYPE_ID`     | `19`  | Work package type = "API Bug" |
| `API_STORY_TYPE_ID`   | `15`  | Work package type = "Story" (Business tickets) |
| `ENV_STAGE_OPTION_ID` | `22`  | Custom Field 9 option = "STAGE" environment |
| `YEAR_LOOKBACK_DAYS`  | `365` | Look-back window for "open end of month" query |

---

## 3. Filter Building Blocks

All filters are combined as a JSON array: `[proj, ...extras]`

| Variable        | Field          | Operator | Value(s)                          | Meaning |
|-----------------|----------------|----------|-----------------------------------|---------|
| `proj`          | `project`      | `=`      | `["75"]`                          | Only MERP Services project |
| `open`          | `status`       | `=`      | 54 open status IDs (see below)    | Work package is open |
| `notBug`        | `type`         | `!`      | `["19"]`                          | Exclude API Bug type |
| `bug`           | `type`         | `=`      | `["19"]`                          | Only API Bug type |
| `noStage`       | `customField9` | `!`      | `["22"]`                          | Exclude env = STAGE |
| `yr`            | `createdAt`    | `<>d`    | `[monthEnd − 365 days, monthEnd]` | Created within the last year (as of month end) |
| `created_month` | `createdAt`    | `<>d`    | `[monthStart, monthEnd]`          | Created within the reported month |
| `updated_month` | `updatedAt`    | `<>d`    | `[monthStart, monthEnd]`          | Last updated within the reported month |

**Month boundaries** (computed at runtime):
```
monthStart = 1st day of previous calendar month   e.g. 2026-06-01
monthEnd   = last day of previous calendar month  e.g. 2026-06-30
```
Computed as: `ms = new Date(today.getFullYear(), today.getMonth()-1, 1)` and `me = new Date(today.getFullYear(), today.getMonth(), 0)`

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
**Filters applied:** `proj` + `created_month` + `open` + `notBug`

```json
[
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["<monthStart>", "<monthEnd>"] } },
  { "status":    { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```

**What it fetches:** Non-bug work packages created during the reported month that are still open  
**Used to calculate:**
- `merpB` = `response.elements.length` → **"Opened During this month (B)"** for Merp SOA Tasks
- `business` = count where `_links.type` ID = 15 (Story) → **"Business Tickets (B)"**
- `internal` = `merpB − business` → **"Internally Opened Tickets (C)"**

---

### API Call 2 — `HTTP: Merp Open End`
**Filter field:** `merpOpenEndFilter`  
**Filters applied:** `proj` + `yr` + `open` + `notBug`

```json
[
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["<monthEnd−365d>", "<monthEnd>"] } },
  { "status":    { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":      { "operator": "!",   "values": ["19"] } }
]
```

**What it fetches:** All non-bug work packages that are open at end of month (created within last year)  
**Used to calculate:**
- `merpOpenEnd` = `response.elements.length` → **"Open: End of this month (A + B − C)"**
- `merpBacklog` = count where `_links.status` ID = 1 → **"Backlog (Yet to align)"**
- `merpWip` = `merpOpenEnd − merpBacklog` → **"Items in Under Development (WIP)"**

---

### API Call 3 — `HTTP: Bugs Opened`
**Filter field:** `bugsOpenedFilter`  
**Filters applied:** `proj` + `created_month` + `open` + `bug` + `noStage`

```json
[
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["<monthStart>", "<monthEnd>"] } },
  { "status":       { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```

**What it fetches:** API Bug tickets created this month, open, and NOT in STAGE environment  
**Used to calculate:**
- `bugsB` = `response.elements.length` → **"Opened During this month (B)"** for SOA Bugs

---

### API Call 4 — `HTTP: Bugs Open End`
**Filter field:** `bugsOpenEndFilter`  
**Filters applied:** `proj` + `yr` + `open` + `bug` + `noStage`

```json
[
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["<monthEnd−365d>", "<monthEnd>"] } },
  { "status":       { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } }
]
```

**What it fetches:** All open API Bug tickets (non-STAGE) created in the last year  
**Used to calculate:**
- `bugsOpenEnd` = `response.elements.length` → **"Open: End of this month (A + B − C)"** for SOA Bugs

---

### API Call 5 — `HTTP: Tasks Detail`
**Filter field:** `tasksDetailFilter`  
**Filters applied:** `proj` + `yr` + `open` + `notBug` + `updated_month`

```json
[
  { "project":   { "operator": "=",   "values": ["75"] } },
  { "createdAt": { "operator": "<>d", "values": ["<monthEnd−365d>", "<monthEnd>"] } },
  { "status":    { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":      { "operator": "!",   "values": ["19"] } },
  { "updatedAt": { "operator": "<>d", "values": ["<monthStart>", "<monthEnd>"] } }
]
```

**What it fetches:** Open non-bug tasks updated during the reported month  
**Used for:** Rows written to the **`{MonthName}MonthsTasksDetails`** Google Sheet tab  
*(e.g., `JuneMonthsTasksDetails` for June 2026)*

---

### API Call 6 — `HTTP: Bugs Detail`
**Filter field:** `bugsDetailFilter`  
**Filters applied:** `proj` + `yr` + `open` + `bug` + `noStage` + `updated_month`

```json
[
  { "project":      { "operator": "=",   "values": ["75"] } },
  { "createdAt":    { "operator": "<>d", "values": ["<monthEnd−365d>", "<monthEnd>"] } },
  { "status":       { "operator": "=",   "values": ["39","44","88",...] } },
  { "type":         { "operator": "=",   "values": ["19"] } },
  { "customField9": { "operator": "!",   "values": ["22"] } },
  { "updatedAt":    { "operator": "<>d", "values": ["<monthStart>", "<monthEnd>"] } }
]
```

**What it fetches:** Open API Bug tickets (non-STAGE) updated during the reported month  
**Used for:** Rows written to the **`{MonthName}MonthsBugsDetails`** Google Sheet tab  
*(e.g., `JuneMonthsBugsDetails` for June 2026)*

---

## 5. Metrics Calculation (Code: Build Report Monthly)

### Direct from API Responses

| Metric         | Source Node           | How Calculated |
|----------------|-----------------------|----------------|
| `merpB`        | HTTP: Merp Opened     | `response.elements.length` |
| `merpOpenEnd`  | HTTP: Merp Open End   | `response.elements.length` |
| `merpBacklog`  | HTTP: Merp Open End   | count where `_links.status` ID = `1` |
| `merpWip`      | HTTP: Merp Open End   | `merpOpenEnd − merpBacklog` |
| `bugsB`        | HTTP: Bugs Opened     | `response.elements.length` |
| `bugsOpenEnd`  | HTTP: Bugs Open End   | `response.elements.length` |
| `business`     | HTTP: Merp Opened     | count where `_links.type` ID = `15` (Story) |
| `internal`     | HTTP: Merp Opened     | `merpB − business` |

### Derived via Rolling 4-Month Cache

The workflow maintains a cache in `$getWorkflowStaticData('global').mcache` (separate key `mcache` from the weekly `cache` to avoid collision if both workflows share n8n static data).

**Cache key format:** `"YYYY-MM"` (e.g., `"2026-06"`)  
**Cache value:**
```
{
  merp_B,       // Opened during month (non-bug)
  merp_C,       // Closed during month (derived, stored after computation)
  merp_open,    // Open end of month (non-bug)
  merp_wip,     // WIP count at end of month
  merp_backlog, // Backlog count at end of month
  bugs_B,       // Bugs opened during month
  bugs_C,       // Bugs closed (derived, stored after computation)
  bugs_open,    // Open bugs end of month
  biz_opened,   // Business (Story-type) tickets opened
  int_opened    // Internally opened tickets
}
```

**Before HTML generation**, the 4-month window `[month-3, month-2, month-1, current]` is built from cache.

For each row in the window:

| Metric    | How Calculated |
|-----------|----------------|
| `merp_A`  | Oldest row (i=0): `merp_open − merp_B + merp_C` (back-calculate). All others (i>0): previous row's `merp_open` |
| `merp_C`  | Current month only (i=3): `merp_A + merp_B − merp_open`. Written back to `mcache[currKey].merp_C` |
| `bugs_A`  | Same logic as `merp_A` using bugs values |
| `bugs_C`  | Current month only (i=3): `bugs_A + bugs_B − bugs_open`. Written back to `mcache[currKey].bugs_C` |

**Pre-seeded cache values** (so first run produces a valid 4-month table):

| Month   | Label            | merp_B | merp_C | merp_open | merp_wip | merp_backlog | bugs_B | bugs_C | bugs_open | biz | int |
|---------|------------------|--------|--------|-----------|----------|--------------|--------|--------|-----------|-----|-----|
| 2026-03 | 01 Mar - 31 Mar  | 64     | 29     | 206       | 124      | 82           | 24     | 10     | 30        | 11  | 53  |
| 2026-04 | 01 Apr - 30 Apr  | 74     | 99     | 181       | 95       | 86           | 24     | 25     | 29        | 35  | 39  |
| 2026-05 | 01 May - 31 May  | 96     | 170    | 107       | 88       | 19           | 40     | 10     | 21        | 46  | 50  |

When June 2026 runs, the report table will show: **Mar | Apr | May | Jun**

---

## 6. Email Report Structure

**To:** `bireports@indiamart.com`  
**CC:** `puneet.agarwal@indiamart.com`, `vipul.bansal1@indiamart.com`  
**Subject:** `BI Monthly Report :BI SOA Task Status Report : June 2026`  
**Body intro:** `Please find the Monthly Task Report of BI-SOA from 01 June to 30 June 2026.`

### Section 1 — Key Highlights (auto-generated bullets)
- Closed tasks change vs previous month (% with color arrow)
- Open bugs change vs previous month (% with color arrow)

### Section 2 — Report Summary Table (6 columns: 4 months + +/- Last Month)

**Column header format:** `01 Feb - 28 Feb` (zero-padded day + 3-letter month)

**Merp SOA Tasks rows:**

| Row Label                          | Value Source |
|------------------------------------|--------------|
| Open: Beginning of this month (A)  | Cache: previous month's `merp_open` |
| Opened During this month (B)       | Live: `merpB` from HTTP: Merp Opened |
| Closed During this month (C)       | Derived: `merp_A + merp_B − merp_open` |
| Open: End of this month (A + B − C)| Live: `merpOpenEnd` from HTTP: Merp Open End |
| Items in Under Development (WIP)   | Live: `merpWip` |
| Backlog (Yet to align)             | Live: `merpBacklog` |

**SOA Bugs rows:**

| Row Label                          | Value Source |
|------------------------------------|--------------|
| Open: Beginning of this month (A)  | Cache: previous month's `bugs_open` |
| Opened During this month (B)       | Live: `bugsB` from HTTP: Bugs Opened |
| Closed During this month (C)       | Derived: `bugs_A + bugs_B − bugs_open` |
| Open: End of this month (A + B − C)| Live: `bugsOpenEnd` from HTTP: Bugs Open End |

### Section 3 — Bifurcation Table (6 columns: 4 months + +/- Last Month)

| Row Label                              | Value Source |
|----------------------------------------|--------------|
| Total Opened Tickets this month (A=B+C)| `merpB` (same as Opened During month) |
| Business Tickets (B)                   | `business` = Story-type tickets from HTTP: Merp Opened |
| Internally Opened Tickets (C)          | `internal` = `merpB − business` |

> **Note:** Monthly report has NO Developer Tasks table (unlike weekly).

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

### Sheet Tabs (Dynamic — created automatically each month)

| Tab Name Pattern              | Example (June 2026)         | Content |
|-------------------------------|-----------------------------|---------|
| `{MonthName}MonthsTasksDetails` | `JuneMonthsTasksDetails`   | Open non-bug tickets updated in June |
| `{MonthName}MonthsBugsDetails`  | `JuneMonthsBugsDetails`    | Open API Bug tickets (env ≠ STAGE) updated in June |

The tab name is computed in `Code: Build Report Monthly` as:
```javascript
const sheetTabTasks = `${monthName}MonthsTasksDetails`;  // e.g. "JuneMonthsTasksDetails"
const sheetTabBugs  = `${monthName}MonthsBugsDetails`;   // e.g. "JuneMonthsBugsDetails"
```

These are stored in the output JSON and referenced in all downstream nodes via:  
`={{ $('Code: Build Report Monthly').first().json.sheetTabTasks }}`

### Columns (both tabs)

| Column        | Source Field |
|---------------|-------------|
| `ID`          | `wp.id` |
| `Subject`     | `wp.subject` |
| `Type`        | `_links.type.title` |
| `Status`      | `_links.status.title` |
| `Author`      | `_links.author.title` |
| `Assignee`    | `_links.assignee.title` |
| `Accountable` | `_links.responsible.title` |
| `Updated on`  | `wp.updatedAt` (first 16 chars, `T` → space) |
| `Created on`  | `wp.createdAt` (first 16 chars, `T` → space) |
| `Month Of`    | Label like `"01 Jun - 30 Jun"` |

### Sheet Operation Flow per Run

1. **HTTP: Create Tasks Tab** — `POST https://sheets.googleapis.com/v4/spreadsheets/<ID>:batchUpdate`  
   Body (dynamic): `{"requests":[{"addSheet":{"properties":{"title":"JuneMonthsTasksDetails"}}}]}`  
   `continueOnFail: true` — tab already existing returns an error, workflow continues

2. **HTTP: Create Bugs Tab** — same for `JuneMonthsBugsDetails`

3. **GSheets: Clear Tasks (M)** — clears the tasks tab (`continueOnFail: true` — safe on freshly created empty tab)

4. **GSheets: Clear Bugs (M)** — clears the bugs tab (`continueOnFail: true`)

5. **Code: To Task Rows (M)** — expands `tasksRows` array from Build Report output into individual items

6. **GSheets: Append Tasks (M)** — appends all task rows (auto-maps JSON keys to column names)

7. **Code: To Bug Rows (M)** — expands `bugsRows` array into individual items

8. **GSheets: Append Bugs (M)** — appends all bug rows

---

## 8. Credential Setup (One-Time)

| Credential | Where Used | What to Set |
|------------|-----------|-------------|
| OpenProject API Token | `Code: Setup Monthly` node → replace `YOUR_OP_TOKEN_HERE` | Your OP personal access token |
| Google Sheets OAuth2 | All `GSheets:*` nodes + `HTTP: Create *` nodes → credential named `"Google Sheets account"` with ID `GOOGLE_SHEETS_CREDENTIAL_ID` | OAuth2 with Sheets + Drive scopes |

---

## 9. API Call Summary

| # | Node                   | Method | Target                        | Data Purpose |
|---|------------------------|--------|-------------------------------|--------------|
| 1 | HTTP: Merp Opened      | GET    | OpenProject work_packages     | Opened this month (non-bug) |
| 2 | HTTP: Merp Open End    | GET    | OpenProject work_packages     | Open end of month (non-bug) |
| 3 | HTTP: Bugs Opened      | GET    | OpenProject work_packages     | Bug tickets opened this month |
| 4 | HTTP: Bugs Open End    | GET    | OpenProject work_packages     | Open bugs end of month |
| 5 | HTTP: Tasks Detail     | GET    | OpenProject work_packages     | Non-bug tickets for Sheets |
| 6 | HTTP: Bugs Detail      | GET    | OpenProject work_packages     | Bug tickets for Sheets |
| 7 | HTTP: Create Tasks Tab | POST   | Google Sheets batchUpdate API | Create `{Month}MonthsTasksDetails` tab |
| 8 | HTTP: Create Bugs Tab  | POST   | Google Sheets batchUpdate API | Create `{Month}MonthsBugsDetails` tab |

**Total: 8 external API calls per execution**

---

## 10. Key Differences vs Weekly Workflow

| Aspect                  | Weekly                          | Monthly |
|-------------------------|---------------------------------|---------|
| Schedule                | Every Sunday 8 PM               | 1st of each month 8 PM |
| Report period           | Sun–Sat (most recent full week) | Previous full calendar month |
| Period label format     | `22 Jun - 28 Jun`               | `01 Jun - 30 Jun` (zero-padded) |
| Rolling window          | 4 weeks                         | 4 months |
| Cache key               | `"YYYY-MM-DD_YYYY-MM-DD"`       | `"YYYY-MM"` |
| Cache namespace         | `staticData.cache`              | `staticData.mcache` |
| API calls (OP)          | 7 (includes Dev Tasks)          | 6 (no Dev Tasks) |
| Developer Tasks table   | Yes                             | No |
| Sheet tab names         | Fixed: `TasksDetails`, `BugsDetails` | Dynamic: `JuneMonthsTasksDetails`, etc. |
| Sheet tab creation      | Auto-created via Sheets API     | Auto-created via Sheets API (new tab each month) |
| Email subject           | `BI Weekly Report :BI SOA Task Status Report : 22 Jun - 28 Jun 2026` | `BI Monthly Report :BI SOA Task Status Report : June 2026` |
| Total API calls         | 9                               | 8 |
| Total nodes             | 21                              | 20 |
