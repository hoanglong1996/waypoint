# Quickstart: Validate the Graph View

Prereqs: monitor app running per `specs/002-pipeline-monitor-dashboard/quickstart.md` with seeded runs: complete, data loss at `read_campaigns` (output 0), and stopped before `read_gads_clickview`. Reference screenshots: `docs/design/pipeline-monitor-graph-update/screenshots/graph/`.

1. `cd performance_monitoring_app && node --test static/tests` and `python -m unittest discover tests`: all pass.
2. Latest run, Graph view (default on first visit): 9 nodes, 9 arrows with no crossings; merge has 3 incoming, `read_instances` 2 outgoing, merge 2 outgoing. Compare with `g01`.
3. Arrow labels and node counts equal the stored records (SC-002).
4. Loss run: `read_campaigns` shows "Data loss"; its outgoing arrow shows 0; merge and persist steps show "affected". Compare `g02`.
5. Incomplete run: first missing step "Not reported", later ones "Not reached", arrows into them inactive with "—". Compare `g03`.
6. Select a node: neighbours highlighted, rest dimmed, Selected step panel with Upstream/Downstream links; click it again or press Esc: cleared and focus returns to the node. Compare `g04`.
7. Hover and focus a node and an arrow: tooltips match `g09`.
8. Toggle to List, reload: List remains; toggle back. Choice is shared with the History drawer.
9. Resize to 960 px (compact, `g08`) and 375 px (top-to-bottom, `g05`): no horizontal page scroll; selection survives resize.
10. History: open a run; drawer shows the compact graph (`g06`); first Esc clears a selection, second closes the drawer.
11. Loading and no-runs states show the skeleton and ghost graph (`g07`); stopping Redis shows the error card instead.
12. Light and dark themes; reduced motion hides the flowing edge animation.
