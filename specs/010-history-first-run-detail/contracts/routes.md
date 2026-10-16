# Contract: Page addresses (supersedes the table in specs/008-pipelines-home-page/contracts/routes.md)

All addresses are in the URL hash, so no server routing is needed.

| Address | Page |
|---|---|
| `#/` (or empty) | Home: one card per pipeline. Cards link to the pipeline's history. |
| `#/p/<pipeline>` | History of `<pipeline>`, default environment (same as the next row without `?env`). |
| `#/p/<pipeline>/history` | History of `<pipeline>`, default environment. |
| `#/p/<pipeline>/history?env=<env>` | History limited to `<env>`. |
| `#/p/<pipeline>/runs/<env>/<runId>` | Run detail page for one run. |

## Rules

- `<pipeline>`, `<env>` and `<runId>` are URL-encoded. `<runId>` is the run id already used by the API (`YYYYMMDDTHHMMSSZ`).
- The run's environment is in the address because the same run id can exist in two environments.
- There is no latest-run address. The newest run is the first row of history.
- An unknown pipeline shows "Pipeline not found" with a link to `#/`.
- A known pipeline with an unknown, expired or malformed run shows "Run not found" with a link to
  `#/p/<pipeline>/history` (with `?env=<env>` when the environment is valid).
- Selecting a run in history is a normal link to its run address (browser Back returns to the history, with its
  filter, because the filter is in the history address).
- The run page back link goes to `#/p/<pipeline>/history?env=<run env>`.
- Moving between routes scrolls to the top. No panel or overlay is used for run details.
- Header on pipeline pages: product name links to `#/`; context bar shows breadcrumb
  `All pipelines › <pipeline> › <run start time>` (history shows `All pipelines › <pipeline>`). The Latest | History
  tabs are removed.
- Page titles: history `<Pipeline> · History · Waypoint Monitor`; run `<Pipeline> · <date time> · Waypoint Monitor`.

## API

Unchanged. The run page calls `GET /api/runs?env=<env>&pipeline=<pipeline>&limit=100`.
