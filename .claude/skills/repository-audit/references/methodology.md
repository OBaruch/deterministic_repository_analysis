# Deterministic Methodology

- Remote sources are bare mirrors in the external workspace; local sources are read in place and never checked out.
- Each configured ref resolves to one commit SHA, which can be pinned with `expected_sha`.
- Tracked files come from NUL-delimited `git ls-tree -r -z` output for that SHA.
- Regular files are materialized byte-for-byte with `git cat-file --batch`; no checkout, filter, text conversion, or archive attribute changes the content.
- Language and code LOC per file come from the verified cloc command, run with `--skip-uniqueness --timeout=0 --hide-rate` and an empty options file.
- Files cloc does not count are listed in `excluded_files.csv` with a deterministic reason.
- History covers the configured `history_scope`; unique commits come from `git rev-list --count` over it.
- Developer contribution comes from numeric `git log --no-merges --root --numstat` fields with renames, external diff drivers, and text conversion disabled and the Myers algorithm pinned.
- Binary numstat entries are counted per commit but excluded from line totals.
- Active periods use the author timestamp: local date, ISO year-week, and `YYYY-MM`.
- Global exact-identity periods are recalculated over the union of commits; averages are never summed.
- Canonical CSV data is written before Markdown, SVG, HTML, and PDF rendering.
- Every repository, developer period, and global sum is reconciled programmatically, and `repo-audit verify` recomputes every derived table independently.
