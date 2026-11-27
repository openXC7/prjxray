# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# Shared generate.tcl of cmt_upper_b and cmt_lower_t; the routes are
# fixed by utils/cmt_phaser_routes.tcl.

source "$::env(XRAY_DIR)/utils/cmt_phaser_routes.tcl"

proc run {} {
    create_project -force -part $::env(XRAY_PART) design design
    read_verilog top.v
    synth_design -top top

    set_property CFGBVS VCCO [current_design]
    set_property CONFIG_VOLTAGE 3.3 [current_design]
    set_property BITSTREAM.GENERAL.PERFRAMECRC YES [current_design]
    # The ports are not constrained: only the CMT column's bits matter here.
    set_property SEVERITY {Warning} [get_drc_checks NSTD-1]
    set_property SEVERITY {Warning} [get_drc_checks UCIO-1]
    # The BUFMRs are fed from a fabric flop.
    set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets]

    set routes [read_routes]
    place_bufrs $routes
    place_design
    fix_routes $routes
    route_design

    write_checkpoint -force design.dcp
    write_bitstream -force design.bit
}

run
