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
"""The calibration gate of utils/tilegrid_derive.py.

The synthetic tests run anywhere.  The calibration test needs a database with
device models in it -- `./download-latest-db.sh`, or XRAY_DATABASE_DIR
pointing at a prjxray-db clone -- and is skipped when there is none, because
the repository only carries the mapping files.

What the calibration asserts is deliberately one-sided: every device model
must be rebuilt byte for byte from its own grid, except the ones listed in
KNOWN_DIFFERENCES, and those may only differ in the ways recorded there.  A
device model that starts differing in a new way, or a new device model that
does not reproduce at all, fails the gate; a database that gets *more* right
than this table expects does not.
"""

import os
import unittest

from utils import tilegrid_derive
from utils import tilegrid_model

# The device models that rebuild byte for byte today, and how many bits
# entries that is in total.  Recomputed from the run, not copied by hand.
REPRODUCED = {
    ('artix7', 'xc7a100t'),
    ('artix7', 'xc7a50t'),
    ('kintex7', 'xc7k160t'),
    ('kintex7', 'xc7k325t'),
    ('kintex7', 'xc7k420t'),
    ('kintex7', 'xc7k480t'),
    ('kintex7', 'xc7k70t'),
    ('spartan7', 'xc7s50'),
    ('zynq7', 'xc7z030'),
    ('zynq7', 'xc7z045'),
    ('zynq7', 'xc7z100'),
}
REPRODUCED_ENTRIES = 500405

# Device models that cannot be rebuilt exactly, with the reason, and the
# (tile type, kind) pairs the difference is allowed to appear in.
KNOWN_DIFFERENCES = {
    ('artix7', 'xc7a200t'): (
        'the only artix7 device with GTP transceivers in the middle of the '
        'die, so no other artix7 model can teach their geometry', {
            ('GTP_CHANNEL_0_MID_LEFT', 'right-only'),
            ('GTP_CHANNEL_0_MID_RIGHT', 'right-only'),
            ('GTP_CHANNEL_1_MID_LEFT', 'right-only'),
            ('GTP_CHANNEL_1_MID_RIGHT', 'right-only'),
            ('GTP_CHANNEL_2_MID_LEFT', 'right-only'),
            ('GTP_CHANNEL_2_MID_RIGHT', 'right-only'),
            ('GTP_CHANNEL_3_MID_LEFT', 'right-only'),
            ('GTP_CHANNEL_3_MID_RIGHT', 'right-only'),
            ('GTP_COMMON_MID_LEFT', 'right-only'),
            ('GTP_COMMON_MID_RIGHT', 'right-only'),
            ('GTP_INT_INTERFACE_L', 'right-only'),
            ('GTP_INT_INTERFACE_R', 'right-only')
        }),
    ('zynq7', 'xc7z020'): (
        'the only zynq7 device model with a right-hand high-range I/O column '
        '(xc7z010 has one but is refused), so nothing teaches which side of '
        'those tiles their interconnect column is on', {
            ('HCLK_IOI3', 'right-only'), ('RIOB33', 'right-only'),
            ('RIOB33_SING', 'right-only'), ('RIOI3', 'right-only'),
            ('RIOI3_SING', 'right-only'), ('RIOI3_TBYTESRC', 'right-only'),
            ('RIOI3_TBYTETERM', 'right-only')
        }),
    ('spartan7', 'xc7s25'): (
        'MONITOR_BOT_FUJI2 exists on no other spartan7 device, and the six '
        'upper *_SING tiles carry the alias start_offset 2 that '
        'generate_full.py has written since the VC707 fix while every older '
        'committed model still says 0', {
            ('MONITOR_BOT_FUJI2', 'right-only'), ('LIOB33_SING', 'differing'),
            ('LIOI3_SING', 'differing'), ('RIOB33_SING', 'differing'),
            ('RIOI3_SING', 'differing')
        }),
    ('spartan7', 'xc7s100'): (
        'built before prjxray#16, so it carries the fingerprint of the '
        'site-type-off-a-placed-design bug: CLK_BUFG_BOT_R measured five '
        'words high, no address for CFG_CENTER_MID, and five LIOB33 tiles '
        'the iob sub-fuzzer skipped', {
            ('CLK_BUFG_BOT_R', 'differing'), ('CFG_CENTER_MID', 'left-only'),
            ('LIOB33', 'left-only')
        }),
}

# Device models that are not rebuilt at all, and why.
NOT_REBUILT = {
    ('zynq7', 'xc7z010'): 'refused',
    ('virtex7', 'xc7vx485t'): 'skipped',
}


def database_dir():
    """The database to calibrate against, or None."""
    candidates = [os.getenv('XRAY_DATABASE_DIR')]
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, os.pardir, 'database'))
    for candidate in candidates:
        if not candidate or not os.path.isdir(candidate):
            continue
        if any(tilegrid_derive.device_models(candidate)):
            return candidate
    return None


def synthetic_device(columns=2, rows=1):
    """A grid and a part.yaml body for a device with plain CLB columns only."""
    grid = {}
    for row in range(rows):
        top = row * 51
        for y in range(top, top + 51):
            for column in range(columns):
                x = column * 2
                hclk = y == top + 25
                grid['CLBLL_L_X%dY%d' % (x, y)] = {
                    'type': 'HCLK_CLB' if hclk else 'CLBLL_L',
                    'grid_x': x,
                    'grid_y': y,
                    'sites': {},
                    'bits': {},
                }
                grid['INT_L_X%dY%d' % (x + 1, y)] = {
                    'type': 'HCLK_L' if hclk else 'INT_L',
                    'grid_x': x + 1,
                    'grid_y': y,
                    'sites': {},
                    'bits': {},
                }
    part = {
        'global_clock_regions': {
            'top': {
                'rows': {
                    row: {
                        'configuration_buses': {
                            'CLB_IO_CLK': {
                                'configuration_columns': {
                                    column: {
                                        'frame_count': 36
                                    }
                                    for column in range(columns)
                                }
                            }
                        }
                    }
                    for row in range(rows)
                }
            }
        }
    }
    return grid, part


def address_synthetic(grid, part):
    """Fill a synthetic grid the way the law says it should come out."""
    rows = tilegrid_model.clock_row_of(grid)
    row_map = tilegrid_model.part_rows(
        part, len(tilegrid_model.clock_rows(grid)))
    columns = tilegrid_model.anchor_columns(grid, 'CLB_IO_CLK')
    for name, tile in grid.items():
        row_index, row_position = rows[name]
        bottom, row = row_map[row_index]
        anchor = tile['grid_x'] if tile['type'].startswith(
            ('INT_L', 'HCLK_L')) else tile['grid_x'] + 1
        tile['bits'] = {
            'CLB_IO_CLK': {
                'baseaddr':
                tilegrid_model.encode_baseaddr(
                    0, bottom, row, columns.index(anchor)),
                'frames':
                36,
                'offset':
                2 * row_position,
                'words':
                2,
            }
        }
    return grid


class TestLaw(unittest.TestCase):
    """The parts of the law that need no database."""

    def test_baseaddr_round_trip(self):
        for fields in ((0, 0, 0, 0), (0, 1, 0, 19), (1, 0, 3, 41), (1, 1, 15,
                                                                    1023)):
            self.assertEqual(
                tilegrid_model.decode_baseaddr(
                    tilegrid_model.encode_baseaddr(*fields)), fields)

    def test_column_gate_counts_columns(self):
        grid, part = synthetic_device(columns=3)
        self.assertEqual(tilegrid_model.column_gate(grid, part), (True, 'ok'))
        wider, _ = synthetic_device(columns=4)
        ok, why = tilegrid_model.column_gate(wider, part)
        self.assertFalse(ok)
        self.assertIn('4 grid columns against 3', why)

    def test_learn_and_reapply(self):
        """The law learnt off a device rebuilds that device exactly."""
        reference, part = synthetic_device(columns=3, rows=2)
        address_synthetic(reference, part)
        model = tilegrid_model.Model()
        accepted, why = model.learn('synthetic', reference, part)
        self.assertTrue(accepted, why)
        model.resolve()
        self.assertEqual(model.conflicts, [])

        target, target_part = synthetic_device(columns=3, rows=2)
        report = model.apply(target, target_part)
        self.assertEqual(report['filled'], len(target))
        counter, differences = tilegrid_model.diff_bits(target, reference)
        self.assertEqual(differences, [])
        self.assertEqual(counter['identical'], len(target))

    def test_unknown_tile_type_gets_no_address(self):
        """A tile type no reference carries is left alone, never guessed."""
        reference, part = synthetic_device(columns=3)
        address_synthetic(reference, part)
        model = tilegrid_model.Model()
        model.learn('synthetic', reference, part)
        model.resolve()

        target, target_part = synthetic_device(columns=3)
        target['DSP_R_X0Y10'] = {
            'type': 'DSP_R',
            'grid_x': 0,
            'grid_y': 10,
            'sites': {},
            'bits': {},
        }
        model.apply(target, target_part)
        self.assertEqual(target['DSP_R_X0Y10']['bits'], {})

    def tied_model(self, learn_order, prefer=None):
        """Two references that disagree on every geometry, learnt in the
        given order; the resolved model."""
        model = tilegrid_model.Model()
        for device, offset in learn_order:
            grid, part = synthetic_device(columns=3)
            address_synthetic(grid, part)
            for tile in grid.values():
                tile['bits']['CLB_IO_CLK']['offset'] = offset
            model.learn(device, grid, part)
        model.resolve(prefer=prefer)
        return model

    def test_a_tie_of_two_goes_to_the_first_alphabetically(self):
        """A tie no vote can settle is deterministic: the alphabetically
        first tied reference wins, in whichever order the references were
        learnt."""
        for learn_order in (
            [('ref-b', 100), ('ref-a', 200)],
            [('ref-a', 200), ('ref-b', 100)],
        ):
            model = self.tied_model(learn_order)
            self.assertTrue(model.conflicts)
            self.assertEqual(
                {c.resolution
                 for c in model.conflicts}, {'arbitrary'})
            self.assertEqual(
                len(model.unresolved_conflicts()), len(model.conflicts))
            for geometry in model.geometry.values():
                self.assertEqual(geometry['offset'], 200)  # ref-a's
            self.assertIn('ref-a', model.conflicts[0].describe())

    def test_preferred_reference_wins_a_tie(self):
        """A named reference beats the deterministic pick, and is recorded."""
        model = self.tied_model(
            [('ref-b', 100), ('ref-a', 200)], prefer=['ref-b'])
        self.assertEqual(
            {c.resolution
             for c in model.conflicts}, {'preferred reference'})
        self.assertEqual(model.unresolved_conflicts(), [])
        for geometry in model.geometry.values():
            self.assertEqual(geometry['offset'], 100)

    def test_preferred_references_that_split_settle_nothing(self):
        """A preference naming both sides of the tie settles nothing, and
        one naming neither side is ignored."""
        for prefer in (['ref-a', 'ref-b'], ['ref-c']):
            model = self.tied_model(
                [('ref-b', 100), ('ref-a', 200)], prefer=prefer)
            self.assertEqual(
                {c.resolution
                 for c in model.conflicts}, {'arbitrary'})
            for geometry in model.geometry.values():
                self.assertEqual(geometry['offset'], 200)


@unittest.skipIf(database_dir() is None, 'no database with device models')
class TestCalibration(unittest.TestCase):
    """Leave-one-out reproduction of every device model in the database."""

    @classmethod
    def setUpClass(cls):
        cls.results = {
            (r.family, r.device): r
            for r in tilegrid_derive.calibrate(database_dir())
        }

    def test_every_device_model_is_accounted_for(self):
        for key, result in sorted(self.results.items()):
            if key in NOT_REBUILT:
                self.assertEqual(result.verdict, NOT_REBUILT[key], key)
            elif key in KNOWN_DIFFERENCES:
                self.assertIn(result.verdict, ('exact', 'differs'), key)
            else:
                self.assertEqual(
                    result.verdict, 'exact',
                    '%s does not rebuild byte for byte; if that is expected, '
                    'record it in KNOWN_DIFFERENCES with the reason' % (key, ))

    def test_the_recorded_device_models_still_reproduce(self):
        for key in sorted(REPRODUCED):
            self.assertIn(key, self.results)
            self.assertEqual(self.results[key].verdict, 'exact', key)
        reproduced = sum(
            r.counter['identical']
            for r in self.results.values()
            if r.verdict == 'exact')
        self.assertGreaterEqual(reproduced, REPRODUCED_ENTRIES)

    def test_known_differences_stay_where_they_are(self):
        for key, (reason, allowed) in sorted(KNOWN_DIFFERENCES.items()):
            if key not in self.results:
                continue
            seen = {
                (tile_type, kind)
                for _, tile_type, _, kind, _, _ in self.results[key].
                differences
            }
            self.assertTrue(
                seen <= allowed,
                '%s differs in a new way (%s); the recorded reason is: %s' %
                (key, sorted(seen - allowed), reason))

    def test_no_geometry_is_settled_by_a_coin_toss(self):
        for key, result in sorted(self.results.items()):
            if result.model is None:
                continue
            self.assertEqual(
                [c.describe() for c in result.model.unresolved_conflicts()],
                [], key)


if __name__ == '__main__':
    unittest.main()
