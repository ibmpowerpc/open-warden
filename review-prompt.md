Review the current GitHub pull request using the attached PR metadata, changed files list, and diff.

Primary goal:
- find real bugs introduced by this PR

Focus on:
- correctness bugs
- behavioral regressions
- data integrity issues
- security issues
- rollout and migration issues
- frontend/backend mismatches
- broken defaults, failure paths, and error handling

Rules:
- report only high-confidence findings caused by this PR
- do not stop after the first bug; continue reviewing the remaining changed files
- do not merge unrelated bugs into one finding
- prefer strong bug reports over style or refactoring advice
- ignore cosmetic issues unless they hide a real defect

For each finding:
- include the exact changed file and line or hunk
- explain the failure mode
- explain how to trigger it
- suggest the smallest practical fix

If the diff is large:
- inspect the highest-risk files first
- then continue through the rest of the changed files before finalizing

Return concise review findings in markdown.
