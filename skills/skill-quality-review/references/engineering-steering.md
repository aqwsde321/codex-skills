# Engineering Steering Patterns

Use this reference only when reviewing a skill that plans or implements software. Treat every term as a behavioral hypothesis, not a required keyword.

## Compact engineering concepts

| Leading word | Behavior it should recruit | Smell it can replace |
| --- | --- | --- |
| `vertical slice` | Deliver one narrow, complete behavior across every affected layer | Layer-by-layer plans that delay integration |
| `tracer bullet` | Prove the first minimal, production-intent end-to-end path, then expand from feedback | Infrastructure built before any executable path |
| `red-green-refactor` | Fail on one behavior, implement the minimum, clean up while green | Bulk tests followed by bulk implementation |
| `tight loop` | Keep feedback fast, deterministic, and cheap enough to repeat | Repeated prose asking for speed and low overhead |
| `deep module` | Put substantial behavior behind a small, stable interface | Many shallow modules that expose coordination complexity |
| `single source of truth` | Give each rule or fact one authoritative home | Duplicated definitions that can drift |

Do not reward keyword presence. Verify that the skill's actual procedure and completion criteria express the recruited behavior.

`Vertical slice` describes the shape of a work unit. `Tracer bullet` describes the first uncertainty-reducing implementation path; unlike a disposable prototype, it is intended to evolve into the delivered system.

## Vertical-slice audit

For a planning skill:

- Flag tickets divided only by schema, backend, API, UI, or tests when no item delivers independently verifiable behavior.
- Prefer tracer-bullet tickets: each item should complete one thin end-to-end capability, declare dependencies, and have acceptance criteria that can pass on its own.

For an implementation skill:

- Prefer one minimal tracer bullet that proves the affected path end to end before expanding breadth.
- Expand through additional thin, testable slices instead of completing an entire horizontal layer first.
- Pair each slice with the shortest relevant feedback loop, such as an integration test, executable check, or observable demo.

A vertical slice crosses every **affected** layer, not every layer in the system. Do not force the pattern onto a genuinely single-layer change, an indivisible migration, or prerequisite platform work that cannot yet deliver user-visible behavior. Even then, require an independently verifiable completion criterion.

Retain a short local definition when project usage differs from an established term. Reject jargon that saves tokens but introduces ambiguity or cargo-cult behavior.
