# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# Build one specimen with the routes of routes.txt fixed, then dump what
# generate.py tags from: every routed pip in the CMT_TOP and HCLK_CMT tiles
# (design_pips.txt), and per forced route the mux pip Vivado used
# (forced_check.txt). The tags are read from what Vivado routed.

source "$::env(XRAY_DIR)/utils/cmt_phaser_routes.tcl"

proc dump_pips {filename} {
    set fp [open $filename w]
    foreach net [get_nets -hierarchical -quiet] {
        foreach pip [get_pips -quiet -of_objects $net] {
            set tt [get_property TYPE [get_tiles -of_objects $pip]]
            if {[string match CMT_TOP_* $tt] || [string match HCLK_CMT* $tt]} {
                puts $fp $pip
            }
        }
    }
    close $fp
}

proc check_routes {routes filename} {
    set fp [open $filename w]
    foreach r $routes {
        lassign $r net bufr ctile src mux hclk n m
        set want "$ctile/[get_property TYPE [get_tiles $ctile]].$src->>$mux"
        set got [lsearch -inline -all [get_pips -of_objects [get_nets $net]] "$ctile/*"]
        set ok [expr {[lsearch $got $want] >= 0}]
        puts $fp "$net $ctile $src $mux status=[get_property ROUTE_STATUS [get_nets $net]] ok=$ok"
    }
    close $fp
}

proc run {} {
    create_project -force -part $::env(XRAY_PART) design design
    read_verilog top.v
    synth_design -top top

    set_property CFGBVS VCCO [current_design]
    set_property CONFIG_VOLTAGE 3.3 [current_design]
    set_property BITSTREAM.GENERAL.PERFRAMECRC YES [current_design]
    # The ports are not constrained: only the CMT column's bits matter.
    set_property SEVERITY {Warning} [get_drc_checks NSTD-1]
    set_property SEVERITY {Warning} [get_drc_checks UCIO-1]
    # The BUFMRs are fed from a fabric flop.
    set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets]

    set routes [read_routes]
    place_bufrs $routes
    place_design
    fix_routes $routes
    route_design

    dump_pips design_pips.txt
    check_routes $routes forced_check.txt

    write_checkpoint -force design.dcp
    write_bitstream -force design.bit
}

run
