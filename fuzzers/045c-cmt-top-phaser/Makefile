# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# Needs the tilegrid's bits entries for CMT_TOP_*_UPPER_B and *_LOWER_T,
# from 005-tilegrid's cmt_upper_b and cmt_lower_t. See README.md.
N ?= 40
FUZDIR ?= ${PWD}

SPECIMENS := $(addprefix build/specimen_,$(shell seq -f '%03.0f' $(N)))
SPECIMENS_OK := $(addsuffix /OK,$(SPECIMENS))

TILES := cmt_top_r_upper_b cmt_top_l_upper_b cmt_top_r_lower_t cmt_top_l_lower_t

all: database

$(SPECIMENS_OK):
	mkdir -p build
	+bash $(FUZDIR)/generate.sh $(subst /OK,,$@)

database: $(addprefix build/segbits_,$(addsuffix .db,$(TILES)))

# solve_rows.py, not segmatch: the reference mux is a code whose bits are
# shared between inputs. It fails, and writes nothing, unless the rows
# explain every tile of every specimen.
build/segbits_%.db: $(SPECIMENS_OK)
	python3 $(FUZDIR)/solve_rows.py $* $@ build/$*.notes.txt $(SPECIMENS)

# Every forced route must have taken its mux input, and the R tiles' rows
# must be the ones measured by forcing each input (gate_rows.txt). Every
# tile type must have its 14 rows.
gate: database
	! grep -h 'ok=0' $(addsuffix /forced_check.txt,$(SPECIMENS))
	while read -r t row; do \
		grep -qxF -- "$$row" build/segbits_$$t.db || { echo "gate: missing in $$t: $$row"; exit 1; }; \
	done < $(FUZDIR)/gate_rows.txt
	for t in $(TILES); do \
		n=$$(wc -l < build/segbits_$$t.db); \
		test "$$n" -eq 14 || { echo "gate: $$t has $$n rows, not 14"; exit 1; }; \
	done

# The rows go into new segbits files. The route-through pips leave the
# ppips files, where 071-ppips listed them as always on (it no longer does).
pushdb: gate
	${XRAY_MERGEDB} cmt_top_r_upper_b build/segbits_cmt_top_r_upper_b.db
	${XRAY_MERGEDB} cmt_top_l_upper_b build/segbits_cmt_top_l_upper_b.db
	${XRAY_MERGEDB} cmt_top_r_lower_t build/segbits_cmt_top_r_lower_t.db
	${XRAY_MERGEDB} cmt_top_l_lower_t build/segbits_cmt_top_l_lower_t.db
	for t in $(TILES); do \
		f=${XRAY_DATABASE_DIR}/${XRAY_DATABASE}/ppips_$$t.db; \
		if [ -f $$f ]; then sed -i -E '/\.CMT_PHASER_IN_(CA|DB)_RCLK\.CMT_PHASER_IN_(CA|DB)_PHASEREFCLK always$$/d' $$f; fi; \
	done

run:
	$(MAKE) clean
	$(MAKE) database
	$(MAKE) pushdb
	touch run.ok

clean:
	rm -rf build run.ok

.PHONY: all database gate pushdb run clean
