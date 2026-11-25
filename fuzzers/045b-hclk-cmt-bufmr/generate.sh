#!/usr/bin/env bash
# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# Specimen driver: derive FUZZ_MODE from the specimen directory name and
# hand over to the generic top_generate.mk.
set -euo pipefail

spec="${1:?specimen dir}"

# A directory left behind by an interrupted run would be picked up as
# finished work.  Drop only this specimen, never a sibling.
if [ -d "$spec" ] && [ ! -f "$spec/OK" ]; then
    rm -rf "$spec"
fi

set +u
# shellcheck disable=SC1090
source "${XRAY_GENHEADER}"
set -u

case "$(basename "$SPECDIR")" in
    specimen_cal_s0) export FUZZ_MODE=cal_s0 ;;
    specimen_cal_s1) export FUZZ_MODE=cal_s1 ;;
    specimen_neg_unused) export FUZZ_MODE=neg_unused ;;
    specimen_neg_unconsumed) export FUZZ_MODE=neg_unconsumed ;;
    specimen_neg_const_ce) export FUZZ_MODE=neg_const_ce ;;
    specimen_probe_above) export FUZZ_MODE=probe_above ;;
    *) export FUZZ_MODE="${FUZZ_MODE:-campaign}" ;;
esac

make -f "${XRAY_DIR}/utils/top_generate.mk"
