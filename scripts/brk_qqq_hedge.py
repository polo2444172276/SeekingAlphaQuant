"""BRK-B / QQQ hedge study: does mixing the two raise the Sharpe ratio?

Covers correlation, crisis returns, static mixes (monthly rebalance),
walk-forward weights (trailing 3y), and a long-BRK / short-QQQ beta hedge.
Run: python scripts/brk_qqq_hedge.py
"""
import numpy as np
import pandas as pd
import yfinance as yf

d = yf.download(["BRK-B", "QQQ", "SPY", "^IRX"], start="1999-03-10",
                auto_adjust=True, progress=False)["Close"]
r=d[['BRK-B','QQQ','SPY']].pct_change().dropna()
rf=(d['^IRX']/100/252).shift(1).reindex(r.index).fillna(0)
def stats(x,rfx):
    ex=x-rfx; ann=(1+x).prod()**(252/len(x))-1
    vol=x.std()*np.sqrt(252); sh=ex.mean()/x.std()*np.sqrt(252)
    eq=(1+x).cumprod(); mdd=(eq/eq.cummax()-1).min()
    return ann,vol,sh,mdd
def port(w,rr):  # monthly rebalance
    out=[];
    for _,g in rr.groupby(rr.index.to_period('M')):
        eq=(1+g).cumprod(); v=(eq*w).sum(axis=1); out.append(v.pct_change().fillna(v.iloc[0]-1))
    return pd.concat(out)
R=r[['BRK-B','QQQ']]
print("Daily corr full:",R.corr().iloc[0,1].round(3)," monthly:",(1+R).resample('ME').prod().sub(1).corr().iloc[0,1].round(3))
for a,b in [('1999','2009'),('2010','2019'),('2020','2026')]:
    print(f" corr {a}-{b}: {R[a:b].corr().iloc[0,1]:.3f}")
rc=R.rolling(252).corr().unstack()['BRK-B']['QQQ']; print(" rolling 1y corr min/median/max:",rc.min().round(2),rc.median().round(2),rc.max().round(2))
print("\nStatic mixes (monthly rebal) BRK weight:")
for per in [('1999-03','2026-11'),('2010','2026-11'),('2016','2026-11')]:
    rr=R[per[0]:per[1]]; f=rf[per[0]:per[1]]
    print(f"-- {per[0]}..{per[1]}")
    best=None
    for wb in np.arange(0,1.01,0.1):
        p=port(np.array([wb,1-wb]),rr); s=stats(p,f)
        print(f"  BRK {wb:.0%}: CAGR {s[0]:6.1%} vol {s[1]:5.1%} Sharpe {s[2]:.2f} MDD {s[3]:6.1%}")
    s=stats(r['SPY'][per[0]:per[1]],f); print(f"  SPY ref: CAGR {s[0]:6.1%} vol {s[1]:5.1%} Sharpe {s[2]:.2f} MDD {s[3]:6.1%}")
# crisis behaviour
print("\nCrisis returns:")
for n,a,b in [('Dotcom','2000-03-24','2002-10-09'),('GFC','2007-10-09','2009-03-09'),('Covid','2020-02-19','2020-03-23'),('2022','2022-01-03','2022-12-28'),('Apr2025','2025-02-19','2025-04-08')]:
    x=(1+R[a:b]).prod()-1; print(f"  {n}: BRK {x['BRK-B']:6.1%}  QQQ {x['QQQ']:6.1%}")
# walk-forward inverse-vol / max-sharpe using trailing 3y
print("\nWalk-forward (trailing 3y, monthly):")
m=(1+R).resample('ME').prod()-1; mrf=(1+rf).resample('ME').prod()-1
res={'invvol':[], 'maxsharpe':[], '50/50':[]}
idx=m.index[36:]
for t in idx:
    h=m.loc[:t].iloc[-37:-1]; ex=h.sub(mrf.loc[h.index],axis=0)
    iv=1/h.std(); w1=iv/iv.sum()
    S=h.cov().values; mu=ex.mean().values
    try: w=np.linalg.solve(S,mu); w=np.clip(w,0,None); w2=w/w.sum() if w.sum()>0 else np.array([.5,.5])
    except: w2=np.array([.5,.5])
    res['invvol'].append((m.loc[t]*w1).sum()); res['maxsharpe'].append((m.loc[t]*w2).sum()); res['50/50'].append(m.loc[t].mean())
def mst(x,f):
    x=pd.Series(x,index=idx); f=f.loc[idx]; eq=(1+x).cumprod()
    return f"CAGR {eq.iloc[-1]**(12/len(x))-1:6.1%} vol {x.std()*12**.5:5.1%} Sharpe {(x-f).mean()/x.std()*12**.5:.2f} MDD {(eq/eq.cummax()-1).min():6.1%}"
for k,v in res.items(): print(f"  {k:9s}",mst(v,mrf))
for c in ['BRK-B','QQQ']: print(f"  {c:9s}",mst(m.loc[idx,c].values,mrf))
# long/short hedge: long BRK, short beta*QQQ (rolling 1y beta)
print("\nLong BRK / short QQQ (rolling beta hedge):")
beta=(R['BRK-B'].rolling(252).cov(R['QQQ'])/R['QQQ'].rolling(252).var()).shift(1)
ls=(R['BRK-B']-beta*(R['QQQ']-rf)).dropna()
s=stats(ls,rf.loc[ls.index]); print(f"  CAGR {s[0]:6.1%} vol {s[1]:5.1%} Sharpe {s[2]:.2f} MDD {s[3]:6.1%}  avg beta {beta.mean():.2f}")
for a,b in [('2000','2009'),('2010','2019'),('2020','2026')]:
    s=stats(ls[a:b],rf[a:b]); print(f"   {a}-{b}: CAGR {s[0]:6.1%} Sharpe {s[2]:.2f}")
