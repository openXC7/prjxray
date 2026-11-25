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
# Specimen generator for the BUFMRCE sites of HCLK_CMT / HCLK_CMT_L.
#
# Every BUFMR that is used drives a BUFR, and every BUFR clocks a counter
# in the fabric of its own clock region, so the multi-region clock really
# reaches a regional buffer. Vivado routes BUFMRCE.O -> PHASEREF ->
# (PHASER_IN route-through in CMT_TOP_*) -> HCLK_CMT_PHASERIN_RCLKn ->
# HCLK_CMT_MUX_PHSR_PERFCLKm -> HCLK_IOI_IOCLK_PLLm -> BUFR.I, either in
# the BUFMR's own region or, through PHASERREF_ABOVE, in the region below.
#
# FUZZ_MODE:
#   campaign (default)  per site a random state (see choose_state())
#   cal_s0 / cal_s1     one-hot: only that BUFMRCE site of every HCLK_CMT
#                       tile, a BUFMR fed from its own dedicated pad, driving
#                       one BUFR in its own region
#   neg_unused          no BUFMR; every dedicated pad drives a BUFR directly
#   neg_unconsumed      cal_s0's BUFMRs with O left open
#   neg_const_ce        cal_s0's shape with a BUFMRCE whose CE is a constant,
#                       IS_CE_INVERTED=1, CE_TYPE=ASYNC and INIT_OUT=1
#   probe_above         cal_s0's shape, but each BUFMR drives a BUFR in the
#                       region above (whether Vivado can route that at all)
#
# params.json records, per BUFMR cell, what top.py asked for; generate.py
# tags from the sites and pips Vivado reports, not from this file alone.
import csv
import json
import os
import random
import runpy
import sys

from prjxray.db import Database
from prjxray import util

MODE = os.getenv("FUZZ_MODE", "campaign")
IOSTANDARD = os.getenv("XRAY_IOSTANDARD", "LVCMOS33")

# Each BUFMRCE site has one dedicated clock-capable input: site 0
# (HCLK_CMT_BUFMR_INP0) takes HCLK_CMT_CCIO0, site 1 (INP1) takes
# HCLK_CMT_CCIO3 (measured with Vivado 2025.2 on xc7a100t / xc7a35t).
SITE_CCIO = {0: 0, 1: 3}

# get_paired_iobs() from 045 maps a HCLK_CMT tile to the IOB33M sites on
# its four CCIO lines; reuse it rather than copy it.
_F045 = runpy.run_path(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "045-hclk-cmt-pips", "top.py"),
    run_name="fuzz045")
get_paired_iobs = _F045["get_paired_iobs"]

XY_BUFMR = util.create_xy_fun("BUFMRCE_")
XY_BUFR = util.create_xy_fun("BUFR_")


def seed_rng():
    raw = os.getenv("SEED", "0")
    try:
        random.seed(int(raw, 16))
    except ValueError:
        random.seed(int(os.getenv("SEEDN", "1")))


def slices_by_region(grid):
    out = {}
    for tn in grid.tiles():
        gi = grid.gridinfo_at_tilename(tn)
        if gi.clock_region is None:
            continue
        if gi.tile_type not in ("CLBLL_L", "CLBLL_R", "CLBLM_L", "CLBLM_R"):
            continue
        for st, sty in gi.sites.items():
            if sty in ("SLICEL", "SLICEM"):
                out.setdefault(gi.clock_region.name, []).append(st)
    for cr in out:
        out[cr].sort()
    return out


def paired_hclk_ioi(grid, tile_name):
    """The HCLK_IOI3 tile on the same row, on the side the CMT faces."""
    gi = grid.gridinfo_at_tilename(tile_name)
    loc = grid.loc_of_tilename(tile_name)
    inc = 1 if gi.tile_type.endswith("_L") else -1
    x = loc.grid_x + inc
    while True:
        try:
            other = grid.tilename_at_loc((x, loc.grid_y))
        except KeyError:
            return None
        if grid.gridinfo_at_tilename(other).tile_type.startswith("HCLK_IOI"):
            return other
        x += inc


def bonded_sites():
    """IOB sites the package bonds out; a LOC on any other one fails."""
    fn = os.path.join(util.get_db_root(), util.get_part(), "package_pins.csv")
    with open(fn) as f:
        return set(row["site"] for row in csv.DictReader(f))


def gen_cmts(db, grid):
    """Yield one record per HCLK_CMT tile that has BUFMRCE sites."""
    bonded = bonded_sites()
    for tile_name in sorted(grid.tiles()):
        gi = grid.gridinfo_at_tilename(tile_name)
        if gi.tile_type not in ("HCLK_CMT", "HCLK_CMT_L"):
            continue
        bufmrs = sorted(
            (XY_BUFMR(s)[1], s) for s, t in gi.sites.items()
            if t == "BUFMRCE")
        if len(bufmrs) != 2 or gi.clock_region is None:
            continue
        y0 = bufmrs[0][0]
        sites = {y - y0: s for y, s in bufmrs}

        ioi = paired_hclk_ioi(grid, tile_name)
        if ioi is None:
            continue
        ioi_gi = grid.gridinfo_at_tilename(ioi)
        if not ioi_gi.tile_type.startswith("HCLK_IOI3"):
            # HP banks (IOB18) are left out of this first population.
            continue
        bufrs = sorted(
            (XY_BUFR(s)[1], s) for s, t in ioi_gi.sites.items()
            if t == "BUFR")

        pads = {}
        for _, site, volt, ccio in get_paired_iobs(db, grid, tile_name):
            if site in bonded:
                pads[ccio] = site

        yield {
            "tile": tile_name,
            "tile_type": gi.tile_type,
            "region": gi.clock_region,
            "sites": sites,
            "bufrs": [s for _, s in bufrs],
            "pads": pads,
        }


def choose_state():
    """Campaign state of one BUFMRCE site."""
    r = random.random()
    if r < 0.20:
        return "unused"
    if r < 0.30:
        # The dedicated pad drives a BUFR directly, no BUFMR: CCIOn_ACTIVE
        # without the BUFMR_INP pip.
        return "direct"
    return "bufmr"


def choose_cell():
    """BUFMR, or BUFMRCE with a constant or a fabric CE."""
    r = random.random()
    if r < 0.25:
        return {"cell": "BUFMR", "ce": "none"}
    cell = {
        "cell": "BUFMRCE",
        "CE_TYPE": random.choice(("SYNC", "ASYNC")),
        "IS_CE_INVERTED": random.randint(0, 1),
        "INIT_OUT": random.randint(0, 1),
    }
    cell["ce"] = "const" if r < 0.40 else "fabric"
    return cell


def choose_source():
    r = random.random()
    if r < 0.60:
        return "pad"
    if r < 0.80:
        return "fabric"
    return "bufg"


class Design(object):
    def __init__(self, grid):
        self.blocks = []
        self.num_pads = 0
        self.slices = slices_by_region(grid)
        self.slice_cursor = {}
        self.used_bufr = set()
        self.params = []
        self.need_gclk = False

    def take_slices(self, region, n):
        pool = self.slices.get(region, [])
        i = self.slice_cursor.get(region, 0)
        self.slice_cursor[region] = i + n
        return pool[i:i + n]

    def pad(self, site, name):
        idx = self.num_pads
        self.num_pads += 1
        self.blocks.append(
            """
    wire {n};
    (* KEEP, DONT_TOUCH, LOC="{site}" *)
    IBUF #(.IOSTANDARD("{iost}")) ibuf_{n} (.I(pads[{idx}]), .O({n}));
""".format(n=name, site=site, idx=idx, iost=IOSTANDARD))
        return name

    def toggle(self, region, name):
        """A fabric signal: a flop toggled by the global clock."""
        self.need_gclk = True
        sl = self.take_slices(region, 1)
        loc = ', LOC="{}", BEL="AFF"'.format(sl[0]) if sl else ""
        self.blocks.append(
            """
    wire {n};
    (* KEEP, DONT_TOUCH{loc} *)
    FDRE #(.INIT(1'b0)) ff_{n} (.C(gclk), .CE(1'b1), .R(1'b0), .D(~{n}), .Q({n}));
""".format(n=name, loc=loc))
        return name

    def bufr(self, cmt, src, name):
        """A BUFR in that CMT's HCLK_IOI3 tile, plus a counter it clocks."""
        free = [s for s in cmt["bufrs"] if s not in self.used_bufr]
        if not free:
            return None
        site = random.choice(free)
        self.used_bufr.add(site)
        self.blocks.append(
            """
    wire {n}_o;
    (* KEEP, DONT_TOUCH, LOC="{site}" *)
    BUFR #(.BUFR_DIVIDE("BYPASS")) bufr_{n} (.CE(1'b1), .CLR(1'b0), .I({src}), .O({n}_o));
""".format(n=name, site=site, src=src))
        sl = self.take_slices(cmt["region"].name, 2)
        for i, s in enumerate(sl):
            self.blocks.append(
                """
    wire {n}_q{i};
    (* KEEP, DONT_TOUCH, LOC="{s}", BEL="AFF" *)
    FDRE #(.INIT(1'b0)) cnt_{n}_{i} (.C({n}_o), .CE(1'b1), .R(1'b0), .D(~{n}_q{i}), .Q({n}_q{i}));
""".format(n=name, i=i, s=s))
        return site

    def bufmr(self, site, cell, src, ce_sig, name, consumed=True):
        out = ".O({}_o)".format(name) if consumed else ""
        if consumed:
            self.blocks.append("    wire {}_o;".format(name))
        if cell["cell"] == "BUFMR":
            self.blocks.append(
                """
    (* KEEP, DONT_TOUCH, LOC="{site}" *)
    BUFMR bufmr_{n} (.I({src}){sep}{out});
""".format(site=site, n=name, src=src, out=out, sep=", " if out else ""))
            return
        ce = ce_sig if cell["ce"] == "fabric" else (
            "1'b0" if cell["IS_CE_INVERTED"] else "1'b1")
        self.blocks.append(
            """
    (* KEEP, DONT_TOUCH, LOC="{site}" *)
    BUFMRCE #(.CE_TYPE("{ct}"), .INIT_OUT({io}), .IS_CE_INVERTED(1'b{inv}))
        bufmr_{n} (.I({src}), .CE({ce}){sep}{out});
""".format(
                site=site, n=name, src=src, ce=ce, out=out,
                sep=", " if out else "", ct=cell["CE_TYPE"],
                io=cell["INIT_OUT"], inv=cell["IS_CE_INVERTED"]))

    def emit(self):
        npads = max(self.num_pads, 1)
        ports = ["input [{}:0] pads".format(npads - 1)]
        if self.need_gclk:
            ports.append("input gclk_pad")
        print("module top({});".format(", ".join(ports)))
        print("    (* KEEP, DONT_TOUCH *) LUT6 dummy ();")
        if self.need_gclk:
            print("    wire gclk;")
            print("    (* KEEP, DONT_TOUCH *) BUFG bufg_gclk (.I(gclk_pad), .O(gclk));")
        for b in self.blocks:
            print(b)
        print("endmodule")
        with open("params.json", "w") as f:
            json.dump(self.params, f, indent=2, sort_keys=True)


def neighbour(cmts, cmt, dy):
    """The HCLK_CMT of the same column whose clock region is dy rows away."""
    want_y = cmt["region"].y + dy
    for other in cmts:
        if (other["tile_type"] == cmt["tile_type"]
                and other["region"].x == cmt["region"].x
                and other["region"].y == want_y):
            return other
    return None


def main():
    seed_rng()
    db = Database(util.get_db_root(), util.get_part())
    grid = db.grid()
    cmts = list(gen_cmts(db, grid))
    if not cmts:
        sys.stderr.write("no HCLK_CMT tiles with BUFMRCE sites\n")
        sys.exit(1)

    d = Design(grid)
    for cmt in cmts:
        tn = cmt["tile"]
        for rel in (0, 1):
            site = cmt["sites"][rel]
            name = site.replace("/", "_")
            pad_site = cmt["pads"].get(SITE_CCIO[rel])
            rec = {"tile": tn, "rel": rel, "site": site, "cell_name": None}

            if MODE in ("cal_s0", "cal_s1", "neg_unconsumed", "neg_const_ce",
                        "probe_above"):
                want = 1 if MODE == "cal_s1" else 0
                state = "bufmr" if rel == want and pad_site else "unused"
                cell = {"cell": "BUFMR", "ce": "none"}
                if MODE == "neg_const_ce":
                    cell = {"cell": "BUFMRCE", "ce": "const", "CE_TYPE": "ASYNC",
                            "IS_CE_INVERTED": 1, "INIT_OUT": 1}
                source = "pad"
                dest = {"probe_above": "above"}.get(MODE, "own")
            elif MODE == "neg_unused":
                state = "direct" if pad_site else "unused"
                cell, source, dest = None, "pad", "own"
            else:
                state = choose_state()
                cell = choose_cell()
                source = choose_source()
                dest = "below" if random.random() < 0.3 else "own"
                if state == "direct" and not pad_site:
                    state = "unused"
                if source == "pad" and not pad_site:
                    source = "fabric"

            rec["state"] = state
            if state == "unused":
                d.params.append(rec)
                continue

            if state == "direct":
                src = d.pad(pad_site, "pad_" + name)
                got = d.bufr(cmt, src, "direct_" + name)
                rec.update({"source": "pad", "pad": pad_site, "bufr": got})
                d.params.append(rec)
                continue

            if source == "pad":
                src = d.pad(pad_site, "pad_" + name)
                rec["pad"] = pad_site
            elif source == "fabric":
                src = d.toggle(cmt["region"].name, "src_" + name)
            else:
                src = "gclk"
                d.need_gclk = True

            ce_sig = None
            if cell["cell"] == "BUFMRCE" and cell["ce"] == "fabric":
                ce_sig = d.toggle(cmt["region"].name, "ce_" + name)

            target = cmt
            if dest == "below":
                target = neighbour(cmts, cmt, -1) or cmt
            elif dest == "above":
                target = neighbour(cmts, cmt, +1)
            if target is None:
                rec["state"] = "unused"
                rec["skipped"] = "no region above"
                d.params.append(rec)
                continue
            dest = "own" if target is cmt else dest

            consumed = MODE != "neg_unconsumed"
            d.bufmr(site, cell, src, ce_sig, name, consumed)
            got = d.bufr(target, name + "_o", "r_" + name) if consumed else None
            rec.update(cell)
            rec.update({
                "cell_name": "bufmr_" + name,
                "source": source,
                "dest": dest,
                "dest_tile": target["tile"],
                "bufr": got,
            })
            d.params.append(rec)

    d.emit()
    sys.stderr.write("MODE={} cmts={} bufmr={}\n".format(
        MODE, len(cmts), sum(1 for p in d.params if p.get("cell_name"))))


if __name__ == "__main__":
    main()
