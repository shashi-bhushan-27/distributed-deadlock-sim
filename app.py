"""
app.py — Streamlit front-end for the Distributed Deadlock Detection Simulation
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for Streamlit

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import streamlit as st

from simulation import SimConfig, SimResult, run_simulation

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Distributed Deadlock Detection Sim",
    page_icon="🔒",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar — parameters
# ---------------------------------------------------------------------------
st.sidebar.title("⚙️ Simulation Parameters")

num_sites = st.sidebar.slider("Sites (S)", min_value=2, max_value=6, value=3)
num_processes = st.sidebar.slider(
    "Processes (N)", min_value=3, max_value=20, value=9
)
resources_per_site = st.sidebar.slider(
    "Resources per site", min_value=1, max_value=5, value=2
)
request_prob = st.sidebar.slider(
    "Request probability", min_value=0.1, max_value=1.0, value=0.8, step=0.05
)
hold_time_min = st.sidebar.number_input(
    "Hold time min (s)", min_value=0.1, max_value=20.0, value=2.0, step=0.5
)
hold_time_max = st.sidebar.number_input(
    "Hold time max (s)", min_value=0.1, max_value=30.0, value=6.0, step=0.5
)
request_interval_min = st.sidebar.number_input(
    "Request interval min (s)", min_value=0.1, max_value=10.0, value=0.5, step=0.1
)
request_interval_max = st.sidebar.number_input(
    "Request interval max (s)", min_value=0.1, max_value=20.0, value=2.0, step=0.5
)
latency_min = st.sidebar.number_input(
    "Network latency min (s)", min_value=0.01, max_value=2.0, value=0.1, step=0.05
)
latency_max = st.sidebar.number_input(
    "Network latency max (s)", min_value=0.01, max_value=5.0, value=0.5, step=0.05
)
run_duration = st.sidebar.number_input(
    "Run duration (sim-seconds)", min_value=10.0, max_value=500.0, value=60.0, step=10.0
)
seed = st.sidebar.number_input("Random seed", min_value=0, max_value=9999, value=42)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🔒 Distributed Deadlock Detection Simulation")
st.markdown(
    """
Discrete-event simulation of the **Chandy–Misra–Haas probe/edge-chasing** algorithm
for detecting deadlocks in a distributed **Wait-For Graph (WFG)** model.

* **S sites**, each hosting a local WFG, a set of resources, and a subset of processes.
* A process may request resources across sites (two-phase acquisition).
* When a process becomes blocked, it sends a *probe* along the WFG edges.
* A probe that returns to its initiator signals a **distributed deadlock**.
"""
)

# ---------------------------------------------------------------------------
# Run / Reset buttons
# ---------------------------------------------------------------------------
col_run, col_reset, _ = st.columns([1, 1, 6])
run_clicked = col_run.button("▶ Run Simulation", type="primary")
reset_clicked = col_reset.button("🔄 Reset")

if reset_clicked:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ---------------------------------------------------------------------------
# Run simulation on button click
# ---------------------------------------------------------------------------
if run_clicked:
    cfg = SimConfig(
        num_sites=num_sites,
        num_processes=num_processes,
        resources_per_site=resources_per_site,
        request_prob=request_prob,
        hold_time_min=hold_time_min,
        hold_time_max=hold_time_max,
        request_interval_min=request_interval_min,
        request_interval_max=request_interval_max,
        latency_min=latency_min,
        latency_max=latency_max,
        run_duration=run_duration,
        seed=int(seed),
    )
    with st.spinner("Running simulation…"):
        result = run_simulation(cfg)
    st.session_state["result"] = result
    st.session_state["cfg"] = cfg

# ---------------------------------------------------------------------------
# Display results
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.info("Configure parameters in the sidebar and click **▶ Run Simulation** to start.")
    st.stop()

result: SimResult = st.session_state["result"]
cfg: SimConfig = st.session_state["cfg"]

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
st.subheader("📊 Summary Metrics")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Sites", cfg.num_sites)
m2.metric("Processes", cfg.num_processes)
m3.metric("Total Resources", cfg.num_sites * cfg.resources_per_site)
m4.metric("Total Events", len(result.events))
m5.metric("🔴 Deadlocks Detected", len(result.deadlocks))

# ---------------------------------------------------------------------------
# Deadlock detections table
# ---------------------------------------------------------------------------
st.subheader("🔴 Detected Deadlocks")
if result.deadlocks:
    dl_df = pd.DataFrame(
        [
            {
                "#": i + 1,
                "Detected at (sim-time)": d["time"],
                "Cycle": d["cycle_str"],
                "Sites involved": d["sites_str"],
            }
            for i, d in enumerate(result.deadlocks)
        ]
    )
    st.dataframe(dl_df, use_container_width=True, hide_index=True)
else:
    st.success(
        "No deadlocks detected in this run. "
        "Try increasing hold times, request probability, or the number of processes."
    )

# ---------------------------------------------------------------------------
# Per-site WFG plots
# ---------------------------------------------------------------------------
st.subheader("🗺️ Per-Site Wait-For Graphs (final state)")

# Collect all cycles for highlighting
cycle_edges: set[tuple[int, int]] = set()
for d in result.deadlocks:
    nodes = d["cycle"]
    for i in range(len(nodes) - 1):
        cycle_edges.add((nodes[i], nodes[i + 1]))

num_cols = min(cfg.num_sites, 3)
cols = st.columns(num_cols)

for site_id in range(cfg.num_sites):
    col = cols[site_id % num_cols]
    edges = result.final_wfg_edges.get(site_id, [])

    G = nx.DiGraph()
    for pid in range(cfg.num_processes):
        G.add_node(pid)
    for u, v in edges:
        G.add_edge(u, v)

    fig, ax = plt.subplots(figsize=(4, 3))
    ax.set_title(f"Site {site_id} WFG", fontsize=11, fontweight="bold")

    # Layout
    try:
        pos = nx.spring_layout(G, seed=42)
    except Exception:
        pos = nx.circular_layout(G)

    # Node colors: blue = processes home to this site
    home_pids = {pid for pid in range(cfg.num_processes) if pid % cfg.num_sites == site_id}
    node_colors = [
        "#4a90d9" if pid in home_pids else "#b0b8c1" for pid in G.nodes()
    ]

    # Edge colors: red = deadlock cycle edge, grey = normal
    edge_colors = []
    for u, v in G.edges():
        if (u, v) in cycle_edges:
            edge_colors.append("#e74c3c")
        else:
            edge_colors.append("#7f8c8d")

    nx.draw_networkx(
        G,
        pos=pos,
        ax=ax,
        node_color=node_colors,
        edge_color=edge_colors if edge_colors else "#7f8c8d",
        node_size=500,
        font_size=8,
        font_color="white",
        arrows=True,
        arrowsize=15,
        width=2.0,
    )

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#4a90d9", label="Home process"),
        Patch(facecolor="#b0b8c1", label="Remote process"),
    ]
    if any(c == "#e74c3c" for c in edge_colors):
        legend_elements.append(
            Patch(facecolor="#e74c3c", label="Deadlock edge")
        )
    ax.legend(handles=legend_elements, loc="lower right", fontsize=6)
    ax.axis("off")
    plt.tight_layout()
    col.pyplot(fig)
    plt.close(fig)

# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------
st.subheader("📋 Simulation Event Log")

EVENT_COLORS = {
    "ACQUIRE": "🟢",
    "RELEASE": "🔵",
    "BLOCK": "🟡",
    "DEADLOCK": "🔴",
    "SIM_END": "⚪",
}

filter_types = st.multiselect(
    "Filter event types",
    options=["ACQUIRE", "RELEASE", "BLOCK", "DEADLOCK", "SIM_END"],
    default=["BLOCK", "DEADLOCK", "SIM_END"],
)

events_to_show = [e for e in result.events if e["type"] in filter_types]
if events_to_show:
    log_df = pd.DataFrame(
        [
            {
                "Sim-time": e["time"],
                "Type": f"{EVENT_COLORS.get(e['type'], '')} {e['type']}",
                "Message": e["message"],
            }
            for e in events_to_show
        ]
    )
    st.dataframe(log_df, use_container_width=True, hide_index=True)
else:
    st.info("No events match the selected filter.")

# ---------------------------------------------------------------------------
# Algorithm explanation
# ---------------------------------------------------------------------------
with st.expander("ℹ️ Algorithm Details"):
    st.markdown(
        """
### Chandy–Misra–Haas Edge-Chasing Algorithm (WFG variant)

1. **Wait-For Graph**: Directed graph where edge **Pi → Pj** means process Pi
   is blocked waiting for a resource currently held by Pj.

2. **Probe message**: `probe(initiator, sender, receiver)` — a lightweight message
   forwarded along WFG edges.

3. **Initiation**: When process Pi becomes blocked on a resource held by Pj,
   it sends `probe(Pi, Pi, Pj)` after a simulated network delay.

4. **Forwarding rule**: When process Pk receives `probe(i, j, k)`:
   - If `k == i`: a **cycle** back to the initiator ⇒ **deadlock detected**.
   - If Pk is still blocked and hasn't forwarded for initiator `i` yet:
     forward `probe(i, k, Pm)` for every successor Pm in the WFG.

5. **Suppression**: A per-initiator visited set prevents probe storms —
   each `(initiator, receiver)` pair is forwarded at most once.

6. **Network latency**: Each probe delivery is delayed by a random uniform
   value in `[latency_min, latency_max]` simulation seconds.
"""
    )
