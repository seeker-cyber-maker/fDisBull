#!/usr/bin/env bash
# Publish only the three authored PR files after explicit operator execution.
set -euo pipefail
bundle=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=${1:?Usage: bash PUBLISH_PR.sh /path/to/clean/fDisBull-checkout}
command -v gh >/dev/null || { printf '%s\n' 'GitHub CLI (gh) is required.' >&2; exit 1; }
gh auth status --hostname github.com
cd -- "$repo"
[[ $(git rev-parse --is-inside-work-tree) == true ]]
[[ -z $(git status --porcelain) ]] || { printf '%s\n' 'Refusing a dirty checkout.' >&2; exit 1; }
remote=$(git remote get-url origin)
case "$remote" in
  https://github.com/seeker-cyber-maker/fDisBull|https://github.com/seeker-cyber-maker/fDisBull.git|git@github.com:seeker-cyber-maker/fDisBull.git) ;;
  *) printf '%s\n' 'Origin must be seeker-cyber-maker/fDisBull.' >&2; exit 1 ;;
esac
branch=docs/diagnostic-graphics-friction-20261031
git fetch origin main
git show-ref --verify --quiet "refs/heads/$branch" && { printf '%s\n' 'Local branch already exists; review it rather than overwrite.' >&2; exit 1; }
git switch -c "$branch" origin/main
git am "$bundle/diagnostic-graphics-friction.patch"
"${PYTHON:-python3}" docs/evidence/diagnostic-graphics-2026-10-31/check_contract_models.py --require-z3
git diff --check HEAD^ HEAD
git push -u origin "$branch"
gh pr create --repo seeker-cyber-maker/fDisBull --base main --head "$branch" \
  --title "$(cat "$bundle/pr/PR_TITLE.txt")" --body-file "$bundle/pr/PR_BODY.md"
