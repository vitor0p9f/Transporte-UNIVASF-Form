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

Procedures inspired by the paper, with the adaptations documented below:
  CW-1 : modified OVRP savings formula with the lambda parameter
  CW-2 : open route construction (no return to the depot)
  CW-3 : post-improvement (2-opt, shift 1-0, swap 1-1)

Route constraints -- the `restrictions` key decides which one(s) apply:

  "capacidade" : the route load stays within the bus capacity
  "tempo"      : the route time stays within the scenario limit
  "ambas"      : both at once (default)
  "nenhuma"    : neither; only the objective function decides

The baseline adapts static CVRP load to OD demand touching any customer stop,
counting a pair only once. Pickup-only and drop-off-only nodes are both active.
Chosen campus anchors are endpoints, not customer-load stops. This is an explicit
adaptation, not a reproduction of the original single-demand-per-customer model.

To measure the real attendance (only the origin->destination pair that fits the
route, in order, counts), the report runs the TOP UNIVASF boarding/alighting
simulation. Construction still uses distance savings and static capacity.
Selection ranks passengers served first and full operating cost second. Only the
two-phase inner loop uses an optimistic OD-order bound in place of exact boarding.
The pipeline is construction -> anchoring -> fleet cut -> CW-3 -> evaluation.

Modules:

    constants    limits, defaults and restriction keys
    model        data structures (context, route, saving, attendance)
    context      trip sense, load per stop and context assembly
    metrics      distance, time and savings (CW-1)
    objective    fuel cost of the solution
    construction route merging and two-phase selection (CW-2)
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
from .context import build_context, build_stop_loads, detect_sense, build_active_nodes, route_load
from .objective import solution_key, service_bound
from .evaluation import (  # noqa: F401
    _instance_from_context,
    _simulated_sequence,
    evaluate_attendance,
    limit_fleet,
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
    "build_context",
    "build_stop_loads",
    "bus_model",
    "clarke_wright_ovrp",
    "compute_savings_ovrp",
    "detect_sense",
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
    "solve_scenario",
    "two_phase_selection",
]
