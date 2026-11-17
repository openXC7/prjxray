# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
SELF_DIR := $(dir $(lastword $(MAKEFILE_LIST)))

# Developer options for quicker runs
# Run algorithm, but only a small number of iterations
QUICK=N
# Skip metadata steps like tile and part generation
# Ex: FUZZONLY=N: 30 min, FUZZONLY=Y: 6 min
FUZZONLY=N
# 074 fuzzer isn't changed often and is slow
# Allow building without it
BITONLY=N

all:
clean: clean_fuzzers clean_piplists clean_logs clean_locks

clean_locks:
	rm -rf /tmp/segbits_*.db.lock

clean_piplists:
	rm -rf $(XRAY_FUZZERS_DIR)/piplist/build

fuzzer_ok:
	mkdir -p fuzzer_ok

clean_fuzzers::
	rm -rf fuzzer_ok

define fuzzer

# $(1) - Fuzzer name/directory
# $(2) - Space seperated list of dependencies for the fuzzer.
# $(3) - Is this fuzzer setting specific? Should be either "part" or "all"

# Make the all target depend on the run.ok file for the fuzzer.
ifeq ($(3),part)
all: $(1)/run.$(XRAY_PART).ok
part_only: $(1)/run.$(XRAY_PART).ok
else
all: $(1)/run.ok
endif

# Make the clean target run `make clean` in the fuzzer's directory.
clean_fuzzers::
	$$(MAKE) -C $(1) clean

clean_logs::
	rm -rf $(1)/logs_*

# Describe how to create the fuzzer's run.ok file.
# This command must start with a + to tell make to pass the jobserver
# parameters downwards.

ifeq ($(3),part)
$(1)/run.$(XRAY_PART).ok: $(addsuffix _$(XRAY_PART).ok,$(addprefix fuzzer_ok/fuzzer_, $(2)))
else
$(1)/run.ok: $(addsuffix _$(XRAY_PART).ok,$(addprefix fuzzer_ok/fuzzer_, $(2)))
endif
ifeq ($(VERBOSE),Y)
# When verbose we just call make directory
	$$(MAKE) -C $(1) run
else
# When not verbose, we use the run_fuzzer wrapper which will save the results
# to log files.
	+@$(SELF_DIR)/run_fuzzer.py $(1)
endif

ifeq ($(3),part)
fuzzer_ok/fuzzer_$(1)_$(XRAY_PART).ok: $(1)/run.$(XRAY_PART).ok | fuzzer_ok
else
fuzzer_ok/fuzzer_$(1)_$(XRAY_PART).ok: $(1)/run.ok | fuzzer_ok
endif
	touch fuzzer_ok/fuzzer_$(1)_$(XRAY_PART).ok

.PHONY: fuzzer_$(1)

fuzzer_$(1): fuzzer_ok/fuzzer_$(1)_$(XRAY_PART).ok

endef

SKIP_DSP=0
HAS_PCIE=0
HAS_GTP=0
HAS_HIGH_PERFORMANCE_BANKS=0
ifneq (,$(filter $(XRAY_DATABASE),kintex7 virtex7))
HAS_HIGH_PERFORMANCE_BANKS=1
else
ifeq ($(XRAY_DATABASE),artix7)
HAS_PCIE=1
HAS_GTP=1
else
ifeq (${XRAY_FABRIC}, $(filter ${XRAY_FABRIC}, xc7z030 xc7z045 xc7z100))
HAS_HIGH_PERFORMANCE_BANKS=1
# DSP fuzzer gives error on 7030, need to make sure 7020/7010 runs before 7030, and use their results
SKIP_DSP=1 
# PCIE hard block: can only use after GTX support comes
HAS_PCIE=0
endif
endif
endif
# Virtex-7 "VX" parts are high-performance-bank only (no IOB33/IOI3 HR tiles),
# so the HR-bank IOB/IOI fuzzers have no sites to target there. The HP (iob18/
# ioi18) fuzzers cover those parts instead.
ifeq ($(XRAY_DATABASE),virtex7)
HAS_HIGH_RANGE_BANKS=0
else
HAS_HIGH_RANGE_BANKS=1
endif
$(eval $(call fuzzer,000-init-db,,part))

ifneq ($(FUZZONLY),Y)
$(eval $(call fuzzer,001-part-yaml,000-init-db,part))
$(eval $(call fuzzer,005-tilegrid,001-part-yaml,part))
else
all:: 005-tilegrid/run.ok
	touch 005-tilegrid/run.ok
endif

ifeq (,$(filter $(XRAY_DATABASE),kintex7 virtex7))
$(eval $(call fuzzer,007-timing,005-tilegrid,all))
endif
$(eval $(call fuzzer,010-clb-lutinit,005-tilegrid,all))
$(eval $(call fuzzer,011-clb-ffconfig,005-tilegrid,all))
$(eval $(call fuzzer,012-clb-n5ffmux,005-tilegrid,all))
$(eval $(call fuzzer,013-clb-ncy0,005-tilegrid,all))
$(eval $(call fuzzer,014-clb-ffsrcemux,005-tilegrid,all))
$(eval $(call fuzzer,015-clb-nffmux,005-tilegrid,all))
$(eval $(call fuzzer,016-clb-noutmux,005-tilegrid,all))
$(eval $(call fuzzer,017-clb-precyinit,005-tilegrid,all))
# 018-clb-ram (distributed RAM / SRL): works on virtex7 once generate.py skips
# slices placed outside the dumped pblock (the grid-ROI yields a SLICE column
# just past the XRAY_ROI box); see the graceful-skip in generate.py.
$(eval $(call fuzzer,018-clb-ram,005-tilegrid,all))
$(eval $(call fuzzer,019-clb-ndi1mux,005-tilegrid,all))
$(eval $(call fuzzer,025-bram-config,005-tilegrid,all))
$(eval $(call fuzzer,026-bram-data,005-tilegrid,all))
$(eval $(call fuzzer,027-bram36-config,005-tilegrid,all))
$(eval $(call fuzzer,028-fifo-config,005-tilegrid,all))
$(eval $(call fuzzer,029-bram-fifo-config,005-tilegrid,all))
ifeq ($(HAS_HIGH_RANGE_BANKS),1)
$(eval $(call fuzzer,030-iob,005-tilegrid,all))
endif
ifeq ($(HAS_HIGH_PERFORMANCE_BANKS),1)
$(eval $(call fuzzer,030-iob18,005-tilegrid,all))
endif
$(eval $(call fuzzer,031-cmt-mmcm,005-tilegrid,all))
$(eval $(call fuzzer,032-cmt-pll,005-tilegrid,all))
$(eval $(call fuzzer,034-cmt-pll-pips,005-tilegrid 071-ppips,all))
ifeq (,$(filter $(XRAY_DATABASE),kintex7 virtex7))
# FIXME: 034b fuzzer is generating conflicting bits around the FREQ_BB[N] bits.
# The fuzzer can be re-enabled once the conflicting bits are not generated anymore
$(eval $(call fuzzer,034b-cmt-mmcm-pips,005-tilegrid 071-ppips,all))
endif
ifeq ($(HAS_HIGH_RANGE_BANKS),1)
$(eval $(call fuzzer,035-iob-ilogic,005-tilegrid,all))
$(eval $(call fuzzer,035a-iob-idelay,005-tilegrid,all))
endif
ifeq ($(HAS_HIGH_PERFORMANCE_BANKS),1)
$(eval $(call fuzzer,035a-iob18-idelay,005-tilegrid,all))
$(eval $(call fuzzer,035a-iob18-odelay,005-tilegrid,all))
endif
ifeq ($(HAS_HIGH_RANGE_BANKS),1)
$(eval $(call fuzzer,035b-iob-iserdes,005-tilegrid,all))
$(eval $(call fuzzer,036-iob-ologic,005-tilegrid,all))
endif
ifeq ($(HAS_HIGH_PERFORMANCE_BANKS),1)
$(eval $(call fuzzer,036-iob18-ologic,005-tilegrid,all))
endif
ifeq ($(HAS_HIGH_RANGE_BANKS),1)
$(eval $(call fuzzer,037-iob-pips,005-tilegrid 035b-iob-iserdes,all))
endif
ifeq ($(HAS_HIGH_PERFORMANCE_BANKS),1)
# 035b-iob-iserdes is HR-only; on HP-only parts 037-iob18-pips runs without it.
$(eval $(call fuzzer,037-iob18-pips,005-tilegrid $(if $(filter 1,$(HAS_HIGH_RANGE_BANKS)),035b-iob-iserdes),all))
endif
$(eval $(call fuzzer,038-cfg,005-tilegrid,all))
$(eval $(call fuzzer,038-cfg-startup,005-tilegrid,all))
$(eval $(call fuzzer,039-hclk-config,005-tilegrid,all))
$(eval $(call fuzzer,040-clk-hrow-config,005-tilegrid,all))
$(eval $(call fuzzer,041-clk-hrow-pips,005-tilegrid,all))
$(eval $(call fuzzer,042-clk-bufg-config,005-tilegrid,all))
$(eval $(call fuzzer,043-clk-rebuf-pips,005-tilegrid,all))
$(eval $(call fuzzer,044-clk-bufg-pips,046-clk-bufg-muxed-pips,all))
$(eval $(call fuzzer,045-hclk-cmt-pips,005-tilegrid,all))
$(eval $(call fuzzer,046-clk-bufg-muxed-pips,005-tilegrid,all))
ifeq ($(HAS_HIGH_RANGE_BANKS),1)
$(eval $(call fuzzer,047-hclk-ioi-pips,005-tilegrid,all))
endif
ifeq ($(HAS_HIGH_PERFORMANCE_BANKS),1)
$(eval $(call fuzzer,047-hclk-ioi18-pips,005-tilegrid,all))
endif
# 047a depends on the hclk-ioi pips fuzzer: use the HR one if present, else HP.
ifeq ($(HAS_HIGH_RANGE_BANKS),1)
$(eval $(call fuzzer,047a-hclk-idelayctrl-pips,047-hclk-ioi-pips,all))
else
$(eval $(call fuzzer,047a-hclk-idelayctrl-pips,047-hclk-ioi18-pips,all))
endif
$(eval $(call fuzzer,048-int-piplist,005-tilegrid,all))
$(eval $(call fuzzer,049-int-imux-gfan,048-int-piplist,all))
$(eval $(call fuzzer,050-pip-seed,048-int-piplist,all))
$(eval $(call fuzzer,051-pip-imuxlout-bypalts,048-int-piplist,all))
$(eval $(call fuzzer,052-pip-clkin,048-int-piplist,all))
$(eval $(call fuzzer,053-pip-ctrlin,048-int-piplist,all))
$(eval $(call fuzzer,054-pip-fan-alt,048-int-piplist,all))
$(eval $(call fuzzer,055-pip-gnd,048-int-piplist,all))
$(eval $(call fuzzer,056-pip-rem,049-int-imux-gfan 050-pip-seed 051-pip-imuxlout-bypalts 052-pip-clkin 053-pip-ctrlin 054-pip-fan-alt 055-pip-gnd 059-pip-byp-bounce,all))
$(eval $(call fuzzer,057-pip-bi,056-pip-rem,all))
ifneq ($(QUICK),Y)
$(eval $(call fuzzer,058-pip-hclk,005-tilegrid,all))
# 039a needs the HCLK_IOI3 / IOB33 tiles of a high-range bank, and merges
# into files 045 and 058 own, so it runs after both.
ifeq ($(HAS_HIGH_RANGE_BANKS),1)
$(eval $(call fuzzer,039a-hclk-bufrclk-perfclk,005-tilegrid 045-hclk-cmt-pips 058-pip-hclk,all))
endif
$(eval $(call fuzzer,059-pip-byp-bounce,048-int-piplist,all))
$(eval $(call fuzzer,060-bram-cascades,005-tilegrid,all))
$(eval $(call fuzzer,071-ppips,057-pip-bi 058-pip-hclk 060-bram-cascades,all))
ifneq ($(BITONLY),Y)
$(eval $(call fuzzer,072-ordered_wires,,part))
$(eval $(call fuzzer,073-get_counts,,part))
$(eval $(call fuzzer,074-dump_all,005-tilegrid 072-ordered_wires,part))
$(eval $(call fuzzer,075-pins,,part))
ifeq ($(XRAY_DATABASE),zynq7)
$(eval $(call fuzzer,076-ps7,,all))
endif
ifeq ($(HAS_PCIE),1)
$(eval $(call fuzzer,061-pcie-conf,005-tilegrid,all))
$(eval $(call fuzzer,062-pcie-int-pips,005-tilegrid,all))
endif
ifeq ($(HAS_GTP),1)
$(eval $(call fuzzer,063-gtp-common-conf,005-tilegrid,part))
$(eval $(call fuzzer,064-gtp-channel-conf,005-tilegrid,part))
$(eval $(call fuzzer,065-gtp-common-pips,005-tilegrid,part))
$(eval $(call fuzzer,065b-gtp-common-pips,005-tilegrid,part))
$(eval $(call fuzzer,066-gtp-int-pips,005-tilegrid,all))
endif
# GTX transceiver config fuzzers. Kintex-7 only: the virtex7 package
# (xc7vx485t-ffg1761) bonds only ~7 of 14 GTX quads, so GTX is skipped there.
ifeq ($(XRAY_DATABASE),kintex7)
$(eval $(call fuzzer,063-gtx-common-conf,005-tilegrid,part))
$(eval $(call fuzzer,064-gtx-channel-conf,005-tilegrid,part))
endif
endif
endif
$(eval $(call fuzzer,100-dsp-mskpat,005-tilegrid,all))
$(eval $(call fuzzer,100-dsp-mskpat-selpat-c,005-tilegrid,all))
ifneq ($(SKIP_DSP),1)
$(eval $(call fuzzer,101-dsp-pips,005-tilegrid,all))
endif

quick:
	$(MAKE) QUICK=Y

# Part only targets
# -----------------

# roi_only runs the fuzzers required for supporting additional parts when building
# a roi harness.
roi_only: 000-init-db/run.${XRAY_PART}.ok 001-part-yaml/run.${XRAY_PART}.ok 075-pins/run.${XRAY_PART}.ok

.PHONY: all clean clean_fuzzers clean_logs quick part_only roi_only
