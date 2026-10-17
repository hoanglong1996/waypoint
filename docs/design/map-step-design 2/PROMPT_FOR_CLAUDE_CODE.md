The Map step design has a v2 update in ./map-step-design/.
Read map-step-design/CHANGES-v2.md first, then the mockups it lists.

Apply only these two changes to the code we already built:
1. Item flow strip in the map step panel: replace the current boxes and arrows with the
   SAME node and edge style as our existing pipeline graph (.gnode / .gedge in styles.css,
   js/views/graph.js). Reuse those classes and helpers; do not create a second look.
   Edge labels show "items N" (items handed to the next inner step). Vertical on mobile.
2. Item detail page, "Inner steps" section: add the same List | Graph segmented control as
   the run page's Steps section (aria-pressed, keep the view in the URL as ?view=list|graph).
   - List: reuse the run page step list (.steps / .step__rail / .step__card); the error block
     sits inside the failed step's card.
   - Graph: the same nodes/edges as change 1, with "rows N" labels. Data lost = red dashed
     "rows 0" edge; not run / waiting = grey dashed edge. Nodes are buttons; selecting one
     shows its detail below the graph; for a failed item the failed step is pre-selected.

Keep all hard rules from HANDOFF.md (no total N, no percentage bars, label + icon for every
status, plain text only). Plain HTML/CSS/vanilla JS, light + dark, desktop + mobile.

Before coding, tell me which existing functions/classes you will reuse and which files you
will change, and wait for my OK. After coding, check both views with keyboard only, and in
light and dark themes.