"""Fan chart for scripts/personal_finance_projection.py -> data/steve_cress/projection.html."""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D_DIR = os.path.join(ROOT, "data", "steve_cress")

TEMPLATE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Net Worth 2031</title><style>
:root{color-scheme:light;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e0;--s1:#2a78d6;--s1f:rgba(42,120,214,.16);--s2:#eb6834;--s2f:rgba(235,104,52,.16)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s1f:rgba(57,135,229,.22);--s2:#d95926;--s2f:rgba(217,89,38,.22)}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s1f:rgba(57,135,229,.22);--s2:#d95926;--s2f:rgba(217,89,38,.22)}
body{margin:0;background:var(--surface);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"PingFang SC",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 14px}
table{border-collapse:collapse;width:100%;margin:6px 0 18px;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:right}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--ink2);font-size:13px;margin-bottom:4px}.legend i{display:inline-block;width:16px;height:2px;vertical-align:middle;margin-right:6px}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--grid);box-shadow:0 2px 8px rgba(0,0,0,.15);border-radius:6px;padding:8px 10px;font-size:12px;display:none;white-space:nowrap}
.tip div{display:flex;justify-content:space-between;gap:14px;color:var(--ink2)}.tip em{font-style:normal;color:var(--ink)}
.note{color:var(--muted);font-size:12px;margin-top:12px}
</style></head><body><div class="wrap">
<h1>到 2031 年底的总资产：SA 推荐股 vs 大盘</h1>
<p class="sub">2022-01 至 __LASTACT__ 为模拟实际值，之后为 1000 条路径的蒙特卡洛推算 · 总资产 = 应税账户 + 401k（+ 2026 年底前的内部基金）</p>
__TABLE__
<div class="legend"><span><i style="background:var(--s1)"></i>SA 推荐股：中位数</span><span><i style="background:var(--s1);height:10px;opacity:.35"></i>p10–p90</span><span><i style="background:var(--s2)"></i>SPY：中位数</span><span><i style="background:var(--s2);height:10px;opacity:.35"></i>p10–p90</span></div>
<div class="chart" id="c"><div class="tip" id="tip"></div></div>
<p class="note">推算假设：2026 年竞业限制，只发 base，当年工作没有 bonus；内部基金 2026-12-31 按当年工资平均所得税率（31.7%）扣税后转入应税账户。2027 年起新工作，总包按 $30 万 × 1.12^n 增长，封顶 $70 万（base 7/12、bonus 5/12，次年 3 月发），新公司没有内部基金。生活开支每月 $7,100。未来收益：从 2022-02 至 2026-10 的真实月度收益中成对随机抽样（推荐股账户的时间加权收益已包含现金拖累和选股）。推荐股每笔持有满 12 个月卖出再买入并交资本利得税，SPY 一直不卖。联邦税档 2027 年起每年按 2.5% 通胀调整，NJ 税档不变。注意：抽样池来自推荐股表现特别好的一段时期，未来未必重现。</p>
</div><script>
const D=__DATA__,ACT=__NACT__;const W=960,H=400,m={l:64,r:16,t:12,b:32},iw=W-m.l-m.r,ih=H-m.t-m.b;
const ns="http://www.w3.org/2000/svg",el=(n,a,p)=>{const e=document.createElementNS(ns,n);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e};
const c=document.getElementById("c"),tip=document.getElementById("tip");
const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"总资产推算"});c.insertBefore(svg,tip);
const ymax=Math.ceil(Math.max(...D.map(d=>d[3]))/1e6)*1e6;const n=D.length-1,x=i=>m.l+i/n*iw,y=v=>m.t+(ymax-v)/ymax*ih;
for(let v=0;v<=ymax;v+=1e6){el("line",{x1:m.l,x2:W-m.r,y1:y(v),y2:y(v),stroke:v===0?"var(--muted)":"var(--grid)"},svg);const t=el("text",{x:m.l-8,y:y(v)+4,"text-anchor":"end","font-size":11,fill:"var(--muted)"},svg);t.textContent="$"+(v/1e6)+"M"}
D.forEach((d,i)=>{if(d[0].endsWith("-01")){const t=el("text",{x:x(i),y:H-10,"text-anchor":"middle","font-size":11,fill:"var(--ink2)"},svg);t.textContent=d[0].slice(0,4)}});
el("rect",{x:x(ACT),y:m.t,width:x(n)-x(ACT),height:ih,fill:"var(--grid)",opacity:.35},svg);
const t0=el("text",{x:x(ACT)+6,y:m.t+14,"font-size":11,fill:"var(--muted)"},svg);t0.textContent="推算";
const line=k=>D.map((d,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(d[k]).toFixed(1)).join("");
const band=(lo,hi)=>line(hi)+D.map((d,i)=>"L"+x(n-i).toFixed(1)+","+y(D[n-i][lo]).toFixed(1)).join("")+"Z";
el("path",{d:band(4,6),fill:"var(--s2f)"},svg);el("path",{d:band(1,3),fill:"var(--s1f)"},svg);
el("path",{d:line(5),fill:"none",stroke:"var(--s2)","stroke-width":2},svg);el("path",{d:line(2),fill:"none",stroke:"var(--s1)","stroke-width":2},svg);
const vl=el("line",{y1:m.t,y2:H-m.b,stroke:"var(--muted)","stroke-dasharray":"3 3",opacity:0},svg);
const hit=el("rect",{x:m.l,y:m.t,width:iw,height:ih,fill:"transparent"},svg);
const f=v=>"$"+(v/1e6).toFixed(2)+"M";
hit.addEventListener("mousemove",e=>{const b=svg.getBoundingClientRect();const i=Math.max(0,Math.min(n,Math.round(((e.clientX-b.left)/b.width*W-m.l)/iw*n)));const d=D[i];
 vl.setAttribute("x1",x(i));vl.setAttribute("x2",x(i));vl.setAttribute("opacity",1);
 tip.innerHTML=i<ACT?`<b>${d[0]}（实际）</b><div>推荐股<em>${f(d[2])}</em></div><div>SPY<em>${f(d[5])}</em></div>`:
 `<b>${d[0]}（推算）</b><div>推荐股 p90<em>${f(d[3])}</em></div><div>推荐股中位数<em>${f(d[2])}</em></div><div>推荐股 p10<em>${f(d[1])}</em></div><div>SPY p90<em>${f(d[6])}</em></div><div>SPY 中位数<em>${f(d[5])}</em></div><div>SPY p10<em>${f(d[4])}</em></div>`;
 tip.style.display="block";const cb=c.getBoundingClientRect();let lx=e.clientX-cb.left+14;if(lx+180>cb.width)lx=e.clientX-cb.left-190;tip.style.left=lx+"px";tip.style.top="10px"});
hit.addEventListener("mouseleave",()=>{tip.style.display="none";vl.setAttribute("opacity",0)});
</script></body></html>"""


def main():
    rows = list(csv.DictReader(open(os.path.join(D_DIR, "projection_monthly.csv"))))
    data = [[r["month"]] + [float(r[k]) for k in ("picks_p10", "picks_median", "picks_p90", "spy_p10", "spy_median",
                                                   "spy_p90")] for r in rows]
    n_act = sum(1 for r in rows if r["kind"] == "actual")
    s = {(r["strategy"], r["metric"]): r for r in csv.DictReader(open(os.path.join(D_DIR, "projection_summary.csv")))}
    f = lambda v: f"${float(v) / 1e6:.2f}M"  # noqa: E731
    names = [("总资产（应税账户市值 + 401k）", "net_worth"), ("应税账户（市值，已扣当年应计税）", "taxable"),
             ("应税账户（全部卖出扣税后）", "after_liq"), ("401k（税前）", "k401")]
    tbl = ("<table><tr><th>2031-12-31</th><th>推荐股 p5</th><th>推荐股中位数</th><th>推荐股 p95</th>"
           "<th>SPY p5</th><th>SPY 中位数</th><th>SPY p95</th></tr>")
    for label, k in names:
        p, q = s[("picks", k)], s[("spy", k)]
        tbl += (f"<tr><td>{label}</td><td>{f(p['p5'])}</td><td><b>{f(p['median'])}</b></td><td>{f(p['p95'])}</td>"
                f"<td>{f(q['p5'])}</td><td><b>{f(q['median'])}</b></td><td>{f(q['p95'])}</td></tr>")
    tbl += "</table>"
    html = (TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__NACT__", str(n_act))
            .replace("__LASTACT__", rows[n_act - 1]["month"]).replace("__TABLE__", tbl))
    with open(os.path.join(D_DIR, "projection.html"), "w") as fh:
        fh.write(html)


if __name__ == "__main__":
    main()
