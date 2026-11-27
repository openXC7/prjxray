#!/usr/bin/env bash
# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
set -euo pipefail

spec="${1:?specimen dir}"
# A directory left behind by an interrupted run would be picked up as
# finished work. Drop only this specimen.
if [ -d "$spec" ] && [ ! -f "$spec/OK" ]; then
    rm -rf "${spec:?}"
fi

set +u
# shellcheck disable=SC1090
source "${XRAY_GENHEADER}"
set -u

make -f "${XRAY_DIR}/utils/top_generate.mk"
