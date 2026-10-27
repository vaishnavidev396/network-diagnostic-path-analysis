#!/usr/bin/env python3
"""Run with sudo. Starts Mininet and a localhost API for the dashboard."""
import json, os, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.log import setLogLevel, info

class DiagnosticTopo(Topo):
    def build(self):
        h1=self.addHost("h1", ip="10.0.0.1/24"); h4=self.addHost("h4", ip="10.0.0.4/24")
        s1=self.addSwitch("s1"); s2=self.addSwitch("s2"); s3=self.addSwitch("s3"); s4=self.addSwitch("s4")
        self.addLink(h1,s1,bw=10,delay="2ms")
        self.addLink(s1,s2,bw=10,delay="3ms"); self.addLink(s2,s4,bw=10,delay="3ms")
        self.addLink(s1,s3,bw=10,delay="5ms"); self.addLink(s3,s4,bw=10,delay="5ms")
        self.addLink(s4,h4,bw=10,delay="2ms")

def udp_probe(net, count=20, timeout=0.35):
    import json as _json
    h1,h4=net.get("h1","h4")
    server = ("import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); "
              "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('0.0.0.0',9999)); "
              "exec('while True:\\n data,addr=s.recvfrom(2048)\\n s.sendto(data,addr)')")
    proc=h4.popen([sys.executable,"-u","-c",server],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    client = (
      "import socket,time,json,sys; count=int(sys.argv[1]); timeout=float(sys.argv[2]); "
      "s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(timeout); "
      "sent=received=0; rtts=[]; "
      "exec('for i in range(count):\\n payload=str(i).encode(); start=time.perf_counter(); sent+=1\\n try:\\n  s.sendto(payload,(\\'10.0.0.4\\',9999)); data,_=s.recvfrom(2048)\\n  if data==payload: received+=1; rtts.append((time.perf_counter()-start)*1000)\\n except socket.timeout: pass\\n time.sleep(0.03)'); "
      "print(json.dumps({'sent':sent,'received':received,'lost':sent-received,"
      "'loss_pct':round((sent-received)*100/sent,2) if sent else 0,"
      "'avg_rtt_ms':round(sum(rtts)/len(rtts),3) if rtts else None,"
      "'min_rtt_ms':round(min(rtts),3) if rtts else None,"
      "'max_rtt_ms':round(max(rtts),3) if rtts else None}))")
    try:
        p=h1.popen([sys.executable,"-c",client,str(count),str(timeout)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        out,err=p.communicate(timeout=count*(timeout+0.1)+5)
        if p.returncode: raise RuntimeError(err.strip() or "UDP probe failed")
        from datetime import datetime
        result=json.loads(out.strip().splitlines()[-1])
        result.update({"source":"h1","destination":"h4","timestamp":datetime.now().astimezone().isoformat(timespec="seconds")})
        return result
    finally:
        proc.terminate()
        try: proc.wait(timeout=1)
        except Exception: proc.kill()

def handler_for(net):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send_json(self,code,obj):
            body=json.dumps(obj).encode(); self.send_response(code)
            self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            if self.path not in ("/status","/health"): return self.send_json(404,{"error":"not found"})
            links=[]
            for link in net.links:
                a,b=link.intf1.node.name,link.intf2.node.name
                if a.startswith("s") and b.startswith("s"):
                    links.append({"a":a,"b":b,"up":bool(link.intf1.isUp() and link.intf2.isUp())})
            self.send_json(200,{"running":True,"hosts":["h1","h4"],"switches":["s1","s2","s3","s4"],"links":links,
              "paths":[["h1","s1","s2","s4","h4"],["h1","s1","s3","s4","h4"]]})
        def do_POST(self):
            try:
                n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
                if self.path=="/diagnose":
                    count=max(1,min(int(data.get("count",20)),200)); self.send_json(200,udp_probe(net,count))
                elif self.path=="/link":
                    a,b=str(data["src"]),str(data["dst"]); state=str(data["state"]).lower()
                    if a not in ("s1","s2","s3","s4") or b not in ("s1","s2","s3","s4") or state not in ("up","down"):
                        return self.send_json(400,{"error":"Invalid switch link or state"})
                    net.configLinkStatus(a,b,state); self.send_json(200,{"ok":True,"src":a,"dst":b,"state":state})
                else: self.send_json(404,{"error":"not found"})
            except Exception as e: self.send_json(500,{"error":str(e)})
    return Handler

def main():
    if os.geteuid()!=0: raise SystemExit("Run with: sudo python3 topology.py")
    setLogLevel("info")
    net=Mininet(topo=DiagnosticTopo(),controller=None,switch=OVSKernelSwitch,link=TCLink,autoSetMacs=True,build=False)
    net.addController("c0",controller=RemoteController,ip="127.0.0.1",port=6653)
    net.build(); net.start()
    server=ThreadingHTTPServer(("127.0.0.1",8765),handler_for(net))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    info("*** Network and dashboard API running on 127.0.0.1:8765. Ctrl+C to stop.\\n")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: pass
    finally: server.shutdown(); net.stop()

if __name__=="__main__": main()
