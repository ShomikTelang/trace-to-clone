# Research plan, limitations, and immediate follow-up

## Research questions

1. **Coverage**: How many user demonstrations or exploration actions are required to recover enough behavioral semantics to reproduce held-out workflows?
2. **Ground truth**: How can we compare source and clone when their internal state schemas differ? Start with independently defined canonical task predicates and observable UI expectations.
3. **Uncertainty**: What should the inference engine represent when it does not know a field's persistence, validation, or side effects? Require provenance tags: observed, inferred, manually supplied.
4. **Design fidelity**: What is the right loss for matched UI states? Screenshot MAE alone is insufficient; match elements, geometry, typography and content, controlling viewport, fonts, and time.
5. **State abstraction**: Where do explicit state machines stop scaling, and where should we switch to symbolic entity-level transitions and data-dependent preconditions?
6. **Exploration policy**: Does uncertainty-guided exploration outperform simple breadth-first navigation for workflow coverage per browser action?
7. **RL transfer**: At what fidelity level do synthetic-agent trajectories transfer to the reference app? Keep evaluation tasks held out from training and the code-generation prompt.

## Milestone 2: true reference-vs-clone differential test

- Start a pinned, disposable Kanboard Docker instance, and establish deterministic test fixtures (possibly using its JSON-RPC API for seeding, with a separate evaluator credential).
- Record task creation, editing, movement, closure, navigation and reload against Kanboard with real Playwright locators.
- Convert traces into a canonical semantic action format, e.g. `create_task(title)`, `move_task(id, column)`.
- Replay semantic actions through a separately discovered GUI element map for each app. Don't assume both apps have the same CSS selectors.
- Compare observable outputs and reference/clone canonical task predicates; capture screenshot differences only for matching screen states.
- Compute held-out success, coverage, time, model tokens, API cost, and uncertainty. Label mismatches by source: inferred spec, generator, UI mapping, or visual renderer.
- Run on a second non-Kanban category after Kanboard is stable to test generalization.

## Important non-goals for this version

- Full Kanboard feature parity; user management, multi-project workflows, swimlanes, plugins, comments and attachments are omitted.
- Exact Kanboard CSS/DOM or screenshot fidelity; the frontend is explicitly Kanboard-inspired, not an identical product copy.
- Autonomous arbitrary-app discovery; capture is scripted or guided.
- Model-trained visual repair, automatic API understanding, and actual RL training.
- Production multi-user isolation and permission controls.

## Evaluation rule

Never use the same generated spec as both the implementation and sole source of truth for correctness. Independent reference observations or held-out test assertions must decide whether the behavior is faithful. The clone's privileged state enables precise *internal* verification only; it does not prove external fidelity.
