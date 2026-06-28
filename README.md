# SOA Weekly Task Status Report

Automates the **BI SOA Task Status Report** email for the MERP Services project (id=75) on OpenProject. Generates the same 4-week rolling HTML report that was previously compiled manually.

## What it produces

- **Key Highlights** — % change in closed tasks and open bugs vs previous week
- **Report Summary table** — 4-week rolling window with color-coded +/- column
  - Merp SOA Tasks: opened (B), closed (C), open beginning (A), open end, WIP, backlog
  - SOA Bugs: same metrics, API Bug type only, excluding STAGE environment tickets
- **Bifurcation table** — business vs internally opened tickets breakdown
- **Developer tasks table** — all tickets updated during the current week, grouped by developer

## Color coding

The `(+/- Last Week)` column uses light background + matching dark bold text (Excel conditional-format palette):

| Cell color | Background | Text | When |
|---|---|---|---|
| Green | `#C6EFCE` | `#375623` dark green | Good direction (>5% change) |
| Pink | `#FFC7CE` | `#9C0006` dark red | Bad direction (>5% change) |
| Amber | `#FFEB9C` | `#9C6500` dark amber | Neutral (≤5% change) |

"Good" direction is context-aware per row (Config column in the source Excel):

| Row | Config | Good direction |
|---|---|---|
| Open Beginning (A) | L | ↓ decrease |
| Opened (B) | L | ↓ decrease |
| Closed (C) | H | ↑ increase |
| Open End | L | ↓ decrease |
| WIP | H | ↑ increase |
| Backlog | L | ↓ decrease |
| Business / Internal tickets | H | ↑ increase |

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure `.env`**

```env
# OpenProject (already set)
OP_URL=https://project.intermesh.net
OP_TOKEN=your_token_here

# Email (add these to send the report)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=ramlal.suthar@indiamart.com
SMTP_PASS=your_app_password
MAIL_FROM=ramlal.suthar@indiamart.com
MAIL_TO=bireports@indiamart.com
MAIL_CC=puneet.agarwal@indiamart.com,vipul.bansal1@indiamart.com
```

> For Gmail, use an [App Password](https://myaccount.google.com/apppasswords) instead of your account password.

## Usage

```bash
# Preview: save HTML and open in browser
python report.py --output report.html

# Send email
python report.py --send

# Generate for a specific past week (pass the Sunday start date)
python report.py --week 2026-06-21 --output report.html

# Also export current-week detail sheets to Excel
python report.py --week 2026-06-21 --output report.html --excel details.xlsx

# Re-fetch current week fresh (historical weeks always load from cache)
python report.py --output report.html
```

## Automate with cron

Run every **Sunday at 8 PM** to send the report right after the week closes:

```bash
crontab -e
```

Add this line:

```
0 20 * * 0 cd /home/ramlal/mycode/open_project/soa-weekly-report && python3 report.py --send >> /tmp/soa_report.log 2>&1
```

## How metrics are calculated

### Merp SOA Tasks

Tickets of **any type except API Bug** (type id 19), created within the last 1 year.

| Metric | Filter |
|---|---|
| Opened (B) | `createdAt` in week + currently open + not API Bug |
| Open End | currently open + not API Bug + created last 1 year |
| WIP | Open End minus tickets in "To Do" status |
| Backlog | tickets in "To Do" status |
| Open Beginning (A) | previous week's Open End (from cache) |
| Closed (C) | A + B − Open End (formula, no separate API call) |

### SOA Bugs

Tickets of **type = API Bug** (type id 19) **and Environment ≠ STAGE** (customField9 ≠ option id 22).

Same A / B / C / Open End formula as Merp SOA Tasks.

### Bifurcation

Splits the Merp "Opened (B)" count into:
- **Business Tickets** — type = API Story (type id 15)
- **Internally Opened** — all other opened tickets

### Developer tasks table

Open tickets (any type, last 1 year) with `updatedAt` in the current week.  
Each ticket is credited to **both assignee and responsible person**.

## Cache

Each week's data is saved to `weekly_data_cache.json` after the first fetch.

- Historical weeks (past 3) are **loaded from cache** and never re-fetched.
- The current week is **always re-fetched** on every run.
- Open Beginning (A) for the current week = previous week's Open End from cache.
- To reset and re-seed the cache from known-good values, update `weekly_data_cache.json` directly with the PDF/manual report figures, then re-run.

> **Best accuracy:** run on Sunday or Monday right after the week closes.

## Excel detail sheets (`--excel`)

Generates two sheets for the **current week**:

| Sheet | Contents |
|---|---|
| `21June-27JuneTasksDetails` | Open tickets, not API Bug, updated in week |
| `21June-27JuneBugsDetails` | Open API Bug tickets, Environment ≠ STAGE, updated in week |

Columns: ID, Project, Subject, Type, Status, Author, Assignee, Accountable, Updated on, Created on.

## Configuration reference

All IDs are defined at the top of `report.py`:

| Variable | Default | Description |
|---|---|---|
| `PROJECT_ID` | `75` | OpenProject project ID (MERP Services) |
| `YEAR_LOOKBACK_DAYS` | `365` | Ticket age limit for open/WIP/backlog counts |
| `API_BUG_TYPE_ID` | `19` | Type ID for API Bug (SOA Bugs section) |
| `API_STORY_TYPE_ID` | `15` | Type ID for API Story (Business tickets in bifurcation) |
| `ENV_STAGE_OPTION_ID` | `"22"` | customField9 option ID for "STAGE" environment (excluded from bugs) |
| `BACKLOG_STATUS_IDS` | `{1}` | Status IDs treated as backlog ("To Do") |

## Files

```
soa-weekly-report/
├── report.py                # Main script
├── requirements.txt         # Python dependencies  (requests, python-dotenv, openpyxl)
├── .env                     # Credentials and email config (not committed)
├── weekly_data_cache.json   # Auto-created; stores historical weekly snapshots
└── README.md
```
