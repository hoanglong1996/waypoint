# Contract: what the operator sees

- **Home card**: status pill `Failed` (error tone, own icon), reason line `Failed at <step>: <error type>` (message
  shown shortened when stored), time line `failed <N> ago`. Failed cards sort first in "needs attention".
- **Run page**: headline `A step failed`; subline `Stopped at <step>`; status pill `Failed`; later steps `Not reached`.
  A run whose pipeline continued past a failed step keeps its own headline and shows the failed step in the list.
- **Step list item**: state `failed` with its own icon and the word "Failed" (never colour alone). It shows
  start and failure times and an **Error** block: type, message (when stored), and the stack trace in a scrollable,
  height-limited monospace area with a **Copy** button (copies type, message and trace; confirms with "Copied").
- **Graph node**: state `failed`, error colour **and** a distinct icon and label; later nodes are `unreached`; the
  summary shows `failed at <step>`.
- **History**: failed runs carry the `Failed` pill; a control "All runs / Failed only" next to the environment
  filter shows only runs whose status is Failed (client side, no request).
- All error text is escaped; nothing from an error item is ever inserted as HTML.
