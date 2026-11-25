#!/usr/bin/env bash
# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# Fail if a Vivado log has a CRITICAL WARNING that is not allowed.
#
# Usage: check_critical.sh LOG [ALLOW_FILE]
#
# ALLOW_FILE, if it exists, has one entry per line: the issue that
# explains the warning, a tab, and an extended regular expression that
# matches the warning's line, e.g.
#
#   #114	\[Place 30-[0-9]+\].*MUXF7
#
# Blank lines and lines starting with "# " are comments. An allowed
# warning is still printed, with its issue, so it shows in the log of the
# run instead of passing silently. Any other CRITICAL line fails the check.
set -euo pipefail

log="${1:?usage: check_critical.sh LOG [ALLOW_FILE]}"
allow="${2:-}"

critical="$(grep -F CRITICAL "$log" || true)"
if [ -z "$critical" ]; then
    exit 0
fi

failed=0
while IFS= read -r line; do
    issue=""
    if [ -n "$allow" ] && [ -f "$allow" ]; then
        while IFS=$'\t' read -r entry_issue entry_re; do
            case "$entry_issue" in "" | "# "* | "#") continue ;; esac
            if [ -n "$entry_re" ] && grep -qE -- "$entry_re" <<<"$line"; then
                issue="$entry_issue"
                break
            fi
        done <"$allow"
    fi
    if [ -n "$issue" ]; then
        echo "$log: allowed ($issue): $line" >&2
    else
        echo "$log: $line" >&2
        failed=1
    fi
done <<<"$critical"

if [ $failed -ne 0 ]; then
    if [ -n "$allow" ] && [ -f "$allow" ]; then
        where="$allow"
    else
        where="an allow list (${allow:-none given} does not exist)"
    fi
    echo "$log: CRITICAL WARNING not in $where; see utils/check_critical.sh" >&2
fi
exit $failed
