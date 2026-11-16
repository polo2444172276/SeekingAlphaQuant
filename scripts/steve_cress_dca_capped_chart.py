"""Chart for scripts/steve_cress_dca_capped.py -> data/steve_cress/dca_capped.html."""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D_DIR = os.path.join(ROOT, "data", "steve_cress")

TEMPLATE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Capped Picks DCA</title><style>
:root{color-scheme:light;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e0;--s1:#2a78d6;--s1f:rgba(42,120,214,.16);--s2:#eb6834;--s3:#1baf7a;--s4:#6250d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s1f:rgba(57,135,229,.22);--s2:#d95926;--s3:#199e70;--s4:#9085e9}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2c;--s1:#3987e5;--s1f:rgba(57,135,229,.22);--s2:#d95926;--s3:#199e70;--s4:#9085e9}
body{margin:0;background:var(--surface);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"PingFang SC",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 14px}
.kpis{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:12px}.kpi b{display:block;font-size:20px}.kpi span{color:var(--ink2);font-size:12px}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--ink2);font-size:13px;margin-bottom:4px}.legend i{display:inline-block;width:16px;height:2px;vertical-align:middle;margin-right:6px}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--grid);box-shadow:0 2px 8px rgba(0,0,0,.15);border-radius:6px;padding:8px 10px;font-size:12px;display:none;white-space:nowrap}
.tip div{display:flex;justify-content:space-between;gap:14px;color:var(--ink2)}.tip em{font-style:normal;color:var(--ink)}
.note{color:var(--muted);font-size:12px;margin-top:12px}
</style></head><body><div class="wrap">
<h1>每月最多买 5 笔：定投 SA 推荐股</h1>
<p class="sub">累计 PnL（不含本金）· 2022-01 至 __END__ · 卖出所得分半年 12 期解锁再投资</p>
<div class="kpis">__KPIS__</div>
<div class="legend"><span><i style="background:var(--s1);height:10px;opacity:.35"></i>随机挑选 1000 次：p5–p95 区间</span><span><i style="background:var(--s1)"></i>随机挑选：中位数</span><span><i style="background:var(--s4)"></i>动量挑选</span><span><i style="background:var(--s3)"></i>不限笔数（全部买）</span><span><i style="background:var(--s2)"></i>SPY</span></div>
<div class="chart" id="c"><div class="tip" id="tip"></div></div>
<p class="note">限额规则：每个自然月最多 5 笔买入（卖出不计）。Alpha Picks 优先，月中还有一期 Alpha Picks 时预留 1 个名额；剩余名额从年初 / 年中 Top 10 名单里挑：随机抽样（模拟 1000 次），或按发布前 6 个月涨幅最高的挑（动量）。其余规则同前：$50 每半月（2022 上半年 $600 年初到账），发布后第一个可成交收盘价买入，持有超过 1 年卖出，含分红。</p>
</div><script>
const D=__DATA__;const W=960,H=380,m={l:56,r:16,t:12,b:32},iw=W-m.l-m.r,ih=H-m.t-m.b;
const ns="http://www.w3.org/2000/svg",el=(n,a,p)=>{const e=document.createElementNS(ns,n);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e};
const c=document.getElementById("c"),tip=document.getElementById("tip");
const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"累计 PnL"});c.insertBefore(svg,tip);
const vals=D.flatMap(d=>d.slice(1));const lo=Math.floor(Math.min(0,...vals)/1000)*1000,hi=Math.ceil(Math.max(...vals)/1000)*1000;
const n=D.length-1,x=i=>m.l+i/n*iw,y=v=>m.t+(hi-v)/(hi-lo)*ih;
for(let v=lo;v<=hi;v+=1000){el("line",{x1:m.l,x2:W-m.r,y1:y(v),y2:y(v),stroke:v===0?"var(--muted)":"var(--grid)"},svg);const t=el("text",{x:m.l-8,y:y(v)+4,"text-anchor":"end","font-size":11,fill:"var(--muted)"},svg);t.textContent="$"+v.toLocaleString()}
D.forEach((d,i)=>{if(i===0||D[i-1][0].slice(0,4)!==d[0].slice(0,4)){const t=el("text",{x:x(i),y:H-10,"text-anchor":"middle","font-size":11,fill:"var(--ink2)"},svg);t.textContent=d[0].slice(0,4)}});
const line=k=>D.map((d,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(d[k]).toFixed(1)).join("");
el("path",{d:line(5)+D.map((d,i)=>"L"+x(n-i).toFixed(1)+","+y(D[n-i][4]).toFixed(1)).join("")+"Z",fill:"var(--s1f)",stroke:"none"},svg);
el("path",{d:line(6),fill:"none",stroke:"var(--s2)","stroke-width":2},svg);
el("path",{d:line(1),fill:"none",stroke:"var(--s3)","stroke-width":1.5},svg);
el("path",{d:line(2),fill:"none",stroke:"var(--s4)","stroke-width":2},svg);
el("path",{d:line(3),fill:"none",stroke:"var(--s1)","stroke-width":2},svg);
const vl=el("line",{y1:m.t,y2:H-m.b,stroke:"var(--muted)","stroke-dasharray":"3 3",opacity:0},svg);
const hit=el("rect",{x:m.l,y:m.t,width:iw,height:ih,fill:"transparent"},svg);
const f=v=>"$"+Math.round(v).toLocaleString();
hit.addEventListener("mousemove",e=>{const b=svg.getBoundingClientRect();const i=Math.max(0,Math.min(n,Math.round(((e.clientX-b.left)/b.width*W-m.l)/iw*n)));const d=D[i];
 vl.setAttribute("x1",x(i));vl.setAttribute("x2",x(i));vl.setAttribute("opacity",1);
 tip.innerHTML=`<b>${d[0]}</b><div>随机 p95<em>${f(d[5])}</em></div><div>随机中位数<em>${f(d[3])}</em></div><div>随机 p5<em>${f(d[4])}</em></div><div>动量挑选<em>${f(d[2])}</em></div><div>不限笔数<em>${f(d[1])}</em></div><div>SPY<em>${f(d[6])}</em></div>`;
 tip.style.display="block";const cb=c.getBoundingClientRect();let lx=e.clientX-cb.left+14;if(lx+170>cb.width)lx=e.clientX-cb.left-180;tip.style.left=lx+"px";tip.style.top="10px"});
hit.addEventListener("mouseleave",()=>{tip.style.display="none";vl.setAttribute("opacity",0)});
</script></body></html>"""


def main():
    rows = list(csv.DictReader(open(os.path.join(D_DIR, "dca_capped_daily.csv"))))
    data = [[r["date"]] + [float(r[k]) for k in ("uncapped_pnl", "momentum_pnl", "random_median_pnl",
                                                  "random_p5_pnl", "random_p95_pnl", "spy_pnl_momentum")]
            for r in rows]
    s = {r["variant"]: r for r in csv.DictReader(open(os.path.join(D_DIR, "dca_capped_summary.csv")))}
    kp = [("随机挑选中位数", s["random_p50"]["pnl"]), ("随机 p5–p95", None), ("动量挑选", s["momentum"]["pnl"]),
          ("不限笔数", s["uncapped"]["pnl"]), ("SPY", s["momentum"]["spy_pnl"])]
    html_k = ""
    for name, v in kp:
        val = (f"${float(s['random_p5']['pnl']):,.0f}–${float(s['random_p95']['pnl']):,.0f}" if v is None
               else f"${float(v):,.0f}")
        html_k += f'<div class="kpi"><b>{val}</b><span>{name}</span></div>'
    html = TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__END__", data[-1][0]).replace("__KPIS__", html_k)
    with open(os.path.join(D_DIR, "dca_capped.html"), "w") as f:
        f.write(html)


if __name__ == "__main__":
    main()
