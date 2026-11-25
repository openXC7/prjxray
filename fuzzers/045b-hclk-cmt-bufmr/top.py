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
#   neg_const_ce        cal_s0's shape with a BUFMRCE whose CE is a constant,
#                       IS_CE_INVERTED=1, CE_TYPE=ASYNC and INIT_OUT=1
#   probe_above         cal_s0's shape, but each BUFMR drives a BUFR in the
#                       region above
#   onehot_perf         one BUFMR per HCLK_CMT tile, pad-fed on site 0, driving
#                       one BUFR in its own region, with its route fixed
#                       through one HCLK_CMT_PHASERIN_RCLK<n> ->
#                       HCLK_CMT_MUX_PHSR_PERFCLK<m> pair (see onehot_pair()).
#                       Unforced, Vivado always fills the mux in the same
#                       order, so its pips only ever appear together and
#                       their shared bits can't be told apart.
#
# A BUFMR whose O drives nothing cannot be built: Vivado's DRC REQP-1936
# only lets BUFMR/O drive BUFR/I, BUFIO/I and the PHASER reference clocks.
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
    """{site: tile} of the IOB sites the package bonds out.

    A LOC on any other IOB fails.
    """
    fn = os.path.join(util.get_db_root(), util.get_part(), "package_pins.csv")
    with open(fn) as f:
        return {row["site"]: row["tile"] for row in csv.DictReader(f)}


def gclk_site(bonded, cmts):
    """An HR pad for the global clock that is none of the CMTs' CCIO pads.

    The BUFG's input needs a LOC and an IOSTANDARD like every other pad,
    or write_bitstream stops on DRC NSTD-1 / UCIO-1.
    """
    ccio = set(p for c in cmts for p in c["pads"].values())
    for site in sorted(bonded):
        if not site.startswith("IOB_") or site in ccio:
            continue
        if bonded[site].startswith(("LIOB33", "RIOB33")):
            return site
    return None


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
    def __init__(self, grid, gclk_site):
        self.gclk_site = gclk_site
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

    def has_free_bufr(self, cmt):
        return any(s not in self.used_bufr for s in cmt["bufrs"])

    def bufmr(self, site, cell, src, ce_sig, name):
        out = ".O({}_o)".format(name)
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
            assert self.gclk_site, "no free HR pad for the global clock"
            ports.append("input gclk_pad")
        print("module top({});".format(", ".join(ports)))
        print("    (* KEEP, DONT_TOUCH *) LUT6 dummy ();")
        if self.need_gclk:
            print("    wire gclk, gclk_ibuf;")
            print(
                '    (* KEEP, DONT_TOUCH, LOC="{}" *) IBUF #(.IOSTANDARD("{}")) '
                'ibuf_gclk (.I(gclk_pad), .O(gclk_ibuf));'.format(
                    self.gclk_site, IOSTANDARD))
            print("    (* KEEP, DONT_TOUCH *) BUFG bufg_gclk (.I(gclk_ibuf), .O(gclk));")
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


# The 16 PHASER_IN -> performance-clock positions of a HCLK_CMT tile.
PERF_PAIRS = [(n, m) for m in range(4) for n in range(4)]


def specimen_index():
    """The number at the end of the specimen directory, e.g. specimen_P_007."""
    tail = os.path.basename(os.getcwd()).rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def onehot_pair(spec, rank):
    """The (RCLK n, PERFCLK m) pair of tile `rank` in specimen `spec`.

    Tiles of one specimen get different pairs, and successive specimens
    shift every tile on by one, so each tile walks all 16 pairs.
    """
    return PERF_PAIRS[(spec + rank) % len(PERF_PAIRS)]


def main_onehot():
    db = Database(util.get_db_root(), util.get_part())
    grid = db.grid()
    cmts = list(gen_cmts(db, grid))
    d = Design(grid, None)
    spec = specimen_index()
    forced = []
    for rank, cmt in enumerate(cmts):
        site = cmt["sites"][0]
        name = site.replace("/", "_")
        pad_site = cmt["pads"].get(SITE_CCIO[0])
        rec = {"tile": cmt["tile"], "rel": 0, "site": site, "cell_name": None}
        if not pad_site or not d.has_free_bufr(cmt):
            rec["state"] = "unused"
            d.params.append(rec)
            continue
        n, m = onehot_pair(spec, rank)
        src = d.pad(pad_site, "pad_" + name)
        cell = {"cell": "BUFMR", "ce": "none"}
        d.bufmr(site, cell, src, None, name)
        bufr = d.bufr(cmt, name + "_o", "r_" + name)
        forced.append(
            "{} {} {} {} {}".format(name + "_o", cmt["tile"], n, m, bufr))
        rec.update(cell)
        rec.update({
            "state": "bufmr",
            "cell_name": "bufmr_" + name,
            "source": "pad",
            "pad": pad_site,
            "dest": "own",
            "dest_tile": cmt["tile"],
            "bufr": bufr,
            "forced_rclk": n,
            "forced_perfclk": m,
        })
        d.params.append(rec)
    d.emit()
    with open("forced.txt", "w") as f:
        for line in forced:
            f.write(line + "\n")
    sys.stderr.write("MODE={} specimen={} cmts={} forced={}\n".format(
        MODE, spec, len(cmts), len(forced)))


def main():
    if MODE == "onehot_perf":
        main_onehot()
        return
    seed_rng()
    db = Database(util.get_db_root(), util.get_part())
    grid = db.grid()
    cmts = list(gen_cmts(db, grid))
    if not cmts:
        sys.stderr.write("no HCLK_CMT tiles with BUFMRCE sites\n")
        sys.exit(1)

    d = Design(grid, gclk_site(bonded_sites(), cmts))
    for cmt in cmts:
        tn = cmt["tile"]
        for rel in (0, 1):
            site = cmt["sites"][rel]
            name = site.replace("/", "_")
            pad_site = cmt["pads"].get(SITE_CCIO[rel])
            rec = {"tile": tn, "rel": rel, "site": site, "cell_name": None}

            if MODE in ("cal_s0", "cal_s1", "neg_const_ce", "probe_above"):
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
                dest = random.choice(("own", "own", "below", "above"))
                if state == "direct" and not pad_site:
                    state = "unused"
                if source == "pad" and not pad_site:
                    source = "fabric"

            rec["state"] = state
            if state == "unused":
                d.params.append(rec)
                continue

            if state == "direct" and not d.has_free_bufr(cmt):
                rec["state"] = "unused"
                rec["skipped"] = "no free BUFR"
                d.params.append(rec)
                continue
            if state == "direct":
                src = d.pad(pad_site, "pad_" + name)
                got = d.bufr(cmt, src, "direct_" + name)
                rec.update({"source": "pad", "pad": pad_site, "bufr": got})
                d.params.append(rec)
                continue

            target = cmt
            if dest == "below":
                target = neighbour(cmts, cmt, -1)
            elif dest == "above":
                target = neighbour(cmts, cmt, +1)
            if target is None and MODE == "campaign":
                # The bottom or top row of CMTs: use the own region.
                target = cmt
            if target is not None and not d.has_free_bufr(target):
                # A BUFMR must drive something (DRC REQP-1936).
                target = None
            if target is None:
                rec["state"] = "unused"
                rec["skipped"] = "no region {} with a free BUFR".format(dest)
                d.params.append(rec)
                continue
            dest = "own" if target is cmt else dest

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

            d.bufmr(site, cell, src, ce_sig, name)
            got = d.bufr(target, name + "_o", "r_" + name)
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
