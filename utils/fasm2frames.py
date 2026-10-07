#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

from __future__ import print_function

import fasm
import argparse
import json
import os
import os.path
import csv
import re

from collections import defaultdict

from prjxray import fasm_assembler, util
from prjxray.db import Database
from prjxray.grid_types import GridLoc
from prjxray.roi import Roi
from prjxray.util import OpenSafeFile

import sys


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class FASMSyntaxError(SyntaxError):
    pass


def dump_frames_verbose(frames):
    print()
    print("Frames: %d" % len(frames))
    for addr in sorted(frames.keys()):
        words = frames[addr]
        print(
            '0x%08X ' % addr + ', '.join(['0x%08X' % w for w in words]) +
            '...')


def dump_frames_sparse(frames):
    print()
    print("Frames: %d" % len(frames))
    for addr in sorted(frames.keys()):
        words = frames[addr]

        # Skip frames without filled words
        for w in words:
            if w:
                break
        else:
            continue

        print('Frame @ 0x%08X' % addr)
        for i, w in enumerate(words):
            if w:
                print('  % 3d: 0x%08X' % (i, w))


def dump_frm(f, frames):
    '''Write a .frm file given a list of frames, each containing a list of 101 32 bit words'''
    for addr in sorted(frames.keys()):
        words = frames[addr]
        f.write(
            '0x%08X ' % addr + ','.join(['0x%08X' % w for w in words]) + '\n')


_TILE_XY_RE = re.compile(r"^(.*)_X(\d+)Y(\d+)$")


def add_fabric_tilename_aliases(tile_to_bank, bank_to_tile, db_root, part_data):
    """
    prjxray-db's fabric-level tilegrid.json (<db_root>/<fabric>/tilegrid.json
    -- what nextpnr-xilinx's bbaexport reads, and what tile names in the
    actual FASM output use) can disagree with the package-level
    tilegrid.json / package_pins.csv (what tile_to_bank above is built from)
    about a tile's X coordinate. Same physical tile, two different names.

    Observed on xc7s25csga324-1: RIOB33/RIOI3/IO_INT_INTERFACE_R tiles are
    consistently offset by +12 in X between the two files (e.g. package-level
    "RIOB33_X31Y37" is fabric-level "RIOB33_X43Y37"). Without this, STEPDOWN
    (and any other bank-keyed tile_to_bank.get() lookup) silently skips
    affected tiles, because the FASM tag's fabric-level tile name never
    matches any key we populated from package_pins.csv.

    Rather than hardcode that +12 (which may not hold for every part), cross
    reference the two tilegrid.json files directly: for every fabric-level
    tile sharing a (tile-type prefix, Y-coordinate) with an already-known
    package-level tile whose OWN name isn't itself a valid fabric tile (i.e.
    it's genuinely unresolvable against the fabric-level grid `db` is built
    from), alias/replace it with the fabric-level name.

    This also has to fix up bank_to_tile, not just tile_to_bank: downstream,
    the "walk every tile of an affected bank" step (further down in `run()`)
    looks up each bank_to_tile[bank] entry against `db` (fabric-level) via
    get_iob_sites()/gridinfo_at_tilename() -- a package-only tile name fails
    there with a KeyError, the same underlying mismatch, just hit from the
    other direction.
    """
    fabric = part_data.get("fabric")
    if fabric is None:
        return
    fabric_grid_path = os.path.join(db_root, fabric, "tilegrid.json")
    if not os.path.isfile(fabric_grid_path):
        return
    with OpenSafeFile(fabric_grid_path, "r") as fp:
        fabric_tiles = json.load(fp)
    fabric_tile_set = set(fabric_tiles)

    # Index already-known (package-level) tiles by (prefix, Y).
    by_prefix_y = {}
    for tile in list(tile_to_bank.keys()):
        m = _TILE_XY_RE.match(tile)
        if not m:
            continue
        by_prefix_y.setdefault((m.group(1), m.group(3)), tile)

    added = 0
    replaced = 0
    for fabric_tile in fabric_tiles:
        if fabric_tile in tile_to_bank:
            continue
        m = _TILE_XY_RE.match(fabric_tile)
        if not m:
            continue
        pkg_tile = by_prefix_y.get((m.group(1), m.group(3)))
        if pkg_tile is None:
            continue
        bank = tile_to_bank[pkg_tile]
        tile_to_bank[fabric_tile] = bank
        added += 1
        # If the package-level name isn't itself a real fabric tile, `db`
        # (built from the fabric grid) can't resolve it -- swap it out of
        # bank_to_tile for the fabric-level name so downstream per-tile
        # lookups against `db` succeed.
        if pkg_tile not in fabric_tile_set and pkg_tile in bank_to_tile[bank]:
            bank_to_tile[bank].discard(pkg_tile)
            bank_to_tile[bank].add(fabric_tile)
            replaced += 1
    if added:
        print(
            "INFO: added {} fabric/package tile-name alias(es) to "
            "tile_to_bank ({} also replaced in bank_to_tile)"
            .format(added, replaced))


def find_pudc_b(db):
    """ Find PUDC_B pin func in grid, and return the tile and site prefix.

    The PUDC_B pin is a special 7-series pin that controls unused pin pullup.

    If the PUDC_B is unused, it is configured as an input with a PULLUP.

    """
    grid = db.grid()

    pudc_b_tile_site = None
    for tile in grid.tiles():
        gridinfo = grid.gridinfo_at_tilename(tile)

        for site, pin_function in gridinfo.pin_functions.items():
            if 'PUDC_B' in pin_function:
                assert pudc_b_tile_site == None, (
                    pudc_b_tile_site, (tile, site))
                iob_y = int(site[-1]) % 2

                pudc_b_tile_site = (tile, 'IOB_Y{}'.format(iob_y))

    return pudc_b_tile_site


def get_iob_sites(db, tile_name):
    """
    Yields prjxray site names for given IOB tile name
    """
    grid = db.grid()
    gridinfo = grid.gridinfo_at_tilename(tile_name)

    for site in gridinfo.sites:
        site_y = int(site[-1]) % 2
        yield "IOB_Y{}".format(site_y)


def run(
        db_root,
        part,
        filename_in,
        f_out,
        sparse=False,
        roi=None,
        debug=False,
        emit_pudc_b_pullup=False):
    db = Database(db_root, part)
    assembler = fasm_assembler.FasmAssembler(db)

    set_features = set()

    def feature_callback(feature):
        set_features.add(feature)

    assembler.set_feature_callback(feature_callback)

    # Build mapping of tile to IO bank
    tile_to_bank = {}
    bank_to_tile = defaultdict(lambda: set())

    if part is not None:
        with OpenSafeFile(os.path.join(db_root, part, "package_pins.csv"), "r") as fp:
            reader = csv.DictReader(fp)
            package_pins = [l for l in reader]

        with OpenSafeFile(os.path.join(db_root, part, "part.json"), "r") as fp:
            part_data = json.load(fp)

        # The IO-bank "anchor" tile prefix differs per family. kintex7/artix7
        # use HR-bank IOLOGIC and therefore HCLK_IOI3. virtex7 HP-only parts
        # (e.g. xc7vx485tffg1761-2) use HCLK_IOI. Probe the grid for whichever
        # one actually exists; if neither, skip this bank-anchor altogether
        # rather than queueing a KeyError for downstream lookups.
        for bank, loc in part_data["iobanks"].items():
            for prefix in ("HCLK_IOI3_", "HCLK_IOI_"):
                tile = prefix + loc
                try:
                    db.grid().gridinfo_at_tilename(tile)
                except KeyError:
                    continue
                bank_to_tile[bank].add(tile)
                tile_to_bank[tile] = bank
                break

        for pin in package_pins:
            bank_to_tile[pin["bank"]].add(pin["tile"])
            tile_to_bank[pin["tile"]] = pin["bank"]

        add_fabric_tilename_aliases(tile_to_bank, bank_to_tile, db_root, part_data)

    # Resolve PUDC_B site unconditionally — we need the tile name later in the
    # HP-bank glue walk to skip it (Vivado does not set IBUF_HP_BANK_GLUE on
    # the PUDC_B tile even though our heuristic would).
    pudc_b_tile_site = find_pudc_b(db) if part is not None else None

    if emit_pudc_b_pullup:
        pudc_b_in_use = False

        def check_for_pudc_b(set_feature):
            feature_callback(set_feature)
            parts = set_feature.feature.split('.')

            if parts[0] == pudc_b_tile_site[0] and parts[
                    1] == pudc_b_tile_site[1]:
                nonlocal pudc_b_in_use
                pudc_b_in_use = True

        if pudc_b_tile_site is not None:
            assembler.set_feature_callback(check_for_pudc_b)

    extra_features = []
    if roi:
        with OpenSafeFile(roi) as f:
            roi_j = json.load(f)
        x1 = roi_j['info']['GRID_X_MIN']
        x2 = roi_j['info']['GRID_X_MAX']
        y1 = roi_j['info']['GRID_Y_MIN']
        y2 = roi_j['info']['GRID_Y_MAX']

        assembler.mark_roi_frames(Roi(db=db, x1=x1, x2=x2, y1=y1, y2=y2))

        if 'required_features' in roi_j:
            extra_features = list(
                fasm.parse_fasm_string('\n'.join(roi_j['required_features'])))

    # Get required extra features for the part
    required_features = db.get_required_fasm_features(part)
    extra_features += list(
        fasm.parse_fasm_string('\n'.join(required_features)))

    assembler.parse_fasm_filename(filename_in, extra_features=extra_features)

    if emit_pudc_b_pullup and not pudc_b_in_use and pudc_b_tile_site is not None:
        # Enable IN-only and PULLUP on PUDC_B IOB.
        #
        # The set of IOSTANDARD aliases differs per family because HR-bank
        # (IOB33) silicon supports more standards than HP-bank (IOB18).
        # Pick the right alias by sniffing the tile name; the chosen alias
        # has to match a segbits entry exactly or fasm2frames will error.
        missing_features = []
        is_hp = pudc_b_tile_site[0].startswith('LIOB18') or \
                pudc_b_tile_site[0].startswith('RIOB18')
        if is_hp:
            # HP-bank (virtex7 xc7vx485tffg1761-2) — Vivado emits this exact
            # feature set on the PUDC_B IOB; the bits flow from segbits
            # entries on LVCMOS12_LVCMOS15.IN, LVCMOS12_LVCMOS15_LVCMOS18.IN,
            # the long IN_ONLY alias, two SLEW.SLOW aliases, the STEPDOWN
            # alias, PULLTYPE.PULLUP on Y0, and Y1's default-state SLEW/
            # STEPDOWN/PULLDOWN trio. Cross-referenced with a Vivado-built
            # rst_to_led reference bitstream.
            pudc_template = (
                "{tile}.{site}.LVCMOS12_LVCMOS15.IN\n"
                "{tile}.{site}.LVCMOS12_LVCMOS15_LVCMOS18.IN\n"
                "{tile}.{site}.LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVDS_25_LVTTL_SSTL135_SSTL15_TMDS_33.IN_ONLY\n"
                "{tile}.{site}.LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVTTL_SSTL135_SSTL15.SLEW.SLOW\n"
                "{tile}.{site}.LVCMOS12_LVCMOS15_LVCMOS18.SLEW.SLOW\n"
                "{tile}.{site}.LVCMOS12_LVCMOS15_LVCMOS18_SSTL135_SSTL15.STEPDOWN\n"
                "{tile}.{site}.PULLTYPE.PULLUP\n"
                "{tile}.{partner}.LVCMOS12_LVCMOS15_LVCMOS18.SLEW.SLOW\n"
                "{tile}.{partner}.LVCMOS12_LVCMOS15_LVCMOS18_SSTL135_SSTL15.STEPDOWN\n"
                "{tile}.{partner}.PULLTYPE.PULLDOWN\n"
            )
            partner = 'IOB_Y1' if pudc_b_tile_site[1] == 'IOB_Y0' else 'IOB_Y0'
            for line in fasm.parse_fasm_string(pudc_template.format(
                    tile=pudc_b_tile_site[0],
                    site=pudc_b_tile_site[1],
                    partner=partner)):
                assembler.add_fasm_line(line, missing_features)
        else:
            # HR-bank (artix7/kintex7-HR/zynq7/spartan7) — original 3-line
            # template kept intact. TODO from the original code still
            # applies to K70T: it is known to be wrong but we have no
            # better data here.
            for line in fasm.parse_fasm_string("""
{tile}.{site}.LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVTTL_SSTL135_SSTL15.IN_ONLY
{tile}.{site}.LVCMOS25_LVCMOS33_LVTTL.IN
{tile}.{site}.PULLTYPE.PULLUP
""".format(
                    tile=pudc_b_tile_site[0],
                    site=pudc_b_tile_site[1],
            )):
                assembler.add_fasm_line(line, missing_features)

        if missing_features:
            raise fasm_assembler.FasmLookupError('\n'.join(missing_features))

    if part is not None:
        # Make a set of all used IOB tiles and sites. Look for the "STEPDOWN"
        # feature. If one is set for an IOB then set it for all other IOBs of
        # the same bank.
        stepdown_tags = defaultdict(lambda: set())
        stepdown_banks = set()
        used_iob_sites = set()

        for set_feature in set_features:
            if set_feature.value == 0:
                continue

            feature = set_feature.feature
            parts = feature.split(".")
            if len(parts) >= 3:
                tile, site, tag = feature.split(".", maxsplit=2)
                if "IOB33" in tile:
                    used_iob_sites.add((
                        tile,
                        site,
                    ))

                # Store STEPDOWN related tags.
                if "STEPDOWN" in tag:
                    bank = tile_to_bank.get(tile)
                    if bank is None:
                        print("WARNING: skipping STEPDOWN for unmapped tile:", tile)
                        continue
                    stepdown_banks.add(bank)
                    stepdown_tags[bank].add(tag)

        # Set the feature for unused IOBs, loop over all banks which were
        # observed to have the STEPDOWN feature set.
        missing_features = []

        for bank in stepdown_banks:
            for tile in bank_to_tile[bank]:

                # This is an IOB33 tile. Set the STEPDOWN feature in it but
                # only if it is unused.
                if "IOB33" in tile:
                    for site in get_iob_sites(db, tile):

                        if (tile, site) in used_iob_sites:
                            continue

                        for tag in stepdown_tags[bank]:
                            feature = "{}.{}.{}".format(tile, site, tag)
                            for line in fasm.parse_fasm_string(feature):
                                assembler.add_fasm_line(line, missing_features)

                # On HR-bank parts the bank-anchor tile is HCLK_IOI3 and gets a
                # STEPDOWN feature; on virtex7 HP-only it is HCLK_IOI which has
                # the same STEPDOWN feature in our segbits.
                if "HCLK_IOI3" in tile or tile.startswith("HCLK_IOI_"):
                    feature = "{}.STEPDOWN".format(tile)
                    for line in fasm.parse_fasm_string(feature):
                        assembler.add_fasm_line(line, missing_features)

        if missing_features:
            raise fasm_assembler.FasmLookupError('\n'.join(missing_features))

        # HP-bank (LIOB18/RIOB18) "bank-glue" auto-injection.
        # The HP-class output buffer (OUTBUF_DCIEN) needs three driver-enable
        # bits, and the HP-class input buffer (INBUF_DCIEN) needs one input-
        # enable bit. Vivado emits these implicitly for every used HP-bank
        # IOB; on HR-bank IOB33 the equivalent bits are factory-default so
        # were never captured in upstream prjxray. For round-trip parity on
        # virtex7 xc7vx485tffg1761-2 (HP-only) we inject the right tag
        # whenever any IOB feature is set on an HP-bank tile, mirroring the
        # STEPDOWN walk above.
        glue_missing = []
        liob_in_features = defaultdict(lambda: {'in': False, 'out': False, 'diff_in': False})
        for set_feature in set_features:
            if set_feature.value == 0:
                continue
            feature = set_feature.feature
            parts = feature.split(".")
            if len(parts) < 3:
                continue
            tile = parts[0]
            site = parts[1]
            tag  = ".".join(parts[2:])
            if not (tile.startswith("LIOB18") or tile.startswith("RIOB18")):
                continue
            if site not in ("IOB_Y0", "IOB_Y1"):
                continue
            # Direction heuristic. Pure ".IN" / ".IN_ONLY" indicates IBUF.
            # ".DRIVE." is the only reliable OBUF marker — output drive
            # strength is meaningless for inputs. ".SLEW." and ".OUT" appear
            # on IBUF tiles too as bank-wide defaults (Vivado emits
            # SLEW.SLOW on every unused IOB), so they would mis-classify
            # IBUFs as IOBUFs and inject spurious OBUF_HP_BANK_GLUE bits.
            # ".IN_DIFF" indicates an IBUFDS (LVDS differential input).
            if "IN_DIFF" in tag:
                liob_in_features[(tile, site)]['diff_in'] = True
            elif "IN_ONLY" in tag or tag.endswith(".IN") or "IBUFDISABLE" in tag:
                liob_in_features[(tile, site)]['in'] = True
            if ".DRIVE." in tag:
                liob_in_features[(tile, site)]['out'] = True

        # The three bits of OBUF_HP_BANK_GLUE are not the IOB's: they are
        # OQUSED, OMUX.D1 and OSERDES.DATA_RATE_TQ.BUF of the OLOGIC in the IOI
        # tile beside it (the two tiles share their frames), which is how an
        # OLOGIC is set when it passes the fabric signal through to the pad.
        # When that OLOGIC holds a cell -- an ODDR or an OSERDES, on the data or
        # on the tristate -- the FASM configures it already, and the glue would
        # add OMUX.D1, driving the pad from D1 around the register, and
        # DATA_RATE_TQ.BUF, which conflicts with a registered tristate's
        # DATA_RATE_TQ.DDR.  So a half whose OLOGIC has any feature beyond that
        # pass-through and ZINV_T1 (the tristate passing through) gets no glue.
        ologic_pass_through = (
            'OQUSED', 'OMUX.D1', 'OSERDES.DATA_RATE_TQ.BUF', 'ZINV_T1')
        configured_ologics = set()
        for set_feature in set_features:
            if set_feature.value == 0:
                continue
            parts = set_feature.feature.split(".")
            if len(parts) < 3 or not parts[1].startswith("OLOGIC_Y"):
                continue
            if ".".join(parts[2:]) in ologic_pass_through:
                continue
            configured_ologics.add((parts[0], parts[1]))

        grid = db.grid()

        def ologic_beside(tile, site):
            # The IOI tile is the IOB tile's neighbour on the fabric side, in
            # the same grid row, and IOB_Yn pairs with OLOGIC_Yn.
            loc = grid.loc_of_tilename(tile)
            step = 1 if tile.startswith("LIOB18") else -1
            ioi_loc = GridLoc(loc.grid_x + step, loc.grid_y)
            if not grid.is_populated(ioi_loc):
                return None
            return grid.tilename_at_loc(ioi_loc), "OLOGIC_Y" + site[-1]

        # Track whether the col-32 LIOB18 column has any Y1 OBUFs anywhere.
        # When it does, Vivado lights a 6-bit "DCI cascade + bank active"
        # pattern in INT_L_X32Y49 — the bottom-most INT_L tile of the X32
        # routing spine that serves the LIOB18 column. The same indicator
        # exists for the X110 (R-side IOB) column too, mirrored at
        # INT_R_X110Y49 — we'd add that when the first RIOB18 test design
        # asks for it.
        any_liob18_y1_obuf = False
        # PUDC_B's tile already gets its own IN/IN_ONLY/PULLUP/SLEW features
        # injected above; do NOT also fire the IBUF_HP_BANK_GLUE rule on it.
        # Empirically (Vivado-built rst_to_led ref) the PUDC_B tile does not
        # carry the bank-glue bit because the pullup is a "virtual" tie,
        # not a real IBUF placement.
        pudc_b_tile_name = pudc_b_tile_site[0] if pudc_b_tile_site else None
        for (tile, site), kind in liob_in_features.items():
            if tile == pudc_b_tile_name:
                continue
            # Both IOB_Y0 (master) and IOB_Y1 (slave) sites have HP_BANK_GLUE
            # patterns now. The Y1 OBUF rule was derived from the counter
            # design (LIOB18 tiles with two driving OBUFs) — Vivado emits an
            # extra 3 bits at rel 30_041 / 32_016 / 33_061 when Y1 has a
            # ".DRIVE." feature in addition to Y0.
            if kind['in']:
                feature = "{}.{}.IBUF_HP_BANK_GLUE".format(tile, site)
                for line in fasm.parse_fasm_string(feature):
                    assembler.add_fasm_line(line, glue_missing)
            if kind['out'] and ologic_beside(tile,
                                             site) not in configured_ologics:
                feature = "{}.{}.OBUF_HP_BANK_GLUE".format(tile, site)
                for line in fasm.parse_fasm_string(feature):
                    assembler.add_fasm_line(line, glue_missing)
            if kind['diff_in']:
                # IBUFDS — empirically Vivado lights a 7-bit pattern in the
                # IOB_Y0 (M-site) slot of the differential pair. Y1 is the
                # negative-half slave and reuses the silicon defaults, so
                # no separate Y1 rule is needed.
                feature = "{}.IOB_Y0.IBUFDS_BANK_GLUE".format(tile)
                for line in fasm.parse_fasm_string(feature):
                    assembler.add_fasm_line(line, glue_missing)
            if kind['out'] and site == 'IOB_Y1' and tile.startswith('LIOB18_X81'):
                any_liob18_y1_obuf = True

        if any_liob18_y1_obuf:
            for tag in ('INT_L_X32Y49.IOB_COL_OBUF_CASCADE_Y1',
                        'INT_L_X32Y49.IOB_COL_BANK_ACTIVE'):
                for line in fasm.parse_fasm_string(tag):
                    assembler.add_fasm_line(line, glue_missing)

        # GFAN0 T-tie root glue. When the design has an OBUF whose T
        # input must be tied to GND through general routing (e.g. an
        # IBUF→OBUF passthrough where no SLICE FF Q drives the OBUF),
        # Vivado emits INT_L_X62Y73.GFAN0.GND_WIRE / .IMUX_L33.GFAN0
        # FASM features AND lights one extra silicon bit at
        # INT_L_X62Y83 minor 26 bit 18 — the "this GFAN tie route is
        # in use" marker for the col-62 routing spine. Only the c=62
        # column has been observed needing this glue (the counter
        # designs use FF-driven OBUFs and route GFAN0 through other
        # columns without triggering an analogous bit). The rule fires
        # only when an X62-column GFAN0.GND_WIRE feature appears.
        x62_gfan_tile = None
        for set_feature in set_features:
            if set_feature.value == 0:
                continue
            feat = set_feature.feature
            if not feat.startswith('INT_L_X62'):
                continue
            if 'GFAN0.GND_WIRE' in feat:
                # The mirror tile (Y+10) gets the glue bit. For
                # INT_L_X62Y73 → INT_L_X62Y83.
                tile = feat.split('.')[0]
                import re as _re
                m = _re.match(r'(INT_L_X(\d+))Y(\d+)', tile)
                if m:
                    x62_gfan_tile = 'INT_L_X{}Y{}'.format(m.group(2), int(m.group(3)) + 10)
                break

        if x62_gfan_tile:
            feature = '{}.GFAN_TIE_ROOT_GLUE'.format(x62_gfan_tile)
            for line in fasm.parse_fasm_string(feature):
                assembler.add_fasm_line(line, glue_missing)

        # HCLK_L per-BUFRCLK-channel "active" markers. Empirically Vivado
        # sets one extra bit per HCLK_L tile per BUFR channel in use, at
        # minor 1 bit 28+ch. Only BUFRCLK3 is observed today (the
        # counter_sw_bufr design); when a kintex7 → virtex7 comparison
        # design that uses BUFRCLK0/1/2 is built we can add those analogues
        # to segbits_hclk_l.db with bits 01_28 / 01_29 / 01_30 respectively.
        hclkl_bufrclk_seen = {}  # (hclkl_tile) -> set of channel-ids in use
        for set_feature in set_features:
            if set_feature.value == 0:
                continue
            feat = set_feature.feature
            parts = feat.split('.')
            if len(parts) < 3:
                continue
            if not parts[0].startswith('HCLK_L'):
                continue
            # HCLK_L_X..Y...HCLK_LEAF_CLK_B_TOP/BOTL[0-5].HCLK_CK_BUFRCLK[0-3]
            tag = '.'.join(parts[2:])
            if 'HCLK_CK_BUFRCLK' not in tag:
                continue
            ch = tag.rsplit('HCLK_CK_BUFRCLK', 1)[1]
            if ch.isdigit():
                hclkl_bufrclk_seen.setdefault(parts[0], set()).add(int(ch))

        for hclkl_tile, channels in hclkl_bufrclk_seen.items():
            for ch in channels:
                if ch != 3:
                    # Only BUFRCLK3 has segbits data so far; skip rest
                    # silently so the partial rule doesn't error.
                    continue
                feature = '{}.HCLK_LEAF_BUFRCLK{}_ACTIVE'.format(hclkl_tile, ch)
                for line in fasm.parse_fasm_string(feature):
                    assembler.add_fasm_line(line, glue_missing)

        # glue_missing entries indicate the segbits don't carry the rule yet
        # (e.g. partially-built database); fall through silently rather than
        # erroring, so this auto-injection is a no-op on databases that
        # haven't been bank-glue-annotated.

    frames = assembler.get_frames(sparse=sparse)

    if debug:
        dump_frames_sparse(frames)

    dump_frm(f_out, frames)


def main():
    parser = argparse.ArgumentParser(
        description=
        'Convert FPGA configuration description ("FPGA assembly") into binary frame equivalent'
    )

    util.db_root_arg(parser)
    util.part_arg(parser)
    parser.add_argument(
        '--sparse', action='store_true', help="Don't zero fill all frames")
    parser.add_argument(
        '--roi',
        help="ROI design.json file defining which tiles are within the ROI.")
    parser.add_argument(
        '--emit_pudc_b_pullup',
        help="Emit an IBUF and PULLUP on the PUDC_B pin if unused",
        action='store_true')
    parser.add_argument(
        '--debug', action='store_true', help="Print debug dump")
    parser.add_argument('fn_in', help='Input FPGA assembly (.fasm) file')
    parser.add_argument(
        'fn_out',
        default=None,
        nargs='?',
        help='Output FPGA frame (.frm) file (default: stdout)')

    args = parser.parse_args()
    run(
        db_root=args.db_root,
        part=args.part,
        filename_in=args.fn_in,
        f_out=(open(args.fn_out, 'w') if args.fn_out else sys.stdout),
        sparse=args.sparse,
        roi=args.roi,
        debug=args.debug,
        emit_pudc_b_pullup=args.emit_pudc_b_pullup)


if __name__ == '__main__':
    main()
