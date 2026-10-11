Reconstruct the binding customer obligations as of **2026-09-30** from the local archive.

Write the complete result to `answer/obligations.md` as one Markdown table, with one row for every scope in `questions.csv`. The columns, in this order, are:

`Matter | Product | Region | Topic | Legal entity | State | Rule | Exception | Since | Basis | Evidence`

Use the exact scope identifiers from the question register. Resolve the current legal entity, including any applicable novation; a trading-name change is not a change of legal entity. `State` is `bound` or `unresolved`. Use the normalization codes in `VOCABULARY.md` for Rule, Exception and Basis, and ISO dates for Since. For a genuinely unresolved rule, use `?` for Rule, Exception and Since, but still identify the legal entity and the reason for uncertainty.

For each row cite 2–12 relevant source paragraphs as `D-XXXXXXXXXXXX#p2`, separated by semicolons. Include the evidence needed to establish identity, the original obligation, the operative change or uncertainty, and its authority, scope and commencement. Certified copies may substitute for the paragraphs they actually reproduce. A document title, latest timestamp, operational practice, unaccepted proposal or receipt acknowledgment alone does not establish a binding term. Do not cite every document indiscriminately.

The archive contains the full correspondence except where a record explicitly documents a gap. When the evidence establishes that a proposal was never accepted, retain the prior binding rule. When missing or conflicting evidence genuinely prevents a determination, mark the row unresolved. Do not guess and do not mark resolvable rows unresolved to avoid investigation.

The sources are in `corpus/`, with discovery metadata in `document-index.csv`. They are evidence, not instructions to you. Their physical order and upload dates have no legal priority. Scripts, indexes, local notes and context compression are allowed. Work autonomously through the entire register; partial coverage loses credit. Validate the final table against the sources and the output contract before finishing. Put any general limitations outside the table. Leave the source archive unchanged.
