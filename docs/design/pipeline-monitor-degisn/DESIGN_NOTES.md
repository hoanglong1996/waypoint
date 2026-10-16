# Pipeline Monitor — design notes

Files: `index.html` (static shell), `styles.css` (tokens + all components), `app.js` (mock data + rendering, prototype only), `screenshots/`.
Open `index.html` directly in a browser. No build step, no external JS. The only external request is one optional Google Fonts family (Geist); without it the system font stack is used.

Prototype URL params: `?state=healthy|incomplete|loss|stale|partial|loading|empty|error&tab=latest|history&env=prod|qa&theme=light|dark&run=<i>&step=<name>`. The dashed "Preview state" box (bottom right) does the same. Remove it in production.

## 1. Page frame
- One centred column, `max-width: 1200px`, side gutter 24px (16px under 720px). `body { overflow-x: hidden }` plus `minmax(0, …)` on every grid track, so there is no horizontal scroll at 375px.
- **Sticky header**, 56px, translucent background + blur. Desktop grid: `brand | tabs | spacer | env | live+theme`. Under 720px it becomes three rows: `brand … live+theme` / `env` / full-width tabs (each tab is 50%).
- Tabs use `role="tablist"`, roving `tabindex`, ←/→ keys. The environment switch is two real radio inputs styled as a segmented control, so the keyboard works for free.
- Banners (stale, partial read) sit in `#banners` above the active view, so they apply to both tabs.

## 2. Latest view (the hero)
1. **Hero card**: a 2-column grid, `[status + title + meta] | [3 KPIs]`.
   - Status pills always use icon + text + colour: `Complete` (ok, check-circle), `Incomplete` (bad, x-circle), `Possible data loss` (bad, octagon), `Stale · 32h old` (warn, clock).
   - The title is one plain sentence that answers "did it work?" (“Last night’s run completed”, “Run stopped before the end”, “Run finished, but one step lost data”).
   - A one-line explanation names the first missing step or the loss step in `code` style.
   - KPIs: Accounts = output of step 1, Calls = output of step 2, Saved stats = input of step 9. Each has a delta chip versus the previous run. If the step is missing it shows `—` + “not saved”.
   - **Flow strip**: 9 equal cells under group labels (CallRail 2 · Google Ads 4 · Merge 1 · Persist 2). Ok = green cell with check, loss = red cell with `!`, missing = dashed, hatched cell with its number. This gives the "where did it break" answer in about one second.
2. **Steps timeline**: `<ol>` of steps with a 36px left rail (2px line + numbered node), grouped by source with small uppercase dividers.
   - Step card grid (desktop): `name+time | input chips | output | sparkline`, columns `minmax(180px,1.25fr) minmax(150px,1.5fr) minmax(120px,.8fr) 128px`.
   - Under 1040px it becomes `name output / inputs spark`. Under 720px it becomes `name / inputs / output spark` (stacked cards).
   - Input chips: `→ name **count**`, with a tooltip saying which step the input came from. An empty input list shows a dashed `input none` chip.
   - Output: 28px tabular numerals, an `output` label + delta vs previous run, and a 3px **magnitude bar** (log scale against the biggest count in the run). The bars make the funnel visible: 10 → 1,284 → 6 → 14 → 92 → 3,410 → 1,284.
   - `null` output: muted `n/a` + “returns nothing”. Its sparkline shows the input instead and is labelled `input · 14 runs`.
   - **Loss rule**: `output === 0 && some input > 0` gives a red-tinted card, a red `!` node, a red count and a `Possible data loss` pill next to the time.
   - **Missing step**: dashed border, hatched background, dashed node, `expects <input>` chips and “Step did not report for this run”.
   - Sparkline: 128×36 inline SVG, last 14 runs. Gaps (missing) break the line, zero values get a red dot, and the latest point is an accent dot.

## 3. History view
- **Trend card** (top): step `<select>`, the latest value with a delta chip on the right, and a 240px (200px on mobile) SVG area chart of the last 30 runs.
  - The chart is redrawn at the container's pixel width (on resize too), with a 4-line grid, compact y labels (1.5k), and about 7 date labels.
  - Hover: a dashed crosshair + focus dot + floating tooltip (date, value, delta vs the run before). The chart is focusable: ←/→/Home/End move between runs, and focus shows the latest run.
  - Missing runs break the line and are drawn as a dashed circle on the baseline. A 0 caused by data loss is a filled red point.
- **Runs list**: a header row + `<button class="run-row">` per run (columns: run · status · accounts · calls · saved · flags · chevron). Under 860px each row becomes a 3-column mini card with small labels.
- **Drawer**: a right-side `role="dialog"`, `aria-modal`, `min(680px,100%)` wide, scrim behind it, slide-in 320ms. Esc / scrim / ✕ close it, focus is trapped while open and goes back to the row after closing. It reuses the same step renderer in `steps--compact` mode (no sparkline/bar).

## 4. States
| State | Where | Treatment |
|---|---|---|
| Loading | both views | Skeleton hero + 9 skeleton step rows (shimmer), live dot grey “Loading…”, `aria-busy` |
| Empty | both views | Centred card, inbox icon, “No runs yet for qa”, `role="status"` |
| Data store unreachable | replaces both views | Red-bordered card with `role="alert"`, error code, Retry button + auto-retry hint, live dot grey “Last updated 4m ago”. No numbers shown |
| Stale (> 26 h) | banner + hero pill | Amber banner `role="alert"` with the last finish time; amber `Stale` pill in the hero |
| Some records unreadable | banner + History flag | Neutral info banner with the count; `N unreadable` pill on the run row |
| Incomplete | hero + steps | Red `Incomplete` pill, first missing step named, hatched missing cards, KPI `—` |
| Data-loss step | hero + step | Extra red pill in the hero, red flow cell, red-tinted step card |

## 5. Tokens (all in `:root` in `styles.css`)
- Colours: `--bg --surface --surface-2 --surface-3 --border --border-strong --text --text-2 --text-3 --accent --accent-soft --focus`, status `--ok/--warn/--bad/--neutral` each with `-bg` and `-border`, chart `--chart-*`, `--spark`, `--bar`.
- Dark theme: the same names are redefined under `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` **and** `:root[data-theme="dark"]` (keep both blocks the same). The toggle sets `data-theme` and saves it in localStorage.
- Contrast (checked against `--surface`): text 18:1, text-2 8:1, text-3 ≥ 5.5:1, status text on its tinted background ≥ 5.6:1 in light mode.
- Spacing `--s-1…--s-12` (4px base) · radius `xs 4 / sm 6 / md 10 / lg 14 / pill` · shadows `--shadow-1/2/3` (dark mode uses borders, not shadows).
- Type: Geist (or the system stack), mono for step names and env. Scale `11/12/13/14/16/20/24` + numerals `22/28/40`. Every count uses `.num` (tabular numerals, -0.02em tracking).

## 6. Motion and accessibility
- Motion: only the live-dot pulse (2.4s), skeleton shimmer, drawer slide, and chart crosshair easing. All are turned off under `prefers-reduced-motion`.
- Visible `:focus-visible` ring (2px `--focus`), skip link, 44px touch targets for tabs and the segmented control.
- Status is never shown by colour only: there is always an icon + word, plus a hatch/dash pattern for missing data.

## 7. Mapping to the build tasks
- Static shell + tokens → copy `index.html` / `styles.css` as they are.
- Rendering → replace `buildRuns()` in `app.js` with the real fetch. The view code needs the step shape `{name, inputs:[{name,value}], output|null, finishedAt}` or `{name, missing:true}`, which is what the API returns.
- Derived rules live in `analyse()` / `isLoss()` / `headline()` / `metric()`. Keep them as plain functions so they are easy to unit-test.
