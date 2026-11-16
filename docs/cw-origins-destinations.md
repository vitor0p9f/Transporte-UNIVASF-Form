# Clarke-Wright endpoints and baseline adaptations

The scenario columns `origin` and `destination_labels` contain allowed endpoint
labels separated by semicolons. Every route selects one origin and destination;
different routes may select different pairs. Equal labels allow a circuit.

The endpoint-only implementation previously discarded all but the first origin
and ignored destination filters. Both lists are now retained. The full adapted
baseline constructs customer orders by distance savings, anchors them to allowed
endpoints using exact service first and operating cost second, cuts to the fleet
size, and then applies CW-3 without discarding or rebuilding its anchored routes.
The complete traveled sequence is shared by time/distance checks, boarding and
reports, including both access and terminal legs.

An explicit `depot` argument (CLI `--deposito`) overrides the origin list only. The
destination filter still applies. The controlled runner deliberately fixes the
same origin for both heuristics; the standard runner keeps all allowed origins.
Without a destination filter, CW can end at its last visited customer. Pure
drop-off nodes remain active, even with no terminal filter.

Static merge capacity is incident OD demand touching the customer stops, counting
each pair once. Anchors are not customers of that static projection but are fully
included in travel and exact boarding. This is an explicit OD adaptation of the
CVRP load, not a claim of reproducing the original published solver. CW is still
not a fully heterogeneous pickup-and-delivery optimizer.

The inner two-phase loop uses a documented optimistic bound. Its initial
construction and record candidates receive exact final service-based selection.
Local-search candidates cannot mutate the incumbent on rejection. The standard
comparison still differs from TOP in how vehicle capacity/autonomy enter
construction; the homogeneous controlled comparison removes that fleet asymmetry.

See [heuristics.md](../heuristics.md) for the algorithm and approximation details,
[heuristics_pseudocode.md](../heuristics_pseudocode.md) for Portuguese pseudocode,
and [cw-validation.md](cw-validation.md) for the measured acceptance results.

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/validate_cw.py --metrics .venv/cw-acceptance.json
```

The validation script regenerates all four reports twice and compares their
complete bytes. Dates and durations are omitted from deterministic report output;
wall-clock timings are recorded separately. No Word article artifacts are part of
this branch update.
