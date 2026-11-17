"""Clarke-Wright OVRP for the UNIVASF university shuttle.

Buses choose among the scenario's permitted origins and destinations. Both
endpoint legs participate in route construction, time checks and evaluation.
With no endpoint lists, the legacy single-depot open-route API is preserved.
Origin equal to destination is allowed when the scenario permits a circuit.

Based on:
  Pichpibul, T. & Kawtummachai, R. (2013). A Heuristic Approach Based on
  Clarke-Wright Algorithm for Open Vehicle Routing Problem. The Scientific
  World Journal, Article ID 874349.
  https://onlinelibrary.wiley.com/doi/10.1155/2013/874349

  Clarke, G. & Wright, J.W. (1964). Scheduling of vehicles from a central
  depot to a number of delivery points. Operations Research, 12(4), 568–581.
  https://www.jstor.org/stable/167703

Procedures implemented (following the paper):
  CW-1 : modified OVRP savings formula with the lambda parameter
  CW-2 : open route construction (no return to the depot)
  CW-3 : post-improvement (2-opt, shift 1-0, swap 1-1)

Route constraints -- the `restrictions` key decides which one(s) apply:

  "capacidade" : the route load stays within the bus capacity
  "tempo"      : the route time stays within the scenario limit
  "ambas"      : both at once (default)
  "nenhuma"    : neither; only the objective function decides

Each stop has a STATIC load (boardings outbound, alightings inbound): nobody
frees a seat along the route. That is how the paper reads it and the projection
the classic CVRP uses (one demand per node) -- which makes it "allocated
demand", NOT "passengers carried": nothing guarantees that the destination of
whoever boards is on the route.

The attendance is what the steps SELECT on: the lambda sweep, the two-phase
selection and the post-improvement keep the solution that carries the most
passengers, with the fuel cost as the tie-break (`objective.solution_key`). A
stop belongs to the set when someone boards OR gets off there, and the endpoint
step (`anchoring`) gives each route the allowed origin/destination that carries
more passengers. The final figures still come from the TOP UNIVASF
boarding/alighting simulation (`evaluate_attendance`), which is the same
simulation the selection uses.

Modules:

    constants    limits, defaults and restriction keys
    model        data structures (context, route, saving, attendance)
    context      trip sense, load per stop and context assembly
    metrics      distance, time and savings (CW-1)
    objective    solution key, attendance estimates and fuel cost
    construction route merging and two-phase selection (CW-2)
    anchoring    the allowed endpoints that carry the most passengers
    improvement  2-opt, shift and swap (CW-3)
    solver       clarke_wright_ovrp and the lambda sweep
    evaluation   attendance simulation and fleet cut
    scenario     scenario reading and conversion to the report model
    report       printing, JSON and fleet listing
    cli          command line

Usage:
    python -m algorithms.clarke_wright --cenario 1
    python -m algorithms.clarke_wright --cenario 2 --restricao tempo --deposito 1
    python -m algorithms.clarke_wright --instancia p1_2_a --periodo morning_1 \
        --deposito 1 --capacidade 32 --limite-tempo 90 --diesel 6.35
    python -m algorithms.clarke_wright --frota
"""

from .anchoring import anchor_routes
from .cli import main
from .constants import (
    DEFAULT_CAPACITY,
    DEFAULT_DIESEL_PRICE,
    DEFAULT_KM_PER_LITER,
    DEFAULT_PERIOD,
    INF,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    LAMBDA_MAX,
    LAMBDA_MIN,
    LAMBDA_PASSO,
    RESTRICTIONS,
)
from .construction import (  # noqa: F401
    _best_direction,
    _merge,
    _roulette_wheel,
    two_phase_selection,
)
from .context import build_context, build_stop_loads, detect_sense
from .evaluation import (  # noqa: F401
    _instance_from_context,
    _simulated_sequence,
    evaluate_attendance,
    limit_fleet,
    served_by,
)
from .improvement import (  # noqa: F401
    _copy_route,
    _shift_10,
    _swap_11,
    _two_opt_route,
    post_improvement,
)
from .metrics import (  # noqa: F401
    _route_distance,
    _route_time,
    _time_limit_text,
    _update_cost,
    _update_route,
    compute_savings_ovrp,
)
from .model import (
    Attendance,
    BusModel,
    Context,
    Pair,
    Pairs,
    Restrictions,
    Route,
    Saving,
    bus_model,
)
from .objective import (
    captured_demand,
    estimated_served,
    served_bound,
    solution_key,
)
from .report import (  # noqa: F401
    _pairs_text,
    _status,
    print_fleet,
    print_solution,
    save_result,
)
from .scenario import (  # noqa: F401
    ROOT,
    _find_scenario,
    _scenario_depot,
    _scenario_fleet,
    plans_and_summary,
    reference_model,
    scenario_context,
    solve_scenario,
)
from .solver import clarke_wright_ovrp

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_DIESEL_PRICE",
    "DEFAULT_KM_PER_LITER",
    "DEFAULT_PERIOD",
    "INF",
    "ITER_POSTIMPROVE",
    "ITER_TWO_PHASE",
    "LAMBDA_MAX",
    "LAMBDA_MIN",
    "LAMBDA_PASSO",
    "RESTRICTIONS",
    "ROOT",
    "Attendance",
    "BusModel",
    "Context",
    "Pair",
    "Pairs",
    "Restrictions",
    "Route",
    "Saving",
    "anchor_routes",
    "build_context",
    "build_stop_loads",
    "bus_model",
    "captured_demand",
    "clarke_wright_ovrp",
    "compute_savings_ovrp",
    "detect_sense",
    "estimated_served",
    "evaluate_attendance",
    "limit_fleet",
    "main",
    "plans_and_summary",
    "post_improvement",
    "print_fleet",
    "print_solution",
    "reference_model",
    "save_result",
    "scenario_context",
    "served_bound",
    "served_by",
    "solution_key",
    "solve_scenario",
    "two_phase_selection",
]
