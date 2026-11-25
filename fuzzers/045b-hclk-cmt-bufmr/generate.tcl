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

# FUZZ_MODE=onehot_perf: top.py lists, per line,
#   <net> <HCLK_CMT tile> <RCLK n> <PERFCLK m> <BUFR site>
# and the net's route is fixed before route_design through that tile's
# HCLK_CMT_PHASERIN_RCLK<n> and HCLK_CMT_MUX_PHSR_PERFCLK<m> wires:
# BUFMRCE/O -> RCLK<n> -> PERFCLK<m> -> BUFR/I. A pair Vivado finds no path
# for is logged and left to the router, not an error: which pairs exist is
# part of what the specimens measure.
proc force_phsr_routes {filename} {
    if {![file exists $filename]} {
        return
    }
    set fp [open $filename r]
    set log [open forced_routes.txt w]
    while {[gets $fp line] >= 0} {
        if {[string trim $line] eq ""} { continue }
        lassign $line netname tile n m bufr
        set net [get_nets $netname]
        set n0 [get_nodes -of_objects [get_site_pins -filter {DIRECTION == OUT} -of_objects $net]]
        set n1 [get_nodes -of_objects [get_wires "$tile/HCLK_CMT_PHASERIN_RCLK$n"]]
        set n2 [get_nodes -of_objects [get_wires "$tile/HCLK_CMT_MUX_PHSR_PERFCLK$m"]]
        set n3 [get_nodes -of_objects [get_site_pins "$bufr/I"]]
        set r1 [find_routing_path -quiet -from $n0 -to $n1]
        set r2 [find_routing_path -quiet -from $n1 -to $n2]
        set r3 [find_routing_path -quiet -from $n2 -to $n3]
        if {$r1 eq "" || $r2 eq "" || $r3 eq ""} {
            puts $log "$netname $tile RCLK$n PERFCLK$m $bufr no_path r1=[llength $r1] r2=[llength $r2] r3=[llength $r3]"
            continue
        }
        set route [concat $r1 [lrange $r2 1 end] [lrange $r3 1 end]]
        set_property FIXED_ROUTE $route $net
        puts $log "$netname $tile RCLK$n PERFCLK$m $bufr fixed $route"
    }
    close $fp
    close $log
}

# What Vivado routed for each forced net: its PHASERIN -> PHSR_PERFCLK pips.
proc check_forced_routes {filename} {
    if {![file exists forced.txt]} {
        return
    }
    set fp [open forced.txt r]
    set out [open $filename w]
    while {[gets $fp line] >= 0} {
        if {[string trim $line] eq ""} { continue }
        lassign $line netname tile n m bufr
        set net [get_nets $netname]
        set hit {}
        foreach pip [get_pips -quiet -of_objects $net] {
            if {[regexp {HCLK_CMT_PHASERIN_RCLK[0-9]->>HCLK_CMT_MUX_PHSR_PERFCLK[0-9]$} $pip]} {
                lappend hit $pip
            }
        }
        puts $out "$netname want=RCLK$n->PERFCLK$m status=[get_property ROUTE_STATUS $net] got=$hit"
    }
    close $fp
    close $out
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
    force_phsr_routes forced.txt
    route_design
    check_forced_routes forced_check.txt

    dump_bufmrs bufmr_sites.txt
    dump_hclk_cmt_pips design_pips.txt

    write_checkpoint -force design.dcp
    write_bitstream -force design.bit
}

run
