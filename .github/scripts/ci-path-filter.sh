#!/usr/bin/env bash
# Decide whether a path-filtered GitHub workflow should run its full suite.
# Fail open (run=true) when the diff cannot be computed so coverage is not dropped.
set -euo pipefail

if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
  echo "GITHUB_OUTPUT is required" >&2
  exit 1
fi

if [[ -z "${FILTER_REGEX:-}" ]]; then
  echo "FILTER_REGEX is required" >&2
  exit 1
fi

force_run() {
  local reason="$1"
  echo "run=true" >> "${GITHUB_OUTPUT}"
  echo "Path filter: run=true (${reason})"
  exit 0
}

event="${GITHUB_EVENT_NAME:-}"
case "${event}" in
  workflow_dispatch|merge_group)
    force_run "event ${event} always runs the full suite"
    ;;
esac

base=""
tip=""
if [[ "${event}" == "push" ]]; then
  base="${GITHUB_EVENT_BEFORE:-}"
  tip="${GITHUB_SHA:-}"
  if [[ -z "${base}" || "${base}" == "0000000000000000000000000000000000000000" ]]; then
    force_run "push has no usable before SHA"
  fi
else
  base="${PR_BASE_SHA:-}"
  tip="${PR_HEAD_SHA:-${GITHUB_SHA:-}}"
fi

if [[ -z "${base}" || -z "${tip}" ]]; then
  force_run "base or tip SHA missing"
fi

if ! changed="$(git diff --name-only "${base}" "${tip}")"; then
  force_run "git diff failed"
fi

if printf '%s\n' "${changed}" | grep -Eq "${FILTER_REGEX}"; then
  echo "run=true" >> "${GITHUB_OUTPUT}"
  echo "Path filter: run=true (matched ${FILTER_REGEX})"
else
  echo "run=false" >> "${GITHUB_OUTPUT}"
  echo "Path filter: run=false (no path matched ${FILTER_REGEX})"
fi
