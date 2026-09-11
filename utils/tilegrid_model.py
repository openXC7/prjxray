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
"""Learn the 7-series tilegrid frame-address law from the device models a
database already holds, and apply it to a device grid.

The law, per family::

    baseaddr = (block_type << 23) | (bottom << 22) | (row << 17) | (column << 7)

column
    The rank of the tile's own configuration column, counted left to right
    over the grid columns that carry an interconnect tile (``INT_L`` /
    ``INT_R`` / ``INT_FEEDTHRU_2``) for the ``CLB_IO_CLK`` bus, or a block-RAM
    tile (``BRAM_L`` / ``BRAM_R``) for the ``BLOCK_RAM`` bus.  Which of those
    columns a tile belongs to is a fixed per-tile-type grid_x delta -- a
    ``CLBLL_L`` sits one column left of its ``INT_L``, a ``DSP_R`` two columns
    right of its ``INT_R`` -- learned from the reference models.

bottom, row
    The clock-region row the tile lives in, numbered outward from the middle
    of the device.  Which rows exist in each half comes from ``part.yaml``.

offset, words, frames
    A fixed function of the tile type and of the tile's vertical position
    inside its clock-region row, again learned from the reference models.
    ``frames`` is capped by the column's own ``frame_count``, the way
    ``fuzzers/005-tilegrid/util.py`` caps it.

Everything the model knows is measured: it comes out of tilegrids that
``005-tilegrid`` produced against real silicon.  Nothing here guesses at a
device nobody has looked at -- a tile type no reference model carries gets no
address at all, and a reference whose grid disagrees with its own
``part.yaml`` is refused rather than averaged in.  The check that this is the
law and not an accident is leave-one-out reproduction of every device model in
the database (``utils/tilegrid_derive.py calibrate``).
"""

import collections
import copy
import importlib.util
import json
import os

from utils import xyaml

# The configuration buses a tilegrid addresses.  CFG_CLB (block type 2) is
# never part of a tilegrid entry, so only these two are modelled.
BUSES = ('CLB_IO_CLK', 'BLOCK_RAM')
BLOCK_TYPE = {'CLB_IO_CLK': 0, 'BLOCK_RAM': 1}

# A configuration column is anchored on its interconnect column.  Where a hard
# block (the configuration centre) interrupts the fabric, the interconnect is
# replaced by a feed-through tile: INT_FEEDTHRU_2 sits exactly where the INT_L
# or INT_R would, and INT_FEEDTHRU_1 where the logic tile would.  The column
# still exists in the bitstream and still consumes a column index, which is why
# xc7s25 declares 38 configuration columns while only 32 of them carry
# interconnect.
INT_TYPES = ('INT_L', 'INT_R', 'INT_FEEDTHRU_2')
BRAM_TYPES = ('BRAM_L', 'BRAM_R')
ANCHOR_TYPES = {'CLB_IO_CLK': INT_TYPES, 'BLOCK_RAM': BRAM_TYPES}

# A clock-region row is 50 tile rows tall, centred on its HCLK row.
CLOCK_ROW_HALF_HEIGHT = 25


def decode_baseaddr(baseaddr):
    """Split a tilegrid base address into (block_type, bottom, row, column).

    >>> decode_baseaddr('0x0040099B')
    (0, 1, 0, 19)
    >>> decode_baseaddr('0x00800100')
    (1, 0, 0, 2)
    """
    a = int(baseaddr, 0)
    return ((a >> 23) & 0x7, (a >> 22) & 1, (a >> 17) & 0x1F, (a >> 7) & 0x3FF)


def encode_baseaddr(block_type, bottom, row, column):
    """Build a tilegrid base address out of its four fields.

    >>> encode_baseaddr(0, 1, 0, 19)
    '0x00400980'
    >>> decode_baseaddr(encode_baseaddr(1, 0, 2, 5))
    (1, 0, 2, 5)
    """
    return '0x%08X' % (
        (block_type << 23) | (bottom << 22) | (row << 17) | (column << 7))


def clock_rows(grid):
    """grid_y of every HCLK row of a grid, top of the device first."""
    return sorted(
        {t['grid_y']
         for t in grid.values()
         if t['type'].startswith('HCLK')})


def clock_row_of(grid, hclk_ys=None):
    """tile name -> (index of its clock-region row, position inside that row)

    The position is counted upward from the bottom of the clock region, which
    is how the tile geometry repeats: the tile at the very bottom of every
    clock region has the same offset and word count wherever it sits.
    """
    if hclk_ys is None:
        hclk_ys = clock_rows(grid)
    out = {}
    for name, tile in grid.items():
        gy = tile['grid_y']
        for i, hy in enumerate(hclk_ys):
            if hy - CLOCK_ROW_HALF_HEIGHT <= gy <= hy + CLOCK_ROW_HALF_HEIGHT:
                out[name] = (i, hy + CLOCK_ROW_HALF_HEIGHT - gy)
                break
    return out


def anchor_columns(grid, bus):
    """sorted grid_x of the columns that anchor a configuration column of `bus`"""
    types = ANCHOR_TYPES[bus]
    return sorted({t['grid_x'] for t in grid.values() if t['type'] in types})


def part_rows(part, n_clock_rows):
    """clock-row index (top of the device first) -> (bottom flag, row number)

    part.yaml enumerates which rows exist in each half.  Rows are numbered
    outward from the middle of the device, so the grid's lower clock rows are
    the 'bottom' half in ascending row order going down, and the rest are the
    'top' half in ascending row order going up.
    """
    gcr = part['global_clock_regions']
    bottom_rows = sorted(int(r) for r in gcr.get('bottom', {}).get('rows', {}))
    top_rows = sorted(int(r) for r in gcr.get('top', {}).get('rows', {}))
    assert len(bottom_rows) + len(top_rows) == n_clock_rows, (
        bottom_rows, top_rows, n_clock_rows)
    out = {}
    for i, r in enumerate(reversed(top_rows)):
        out[i] = (0, r)
    for j, r in enumerate(bottom_rows):
        out[len(top_rows) + j] = (1, r)
    return out


def part_frame_counts(part):
    """(bottom, row, bus, column) -> frame_count, straight out of part.yaml"""
    out = {}
    for half, gcr in part['global_clock_regions'].items():
        bottom = 1 if half == 'bottom' else 0
        for row, rowd in gcr['rows'].items():
            for bus, busd in rowd['configuration_buses'].items():
                for col, cold in busd['configuration_columns'].items():
                    key = (bottom, int(row), bus, int(col))
                    out[key] = cold['frame_count']
    return out


def column_gate(grid, part):
    """Check that a grid and a part.yaml describe the same device.

    The column rule holds only where the fabric spans the whole device: the
    number of anchor columns in the grid must equal the number of
    configuration columns part.yaml declares for the widest row, and the two
    must agree on how many clock-region rows there are.

    It refuses xc7z010, whose PS7 swallows 24 configuration columns down the
    left-hand side, and it is what catches a device model that was built for
    another device: it is how the committed xc7s25 and xc7s75 models were
    found to be the xc7s50 fabric (44 interconnect columns in the grid against
    the 38 and 54 their own part.yaml declares).

    Returns (ok, reason).
    """
    declared = {}
    for (_, _, bus, col) in part_frame_counts(part):
        declared[bus] = max(declared.get(bus, 0), col + 1)
    for bus in BUSES:
        n = len(anchor_columns(grid, bus))
        if n != declared.get(bus, 0):
            return False, '%s: %d grid columns against %d in part.yaml' % (
                bus, n, declared.get(bus, 0))
    n_rows = sum(
        len(half['rows']) for half in part['global_clock_regions'].values())
    if n_rows != len(clock_rows(grid)):
        return False, 'rows: %d HCLK rows in the grid against %d in part.yaml' % (
            len(clock_rows(grid)), n_rows)
    return True, 'ok'


class Conflict(collections.namedtuple(
        'Conflict', 'tile_type row_position bus alternatives resolution')):
    """Reference models that disagree on the geometry of one tile type.

    `alternatives` is a list of (geometry, [devices], outside_votes), the one
    that won first.  `resolution` says how it won: 'majority' (most devices in
    the family), 'preferred reference' (the family was split evenly and a
    reference named with --prefer-reference was one of the tied ones),
    'other families' (the family was split evenly and the models of the
    other families broke the tie) or 'arbitrary' (nothing broke the tie, so
    the alphabetically first tied reference won -- a fixed rule, never the
    order the references were given in).
    """

    def describe(self):
        winner_devices = self.alternatives[0][1]
        if self.resolution == 'arbitrary':
            headline = (
                '%s row_position=%d %s -- no vote settled it; %s wins as '
                'the alphabetically first tied reference' % (
                    self.tile_type, self.row_position, self.bus,
                    winner_devices[0]))
        elif self.resolution == 'preferred reference':
            headline = (
                '%s row_position=%d %s -- settled by the preferred '
                'reference (%s)' % (
                    self.tile_type, self.row_position, self.bus,
                    ' '.join(winner_devices)))
        else:
            headline = '%s row_position=%d %s -- resolved by %s' % (
                self.tile_type, self.row_position, self.bus, self.resolution)
        lines = [headline]
        for geom, devices, outside in self.alternatives:
            lines.append(
                '    %-40s %s%s' % (
                    json.dumps(geom, sort_keys=True), ' '.join(devices),
                    ' (+%d elsewhere)' % outside if outside else ''))
        return '\n'.join(lines)


class Model:
    """The frame-address law, learned from reference device models."""

    def __init__(self):
        # (bus, tile_type) -> ordered set of grid_x deltas to the anchor column
        self.deltas = collections.defaultdict(dict)
        # (tile_type, row_position, bus) -> {geometry key -> [(device, geom)]}
        self.observations = collections.defaultdict(
            lambda: collections.OrderedDict())
        self.geometry = {}
        self.conflicts = []
        self.references = []
        self.rejected = []

    def learn(self, device, grid, part):
        """Add one reference device model.  Returns (accepted, reason)."""
        ok, why = column_gate(grid, part)
        if not ok:
            self.rejected.append((device, why))
            return False, why
        rows = clock_row_of(grid)
        columns = {bus: anchor_columns(grid, bus) for bus in BUSES}
        for name, tile in sorted(grid.items()):
            if name not in rows:
                continue
            _, row_position = rows[name]
            for bus, bits in sorted(tile.get('bits', {}).items()):
                if bus not in BUSES:
                    continue
                _, _, _, column = decode_baseaddr(bits['baseaddr'])
                if column >= len(columns[bus]):
                    # Cannot place the tile in a grid column: the model and
                    # the grid disagree, so learn nothing from this tile.
                    continue
                delta = tile['grid_x'] - columns[bus][column]
                self.deltas[(bus, tile['type'])][delta] = True
                geom = {
                    'offset': bits['offset'],
                    'words': bits['words'],
                    'frames': bits['frames'],
                }
                if 'alias' in bits:
                    geom['alias'] = copy.deepcopy(bits['alias'])
                key = (tile['type'], row_position, bus)
                self.observations[key].setdefault(_geometry_key(geom),
                                                  []).append((device, geom))
        self.references.append(device)
        self.geometry = {}
        self.conflicts = []
        return True, 'ok'

    def resolve(self, tiebreaker=None, prefer=None):
        """Turn the observations into one geometry per key.

        Observations that differ only in `frames` are the same geometry seen
        in columns of different depth; the deepest wins, and apply() caps it
        again per column.  Anything else is a genuine disagreement between
        reference models, and it is resolved in this order:

        1. the geometry the most devices of the family agree on;
        2. if the family is split evenly and `prefer` names one of the tied
           references, that reference wins outright -- an explicit choice
           beats the proxy votes below, which can be stale (every older
           model may carry a value the current fuzzer no longer writes), but
           it does not beat a majority of the family itself; narrow the
           reference list for that;
        3. with nothing preferred, the geometry the models in `tiebreaker`
           agree on -- pass a model built from the *other* families, so a
           device never gets to vote on itself;
        4. if that is split too, the alphabetically first of the tied
           references wins -- a fixed rule, never the order the references
           happened to be given in -- and the conflict is marked
           'arbitrary'.

        Every disagreement is recorded in self.conflicts whichever way it
        went, because a model standing alone against the rest of the database
        is exactly what this tool is meant to surface.
        """
        self.geometry = {}
        self.conflicts = []
        for key, alternatives in sorted(self.observations.items()):
            merged = []
            for geometry_key, observations in alternatives.items():
                geom = dict(observations[0][1])
                geom['frames'] = max(g['frames'] for _, g in observations)
                devices = sorted({d for d, _ in observations})
                merged.append(
                    (
                        geom, devices,
                        _outside_votes(tiebreaker, key, geometry_key)))
            top = max(len(m[1]) for m in merged)
            leaders = [m for m in merged if len(m[1]) == top]
            resolution = 'majority'
            if len(leaders) > 1:
                preferred = [
                    m for m in leaders
                    if prefer and any(d in prefer for d in m[1])
                ]
                if len(preferred) == 1:
                    leaders = preferred
                    resolution = 'preferred reference'
                else:
                    best_outside = max(m[2] for m in leaders)
                    leaders = [m for m in leaders if m[2] == best_outside]
                    if best_outside and len(leaders) == 1:
                        resolution = 'other families'
                    else:
                        # Nothing broke the tie: a fixed rule, not the order
                        # the references happened to be learnt in.
                        leaders.sort(key=lambda m: m[1])
                        resolution = 'arbitrary'
            winner = leaders[0]
            self.geometry[key] = winner[0]
            if len(merged) > 1:
                ordered = [winner] + [m for m in merged if m is not winner]
                self.conflicts.append(
                    Conflict(key[0], key[1], key[2], ordered, resolution))
        return self.conflicts

    def merge(self, other):
        """Fold another Model's observations into this one."""
        for key, deltas in other.deltas.items():
            self.deltas[key].update(deltas)
        for key, alternatives in other.observations.items():
            for geometry_key, observations in alternatives.items():
                self.observations[key].setdefault(geometry_key,
                                                  []).extend(observations)
        self.references.extend(other.references)
        self.rejected.extend(other.rejected)
        self.geometry = {}
        self.conflicts = []
        return self

    def unresolved_conflicts(self):
        return [c for c in self.conflicts if c.resolution == 'arbitrary']

    def apply(self, grid, part, fallback=None):
        """Fill in the `bits` of a grid, in place.  Returns a Counter report.

        A tile type no reference model of the family carries gets no address
        at all -- unless `fallback` is given, in which case a second resolved
        model (the rest of the database) is asked for that tile type alone.
        Those entries are counted separately in the report: they are the ones
        that rest on another family behaving the same way.
        """
        if not self.geometry:
            self.resolve()
        rows = clock_row_of(grid)
        columns = {bus: anchor_columns(grid, bus) for bus in BUSES}
        row_map = part_rows(part, len(clock_rows(grid)))
        frame_counts = part_frame_counts(part)
        report = collections.Counter()
        for name, tile in sorted(grid.items()):
            if name not in rows:
                report['outside-any-clock-row'] += 1
                continue
            row_index, row_position = rows[name]
            bottom, row = row_map[row_index]
            for bus in BUSES:
                key = (tile['type'], row_position, bus)
                geom = self.geometry.get(key)
                deltas = self.deltas.get((bus, tile['type']))
                borrowed = False
                if geom is None and fallback is not None:
                    geom = fallback.geometry.get(key)
                    deltas = fallback.deltas.get((bus, tile['type']))
                    borrowed = geom is not None
                if geom is None or not deltas:
                    continue
                candidates = [tile['grid_x'] - d for d in sorted(deltas)]
                hits = [x for x in candidates if x in columns[bus]]
                if len(hits) != 1:
                    report['ambiguous-column' if hits else 'no-column'] += 1
                    continue
                column = columns[bus].index(hits[0])
                column_key = (bottom, row, bus, column)
                if column_key not in frame_counts:
                    report['column-not-in-part'] += 1
                    continue
                entry = {
                    'baseaddr':
                    encode_baseaddr(BLOCK_TYPE[bus], bottom, row, column),
                    'frames':
                    min(geom['frames'], frame_counts[column_key]),
                    'offset':
                    geom['offset'],
                    'words':
                    geom['words'],
                }
                if 'alias' in geom:
                    entry['alias'] = copy.deepcopy(geom['alias'])
                tile.setdefault('bits', {})[bus] = entry
                report['filled'] += 1
                if borrowed:
                    report['filled-from-other-families'] += 1
        return report


def _outside_votes(tiebreaker, key, geometry_key):
    """How many devices outside the family agree with one geometry."""
    if tiebreaker is None:
        return 0
    observations = tiebreaker.observations.get(key, {}).get(geometry_key, [])
    return len({device for device, _ in observations})


def _geometry_key(geom):
    """Everything but `frames`, which is a property of the column, not the tile."""
    return json.dumps(
        {k: v
         for k, v in geom.items()
         if k != 'frames'}, sort_keys=True)


def load_part(path):
    """Read a part.yaml."""
    with open(path) as f:
        return xyaml.load(f)


def load_grid(tiles_txt, pin_func_txt):
    """Build a bare grid out of what generate_tiles.tcl dumps from Vivado.

    The parser is the fuzzer's own, so a grid dumped for this tool and a grid
    dumped inside 005-tilegrid are read exactly the same way.
    """
    generate = _import_generate_005()
    return generate.make_database(
        generate.load_tiles(tiles_txt),
        generate.load_pin_functions(pin_func_txt))


def _import_generate_005():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(
        here, os.pardir, 'fuzzers', '005-tilegrid', 'generate.py')
    spec = importlib.util.spec_from_file_location('generate_005', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def diff_bits(left, right):
    """Compare the `bits` of two grids, tile by tile and bus by bus.

    Returns (Counter, [(tile_name, tile_type, bus, kind, left, right)]) where
    kind is 'identical', 'differing', 'left-only' or 'right-only'.
    """
    counter = collections.Counter()
    differences = []
    for name in sorted(set(left) | set(right)):
        if name not in left or name not in right:
            counter['left-only-tile' if name in
                    left else 'right-only-tile'] += 1
            continue
        lbits = left[name].get('bits', {})
        rbits = right[name].get('bits', {})
        tile_type = left[name]['type']
        for bus in sorted(set(lbits) | set(rbits)):
            if lbits.get(bus) == rbits.get(bus):
                counter['identical'] += 1
                continue
            if bus in lbits and bus in rbits:
                kind = 'differing'
            elif bus in lbits:
                kind = 'left-only'
            else:
                kind = 'right-only'
            counter[kind] += 1
            differences.append(
                (name, tile_type, bus, kind, lbits.get(bus), rbits.get(bus)))
    return counter, differences
