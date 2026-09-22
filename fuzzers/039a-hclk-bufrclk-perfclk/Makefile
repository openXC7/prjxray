# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

# N randomised specimens plus the four one-hot calibration specimens and
# the four negative controls.  See README.md for what each one is for.
N ?= 50
FUZDIR ?= ${PWD}

RAND := $(addprefix build/specimen_,$(shell seq -f '%03.0f' $(N)))
FIXED := \
	build/specimen_cal0 \
	build/specimen_cal1 \
	build/specimen_cal2 \
	build/specimen_cal3 \
	build/specimen_neg_ioi \
	build/specimen_neg_unused \
	build/specimen_neg_bufh \
	build/specimen_neg_unconsumed
SPECIMENS := $(RAND) $(FIXED)
SPECIMENS_OK := $(addsuffix /OK,$(SPECIMENS))

# Forced-column population.  Not part of the default `make database`:
# that run stays the mixed one above.  `make database-sides` builds
# SIDE_N randomised specimens on each CMT column plus one mmcm-fed
# one-hot specimen per BUFRCLK index per column.
SIDE_N ?= 32
SIDE_SEQ := $(shell seq -f '%03.0f' $(SIDE_N))
SIDE_SPECIMENS := \
	$(foreach sd,L R, \
		$(addprefix build/specimen_$(sd)_,$(SIDE_SEQ)) \
		$(foreach n,0 1 2 3,build/specimen_cal$(sd)$(n)))

all: database

$(SPECIMENS_OK):
	mkdir -p build
	+bash $(FUZDIR)/generate.sh $(subst /OK,,$@)

# The enable buffers are one bit, like the rest of the HCLK enables that
# 039 and 058 resolve at -c 5.  The CMT performance-clock mux positions
# are one or two bits and need the lower threshold 045 uses.  Neither
# number is lowered to make a family resolve.
SEGMATCH_EN = ${XRAY_SEGMATCH} -c 5
SEGMATCH_PIP = ${XRAY_SEGMATCH} -c 2

TILES := hclk_l hclk_r hclk_cmt hclk_cmt_l cmt_top_r_lower_b cmt_top_l_lower_b

database: $(addprefix build/segbits_,$(addsuffix .db,$(TILES)))

database-sides:
	$(MAKE) database SPECIMENS="$(SIDE_SPECIMENS)"

build/segbits_hclk_l.rdb: $(SPECIMENS_OK)
	$(SEGMATCH_EN) -o $@ $(addsuffix /segdata_hclk_l.txt,$(SPECIMENS))

build/segbits_hclk_r.rdb: $(SPECIMENS_OK)
	$(SEGMATCH_EN) -o $@ $(addsuffix /segdata_hclk_r.txt,$(SPECIMENS))

build/segbits_hclk_cmt.rdb: $(SPECIMENS_OK)
	$(SEGMATCH_PIP) -o $@ $(addsuffix /segdata_hclk_cmt.txt,$(SPECIMENS))

build/segbits_hclk_cmt_l.rdb: $(SPECIMENS_OK)
	$(SEGMATCH_PIP) -o $@ $(addsuffix /segdata_hclk_cmt_l.txt,$(SPECIMENS))

build/segbits_cmt_top_r_lower_b.rdb: $(SPECIMENS_OK)
	$(SEGMATCH_PIP) -o $@ $(addsuffix /segdata_cmt_top_r_lower_b.txt,$(SPECIMENS))

build/segbits_cmt_top_l_lower_b.rdb: $(SPECIMENS_OK)
	$(SEGMATCH_PIP) -o $@ $(addsuffix /segdata_cmt_top_l_lower_b.txt,$(SPECIMENS))

# filter_rdb.py splits the raw segmatch output into rows that carry bits,
# pseudo-pips for routed pips with zero candidate bits, and a notes file
# for everything it refuses to publish.
build/segbits_%.db: build/segbits_%.rdb
	python3 $(FUZDIR)/filter_rdb.py $< $@ build/ppips_$*.db build/$*.notes.txt

# The calibration gate: if the one-hot specimens do not put 00_31 on
# BUFRCLK2, the campaign resolved something else and nothing is merged.
gate: build/segbits_hclk_l.db
	grep -E 'ENABLE_BUFFER\.HCLK_CK_BUFRCLK2( [^ ]+)* 00_31( |$$)' $<

# Only the rows that carry bits are merged.  The pseudo-pips land in
# build/ppips_*.db already tile-prefixed; they are reviewed and applied
# to ppips_cmt_top_{r,l}_lower_b.db by hand, the way the I2IOCLK default
# positions were.  This fuzzer runs no maskmerge: its population is far
# too narrow to rewrite a mask that 045 and 058 built.
pushdb: gate
	${XRAY_MERGEDB} hclk_l build/segbits_hclk_l.db
	${XRAY_MERGEDB} hclk_r build/segbits_hclk_r.db
	${XRAY_MERGEDB} hclk_cmt build/segbits_hclk_cmt.db
	${XRAY_MERGEDB} hclk_cmt_l build/segbits_hclk_cmt_l.db
	${XRAY_MERGEDB} cmt_top_r_lower_b build/segbits_cmt_top_r_lower_b.db
	${XRAY_MERGEDB} cmt_top_l_lower_b build/segbits_cmt_top_l_lower_b.db

run:
	$(MAKE) clean
	$(MAKE) database
	$(MAKE) pushdb
	touch run.ok

clean:
	rm -rf build run.ok

.PHONY: all database database-sides gate pushdb run clean
