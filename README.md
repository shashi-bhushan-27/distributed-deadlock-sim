# Distributed Deadlock Detection Simulation

A discrete-event simulation of the **Chandy–Misra–Haas probe/edge-chasing algorithm** for detecting deadlocks in a distributed system modelled with **Wait-For Graphs (WFG)**.

Built with **SimPy** (simulation engine) and **Streamlit** (interactive UI).

---

## Overview

* **N processes** compete for shared resources distributed across **S sites**.
* Each site maintains a local **NetworkX DiGraph** as its Wait-For Graph.
* A **probe-based** deadlock-detection algorithm propagates lightweight probe messages along WFG edges; a cycle is confirmed when a probe returns to its initiator.
* A **Streamlit** web UI lets you configure every parameter, run the simulation, and inspect WFG plots, event logs, and detected deadlocks.

---

## Algorithm

### Wait-For Graph (WFG)
An edge **Pi → Pj** in the WFG means process Pi is blocked waiting for a resource currently held by Pj.

### Chandy–Misra–Haas Edge-Chasing (WFG variant)

| Step | Description |
|------|-------------|
| **Initiation** | When Pi becomes blocked on a resource held by Pj, Pi sends `probe(Pi, Pi, Pj)` after a simulated network delay. |
| **Forwarding** | When Pk receives `probe(i, j, k)` and Pk is blocked on Pm: forward `probe(i, k, Pm)`. |
| **Detection** | If `k == i` the probe has completed a cycle → **deadlock**. |
| **Suppression** | A per-initiator visited set prevents duplicate probe storms. |

---

## Project Structure

```
distributed-deadlock-sim/
├── app.py              # Streamlit UI
├── simulation.py       # SimPy simulation core + CMH algorithm
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── REPORT.md           # Detailed technical report
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Streamlit app

```bash
streamlit run app.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

### 3. Run a simulation programmatically

```python
from simulation import SimConfig, run_simulation

cfg = SimConfig(
    num_sites=3,
    num_processes=9,
    resources_per_site=2,
    request_prob=0.8,
    hold_time_min=2.0,
    hold_time_max=6.0,
    run_duration=60.0,
    seed=42,
)
result = run_simulation(cfg)

print(f"Events: {len(result.events)}")
print(f"Deadlocks: {len(result.deadlocks)}")
for d in result.deadlocks:
    print(d["cycle_str"], "—", d["sites_str"])
```

---

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `num_sites` | Number of sites (S) | 3 |
| `num_processes` | Number of processes (N) | 9 |
| `resources_per_site` | Resources hosted at each site | 2 |
| `request_prob` | Probability a process requests resources in a round | 0.8 |
| `hold_time_min/max` | Uniform range for how long a process holds resources (sim-s) | 2–6 |
| `request_interval_min/max` | Uniform range for inter-request idle time (sim-s) | 0.5–2 |
| `latency_min/max` | Uniform range for network probe latency (sim-s) | 0.1–0.5 |
| `run_duration` | Total simulation time (sim-seconds) | 60 |
| `seed` | Random seed for reproducibility | 42 |

---

## Export README as PDF

```bash
pip install grip
grip README.md --export README.html
# then print README.html to PDF from your browser
```

Or with `pandoc`:

```bash
pandoc README.md -o README.pdf
```
