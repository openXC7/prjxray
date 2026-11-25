# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# Build one specimen, then dump what generate.py tags from: the BUFMR
# cells' sites and properties, and the used pips of the HCLK_CMT tiles.
# The tags are read from what Vivado placed and routed, not from what
# top.py asked for, so these dumps are part of the measurement.

proc dump_bufmrs {filename} {
    set fp [open $filename w]
    foreach c [get_cells -quiet -hierarchical -filter {REF_NAME =~ BUFMR*}] {
        set ce_net [get_nets -quiet -of_objects [get_pins -quiet $c/CE]]
        set ce_driver ""
        if {$ce_net ne ""} {
            set ce_driver [get_property REF_NAME [get_cells -quiet -of_objects \
                [get_pins -quiet -leaf -of_objects $ce_net -filter {DIRECTION == OUT}]]]
        }
        # A CE tied to a constant is folded away by Vivado (BUFMR and
        # BUFMRCE CE=1 give identical bitstreams); record what drives it.
        puts $fp [list \
            [get_property NAME $c] \
            [get_sites -quiet -of_objects $c] \
            [get_property REF_NAME $c] \
            [get_property -quiet CE_TYPE $c] \
            [get_property -quiet INIT_OUT $c] \
            [get_property -quiet IS_CE_INVERTED $c] \
            $ce_driver \
            [get_property -quiet ROUTE_STATUS [get_nets -quiet -of_objects [get_pins -quiet $c/O]]]]
    }
    close $fp
}

proc dump_hclk_cmt_pips {filename} {
    set fp [open $filename w]
    foreach net [get_nets -quiet -hierarchical] {
        foreach pip [get_pips -quiet -of_objects $net] {
            if {[regexp {^HCLK_CMT} $pip]} {
                puts $fp "$pip"
            }
        }
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

    # Fabric- and BUFG-fed BUFMRs are not on a dedicated clock route.
    set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets]

    place_design
    route_design

    dump_bufmrs bufmr_sites.txt
    dump_hclk_cmt_pips design_pips.txt

    write_checkpoint -force design.dcp
    write_bitstream -force design.bit
}

run
