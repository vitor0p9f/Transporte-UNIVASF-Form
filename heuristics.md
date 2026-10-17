# UNIVASF TOP heuristic — overview

The code is the source of truth (`algorithms/top_univasf/`); the full
step-by-step pseudocode is in `heuristics_pseudocode.md`.

## 1. Main flow (the round)

```mermaid
flowchart TD
    A["load the instance and the fleet"] --> B{"is there demand left?"}
    B -- "no" --> Z["final plans<br/>(only buses with passengers)"]
    B -- "yes" --> C["ROUND: every bus proposes 1 step"]
    C --> D{"does the bus already have<br/>a locked pair?"}
    D -- "no" --> E["DRAFT<br/>picks the base route [o, d] or [o, P, d]<br/>score = passengers on the route / route time"]
    D -- "yes" --> F["EXPANSION<br/>inserts 1 demand-driven point<br/>score = passengers gained / extra time"]
    E --> G["CONFLICT: group the proposals that<br/>share a point or an origin-destination pair"]
    F --> G
    G --> H{"any group<br/>with more than one?"}
    H -- "no" --> I["all of them commit together"]
    H -- "yes" --> J["only the highest score acts<br/>(tie-break: passenger count,<br/>shorter time, lower bus id)"]
    I --> K["COMMIT: charge the global demand"]
    J --> K
    K --> B
```

## 2. Expansion detail (where the new point enters)

```mermaid
flowchart TD
    P["candidate P off the route,<br/>with demand linked to a node on the route"] --> R1{"does A arrive at P?<br/>(A already on the route)"}
    P --> R2{"does P leave for Y?<br/>(Y already on the route)"}
    R1 -- "A is the final destination" --> T1["extend the route: [..., d, P, d]"]
    R1 -- "general case" --> T2["P right after A"]
    R2 -- "Y is the start o<br/>and o differs from d" --> T3["dobradinha (new): [o, P, o, ...]"]
    R2 -- "general case" --> T4["P right before Y"]
    T1 --> S["simulate the whole route<br/>(capacity leg by leg, time within the limit)"]
    T2 --> S
    T3 --> S
    T4 --> S
    S --> SC["score = passengers gained / extra time<br/>discard when <= 0, or with no new pair"]
    SC --> BE["best proposal of that bus in the round wins"]
```

## Legend

- **draft** — a bus without a locked pair picks the base route; the route is
  born at the pair origin (no deadhead).
- **expansion** — a bus with a locked pair inserts 1 point; the position comes
  from the demand. The **dobradinha** `[o, P, o, ...]` is the case where the
  demand is `P→o` (leaving for the start) and the route does not end at the
  start — the only position that revisits the origin.
- **conflict** — proposals sharing a key (point or origin-destination pair)
  fall into the same group, directly or by transitivity.
- **scores** — draft: `passengers on the route ÷ route time`; expansion:
  `passengers gained ÷ extra time`. The final plan reports
  `total passengers ÷ total time`.
