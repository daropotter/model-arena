Finish and locally release the returns/refunds feature in this existing
Orders system. Own the whole delivery in one autonomous session, through
migration, domain rules, HTTP API, shipped client, authorization, accounting,
backward compatibility, tests, actual deployment, rollback and recovery.

Read README.md, SPEC.md and RELEASE.md. They contain the complete product
and release contract. Use the existing application as the starting point;
all source changes must reach the built product. Each component is
straightforward in isolation, but the release must remain correct as a whole.

Use notes and intermediate checks as needed. Continue until the final built
artifact has passed every acceptance group, the deployed refund journey,
actual rollback to old code and redeployment with retained state. Retest
whenever later changes invalidate earlier evidence. Leave the new release
running and document its exact artifact and verification receipts.

The evaluation reports 36 delivery stages, the longest dependency-complete
chain, working user journeys and whether tests cover the final source and
artifact. A single session can contain many model/tool calls and context
compactions. There will be no human nudge to finish omitted parts. A change
in a file excluded from the build earns no product credit.
