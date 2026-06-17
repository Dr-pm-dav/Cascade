# Main Branch Protection

This repository should treat `main` as a protected branch. Changes should land through pull requests after review and automated checks.

## Rules Included

- Block branch deletion.
- Block force pushes.
- Require linear history.
- Require signed commits.
- Require pull requests before merging.
- Require at least one approving review.
- Dismiss stale approvals after new commits.
- Require approval from someone other than the last pusher.
- Require all review conversations to be resolved.
- Require branches to be up to date before merging.
- Allow squash and rebase merges.

## Apply With GitHub CLI

Replace `OWNER/REPO` with the target repository:

```sh
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/OWNER/REPO/rulesets \
  --input .github/rulesets/main-branch-protection.json
```

## Add Required Checks

The ruleset currently contains an empty `required_status_checks` list so it can work for any repo. After CI is configured, add the exact check names to `.github/rulesets/main-branch-protection.json`.

Example:

```json
"required_status_checks": [
  {
    "context": "test",
    "integration_id": null
  }
]
```

## Notes

Repository administrators can also create the same protection manually in GitHub:

`Settings -> Rules -> Rulesets -> New branch ruleset`
