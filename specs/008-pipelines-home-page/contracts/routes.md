# Contract: Page addresses

> Superseded for pipeline and run pages by `specs/010-history-first-run-detail/contracts/routes.md`: `#/p/<pipeline>` is now History and runs have their own address.

All addresses are in the URL hash, so no server routing is needed.

| Address | Page |
|---|---|
| `#/` (or empty) | Home: one card per pipeline. |
| `#/p/<pipeline>` | Latest-run page of `<pipeline>` (newest run across environments, same as its card). |
| `#/p/<pipeline>/history` | History of `<pipeline>` with the default environment. |
| `#/p/<pipeline>/history?env=<env>` | History limited to `<env>`. |

## Rules

- `<pipeline>` is URL-encoded and must match the pipeline name pattern already enforced by `/api/runs`.
- An unknown pipeline shows "Pipeline not found" with a link to `#/`.
- An empty `env` uses the default (prod when present, else the newest run's environment). An `env` with no runs
  is kept: the filter shows it with a "no runs" hint and the page says "No runs in this environment".
- Changing the filter updates `?env=` and adds a browser history entry; focus stays on the chosen option.
- Moving between routes closes the run drawer and scrolls to the top.
- Header: product name links to `#/`. Pipeline pages show a back link to `#/`, the pipeline name and the
  Latest | History tabs. The old header pipeline dropdown and the remembered-pipeline setting are removed.

## Keyboard and layout

Cards are links (focusable, Enter opens). The filter is a native select (labelled "Environment").
Cards wrap to one column at phone width with no horizontal scroll.
