---
name: skill-quality-review
description: Audit the active Codex skill catalog as a suite, then drill into specified or high-risk skills for trigger precision, information structure, guidance, pruning, and behavior-backed validation. Invoke only through $skill-quality-review; with no target audit the current active catalog, with a skill target perform a deep review, and with a directory target audit that suite. Do not scaffold a new skill.
---

# Skill Quality Review

Audit the portfolio first, then drill into individual skills when the user or evidence warrants it. Judge observable behavior, not file length or adherence to one universal shape.

Do not scaffold a new skill. Use this as the final quality gate after authoring or updating one, or as a periodic audit of the active catalog.

## 1. Resolve scope and authority

Interpret the invocation target:

- No target: audit the active skill catalog exposed to the current Codex session.
- One skill name, `SKILL.md`, or directory containing one skill: deeply review that skill.
- A directory or repository containing multiple skills: audit that suite, then drill into selected risks.

Use the runtime's available-skills catalog as the primary inventory. Do not equate the active catalog with `~/.codex/skills`; include active system, bundled, personal, project, and plugin skills. In no-target mode, exclude recommended, uninstalled, or inactive skills. In a targeted directory, include every target entry and mark its active status.

For a targeted suite, compare its descriptions against the wider active catalog when available, but keep findings and edits scoped to the target.

In single-skill mode, use active-catalog metadata for trigger comparison but do not read unrelated skill bodies unless an overlap or dependency makes them relevant.

Inventory each in-scope skill with its name, provenance, source locator, active status, version or revision when available, invocation policy, description, local resources, cross-skill references, and tool dependencies. Preserve duplicate names as separate entries and report shadowing unless runtime precedence is documented. Mark inaccessible or uncertain entries instead of silently omitting them.

Reconcile coverage counts for visible, body-readable, metadata-only, and unresolved skills.

If the runtime inventory is unavailable or may be truncated, label the result `partial catalog` and never issue a catalog-wide pass. If one target name resolves to multiple sources, review them as a collision group and do not choose an edit target silently.

Treat managed system, bundled, plugin, and installation-cache sources as read-only comparison inputs. Prefer the authoring source of truth over an installed copy even when both are writable. Edit only the exact user-owned or project target for which the user requested fixes.

If the user requested review only, do not edit. Pin the inspected revision and scope before making suite-wide claims.

## 2. Audit the suite

In suite mode, inspect every accessible in-scope skill statically before selecting individual deep reviews.

Work cheap-first: inventory metadata, validate schemas and links, cluster static risks, then run targeted behavior. Do not accumulate every `SKILL.md` in one context; inspect bodies in bounded fresh contexts and aggregate structured findings.

Check:

- Trigger collisions, ambiguous ownership, overly broad descriptions, and expected routes with no owner.
- Duplicate workflows, conflicting instructions, same-name shadowing, and stale aliases.
- Broken or circular cross-skill references and missing tool or resource dependencies.
- Invocation policies that do not match frequency, context cost, side effects, or authority.
- Related user-only skills whose cognitive load warrants a router, and routers with missing or stale targets.
- Repository and runtime conventions applied inconsistently across skills.

Assess coverage gaps only against declared routes, known usage, or an explicit task set. Do not invent a requirement that every conceivable task needs a skill.

Do not infer a trigger collision from shared words alone. Require overlapping intended tasks, concrete positive or near-miss cases, or observed misrouting.

Cluster plausible collisions before execution and test only the closest or highest-impact pairs. Do not run an all-pairs behavioral matrix.

Classify apparent overlap as exact duplication, functional overlap, conflicting implementation, or complementary specialization before recommending any deletion.

Calculate resident description cost only for skills the runtime confirms are exposed for model invocation. Separate user-only and unknown-policy skills. Label characters or words as proxies; do not report exact token cost without the relevant tokenizer.

Do not convert user-only skills to model invocation merely to make them memorable. When recall is the problem, prefer one small user-invoked router and verify that it names every intended target and its current invocation contract.

Rank drill-down candidates by behavioral risk:

- Broken mechanics or dependencies.
- Trigger collisions or observed misrouting.
- Implicit skills with material side effects or broad authority.
- Large resident-context contribution with weak routing value.
- Changed skills, suspected regressions, or unverified critical workflows.

Do not select a skill merely because its body is long or short. Choose the smallest set that covers each distinct high-risk finding. Do not run full behavioral tests for every installed skill unless the user explicitly requests full certification.

## 3. Deeply review selected skills

Deeply review a user-specified skill or each candidate selected by the suite audit.

Read its `SKILL.md`, directly linked resources, agent metadata, applicable repository instructions, and relevant neighboring skill descriptions.

### Trigger

Verify that the description states what the skill does and when it applies. Compare it with the active catalog, not in isolation.

For model-invoked descriptions, front-load a stable leading word when it improves routing. Keep one trigger expression per distinct execution branch and collapse synonyms that merely rename the same branch. When one concept controls invocation and execution, keep its vocabulary stable across the description, body, and related artifacts. Do not copy execution detail into the description merely for lexical alignment, or pad a user-only description for autonomous routing.

For model-invoked skills, count exposed description text as persistent context cost. For user-only skills, verify runtime behavior before assigning the same cost.

Flag broad or missing task language, trigger overlap, hidden side effects or authority expansion, and implementation detail that does not improve routing. Do not score description quality by length alone.

### Structure

Classify the skill as procedure-heavy, reference-heavy, or mixed. Treat none as inherently superior.

Keep material needed by nearly every execution in `SKILL.md`. Move branch-specific detail to linked resources only when that reduces irrelevant context. Require every context pointer to say when and why its resource should be read.

Flag duplicated facts, broken or deeply chained references, mandatory steps hidden in optional material, and reference files created only to satisfy a rigid architecture rule. Do not enforce a universal two-layer structure.

Keep a concept's definition, rules, and caveats together. Recommend an invocation cut only when a branch has an independent trigger or leading word and useful standalone execution. Recommend a sequence cut only when tightened criteria and checkpoints still leave reproduced premature completion. Otherwise keep one skill; account for the new description's context cost or the user's recall cost before splitting.

### Guidance

Hunt for prose that an established concept already encodes. For each compression candidate, record the original prose, proposed leading word, intended behavior, and evidence that the compressed form preserves or improves that behavior. Treat leading words as steering hypotheses, not proof.

Use the same term consistently where the concept recurs, without repeating its definition. Reject jargon that sounds authoritative but makes the target behavior less precise.

When reviewing a software planning or implementation skill, read [engineering-steering.md](references/engineering-steering.md) and apply its leading-word, vertical-slice, and tracer-bullet checks.

Require every material step and the workflow overall to end with an observable completion criterion. State the required result and coverage, not merely an activity. If the model finishes prematurely:

1. Sharpen the completion criterion.
2. Add an explicit checkpoint.
3. Split or delay future steps only if premature execution persists.

Do not hide future work by default. State the desired behavior positively; keep a prohibition only as a hard guardrail and pair it with what to do instead. Flag vague instructions such as "handle carefully", "use best practices", or "make it robust" unless paired with a checkable outcome.

### Pruning

Mark text as a deletion candidate when it restates default model behavior, duplicates another instruction, explains history without affecting execution, or has no identifiable trigger, decision, action, or completion effect.

Static review may identify candidates but cannot prove redundancy. Compare the full skill with an ablated version under the same tasks and settings. Delete only when repeated results show no meaningful regression.

Treat safety, authority, and irreversible-action instructions as high risk; do not prune them from a small sample. Do not optimize for a target line count or one-sentence body.

## 4. Run mechanical validation

Check every accessible in-scope skill for:

- Frontmatter syntax and runtime-supported keys.
- Skill name, folder name, metadata, invocation policy, and alias consistency.
- Every local link, referenced file, cross-skill edge, tool dependency, and runnable command.
- Repository-provided validators.

Record validator dependency failures separately from skill failures. A mechanical pass is not a behavioral pass.

## 5. Run behavioral validation

Use fresh contexts without leaking expected answers.

Test invocation according to the contract:

- For model-invoked skills, use positive prompts that should trigger and near-miss prompts that should not.
- For user-only skills, verify direct invocation and, when the runtime makes it observable, non-invocation without the explicit call.
- For mixed skills, verify both direct invocation and the model-invoked positive/near-miss cases.

For suite collision findings, test the same ambiguous prompt against the involved skills and observe routing. For each selected skill, test normal completion, important branches, and failure or incomplete-input behavior.

For leading-word compression, compare the original prose and compressed form on the same tasks. Pass only when intended behavior and safety constraints are preserved, not merely when token count falls.

Use no-skill, full-skill, and ablated-skill comparisons when deciding a guidance or pruning dispute. Repeat probabilistic cases only enough to distinguish a pattern from one lucky result; do not build an exhaustive model-by-prompt-by-repeat matrix by default.

Use fixtures or sandboxes for side-effecting workflows. If safe execution or required authority is unavailable, skip the case and mark it `not tested`.

Record runtime, model, prompts, revisions, and observed results. Do not declare the suite or a skill effective when only static checks ran. A sampled behavioral pass is not a suite-wide behavioral pass.

## 6. Report and complete

For a suite audit, report:

- Included and excluded sources, revisions, inaccessible entries, and inventory counts by provenance and invocation policy.
- Resident description cost with its measurement method and unknown-policy subtotal.
- Trigger collisions, gaps, duplicate responsibilities, broken dependencies, and policy risks.
- Ranked drill-down candidates, tested cases, and explicitly untested risks.

For a single-skill review, report its contract, four-axis findings, mechanical results, behavioral evidence, and active-catalog comparison scope.

Separate findings into:

- **Observed behavior** — reproduced through execution.
- **Static risk** — inferred from text or structure.
- **Mechanical failure** — invalid metadata, links, dependencies, or files.

Format each finding as `[severity] axis — evidence → impact → smallest fix`. Rank severity by behavioral impact, not style preference.

Give separate catalog and behavioral verdicts using `pass`, `pass with risks`, `fail`, `static review only`, or `not tested`.

A suite audit is complete only when inventory counts reconcile, unresolved sources are listed, every accessible skill receives mechanical checks, all model-invoked or unknown descriptions are compared, cross-skill edges are checked, high-severity findings have a disposition, and behavioral coverage or its absence is explicit.

If fixes were requested, make minimal edits only in the authorized scope and rerun affected checks. Do not generalize universal or suite-wide rules from an unpinned or partial sample.
