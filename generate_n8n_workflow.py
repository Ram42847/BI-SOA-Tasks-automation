#!/usr/bin/env python3
"""Generates n8n_workflow.json — split architecture: HTTP Request nodes for API calls."""
import json, uuid
from pathlib import Path

SHEET_ID  = '1xK11zA-7yEEOPFROe1uKLOTnsh9jDXch6owK6szd3-0'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}'

# Persistent on-disk cache — same file report.py reads/writes, so history survives
# workflow re-imports/redeploys (n8n's $getWorkflowStaticData resets on those).
# Must be a path the n8n process itself can read/write. If n8n is self-hosted with
# N8N_RESTRICT_FILE_ACCESS_TO set, add this directory to that allow-list.
CACHE_FILE_PATH = '/home/ramlal/mycode/open_project/soa-weekly-report/weekly_data_cache.json'

# ── Code: Setup ───────────────────────────────────────────────────────────────
JS_SETUP = r"""// Replace YOUR_OP_TOKEN_HERE with your actual OpenProject API token
const OP_TOKEN = 'YOUR_OP_TOKEN_HERE';

const PROJECT_ID          = 75;
const YEAR_LOOKBACK_DAYS  = 365;
const API_BUG_TYPE_ID     = 19;
const ENV_STAGE_OPTION_ID = '22';
const TODO_STATUS_ID      = '1';

// Pure-JS Base64 — works even if Buffer is unavailable in this n8n version
function _b64(str) {
  if (typeof Buffer !== 'undefined') return Buffer.from(str).toString('base64');
  const C = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const b = Array.from(str).map(c => c.charCodeAt(0));
  let o = '', i = 0;
  while (i < b.length) {
    const b0=b[i++], b1=b[i], b2=b[i+1]; i+=2;
    o += C[b0>>2]+C[((b0&3)<<4)|(b1>>4||0)]+
         (b1===undefined?'=':C[((b1&15)<<2)|(b2>>6||0)])+
         (b2===undefined?'=':C[b2&63]);
  }
  return o;
}
const authHeader = 'Basic ' + _b64('apikey:' + OP_TOKEN);

function toISO(d) { return d.toISOString().slice(0, 10); }
function addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r; }

const today = new Date(); today.setHours(0,0,0,0);
const pyDay = (today.getDay() + 6) % 7;
let dsSat = ((pyDay - 5) % 7 + 7) % 7;
if (dsSat === 0) dsSat = 7;
const sat = addDays(today, -dsSat);
const sun = addDays(sat, -6);
const ws  = toISO(sun), we = toISO(sat);
const cutoff = toISO(addDays(sun, -YEAR_LOOKBACK_DAYS));  // from weekStart, matching UI

const bugIds  = [String(API_BUG_TYPE_ID)];
const proj    = { project:      { operator: '=',   values: [String(PROJECT_ID)] } };
const openSt  = { status:       { operator: 'o',   values: [] } };               // Status: open
const todo    = { status:       { operator: '=',   values: [TODO_STATUS_ID] } }; // Status: is To Do
const notBug  = { type:         { operator: '!',   values: bugIds } };
const bug     = { type:         { operator: '=',   values: bugIds } };
const noStage = { customField9: { operator: '!',   values: [ENV_STAGE_OPTION_ID] } };
const created = { createdAt:    { operator: '<>d', values: [ws, we] } };  // created this week
const yr      = { createdAt:    { operator: '<>d', values: [cutoff, we] } }; // created last year
const updated = { updatedAt:    { operator: '<>d', values: [ws, we] } };  // updated this week

const fj = (...extras) => JSON.stringify([proj, ...extras]);

return [{ json: {
  authHeader,
  weekStart:          ws,
  weekEnd:            we,
  merpOpenedFilter:   fj(created, notBug),           // Status=all, created this week, !bug
  merpOpenEndFilter:  fj(yr, openSt, notBug),        // Status=open, yr lookback, !bug
  bugsOpenedFilter:   fj(created, bug),              // Status=all, created this week, bug
  bugsOpenEndFilter:  fj(yr, openSt, bug, noStage),  // Status=open, yr lookback, bug, env!=STAGE
  devTasksFilter:     fj(yr, updated),               // Status=all, yr lookback, updated this week
  todoFilter:         fj(yr, todo, notBug),          // Status=is To Do, yr lookback, !bug
  tasksDetailFilter:  fj(yr, updated, notBug),       // Status=all, yr lookback, updated this week, !bug
  bugsDetailFilter:   fj(yr, updated, bug),          // Status=all, yr lookback, updated this week, bug
}}];
"""

# ── Code: Parse Cache ──────────────────────────────────────────────────────────
# Reads the binary output of "Read/Write File: Load Cache" and decodes it to text.
# If the file doesn't exist yet (first-ever run), the disk-read node fails but
# continueOnFail lets the item through with no binary — we fall back to '{}'.
JS_PARSE_CACHE = r"""const item = $input.first();
let cacheRaw = '{}';
try {
  const b64 = item && item.binary && item.binary.data && item.binary.data.data;
  if (b64) cacheRaw = Buffer.from(b64, 'base64').toString('utf-8');
} catch (e) { /* leave cacheRaw as '{}' */ }
return [{ json: { cacheRaw } }];
"""

# ── Code: Prepare Cache File ───────────────────────────────────────────────────
# Turns the updated cache JSON (produced by Code: Build Report) into binary data
# so "Read/Write File: Save Cache" can write it to disk.
JS_PREPARE_CACHE_FILE = r"""const d = $('Code: Build Report').first().json;
const buffer = Buffer.from(d.cacheOut, 'utf-8');
const binaryData = await this.helpers.prepareBinaryData(buffer, 'weekly_data_cache.json', 'application/json');
return [{ json: {}, binary: { data: binaryData } }];
"""

# ── Code: Build Report ────────────────────────────────────────────────────────
JS_BUILD = ("const API_STORY_TYPE_ID  = 15;\n"
            f"const SHEET_URL = '{SHEET_URL}';\n") + r"""

function linkId(links, key) {
  const m = ((links?.[key]?.href) || '').match(/\/(\d+)$/);
  return m ? parseInt(m[1]) : null;
}
function linkTitle(links, key, def='') { return (links?.[key]?.title) || def; }

// getEls unwraps n8n v2.x HTTP response (body is in r.data as a JSON string)
function getEls(nodeName) {
  let r = $(nodeName).first().json;
  if (r && r.data !== undefined) {
    r = typeof r.data === 'string' ? JSON.parse(r.data) : r.data;
  }
  if (!r || !r._embedded) {
    throw new Error(`${nodeName} — unexpected: ${JSON.stringify(r).slice(0,400)}`);
  }
  return r._embedded.elements || [];
}

const merpOpenedEls  = getEls('HTTP: Merp Opened');
const merpOpenEndEls = getEls('HTTP: Merp Open End');
const bugsOpenedEls  = getEls('HTTP: Bugs Opened');
const bugsOpenEndEls = getEls('HTTP: Bugs Open End');
const devTasksEls    = getEls('HTTP: Dev Tasks');
const todoEls        = getEls('HTTP: Todo Tasks');
const tasksDetailEls = getEls('HTTP: Tasks Detail');
const bugsDetailEls  = getEls('HTTP: Bugs Detail');

const merpB       = merpOpenedEls.length;
const merpOpenEnd = merpOpenEndEls.length;
const merpBacklog = todoEls.length;
const merpWip     = merpOpenEnd - merpBacklog;
const bugsB       = bugsOpenedEls.length;
const bugsOpenEnd = bugsOpenEndEls.length;
const business    = merpOpenedEls.filter(w => linkId(w._links,'type') === API_STORY_TYPE_ID).length;
const internal    = merpB - business;

// Dev tasks map (grouped by person, for the email table)
const devTasks = {}, seen = new Set();
for (const wp of devTasksEls) {
  const links = wp._links || {};
  const entry = { id: wp.id, subject: wp.subject||'', type: linkTitle(links,'type','Task') };
  for (const person of [...new Set([linkTitle(links,'assignee',''), linkTitle(links,'responsible','')].filter(Boolean))]) {
    const k = `${person}:${wp.id}`;
    if (!seen.has(k)) {
      (devTasks[person] = devTasks[person]||[]).push(entry);
      seen.add(k);
    }
  }
}
for (const p of Object.keys(devTasks)) devTasks[p].sort((a,b) => a.id - b.id);

// Convert work package list to flat rows for Google Sheets
function extractSheetRows(els, weekOf) {
  return els.map(wp => {
    const links = wp._links || {};
    const fmt = s => s ? s.slice(0,16).replace('T',' ') : '';
    return {
      ID:          wp.id,
      Subject:     wp.subject || '',
      Type:        linkTitle(links, 'type', ''),
      Status:      linkTitle(links, 'status', ''),
      Author:      linkTitle(links, 'author', ''),
      Assignee:    linkTitle(links, 'assignee', ''),
      Accountable: linkTitle(links, 'responsible', ''),
      'Updated on': fmt(wp.updatedAt),
      'Created on': fmt(wp.createdAt),
      'Week Of':   weekOf,
    };
  });
}

// Rolling 4-week cache — persisted to disk (weekly_data_cache.json) via the
// Read/Write File nodes, NOT $getWorkflowStaticData (that resets whenever this
// workflow is re-imported/redeployed, which is what caused missing weeks before).
// The seed below is only a one-time bootstrap for a brand-new/empty cache file.
let cache;
try {
  cache = JSON.parse($('Code: Parse Cache').first().json.cacheRaw || '{}');
} catch (e) { cache = {}; }
if (!cache || Object.keys(cache).length === 0) {
  cache = {
    "2026-05-31_2026-06-06": { merp_B:32,merp_C:15,merp_open:124,merp_wip:103,merp_backlog:21,bugs_B:13,bugs_C:18,bugs_open:16,biz_opened:17,int_opened:15,dev_tasks:{} },
    "2026-06-07_2026-06-13": { merp_B:20,merp_C:21,merp_open:123,merp_wip:101,merp_backlog:22,bugs_B:9, bugs_C:13,bugs_open:12,biz_opened:10,int_opened:10,dev_tasks:{} },
    "2026-06-14_2026-06-20": { merp_B:22,merp_C:38,merp_open:107,merp_wip:92, merp_backlog:15,bugs_B:7, bugs_C:5, bugs_open:14,biz_opened:13,int_opened:9, dev_tasks:{} },
    "2026-06-21_2026-06-27": { merp_B:18,merp_C:18,merp_open:107,merp_wip:90, merp_backlog:17,bugs_B:7, bugs_C:9, bugs_open:12,biz_opened:10,int_opened:8, dev_tasks:{} }
  };
}

const setup = $('Code: Setup').first().json;
const ws = setup.weekStart, we = setup.weekEnd;

function toISO(d) { return d.toISOString().slice(0,10); }
function addDays(d,n) { const r=new Date(d); r.setDate(r.getDate()+n); return r; }
function cacheKey(s,e) { return `${toISO(s)}_${toISO(e)}`; }

const currStart = new Date(ws+'T00:00:00'), currEnd = new Date(we+'T00:00:00');
const currKey   = cacheKey(currStart, currEnd);

cache[currKey] = {
  merp_B:merpB, merp_open:merpOpenEnd, merp_wip:merpWip, merp_backlog:merpBacklog,
  bugs_B:bugsB, bugs_open:bugsOpenEnd, biz_opened:business, int_opened:internal, dev_tasks:devTasks
};

const weeks = [3,2,1,0].map(i=>[addDays(currStart,-7*i),addDays(currEnd,-7*i)]);
const rows  = weeks.map(([s,e])=>({ start:s, end:e, ...(cache[cacheKey(s,e)]||{}) }));

const MS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const ML=['January','February','March','April','May','June','July','August','September','October','November','December'];
function sl(s,e) { return `${s.getDate()} ${MS[s.getMonth()]} - ${e.getDate()} ${MS[e.getMonth()]}`; }
function wl(s,e) { return `${s.getDate()} ${ML[s.getMonth()]} - ${e.getDate()} ${ML[e.getMonth()]} ${e.getFullYear()}`; }

for (let i=0;i<rows.length;i++) {
  const r=rows[i];
  r.merp_open_corrected=r.merp_open||0; r.bugs_open_corrected=r.bugs_open||0;
  if (i===0) { r.merp_A=(r.merp_open||0)-(r.merp_B||0)+(r.merp_C||0); r.bugs_A=(r.bugs_open||0)-(r.bugs_B||0)+(r.bugs_C||0); }
  else        { r.merp_A=rows[i-1].merp_open||0; r.bugs_A=rows[i-1].bugs_open||0; }
  if (i===3) {
    r.merp_C=r.merp_A+(r.merp_B||0)-(r.merp_open||0);
    r.bugs_C=r.bugs_A+(r.bugs_B||0)-(r.bugs_open||0);
    cache[currKey].merp_C=r.merp_C;
    cache[currKey].bugs_C=r.bugs_C;
  }
}

const cacheOut = JSON.stringify(cache, null, 2);

// HTML generation
const H='#2E6B73',S='#5F9EA0';
const AB='#FFEB9C',AF='#9C6500',GB='#C6EFCE',GF='#375623',PB='#FFC7CE',PF='#9C0006';
const TH=`background:${H};color:white;padding:6px 10px;font-weight:bold`;

function pct(cv,pv,gu=true) {
  if(!pv) return '<td style="text-align:center;padding:5px 8px">—</td>';
  const d=cv-pv,p=Math.abs(d)/pv*100,ar=d>=0?'▲':'▼';
  let bg,fg;
  if(p<=5){bg=AB;fg=AF;}else if((d>0)===gu){bg=GB;fg=GF;}else{bg=PB;fg=PF;}
  return `<td style="background:${bg};color:${fg};font-weight:bold;white-space:nowrap;text-align:center;padding:5px 8px">${ar} ${p.toFixed(1)}%</td>`;
}
function num(n){return `<td style="text-align:right;padding:5px 10px">${n}</td>`;}

const cur=rows[3],prv=rows[2],lbs=rows.map(r=>sl(r.start,r.end));
const cD=(cur.merp_C||0)-(prv.merp_C||0),cP=prv.merp_C?Math.abs(cD)/prv.merp_C*100:0;
const bD=(cur.bugs_open_corrected||0)-(prv.bugs_open_corrected||0),bP=prv.bugs_open_corrected?Math.abs(bD)/prv.bugs_open_corrected*100:0;
const hc=(d,p,g)=>p<=5?'#f39c12':(d>0)===g?'#27ae60':'#e74c3c';

const hl=`<ul>
<li>The total number of <strong>closed tasks</strong> has <strong>${cD>=0?'increased':'decreased'}</strong> by
    <span style="color:${hc(cD,cP,true)};font-weight:bold">${cD>=0?'▲':'▼'} ${cP.toFixed(1)}%</span> vs last week.</li>
<li>The total count of <strong>open bugs</strong> has <strong>${bD>=0?'increased':'decreased'}</strong> by
    <span style="color:${hc(bD,bP,false)};font-weight:bold">${bD>=0?'▲':'▼'} ${bP.toFixed(1)}%</span> vs last week.</li>
</ul>`;

const th=lbs.map(l=>`<th style="${TH};text-align:center">${l}</th>`).join('');
const hdr=`<tr><th style="${TH};text-align:left">Report Summary</th>${th}<th style="${TH};text-align:center">(+/- Last Week)</th></tr>`;
const sec=l=>`<tr><td colspan="6" style="background:${S};color:white;font-weight:bold;padding:5px 10px">${l}</td></tr>`;
const dr=(label,vals,pv,cv,gu=true)=>`<tr><td style="padding:5px 10px">${label}</td>${vals.map(num).join('')}${pct(cv,pv,gu)}</tr>`;

const mr=[
  sec('Merp SOA Tasks'),
  dr('Open: Beginning of this week (A)',rows.map(r=>r.merp_A||0),prv.merp_A||0,cur.merp_A||0,false),
  dr('Opened During this week (B)',rows.map(r=>r.merp_B||0),prv.merp_B||0,cur.merp_B||0,false),
  dr('Closed During this week (C)',rows.map(r=>r.merp_C||0),prv.merp_C||0,cur.merp_C||0,true),
  dr('Open: End of this week (A + B - C)',rows.map(r=>r.merp_open_corrected||0),prv.merp_open_corrected||0,cur.merp_open_corrected||0,false),
  '<tr><td colspan="6" style="padding:3px"></td></tr>',
  dr('Items in Under Development (WIP)',rows.map(r=>r.merp_wip||0),prv.merp_wip||0,cur.merp_wip||0,true),
  dr('Backlog (Yet to align)',rows.map(r=>r.merp_backlog||0),prv.merp_backlog||0,cur.merp_backlog||0,false),
].join('');

const br=[
  sec('SOA Bugs - Open Project Tickets'),
  dr('Open : Beginning of this week (A)',rows.map(r=>r.bugs_A||0),prv.bugs_A||0,cur.bugs_A||0,false),
  dr('Opened During this week (B)',rows.map(r=>r.bugs_B||0),prv.bugs_B||0,cur.bugs_B||0,false),
  dr('Closed During this week (C)',rows.map(r=>r.bugs_C||0),prv.bugs_C||0,cur.bugs_C||0,true),
  dr('Open: End of this week (A + B - C)',rows.map(r=>r.bugs_open_corrected||0),prv.bugs_open_corrected||0,cur.bugs_open_corrected||0,false),
].join('');

const sumT=`<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:13px;min-width:700px">${hdr}${mr}<tr><td colspan="6" style="padding:6px"></td></tr>${br}</table>`;
const bifT=`<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:13px;min-width:700px;margin-top:20px">${hdr}${sec('Merp SOA Tasks')}${dr('Total Opened Tickets during this week (A=B+C)',rows.map(r=>r.merp_B||0),prv.merp_B||0,cur.merp_B||0,true)}<tr><td colspan="6" style="padding:3px"></td></tr>${dr('Business Tickets (B)',rows.map(r=>r.biz_opened||0),prv.biz_opened||0,cur.biz_opened||0,true)}${dr('Internally Opened Tickets (C)',rows.map(r=>r.int_opened||0),prv.int_opened||0,cur.int_opened||0,true)}</table>`;

let devH='';
for (const [dev,tasks] of Object.entries(cur.dev_tasks||{}).sort()){
  if(!tasks.length)continue;
  let f=true;
  for(const t of tasks){
    const dc=f?`<td rowspan="${tasks.length}" style="vertical-align:top;padding:5px 10px;font-weight:bold">${dev}</td>`:'';
    devH+=`<tr>${dc}<td style="padding:4px 10px">${t.type} #${t.id}: ${t.subject}</td></tr>`;
    f=false;
  }
}
const devT=`<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:13px;min-width:700px;margin-top:20px"><tr><th style="${TH};text-align:left;width:160px">Developer</th><th style="${TH};text-align:center">${wl(cur.start,cur.end)}</th></tr><tr><td style="padding:5px 10px"></td><th style="background:${S};color:white;padding:5px 10px;text-align:center">Tasks</th></tr>${devH}</table>`;

const weekOf = sl(currStart, currEnd);
const period = `${weekOf} ${cur.end.getFullYear()}`;
const tasksRows = extractSheetRows(tasksDetailEls, weekOf);
const bugsRows  = extractSheetRows(bugsDetailEls,  weekOf);

// Dynamic sheet tab names — include the week date range so each week is identifiable
const weekLabel      = `${currStart.getDate()}${MS[currStart.getMonth()]}-${currEnd.getDate()}${MS[currEnd.getMonth()]}`;
const sheetTabTasks  = `Tasks ${weekLabel}`;
const sheetTabBugs   = `Bugs ${weekLabel}`;
const sheetBodyTasks = JSON.stringify({requests:[{addSheet:{properties:{title:sheetTabTasks}}}]});
const sheetBodyBugs  = JSON.stringify({requests:[{addSheet:{properties:{title:sheetTabBugs}}}]});

const html=`<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="font-family:Arial,sans-serif;font-size:13px;color:#222;max-width:900px"><p>Hi All,</p><p>Please find the Weekly Task Report of BI-SOA from <strong>${period}</strong>.</p><p><strong>Key Highlights :</strong></p>${hl}${sumT}<p style="margin-top:20px">Please find below the bifurcation of total tickets opened :-</p>${bifT}${devT}<br><p>Please refer below for a detailed tracker.<br><a href="${SHEET_URL}">BI-SOA Detailed Tracker</a></p><br><p><em>Thanks &amp; Regards,<br>BI SOA Automation<br>IndiaMart Intermesh Limited</em></p></body></html>`;
const subject=`BI Weekly Report :BI SOA Task Status Report : ${period}`;

return [{ json: { html, subject, tasksRows, bugsRows, sheetTabTasks, sheetTabBugs, sheetBodyTasks, sheetBodyBugs, cacheOut } }];
"""

# ── Code: To Task Rows ────────────────────────────────────────────────────────
# runOnceForAllItems — ignores its input, reads Build Report's tasksRows, outputs N items
JS_TO_TASK_ROWS = r"""const d = $('Code: Build Report').first().json;
const rows = d.tasksRows || [];
if (rows.length === 0) return [{ json: { _noop: true } }];
return rows.map(r => ({ json: r }));
"""

# ── Code: To Bug Rows ─────────────────────────────────────────────────────────
# runOnceForAllItems — ignores N items from Append Tasks, outputs M bug items
JS_TO_BUG_ROWS = r"""const d = $('Code: Build Report').first().json;
const rows = d.bugsRows || [];
if (rows.length === 0) return [{ json: { _noop: true } }];
return rows.map(r => ({ json: r }));
"""

# ── Code: Restore Email ───────────────────────────────────────────────────────
# runOnceForAllItems — collapses M items back to 1 item for Gmail
JS_RESTORE = r"""const d = $('Code: Build Report').first().json;
return [{ json: { html: d.html, subject: d.subject } }];
"""

# ── Helper: HTTP Request node ─────────────────────────────────────────────────
def http_node(name, filter_field, pos):
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.1,
        "position": pos,
        "parameters": {
            "method": "GET",
            "url": "https://project.intermesh.net/api/v3/work_packages",
            "authentication": "none",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Authorization",
                     "value": "={{ $('Code: Setup').first().json.authHeader }}"}
                ]
            },
            "sendQuery": True,
            "queryParameters": {
                "parameters": [
                    {"name": "filters",
                     "value": f"={{{{ $('Code: Setup').first().json.{filter_field} }}}}"},
                    {"name": "pageSize", "value": "1000"},
                    {"name": "offset",   "value": "1"},
                ]
            },
            "options": {}
        }
    }

# ── Helper: Google Sheets API — create tab (body pre-built in Code: Build Report) ──
def http_create_tab(name, body_field, pos):
    body_expr = f"={{{{ $('Code: Build Report').first().json.{body_field} }}}}"
    return {
        "id": str(uuid.uuid4()), "name": name,
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.1,
        "continueOnFail": True, "position": pos,
        "parameters": {
            "method": "POST",
            "url": f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "googleSheetsOAuth2Api",
            "sendBody": True,
            "contentType": "raw",
            "rawContentType": "application/json",
            "body": body_expr,
            "options": {}
        },
        "credentials": {
            "googleSheetsOAuth2Api": {
                "id": "GOOGLE_SHEETS_CREDENTIAL_ID",
                "name": "Google Sheets account"
            }
        }
    }

# ── Helper: Google Sheets node (dynamic tab name from Code: Build Report) ────
def gsheets_dynamic(name, operation, tab_field, pos, continue_on_fail=False):
    sheet_expr = f"={{{{ $('Code: Build Report').first().json.{tab_field} }}}}"
    params = {
        "operation": operation,
        "documentId": {"__rl": True, "value": SHEET_ID, "mode": "id"},
        "sheetName":  {"__rl": True, "value": sheet_expr, "mode": "name"},
    }
    if operation == "append":
        params["columns"] = {
            "mappingMode": "autoMapInputData",
            "value": {},
            "matchingColumns": [],
            "schema": [],
        }
        params["options"] = {}
    node = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": "n8n-nodes-base.googleSheets",
        "typeVersion": 4.4,
        "position": pos,
        "parameters": params,
        "credentials": {
            "googleSheetsOAuth2Api": {
                "id": "GOOGLE_SHEETS_CREDENTIAL_ID",
                "name": "Google Sheets account"
            }
        }
    }
    if continue_on_fail:
        node["continueOnFail"] = True
    return node

# ── Build workflow ────────────────────────────────────────────────────────────
# Parallel architecture:
#
#   Triggers → Setup → [8 HTTP nodes in parallel] → Merge → Build Report
#                                                               ↓
#                               ┌───────────────────────────────┼───────────────────────────┐
#                          Tasks path                      Bugs path                  Email path
#                  CreateTab→Clear→ToRows→Append   CreateTab→Clear→ToRows→Append   Restore→Gmail

IDS = {k: str(uuid.uuid4()) for k in
       ['manual','schedule','setup','merge','build','toTaskRows','toBugRows','restore','gmail','wf',
        'loadCache','parseCache','prepCache','saveCache']}

# 8 HTTP nodes + 1 cache-load branch, spread vertically (step 170, centre = 645)
HTTP_Y = [50 + i * 170 for i in range(9)]
CENTER_Y = (HTTP_Y[0] + HTTP_Y[-1]) // 2   # 730 -> nearest branch used as merge/build centre
LOAD_CACHE_Y = HTTP_Y[8]

# Y levels for the 3 post-build paths
TA_Y = 100          # Tasks path
BU_Y = CENTER_Y     # Bugs path (same level as Build/Merge)
EM_Y = CENTER_Y + 545  # Email path

manual   = {"id":IDS['manual'],   "name":"Manual Trigger",
            "type":"n8n-nodes-base.manualTrigger",   "typeVersion":1,
            "position":[200, CENTER_Y - 80], "parameters":{}}
schedule = {"id":IDS['schedule'], "name":"Schedule Trigger",
            "type":"n8n-nodes-base.scheduleTrigger", "typeVersion":1.2,
            "position":[200, CENTER_Y + 80],
            "parameters":{"rule":{"interval":[{"field":"cronExpression","expression":"0 20 * * 0"}]}}}
setup    = {"id":IDS['setup'],    "name":"Code: Setup",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[440, CENTER_Y],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_SETUP}}
merge    = {"id":IDS['merge'],    "name":"Merge",
            "type":"n8n-nodes-base.merge", "typeVersion":3,
            "position":[1180, CENTER_Y],
            "parameters":{"mode":"append","numberInputs":9,"options":{}}}
load_cache  = {"id":IDS['loadCache'], "name":"Read/Write File: Load Cache",
            "type":"n8n-nodes-base.readWriteFile", "typeVersion":1,
            "continueOnFail": True,
            "position":[900, LOAD_CACHE_Y],
            "parameters":{
                "operation": "read",
                "fileSelector": CACHE_FILE_PATH,
                "options": {"dataPropertyName": "data"}
            }}
parse_cache = {"id":IDS['parseCache'], "name":"Code: Parse Cache",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[1180, LOAD_CACHE_Y],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_PARSE_CACHE}}
prep_cache  = {"id":IDS['prepCache'], "name":"Code: Prepare Cache File",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[1740, LOAD_CACHE_Y],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_PREPARE_CACHE_FILE}}
save_cache  = {"id":IDS['saveCache'], "name":"Read/Write File: Save Cache",
            "type":"n8n-nodes-base.readWriteFile", "typeVersion":1,
            "continueOnFail": True,
            "position":[2020, LOAD_CACHE_Y],
            "parameters":{
                "operation": "write",
                "fileName": CACHE_FILE_PATH,
                "dataPropertyName": "data",
                "options": {}
            }}
build    = {"id":IDS['build'],    "name":"Code: Build Report",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[1460, CENTER_Y],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_BUILD}}
to_tasks = {"id":IDS['toTaskRows'],"name":"Code: To Task Rows",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[2280, TA_Y],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_TO_TASK_ROWS}}
to_bugs  = {"id":IDS['toBugRows'], "name":"Code: To Bug Rows",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[2280, BU_Y],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_TO_BUG_ROWS}}
restore  = {"id":IDS['restore'],  "name":"Code: Restore Email",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[1740, EM_Y],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_RESTORE}}
gmail    = {"id":IDS['gmail'],    "name":"Send Email via Gmail",
            "type":"n8n-nodes-base.gmail", "typeVersion":2.1,
            "position":[2020, EM_Y],
            "parameters":{
                "sendTo":    "bireports@indiamart.com",
                "subject":   "={{ $json.subject }}",
                "emailType": "html",
                "message":   "={{ $json.html }}",
                "options":   {"ccList":"puneet.agarwal@indiamart.com,vipul.bansal1@indiamart.com"}
            }}

# 8 HTTP nodes — all independent, run in parallel after Setup
http_nodes = [
    http_node("HTTP: Merp Opened",   "merpOpenedFilter",  [900, HTTP_Y[0]]),
    http_node("HTTP: Merp Open End", "merpOpenEndFilter", [900, HTTP_Y[1]]),
    http_node("HTTP: Bugs Opened",   "bugsOpenedFilter",  [900, HTTP_Y[2]]),
    http_node("HTTP: Bugs Open End", "bugsOpenEndFilter", [900, HTTP_Y[3]]),
    http_node("HTTP: Dev Tasks",     "devTasksFilter",    [900, HTTP_Y[4]]),
    http_node("HTTP: Todo Tasks",    "todoFilter",        [900, HTTP_Y[5]]),
    http_node("HTTP: Tasks Detail",  "tasksDetailFilter", [900, HTTP_Y[6]]),
    http_node("HTTP: Bugs Detail",   "bugsDetailFilter",  [900, HTTP_Y[7]]),
]

# Tasks path (parallel stream A) — tab name is dynamic e.g. "Tasks 22Jun-28Jun"
create_tasks = http_create_tab("HTTP: Create Tasks Tab", "sheetBodyTasks", [1740, TA_Y])
clear_tasks  = gsheets_dynamic("GSheets: Clear Tasks",  "clear",  "sheetTabTasks", [2020, TA_Y], continue_on_fail=True)
append_tasks = gsheets_dynamic("GSheets: Append Tasks", "append", "sheetTabTasks", [2560, TA_Y], continue_on_fail=True)

# Bugs path (parallel stream B) — tab name is dynamic e.g. "Bugs 22Jun-28Jun"
create_bugs  = http_create_tab("HTTP: Create Bugs Tab",  "sheetBodyBugs",  [1740, BU_Y])
clear_bugs   = gsheets_dynamic("GSheets: Clear Bugs",   "clear",  "sheetTabBugs",  [2020, BU_Y], continue_on_fail=True)
append_bugs  = gsheets_dynamic("GSheets: Append Bugs",  "append", "sheetTabBugs",  [2560, BU_Y], continue_on_fail=True)

all_nodes = (
    [manual, schedule, setup]
    + http_nodes
    + [load_cache, parse_cache, merge, build, prep_cache, save_cache,
       create_tasks, clear_tasks, to_tasks, append_tasks,
       create_bugs,  clear_bugs,  to_bugs,  append_bugs,
       restore, gmail]
)

# ── Connections (parallel) ────────────────────────────────────────────────────
conns = {
    "Manual Trigger":   {"main": [[{"node":"Code: Setup","type":"main","index":0}]]},
    "Schedule Trigger": {"main": [[{"node":"Code: Setup","type":"main","index":0}]]},
    # Setup → all 8 HTTP nodes + the cache-file read, in parallel (9 targets)
    "Code: Setup": {"main": [[
        *({"node": n["name"], "type": "main", "index": 0} for n in http_nodes),
        {"node": "Read/Write File: Load Cache", "type": "main", "index": 0},
    ]]},
    "Read/Write File: Load Cache": {"main": [[{"node":"Code: Parse Cache","type":"main","index":0}]]},
    "Code: Parse Cache": {"main": [[{"node":"Merge","type":"main","index":8}]]},
    # Build Report → 3 existing parallel paths + persist the updated cache to disk
    "Code: Build Report": {"main": [[
        {"node": "HTTP: Create Tasks Tab", "type": "main", "index": 0},
        {"node": "HTTP: Create Bugs Tab",  "type": "main", "index": 0},
        {"node": "Code: Restore Email",    "type": "main", "index": 0},
        {"node": "Code: Prepare Cache File", "type": "main", "index": 0},
    ]]},
    "Code: Prepare Cache File": {"main": [[{"node":"Read/Write File: Save Cache","type":"main","index":0}]]},
    # Tasks path
    "HTTP: Create Tasks Tab": {"main": [[{"node":"GSheets: Clear Tasks", "type":"main","index":0}]]},
    "GSheets: Clear Tasks":   {"main": [[{"node":"Code: To Task Rows",   "type":"main","index":0}]]},
    "Code: To Task Rows":     {"main": [[{"node":"GSheets: Append Tasks","type":"main","index":0}]]},
    # Bugs path
    "HTTP: Create Bugs Tab": {"main": [[{"node":"GSheets: Clear Bugs", "type":"main","index":0}]]},
    "GSheets: Clear Bugs":   {"main": [[{"node":"Code: To Bug Rows",   "type":"main","index":0}]]},
    "Code: To Bug Rows":     {"main": [[{"node":"GSheets: Append Bugs","type":"main","index":0}]]},
    # Email path
    "Code: Restore Email": {"main": [[{"node":"Send Email via Gmail","type":"main","index":0}]]},
    # Merge → Build
    "Merge": {"main": [[{"node":"Code: Build Report","type":"main","index":0}]]},
}
# Each HTTP node → Merge at its own input index (Merge waits for all before firing)
for i, n in enumerate(http_nodes):
    conns[n["name"]] = {"main": [[{"node":"Merge","type":"main","index":i}]]}

workflow = {
    "name": "SOA Weekly Report",
    "id":   IDS['wf'],
    "active": False,
    "settings": {"executionOrder": "v1"},
    "nodes": all_nodes,
    "connections": conns,
}

out = Path(__file__).parent / "n8n_workflow.json"
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False))
print(f"Generated: {out}  ({len(all_nodes)} nodes)")
