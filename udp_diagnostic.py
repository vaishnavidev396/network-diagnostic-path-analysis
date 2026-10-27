"""Append every completed UDP diagnostic to measurements.csv."""
import csv, os
from datetime import datetime
BASE=os.path.dirname(os.path.abspath(__file__))
MEASUREMENTS_CSV=os.path.join(BASE,"measurements.csv")
FIELDS=["timestamp","source","destination","sent","received","lost","loss_pct","avg_rtt_ms","min_rtt_ms","max_rtt_ms","status"]

def append_measurement(result):
    row={k:result.get(k) for k in FIELDS}
    row["timestamp"]=row.get("timestamp") or datetime.now().astimezone().isoformat(timespec="seconds")
    row["source"]=row.get("source") or "h1"; row["destination"]=row.get("destination") or "h4"
    row["status"]="Available" if int(row.get("received") or 0)>0 else "Unavailable"
    exists=os.path.exists(MEASUREMENTS_CSV) and os.path.getsize(MEASUREMENTS_CSV)>0
    with open(MEASUREMENTS_CSV,"a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if not exists: w.writeheader()
        w.writerow(row)
    return row
