"""Chart for scripts/personal_finance_sim.py -> data/steve_cress/personal_finance.html."""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D_DIR = os.path.join(ROOT, "data", "steve_cress")

TEMPLATE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Savings Simulation</title><style>
:root{color-scheme:light;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e0;--s1:#2a78d6;--s1f:rgba(42,120,214,.16);--s2:#eb6834;--s3:#1baf7a;--s4:#6250d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s1f:rgba(57,135,229,.22);--s2:#d95926;--s3:#199e70;--s4:#9085e9}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s1f:rgba(57,135,229,.22);--s2:#d95926;--s3:#199e70;--s4:#9085e9}
body{margin:0;background:var(--surface);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"PingFang SC",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 14px}
table{border-collapse:collapse;width:100%;margin:6px 0 18px;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:right}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--ink2);font-size:13px;margin-bottom:4px}.legend i{display:inline-block;width:16px;height:2px;vertical-align:middle;margin-right:6px}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--grid);box-shadow:0 2px 8px rgba(0,0,0,.15);border-radius:6px;padding:8px 10px;font-size:12px;display:none;white-space:nowrap}
.tip div{display:flex;justify-content:space-between;gap:14px;color:var(--ink2)}.tip em{font-style:normal;color:var(--ink)}
.note{color:var(--muted);font-size:12px;margin-top:12px}
</style></head><body><div class="wrap">
<h1>2022 至今能存多少钱：SA 推荐股 vs 大盘</h1>
<p class="sub">截至 __END__ · 单身 · NJ · 起薪总包 $30 万（base $17.5 万 + bonus $12.5 万），每年 +12% · 生活开支每月 $7,100</p>
__TABLE__
<div class="legend"><span><i style="background:var(--s1)"></i>应税账户：SA 推荐股（随机挑选中位数）</span><span><i style="background:var(--s1);height:10px;opacity:.35"></i>p5–p95</span><span><i style="background:var(--s2)"></i>应税账户：SPY 买入持有</span><span><i style="background:var(--s3)"></i>401k（SPY）</span><span><i style="background:var(--s4)"></i>公司内部基金</span></div>
<div class="chart" id="c"><div class="tip" id="tip"></div></div>
<p class="note">应税账户为月末市值（含未投出的现金，未扣当年应计税）。401k 与内部基金为税前余额。推荐股策略：每半月可投资现金等权买入当期推荐（每月最多 5 笔，Alpha Picks 优先，名单随机挑选，模拟 200 次），持有超过 1 年卖出，卖出所得与奖金税后到手分 12 期投入，闲置现金按 13 周国债利率计息；投资收益的税次年 4 月 15 日缴纳。SPY：同样的现金流在发薪日买入并一直持有。</p>
</div><script>
const D=__DATA__;const W=960,H=380,m={l:64,r:16,t:12,b:32},iw=W-m.l-m.r,ih=H-m.t-m.b;
const ns="http://www.w3.org/2000/svg",el=(n,a,p)=>{const e=document.createElementNS(ns,n);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e};
const c=document.getElementById("c"),tip=document.getElementById("tip");
const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"账户余额"});c.insertBefore(svg,tip);
const hi=Math.ceil(Math.max(...D.flatMap(d=>d.slice(1)))/200000)*200000,lo=0;
const n=D.length-1,x=i=>m.l+i/n*iw,y=v=>m.t+(hi-v)/(hi-lo)*ih;
for(let v=lo;v<=hi;v+=200000){el("line",{x1:m.l,x2:W-m.r,y1:y(v),y2:y(v),stroke:v===0?"var(--muted)":"var(--grid)"},svg);const t=el("text",{x:m.l-8,y:y(v)+4,"text-anchor":"end","font-size":11,fill:"var(--muted)"},svg);t.textContent="$"+(v/1000)+"k"}
D.forEach((d,i)=>{if(d[0].slice(5,7)==="01"||i===0){const t=el("text",{x:x(i),y:H-10,"text-anchor":"middle","font-size":11,fill:"var(--ink2)"},svg);t.textContent=d[0].slice(0,4)}});
const line=k=>D.map((d,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(d[k]).toFixed(1)).join("");
el("path",{d:line(3)+D.map((d,i)=>"L"+x(n-i).toFixed(1)+","+y(D[n-i][2]).toFixed(1)).join("")+"Z",fill:"var(--s1f)"},svg);
[[6,"--s4"],[5,"--s3"],[4,"--s2"],[1,"--s1"]].forEach(([k,col])=>el("path",{d:line(k),fill:"none",stroke:`var(${col})`,"stroke-width":2},svg));
const vl=el("line",{y1:m.t,y2:H-m.b,stroke:"var(--muted)","stroke-dasharray":"3 3",opacity:0},svg);
const hit=el("rect",{x:m.l,y:m.t,width:iw,height:ih,fill:"transparent"},svg);
const f=v=>"$"+Math.round(v).toLocaleString();
hit.addEventListener("mousemove",e=>{const b=svg.getBoundingClientRect();const i=Math.max(0,Math.min(n,Math.round(((e.clientX-b.left)/b.width*W-m.l)/iw*n)));const d=D[i];
 vl.setAttribute("x1",x(i));vl.setAttribute("x2",x(i));vl.setAttribute("opacity",1);
 tip.innerHTML=`<b>${d[0]}</b><div>推荐股账户（中位数）<em>${f(d[1])}</em></div><div>SPY 账户<em>${f(d[4])}</em></div><div>401k<em>${f(d[5])}</em></div><div>内部基金<em>${f(d[6])}</em></div>`;
 tip.style.display="block";const cb=c.getBoundingClientRect();let lx=e.clientX-cb.left+14;if(lx+200>cb.width)lx=e.clientX-cb.left-210;tip.style.left=lx+"px";tip.style.top="10px"});
hit.addEventListener("mouseleave",()=>{tip.style.display="none";vl.setAttribute("opacity",0)});
</script></body></html>"""


def main():
    rows = [r for r in csv.DictReader(open(os.path.join(D_DIR, "personal_finance_monthly.csv")))
            if r["month_end"] >= "2022-01"]
    data = [[r["month_end"]] + [float(r[k]) for k in ("picks_taxable_median", "picks_taxable_p5", "picks_taxable_p95",
                                                       "spy_taxable", "k401", "internal_fund")] for r in rows]
    s = {r["strategy"]: r for r in csv.DictReader(open(os.path.join(D_DIR, "personal_finance_summary.csv")))}
    p, q = s["picks_median"], s["spy"]
    f = lambda v: f"${float(v):,.0f}"  # noqa: E731
    lines = [("应税账户（市值，已扣当年应计税）", "taxable_mtm"), ("　其中未投出的现金", "cash_in_taxable"),
             ("应税账户（若今天全部卖出，扣税后）", "taxable_after_liquidation"), ("401k（税前）", "k401"),
             ("公司内部基金（税前）", "internal_fund"), ("<b>总资产（应税市值 + 401k + 内部基金）</b>", "net_worth"),
             ("已缴和应计的投资收益税", "investment_taxes"), ("工资税（联邦 + NJ + FICA）", "wage_taxes"),
             ("生活开支", "spent"), ("税前总收入（base + 已发 bonus）", "gross_comp")]
    tbl = "<table><tr><th></th><th>SA 推荐股</th><th>SPY</th><th>差额</th></tr>"
    for name, k in lines:
        tbl += (f"<tr><td>{name}</td><td>{f(p[k])}</td><td>{f(q[k])}</td>"
                f"<td>{f(float(p[k]) - float(q[k]))}</td></tr>")
    tbl += "</table>"
    html = TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__END__", rows[-1]["month_end"]).replace(
        "__TABLE__", tbl)
    with open(os.path.join(D_DIR, "personal_finance.html"), "w") as fh:
        fh.write(html)


if __name__ == "__main__":
    main()
