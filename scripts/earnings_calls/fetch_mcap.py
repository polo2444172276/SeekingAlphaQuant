import json, os, sys, time, requests, duckdb
S=sys.argv[1]
B="https://financialmodelingprep.com/stable"
files=[f"{S}/hf/data/train-0000{i}-of-00004.parquet" for i in range(4)]
syms=[r[0] for r in duckdb.sql(f"select distinct symbol from read_parquet({files})").fetchall()]
extra=["AAPL","MSFT","GOOGL","NVDA","AMZN","META","TSLA","AVGO","LLY","WMT","JPM","V","ORCL","XOM","PLTR","ANET","CRWD","APP","GEV"]
syms=sorted(set(syms)|set(extra))
print(len(syms),flush=True)
for s in syms:
    f=f"{S}/mcap/{s}.json"
    if os.path.exists(f): continue
    out=[]
    for a,b in [("2005-01-01","2010-12-31"),("2011-01-01","2016-12-31"),("2017-01-01","2022-12-31"),("2023-01-01","2026-11-24")]:
        for k in range(4):
            try:
                d=requests.get(f"{B}/historical-market-capitalization",params={"symbol":s,"from":a,"to":b,"limit":5000},timeout=60).json()
                if isinstance(d,list): break
                time.sleep(8*(k+1))
            except Exception: time.sleep(3); d=[]
        if isinstance(d,list): out+=d
        time.sleep(0.14)
    last={}
    for x in out:
        q=(x["date"][:4],(int(x["date"][5:7])-1)//3)
        if q not in last or x["date"]>last[q]["date"]: last[q]=x
    json.dump(sorted(last.values(),key=lambda x:x["date"]),open(f,"w"))
print("done",flush=True)
