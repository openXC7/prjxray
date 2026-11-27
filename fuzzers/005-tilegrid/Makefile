# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

# I/O bank types present on the target device. Most 7-series parts have
# high-range (HR) banks; Virtex-7 "VX" parts are high-performance (HP) only.
HAS_HIGH_RANGE_BANKS ?= 1
HAS_HIGH_PERFORMANCE_BANKS ?= 0

ifeq (${XRAY_DATABASE}, virtex7)
HAS_HIGH_PERFORMANCE_BANKS = 1
# TODO: some virtex devices also have high range banks
HAS_HIGH_RANGE_BANKS = 0
endif
ifeq (${XRAY_DATABASE}, kintex7)
# xc7k420t/xc7k480t have no high performance banks
ifneq (${XRAY_FABRIC}, $(filter ${XRAY_FABRIC}, xc7k480t))
HAS_HIGH_PERFORMANCE_BANKS = 1
endif
endif

FUZDIR=$(shell pwd)
BUILD_FOLDER=build_${XRAY_PART}
BUILD_DIR=$(FUZDIR)/$(BUILD_FOLDER)
TILEGRID_TDB_DEPENDENCIES=
# High-range (HR) bank I/O tiles
ifeq (${HAS_HIGH_RANGE_BANKS}, 1)
TILEGRID_TDB_DEPENDENCIES += iob/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += iob_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += ioi/$(BUILD_FOLDER)/segbits_tilegrid.tdb
endif
TILEGRID_TDB_DEPENDENCIES += monitor/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += bram/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += bram_block/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += bram_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += clb/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += clb_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += cfg/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += dsp/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += fifo_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += cfg_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += monitor_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += clk_hrow/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += clk_bufg/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += hclk_cmt/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += cmt_upper_b/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += cmt_lower_t/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += pll/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += hclk_ioi/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += mmcm/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += dsp_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
GENERATE_FULL_ARGS=

# Artix7 only fuzzers
ifeq (${XRAY_DATABASE}, artix7)
TILEGRID_TDB_DEPENDENCIES += pcie/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += pcie_int_interface/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += gtp_common/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += gtp_channel/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += gtp_int_interface/$(BUILD_FOLDER)/segbits_tilegrid.tdb
endif

# Zynq7 only fuzzers
ifeq (${XRAY_DATABASE}, zynq7)
TILEGRID_TDB_DEPENDENCIES += ps7_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
ifeq (${XRAY_FABRIC}, $(filter ${XRAY_FABRIC}, xc7z030 xc7z045 xc7z100))
TILEGRID_TDB_DEPENDENCIES += iob18/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += iob18_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += ioi18/$(BUILD_FOLDER)/segbits_tilegrid.tdb
#TILEGRID_TDB_DEPENDENCIES += pcie/$(BUILD_FOLDER)/segbits_tilegrid.tdb
#TILEGRID_TDB_DEPENDENCIES += pcie_int_interface/$(BUILD_FOLDER)/segbits_tilegrid.tdb
# TODO: This has issue with 7030: tdb uncertainty?
#PCIE_INT_INTERFACE_L_X66Y0.DWORD:0.AUTO_FRAME 0044211A_000_00
#PCIE_INT_INTERFACE_R_X63Y0.DWORD:0.AUTO_FRAME <6 candidates>
endif
endif

# High-performance (HP) bank I/O fuzzers.
# Present on Kintex-7 (except xc7k480t) and Virtex-7 VX parts.
ifeq (${HAS_HIGH_PERFORMANCE_BANKS}, 1)
TILEGRID_TDB_DEPENDENCIES += iob18/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += iob18_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb
# iob18_sing is intentionally NOT a tilegrid dependency: SING tiles inherit
# their base address from the parent IOB18 column via propagate_IOB_SING in
# generate_full.py, not via direct measurement. The iob18_sing rule below is
# kept so the build can still be invoked manually as a Vivado-measurement
# guard (its tdb half-aligns at offset+1 - exactly what propagate_IOB_SING's
# top-tile alias models with offset=99).
TILEGRID_TDB_DEPENDENCIES += ioi18/$(BUILD_FOLDER)/segbits_tilegrid.tdb
# GTX transceiver fuzzers. Kintex-7 only: the xc7vx485t-ffg1761 package used for
# virtex7 bonds only ~7 of its 14 GTX quads, so the unbonded GTX_COMMON tiles
# cannot be placed/fuzzed. GTX is therefore skipped for virtex7.
ifneq (${XRAY_DATABASE}, virtex7)
TILEGRID_TDB_DEPENDENCIES += gtx_common/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += gtx_channel/$(BUILD_FOLDER)/segbits_tilegrid.tdb
TILEGRID_TDB_DEPENDENCIES += gtx_int_interface/$(BUILD_FOLDER)/segbits_tilegrid.tdb
endif
endif

# These kintex parts give an empty design
ifeq (${XRAY_DATABASE}, kintex7)
ifneq (${XRAY_FABRIC}, $(filter ${XRAY_FABRIC}, xc7k160t xc7k325t xc7k480t))
TILEGRID_TDB_DEPENDENCIES += orphan_int_column/$(BUILD_FOLDER)/segbits_tilegrid.tdb
endif
endif

BASICDB_TILEGRID=$(BUILD_FOLDER)/basicdb/${XRAY_FABRIC}/tilegrid.json

database: $(BUILD_FOLDER)/tilegrid.json

pushdb: $(BUILD_FOLDER)/tilegrid.json
	cp $(BUILD_FOLDER)/tilegrid.json ${XRAY_FAMILY_DIR}/${XRAY_FABRIC}/tilegrid.json

$(BUILD_FOLDER)/tiles/tiles.txt:
	bash generate.sh $(BUILD_FOLDER)/tiles tiles

${BASICDB_TILEGRID}: generate.py $(BUILD_FOLDER)/tiles/tiles.txt
	mkdir -p $(BUILD_FOLDER)/basicdb/${XRAY_FABRIC}
	ln -sf $(XRAY_DATABASE_DIR)/$(XRAY_DATABASE)/mapping $(BUILD_FOLDER)/basicdb/
	cd $(BUILD_FOLDER) && python3 ${FUZDIR}/generate.py \
		--tiles $(BUILD_DIR)/tiles/tiles.txt \
		--pin_func $(BUILD_DIR)/tiles/pin_func.txt \
		--out ${BUILD_DIR}/basicdb/${XRAY_FABRIC}/tilegrid.json

OKFLAG=run-005.${XRAY_PART}.ok

clb/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd clb && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

clb_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd clb_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

cfg/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd cfg && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

iob/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd iob && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

iob18/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd iob18 && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

iob_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd iob_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

iob18_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd iob18_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

iob18_sing/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd iob18_sing && $(MAKE)

ioi/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd ioi && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

ioi18/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd ioi18 && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

mmcm/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd mmcm && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

pll/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd pll && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

ps7_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd ps7_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

monitor/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd monitor && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

monitor_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd monitor_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

bram/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd bram && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

bram_block/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd bram_block && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

bram_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd bram_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

dsp/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd dsp && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

dsp_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd dsp_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

fifo_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd fifo_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

cfg_int/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd cfg_int && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

orphan_int_column/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd orphan_int_column && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

clk_hrow/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd clk_hrow && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

clk_bufg/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd clk_bufg && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

hclk_cmt/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd hclk_cmt && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

cmt_upper_b/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd cmt_upper_b && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

cmt_lower_t/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd cmt_lower_t && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

hclk_ioi/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd hclk_ioi && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

pcie/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd pcie && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

pcie_int_interface/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd pcie_int_interface && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

gtp_common/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd gtp_common && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

gtp_channel/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd gtp_channel && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

gtp_int_interface/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd gtp_int_interface && test -s ${OKFLAG} || ($(MAKE) && touch ${OKFLAG})

gtx_common/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd gtx_common && $(MAKE)

gtx_channel/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd gtx_channel && $(MAKE)

gtx_int_interface/$(BUILD_FOLDER)/segbits_tilegrid.tdb: ${BASICDB_TILEGRID}
	cd gtx_int_interface && $(MAKE)

$(BUILD_FOLDER)/tilegrid_tdb.json: add_tdb.py $(TILEGRID_TDB_DEPENDENCIES)
	python3 add_tdb.py \
		--fn-in ${BASICDB_TILEGRID} \
		--fn-out $(BUILD_FOLDER)/tilegrid_tdb.json

$(BUILD_FOLDER)/tilegrid.json: generate_full.py $(BUILD_FOLDER)/tilegrid_tdb.json
	cd $(BUILD_FOLDER) && python3 ${FUZDIR}/generate_full.py \
        --json-in tilegrid_tdb.json --json-out ${BUILD_DIR}/tilegrid.json
run:
	$(MAKE) clean_part
	$(MAKE) database
	$(MAKE) pushdb
	touch run.${XRAY_PART}.ok

clean:
	rm -rf build_* run.*.ok
	find . | grep run-005.*.ok | xargs rm -rf
	cd clb && rm run.${XRAY_PART}.ok && $(MAKE) clean
	cd clb_int && $(MAKE) clean
	cd cfg && $(MAKE) clean
	cd iob && $(MAKE) clean
	cd iob18 && $(MAKE) clean
	cd iob_int && $(MAKE) clean
	cd iob18_int && $(MAKE) clean
	cd iob18_sing && $(MAKE) clean
	cd ioi && $(MAKE) clean
	cd ioi18 && $(MAKE) clean
	cd mmcm && $(MAKE) clean
	cd pll && $(MAKE) clean
	cd ps7_int && $(MAKE) clean
	cd bram && $(MAKE) clean
	cd bram_block && $(MAKE) clean
	cd bram_int && $(MAKE) clean
	cd dsp && $(MAKE) clean
	cd dsp_int && $(MAKE) clean
	cd fifo_int && $(MAKE) clean
	cd monitor && $(MAKE) clean
	cd monitor_int && $(MAKE) clean
	cd cfg_int && $(MAKE) clean
	cd orphan_int_column && $(MAKE) clean
	cd clk_hrow && $(MAKE) clean
	cd clk_bufg && $(MAKE) clean
	cd hclk_cmt && $(MAKE) clean
	cd cmt_upper_b && $(MAKE) clean
	cd cmt_lower_t && $(MAKE) clean
	cd hclk_ioi && $(MAKE) clean
	cd pcie && $(MAKE) clean
	cd pcie_int_interface && $(MAKE) clean
	cd gtp_common && $(MAKE) clean
	cd gtp_channel && $(MAKE) clean
	cd gtp_int_interface && $(MAKE) clean
	cd gtx_common && $(MAKE) clean
	cd gtx_channel && $(MAKE) clean
	cd gtx_int_interface && $(MAKE) clean

clean_part:
	find . | grep ${OKFLAG} | xargs rm -rf
	rm -rf $(BUILD_FOLDER) run.${XRAY_PART}.ok
	cd clb && $(MAKE) clean_part
	cd clb_int && $(MAKE) clean_part
	cd cfg && $(MAKE) clean_part
	cd iob && $(MAKE) clean_part
	cd iob18 && $(MAKE) clean_part
	cd iob_int && $(MAKE) clean_part
	cd iob18_int && $(MAKE) clean_part
	cd iob18_sing && $(MAKE) clean_part
	cd ioi && $(MAKE) clean_part
	cd ioi18 && $(MAKE) clean_part
	cd mmcm && $(MAKE) clean_part
	cd pll && $(MAKE) clean_part
	cd ps7_int && $(MAKE) clean_part
	cd bram && $(MAKE) clean_part
	cd bram_block && $(MAKE) clean_part
	cd bram_int && $(MAKE) clean_part
	cd dsp && $(MAKE) clean_part
	cd dsp_int && $(MAKE) clean_part
	cd fifo_int && $(MAKE) clean_part
	cd monitor && $(MAKE) clean_part
	cd monitor_int && $(MAKE) clean_part
	cd cfg_int && $(MAKE) clean_part
	cd orphan_int_column && $(MAKE) clean_part
	cd clk_hrow && $(MAKE) clean_part
	cd clk_bufg && $(MAKE) clean_part
	cd hclk_cmt && $(MAKE) clean_part
	cd cmt_upper_b && $(MAKE) clean_part
	cd cmt_lower_t && $(MAKE) clean_part
	cd hclk_ioi && $(MAKE) clean_part
	cd pcie && $(MAKE) clean_part
	cd pcie_int_interface && $(MAKE) clean_part
	cd gtp_common && $(MAKE) clean_part
	cd gtp_channel && $(MAKE) clean_part
	cd gtp_int_interface && $(MAKE) clean_part
	cd gtx_common && $(MAKE) clean_part
	cd gtx_channel && $(MAKE) clean_part
	cd gtx_int_interface && $(MAKE) clean_part

.PHONY: database pushdb clean clean_part run

