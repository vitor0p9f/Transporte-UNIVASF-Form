"""UNIVASF TOP heuristic: sequential greedy with a locked OD pair.

Stage 1 (the pair draft): every bus still without a pair scans the possible
(origin, destination) selections and, for each pair, looks in the demand graph
for the points P with demand coming from `o` OR going to `d`, scoring the route
[o, P, d] (plus the direct option [o, d]):
    servable = boardings along that route under the capacity lock
               (o->P alights, so P->d boards, plus o->d along the way)
    score = servable / route cost
The P with the highest score wins. The pair does NOT need direct demand
`o->d`. The globally best score locks the base route [o, P, d] first (the bus
is born at the pair origin, or at the fixed depot when one is given) and
charges the demand for whatever that route boarded. The others repeat over the
updated demand.

Stage 2 (global rounds): each round, every bus with a locked pair (o, d)
proposes one demand-driven step -- the new point enters where the pair tells
it to: `A->B` puts `B` after `A` (if `A` is the final destination, the crossing
[..., d, B, d]); `B->Y` puts `B` before `Y` (the start is fixed); in a point or
pair conflict the highest marginal score always commits and claims the demand;
the others replan in the next round, until time/capacity runs out or the score
drops to zero.

`destinations`/`draft_origins` (when given) filter the possible
destination/origin selections of the pair.

Every score is passengers per real (R$). Each bus pays fuel with its own km per
liter plus the driver, priced by the scenario; maximising pax/R$ is equivalent
to minimising R$ per passenger, and the marginal insertion minimises R$ per
extra passenger.

Modules:

    model       data (plans, proposals, work state)
    cost        CostModel and route distance (fuel + driver)
    scoring     the scores (pair, marginal, final plan)
    simulation  capacity-locked boarding and candidate nodes
    draft       stage 1: best OD pair and its base route
    expansion   stage 2: inserting one demand-driven point
    conflict    grouping the proposals that dispute a point or pair
    fleet       the round: proposals, conflict, commit, final plans
    solver      solve_scenario: load the scenario and run the fleet
"""

from algorithms.top_univasf.cost import CostModel, RouteCost, route_distance_km
from algorithms.top_univasf.draft import best_pair_for_bus
from algorithms.top_univasf.expansion import best_demand_driven_insertion
from algorithms.top_univasf.fleet import collect_proposals, run_fleet
from algorithms.top_univasf.model import (
    BoardingOutcome,
    BusPlan,
    ConflictKey,
    DraftProposal,
    ExpansionProposal,
    FleetSummary,
    Proposal,
    ServedPair,
    StopSequence,
    WorkState,
    fleet_summary,
    with_depot,
)
from algorithms.top_univasf.scoring import (
    marginal_passengers_per_real,
    od_pair_score_real,
    passengers_per_real,
)
from algorithms.top_univasf.simulation import (
    candidate_nodes,
    segment_passengers,
    simulate_stops,
)
from algorithms.top_univasf.solver import solve_scenario
from utils.instances import InstanceData

__all__ = [
    "BoardingOutcome",
    "BusPlan",
    "ConflictKey",
    "CostModel",
    "DraftProposal",
    "ExpansionProposal",
    "FleetSummary",
    "InstanceData",
    "Proposal",
    "RouteCost",
    "ServedPair",
    "StopSequence",
    "WorkState",
    "best_demand_driven_insertion",
    "best_pair_for_bus",
    "candidate_nodes",
    "collect_proposals",
    "fleet_summary",
    "marginal_passengers_per_real",
    "od_pair_score_real",
    "passengers_per_real",
    "route_distance_km",
    "run_fleet",
    "segment_passengers",
    "simulate_stops",
    "solve_scenario",
    "with_depot",
]
