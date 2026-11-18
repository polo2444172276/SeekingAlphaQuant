"""Log cumulative return chart: SA picks with and without the top-10 winners vs
SPY. Reads data/steve_cress/alpha_daily.csv (all picks) and alpha_daily_ex10.csv
(run scripts/steve_cress_alpha.py --exclude <top10 from steve_cress_winners.py>).
Writes data/steve_cress/ex_top10.html.
"""
import csv
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D_DIR = os.path.join(ROOT, "data", "steve_cress")

TEMPLATE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Picks Ex Top 10</title><style>
:root{color-scheme:light;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e0;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s2:#d95926;--s3:#199e70}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s2:#d95926;--s3:#199e70}
body{margin:0;background:var(--surface);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"PingFang SC",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 14px}
table{border-collapse:collapse;width:100%;margin:6px 0 16px;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:right}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--ink2);font-size:13px;margin-bottom:4px}.legend i{display:inline-block;width:16px;height:2px;vertical-align:middle;margin-right:6px}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--grid);box-shadow:0 2px 8px rgba(0,0,0,.15);border-radius:6px;padding:8px 10px;font-size:12px;display:none;white-space:nowrap}
.tip div{display:flex;justify-content:space-between;gap:14px;color:var(--ink2)}.tip em{font-style:normal;color:var(--ink)}
.note{color:var(--muted);font-size:12px;margin-top:12px}
</style></head><body><div class="wrap">
<h1>去掉 10 只最大赢家后，SA 推荐股 vs SPY</h1>
<p class="sub">累计收益（对数坐标）· __START__ 至 __END__ · 每只推荐持有 1 年、每日等权、满仓</p>
__TABLE__
<div class="legend"><span><i style="background:var(--s1)"></i>推荐股（去掉 10 只最大赢家）</span><span><i style="background:var(--s2)"></i>SPY</span><span><i style="background:repeating-linear-gradient(90deg,var(--s3) 0 4px,transparent 4px 7px)"></i>推荐股（全部）</span></div>
<div class="chart" id="c"><div class="tip" id="tip"></div></div>
<p class="note">去掉的 10 只（按持满 1 年的平均超额收益排名）：APP、MU、CLS、VISN、SMCI、MOD、SSRM、CRDO、TTMI、AGX。组合：每只推荐股从发布后第一个可成交收盘价起持有到满 1 年，每天对当时持有的所有推荐股等权平均（含分红），不含定投现金流和交税。纵轴为对数坐标：同样的垂直距离代表同样的百分比涨跌。</p>
</div><script>
const D=__DATA__;const W=960,H=400,m={l:60,r:16,t:12,b:32},iw=W-m.l-m.r,ih=H-m.t-m.b;
const ns="http://www.w3.org/2000/svg",el=(n,a,p)=>{const e=document.createElementNS(ns,n);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e};
const c=document.getElementById("c"),tip=document.getElementById("tip");
const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"对数累计收益"});c.insertBefore(svg,tip);
const L=D.flatMap(d=>[d[1],d[2],d[3]].map(Math.log));const lo=Math.min(...L)-0.05,hi=Math.max(...L)+0.05;
const n=D.length-1,x=i=>m.l+i/n*iw,y=v=>m.t+(hi-Math.log(v))/(hi-lo)*ih;
[0.8,1,1.25,1.5,2,2.5,3,4,5].forEach(v=>{if(Math.log(v)<lo||Math.log(v)>hi)return;el("line",{x1:m.l,x2:W-m.r,y1:y(v),y2:y(v),stroke:v===1?"var(--muted)":"var(--grid)"},svg);const t=el("text",{x:m.l-8,y:y(v)+4,"text-anchor":"end","font-size":11,fill:"var(--muted)"},svg);t.textContent=(v>=1?"+":"")+Math.round((v-1)*100)+"%"});
D.forEach((d,i)=>{if(i===0||D[i-1][0].slice(0,4)!==d[0].slice(0,4)){const t=el("text",{x:x(i),y:H-10,"text-anchor":"middle","font-size":11,fill:"var(--ink2)"},svg);t.textContent=d[0].slice(0,4)}});
const line=k=>D.map((d,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(d[k]).toFixed(1)).join("");
el("path",{d:line(3),fill:"none",stroke:"var(--s3)","stroke-width":1.5,"stroke-dasharray":"4 3"},svg);
el("path",{d:line(2),fill:"none",stroke:"var(--s2)","stroke-width":2},svg);
el("path",{d:line(1),fill:"none",stroke:"var(--s1)","stroke-width":2},svg);
[[1,"去掉前 10"],[2,"SPY"],[3,"全部推荐"]].forEach(([k,l])=>{const t=el("text",{x:x(n)-4,y:y(D[n][k])-7,"text-anchor":"end","font-size":12,fill:"var(--ink)"},svg);t.textContent=l+" "+(D[n][k]>=1?"+":"")+Math.round((D[n][k]-1)*100)+"%"});
const vl=el("line",{y1:m.t,y2:H-m.b,stroke:"var(--muted)","stroke-dasharray":"3 3",opacity:0},svg);
const hit=el("rect",{x:m.l,y:m.t,width:iw,height:ih,fill:"transparent"},svg);
const f=v=>(v>=1?"+":"")+((v-1)*100).toFixed(1)+"%";
hit.addEventListener("mousemove",e=>{const b=svg.getBoundingClientRect();const i=Math.max(0,Math.min(n,Math.round(((e.clientX-b.left)/b.width*W-m.l)/iw*n)));const d=D[i];
 vl.setAttribute("x1",x(i));vl.setAttribute("x2",x(i));vl.setAttribute("opacity",1);
 tip.innerHTML=`<b>${d[0]}</b><div>推荐股（去掉前 10）<em>${f(d[1])}</em></div><div>SPY<em>${f(d[2])}</em></div><div>推荐股（全部）<em>${f(d[3])}</em></div>`;
 tip.style.display="block";const cb=c.getBoundingClientRect();let lx=e.clientX-cb.left+14;if(lx+190>cb.width)lx=e.clientX-cb.left-200;tip.style.left=lx+"px";tip.style.top="10px"});
hit.addEventListener("mouseleave",()=>{tip.style.display="none";vl.setAttribute("opacity",0)});
</script></body></html>"""


def load(name):
    return list(csv.DictReader(open(os.path.join(D_DIR, name))))


def main():
    full = {r["date"]: r for r in load("alpha_daily.csv")}
    ex = load("alpha_daily_ex10.csv")
    nav = [1.0, 1.0, 1.0]
    data = []
    for r in ex:
        f = full.get(r["date"])
        if not f or not r["all_picks"] or not f["all_picks"]:
            continue
        for k, v in enumerate((r["all_picks"], r["spy"], f["all_picks"])):
            nav[k] *= 1 + float(v)
        data.append([r["date"], round(nav[0], 5), round(nav[1], 5), round(nav[2], 5)])
    s_full = {r["portfolio"]: r for r in load("alpha_summary.csv")}
    s_ex = {r["portfolio"]: r for r in load("alpha_summary_ex10.csv")}

    def pct(v):
        return f"{float(v) * 100:.1f}%"
    cols = [("年化收益", "ann_return", pct), ("年化波动", "ann_vol", pct), ("夏普", "sharpe", str),
            ("最大回撤", "max_dd", pct), ("贝塔", "beta", str), ("CAPM alpha（t 值）", None, None)]
    tbl = "<table><tr><th></th>" + "".join(f"<th>{c[0]}</th>" for c in cols) + "</tr>"
    for label, r in (("推荐股（全部）", s_full["All picks"]), ("推荐股（去掉前 10）", s_ex["All picks"]),
                     ("SPY", s_full["SPY"])):
        tbl += f"<tr><td>{label}</td>"
        for _, k, fn in cols:
            if k is None:
                tbl += f"<td>{pct(r['capm_alpha'])}（{r['capm_alpha_t']}）</td>"
            else:
                tbl += f"<td>{fn(r[k])}</td>"
        tbl += "</tr>"
    tbl += "</table>"
    html = (TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__START__", data[0][0])
            .replace("__END__", data[-1][0]).replace("__TABLE__", tbl))
    with open(os.path.join(D_DIR, "ex_top10.html"), "w") as fh:
        fh.write(html)
    print("end:", data[-1], "log:", [round(math.log(v), 3) for v in data[-1][1:]])


if __name__ == "__main__":
    main()
