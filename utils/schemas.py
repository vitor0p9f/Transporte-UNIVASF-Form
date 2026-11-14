"""Column layouts of the CSVs that scripts write and other scripts read.

The column order is a contract: a generator writes the file, `utils/scenarios.py`
and `utils/instances.py` read it, and the runners print the same names in their
reports. Keeping the layouts here means the two writers of `scenarios.csv`
(`scripts/generate_scenarios.py` and `scripts/convert_archeti.py`) cannot drift
apart.
"""

#: scenarios.csv / scenarios_base.csv / scenarios_control.csv / *_base_control.csv.
SCENARIO_FIELDS = (
    "scenario_id",
    "instance_id",
    "fleet_bus_ids",
    "period",
    "max_time_limit",
    "diesel_price_per_liter",
    "driver_hourly_rate",
    "origin",
    "destination_labels",
)

#: instances/index.csv -- one row per instance on disk.
INSTANCE_INDEX_FIELDS = (
    "instance_id",
    "path",
    "seed",
    "kind",
    "num_nodes",
    "num_od_pairs",
    "total_demand",
)
