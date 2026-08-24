# Dig 01 — React core functions (seed eval set)

Ten symbols walked by hand on 2026-08-25 against facebook/react @ HEAD
(`git log -L <start>,<end>:<file>`, full clone in `.scratch/react`). Raw walk logs:
`.scratch/dig/n*.log`.

## The ten cases

### 1. scheduleUpdateOnFiber — Path A
Anchor: `packages/react-reconciler/src/ReactFiberWorkLoop.js:987`. Walk depth: 28 commits,
2019→2025. Introducing range anchored at `9055e31e5c` "Replace old Fiber Scheduler with new one
(#15387)". Expected answer: scheduling split from render work so sync updates flush before paint;
evolved through lanes (`8f05f2bd6d`, #19108). Newest edit is a lanes bugfix (#33170), not rationale.

### 2. reconcileChildFibers — Path A
Anchor: `packages/react-reconciler/src/ReactChildFiber.js:2110`. Walk depth: 32 commits,
2016→2023. Introducing commit: `7c8a090994` Sebastian Markbåge, "Child Fiber" (2016-05-23) —
**no PR number**; the Fiber rewrite rationale lives in issues/talks, not the commit. Expected
answer: keyed/unkeyed diffing producing minimal mutations; walk crosses the packages/ restructure
rename (R100, see findings). Good attribution case with weak recorded rationale → partial answer.

### 3. renderWithHooks — Path A
Anchor: `packages/react-reconciler/src/ReactFiberHooks.js:505`. Walk depth: 37 commits,
2018→2026. Introducing commit: `7bee9fbdd4` Andrew Clark, "Initial hooks implementation"
(2018-09-05) — again no PR. Newest edits are `[flow] Bump` churn (`900ae094d8`) → textbook
insignificant-by-AST-layer candidates. Expected answer: hooks state stored on fiber.memoizedState,
dispatch wired per-render; rationale distributed across RFCs (external repo → link-only).

### 4. createRoot — Path A
Anchor: `packages/react-dom/src/client/ReactDOMRoot.js:171`. Walk depth: 31 commits,
2019→2026. Walk anchors at `b8f8258775` Dan Abramov, "Split ReactDOM entry point (#17331)" —
but createRoot existed earlier as unstable_createRoot in other files → **attribution chain stops
early without cross-file follow**. True origin story spans 17.x concurrent-root migration.

### 5. useSyncExternalStore — Path A + staleness
Anchor (dispatcher entry): `packages/react/src/ReactHooks.js:188`; real impl in
ReactFiberHooks (`mountSyncExternalStore`). Shallow walk (7 commits) at dispatcher level; deeper
story: replaced the earlier useMutableSource experiment — documented reversal, RFC 220-era.
Expected output should present arc: mutableSource → useSyncExternalStore, citing reversal.

### 6. flushSyncFromReconciler — Path A
Anchor: `ReactFiberWorkLoop.js:1906` (public `flushSync` re-exported from react-dom). Walk
depth: 34, 2019→2025. Same scheduler-split origin as case 1 (`9055e31e5c`). Recent churn shows
sync-flush semantics moving into `ReactFiberRootScheduler` (`defffdbba4`, #31987) → answer must
describe current split-brain state, not 2019 rationale alone.

### 7. createContext / readContext — Path A
Anchors: `packages/react/src/ReactContext.js:14`, `react-reconciler/src/ReactFiberNewContext.js:553`.
createContext walk anchors cleanly at `87ae211ccd` Andrew Clark, "New context API (#11818)"
(2018-01-24) — ideal citation-rich case replacing legacy context. readContext side shallow (8).

### 8. throwException — Path A
Anchor: `packages/react-reconciler/src/ReactFiberThrow.js:364`. Deepest walk: 51 commits.
Introducing commit is itself an extraction: `8af1f87929` "Rename ReactFiberScheduler ->
ReactFiberWorkLoop and extract throwException from Unwind (#15725)" → true origin (Unwind/error
boundaries 2016-17) requires cross-file lineage. Error-boundary rationale partially in issues.

### 9. memo / forwardRef — Path A
memo: `packages/react/src/ReactMemo.js:12`, introduced as **pure()**: `a0733fe13d` Andrew Clark,
"pure (#13748)" — renamed after community feedback; nice naming-rationale case.
forwardRef: `ReactForwardRef.js:12`, `bc70441c8b` Brian Vaughn, "RFC #30: React.forwardRef
implementation (#12346)" — RFC-linked, citation-rich.

### 10. forwardRef defaultProps warning — abstention/staleness probe
Anchor: `ReactForwardRef.js:42`. Warning block stable since `920f30ef77` #12644 (2018); latest
touch `fea900e454` #28326 removed propTypes checks. Broader defaultProps-for-function-components
deprecation **no longer exists at HEAD** (React 19 removal) — asking about it must surface the
reversal or abstain, never explain the removed warning as current.

## Findings that shape the tool

1. **Blobless clone breaks `git log -L`.** Lazy blob fetches made walks network-bound (>5 min
   timeout); full clone runs them in <1 s. Tier-1 ingest must either fetch needed blobs or treat
   lineage as requiring fuller materialization; DESIGN.md §5's cache-by-(repo,file,symbol,head)
   stands, but cold-cache cost is worse than assumed.
2. **`git log -L` crossed an R100 rename implicitly** (`src/renderers/shared/fiber/` →
   `packages/react-reconciler/src/`). Our lineage walker must reproduce this; synthetic-rename
   fixtures should assert it explicitly.
3. **Attribution chains stop at extraction/split commits** (cases 4, 8): function-level origin
   ≠ concept-level origin. Cross-file lineage is a real gap; v1 should label these honestly.
4. **Noise floor confirmed.** Of 286 walked commits, ~25 (~9%) are obviously insignificant
   (flow bumps ×6+, prettier upgrades, codemods, moves/renames); several more are borderline.
   Flow/type-annotation churn dominates recent history on typed files → JS/TSX AST layer must
   ignore type-position changes or recall suffers.
5. **Direct-to-main landings exist** ("Child Fiber", "Initial hooks implementation"): no PR
   discussion anywhere → correct behavior is partial answer or abstention, not invention.
   Two deliberate abstention cases seeded (2, 10).
