# Codebase Archaeology

Reconstructs why code exists — from git history, PR discussions, and linked issues — with every
claim traced back to a specific commit or comment. This glossary is the project's shared language.
Design lives in [DESIGN.md](./DESIGN.md); it is not repeated here.

## Language

### Support tiers

**Symbol-anchored support**:
A language for which the full pipeline is available, including resolving a symbol to a line range
and filtering commits by significance beyond the floor. Requires per-language work and its own
validation set.
_Avoid_: full support, first-class support, supported language

**Discussion-only support**:
A language for which everything language-blind is available — ingest, the lineage walk, retrieval
over discussion, and the significance floor — but symbol anchoring is not. The default state of any
language nobody has validated.
_Avoid_: partial support, unsupported, degraded mode

**Significance floor**:
The subset of insignificance that can be detected with no knowledge of any particular language:
changes touching only whitespace and comments. Verified to hold across 371 languages.
_Avoid_: the naive classifier, the whitespace check

### Significance classifier feature set

The concrete rules deciding which commits count as insignificant. **Layered**: the significance
floor applies to every language; an opt-in per-language AST layer (tree-sitter diff ignoring
format-only changes, JS/TSX first) stacks above it. Features are cached per commit and labels are
derived from them as a pure function, so revising the rules relabels history without touching git.
Recall-biased by design: dropping the introducing commit costs more than passing noise through.

### Resolved

**Significance**:
Was contested — DESIGN.md §3 and §7 gave incompatible definitions and the headline eval numbers
depended on which was right. Resolved as the layered classifier defined by *Significance
classifier feature set* above.
