# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
N ?= 10
# PHASER_IN A's "reference input 1" bit, column word 38. The tile's words
# are 27..45, the mirror of UPPER_B's 55..73 about the HCLK row.
GENERATE_ARGS?="--oneval 1 --design params.csv --dframe 1C --dword 11 --dbit 27"
include ../fuzzaddr/common.mk
