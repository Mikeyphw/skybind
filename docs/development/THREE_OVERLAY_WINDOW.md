# Rolling three-overlay lookahead

Before an implementation, inspect the active overlay and its two immediate planned successors. Merge two or three only if source ownership, dependency order, validation and negative gates are coherent; preserve separate IDs/obligations in combined evidence. Never merge away milestone-gate independence. Recompute the lookahead after each completed package.

Initial review: SB-O01, SB-O02, SB-O03. **SB-O01+SB-O02 merge** is beneficial: the frozen contracts, Devtool target jobs and frontend fixture verifier must be introduced together to prevent temporarily unenforced baselines. **SB-O03 remains independent**: privileged filesystem ownership, atomicity and Go cross-compilation form their own security validation boundary. Neither package covers SB-O04.
