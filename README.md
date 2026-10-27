# Network Diagnostic & Path Analysis Tool

## Included files
- `topology.py`: Mininet topology plus localhost API used by the dashboard.
- `udp_diagnostic.py`: writes UDP probe results to `measurements.csv`.
- `sdn_controller.py`: Ryu OpenFlow 1.3 learning-switch app and topology discovery.
- `path_analysis.py`: route definitions and `path_comparison.csv` persistence.
- `app.py`: Streamlit visual dashboard.
- `requirements.txt`: dashboard dependencies.

## Topology
Hosts h1 (10.0.0.1) and h4 (10.0.0.4), switches s1-s4.
Path 1: h1-s1-s2-s4-h4
Path 2: h1-s1-s3-s4-h4

## Run in three terminals
Terminal 1, in the environment where Ryu is installed:
```bash
ryu-manager --observe-links sdn_controller.py
```
Terminal 2:
```bash
sudo python3 topology.py
```
Terminal 3, install dashboard packages in a virtual environment if needed:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
Open the local Streamlit URL, usually http://localhost:8501.

## Automatic CSVs
`measurements.csv` is created after the first diagnostic. Every subsequent diagnostic appends a row.
`path_comparison.csv` is created after the first path comparison. Each comparison appends rows.
Both are stored next to the Python files and are not overwritten on normal runs.

## Important notes
- Run in a disposable lab VM. Mininet requires root; dashboard API binds to localhost only.
- UDP probes are actual request/reply tests in Mininet host namespaces.
- The Ryu controller provides learning-switch forwarding and topology discovery. It is a starter controller, not a production-grade path optimizer; guaranteed shortest-path rerouting needs additional route-aware controller logic and testing.
- Path comparison briefly disables the competing branch and restores original switch-link states. Do not run another link-changing process at the same time.
