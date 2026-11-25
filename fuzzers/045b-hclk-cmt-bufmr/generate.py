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
#
# Segmaker for the BUFMRCE sites of HCLK_CMT / HCLK_CMT_L and the pips
# around them. Every tag is read from generate.tcl's dumps of what Vivado
# placed and routed:
#
#   HCLK_CMT_BUFMR_INP<n>.<src>
#       the pips into a BUFMRCE input, from design_pips.txt.
#   HCLK_CMT_MUX_PHSR_PERFCLK<m>.HCLK_CMT_PHASERIN_RCLK<n>
#       the PHASER_IN side of the performance-clock mux, which a BUFMR
#       driving a BUFR goes through. 039a tags the MMCM_MUXED side of the
#       same mux; this fuzzer tags both, from the same pip dump, so its
#       specimens (which have no MMCM) say the MMCM positions are off.
#   BUFMRCE.BUFMRCE_X0Y<n>.IN_USE
#       1 when a BUFMR cell is on that site and its output is routed, 0
#       when no cell is on it. A cell that is placed but drives nothing
#       (neg_unconsumed) gets no IN_USE tag; README.md says why.
#   BUFMRCE.BUFMRCE_X0Y<n>.ZINV_CE / .CE_TYPE.ASYNC / .INIT_OUT
#       only for a BUFMRCE whose CE is driven from the fabric, and 0 on an
#       unused site. With a constant CE Vivado folds the CE away (a BUFMR
#       and a BUFMRCE with CE tied active give identical bitstreams), so
#       those cells get none of these tags.
import json
import os
import re
import sys

from prjxray.db import Database
from prjxray.segmaker import Segmaker
from prjxray import util

XY_BUFMR = util.create_xy_fun("BUFMRCE_")
PIP_RE = re.compile(r"^([^/]+)/[^.]+\.(.+?)->>?(.+)$")


def parse_pips(path):
    """{tile: set((src, dst))} from design_pips.txt."""
    used = {}
    with open(path) as f:
        for line in f:
            m = PIP_RE.match(line.strip())
            if m:
                used.setdefault(m.group(1), set()).add((m.group(2), m.group(3)))
    return used


def parse_tcl_list(line):
    """One `puts [list ...]` line of plain words; {} is an empty word."""
    return ["" if w == "{}" else w for w in line.split()]


def parse_bufmrs(path):
    """{site: dict} from bufmr_sites.txt."""
    out = {}
    with open(path) as f:
        for line in f:
            w = parse_tcl_list(line.strip())
            if not w:
                continue
            name, site, ref, ce_type, init_out, inv, ce_drv, status = (
                w + [""] * 8)[:8]
            out[site] = {
                "name": name,
                "ref": ref,
                "CE_TYPE": ce_type,
                "INIT_OUT": init_out,
                "IS_CE_INVERTED": inv,
                "ce_driver": ce_drv,
                "routed": status == "ROUTED",
            }
    return out


def tile_pips(tile_type):
    """The pips of a HCLK_CMT tile type that this fuzzer tags."""
    fn = os.path.join(
        util.get_db_root(), "tile_type_{}.json".format(tile_type))
    with open(fn) as f:
        pips = json.load(f)["pips"]
    out = []
    for p in pips.values():
        src, dst = p["src_wire"], p["dst_wire"]
        if dst in ("HCLK_CMT_BUFMR_INP0", "HCLK_CMT_BUFMR_INP1"):
            out.append((src, dst))
        elif dst.startswith("HCLK_CMT_MUX_PHSR_PERFCLK"):
            out.append((src, dst))
    return sorted(out)


def bit_of(value):
    """1'b0 / 1'b1 / 0 / 1 -> 0 or 1."""
    return int(value.strip()[-1])


def main():
    segmk = Segmaker("design.bits")
    used = parse_pips("design_pips.txt")
    bufmrs = parse_bufmrs("bufmr_sites.txt")

    db = Database(util.get_db_root(), util.get_part())
    grid = db.grid()
    pip_cache = {}
    counts = {"in_use": 0, "ce_tags": 0, "pip_ones": 0}

    for tile_name in grid.tiles():
        gi = grid.gridinfo_at_tilename(tile_name)
        if gi.tile_type not in ("HCLK_CMT", "HCLK_CMT_L"):
            continue
        sites = sorted(
            (XY_BUFMR(s)[1], s) for s, t in gi.sites.items()
            if t == "BUFMRCE")
        if not sites:
            continue
        y0 = sites[0][0]
        tile_used = used.get(tile_name, set())

        if gi.tile_type not in pip_cache:
            pip_cache[gi.tile_type] = tile_pips(gi.tile_type)
        for src, dst in pip_cache[gi.tile_type]:
            val = 1 if (src, dst) in tile_used else 0
            segmk.add_tile_tag(tile_name, "{}.{}".format(dst, src), val)
            counts["pip_ones"] += val

        for y, site in sites:
            prefix = "BUFMRCE.BUFMRCE_X0Y{}".format(y - y0)
            cell = bufmrs.get(site)
            if cell is None:
                for tag in ("IN_USE", "ZINV_CE", "CE_TYPE.ASYNC", "INIT_OUT"):
                    segmk.add_tile_tag(tile_name, prefix + "." + tag, 0)
                continue
            if not cell["routed"]:
                continue
            segmk.add_tile_tag(tile_name, prefix + ".IN_USE", 1)
            counts["in_use"] += 1
            if cell["ref"] == "BUFMRCE" and cell["ce_driver"] == "FDRE":
                segmk.add_tile_tag(
                    tile_name, prefix + ".ZINV_CE",
                    1 - bit_of(cell["IS_CE_INVERTED"]))
                segmk.add_tile_tag(
                    tile_name, prefix + ".CE_TYPE.ASYNC",
                    1 if cell["CE_TYPE"] == "ASYNC" else 0)
                segmk.add_tile_tag(
                    tile_name, prefix + ".INIT_OUT", bit_of(cell["INIT_OUT"]))
                counts["ce_tags"] += 1

    print(
        "bufmr cells={} in_use={} fabric_ce={} pip_ones={}".format(
            len(bufmrs), counts["in_use"], counts["ce_tags"],
            counts["pip_ones"]),
        file=sys.stderr)

    # The HCLK_CMT bits Vivado sets for these features are in frames
    # 26..29, as 045 finds for the rest of the tile.
    def bitfilter(frame, bit):
        return frame >= 26

    segmk.compile(bitfilter=bitfilter)
    segmk.write(allow_empty=True)


if __name__ == "__main__":
    main()
