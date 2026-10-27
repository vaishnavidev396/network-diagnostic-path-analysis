"""Streamlit dashboard. Start with: streamlit run app.py"""
import os
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from udp_diagnostic import append_measurement, MEASUREMENTS_CSV
from path_analysis import append_path_result, PATH_CSV, PATHS

API="http://127.0.0.1:8765"
st.set_page_config(page_title="Network Diagnostic Dashboard",page_icon="🌐",layout="wide")
st.title("🌐 Network Diagnostic & Path Analysis")
st.caption("Live Mininet diagnostics, path testing, and persistent CSV history.")
def get(path): 
    r=requests.get(API+path,timeout=3); r.raise_for_status(); return r.json()
def post(path,data):
    r=requests.post(API+path,json=data,timeout=90); r.raise_for_status(); return r.json()

try: status=get("/status"); online=True
except Exception as e:
    status=None; online=False
    st.error("Mininet API is offline. In another terminal run: sudo python3 topology.py")
    st.caption(str(e))

a,b,c,d=st.columns(4)
a.metric("Network","Running" if online else "Offline")
b.metric("Hosts",len(status["hosts"]) if status else "—")
c.metric("Switches",len(status["switches"]) if status else "—")
d.metric("Switch links UP",sum(x["up"] for x in status["links"]) if status else "—")
t1,t2,t3=st.tabs(["Topology & link control","UDP diagnostics","Path comparison & history"])

with t1:
    st.subheader("Two alternative routes")
    st.code("Path 1: h1 → s1 → s2 → s4 → h4\nPath 2: h1 → s1 → s3 → s4 → h4")
    if status:
        for x in status["links"]:
            st.write(f"{'🟢 UP' if x['up'] else '🔴 DOWN'} — {x['a']} ↔ {x['b']}")
    col1,col2,col3=st.columns(3)
    with col1: src=st.selectbox("Switch A",["s1","s2","s3","s4"],key="src")
    with col2: dst=st.selectbox("Switch B",["s1","s2","s3","s4"],index=1,key="dst")
    with col3: action=st.selectbox("Action",["down","up"])
    if st.button("Apply link change",disabled=not online):
        if src==dst: st.error("Choose two different switches.")
        else:
            try: post("/link",{"src":src,"dst":dst,"state":action}); st.success(f"{src}-{dst} set {action}."); st.rerun()
            except Exception as e: st.error(str(e))
    if st.button("Refresh status"): st.rerun()

with t2:
    st.subheader("Run actual UDP request/reply probes")
    count=st.slider("Probe count",5,100,20,5)
    if st.button("▶ Run diagnostics",type="primary",disabled=not online):
        try:
            with st.spinner("Sending UDP probes from h1 to h4..."): result=post("/diagnose",{"count":count})
            append_measurement(result); st.session_state["last_result"]=result
            st.success("Saved new row to measurements.csv.")
        except Exception as e: st.error(f"Diagnostic failed: {e}")
    result=st.session_state.get("last_result")
    if result:
        a,b,c,d=st.columns(4)
        a.metric("Received",f'{result["received"]}/{result["sent"]}')
        b.metric("Packet loss",f'{result["loss_pct"]}%')
        c.metric("Average RTT",f'{result["avg_rtt_ms"]} ms' if result["avg_rtt_ms"] is not None else "No replies")
        d.metric("Status","Available" if result["received"] else "Unavailable")
        st.json(result)

with t3:
    st.subheader("Compare Path 1 and Path 2")
    st.warning("The comparison briefly disables the competing branch, measures the selected route, then restores the original switch-link states.")
    if st.button("⚖ Compare paths",disabled=not online):
        original=get("/status")
        links={(x["a"],x["b"]):x["up"] for x in original["links"]}
        links.update({(b,a):v for (a,b),v in list(links.items())})
        branches={"Path 1":[("s1","s2"),("s2","s4")],"Path 2":[("s1","s3"),("s3","s4")]}
        rows=[]
        try:
            with st.spinner("Measuring paths..."):
                for name in ("Path 1","Path 2"):
                    for (x,y),up in links.items():
                        if x<y: post("/link",{"src":x,"dst":y,"state":"up" if up else "down"})
                    other="Path 2" if name=="Path 1" else "Path 1"
                    for x,y in branches[other]: post("/link",{"src":x,"dst":y,"state":"down"})
                    result=post("/diagnose",{"count":20}); append_measurement(result)
                    rows.append(append_path_result(name,result,"Other branch temporarily disabled"))
        except Exception as e: st.error(f"Comparison failed: {e}")
        finally:
            for (x,y),up in links.items():
                if x<y:
                    try: post("/link",{"src":x,"dst":y,"state":"up" if up else "down"})
                    except Exception: pass
        st.session_state["path_rows"]=rows
        st.success("Comparison saved to path_comparison.csv; original link states restored where possible.")
    rows=st.session_state.get("path_rows",[])
    if rows:
        df=pd.DataFrame(rows); st.dataframe(df,use_container_width=True)
        valid=df.dropna(subset=["avg_rtt_ms"])
        if not valid.empty: st.plotly_chart(px.bar(valid,x="path_name",y="avg_rtt_ms",title="Average RTT by path (ms)"),use_container_width=True)
    left,right=st.columns(2)
    with left:
        st.markdown("#### measurements.csv")
        if os.path.exists(MEASUREMENTS_CSV):
            df=pd.read_csv(MEASUREMENTS_CSV); st.dataframe(df.tail(100),use_container_width=True)
            st.download_button("Download measurements.csv",df.to_csv(index=False).encode(),"measurements.csv","text/csv")
        else: st.info("Created automatically after the first diagnostic.")
    with right:
        st.markdown("#### path_comparison.csv")
        if os.path.exists(PATH_CSV):
            df=pd.read_csv(PATH_CSV); st.dataframe(df.tail(100),use_container_width=True)
            st.download_button("Download path_comparison.csv",df.to_csv(index=False).encode(),"path_comparison.csv","text/csv")
        else: st.info("Created automatically after the first path comparison.")
