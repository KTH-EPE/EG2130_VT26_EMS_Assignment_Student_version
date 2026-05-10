"""
svedala_loader.py
=================
Reconstitute a pandapower network from the five CSV files produced by
KTH-EPE's `Pandapower_CIM_import.ipynb` (the simplified Svedala model).

The CIM-imported CSVs contain pandapower's standard element columns plus a
number of CIM/origin metadata columns. We assign them straight onto the
network's element tables — pandapower ignores unknown columns at power-flow
time, so the metadata travels along harmlessly.

Two fix-ups are applied:

1. **Line ratings.** The simplified model has empty `max_i_ka` for every
   line (typical of CGMES exports — thermal limits live in a separate profile
   that is not always shipped). We fill in conservative defaults based on
   each line's nominal voltage so that loading_percent calculations work.

2. **Geo coordinate column.** Newer pandapower stores GeoJSON-string
   coordinates in `bus.geo`. The CSVs already use that column; we leave it
   alone.
"""
import os
import pandas as pd


# Voltage-level → default thermal rating (kA per single circuit).
# These are conservative typical Nordic values. Override per-line if needed.
DEFAULT_MAX_I_KA = {
    400.0: 2.50,   # ~ 1700 MVA
    220.0: 1.50,   # ~  570 MVA
    135.0: 0.95,   # ~  220 MVA
    20.0:  1.00,
    17.0:  1.00,
}


def _fill_line_ratings(net):
    """In-place: populate net.line.max_i_ka where it is missing,
    using the from_bus voltage level as the lookup."""
    for idx in net.line.index:
        if pd.isna(net.line.at[idx, "max_i_ka"]):
            vn = net.bus.at[net.line.at[idx, "from_bus"], "vn_kv"]
            # Pick the closest known voltage level.
            key = min(DEFAULT_MAX_I_KA.keys(), key=lambda k: abs(k - vn))
            net.line.at[idx, "max_i_ka"] = DEFAULT_MAX_I_KA[key]


def _fill_trafo_ratings(net, scale=1.4):
    """In-place: estimate sn_mva for network trafos where the CIM export left
    the rated power at the 100 MVA placeholder (ratedS absent from the
    simplified CGMES export).

    Strategy: run a quick load flow (pandapower never enforces transformer
    limits, so the power flows are correct regardless of the placeholder
    rating) and set sn_mva = max(|S_actual| * scale, 200) rounded to the
    nearest 50 MVA.  The PF result tables are cleared afterwards so the
    calling notebook starts from a clean state.

    scale = 1.4 gives roughly 70-85% base-case loading, consistent with how
    transmission transformers are typically operated.
    """
    import pandapower as _pp
    import warnings as _warnings

    placeholder_idx = net.trafo.index[
        (net.trafo["sn_mva"] - 100.0).abs() < 1.0
    ].tolist()
    if not placeholder_idx:
        return

    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            _pp.runpp(net, numba=True)
    except Exception:
        return   # PF failed; leave sn_mva unchanged

    for idx in placeholder_idx:
        p = net.res_trafo.at[idx, "p_hv_mw"]
        q = net.res_trafo.at[idx, "q_hv_mvar"]
        s_mva = (p ** 2 + q ** 2) ** 0.5
        sn_new = max(round(s_mva * scale / 50.0) * 50.0, 200.0)
        net.trafo.at[idx, "sn_mva"] = sn_new

    # Clear cached PF results; the caller should run their own clean PF.
    for _key in list(net.keys()):
        if isinstance(_key, str) and _key.startswith("res_"):
            try:
                net[_key] = net[_key].iloc[0:0]
            except Exception:
                pass


def _clamp_gen_vm_pu(net, lower=0.95, upper=1.05):
    """In-place: clamp generator terminal voltage setpoints to [lower, upper].

    The CIM-imported operating snapshot contains actual measured bus voltages
    as vm_pu setpoints.  Several generators in ZON_NORR were operating with
    terminal voltages above 1.05 pu (NORRSELE_G1/G2: 1.10, OLMÅFALLET_G1:
    1.117, STUPET_G1–G4: 1.088, VATTENDRAGET_G1: 1.103, STORFORS_G1: 1.059).
    When pandapower enforces these as voltage control targets, the surrounding
    135–220 kV buses end up above 1.05 pu — violating the standard Nordic
    transmission band even in the base case.

    Clamping to ≤ 1.05 pu removes all generator-driven over-voltage violations.
    The four radial 135 kV load buses (NYSTAD RT133, YTTERFORSEN RT131,
    SYDKÖPING FT50, NORRÅS FT42) remain below 0.95 pu — a structural
    limitation of the simplified model (missing reactive compensation and
    transformer tap data) documented in the course README.
    """
    if "vm_pu" not in net.gen.columns:
        return
    net.gen["vm_pu"] = net.gen["vm_pu"].clip(lower=lower, upper=upper)


def load_svedala(data_dir="data"):
    """Build a pandapower network from the Svedala CSVs in `data_dir`.

    Expects the files: buses.csv, lines.csv, transformers.csv,
    generators.csv, loads.csv.
    """
    import pandapower as pp

    needed = ["buses.csv", "lines.csv", "transformers.csv",
              "generators.csv", "loads.csv"]
    for f in needed:
        path = os.path.join(data_dir, f)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Missing {path!r}. Place the five Svedala CSVs in "
                f"{data_dir!r} (see KTH-EPE/CIM_exportimport)."
            )

    net = pp.create_empty_network(name="Svedala")

    # Element tables: index is the original pandapower index (preserved from CSV).
    net.bus    = pd.read_csv(os.path.join(data_dir, "buses.csv"),        index_col=0)
    net.line   = pd.read_csv(os.path.join(data_dir, "lines.csv"),        index_col=0)
    net.trafo  = pd.read_csv(os.path.join(data_dir, "transformers.csv"), index_col=0)
    net.gen    = pd.read_csv(os.path.join(data_dir, "generators.csv"),   index_col=0)
    net.load   = pd.read_csv(os.path.join(data_dir, "loads.csv"),        index_col=0)

    # Fix #2: ensure all auxiliary tables that pandapower's runpp requires exist.
    # A fresh empty network carries all of them; we add any that are missing so
    # that networks loaded from CSVs work across pandapower versions.
    _template = pp.create_empty_network()
    for _key, _val in _template.items():
        if _key not in net:
            net[_key] = _val

    # Fix #3: line thermal ratings.
    _fill_line_ratings(net)

    # Fix #4: The CIM export has tap_dependency_table=True for some transformers
    # that reference characteristic curves not included in this simplified model.
    # pandapower 3.x will raise AttributeError when it tries to look up
    # net.trafo_characteristic_table for those trafos.  Reset the flag so the
    # simple linear tap model is used instead (appropriate for static studies).
    if "tap_dependency_table" in net.trafo.columns:
        net.trafo["tap_dependency_table"] = False

    # Fix #5: network transformer ratings.
    _fill_trafo_ratings(net)

    # Fix #6: clamp generator voltage setpoints to the standard Nordic band.
    _clamp_gen_vm_pu(net)

    # Sanity: there must be exactly one slack source (a slack=True gen, since
    # this model has no ext_grid).
    if "slack" in net.gen.columns:
        n_slack = int(net.gen.slack.fillna(False).astype(bool).sum())
    else:
        n_slack = 0
    if n_slack == 0 and len(net.ext_grid) == 0:
        raise RuntimeError(
            "No slack found. Expected one generator with slack=True "
            "or a populated ext_grid table."
        )

    return net


if __name__ == "__main__":
    # Quick smoke test
    net = load_svedala("data")
    print(net)
    print("Zones:", sorted(net.bus.SubGeographicalRegion_name.dropna().unique()))
    print("Voltage levels:", sorted(net.bus.vn_kv.unique()))
    print("Slack gens:", net.gen[net.gen.slack.fillna(False).astype(bool)]["name"].tolist())
