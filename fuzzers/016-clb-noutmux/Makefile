# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
# Specimen count
# top.py fixes random.seed(0), so every specimen is the same design
# (#113). Two are still needed: segmatch runs with -m 2, and with one
# specimen the tags set in it once fall below that and the rows change.
N := 2

# A grep regex for SLICEM features to be skipped for SLICELs
SLICEM_FEATURES ?= "DOUTMUX.MC31"

include ../clb_ext.mk

