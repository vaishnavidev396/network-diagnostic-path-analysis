"""Path definitions and append-only path_comparison.csv history."""
import csv, os
from datetime import datetime
BASE=os.path.dirname(os.path.abspath(__file__))
PATH_CSV=os.path.join(BASE,"path_comparison.csv")
FIELDS=["timestamp","path_name","route","sent","received","loss_pct","avg_rtt_ms","status","notes"]
PATHS={"Path 1":["h1","s1","s2","s4","h4"],"Path 2":["h1","s1","s3","s4","h4"]}

def append_path_result(path_name,result,notes=""):
    row={"timestamp":result.get("timestamp") or datetime.now().astimezone().isoformat(timespec="seconds"),
         "path_name":path_name,"route":"-".join(PATHS[path_name]),"sent":result.get("sent",0),
         "received":result.get("received",0),"loss_pct":result.get("loss_pct",100),
         "avg_rtt_ms":result.get("avg_rtt_ms"),"status":"Available" if result.get("received",0)>0 else "Unavailable",
         "notes":notes}
    exists=os.path.exists(PATH_CSV) and os.path.getsize(PATH_CSV)>0
    with open(PATH_CSV,"a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if not exists: w.writeheader()
        w.writerow(row)
    return row
