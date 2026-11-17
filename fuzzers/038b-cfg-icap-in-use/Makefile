# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
N = 3
include ../fuzzer.mk

database: build/segbits_cfg_center_mid.rdb
	${XRAY_DBFIXUP} --db-root build --zero-db bits.dbf \
                --seg-fn-in build/segbits_cfg_center_mid.rdb \
                --seg-fn-out build/segbits_cfg_center_mid.db

build/segbits_cfg_center_mid.rdb: $(SPECIMENS_OK)
	${XRAY_SEGMATCH} -c 15 -o build/segbits_cfg_center_mid.rdb \
		$$(find -name segdata_cfg_center_mid.txt)

pushdb:
	${XRAY_MERGEDB} cfg_center_mid build/segbits_cfg_center_mid.db

.PHONY: database pushdb
