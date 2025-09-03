#!/bin/bash

header="$(printf "+%.0s" {1..80})"
failures=()

preReqs=(shellcheck isort flake8)
for tool in "${preReqs[@]}"; do
  if ! command -v "${tool}" >/dev/null; then
    echo "ERROR: '${tool}' not found ..." >&2
    exit 1
  fi
done

mapfile -t shScripts < <(
  find . -type d -name .git -prune -o -type f -exec file {} + \
    | grep 'shell script' \
    | cut -d: -f1
)

for script in "${shScripts[@]}"; do
  if ! shellcheck "${script}" &> /dev/null; then
    echo "${header}"
    echo "ERROR: shellcheck '${script}' failed ..." >&2
    shellcheck "${script}"
    echo "${header}"
    [[ ! " ${failures[*]} " =~ " shellcheck " ]] && failures+=("shellcheck")
  fi
done

isort --check-only --diff . || failures+=("isort")

flake8 . || failures+=("flake8")

if [ ${#failures[@]} -eq 0 ]; then
  echo "PASS: All linter checks passed ..."
else
  for f in "${failures[@]}"; do
    echo "ERROR: '$f' lint checks failed" >&2
  done
fi

exit "${#failures[@]}"
