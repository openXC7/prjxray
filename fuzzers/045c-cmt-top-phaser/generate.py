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
"""Tag the CMT_TOP_*_UPPER_B / *_LOWER_T tiles from what Vivado routed.

Per PHASER_IN of a tile, two kinds of tag:
- the route-through, CMT_PHASER_IN_<CA|DB>_RCLK.CMT_PHASER_IN_<CA|DB>_PHASEREFCLK:
  1 when a route went through that PHASER_IN, else 0;
- every input of its reference mux, <mux wire>.<input wire>: 1 when the
  route took that input, else 0.
"""
import json
import os
import re
import sys

from prjxray.db import Database
from prjxray.segmaker import Segmaker
from prjxray import util

PIP_RE = re.compile(r"^([^/]+)/[^.]+\.(.+?)->>?(.+)$")
MUX_RE = re.compile(r"^CMT_PHASERREF(?:_DOWN)?_PHASERIN_[ABCD]$")
RT_RE = re.compile(r"^CMT_PHASER_IN_(CA|DB)_PHASEREFCLK$")


def parse_pips(path):
    used = {}
    with open(path) as f:
        for line in f:
            m = PIP_RE.match(line.strip())
            if m:
                used.setdefault(m.group(1), set()).add((m.group(2), m.group(3)))
    return used


def tile_pips(tile_type):
    """(src, dst) of the reference-mux and route-through pips of a tile type."""
    fn = os.path.join(util.get_db_root(), "tile_type_{}.json".format(tile_type))
    with open(fn) as f:
        pips = json.load(f)["pips"]
    muxes, rts = [], []
    for p in pips.values():
        src, dst = p["src_wire"], p["dst_wire"]
        if MUX_RE.match(dst):
            muxes.append((src, dst))
        elif RT_RE.match(src) and dst == src.replace("_PHASEREFCLK", "_RCLK"):
            rts.append((src, dst))
    return sorted(muxes), sorted(rts)


def main():
    segmk = Segmaker("design.bits")
    used = parse_pips("design_pips.txt")
    db = Database(util.get_db_root(), util.get_part())
    grid = db.grid()
    cache = {}
    ones = 0
    for tile_name in grid.tiles():
        gi = grid.gridinfo_at_tilename(tile_name)
        tt = gi.tile_type
        if not (tt.startswith("CMT_TOP_") and tt.endswith(("_UPPER_B", "_LOWER_T"))):
            continue
        if tt not in cache:
            cache[tt] = tile_pips(tt)
        muxes, rts = cache[tt]
        tile_used = used.get(tile_name, set())
        for src, dst in muxes + rts:
            val = 1 if (src, dst) in tile_used else 0
            segmk.add_tile_tag(tile_name, "{}.{}".format(dst, src), val)
            ones += val
    print("tags set: {}".format(ones), file=sys.stderr)

    # The PHASER_IN bits are in frames 28 and 29 of the column.
    def bitfilter(frame, bit):
        return frame >= 26

    segmk.compile(bitfilter=bitfilter)
    segmk.write(allow_empty=True)


if __name__ == "__main__":
    main()
