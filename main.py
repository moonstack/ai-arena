#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 竞赛导航 · 自动采集 + 渲染一体机
=====================================
本地运行（需要梯子访问境外源）:
    $env:ARENA_PROXY='http://127.0.0.1:7897'; python main.py
GitHub Actions 运行（境外直连,不设代理）:
    python main.py

输出:
    index.html  — 单页导航站（发布物）
    data.json   — 本次采集原始快照（调试/比对用）
"""
import os
import re
import sys
import json
import html as H
import ssl
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).parent
TODAY = dt.date.today()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
PROXY = os.environ.get("ARENA_PROXY", "").strip()
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # 部分代理链下证书校验会失败

def fetch(url, use_proxy=True, timeout=30):
    """抓取 URL。use_proxy=True 时走 ARENA_PROXY（本地梯子），False 直连（国内站）。"""
    handlers = []
    if use_proxy and PROXY:
        handlers.append({"http": PROXY, "https": PROXY})
    if not handlers:
        handlers.append({})  # 显式空代理 = 强制直连
    opener = _mk_opener(handlers[0])
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en,zh-CN;q=0.9"})
    with opener.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def _mk_opener(proxy_map):
    return urllib.request.build_opener(urllib.request.ProxyHandler(proxy_map))

import urllib.request  # noqa: E402  (放前面是为了让 _mk_opener 可被单测)

# ----------------------------------------------------------------------------
# 源 1: Zindi（官方 API, 境外 → 走代理）
# ----------------------------------------------------------------------------
def collect_zindi():
    api = "https://api.zindi.africa/v1/competitions"
    raw = fetch(api, use_proxy=True)
    data = json.loads(raw).get("data", [])
    out, errors = [], []
    for c in data:
        try:
            end = dt.datetime.fromisoformat(
                c["end_time"].replace("Z", "+00:00")).date()
        except Exception:
            continue
        if end < TODAY:
            continue
        title = (c.get("title") or c.get("id") or "").strip()
        item = {
            "title": title,
            "platform": "Zindi",
            "url": "https://zindi.africa/competitions/" + c["id"],
            "prize": c.get("reward") or "—",
            "deadline": end.isoformat(),
            "participants": c.get("participations_count"),
            "kind": c.get("kind") or "competition",
            "org": (c.get("organization") or {}).get("name", "")
                   if isinstance(c.get("organization"), dict) else (c.get("organization") or ""),
            "note": "公开榜 · 规则页确认 Eligibility（个别赛限国别）",
        }
        out.append(item)
    out.sort(key=lambda x: x["deadline"])
    return out, errors

# ----------------------------------------------------------------------------
# 源 2: DrivenData（HTML 解析, 境外 → 走代理）
# ----------------------------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

def collect_drivendata():
    idx_html = fetch("https://www.drivendata.org/competitions/", use_proxy=True)
    out, errors = [], []
    # 每个比赛卡片容器带结构化 data-* 属性:
    #   data-start_date="20260910" data-deadline="-120261203"(末8位=YYYYMMDD)
    #   data-joined="969" data-total_prize_purse="300000.0" ...
    card_pat = re.compile(
        r'class="[^"]*active-comp[^"]*"[^>]*?data-start_date="(\d{8})"'
        r'[^>]*?data-deadline="([^"]+)"[^>]*?data-joined="(\d+)"'
        r'[^>]*?data-total_prize_purse="([\d.]+)"[^>]*?data-reward_prize="(\d)"',
        re.S)
    seen = set()
    for m in card_pat.finditer(idx_html):
        start_s, dl_s, joined, purse, is_prize = m.groups()
        dm = re.search(r"(\d{4})(\d{2})(\d{2})$", dl_s.strip())
        if not dm:
            continue
        deadline = dt.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
        if deadline < TODAY or float(purse) <= 0 or is_prize != "1":
            continue
        # 卡片窗口内找比赛链接与标题(title 属性)
        seg = idx_html[m.end(): m.end() + 2500]
        lm = re.search(r'href="(/competitions/(\d+)/([a-z0-9-]+)/)"[^>]*?title="([^"]{4,140})"', seg)
        if not lm:
            lm = re.search(r'title="([^"]{4,140})"[^>]*?href="(/competitions/(\d+)/([a-z0-9-]+)/)"', seg)
            if not lm:
                continue
            slug, title = lm.group(4), H.unescape(lm.group(1)).strip()
        else:
            slug, title = lm.group(3), H.unescape(lm.group(4)).strip()
        if slug in seen:
            continue
        seen.add(slug)
        pool = float(purse)
        out.append({
            "title": title, "platform": "DrivenData",
            "url": f"https://www.drivendata.org/competitions/{lm.group(2)}/{slug}/",
            "prize": "$" + format(int(pool), ","),
            "deadline": deadline.isoformat(),
            "participants": int(joined), "kind": "prize",
            "org": "DrivenData",
            "note": "公益数据科学赛 · 注意个别赛为美国联邦资助(如 American-Made 系列)需自查资格",
        })
    if not out and not errors and "active_comp" not in idx_html:
        errors.append("DrivenData: 页面结构变化,未解析到任何卡片")
    out.sort(key=lambda x: x["deadline"])
    return out, errors

# ----------------------------------------------------------------------------
# 源 3: DataFountain（国内站 → 直连）
# ----------------------------------------------------------------------------
def collect_df():
    page = fetch("https://www.datafountain.cn/competitions", use_proxy=False)
    out, errors = [], []
    pat = re.compile(
        r'<a href="/competitions/(\d+)" class="el-tooltip compt__title item">\s*([^<]+?)\s*</a>')
    seen = set()
    for m in pat.finditer(page):
        cid, title = m.group(1), H.unescape(m.group(2)).strip()
        if cid in seen:
            continue
        seen.add(cid)
        seg = page[m.end(): m.end() + 3000]
        dm = re.search(
            r'(\d{4})\.(\d{2})\.(\d{2})</span>\s*<span[^>]*>-</span>\s*<span>(\d{4})\.(\d{2})\.(\d{2})', seg)
        if not dm:
            continue
        end = dt.date(int(dm.group(4)), int(dm.group(5)), int(dm.group(6)))
        if end < TODAY:
            continue
        pm = re.search(r"[￥¥]([\d,]+)", seg)
        out.append({
            "title": title, "platform": "DataFountain",
            "url": f"https://www.datafountain.cn/competitions/{cid}",
            "prize": ("¥" + pm.group(1)) if pm else "见官网",
            "deadline": end.isoformat(),
            "participants": None, "kind": "competition",
            "org": "DataFountain",
            "note": "国内公开榜 · CCF BDCI/数字中国系列承办平台",
        })
    out.sort(key=lambda x: x["deadline"])
    return out, errors

# ----------------------------------------------------------------------------
# 渲染
# ----------------------------------------------------------------------------
CSS = """
:root{--bg:#07090d;--panel:#0d1117;--panel2:#11161d;--line:#1e2733;--cyan:#00e5ff;
--mag:#ff2d78;--amber:#ffb300;--green:#00ff9d;--dim:#8b98a8;--txt:#d7dee8;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:"Microsoft YaHei","PingFang SC",sans-serif;font-size:14px;line-height:1.65;padding:24px 12px 70px}
a{color:var(--cyan);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto}
header{border:1px solid var(--line);border-left:3px solid var(--cyan);
background:linear-gradient(90deg,rgba(0,229,255,.06),transparent 60%);padding:20px 24px;margin-bottom:16px}
h1{font-size:21px;color:var(--cyan);letter-spacing:1px;font-family:Consolas,"Microsoft YaHei",monospace;margin-bottom:4px}
h2{font-size:16px;color:var(--mag);letter-spacing:1px;margin:26px 0 10px;padding-left:10px;border-left:3px solid var(--mag);font-family:Consolas,"Microsoft YaHei",monospace}
.meta{color:var(--dim);font-size:12px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 2px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:8px 14px;min-width:120px}
.stat b{color:var(--cyan);font-family:Consolas,monospace;font-size:18px;display:block}
.stat span{color:var(--dim);font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--panel);font-size:13px}
th{background:var(--panel2);color:var(--cyan);text-align:left;padding:8px 10px;border:1px solid var(--line);white-space:nowrap}
td{padding:7px 10px;border:1px solid var(--line);vertical-align:top}
tr:hover td{background:rgba(0,229,255,.04)}
.tag{display:inline-block;padding:1px 8px;border-radius:2px;font-size:11px;margin:0 3px 3px 0;white-space:nowrap}
.t-go{background:rgba(0,255,157,.12);color:var(--green);border:1px solid rgba(0,255,157,.4)}
.t-mid{background:rgba(255,179,0,.12);color:var(--amber);border:1px solid rgba(255,179,0,.4)}
.t-no{background:rgba(139,152,168,.12);color:var(--dim);border:1px solid rgba(139,152,168,.4)}
.t-hot{background:rgba(255,45,120,.18);color:var(--mag);border:1px solid rgba(255,45,120,.5)}
.urgent{color:var(--mag);font-weight:700;font-family:Consolas,monospace}
.soon{color:var(--amber);font-family:Consolas,monospace}
.far{color:var(--green);font-family:Consolas,monospace}
.filters{margin:8px 0}
.filters button{background:var(--panel);border:1px solid var(--line);color:var(--dim);padding:5px 14px;cursor:pointer;font-size:12px;margin-right:6px;border-radius:3px}
.filters button.on{color:var(--cyan);border-color:var(--cyan)}
.filters button:hover{color:var(--cyan)}
.note{background:rgba(255,179,0,.07);border-left:3px solid var(--amber);padding:9px 13px;font-size:13px;color:#e8d5ad;margin:10px 0}
.danger{background:rgba(255,45,120,.07);border-left:3px solid var(--mag);padding:9px 13px;font-size:13px;color:#f0b8cc;margin:10px 0}
.small{color:var(--dim);font-size:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:12px 14px;margin-bottom:10px}
.card h3{font-size:14px;color:var(--amber);margin-bottom:4px}
.cal{border-left:2px solid var(--line);margin-left:8px;padding-left:18px}
.cal-item{position:relative;margin-bottom:12px}
.cal-item:before{content:"";position:absolute;left:-23px;top:6px;width:8px;height:8px;background:var(--cyan);border-radius:50%;box-shadow:0 0 8px var(--cyan)}
.cal-item .m{font-family:Consolas,monospace;color:var(--amber);font-size:12px}
footer{margin-top:32px;padding-top:14px;border-top:1px solid var(--line);color:var(--dim);font-size:12px}
"""

def esc(s):
    return H.escape(str(s), quote=True)

def fmt_deadline_td(item):
    d = item.get("deadline")
    if not d:
        return '<span class="small">滚动/见官网</span>'
    dd = dt.date.fromisoformat(d)
    days = (dd - TODAY).days
    label = f"{d} <small>(剩{days}天)</small>" if days >= 0 else f"{d} <small>(已过)</small>"
    cls = "urgent" if days <= 14 else ("soon" if days <= 45 else "far")
    return f'<span class="{cls}">{label}</span>'

def fmt_participants(n):
    return str(n) if n is not None else "—"

def platform_color(p):
    return {"Zindi": "#00e5ff", "DrivenData": "#ff2d78",
            "DataFountain": "#ffb300"}.get(p, "#00ff9d")

def render(auto_items, source_errors, curated):
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    platforms = sorted({i["platform"] for i in auto_items})

    # live 表
    rows = []
    for it in auto_items:
        c = platform_color(it["platform"])
        rows.append(
            f'<tr data-p="{esc(it["platform"])}">'
            f'<td><a href="{esc(it["url"])}" target="_blank">{esc(it["title"])}</a><br>'
            f'<span class="small">{esc(it["note"] or "")}</span></td>'
            f'<td><b style="color:{c}">{esc(it["platform"])}</b></td>'
            f'<td class="mono" style="font-family:Consolas">{esc(it["prize"])}</td>'
            f'<td>{fmt_deadline_td(it)}</td>'
            f'<td>{fmt_participants(it.get("participants"))}</td></tr>')
    live_rows = "\n".join(rows) or '<tr><td colspan="5">本次采集无在途赛</td></tr>'

    filter_btns = ['<button class="on" data-f="ALL">全部</button>']
    for p in platforms:
        filter_btns.append(f'<button data-f="{esc(p)}">{esc(p)}</button>')
    filter_btns_html = "".join(filter_btns)

    err_html = ""
    if source_errors:
        err_html = ('<div class="note">⚠ 本次部分数据源采集异常（不影响其余来源）：<br>'
                    + "<br>".join(esc(e) for e in source_errors) + "</div>")

    # 人工窗口
    win_cards = []
    for w in curated.get("windows", []):
        dl = w.get("deadline")
        if dl:
            dd = dt.date.fromisoformat(dl)
            days = (dd - TODAY).days
            if days < 0:
                continue
            dl_html = f'<span class="urgent">{dl}（剩{days}天）</span>'
        else:
            dl_html = '<span class="t-mid tag">滚动报名 · 见官网</span>'
        tags = "".join(f'<span class="t-go tag">{esc(t)}</span>' for t in w.get("tags", []))
        win_cards.append(
            f'<div class="card"><h3><a href="{esc(w["url"])}" target="_blank">{esc(w["title"])}</a></h3>'
            f'<div class="small">截止：{dl_html} ｜ 奖励：{esc(w.get("prize",""))}</div>'
            f'<div style="margin:4px 0">{tags}</div>'
            f'<div class="small">{esc(w.get("note",""))}</div></div>')
    win_html = "\n".join(win_cards) or '<div class="small">暂无</div>'

    # 永续
    always_html = "\n".join(
        f'<div class="card"><h3><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></h3>'
        f'<div class="small">奖励：{esc(a.get("prize",""))}</div>'
        f'<div style="margin:4px 0">{"".join(f"<span class=\"t-go tag\">{esc(t)}</span>" for t in a.get("tags", []))}</div>'
        f'<div class="small">{esc(a.get("note",""))}</div></div>'
        for a in curated.get("always", []))

    # 观察/避坑
    watch_html = "\n".join(
        f'<div class="{"danger" if w.get("level")=="red" else "note"}">'
        f'<b><a href="{esc(w["url"])}" target="_blank">{esc(w["title"])}</a></b>'
        f'{" · 截止 " + esc(w["deadline"]) if w.get("deadline") else ""}<br>{esc(w.get("note",""))}</div>'
        for w in curated.get("watch", []))

    # 日历
    cal_items = []
    for c in curated.get("calendar", []):
        cal_items.append(
            f'<div class="cal-item"><span class="m">[{esc(c["month"])}]</span> '
            f'<b><a href="{esc(c.get("url",""))}" target="_blank">{esc(c["title"])}</a></b>'
            f'<div class="small">{esc(c.get("desc",""))}</div></div>')
    cal_html = '<div class="cal">' + "\n".join(cal_items) + "</div>"

    n_live = len(auto_items)
    n_win = len(win_cards)
    cur_updated = curated.get("updated", "?")

    src_html = """
<div class="card" id="source-note" style="border-left:3px solid var(--cyan)">
<h3>数据来源与转载声明</h3>
<ul style="margin-left:18px">
<li><b>自动采集来源</b>：Zindi 官方 API（api.zindi.africa）· DrivenData 公开列表页 · DataFountain 公开列表页。仅抓取公开发布的事实字段（名称 / 奖金 / 截止时间 / 参赛规模），不搬运正文内容。</li>
<li><b>人工情报来源</b>：各赛事主办方官网与官方微信公众号公开发布的信息（CCF / 华为 / 讯飞 / 魔搭 / 波克 / WorldQuant / 珠海市政府等），情报更新时间见页首。</li>
<li><b>版权归属</b>：各赛事的名称、规则、素材与奖金信息的版权归主办方所有。本站所有条目均附<b>官方原文链接</b>，一切以官方页面为准；报名前请阅读各赛 Rules / Eligibility 条款。</li>
<li><b>用途说明</b>：本页为公开信息的个人导航聚合，不用于商业转售。如需引用或转载本页内容，请注明原始赛事来源；如有主办方不希望被收录，可联系删除。</li>
</ul>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 竞赛导航 · 自动更新</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%2307090d'/%3E%3Ctext x='16' y='23' font-size='20' text-anchor='middle' fill='%2300e5ff' font-family='monospace'%3E%CE%9E%3C/text%3E%3C/svg%3E">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>[ AI 竞赛导航 ] // AUTO-UPDATED</h1>
  <div class="meta">自动采集：Zindi API · DrivenData · DataFountain ｜ 人工情报更新于 {cur_updated} ｜
  本页数据生成时间：<b>{now_str}</b> ｜ <a href="#source-note" style="color:var(--amber)">来源与转载声明见页底</a></div>
  <div class="stats">
    <div class="stat"><b>{n_live}</b><span>自动源在途赛</span></div>
    <div class="stat"><b>{n_win}</b><span>国内人工窗口</span></div>
    <div class="stat"><b>{len(platforms)}</b><span>自动源平台</span></div>
  </div>
</header>

{err_html}

<h2>▍进行中 · 自动采集（公开榜优先 · 按截止日排序）</h2>
<div class="filters">{filter_btns_html}</div>
<table id="live">
<tr><th>比赛</th><th>平台</th><th>奖金</th><th>截止</th><th>已报名</th></tr>
{live_rows}
</table>
<p class="small">说明：Zindi 已报名数为注册数（实际认真参赛队伍远少于此）；报名前点开各赛 Rules 页确认 Eligibility；DrivenData 部分赛为美国联邦资助（American-Made 系列仅限美国主体）。</p>

<h2>▍国内窗口 · 人工情报（公司主体可报）</h2>
{win_html}

<h2>▍永续长线</h2>
{always_html}

<h2>▍观察 / 避坑清单</h2>
{watch_html}

<h2>▍2027 备战日历</h2>
{cal_html}

<h2>▍数据来源与转载声明</h2>
{src_html}

<footer>
  由 ai-arena 自动采集渲染 · 各源详情见上方声明区块 · 本页纯静态无外部依赖，可双击打开或托管于 GitHub Pages
</footer>

</div>
<script>
document.querySelectorAll('.filters button').forEach(function(b){{
  b.addEventListener('click',function(){{
    document.querySelectorAll('.filters button').forEach(function(x){{x.classList.remove('on')}});
    b.classList.add('on');
    var f=b.dataset.f;
    document.querySelectorAll('#live tr').forEach(function(tr){{
      if(tr.querySelector('th'))return;
      tr.style.display=(f==='ALL'||tr.dataset.p===f)?'':'none';
    }});
  }});
}});
</script>
</body>
</html>"""

# ----------------------------------------------------------------------------
def main():
    items, errors = [], []
    for name, fn, use in [("Zindi", collect_zindi, True),
                          ("DrivenData", collect_drivendata, True),
                          ("DataFountain", collect_df, False)]:
        try:
            got, errs = fn()
            items.extend(got)
            errors.extend(errs)
            print(f"[ok] {name}: {len(got)} 个在途赛")
        except Exception as e:
            errors.append(f"{name}: 采集失败 — {e}")
            print(f"[fail] {name}: {e}")

    curated = json.loads((ROOT / "curated.json").read_text(encoding="utf-8"))
    items.sort(key=lambda x: x["deadline"] or "9999-12-31")

    (ROOT / "data.json").write_text(
        json.dumps({"generated": dt.datetime.now().isoformat(timespec="seconds"),
                    "proxy": PROXY or "(direct)", "items": items,
                    "errors": errors}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    page = render(items, errors, curated)
    (ROOT / "index.html").write_text(page, encoding="utf-8")

    print(f"\n完成：{len(items)} 个自动源在途赛, "
          f"{len(curated.get('windows', []))} 个国内窗口, "
          f"{len(errors)} 条采集异常")
    print("输出: index.html / data.json")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
