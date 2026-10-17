"""Root seed for the synthetic data generation.

Every synthetic datum in the project comes from the SAME root seed,
`DEFAULT_SEED`:

    travel times + demand     -> scripts/generate_instances.py
    fleet (fleet.csv)         -> scripts/generate_fleet.py
    scenarios (scenarios.csv) -> scripts/generate_scenarios.py
    missing matrices          -> utils.synth.ensure_matrices

Running the three generators with the same `--seed` reproduces exactly the same
instances, fleet and scenarios; to swap the whole experiment, change only
`DEFAULT_SEED` here (or pass `--seed` to each generator).

`scripts/run_all.py` records the seed it used in the `results.md` header.
"""

DEFAULT_SEED = 42
