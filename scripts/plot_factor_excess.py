"""Plot cumulative log excess return vs SPY of the iShares factor ETFs
(QUAL quality, VLUE value, MTUM momentum, IUSG growth) and print their
raw / excess monthly return correlations.

Prices come from Supabase prices_daily. MTUM/QUAL rows from 2021-12 onward
are FMP-sourced with mis-adjusted dividends, so those two are taken from
Yahoo adjclose until the DB is repaired.

Usage: python scripts/plot_factor_excess.py  -> data/factor_log_excess_vs_spy.png
"""
import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seekingalpha_quant.data import supabase_db as db  # noqa: E402
import json,urllib.request
import pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


def px(sym):
    sid = db.select("securities", params={"select": "id", "market": "eq.US", "symbol": f"eq.{sym}"})[0]["id"]
    r = pd.DataFrame(db.select("prices_daily", params={"select": "date,adj_close", "security_id": f"eq.{sid}"}))
    return r.assign(date=pd.to_datetime(r.date)).set_index("date").adj_close.sort_index()


P = pd.DataFrame({t: px(t) for t in ["SPY", "QUAL", "VLUE", "MTUM", "IUSG"]}).dropna()
for t in ["MTUM","QUAL"]:   # replace mis-adjusted FMP rows with Yahoo adjclose
    js=json.load(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1=1356998400&period2=9999999999&interval=1d&events=div",headers={"User-Agent":"research-script/1.0"})))
    r=js["chart"]["result"][0]
    P[t]=pd.Series(r["indicators"]["adjclose"][0]["adjclose"],index=pd.to_datetime(r["timestamp"],unit="s").normalize())
P=P.dropna()
d=P.pct_change().dropna(); print("max |daily| after fix:", d.abs().max().round(3).to_dict())
m=P.resample("ME").last().pct_change().dropna()
F=["QUAL","VLUE","MTUM","IUSG"]
print("原始月收益相关性:\n", m[["SPY"]+F].corr().round(2))
print("超额月收益相关性:\n", m[F].sub(m.SPY,axis=0).corr().round(2))
L=np.log(P[F].div(P[F].iloc[0])).sub(np.log(P.SPY/P.SPY.iloc[0]),axis=0)
print("终值 log 超额:", L.iloc[-1].round(3).to_dict(), "=> 相对财富倍数", np.exp(L.iloc[-1]).round(3).to_dict())
yrs=(P.index[-1]-P.index[0]).days/365.25
print("年化超额(几何):", (np.exp(L.iloc[-1]/yrs)-1).map(lambda v:f"{v:+.2%}").to_dict(), "年数",round(yrs,1))
print("峰值/谷值:", {t:(L[t].idxmax().date(),round(L[t].max(),3),L[t].idxmin().date(),round(L[t].min(),3)) for t in F})

# ---- plot
for f in ["Noto Sans CJK SC","Noto Sans CJK JP","WenQuanYi Zen Hei","Source Han Sans SC"]:
    if any(f in x.name for x in font_manager.fontManager.ttflist): plt.rcParams["font.family"]=[f,"DejaVu Sans"]; break
C={"QUAL":"#2a78d6","VLUE":"#eb6834","MTUM":"#1baf7a","IUSG":"#eda100"}
NAME={"QUAL":"质量 QUAL","VLUE":"价值 VLUE","MTUM":"动量 MTUM","IUSG":"成长 IUSG"}
INK,INK2,GRID,SURF="#1f1f1e","#5f5e58","#e6e5e0","#fcfcfb"
fig,ax=plt.subplots(figsize=(11,6),dpi=200); fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
ax.axhline(0,color=INK2,lw=1)
for t in F: ax.plot(L.index,L[t],color=C[t],lw=2,label=NAME[t])
ends=L.iloc[-1].sort_values()
ys=list(ends.values); 
for i in range(1,len(ys)):
    if ys[i]-ys[i-1]<0.04: ys[i]=ys[i-1]+0.04
for (t,v),y in zip(ends.items(),ys):
    ax.annotate(f"{NAME[t]}  {v:+.2f}",xy=(L.index[-1],v),xytext=(L.index[-1]+pd.Timedelta(days=60),y),color=INK,fontsize=10,va="center",
                arrowprops=dict(arrowstyle="-",color=C[t],lw=1))
ax.set_xlim(L.index[0],L.index[-1]+pd.Timedelta(days=900)); ax.set_xticks([pd.Timestamp(f"{y}-01-01") for y in range(2014,2027,2)])
for s in ["top","right"]: ax.spines[s].set_visible(False)
for s in ["left","bottom"]: ax.spines[s].set_color(GRID)
ax.grid(axis="y",color=GRID,lw=0.8); ax.tick_params(colors=INK2,labelsize=9)
ax.set_ylabel("累计 log 超额收益  ln(ETF/ETF₀) − ln(SPY/SPY₀)",color=INK2,fontsize=10)
ax.set_title("因子 ETF 相对 SPY 的累计 log 超额收益（2013-07-18 → 2026-11-13，含分红）",color=INK,fontsize=13,loc="left",pad=12)
ax.text(0,-0.12,"0 = 与 SPY 持平；−0.10 ≈ 相对 SPY 少 9.5% 财富。数据：Supabase prices_daily（Yahoo 复权价；MTUM/QUAL 用 Yahoo 替换了库里有误的 FMP 段）",transform=ax.transAxes,color=INK2,fontsize=8.5)
ax.legend(loc="upper left",frameon=False,fontsize=10,labelcolor=INK)
fig.tight_layout(); fig.savefig(os.path.join(ROOT, "data", "factor_log_excess_vs_spy.png"),facecolor=SURF)
