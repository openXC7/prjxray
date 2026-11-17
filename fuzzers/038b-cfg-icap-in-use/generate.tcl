# Copyright (C) 2017-2020  The Project X-Ray Authors
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# No pblock and no I/O: the design is only STARTUPE2 (for CFGMCLK) plus an
# optional ICAPE2.  Everything that matters is inside the CFG_CENTER_MID
# tile, so the place and route of the rest of the device is irrelevant.
create_project -force -part $::env(XRAY_PART) design design
read_verilog top.v
synth_design -top top

set_property BITSTREAM.GENERAL.PERFRAMECRC YES [current_design]

place_design
route_design

write_bitstream -force design.bit
