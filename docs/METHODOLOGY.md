# Methodology

This document defines every reported metric precisely. The normative requirements are in [specs.md](../specs.md); each generated output also contains a `METHODOLOGY.md` with the exact tool versions used.

## Snapshot metrics

Each repository's configured ref resolves to one commit SHA, recorded with the full ref name. Remote sources are bare mirrors in the workspace; local sources are read in place.

**Tracked files** are the entries returned by NUL-delimited `git ls-tree -r -z --full-tree <sha>`, including symbolic links and submodule references.

**Materialization.** Every regular file (mode `100644` or `100755`) is written to the workspace with its exact blob bytes, read through `git cat-file --batch`. Because no checkout or archive step is involved, `.gitattributes` rules (`export-ignore`, `export-subst`, `eol`, `text`), `core.autocrlf`, and smudge filters such as Git LFS cannot change the measured content. Each file is stored in its own numbered directory under a safe name: names consisting of letters, digits, and `._+@=~-` are kept verbatim; other names keep only their safe suffixes (for example `odd, "name".py` becomes `file.py`). This preserves the LOC tool's language detection while making its output unambiguous to parse. `snapshots/<name>/manifest.json` in the workspace maps every materialized file back to its tracked path and blob ID.

**Source files and LOC.** The verified LOC tool runs once per repository with:

```text
--by-file --json --quiet --skip-uniqueness --timeout=0 --hide-rate --config=<empty file>
```

- `--skip-uniqueness` counts every tracked file, even when several have identical content.
- `--timeout=0` removes cloc's speed-dependent per-file time limit.
- `--hide-rate` keeps elapsed-time data out of the raw report.
- The empty `--config` file prevents a user's `~/.config/cloc/options.txt` from changing results.

A **source file** is a file the LOC tool assigns a language to; **LOC** is its `code` count, excluding blank and comment lines. Tracked files that are not counted appear in `excluded_files.csv` with one reason: symbolic link, submodule reference, empty file, binary or media extension, data extension, or not recognized by the LOC tool.

## History metrics

**History scope.** With the default `history_scope = "branches-and-tags"`, history is the set of commits reachable from `--branches --tags --remotes` plus the snapshot commit. Hosting-internal refs such as `refs/pull/*` (unmerged pull requests in GitHub mirrors), `refs/notes/*`, and `refs/stash` are excluded. With `history_scope = "all-refs"`, history is `--all`.

**Unique commits** equal `git rev-list --count` over the history scope, including merge commits.

**Contribution** comes from:

```text
git log --no-merges --root --numstat --no-renames --diff-algorithm=myers
        --no-ext-diff --no-textconv --no-color --no-mailmap --no-show-signature
        --encoding=UTF-8 <history scope>
```

Merge commits are excluded from contribution. Added and deleted lines are the numeric `numstat` fields summed per commit; binary entries (`-`) are counted in `Binary Files Excluded` and contribute no lines. Every flag that user or system Git configuration could otherwise change is pinned.

**Identity** is the exact author name and email. An explicit alias in `audit.toml` replaces it with a canonical identity; the original values remain in `commits.csv`. Authors matching an exclusion pattern are removed from contribution metrics and listed with their commit counts in `excluded_authors.csv`.

**Active periods** use the author timestamp in the author's own time zone: the local calendar date (active days), the ISO 8601 year-week (active weeks), and `YYYY-MM` (active months). Average lines added per active day, week, or month equal total lines added divided by the number of distinct active periods.

## Global consolidation

Repository commit counts are summed without claiming cross-repository uniqueness, and are labeled as a sum. Developer identities are consolidated across repositories by exact identity: a commit SHA that appears in several repositories (for example in forks) is counted once, provided its metadata is identical everywhere; otherwise the run fails. Active periods and averages are recalculated from the union of commits, never summed.

## Rounding

Canonical ratios and percentages use decimal arithmetic rounded half-up to 12 decimal places and are stored as strings, so results are identical on every platform. Markdown tables and chart labels round to 2 decimal places for presentation only.

## Validation

Every run records the reconciliation checks listed in [specs.md](../specs.md#6-validation-catalog). They compare independent sources: the LOC tool's own totals against per-file rows, `git rev-list` counts against parsed commits, per-period series against developer totals, and repository totals against global totals. Each run also fingerprints the status and refs of every source repository before and after analysis.

Any failed check stops the run after the canonical CSV files are written as evidence; `REPORT.md` is not produced. `repo-audit verify` repeats the reconciliation independently by recomputing every derived table from canonical data.

## Interpretation limits

The metrics describe repository content and recorded history. They are sensitive to generated or vendored code, squash and rebase policies, history rewrites, pair programming, and identity hygiene. They do not measure effort, value, quality, or individual performance (see [intent.md](../intent.md#responsible-use)).
