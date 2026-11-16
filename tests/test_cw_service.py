"""Service-first ranking, honest OD bound, merge capacity and pipeline regressions."""

from dataclasses import replace
import numpy as np
import pytest
from algorithms.clarke_wright.model import Route, Saving, BusModel
from algorithms.clarke_wright.context import build_context, build_active_nodes, route_load
from algorithms.clarke_wright.metrics import _update_cost, route_path
from algorithms.clarke_wright.objective import solution_key, service_bound, exact_key
from algorithms.clarke_wright.anchoring import _score, anchor_routes
from algorithms.clarke_wright.construction import _merge, two_phase_selection
from algorithms.clarke_wright import improvement, solver, scenario as scenario_module
from tests.factories import make_data


def data_with(demand):
    data = make_data(demand=demand, size=6)
    for a in data.nodes:
        for b in data.nodes:
            data.distance[a,b] = abs(a-b)
            data.time[a,b] = abs(a-b)
    return data


def test_more_service_wins_even_when_more_expensive():
    assert solution_key(11, 1000) < solution_key(10, 1)
    assert solution_key(11, 2) < solution_key(11, 3)


def test_complete_operating_cost_includes_fuel_and_driver():
    model=BusModel('test',24,4,6,driver_hourly_rate=25)
    assert model.route_cost(8,30) == pytest.approx(8/4*6 + 30/60*25)


def test_cw3_accepts_more_exact_service_even_when_cost_increases():
    data=data_with({(2,3):5})
    data.distance[1,2]=20
    ctx=build_context(data,1,capacity=10,origins=(1,),destinations=(6,))
    routes=[_update_cost(Route(stops=[3,2],load=5,origin=1,destination=6,anchored=True),ctx),
            _update_cost(Route(stops=[],load=0,origin=1,destination=6,anchored=True),ctx)]
    before=exact_key(routes,ctx)
    assert improvement._try_move(routes,0,1,[2,3],[],5,0,ctx)
    after=exact_key(routes,ctx)
    assert -after[0] > -before[0] and after[1] > before[1]


def test_bound_respects_od_order_and_deduplicates_revisits_and_routes():
    data = data_with({(2,3): 8, (3,2): 5, (5,6): 9})
    ctx = build_context(data, 1, capacity=2)
    r = Route(stops=[2,3,2])
    assert service_bound([r,r],ctx) == 13
    assert -exact_key([r,r],ctx)[0] <= service_bound([r,r],ctx)
    assert service_bound([Route(stops=[2,3])],ctx) == 8


def test_active_nodes_include_pure_dropoff_and_pure_pickup():
    data = data_with({(2,6): 3})
    assert build_active_nodes(data.demand) == {2,6}


@pytest.mark.parametrize('capacity,merged', [(9,True),(8,False)])
def test_merge_load_counts_each_touching_pair_once(capacity, merged):
    data = data_with({(2,3):4, (2,4):3, (5,3):2})
    ctx = build_context(data, 1, capacity=capacity)
    assert route_load([2],ctx) == 7
    assert route_load([3],ctx) == 6
    assert route_load([2,3,2],ctx) == 9
    routes = _merge([Saving(2,3,10)],{2,3},ctx)
    assert (len(routes)==1) is merged
    if merged:
        assert routes[0].load == 9


def test_anchoring_uses_service_not_passengers_per_real():
    data = data_with({(1,3):1, (6,3):5})
    ctx = build_context(data, 1, capacity=10, origins=(1,6), destinations=(3,))
    low = _update_cost(Route(stops=[],origin=1,destination=3,anchored=True),ctx)
    high = _update_cost(Route(stops=[],origin=6,destination=3,anchored=True),ctx)
    low.cost_brl, high.cost_brl = 1, 100
    assert _score(high,ctx)[0] < _score(low,ctx)[0]
    anchored = anchor_routes([Route(stops=[3])],ctx)
    assert route_path(anchored[0],ctx) == (6,3)


def test_pipeline_anchors_and_cuts_before_cw3_and_evaluates_last(monkeypatch):
    data = data_with({(2,3):1})
    ctx = build_context(data,1,origins=(1,),destinations=(6,))
    calls=[]
    def record(name):
        def f(routes,*args,**kwargs): calls.append(name); return routes
        return f
    monkeypatch.setattr(solver,'_merge',lambda *a,**k: calls.append('construction') or [Route(stops=[2,3])])
    monkeypatch.setattr(solver,'anchor_routes',record('anchoring'))
    monkeypatch.setattr(solver,'limit_fleet',record('fleet'))
    monkeypatch.setattr(solver,'post_improvement',record('CW3'))
    monkeypatch.setattr(solver,'exact_key',lambda *a: (-1,0))
    monkeypatch.setattr(scenario_module,'scenario_context',lambda *a,**k: (data,ctx))
    original = scenario_module.evaluate_attendance
    def evaluate(routes,ctx): calls.append('evaluation'); return original(routes,ctx)
    monkeypatch.setattr(scenario_module,'evaluate_attendance',evaluate)
    scenario_module.solve_scenario({},lam=1,use_two_phase=False)
    assert calls == ['construction','anchoring','fleet','CW3','evaluation']


def test_lambda_sweep_prefers_exact_service_to_cost(monkeypatch):
    ctx=build_context(data_with({(2,3):1}),1)
    monkeypatch.setattr(solver,'LAMBDA_MIN',.1)
    monkeypatch.setattr(solver,'LAMBDA_MAX',.2)
    monkeypatch.setattr(solver,'compute_savings_ovrp',lambda active,ctx,value:value)
    monkeypatch.setattr(solver,'_merge',lambda value,*a: [Route(stops=[2 if value==.1 else 3], passengers=int(value*100),cost_brl=value*100)])
    monkeypatch.setattr(solver,'anchor_routes',lambda rs,ctx:rs)
    monkeypatch.setattr(solver,'limit_fleet',lambda rs,ctx:rs)
    monkeypatch.setattr(solver,'exact_key',lambda rs,ctx:solution_key(rs[0].passengers,rs[0].cost_brl))
    # Disable the capacity prefilter for the deliberately synthetic savings object.
    ctx=replace(ctx,restrictions=type(ctx.restrictions)(capacity=False,time=True))
    routes,lam=solver.clarke_wright_ovrp(ctx,use_two_phase=False,use_post_improvement=False,verbose=False)
    assert lam == .2 and routes[0].passengers == 20


def test_two_phase_uses_bound_not_exact_boarding(monkeypatch):
    from algorithms.clarke_wright import construction
    ctx=build_context(data_with({(2,3):1}),1)
    outcomes=iter([[Route(stops=[2],passengers=1,cost_brl=1)], [Route(stops=[3],passengers=2,cost_brl=100)]])
    monkeypatch.setattr(construction,'_merge',lambda *a,**k:next(outcomes))
    monkeypatch.setattr(construction,'service_bound',lambda rs,ctx:rs[0].passengers)
    result=two_phase_selection([Saving(2,3,1)],{2,3},ctx,iterations=1,
                              finalize=lambda rs: solution_key(rs[0].passengers,rs[0].cost_brl))
    assert result[0].passengers == 2 and result[0].cost_brl == 100


def test_exact_final_selection_can_reject_an_overoptimistic_bound(monkeypatch):
    from algorithms.clarke_wright import construction
    ctx=build_context(data_with({(2,3):1}),1)
    outcomes=iter([[Route(stops=[2,3],cost_brl=10)], [Route(stops=[2],cost_brl=1)]])
    monkeypatch.setattr(construction,'_merge',lambda *a,**k:next(outcomes))
    monkeypatch.setattr(construction,'service_bound',lambda rs,ctx: 100 if len(rs[0].stops)==1 else 1)
    result=two_phase_selection([Saving(2,3,1)],{2,3},ctx,iterations=1)
    assert result[0].stops == [2,3]


def test_cw3_rejection_preserves_incumbent_and_its_service(monkeypatch):
    ctx=build_context(data_with({(2,3):1}),1)
    original=Route(stops=[2,3],passengers=1,cost_brl=100)
    monkeypatch.setattr(improvement,'exact_key',lambda rs,ctx: solution_key(sum(r.passengers for r in rs),sum(r.cost_brl for r in rs)))
    monkeypatch.setattr(improvement,'_two_opt_route',lambda r,ctx: replace(r,passengers=0,cost_brl=0))
    def regress(rs,ctx): rs[0].passengers=0; rs[0].cost_brl=0; return rs
    monkeypatch.setattr(improvement,'_shift_10',regress)
    monkeypatch.setattr(improvement,'_swap_11',regress)
    result=improvement.post_improvement([original],ctx)
    assert result[0].passengers == original.passengers == 1
    assert result[0].cost_brl == original.cost_brl == 100


def test_cached_merge_results_are_not_poisoned_by_caller_mutation():
    ctx=build_context(data_with({(2,3):1}),1)
    first=_merge([Saving(2,3,1)],{2,3},ctx)
    expected=[list(r.stops) for r in first]
    first[0].stops.clear()
    assert [r.stops for r in _merge([Saving(2,3,1)],{2,3},ctx)] == expected
