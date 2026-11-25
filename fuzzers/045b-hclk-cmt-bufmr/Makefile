# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# N randomised specimens plus the fixed calibration and negative ones.
# See README.md for what each one is for.
N ?= 50
FUZDIR ?= ${PWD}

RAND := $(addprefix build/specimen_,$(shell seq -f '%03.0f' $(N)))
FIXED := \
	build/specimen_cal_s0 \
	build/specimen_cal_s1 \
	build/specimen_neg_unused \
	build/specimen_neg_const_ce \
	build/specimen_probe_above
SPECIMENS := $(RAND) $(FIXED)
SPECIMENS_OK := $(addsuffix /OK,$(SPECIMENS))

# One-hot PHASER_IN -> performance-clock population: ONEHOT_N specimens in
# which every HCLK_CMT tile has one BUFMR whose route is fixed through one
# of the 16 (PHASERIN_RCLKn, PHSR_PERFCLKm) pairs.  `make database-onehot`
# builds the default population plus these.
ONEHOT_N ?= 32
ONEHOT := $(addprefix build/specimen_P_,$(shell seq -f '%03.0f' $(ONEHOT_N)))

all: database

$(SPECIMENS_OK) $(addsuffix /OK,$(ONEHOT)):
	mkdir -p build
	+bash $(FUZDIR)/generate.sh $(subst /OK,,$@)

# -c 2 as 045 uses for the HCLK_CMT mux positions.  Not lowered to make a
# row resolve.
SEGMATCH = ${XRAY_SEGMATCH} -c 2

TILES := hclk_cmt hclk_cmt_l

database: $(addprefix build/segbits_,$(addsuffix .db,$(TILES)))

database-onehot:
	$(MAKE) database SPECIMENS="$(SPECIMENS) $(ONEHOT)"

build/segbits_hclk_cmt.rdb: $(SPECIMENS_OK)
	$(SEGMATCH) -o $@ $(addsuffix /segdata_hclk_cmt.txt,$(SPECIMENS))

build/segbits_hclk_cmt_l.rdb: $(SPECIMENS_OK)
	$(SEGMATCH) -o $@ $(addsuffix /segdata_hclk_cmt_l.txt,$(SPECIMENS))

# 039a's filter: rows with bits, nothing for <const0> / <0 candidates> /
# unresolved tags, and a notes file for everything refused.  Then
# onehot_rows.py replaces the PHASERIN -> PHSR_PERFCLK rows, whose bits are
# all shared with other pips, with the ones the onehot_perf specimens give,
# and fails if any specimen disagrees with them.
build/segbits_%.db: build/segbits_%.rdb
	python3 $(FUZDIR)/../039a-hclk-bufrclk-perfclk/filter_rdb.py \
		$< build/segbits_$*.filtered.db build/ppips_$*.db build/$*.notes.txt
	python3 $(FUZDIR)/onehot_rows.py build $* \
		build/segbits_$*.filtered.db $@ build/$*.notes.txt \
		${XRAY_DATABASE_DIR}/${XRAY_DATABASE}/segbits_$*.db

# The calibration gate: Vivado 2025.2 sets HCLK_CMT_L 28_187 for a used
# BUFMRCE site 0 on xc7a100t and xc7a35t.  If IN_USE of site 0 does not
# come back with that bit, the campaign resolved something else and
# nothing is merged.  segmaker names both tile types HCLK_CMT; mergedb
# renames the _l rows to HCLK_CMT_L when they are merged.
gate: build/segbits_hclk_cmt_l.db
	grep -E '^HCLK_CMT\.BUFMRCE\.BUFMRCE_X0Y0\.IN_USE( [^ ]+)* 28_187( |$$)' $<
	grep -E '^HCLK_CMT\.HCLK_CMT_MUX_PHSR_PERFCLK0\.HCLK_CMT_PHASERIN_RCLK2 26_178 27_179 29_131$$' $<

# Only rows that carry bits are merged, and no maskmerge: this population
# is far too narrow to rewrite the masks 045 built.
pushdb: gate
	${XRAY_MERGEDB} hclk_cmt build/segbits_hclk_cmt.db
	${XRAY_MERGEDB} hclk_cmt_l build/segbits_hclk_cmt_l.db

run:
	$(MAKE) clean
	$(MAKE) database
	$(MAKE) pushdb
	touch run.ok

clean:
	rm -rf build run.ok

.PHONY: all database database-onehot gate pushdb run clean
