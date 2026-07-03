#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a single-file bilingual transcript HTML from a completed spec.json.

Usage:
    python3 build_html.py spec.json out.html

spec.json schema (see SKILL.md): meta{}, chapters[]{title,title_zh,start,summary[],
segments[]{ts,speaker,en,zh,key}}, glossary[]{term,zh,desc}.

Features: chapter TOC with numbers, clickable timestamps -> YouTube, Chinese-primary
with dimmed English, key-line highlighting, "hide English" / "key-only" toggles, and
inline click-to-expand glossary annotations (first occurrence of each term). The full
glossary lives in a collapsed appendix at the end, not at the top.
"""
import json, sys, html as H

def esc(s): return H.escape(s or "", quote=True)

def s2sec(ts):
    a = ts.split(":")
    a = [int(x) for x in a]
    while len(a) < 3:
        a = [0] + a
    return a[0]*3600 + a[1]*60 + a[2]

# stable color per speaker (1st speaker = blue, 2nd = warm amber, then more)
PALETTE = ["#5aa2ff", "#f0a35e", "#39c5b0", "#e879a6", "#f5c451"]
def spk_color(name, table):
    if name not in table:
        table[name] = PALETTE[len(table) % len(PALETTE)]
    return table[name]

def build(spec):
    m = spec["meta"]
    vid = m.get("video_id", "")
    def yturl(ts): return f"https://www.youtube.com/watch?v={vid}&t={s2sec(ts)}"
    chapters = spec["chapters"]
    glossary = spec.get("glossary", [])
    has_spk = m.get("has_speakers", False)
    spk_table = {}

    title_main = m.get("title_zh") or m.get("title", "")
    P = []
    P.append(f"""<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title_main)} · 中英对照转录</title>
<style>
:root{{--bg:#0e1217;--panel:#161b22;--panel2:#1d242e;--fg:#e8ecf2;--muted:#8e99a8;--line:#28303b;--accent:#39c5b0;--accent2:#2aa899;--key:#f5c451;--keybg:rgba(245,196,81,.10);--jensen:#f0a35e;--lex:#5aa2ff;}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}}
a{{color:var(--accent);text-decoration:none}} a:hover{{color:var(--accent);text-decoration:underline}}
.wrap{{max-width:1160px;margin:0 auto;padding:0 22px}}
header.hero{{position:relative;background:radial-gradient(1200px 300px at 12% -40%,rgba(57,197,176,.16),transparent 60%),linear-gradient(135deg,#0d1319,#10191d);border-bottom:1px solid var(--line);padding:40px 0 30px}}
.hero::after{{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:linear-gradient(90deg,var(--accent),transparent 55%)}}
.hero h1{{margin:0 0 8px;font-size:27px;line-height:1.32;letter-spacing:-.01em;font-weight:700}}
.hero .sub{{color:var(--muted);font-size:15px;margin-bottom:14px}}
.meta{{display:flex;flex-wrap:wrap;gap:10px 18px;font-size:13.5px;color:var(--muted)}}
.meta b{{color:var(--fg);font-weight:600}}
.badge{{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:12.5px;color:var(--muted)}}
.badge.play{{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#06231f;border:none;font-weight:600}}
.badge.play:hover{{text-decoration:none;filter:brightness(1.08)}}
.layout{{display:grid;grid-template-columns:288px 1fr;gap:28px;align-items:start;padding:26px 0 90px}}
nav.toc{{position:sticky;top:14px;max-height:calc(100vh - 28px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 12px}}
nav.toc h2{{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:6px 8px 10px}}
nav.toc ol{{list-style:none;margin:0;padding:0}}
nav.toc a.ch{{display:flex;gap:8px;align-items:baseline;padding:6px 8px;border-radius:8px;color:var(--fg);font-size:13.5px;line-height:1.4}}
nav.toc a.ch:hover{{background:var(--panel2);text-decoration:none}}
nav.toc a.ch:hover .n{{background:var(--accent);color:#06231f}}
nav.toc a.ch .n{{flex:0 0 auto;color:var(--accent);font-weight:700;font-size:11.5px;font-variant-numeric:tabular-nums;background:rgba(57,197,176,.12);border-radius:6px;padding:1px 6px;min-width:1.9em;text-align:center}}
nav.toc a.ch .t{{color:var(--muted);font-variant-numeric:tabular-nums;font-size:12px;white-space:nowrap}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin:0 6px 12px}}
.toolbar button{{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12.5px;cursor:pointer}}
.toolbar button:hover{{border-color:var(--accent)}}
main{{min-width:0}}
.note{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:10px;padding:12px 16px;color:var(--muted);font-size:13.5px;margin-bottom:22px}}
section.chapter{{margin:0 0 30px;scroll-margin-top:14px}}
.chhead{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:14px}}
.chnum{{color:#06231f;background:var(--accent);font-weight:700;font-size:13px;font-variant-numeric:tabular-nums;border-radius:7px;padding:3px 9px;letter-spacing:.02em}}
.chhead h2{{font-size:20px;margin:0;flex:1 1 auto;min-width:200px;letter-spacing:-.01em}}
.chhead h2 .en-t{{color:var(--muted);font-size:14px;font-weight:400;margin-left:8px}}
.chhead .jump{{font-size:12.5px;background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:4px 11px;color:var(--muted)}}
.chhead .jump:hover{{border-color:var(--accent);color:var(--accent);text-decoration:none}}
.chsum{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 16px 12px 18px;margin-bottom:16px}}
.chsum .lab{{font-size:12px;letter-spacing:.08em;color:var(--key);font-weight:700;text-transform:uppercase;margin-bottom:6px}}
.chsum ul{{margin:0;padding-left:18px}} .chsum li{{margin:5px 0;color:#cfd6e2;font-size:14.5px}}
.seg{{padding:9px 12px;border-radius:10px;margin:3px 0;display:flex;gap:12px;align-items:baseline}}
.seg:hover{{background:var(--panel)}}
.seg.key{{background:var(--keybg);border:1px solid rgba(245,196,81,.26);box-shadow:inset 3px 0 0 var(--key)}}
.seg .ts{{flex:0 0 auto;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap;padding-top:3px}}
.seg .ts:hover{{color:var(--key);text-decoration:none}}
.seg .body{{flex:1 1 auto;min-width:0}}
.spk{{font-weight:700;font-size:13px;margin-right:6px}}
.seg.key .zh::before{{content:"★ 重点";color:#0f1115;background:var(--key);font-size:11px;font-weight:700;border-radius:5px;padding:1px 6px;margin-right:8px;vertical-align:2px}}
.zh{{color:#e7ecf4;font-size:15.5px;line-height:1.72}}
.en{{display:block;color:#6f7787;font-size:12.5px;line-height:1.6;margin-top:5px;padding-left:9px;border-left:2px solid var(--line)}}
.seg:hover .en{{color:#828b9c}} .hideen .en{{display:none}}
.term{{border-bottom:1px dotted var(--accent);cursor:pointer;color:inherit;transition:background .12s}}
.term::after{{content:"ⓘ";font-size:.62em;vertical-align:super;color:var(--accent);margin-left:1px;opacity:.85}}
.term:hover{{background:rgba(57,197,176,.15);border-radius:3px}}
#pop{{position:absolute;z-index:99;max-width:min(380px,86vw);background:#0a0f12;color:#e8ecf2;border:1px solid var(--accent);border-radius:11px;padding:11px 14px;font-size:13px;line-height:1.62;box-shadow:0 14px 38px rgba(0,0,0,.6);display:none}}
#pop b{{color:var(--key)}}
details.gloss{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:6px 18px;margin-top:30px}}
details.gloss>summary{{cursor:pointer;font-size:15px;font-weight:600;padding:10px 0;list-style:none}}
details.gloss>summary::-webkit-details-marker{{display:none}}
details.gloss>summary::before{{content:"▸ ";color:var(--accent)}} details.gloss[open]>summary::before{{content:"▾ "}}
.gtable{{width:100%;border-collapse:collapse;font-size:14px}}
.gtable td{{border-top:1px solid var(--line);padding:7px 8px;vertical-align:top}}
.gtable td.k{{white-space:nowrap;color:var(--fg);font-weight:600;width:1%}}
.gtable td.z{{color:var(--jensen);white-space:nowrap;width:1%}} .gtable td.d{{color:var(--muted)}}
.totop{{position:fixed;right:18px;bottom:18px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#06231f;border:none;border-radius:50%;width:44px;height:44px;font-size:18px;font-weight:700;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.45);display:none}}
@media(max-width:880px){{.layout{{grid-template-columns:1fr}} nav.toc{{position:static;max-height:none}}}}
footer{{border-top:1px solid var(--line);color:var(--muted);font-size:13px;padding:22px 0;text-align:center}}
</style></head><body>""")

    # hero
    sub = m.get("subtitle") or m.get("title", "")
    P.append('<header class="hero"><div class="wrap">')
    P.append(f'<h1>{esc(title_main)}</h1>')
    if sub and sub != title_main:
        P.append(f'<div class="sub">{esc(sub)}</div>')
    P.append('<div class="meta">')
    if m.get("guest"): P.append(f'<span><b>嘉宾</b> {esc(m["guest"])}</span>')
    if m.get("channel"): P.append(f'<span><b>频道</b> {esc(m["channel"])}</span>')
    if m.get("duration"): P.append(f'<span><b>时长</b> {esc(m["duration"])}</span>')
    if m.get("upload_date"):
        d = m["upload_date"]
        d = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 and d.isdigit() else d
        P.append(f'<span><b>发布</b> {esc(d)}</span>')
    P.append(f'<span class="badge">{len(chapters)} 章节</span><span class="badge">★ 重点已标注</span>')
    P.append(f'<a class="badge play" href="{esc(m.get("url",""))}" target="_blank">▶ 原视频</a>')
    P.append('</div></div></header>')

    # layout + toc
    P.append('<div class="wrap"><div class="layout"><nav class="toc">')
    P.append('<div class="toolbar"><button onclick="markKey()">只看重点</button>'
             '<button onclick="toggleEN()">隐藏英文</button></div>')
    P.append('<h2>目录 · 点击跳转</h2><ol>')
    for i, c in enumerate(chapters, 1):
        ts = c["segments"][0]["ts"]
        t = c.get("title_zh") or c.get("title", "")
        P.append(f'<li><a class="ch" href="#ch{i}"><span class="n">{i:02d}</span>'
                 f'<span class="t">{ts}</span><span>{esc(t)}</span></a></li>')
    P.append('</ol></nav><main>')

    P.append('<div class="note">📌 中英对照逐字稿：<b>中文为主、英文原文为下方小字</b>'
             '（左上「隐藏英文」可切换）。时间戳可点击跳转 YouTube；每章顶部为中文要点，'
             '正文 <b>★ 重点</b> 为高亮金句。带<span class="term" data-tip="点击带虚线下划线的词即可展开中文注释。">虚线词</span>'
             '可<b>点击展开专有名词注释</b>，完整术语表见页面底部。</div>')

    # chapters
    for i, c in enumerate(chapters, 1):
        ts0 = c["segments"][0]["ts"]
        t_zh = c.get("title_zh") or c.get("title", "")
        t_en = c.get("title") if c.get("title_zh") else ""
        P.append(f'<section class="chapter" id="ch{i}"><div class="chhead">'
                 f'<span class="chnum">{i:02d}</span>'
                 f'<h2>{esc(t_zh)}{f"<span class=\"en-t\">{esc(t_en)}</span>" if t_en else ""}</h2>'
                 f'<a class="jump" href="{yturl(ts0)}" target="_blank">▶ {ts0} 跳转视频</a></div>')
        sm = c.get("summary") or []
        if sm:
            P.append('<div class="chsum"><div class="lab">本章要点</div><ul>')
            for b in sm: P.append(f'<li>{esc(b)}</li>')
            P.append('</ul></div>')
        for s in c["segments"]:
            keycls = " key" if s.get("key") else ""
            spk = ""
            if has_spk and s.get("speaker"):
                col = spk_color(s["speaker"], spk_table)
                spk = f'<span class="spk" style="color:{col}">{esc(s["speaker"])}</span>'
            P.append(f'<div class="seg{keycls}">'
                     f'<a class="ts" href="{yturl(s["ts"])}" target="_blank" title="跳转 YouTube">{s["ts"]}</a>'
                     f'<div class="body">{spk}'
                     f'<span class="zh">{esc(s.get("zh") or "")}</span>'
                     f'<span class="en">{esc(s.get("en") or "")}</span></div></div>')
        P.append('</section>')

    # glossary appendix (collapsed, at the END)
    if glossary:
        P.append('<details class="gloss" id="glossary"><summary>📖 专有名词术语表（完整列表）</summary><table class="gtable"><tbody>')
        for g in glossary:
            z = "" if g.get("zh", "") in ("", "——") else esc(g["zh"])
            P.append(f'<tr><td class="k">{esc(g["term"])}</td><td class="z">{z}</td><td class="d">{esc(g.get("desc",""))}</td></tr>')
        P.append('</tbody></table></details>')

    P.append('</main></div></div><div id="pop"></div>'
             '<button class="totop" id="totop" onclick="scrollTo({top:0,behavior:\'smooth\'})">↑</button>')
    P.append(f'<footer>由 YouTube 字幕整理 · 时间戳指向原视频 · {esc(m.get("url",""))}</footer>')

    # glossary map for inline annotation: match-string -> tip html
    gmap = {}
    for g in glossary:
        z = g.get("zh", "")
        match = z if z and z != "——" else g["term"]
        head = g["term"] + (f" · {z}" if z and z != "——" else "")
        gmap[match] = f"<b>{H.escape(head)}</b><br>{H.escape(g.get('desc',''))}"
    P.append("<script>const G=" + json.dumps(gmap, ensure_ascii=False) + ";")
    P.append(r"""
(function(){
  const keys=Object.keys(G).sort((a,b)=>b.length-a.length);
  const done=new Set();
  const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const nodes=Array.from(document.querySelectorAll('.zh'));
  for(const k of keys){
    const re=new RegExp(esc(k));
    for(const node of nodes){
      if(done.has(k))break;
      const w=document.createTreeWalker(node,NodeFilter.SHOW_TEXT,null);
      let tn,hit=null,idx=-1;
      while((tn=w.nextNode())){const mm=tn.nodeValue.match(re);if(mm){hit=tn;idx=mm.index;break;}}
      if(hit){
        const t=hit.nodeValue;
        const sp=document.createElement('span');
        sp.className='term';sp.setAttribute('data-tip',G[k]);sp.textContent=k;
        const after=document.createTextNode(t.slice(idx+k.length));
        const before=document.createTextNode(t.slice(0,idx));
        const p=hit.parentNode;
        p.replaceChild(after,hit);p.insertBefore(sp,after);p.insertBefore(before,sp);
        done.add(k);
      }
    }
  }
})();
const pop=document.getElementById('pop');let cur=null;
document.addEventListener('click',e=>{
  const t=e.target.closest('.term');
  if(t){
    if(cur===t){pop.style.display='none';cur=null;return;}
    pop.innerHTML=t.getAttribute('data-tip');pop.style.display='block';
    const r=t.getBoundingClientRect();
    pop.style.left=(window.scrollX+Math.min(r.left,innerWidth-pop.offsetWidth-16))+'px';
    pop.style.top=(window.scrollY+r.bottom+6)+'px';cur=t;e.stopPropagation();
  }else if(!e.target.closest('#pop')){pop.style.display='none';cur=null;}
});
let keyOnly=false;
function markKey(){keyOnly=!keyOnly;
  document.querySelectorAll('.seg').forEach(s=>s.style.display=(!keyOnly||s.classList.contains('key'))?'':'none');
  document.querySelectorAll('.chsum').forEach(s=>s.style.display=keyOnly?'none':'');
  event.target.textContent=keyOnly?'显示全部':'只看重点';}
let enHidden=false;
function toggleEN(){enHidden=!enHidden;document.body.classList.toggle('hideen',enHidden);
  event.target.textContent=enHidden?'显示英文':'隐藏英文';}
const tb=document.getElementById('totop');
addEventListener('scroll',()=>{tb.style.display=scrollY>600?'block':'none'});
</script></body></html>""")
    return "".join(P)

def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: build_html.py spec.json out.html")
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    out = build(spec)
    open(sys.argv[2], "w", encoding="utf-8").write(out)
    print(f"[build] wrote {sys.argv[2]} ({len(out)} bytes)", file=sys.stderr)

if __name__ == "__main__":
    main()
