"""Render data/steve_cress/dca_backtest_daily.csv as an interactive HTML chart
(data/steve_cress/dca_backtest.html): cumulative PnL of the picks DCA vs SPY.
"""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D_DIR = os.path.join(ROOT, "data", "steve_cress")

TEMPLATE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Picks DCA PnL</title><style>
:root{color-scheme:light;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e0;--s1:#2a78d6;--s2:#eb6834}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s2:#d95926}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s2:#d95926}
body{margin:0;background:var(--surface);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"PingFang SC",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 14px}
.kpis{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:12px}.kpi b{display:block;font-size:22px}.kpi span{color:var(--ink2);font-size:12px}
.legend{display:flex;gap:18px;color:var(--ink2);font-size:13px;margin-bottom:4px}.legend i{display:inline-block;width:16px;height:2px;vertical-align:middle;margin-right:6px}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--grid);box-shadow:0 2px 8px rgba(0,0,0,.15);border-radius:6px;padding:8px 10px;font-size:12px;display:none;white-space:nowrap}
.tip div{display:flex;justify-content:space-between;gap:14px;color:var(--ink2)}.tip em{font-style:normal;color:var(--ink)}
.note{color:var(--muted);font-size:12px;margin-top:12px}
</style></head><body><div class="wrap">
<h1>每半月 $50 定投 SA 推荐股，持有满 1 年，卖出所得再投资</h1>
<p class="sub">累计 PnL（不含本金）· __START__ 至 __END__ · 对比：同样金额、同一天买入 SPY、同样持有 1 年</p>
<div class="kpis"><div class="kpi"><b>$__P__</b><span>推荐股 PnL</span></div><div class="kpi"><b>$__S__</b><span>SPY PnL</span></div><div class="kpi"><b>$__C__</b><span>累计投入本金</span></div></div>
<div class="legend"><span><i style="background:var(--s1)"></i>推荐股（再投资）</span><span><i style="background:var(--s2)"></i>SPY（再投资）</span><span><i style="background:repeating-linear-gradient(90deg,var(--s1) 0 4px,transparent 4px 7px)"></i>推荐股（不再投资）</span></div>
<div class="chart" id="c"><div class="tip" id="tip"></div></div>
<p class="note">规则：每月 1 日、15 日各到账 $50，等权买入接下来半个月内推荐的所有股票（三个来源，同一窗口内重复的只买一次；没有推荐的窗口资金顺延）。买入价为发布后第一个能成交的收盘价，持有超过 1 年后卖出，卖出所得分 12 份，在接下来半年的 12 期里每期解锁 1 份，并入当期预算（SPY 对照组同理再买 SPY）。2022 上半年的 12 期 $50（$600）在 2022-01-01 一次性到账。虚线为卖出后不再投资的版本。含分红再投资；退市股按最后价格转现金。</p>
</div><script>
const D=__DATA__;const W=960,H=380,m={l:56,r:16,t:12,b:32},iw=W-m.l-m.r,ih=H-m.t-m.b;
const ns="http://www.w3.org/2000/svg",el=(n,a,p)=>{const e=document.createElementNS(ns,n);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e};
const c=document.getElementById("c"),tip=document.getElementById("tip");
const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"累计 PnL 曲线"});c.insertBefore(svg,tip);
const vals=D.flatMap(d=>[d[1],d[2]]);const lo=Math.floor(Math.min(0,...vals)/500)*500,hi=Math.ceil(Math.max(...vals)/500)*500;
const x=i=>m.l+i/(D.length-1)*iw,y=v=>m.t+(hi-v)/(hi-lo)*ih;
for(let v=lo;v<=hi;v+=500){el("line",{x1:m.l,x2:W-m.r,y1:y(v),y2:y(v),stroke:v===0?"var(--muted)":"var(--grid)"},svg);const t=el("text",{x:m.l-8,y:y(v)+4,"text-anchor":"end","font-size":11,fill:"var(--muted)"},svg);t.textContent="$"+v.toLocaleString()}
D.forEach((d,i)=>{if(i===0||D[i-1][0].slice(0,4)!==d[0].slice(0,4)){const t=el("text",{x:x(i),y:H-10,"text-anchor":"middle","font-size":11,fill:"var(--ink2)"},svg);t.textContent=d[0].slice(0,4)}});
const path=k=>D.map((d,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(d[k]).toFixed(1)).join("");
el("path",{d:path(2),fill:"none",stroke:"var(--s2)","stroke-width":2},svg);
if(D[0][5]!==null)el("path",{d:path(5),fill:"none",stroke:"var(--s1)","stroke-width":1.5,"stroke-dasharray":"4 3",opacity:.8},svg);
el("path",{d:path(1),fill:"none",stroke:"var(--s1)","stroke-width":2},svg);
const n=D.length-1;
[[1,"推荐股"],[2,"SPY"]].forEach(([k,l])=>{const t=el("text",{x:x(n)-4,y:y(D[n][k])-8,"text-anchor":"end","font-size":12,fill:"var(--ink)"},svg);t.textContent=l+" $"+Math.round(D[n][k]).toLocaleString()});
const vl=el("line",{y1:m.t,y2:H-m.b,stroke:"var(--muted)","stroke-dasharray":"3 3",opacity:0},svg);
const d1=el("circle",{r:4,fill:"var(--s1)",stroke:"var(--surface)","stroke-width":2,opacity:0},svg);
const d2=el("circle",{r:4,fill:"var(--s2)",stroke:"var(--surface)","stroke-width":2,opacity:0},svg);
const hit=el("rect",{x:m.l,y:m.t,width:iw,height:ih,fill:"transparent"},svg);
hit.addEventListener("mousemove",e=>{const b=svg.getBoundingClientRect();const px=(e.clientX-b.left)/b.width*W;
 const i=Math.max(0,Math.min(n,Math.round((px-m.l)/iw*n)));const d=D[i];
 vl.setAttribute("x1",x(i));vl.setAttribute("x2",x(i));vl.setAttribute("opacity",1);
 d1.setAttribute("cx",x(i));d1.setAttribute("cy",y(d[1]));d1.setAttribute("opacity",1);
 d2.setAttribute("cx",x(i));d2.setAttribute("cy",y(d[2]));d2.setAttribute("opacity",1);
 tip.innerHTML=`<b>${d[0]}</b><div>推荐股 PnL<em>$${Math.round(d[1]).toLocaleString()}</em></div><div>SPY PnL<em>$${Math.round(d[2]).toLocaleString()}</em></div>${d[5]!==null?`<div>推荐股（不再投资）<em>$${Math.round(d[5]).toLocaleString()}</em></div>`:""}<div>累计本金<em>$${d[3].toLocaleString()}</em></div><div>持仓笔数<em>${d[4]}</em></div>`;
 tip.style.display="block";const cb=c.getBoundingClientRect();let lx=e.clientX-cb.left+14;if(lx+180>cb.width)lx=e.clientX-cb.left-190;tip.style.left=lx+"px";tip.style.top="10px"});
hit.addEventListener("mouseleave",()=>{tip.style.display="none";[vl,d1,d2].forEach(z=>z.setAttribute("opacity",0))});
</script></body></html>"""


def main():
    rows = list(csv.DictReader(open(os.path.join(D_DIR, "dca_backtest_daily.csv"))))
    nr_path = os.path.join(D_DIR, "dca_backtest_daily_noreinvest.csv")
    nr = {r["date"]: float(r["pnl"]) for r in csv.DictReader(open(nr_path))} if os.path.exists(nr_path) else {}
    data = [[r["date"], float(r["pnl"]), float(r["spy_pnl"]), float(r["contributions"]), int(r["open_lots"]),
             nr.get(r["date"])] for r in rows]
    last = data[-1]
    html = (TEMPLATE.replace("__DATA__", json.dumps(data))
            .replace("__START__", data[0][0][:7]).replace("__END__", last[0])
            .replace("__P__", f"{last[1]:,.0f}").replace("__S__", f"{last[2]:,.0f}")
            .replace("__C__", f"{last[3]:,.0f}"))
    with open(os.path.join(D_DIR, "dca_backtest.html"), "w") as f:
        f.write(html)


if __name__ == "__main__":
    main()
