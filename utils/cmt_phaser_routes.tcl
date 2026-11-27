# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
#
# Fixed BUFMR -> PHASER_IN -> BUFR routes, for the fuzzers of the CMT_TOP
# PHASER tiles (005-tilegrid's cmt_upper_b / cmt_lower_t, and 045c).
# routes.txt has, per line:
#   <BUFMR net> <BUFR cell> <CMT_TOP tile> <mux source wire> <mux output wire>
#   <HCLK_CMT tile> <RCLK n> <PERFCLK m>
# place_bufrs puts each BUFR in its HCLK_CMT tile's clock region, on a site
# that PERFCLK m reaches; fix_routes fixes each BUFMR net's route through
# the named mux input, PHASER_IN, RCLK and PERFCLK.

proc node_of_wire {w} {
    set n [get_nodes -quiet -of_objects [get_wires -quiet $w]]
    if {$n eq ""} { error "no wire $w" }
    return $n
}

proc read_routes {} {
    set routes {}
    set fp [open routes.txt r]
    while {[gets $fp line] >= 0} {
        if {[string trim $line] ne ""} { lappend routes $line }
    }
    close $fp
    return $routes
}

proc place_bufrs {routes} {
    set used {}
    foreach r $routes {
        lassign $r net bufr ctile src mux hclk n m
        set region [get_property CLOCK_REGION [lindex [get_sites -of_objects [get_tiles $hclk]] 0]]
        set n_perf [node_of_wire "$hclk/HCLK_CMT_MUX_PHSR_PERFCLK$m"]
        set site ""
        foreach s [lsort [get_sites -quiet -filter "SITE_TYPE == BUFR && CLOCK_REGION == $region"]] {
            if {[lsearch $used $s] >= 0} { continue }
            if {[find_routing_path -quiet -from $n_perf -to [get_nodes -of_objects [get_site_pins $s/I]]] ne ""} {
                set site $s
                break
            }
        }
        if {$site eq ""} { error "no BUFR in $region reachable from $hclk PERFCLK$m" }
        lappend used $site
        set_property LOC $site [get_cells $bufr]
    }
}

proc fix_routes {routes} {
    foreach r $routes {
        lassign $r net bufr ctile src mux hclk n m
        set bufmr [get_sites -of_objects [get_cells -of_objects [get_pins -leaf -filter {DIRECTION == OUT} -of_objects [get_nets $net]]]]
        set bufr_site [get_sites -of_objects [get_cells $bufr]]
        set hops [list \
            [get_nodes -of_objects [get_site_pins $bufmr/O]] \
            [node_of_wire "$ctile/$src"] \
            [node_of_wire "$ctile/$mux"] \
            [node_of_wire "$hclk/HCLK_CMT_PHASERIN_RCLK$n"] \
            [node_of_wire "$hclk/HCLK_CMT_MUX_PHSR_PERFCLK$m"] \
            [get_nodes -of_objects [get_site_pins $bufr_site/I]]]
        set route {}
        for {set i 0} {$i < [llength $hops] - 1} {incr i} {
            set seg [find_routing_path -quiet -from [lindex $hops $i] -to [lindex $hops [expr {$i + 1}]]]
            if {$seg eq ""} { error "no path for $net from [lindex $hops $i] to [lindex $hops [expr {$i + 1}]]" }
            if {$route eq ""} { set route $seg } else { set route [concat $route [lrange $seg 1 end]] }
        }
        set_property FIXED_ROUTE $route [get_nets $net]
    }
}
