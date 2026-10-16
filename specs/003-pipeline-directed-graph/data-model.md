# Data Model: Pipeline Directed Graph View

Derived entirely from existing API payloads; nothing new is stored.

## Pipeline Structure
- From `/api/config` `expected_steps`: `name`, `group`, `inputs: [{name, from}]`, `returns_nothing`. Acyclic by construction.
- Front-end table keyed by step name: friendly `label`, `col`, `row` (see research §3), tab-order index. Steps absent from the table go to "Other steps".

## Step Node (per run)
| Field | Source | Notes |
|---|---|---|
| `name`, `group`, `label` | structure | |
| `col`, `row` | table | fixed; position then comes from the layout kind |
| `output` | run step | number or null (n/a, returns nothing) |
| `state` | computed, in this order | `stopped` (first missing), `unreached` (later missing), `loss` (`output === 0` and some input > 0), `ok` |
| `affected` | computed | true when `state === ok` and the node is transitively downstream of a `loss` node |
| `finished_at` | run step | absent when missing |

## Data Link (edge)
| Field | Source | Notes |
|---|---|---|
| `from`, `to`, `input` | structure | one per consumer input (9 total) |
| `k`, `n` | structure | input index and count, for the entry port on the consumer |
| `count` | consumer's recorded input value | null when missing |
| `state` | computed | `inactive` (producer or consumer missing; chip "—"), `empty` (count 0; chip "0"), `ok`; `ghost` in loading/empty modes |
| `width` | computed | `ok` only: `1.25 + 2.75 × log10(count+1) / log10(max+1)` px, max = largest edge count in the run; 1.5 px otherwise |

## Layout (computed from container width)
`kind`: `lr` (≥880), `compact` (600–879), `tb` (<600); `scale`: `lr` `min(1, w/1138)`, `compact` `min(1.35, w/628)`, `tb` 1. Holds node rectangles, group bands, edge paths and chip positions.

## Selection
`selected` step index or none; derived `upstream`, `downstream` direct-neighbour sets drive highlighting (others dimmed) and the Selected-step panel links.

## Rules
- Nodes and edges are identical for every run; only counts and states change.
- `record_*` and `save_*` return nothing: no outgoing edge, shown as sinks with "n/a · returns nothing".
- Unreadable records count as missing.
