"""Production Streamlit dashboard for the distributed deadlock simulation."""

from __future__ import annotations

from typing import Set, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import networkx as nx
import pandas as pd
import streamlit as st

from simulation import SimConfig, SimResult, run_simulation

st.set_page_config(
    page_title="Distributed Deadlock Detection",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(44, 123, 229, 0.12), transparent 28%),
                radial-gradient(circle at top right, rgba(16, 185, 129, 0.10), transparent 24%),
                linear-gradient(180deg, #f7f9fc 0%, #eef3f9 100%);
        }
        .hero {
            padding: 1.8rem 1.8rem 1.4rem;
            border-radius: 24px;
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(15, 23, 42, 0.08);
            box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08);
            margin-bottom: 1rem;
            backdrop-filter: blur(8px);
        }
        .hero h1 {
            margin: 0;
            font-size: 2.5rem;
            line-height: 1.05;
            letter-spacing: -0.04em;
            color: #0f172a;
        }
        .hero p {
            margin: 0.7rem 0 0;
            color: rgba(15, 23, 42, 0.78);
            font-size: 1.02rem;
            line-height: 1.65;
            max-width: 74ch;
        }
        .pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1rem;
        }
        .pill {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.42rem 0.8rem;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.05);
            border: 1px solid rgba(15, 23, 42, 0.08);
            color: #0f172a;
            font-size: 0.88rem;
            font-weight: 600;
        }
        .surface {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 20px;
            box-shadow: 0 12px 36px rgba(15, 23, 42, 0.06);
            padding: 1rem 1.1rem;
        }
        .section-title {
            font-size: 1.05rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #0f172a;
            margin: 0 0 0.7rem;
        }
        .muted-copy {
            color: rgba(15, 23, 42, 0.72);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <h1>Distributed Deadlock Detection</h1>
            <p>
                A production-ready Streamlit dashboard for exploring a simulated
                Chandy–Misra–Haas probe/edge-chasing workflow across sites,
                resources, and wait-for graphs.
            </p>
            <div class="pill-row">
                <span class="pill">Discrete-event simulation</span>
                <span class="pill">Wait-for graph analysis</span>
                <span class="pill">Cycle detection and reporting</span>
                <span class="pill">Exportable event logs</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def validate_config_ranges() -> None:
    if hold_time_min > hold_time_max:
        st.sidebar.error("Hold time min must be less than or equal to hold time max.")
        st.stop()
    if request_interval_min > request_interval_max:
        st.sidebar.error("Request interval min must be less than or equal to request interval max.")
        st.stop()
    if latency_min > latency_max:
        st.sidebar.error("Network latency min must be less than or equal to max.")
        st.stop()


def build_download_frame(result: SimResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"time": event["time"], "type": event["type"], "message": event["message"]}
            for event in result.events
        ]
    )


inject_styles()

st.sidebar.title("⚙️ Simulation Parameters")
st.sidebar.caption("Tune contention, latency, and runtime. Same seed + same inputs = same run.")

num_sites = st.sidebar.slider("Sites (S)", min_value=2, max_value=6, value=3)
num_processes = st.sidebar.slider("Processes (N)", min_value=3, max_value=20, value=9)
resources_per_site = st.sidebar.slider("Resources per site", min_value=1, max_value=5, value=2)
request_prob = st.sidebar.slider("Request probability", min_value=0.1, max_value=1.0, value=0.8, step=0.05)
hold_time_min = st.sidebar.number_input("Hold time min (s)", min_value=0.1, max_value=20.0, value=2.0, step=0.5)
hold_time_max = st.sidebar.number_input("Hold time max (s)", min_value=0.1, max_value=30.0, value=6.0, step=0.5)
request_interval_min = st.sidebar.number_input("Request interval min (s)", min_value=0.1, max_value=10.0, value=0.5, step=0.1)
request_interval_max = st.sidebar.number_input("Request interval max (s)", min_value=0.1, max_value=20.0, value=2.0, step=0.5)
latency_min = st.sidebar.number_input("Network latency min (s)", min_value=0.01, max_value=2.0, value=0.1, step=0.05)
latency_max = st.sidebar.number_input("Network latency max (s)", min_value=0.01, max_value=5.0, value=0.5, step=0.05)
run_duration = st.sidebar.number_input("Run duration (sim-seconds)", min_value=10.0, max_value=500.0, value=60.0, step=10.0)
seed = st.sidebar.number_input("Random seed", min_value=0, max_value=9999, value=42)

validate_config_ranges()

render_hero()

st.markdown(
    """
    <div class="surface">
        <div class="section-title">What this dashboard shows</div>
        <div class="muted-copy">
            Each run generates a full simulation trace, highlights detected cycles,
            and renders the final wait-for graph per site. The same app can be
            deployed locally, in a container, or behind a managed Streamlit host.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

col_run, col_reset, _ = st.columns([1, 1, 6])
run_clicked = col_run.button("▶ Run Simulation", type="primary")
reset_clicked = col_reset.button("🔄 Reset")

if reset_clicked:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

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

if "result" not in st.session_state:
    left, right = st.columns([1.35, 1])
    with left:
        st.markdown(
            """
            <div class="surface">
                <div class="section-title">Ready to run</div>
                <div class="muted-copy">
                    Use the sidebar to set contention and latency, then run the
                    simulation to inspect deadlock cycles, event logs, and the final
                    wait-for graphs.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """
            <div class="surface">
                <div class="section-title">Production posture</div>
                <div class="muted-copy">
                    This app is designed to run statelessly per browser session and
                    is safe to containerize behind a reverse proxy or managed hosting
                    platform.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()

result: SimResult = st.session_state["result"]
cfg: SimConfig = st.session_state["cfg"]

tab_overview, tab_graphs, tab_events, tab_algorithm = st.tabs(["Overview", "Graphs", "Event log", "Algorithm"])

cycle_edges: Set[Tuple[int, int]] = set()
for deadlock in result.deadlocks:
    nodes = deadlock["cycle"]
    for index in range(len(nodes) - 1):
        cycle_edges.add((nodes[index], nodes[index + 1]))

with tab_overview:
    st.markdown("<div class='section-title'>Run summary</div>", unsafe_allow_html=True)
    metric_columns = st.columns(5)
    metric_columns[0].metric("Sites", cfg.num_sites)
    metric_columns[1].metric("Processes", cfg.num_processes)
    metric_columns[2].metric("Resources", cfg.num_sites * cfg.resources_per_site)
    metric_columns[3].metric("Events", len(result.events))
    metric_columns[4].metric("Deadlocks", len(result.deadlocks))

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("<div class='section-title'>Detected deadlocks</div>", unsafe_allow_html=True)
        if result.deadlocks:
            deadlock_df = pd.DataFrame(
                [
                    {
                        "#": index + 1,
                        "Detected at (sim-time)": deadlock["time"],
                        "Cycle": deadlock["cycle_str"],
                        "Sites involved": deadlock["sites_str"],
                    }
                    for index, deadlock in enumerate(result.deadlocks)
                ]
            )
            st.dataframe(deadlock_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download deadlocks CSV",
                data=deadlock_df.to_csv(index=False).encode("utf-8"),
                file_name="deadlocks.csv",
                mime="text/csv",
            )
        else:
            st.success("No deadlocks detected in this run. Try increasing hold times, request probability, or the number of processes.")
    with right:
        st.markdown("<div class='section-title'>Exportable trace</div>", unsafe_allow_html=True)
        trace_df = build_download_frame(result)
        st.dataframe(trace_df.head(12), use_container_width=True, hide_index=True)
        st.download_button(
            "Download event log CSV",
            data=trace_df.to_csv(index=False).encode("utf-8"),
            file_name="simulation-events.csv",
            mime="text/csv",
        )

with tab_graphs:
    st.markdown("<div class='section-title'>Per-site wait-for graphs</div>", unsafe_allow_html=True)
    st.caption("Red edges belong to at least one detected deadlock cycle.")
    num_cols = min(cfg.num_sites, 3)
    graph_columns = st.columns(num_cols)

    for site_id in range(cfg.num_sites):
        target_col = graph_columns[site_id % num_cols]
        edges = result.final_wfg_edges.get(site_id, [])

        graph = nx.DiGraph()
        for pid in range(cfg.num_processes):
            graph.add_node(pid)
        for waiting_pid, holder_pid in edges:
            graph.add_edge(waiting_pid, holder_pid)

        fig, ax = plt.subplots(figsize=(4, 3))
        ax.set_title(f"Site {site_id} WFG", fontsize=11, fontweight="bold")

        try:
            pos = nx.spring_layout(graph, seed=42)
        except Exception:
            pos = nx.circular_layout(graph)

        home_pids = {pid for pid in range(cfg.num_processes) if pid % cfg.num_sites == site_id}
        node_colors = ["#2c7be5" if pid in home_pids else "#a8b2c1" for pid in graph.nodes()]

        edge_colors = ["#e74c3c" if edge in cycle_edges else "#7f8c8d" for edge in graph.edges()]

        nx.draw_networkx(
            graph,
            pos=pos,
            ax=ax,
            node_color=node_colors,
            edge_color=edge_colors if edge_colors else "#7f8c8d",
            node_size=560,
            font_size=8,
            font_color="white",
            arrows=True,
            arrowsize=15,
            width=2.0,
        )

        legend_elements = [
            Patch(facecolor="#2c7be5", label="Home process"),
            Patch(facecolor="#a8b2c1", label="Remote process"),
        ]
        if any(color == "#e74c3c" for color in edge_colors):
            legend_elements.append(Patch(facecolor="#e74c3c", label="Deadlock edge"))
        ax.legend(handles=legend_elements, loc="lower right", fontsize=6)
        ax.axis("off")
        plt.tight_layout()
        target_col.pyplot(fig)
        plt.close(fig)

with tab_events:
    st.markdown("<div class='section-title'>Simulation event log</div>", unsafe_allow_html=True)

    event_colors = {
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

    filtered_events = [event for event in result.events if event["type"] in filter_types]
    if filtered_events:
        event_df = pd.DataFrame(
            [
                {
                    "Sim-time": event["time"],
                    "Type": f"{event_colors.get(event['type'], '')} {event['type']}",
                    "Message": event["message"],
                }
                for event in filtered_events
            ]
        )
        st.dataframe(event_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download filtered event log CSV",
            data=event_df.to_csv(index=False).encode("utf-8"),
            file_name="filtered-events.csv",
            mime="text/csv",
        )
    else:
        st.info("No events match the selected filter.")

with tab_algorithm:
    st.markdown(
        """
        <div class="surface">
            <div class="section-title">Algorithm details</div>
            <div class="muted-copy">
                The app uses a Chandy–Misra–Haas edge-chasing workflow on the
                wait-for graph. When a blocked process sends a probe, the probe
                traverses successor edges until it either returns to its initiator
                or reaches a process that is no longer blocked.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("How detection works"):
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
