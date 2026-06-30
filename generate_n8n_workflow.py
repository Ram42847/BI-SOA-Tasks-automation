#!/usr/bin/env python3
"""Generates n8n_workflow.json — split architecture: HTTP Request nodes for API calls."""
import json, uuid
from pathlib import Path

SHEET_ID  = '1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}'

# ── Code: Setup ───────────────────────────────────────────────────────────────
JS_SETUP = r"""// Replace YOUR_OP_TOKEN_HERE with your actual OpenProject API token
const OP_TOKEN = 'YOUR_OP_TOKEN_HERE';

const PROJECT_ID          = 75;
const YEAR_LOOKBACK_DAYS  = 365;
const API_BUG_TYPE_ID     = 19;
const ENV_STAGE_OPTION_ID = '22';
const OPEN_STATUS_IDS = [
  39,44,88,36,97,42,37,40,43,46,96,59,60,61,62,63,47,98,
  93,94,95,64,89,90,91,92,82,48,49,52,50,51,53,65,54,66,
  67,68,57,69,71,72,73,74,75,76,77,78,79,80,81,1,38,99,100,101
];

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
const cutoff = toISO(addDays(sat, -YEAR_LOOKBACK_DAYS));

const openIds = OPEN_STATUS_IDS.map(String);
const bugIds  = [String(API_BUG_TYPE_ID)];
const proj    = { project:      { operator: '=',   values: [String(PROJECT_ID)] } };
const open    = { status:       { operator: '=',   values: openIds } };
const notBug  = { type:         { operator: '!',   values: bugIds } };
const bug     = { type:         { operator: '=',   values: bugIds } };
const noStage = { customField9: { operator: '!',   values: [ENV_STAGE_OPTION_ID] } };
const created = { createdAt:    { operator: '<>d', values: [ws, we] } };
const yr      = { createdAt:    { operator: '<>d', values: [cutoff, we] } };
const updated = { updatedAt:    { operator: '<>d', values: [ws, we] } };

const fj = (...extras) => JSON.stringify([proj, ...extras]);

return [{ json: {
  authHeader,
  weekStart:          ws,
  weekEnd:            we,
  merpOpenedFilter:   fj(created, open, notBug),
  merpOpenEndFilter:  fj(yr, open, notBug),
  bugsOpenedFilter:   fj(created, open, bug, noStage),
  bugsOpenEndFilter:  fj(yr, open, bug, noStage),
  devTasksFilter:     fj(open, yr, updated),
  tasksDetailFilter:  fj(open, yr, notBug, updated),
  bugsDetailFilter:   fj(open, yr, bug, noStage, updated),
}}];
"""

# ── Code: Build Report ────────────────────────────────────────────────────────
JS_BUILD = r"""const BACKLOG_STATUS_IDS = new Set([1]);
const API_STORY_TYPE_ID  = 15;
const SHEET_URL = 'https://docs.google.com/spreadsheets/d/1fOoMgQKUIxjtIAMei3u073epQqHIf9omAkaVcu_512Q';

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
const tasksDetailEls = getEls('HTTP: Tasks Detail');
const bugsDetailEls  = getEls('HTTP: Bugs Detail');

const merpB       = merpOpenedEls.length;
const merpOpenEnd = merpOpenEndEls.length;
const merpBacklog = merpOpenEndEls.filter(w => BACKLOG_STATUS_IDS.has(linkId(w._links,'status'))).length;
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

// Rolling 4-week cache (seeded with PDF ground-truth values)
const staticData = $getWorkflowStaticData('global');
if (!staticData.cache) {
  staticData.cache = {
    "2026-05-31_2026-06-06": { merp_B:32,merp_C:15,merp_open:124,merp_wip:103,merp_backlog:21,bugs_B:13,bugs_C:18,bugs_open:16,biz_opened:17,int_opened:15,dev_tasks:{} },
    "2026-06-07_2026-06-13": { merp_B:20,merp_C:21,merp_open:123,merp_wip:101,merp_backlog:22,bugs_B:9, bugs_C:13,bugs_open:12,biz_opened:10,int_opened:10,dev_tasks:{} },
    "2026-06-14_2026-06-20": { merp_B:22,merp_C:38,merp_open:107,merp_wip:92, merp_backlog:15,bugs_B:7, bugs_C:5, bugs_open:14,biz_opened:13,int_opened:9, dev_tasks:{} }
  };
}

const setup = $('Code: Setup').first().json;
const ws = setup.weekStart, we = setup.weekEnd;

function toISO(d) { return d.toISOString().slice(0,10); }
function addDays(d,n) { const r=new Date(d); r.setDate(r.getDate()+n); return r; }
function cacheKey(s,e) { return `${toISO(s)}_${toISO(e)}`; }

const currStart = new Date(ws+'T00:00:00'), currEnd = new Date(we+'T00:00:00');
const currKey   = cacheKey(currStart, currEnd);

staticData.cache[currKey] = {
  merp_B:merpB, merp_open:merpOpenEnd, merp_wip:merpWip, merp_backlog:merpBacklog,
  bugs_B:bugsB, bugs_open:bugsOpenEnd, biz_opened:business, int_opened:internal, dev_tasks:devTasks
};

const weeks = [3,2,1,0].map(i=>[addDays(currStart,-7*i),addDays(currEnd,-7*i)]);
const rows  = weeks.map(([s,e])=>({ start:s, end:e, ...(staticData.cache[cacheKey(s,e)]||{}) }));

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
    staticData.cache[currKey].merp_C=r.merp_C;
    staticData.cache[currKey].bugs_C=r.bugs_C;
  }
}

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

const html=`<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="font-family:Arial,sans-serif;font-size:13px;color:#222;max-width:900px"><p>Hi All,</p><p>Please find the Weekly Task Report of BI-SOA from <strong>${period}</strong>.</p><p><strong>Key Highlights :</strong></p>${hl}${sumT}<p style="margin-top:20px">Please find below the bifurcation of total tickets opened :-</p>${bifT}${devT}<br><p>Please refer below for a detailed tracker.<br><a href="${SHEET_URL}">BI-SOA Detailed Tracker</a></p><br><p><em>Thanks &amp; Regards,<br>BI SOA Automation<br>IndiaMart Intermesh Limited</em></p></body></html>`;
const subject=`BI Weekly Report :BI SOA Task Status Report : ${period}`;

return [{ json: { html, subject, tasksRows, bugsRows } }];
"""

# ── Code: To Task Rows ────────────────────────────────────────────────────────
# runOnceForAllItems — ignores its input, reads Build Report's tasksRows, outputs N items
JS_TO_TASK_ROWS = r"""const d = $('Code: Build Report').first().json;
return (d.tasksRows || []).map(r => ({ json: r }));
"""

# ── Code: To Bug Rows ─────────────────────────────────────────────────────────
# runOnceForAllItems — ignores N items from Append Tasks, outputs M bug items
JS_TO_BUG_ROWS = r"""const d = $('Code: Build Report').first().json;
return (d.bugsRows || []).map(r => ({ json: r }));
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

# ── Helper: Google Sheets node ────────────────────────────────────────────────
def gsheets_node(name, operation, sheet_name, pos):
    params = {
        "operation": operation,
        "documentId": {"__rl": True, "value": SHEET_ID, "mode": "id"},
        "sheetName":  {"__rl": True, "value": sheet_name, "mode": "name"},
    }
    if operation == "append":
        params["columns"] = {
            "mappingMode": "autoMapInputData",
            "value": {},
            "matchingColumns": [],
            "schema": [],
        }
        params["options"] = {}
    return {
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

# ── Build workflow ────────────────────────────────────────────────────────────
# Sequential chain — every upstream node reachable via $() from any downstream node:
#
#   Triggers → Setup → [7 HTTP nodes] → Build Report
#     → Clear Tasks → Clear Bugs
#     → To Task Rows → Append Tasks
#     → To Bug Rows  → Append Bugs
#     → Restore Email → Gmail

IDS = {k: str(uuid.uuid4()) for k in
       ['manual','schedule','setup','build','toTaskRows','toBugRows','restore','gmail','wf']}

manual   = {"id":IDS['manual'],   "name":"Manual Trigger",
            "type":"n8n-nodes-base.manualTrigger",   "typeVersion":1,
            "position":[200,200], "parameters":{}}
schedule = {"id":IDS['schedule'], "name":"Schedule Trigger",
            "type":"n8n-nodes-base.scheduleTrigger", "typeVersion":1.2,
            "position":[200,380],
            "parameters":{"rule":{"interval":[{"field":"cronExpression","expression":"0 20 * * 0"}]}}}
setup    = {"id":IDS['setup'],    "name":"Code: Setup",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[440,290],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_SETUP}}
build    = {"id":IDS['build'],    "name":"Code: Build Report",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[2080,290],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_BUILD}}
to_tasks = {"id":IDS['toTaskRows'],"name":"Code: To Task Rows",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[2680,290],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_TO_TASK_ROWS}}
to_bugs  = {"id":IDS['toBugRows'], "name":"Code: To Bug Rows",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[3080,290],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_TO_BUG_ROWS}}
restore  = {"id":IDS['restore'],  "name":"Code: Restore Email",
            "type":"n8n-nodes-base.code", "typeVersion":2,
            "position":[3480,290],
            "parameters":{"mode":"runOnceForAllItems","jsCode":JS_RESTORE}}
gmail    = {"id":IDS['gmail'],    "name":"Send Email via Gmail",
            "type":"n8n-nodes-base.gmail", "typeVersion":2.1,
            "position":[3680,290],
            "parameters":{
                "sendTo":    "bireports@indiamart.com",
                "subject":   "={{ $json.subject }}",
                "emailType": "html",
                "message":   "={{ $json.html }}",
                "options":   {"ccList":"puneet.agarwal@indiamart.com,vipul.bansal1@indiamart.com"}
            }}

http_nodes = [
    http_node("HTTP: Merp Opened",   "merpOpenedFilter",  [ 680, 290]),
    http_node("HTTP: Merp Open End", "merpOpenEndFilter", [ 880, 290]),
    http_node("HTTP: Bugs Opened",   "bugsOpenedFilter",  [1080, 290]),
    http_node("HTTP: Bugs Open End", "bugsOpenEndFilter", [1280, 290]),
    http_node("HTTP: Dev Tasks",     "devTasksFilter",    [1480, 290]),
    http_node("HTTP: Tasks Detail",  "tasksDetailFilter", [1680, 290]),
    http_node("HTTP: Bugs Detail",   "bugsDetailFilter",  [1880, 290]),
]

gsheet_nodes = [
    gsheets_node("GSheets: Clear Tasks",  "clear",  "TasksDetails", [2280, 290]),
    gsheets_node("GSheets: Clear Bugs",   "clear",  "BugsDetails",  [2480, 290]),
    gsheets_node("GSheets: Append Tasks", "append", "TasksDetails", [2880, 290]),
    gsheets_node("GSheets: Append Bugs",  "append", "BugsDetails",  [3280, 290]),
]

all_nodes = (
    [manual, schedule, setup]
    + http_nodes
    + [build,
       gsheet_nodes[0], gsheet_nodes[1],
       to_tasks, gsheet_nodes[2],
       to_bugs,  gsheet_nodes[3],
       restore, gmail]
)

http_names = [n["name"] for n in http_nodes]
chain = (
    ["Code: Setup"]
    + http_names
    + ["Code: Build Report",
       "GSheets: Clear Tasks", "GSheets: Clear Bugs",
       "Code: To Task Rows",   "GSheets: Append Tasks",
       "Code: To Bug Rows",    "GSheets: Append Bugs",
       "Code: Restore Email",  "Send Email via Gmail"]
)

conns = {
    "Manual Trigger":   {"main": [[{"node":"Code: Setup","type":"main","index":0}]]},
    "Schedule Trigger": {"main": [[{"node":"Code: Setup","type":"main","index":0}]]},
}
for i, src in enumerate(chain[:-1]):
    conns[src] = {"main": [[{"node": chain[i+1], "type":"main","index":0}]]}

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
