"""
tools.py - helpers for the combined N-1 / Capacity assignment on Svedala.

These are non-core utilities you have already seen in the tutorial notebooks.
You may import them as-is. The CORE combined logic — N-1 secure capacity sweep
and bisection on top — is what you write in the assignment notebook.
"""
import copy
import os
import json
import numpy as np
import pandas as pd
# pandapower is imported lazily inside load_svedala() so that this file can
# be inspected (and helpers like check_limits used) on machines that lack it.


# ---------------------------------------------------------------------------
# Loader (same as svedala_loader.py - duplicated here to keep the assignment
# self-contained)
# ---------------------------------------------------------------------------
DEFAULT_MAX_I_KA = {400.0: 2.50, 220.0: 1.50, 135.0: 0.95, 20.0: 1.00, 17.0: 1.00}


def load_svedala(data_dir="data"):
    """Build a pandapower net from the five Svedala CSVs."""
    import pandapower as pp
    needed = ["buses.csv", "lines.csv", "transformers.csv",
              "generators.csv", "loads.csv"]
    for f in needed:
        if not os.path.isfile(os.path.join(data_dir, f)):
            raise FileNotFoundError(f"Missing {f!r} in {data_dir!r}.")
    net = pp.create_empty_network(name="Svedala")
    net.bus    = pd.read_csv(os.path.join(data_dir, "buses.csv"),        index_col=0)
    net.line   = pd.read_csv(os.path.join(data_dir, "lines.csv"),        index_col=0)
    net.trafo  = pd.read_csv(os.path.join(data_dir, "transformers.csv"), index_col=0)
    net.gen    = pd.read_csv(os.path.join(data_dir, "generators.csv"),   index_col=0)
    net.load   = pd.read_csv(os.path.join(data_dir, "loads.csv"),        index_col=0)
    for idx in net.line.index:
        if pd.isna(net.line.at[idx, "max_i_ka"]):
            vn = net.bus.at[net.line.at[idx, "from_bus"], "vn_kv"]
            key = min(DEFAULT_MAX_I_KA.keys(), key=lambda k: abs(k - vn))
            net.line.at[idx, "max_i_ka"] = DEFAULT_MAX_I_KA[key]
    return net


# ---------------------------------------------------------------------------
# Limit checking
# ---------------------------------------------------------------------------
def check_limits(net, v_min=0.95, v_max=1.05,
                 line_limit=100.0, trafo_limit=100.0, min_kv=220.0):
    """Return violating element indices, scoped to buses/branches at or above min_kv.
    Lower-voltage buses (generator terminals, distribution) are excluded because
    the simplified Svedala model lacks reactive compensation at those levels."""
    hv_buses  = net.bus[net.bus.vn_kv >= min_kv].index
    hv_lines  = net.line[net.line.from_bus.isin(hv_buses) &
                         net.line.to_bus.isin(hv_buses)].index
    hv_trafos = net.trafo[net.trafo.hv_bus.isin(hv_buses) &
                          net.trafo.lv_bus.isin(hv_buses)].index
    return {
        "voltage_low":    net.res_bus.loc[hv_buses][net.res_bus.loc[hv_buses].vm_pu < v_min].index.tolist(),
        "voltage_high":   net.res_bus.loc[hv_buses][net.res_bus.loc[hv_buses].vm_pu > v_max].index.tolist(),
        "line_overload":  net.res_line.loc[hv_lines][net.res_line.loc[hv_lines].loading_percent > line_limit].index.tolist(),
        "trafo_overload": net.res_trafo.loc[hv_trafos][net.res_trafo.loc[hv_trafos].loading_percent > trafo_limit].index.tolist() if len(hv_trafos) else [],
    }


def is_feasible(net, v_min=0.95, v_max=1.05,
                line_limit=100.0, trafo_limit=100.0, min_kv=220.0):
    """Check operating limits scoped to the HV transmission grid (>= min_kv).
    Lower-voltage buses are excluded — the simplified Svedala model lacks
    reactive compensation at 135 kV and below."""
    hv_buses  = net.bus[net.bus.vn_kv >= min_kv].index
    hv_lines  = net.line[net.line.from_bus.isin(hv_buses) &
                         net.line.to_bus.isin(hv_buses)].index
    hv_trafos = net.trafo[net.trafo.hv_bus.isin(hv_buses) &
                          net.trafo.lv_bus.isin(hv_buses)].index
    if (net.res_line.loc[hv_lines,  'loading_percent'] > line_limit).any(): return False
    if len(hv_trafos) and \
       (net.res_trafo.loc[hv_trafos, 'loading_percent'] > trafo_limit).any(): return False
    if (net.res_bus.loc[hv_buses, 'vm_pu'] < v_min).any(): return False
    if (net.res_bus.loc[hv_buses, 'vm_pu'] > v_max).any(): return False
    return True


# ---------------------------------------------------------------------------
# Corridor & GSK
# ---------------------------------------------------------------------------
def cross_zone_branches(net, zone_a_buses, zone_b_buses):
    a, b = set(zone_a_buses), set(zone_b_buses)
    line_dir, trafo_dir = [], []
    for idx, row in net.line.iterrows():
        if   row.from_bus in a and row.to_bus in b: line_dir.append((idx, +1))
        elif row.from_bus in b and row.to_bus in a: line_dir.append((idx, -1))
    for idx, row in net.trafo.iterrows():
        if   row.hv_bus in a and row.lv_bus in b: trafo_dir.append((idx, +1))
        elif row.hv_bus in b and row.lv_bus in a: trafo_dir.append((idx, -1))
    return line_dir, trafo_dir


def corridor_flow(net, line_dir, trafo_dir):
    p = 0.0
    for idx, d in line_dir:  p += d * net.res_line.at[idx, "p_from_mw"]
    for idx, d in trafo_dir: p += d * net.res_trafo.at[idx, "p_hv_mw"]
    return p


def gsk_pmax(net, zone_buses):
    in_zone = net.gen[net.gen.bus.isin(zone_buses) & net.gen.in_service]
    if in_zone.empty:
        raise ValueError("No in-service generators in this zone.")
    pmax = in_zone.max_p_mw.replace(0, np.nan).fillna(in_zone.p_mw.abs())
    return pmax / pmax.sum()


# ---------------------------------------------------------------------------
# Dispatch shift
# ---------------------------------------------------------------------------
def apply_dispatch_shift(net, delta_mw, gsk_a, gsk_b):
    for g, k in gsk_a.items():
        new_p = net.gen.at[g, "p_mw"] + k * delta_mw
        if not np.isnan(net.gen.at[g, "max_p_mw"]):
            new_p = min(new_p, net.gen.at[g, "max_p_mw"])
        if not np.isnan(net.gen.at[g, "min_p_mw"]):
            new_p = max(new_p, net.gen.at[g, "min_p_mw"])
        net.gen.at[g, "p_mw"] = new_p
    for g, k in gsk_b.items():
        new_p = net.gen.at[g, "p_mw"] - k * delta_mw
        if not np.isnan(net.gen.at[g, "max_p_mw"]):
            new_p = min(new_p, net.gen.at[g, "max_p_mw"])
        if not np.isnan(net.gen.at[g, "min_p_mw"]):
            new_p = max(new_p, net.gen.at[g, "min_p_mw"])
        net.gen.at[g, "p_mw"] = new_p
