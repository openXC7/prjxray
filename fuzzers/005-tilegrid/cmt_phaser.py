#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
"""Shared top.py of cmt_upper_b and cmt_lower_t.

The CMT_TOP_*_UPPER_B and *_LOWER_T tiles hold the PHASER sites and have no
cell this fuzzer can configure simply, but a BUFMR's route to a BUFR goes
through one of their PHASER_INs. Each PHASER_IN's reference input is a mux:
"own region, input 0" sets one bit, "own region, input 1" sets that bit and
one more. So in every clock region two BUFMRs drive two BUFRs, through the
tile's two PHASER_INs, and the toggle only swaps which BUFMR feeds which:

  isone: BUFMR site 1 -> 1st PHASER_IN, BUFMR site 0 -> 2nd PHASER_IN
  else:  BUFMR site 0 -> 1st PHASER_IN, BUFMR site 1 -> 2nd PHASER_IN

That changes one bit in each PHASER_IN's mux, and nothing else in the CMT
frames: the 1st PHASER_IN's "input 1" bit is set exactly when isone, the
2nd's exactly when not. segmatch (without -i) only reports the first, at
frame 0x1C, bit 27: word 59 of the column for UPPER_B (PHASER_IN C), word 38
for LOWER_T (PHASER_IN A). generate.tcl fixes the routes in routes.txt.

CMT_HALF selects the tile type: "upper" (UPPER_B, PHASER_IN C and D, RCLK2
and RCLK3) or "lower" (LOWER_T, PHASER_IN A and B, RCLK0 and RCLK1).
"""
import os
import random
random.seed(int(os.getenv("SEED"), 16))
from prjxray import util
from prjxray.db import Database

HALF = os.environ["CMT_HALF"]
if HALF == "upper":
    TILE_SUFFIX = "_UPPER_B"
    SRC = "CMT_PHASER_UP_PHASERREF%d"
    MUX = ["CMT_PHASERREF_PHASERIN_C", "CMT_PHASERREF_PHASERIN_D"]
    RCLK = [2, 3]
else:
    TILE_SUFFIX = "_LOWER_T"
    SRC = "CMT_PHASER_DOWN_PHASERREF%d"
    MUX = ["CMT_PHASERREF_DOWN_PHASERIN_A", "CMT_PHASERREF_DOWN_PHASERIN_B"]
    RCLK = [0, 1]
# The PERFCLK each PHASER_IN's route takes to its BUFR.
PERFCLK = [0, 1]


def gen_regions():
    """(HCLK_CMT tile, its two BUFMRCE sites, the CMT_TOP tile)."""
    db = Database(util.get_db_root(), util.get_part())
    grid = db.grid()
    cmt = {}
    hclks = []
    for tile_name in sorted(grid.tiles()):
        gi = grid.gridinfo_at_tilename(tile_name)
        loc = grid.loc_of_tilename(tile_name)
        if gi.tile_type.startswith("CMT_TOP_") and gi.tile_type.endswith(TILE_SUFFIX):
            cmt.setdefault(loc.grid_x, []).append((loc.grid_y, tile_name))
        bufmrs = sorted(s for s, t in gi.sites.items() if t == "BUFMRCE")
        if len(bufmrs) == 2:
            hclks.append((tile_name, loc, bufmrs))
    for tile_name, loc, bufmrs in hclks:
        col = cmt.get(loc.grid_x, [])
        if not col:
            continue
        # The tile of this type nearest to the HCLK_CMT is in its region.
        _, ctile = min((abs(y - loc.grid_y), t) for y, t in col)
        yield tile_name, bufmrs, ctile


def run():
    regions = list(gen_regions())
    params = {}
    routes = []
    body = []
    for (hclk, bufmrs, ctile), isone in zip(regions,
                                            util.gen_fuzz_states(len(regions))):
        params[ctile] = (hclk, isone)
        # which BUFMR site feeds the 1st and the 2nd PHASER_IN
        order = [1, 0] if isone else [0, 1]
        for k in range(2):
            body.append(
                '''
    wire m_{site};
    (* KEEP, DONT_TOUCH, LOC = "{site}" *)
    BUFMR bm_{site} (.I(t), .O(m_{site}));'''.format(site=bufmrs[k]))
        for p in range(2):
            site = bufmrs[order[p]]
            bufr = "br_%s_%d" % (hclk, p)
            body.append(
                '''
    wire r_{bufr};
    (* KEEP, DONT_TOUCH *)
    BUFR #(.BUFR_DIVIDE("BYPASS")) {bufr} (.I(m_{site}), .O(r_{bufr}), .CE(1'b1), .CLR(1'b0));
    reg q_{bufr} = 1'b0;
    always @(posedge r_{bufr}) q_{bufr} <= ~q_{bufr};
    assign q[{i}] = q_{bufr};'''.format(bufr=bufr, site=site, i=len(routes)))
            routes.append((
                "m_" + site, bufr, ctile, SRC % order[p], MUX[p], hclk, RCLK[p],
                PERFCLK[p]))
    print('''
module top(input clk, output o);
    reg t = 1'b0;
    always @(posedge clk) t <= ~t;
    wire [{n}:0] q;'''.format(n=max(len(routes) - 1, 0)))
    print("".join(body))
    print('''
    assign o = ^q;
endmodule''')
    with open("routes.txt", "w") as f:
        for r in routes:
            f.write(" ".join(str(x) for x in r) + "\n")
    with open("params.csv", "w") as f:
        f.write("tile,val,site\n")
        for tile, (hclk, val) in sorted(params.items()):
            f.write("%s,%s,%s\n" % (tile, val, hclk))


if __name__ == "__main__":
    run()
