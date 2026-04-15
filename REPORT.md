# REPORT — Distributed Deadlock Detection Simulation

## 1. Introduction

Deadlock is a classic problem in distributed systems: a set of processes each
hold resources and wait for resources held by other processes, forming a cycle
with no possibility of progress. In a distributed setting (multiple sites,
message-passing), detection is non-trivial because no single node has a
complete, up-to-date view of the global state.

This project builds a discrete-event simulation that:

* Models N processes competing for resources across S sites.
* Maintains a per-site **Wait-For Graph (WFG)**.
* Implements the **Chandy–Misra–Haas (CMH) probe/edge-chasing** algorithm to
  detect global cycles spanning multiple sites.
* Provides a **Streamlit** web UI for interactive exploration.

---

## 2. System Model

### 2.1 Sites and Processes

* The system has **S sites** (configurable, default 3).
* Each site hosts `R` resources (configurable, default 2 per site) and owns a
  subset of the N processes (processes assigned round-robin by `pid % S`).
* Total resources = S × R; total processes = N.

### 2.2 Resources

A resource is identified by `(site_id, res_id)`. At most one process can hold
it at a time (mutual exclusion). Waiting processes are queued in FIFO order.

### 2.3 Wait-For Graph

Each site maintains a **NetworkX DiGraph** where:

* Nodes are all process IDs.
* A directed edge **Pi → Pj** means Pi is currently blocked waiting for a
  resource held by Pj.

Edges are added when a process blocks and removed when the holder releases the
resource (and either the waiter acquires it or there are no waiters left).

For simplicity every site maintains a **global view** of the WFG; in a real
system each site would maintain only locally-known edges and rely on probe
messages to infer remote dependencies.

### 2.4 Two-Phase Acquisition

To ensure deadlocks can occur, each process follows a **two-phase locking**
style: it requests resource A, and while holding A, requests resource B. This
creates the circular-wait conditions needed for deadlock. After holding both
for a random "work time", it releases both.

---

## 3. Algorithm

### 3.1 Chandy–Misra–Haas (WFG variant)

The CMH algorithm for WFG-based deadlock detection works as follows:

**Probe format**: `probe(initiator, sender, receiver)`

| Event | Action |
|-------|--------|
| Pi becomes blocked on Pj | Pi sends `probe(Pi, Pi, Pj)` after network latency |
| Pk receives `probe(i, j, k)` | If `k == i`: **deadlock detected**; else if Pk is blocked on Pm and not already forwarded for initiator i: send `probe(i, k, Pm)` |

### 3.2 Probe Suppression

A `probes_sent[initiator]` set tracks which receiver processes have already
received a forwarded probe for each initiator. This prevents exponential
message storms in dense WFGs.

### 3.3 Network Latency

Each probe delivery is delayed by a random value drawn uniformly from
`[latency_min, latency_max]` simulation seconds, modelling realistic
message propagation delays.

### 3.4 Cycle Reconstruction

When a probe returns to its initiator, NetworkX's `find_cycle` on the
initiator's home-site WFG is used to reconstruct the actual cycle node list
for reporting.

---

## 4. Implementation

### 4.1 File Structure

| File | Purpose |
|------|---------|
| `simulation.py` | SimPy simulation core: `SimConfig`, `Resource`, `Process`, `SimResult`, `DistributedDeadlockSim` |
| `app.py` | Streamlit UI: parameter sidebar, run/reset buttons, WFG plots, event log, deadlock table |
| `requirements.txt` | Python package dependencies |
| `README.md` | Quick-start guide and parameter reference |
| `REPORT.md` | This report |

### 4.2 Key Classes

#### `SimConfig`
Dataclass holding all simulation parameters (sites, processes, resources,
probabilities, timing ranges, seed).

#### `Resource`
Tracks `holder` (pid or None) and `waiters` (list of `(pid, SimPy Event)`).

#### `Process`
Tracks `status` (idle/running/blocked), `holding` (list of resources),
and `waiting_for` (resource being awaited).

#### `DistributedDeadlockSim`
Core simulation class:

* Builds the SimPy environment, resources, processes, and per-site WFGs.
* `_request_resource` — allocates or blocks with WFG edge insertion.
* `_release_resource` — hands resource to next waiter, updates WFG.
* `_initiate_probe` / `_send_probe` / `_receive_probe` — CMH probe logic.
* `_process_loop` — two-phase acquisition loop for each process.
* `run()` — starts all process coroutines and runs `env.run(until=...)`.

#### `SimResult`
Collects:
* `events` — list of `{time, type, message}` dicts.
* `deadlocks` — list of `{time, cycle, cycle_str, sites, sites_str}` dicts.
* `final_wfg_edges` — per-site edge lists captured at simulation end.

---

## 5. Experiments

### 5.1 Baseline (default parameters)

| Parameter | Value |
|-----------|-------|
| Sites | 3 |
| Processes | 9 |
| Resources/site | 2 |
| Request probability | 0.8 |
| Hold time | 2–6 s |
| Run duration | 60 s |
| Seed | 42 |

**Result**: 1 deadlock detected at t ≈ 42.55 s involving processes P7 → P1 → P5 → P7 across sites S1, S2.

### 5.2 Effect of Hold Time

Longer hold times increase resource contention and therefore deadlock
probability. With `hold_time_min=5, hold_time_max=15` and the same seed,
multiple deadlocks were observed.

### 5.3 Effect of Number of Processes

Increasing N (more processes) relative to the number of resources (S × R)
increases contention. With N=15, S=3, R=2 (15 processes, 6 resources)
deadlocks become very frequent.

### 5.4 Distributed vs. Local Cycles

The algorithm correctly detects cycles spanning multiple sites (edges
cross-site). The `sites_str` field in each deadlock report shows which
sites' home processes are involved.

---

## 6. Limitations

1. **Simplified WFG model**: All sites maintain a full global WFG copy for
   simplicity. In a real distributed system each site would maintain only its
   local edges and the probe mechanism itself provides the distributed
   traversal.

2. **No deadlock resolution**: The simulation detects but does not resolve
   deadlocks (no victim selection / resource preemption). Deadlocked processes
   remain blocked for the remainder of the simulation.

3. **No process timeouts**: Processes wait indefinitely. A production system
   would add timeouts and retry logic.

4. **Single resource per request**: Each two-phase round requests exactly two
   resources. Real systems may hold many more.

5. **Probe TTL not implemented**: Suppression is per-(initiator, receiver)
   visited-set; a TTL-based expiry is not used because the simulation
   has a finite duration.

---

## 7. How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the interactive UI
streamlit run app.py
```

Open `http://localhost:8501`, adjust parameters in the sidebar, and click
**▶ Run Simulation**.

### Export this report to PDF

```bash
pandoc REPORT.md -o REPORT.pdf
```

---

## 8. References

* Chandy, K. M., Misra, J., & Haas, L. M. (1983). *Distributed deadlock
  detection*. ACM Transactions on Computer Systems, 1(2), 144–156.
* SimPy documentation: https://simpy.readthedocs.io/
* NetworkX documentation: https://networkx.org/
* Streamlit documentation: https://docs.streamlit.io/
