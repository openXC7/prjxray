# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
N ?= 10
# PHASER_IN C's "reference input 1" bit, column word 59. The tile's words
# are 55..73, between HCLK_CMT (45..54) and UPPER_T (74..100).
GENERATE_ARGS?="--oneval 1 --design params.csv --dframe 1C --dword 4 --dbit 27"
include ../fuzzaddr/common.mk
