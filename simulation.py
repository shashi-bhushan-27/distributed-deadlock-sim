"""
Distributed Deadlock Detection Simulation
==========================================
Implements a discrete-event simulation using SimPy of the
Chandy-Misra-Haas probe/edge-chasing algorithm for detecting
deadlocks in a distributed Wait-For Graph (WFG) model.

Architecture
------------
- S sites, each hosting R resources and a subset of N processes.
- Each site owns a local NetworkX DiGraph (the WFG).
- Edges Pi → Pj mean "Pi is blocked waiting for a resource held by Pj".
- When a process becomes blocked it initiates a probe(initiator, sender, receiver).
- Probes traverse the WFG (possibly crossing sites) with simulated
  network latency.
- A deadlock is confirmed when probe(i, *, i) arrives back at process i,
  i.e. the probe completes a cycle.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import simpy


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SimConfig:
    num_sites: int = 3
    num_processes: int = 9
    resources_per_site: int = 2
    request_prob: float = 0.8
    hold_time_min: float = 2.0
    hold_time_max: float = 6.0
    request_interval_min: float = 0.5
    request_interval_max: float = 2.0
    latency_min: float = 0.1
    latency_max: float = 0.5
    run_duration: float = 60.0
    seed: int = 42


# ---------------------------------------------------------------------------
# Resource & Process data classes
# ---------------------------------------------------------------------------

@dataclass
class Resource:
    site_id: int
    res_id: int
    # Process id currently holding this resource; None if free
    holder: Optional[int] = None
    # Ordered list of (process_id, event) waiting for this resource
    waiters: List[Tuple[int, "simpy.Event"]] = field(default_factory=list)

    @property
    def uid(self) -> str:
        return f"S{self.site_id}R{self.res_id}"


@dataclass
class Process:
    pid: int
    home_site: int
    # idle | running | blocked
    status: str = "idle"
    # Resources currently held: list of Resource objects
    holding: List[Resource] = field(default_factory=list)
    # Resource this process is currently blocked on
    waiting_for: Optional[Resource] = None


# ---------------------------------------------------------------------------
# Simulation result collector
# ---------------------------------------------------------------------------

class SimResult:
    def __init__(self) -> None:
        self.events: List[dict] = []
        self.deadlocks: List[dict] = []
        # Snapshots of WFG edges at the end of simulation: site_id -> list of (u, v)
        self.final_wfg_edges: Dict[int, List[Tuple[int, int]]] = {}

    def log(self, time: float, kind: str, message: str) -> None:
        self.events.append({"time": round(time, 3), "type": kind, "message": message})

    def record_deadlock(self, time: float, cycle: List[int], sites: List[int]) -> None:
        self.deadlocks.append(
            {
                "time": round(time, 3),
                "cycle": cycle,
                "cycle_str": " → ".join(f"P{p}" for p in cycle),
                "sites": sorted(set(sites)),
                "sites_str": ", ".join(f"S{s}" for s in sorted(set(sites))),
            }
        )


# ---------------------------------------------------------------------------
# Distributed Deadlock Simulator
# ---------------------------------------------------------------------------

class DistributedDeadlockSim:
    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.env = simpy.Environment()
        self.result = SimResult()

        # --- build resources ---
        self.resources: Dict[Tuple[int, int], Resource] = {}
        for s in range(cfg.num_sites):
            for r in range(cfg.resources_per_site):
                res = Resource(site_id=s, res_id=r)
                self.resources[(s, r)] = res

        # --- build processes (distributed evenly across sites) ---
        self.processes: Dict[int, Process] = {}
        for pid in range(cfg.num_processes):
            site = pid % cfg.num_sites
            self.processes[pid] = Process(pid=pid, home_site=site)

        # --- per-site local WFG ---
        self.wfg: Dict[int, nx.DiGraph] = {
            s: nx.DiGraph() for s in range(cfg.num_sites)
        }
        # Add all process nodes to every site's WFG for visibility
        for s in range(cfg.num_sites):
            for pid in range(cfg.num_processes):
                self.wfg[s].add_node(pid)

        # --- probe suppression: set of (initiator, receiver) pairs seen ---
        # per initiator, track the set of receivers to which we've forwarded
        self.probes_sent: Dict[int, Set[int]] = {
            pid: set() for pid in range(cfg.num_processes)
        }

        # Track which cycles have been reported (by frozenset) to avoid duplicates
        self._reported_cycles: Set[frozenset] = set()

    # -----------------------------------------------------------------------
    # WFG helpers
    # -----------------------------------------------------------------------

    def _add_wfg_edge(self, waiting_pid: int, holder_pid: int) -> None:
        """Add Pi → Pj edge to both sites' local WFGs."""
        for s in range(self.cfg.num_sites):
            self.wfg[s].add_edge(waiting_pid, holder_pid)

    def _remove_wfg_edges_to(self, holder_pid: int) -> None:
        """Remove all incoming edges to holder_pid (holder released resources)."""
        for s in range(self.cfg.num_sites):
            preds = list(self.wfg[s].predecessors(holder_pid))
            for pred in preds:
                if self.wfg[s].has_edge(pred, holder_pid):
                    self.wfg[s].remove_edge(pred, holder_pid)

    def _remove_wfg_edge(self, waiting_pid: int, holder_pid: int) -> None:
        for s in range(self.cfg.num_sites):
            if self.wfg[s].has_edge(waiting_pid, holder_pid):
                self.wfg[s].remove_edge(waiting_pid, holder_pid)

    # -----------------------------------------------------------------------
    # Probe / edge-chasing algorithm (Chandy-Misra-Haas style)
    # -----------------------------------------------------------------------

    def _initiate_probe(self, initiator: int, blocked_on_holder: int) -> None:
        """
        Process `initiator` just became blocked on `blocked_on_holder`.
        Send probe(initiator, initiator, blocked_on_holder).
        """
        self.env.process(
            self._send_probe(
                initiator=initiator,
                sender=initiator,
                receiver=blocked_on_holder,
            )
        )

    def _send_probe(self, initiator: int, sender: int, receiver: int):
        """Deliver probe(initiator, sender, receiver) after network latency."""
        latency = self.rng.uniform(self.cfg.latency_min, self.cfg.latency_max)
        yield self.env.timeout(latency)
        self._receive_probe(initiator=initiator, sender=sender, receiver=receiver)

    def _receive_probe(self, initiator: int, sender: int, receiver: int) -> None:
        """
        Process `receiver` gets probe(initiator, sender, receiver).

        Rules (CMH for WFG):
        1. If receiver == initiator → deadlock detected.
        2. If receiver is still blocked and hasn't forwarded for this initiator:
           forward probe(initiator, receiver, next_holder) for each out-edge.
        """
        proc = self.processes[receiver]

        # Rule 1: cycle back to initiator
        if receiver == initiator:
            # Reconstruct cycle from WFG
            try:
                cycle = list(nx.find_cycle(self.wfg[proc.home_site], initiator))
                cycle_nodes = [e[0] for e in cycle] + [cycle[-1][1]]
            except nx.NetworkXNoCycle:
                # fallback: just record what we know
                cycle_nodes = [initiator]

            key = frozenset(cycle_nodes)
            if key not in self._reported_cycles:
                self._reported_cycles.add(key)
                sites = [self.processes[p].home_site for p in cycle_nodes]
                self.result.log(
                    self.env.now,
                    "DEADLOCK",
                    f"Deadlock detected! Cycle: {' → '.join(f'P{p}' for p in cycle_nodes)}",
                )
                self.result.record_deadlock(self.env.now, cycle_nodes, sites)
            return

        # Rule 2: forward if receiver is blocked
        if proc.status != "blocked":
            return  # not blocked, discard

        # Suppress duplicate forwarding for this initiator
        if receiver in self.probes_sent[initiator]:
            return
        self.probes_sent[initiator].add(receiver)

        # Forward along all out-edges in the WFG
        home = proc.home_site
        successors = list(self.wfg[home].successors(receiver))
        for nxt in successors:
            self.env.process(
                self._send_probe(initiator=initiator, sender=receiver, receiver=nxt)
            )

    # -----------------------------------------------------------------------
    # Resource allocation / release
    # -----------------------------------------------------------------------

    def _request_resource(self, proc: Process, res: Resource):
        """
        Generator: tries to acquire `res` for `proc`.
        Blocks if the resource is held; adds WFG edge when blocking.
        """
        if res.holder is None:
            # Allocate immediately
            res.holder = proc.pid
            proc.holding.append(res)
            proc.status = "running"
            self.result.log(
                self.env.now,
                "ACQUIRE",
                f"P{proc.pid} acquired {res.uid}",
            )
            return

        # Resource is busy — block and wait
        event = self.env.event()
        res.waiters.append((proc.pid, event))

        # Update WFG: proc is waiting for resource held by res.holder
        holder_pid = res.holder
        proc.waiting_for = res
        proc.status = "blocked"
        self._add_wfg_edge(proc.pid, holder_pid)

        self.result.log(
            self.env.now,
            "BLOCK",
            f"P{proc.pid} blocked on {res.uid} held by P{holder_pid}",
        )

        # Initiate probe for deadlock detection
        self._initiate_probe(initiator=proc.pid, blocked_on_holder=holder_pid)

        # Wait for the resource to be released to us
        yield event

        # Woke up — we now hold the resource
        proc.holding.append(res)
        proc.waiting_for = None
        proc.status = "running"
        self.result.log(
            self.env.now,
            "ACQUIRE",
            f"P{proc.pid} acquired {res.uid} (was waiting)",
        )

    def _release_resource(self, proc: Process, res: Resource) -> None:
        """Release `res` held by `proc` and wake up the next waiter."""
        if res not in proc.holding:
            return
        proc.holding.remove(res)

        # Remove all WFG edges pointing to this proc via this resource
        # (only those waiting for this resource)
        if res.waiters:
            next_pid, next_event = res.waiters.pop(0)
            # Remove old WFG edge: next_pid → proc.pid (waiting for proc)
            self._remove_wfg_edge(next_pid, proc.pid)

            # Allocate to next waiter
            res.holder = next_pid
            next_proc = self.processes[next_pid]

            # If the next process is now blocked on someone else too, keep those edges
            # (they will be cleaned up when they wake up)
            next_event.succeed()

            self.result.log(
                self.env.now,
                "RELEASE",
                f"P{proc.pid} released {res.uid} → handed to P{next_pid}",
            )

            # Update WFG edges for remaining waiters
            for waiter_pid, _ in res.waiters:
                # Remove old edge waiter → proc, add new edge waiter → next_pid
                self._remove_wfg_edge(waiter_pid, proc.pid)
                self._add_wfg_edge(waiter_pid, next_pid)
        else:
            res.holder = None
            # No waiters – remove all WFG edges to proc (since none are waiting now)
            # Actually just log the release
            self.result.log(
                self.env.now,
                "RELEASE",
                f"P{proc.pid} released {res.uid} (no waiters)",
            )

        # Reset probe suppression for proc (it's now active again)
        self.probes_sent[proc.pid] = set()

    # -----------------------------------------------------------------------
    # Process behaviour
    # -----------------------------------------------------------------------

    def _process_loop(self, proc: Process):
        """
        Infinite loop for a process.

        To create the conditions for distributed deadlock each iteration:
        1. Pick TWO distinct random resources.
        2. Acquire the first resource.
        3. While holding it, try to acquire the second resource.
           This two-phase acquisition creates circular wait chains between
           processes, enabling deadlock to form.
        4. Hold both for a random time, then release both.
        5. Wait for a random interval before the next round.
        """
        all_keys = list(self.resources.keys())

        while True:
            # Random inter-request interval
            interval = self.rng.uniform(
                self.cfg.request_interval_min, self.cfg.request_interval_max
            )
            yield self.env.timeout(interval)

            if self.rng.random() > self.cfg.request_prob:
                continue  # Skip this round

            # Pick two distinct resources
            if len(all_keys) < 2:
                keys = all_keys * 2
            else:
                keys = self.rng.sample(all_keys, 2)

            res1 = self.resources[keys[0]]
            res2 = self.resources[keys[1]]

            # Acquire first resource
            yield from self._request_resource(proc, res1)

            # While holding res1, acquire res2 (creates potential circular wait)
            yield from self._request_resource(proc, res2)

            # Hold both for a random time
            hold = self.rng.uniform(self.cfg.hold_time_min, self.cfg.hold_time_max)
            yield self.env.timeout(hold)

            # Release both
            if res2 in proc.holding:
                self._release_resource(proc, res2)
            if res1 in proc.holding:
                self._release_resource(proc, res1)

    # -----------------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------------

    def run(self) -> SimResult:
        """Start all process loops and run the simulation."""
        for proc in self.processes.values():
            self.env.process(self._process_loop(proc))

        self.env.run(until=self.cfg.run_duration)

        # Capture final WFG state
        for s in range(self.cfg.num_sites):
            self.result.final_wfg_edges[s] = list(self.wfg[s].edges())

        self.result.log(
            self.env.now,
            "SIM_END",
            (
                f"Simulation ended at t={self.env.now:.2f}. "
                f"Deadlocks detected: {len(self.result.deadlocks)}"
            ),
        )
        return self.result


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def run_simulation(cfg: SimConfig) -> SimResult:
    sim = DistributedDeadlockSim(cfg)
    return sim.run()
