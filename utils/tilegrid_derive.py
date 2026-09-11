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
"""Derive a device tilegrid from a Vivado grid dump, and check the law it uses.

Three commands:

calibrate
    Leave one device model out of the database, learn the frame-address law
    from the rest of its family, rebuild the model from its grid alone and
    diff it against the committed file.  Needs no Vivado.  This is the gate:
    a law that cannot rebuild the models we already trust has no business
    building one we cannot check.

derive
    Apply the law to a grid dumped from Vivado (fuzzers/005-tilegrid's own
    generate_tiles.tcl writes it) and write a tilegrid.json.

compare
    Diff the `bits` of two tilegrid.json files, tile by tile.

The intended use is as a second opinion on 005-tilegrid: run the fuzzer,
derive the same device, and compare.  Where the two agree the model is
measured twice over; where they disagree one of them is wrong, and the
disagreement says which tile to look at.  Running `derive` against the
committed model of a device that was never fuzzed is also how a model built
for the wrong device shows itself -- that is how the committed xc7s25 and
xc7s75 models were caught carrying the xc7s50 fabric.

Examples::

    utils/tilegrid_derive.py calibrate --database-dir database
    utils/tilegrid_derive.py derive --db-root database/spartan7 \\
        --part xc7s25csga324-1 --tiles tiles.txt --pin-func pin_func.txt \\
        --output xc7s25-derived.json
    utils/tilegrid_derive.py compare database/spartan7/xc7s25/tilegrid.json \\
        xc7s25-derived.json --labels fuzzed derived
"""

import argparse
import collections
import json
import os
import sys

from prjxray import util
from utils import tilegrid_model
from utils import xjson

# A device model lives in <family>/<device>/tilegrid.json; the frame layout it
# has to be checked against lives in the part.yaml of one of that device's
# parts.  Only the fully fuzzed part carries global_clock_regions, the others
# are stubs, so picking the first such part in sorted order is deterministic
# and picks the same part on every run.
TILEGRID = 'tilegrid.json'
PART_YAML = 'part.yaml'


def device_models(database_dir, family=None):
    """Yield (family, device) for every device model in a database."""
    for fam in sorted(os.listdir(database_dir)):
        if family is not None and fam != family:
            continue
        family_dir = os.path.join(database_dir, fam)
        if not os.path.isdir(family_dir):
            continue
        for device in sorted(os.listdir(family_dir)):
            if os.path.isfile(os.path.join(family_dir, device, TILEGRID)):
                yield fam, device


def part_of(family_dir, device):
    """The part whose part.yaml carries the frame layout of `device`."""
    for entry in sorted(os.listdir(family_dir)):
        if not entry.startswith(device) or entry == device:
            continue
        path = os.path.join(family_dir, entry, PART_YAML)
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            if 'global_clock_regions' in f.read():
                return entry
    return None


def read_grid(path):
    with open(path) as f:
        return json.load(f)


def strip_bits(grid):
    """A copy of a grid with every frame address removed."""
    bare = json.loads(json.dumps(grid))
    for tile in bare.values():
        tile['bits'] = {}
    return bare


def learn(model, family_dir, device):
    """Add one device model of one family to `model`.  Returns (ok, why)."""
    part = part_of(family_dir, device)
    if part is None:
        model.rejected.append((device, 'no part.yaml with a frame layout'))
        return False, 'no part.yaml with a frame layout'
    grid = read_grid(os.path.join(family_dir, device, TILEGRID))
    part_yaml = tilegrid_model.load_part(
        os.path.join(family_dir, part, PART_YAML))
    return model.learn(device, grid, part_yaml)


def learn_references(family_dir, references, elsewhere=None, prefer=None):
    """Learn the law of one family from the named device models.

    `prefer` names references that win a family tie outright; the
    calibration gate passes none, because a gate with a preference is
    measuring the preference.
    """
    model = tilegrid_model.Model()
    for device in references:
        learn(model, family_dir, device)
    model.resolve(elsewhere, prefer)
    return model


def learn_families(database_dir):
    """family -> a Model holding every device model of that family."""
    models = {}
    for family, device in device_models(database_dir):
        model = models.setdefault(family, tilegrid_model.Model())
        learn(model, os.path.join(database_dir, family), device)
    return models


def learn_elsewhere(family_models, family):
    """One resolved Model holding every device model of the OTHER families.

    It settles ties inside a family, and -- only where asked to -- lends a
    geometry for a tile type the family itself has no reference for.  Keeping
    the family out of it is what makes calibration a real leave-one-out: a
    device never votes on itself, not even through a sibling.
    """
    model = tilegrid_model.Model()
    for other, other_model in sorted(family_models.items()):
        if other != family:
            model.merge(other_model)
    model.resolve()
    return model


def print_rejected(model, indent=''):
    for device, why in model.rejected:
        print('%snot used as a reference: %s (%s)' % (indent, device, why))


def print_conflicts(model, indent=''):
    if not model.conflicts:
        return
    print(
        '%s%d tile geometries the reference models disagree on '
        '(the winner is listed first):' % (indent, len(model.conflicts)))
    for conflict in model.conflicts:
        for line in conflict.describe().split('\n'):
            print('%s%s' % (indent, line))


def difference_breakdown(differences):
    """(tile_type, kind) -> count, for the per-type table."""
    counter = {}
    for _, tile_type, _, kind, _, _ in differences:
        counter[(tile_type, kind)] = counter.get((tile_type, kind), 0) + 1
    return counter


Calibration = collections.namedtuple(
    'Calibration',
    'family device part verdict reason counter differences report model notes')

HEADER = (
    '%-9s %-11s %-9s %-20s %8s %9s %9s %9s %9s' % (
        'family', 'device', 'verdict', 'part', 'entries', 'identical',
        'differing', 'missing', 'extra'))


def calibrate(database_dir, family=None, device=None, fallback=False):
    """Leave one device model out at a time and rebuild it from its grid.

    Yields one Calibration per device model.  The verdict is 'exact' when the
    rebuilt model matches the committed one byte for byte, 'differs' when it
    does not, 'refused' when the committed model does not match its own
    part.yaml, and 'skipped' when there is nothing to learn from.
    """
    by_family = {}
    for fam, dev in device_models(database_dir):
        by_family.setdefault(fam, []).append(dev)
    family_models = learn_families(database_dir)
    elsewhere = {}

    for fam, dev in device_models(database_dir, family):
        if device is not None and dev != device:
            continue
        family_dir = os.path.join(database_dir, fam)
        with open(os.path.join(family_dir, dev, TILEGRID), 'rb') as f:
            committed_bytes = f.read()

        notes = []
        references = []
        for other in by_family[fam]:
            if other == dev:
                continue
            with open(os.path.join(family_dir, other, TILEGRID), 'rb') as f:
                if f.read() == committed_bytes:
                    notes.append(
                        '%s is a byte copy of this model, not used as a '
                        'reference' % other)
                    continue
            references.append(other)

        part = part_of(family_dir, dev)
        if not references or part is None:
            reason = (
                'no other device model in the family'
                if not references else 'no part.yaml with a frame layout')
            yield Calibration(
                fam, dev, part, 'skipped', reason, collections.Counter(), [],
                collections.Counter(), None, notes)
            continue

        if fam not in elsewhere:
            elsewhere[fam] = learn_elsewhere(family_models, fam)
        model = learn_references(family_dir, references, elsewhere[fam])
        committed = json.loads(committed_bytes.decode('utf-8'))
        part_yaml = tilegrid_model.load_part(
            os.path.join(family_dir, part, PART_YAML))

        ok, why = tilegrid_model.column_gate(committed, part_yaml)
        if not ok:
            yield Calibration(
                fam, dev, part, 'refused', why, collections.Counter(), [],
                collections.Counter(), model, notes)
            continue

        derived = strip_bits(committed)
        report = model.apply(
            derived, part_yaml, elsewhere[fam] if fallback else None)
        counter, differences = tilegrid_model.diff_bits(derived, committed)
        exact = not (
            counter['differing'] or counter['left-only']
            or counter['right-only'])
        yield Calibration(
            fam, dev, part, 'exact' if exact else 'differs', '', counter,
            differences, report, model, notes)


def cmd_calibrate(args):
    print(HEADER)
    verdicts = {}
    for result in calibrate(args.database_dir, args.family, args.device,
                            args.cross_family_fallback):
        for note in result.notes:
            print('%-9s %-11s note: %s' % (result.family, result.device, note))
        verdicts[(result.family, result.device)] = (
            result.verdict, result.counter['identical'])
        if result.verdict in ('skipped', 'refused'):
            print(
                '%-9s %-11s %-9s %-20s %s' % (
                    result.family, result.device, result.verdict, result.part
                    or '', result.reason))
            continue
        print(
            '%-9s %-11s %-9s %-20s %8d %9d %9d %9d %9d' % (
                result.family, result.device, result.verdict, result.part,
                result.counter['identical'] + len(result.differences),
                result.counter['identical'], result.counter['differing'],
                result.counter['right-only'], result.counter['left-only']))
        for kind in ('no-column', 'ambiguous-column', 'column-not-in-part',
                     'filled-from-other-families'):
            if result.report[kind]:
                print('    %-26s %d tiles' % (kind, result.report[kind]))
        if result.verdict != 'exact' or args.verbose:
            for (tile_type, kind), count in sorted(difference_breakdown(
                    result.differences).items()):
                print('    %-40s %-10s %d' % (tile_type, kind, count))
        if args.verbose:
            print_rejected(result.model, '    ')
            print_conflicts(result.model, '    ')
        elif result.model.unresolved_conflicts():
            print(
                '    %d tile geometries no vote could settle; run with '
                '--verbose' % len(result.model.unresolved_conflicts()))

    counts = {}
    for verdict in verdicts.values():
        counts[verdict[0]] = counts.get(verdict[0], 0) + 1
    reproduced = sum(n for v, n in verdicts.values() if v == 'exact')
    print(
        'summary: %d device models, %s; %d bits entries reproduced byte for '
        'byte' % (
            len(verdicts), ', '.join(
                '%d %s' % (n, v) for v, n in sorted(counts.items())),
            reproduced))
    return 0


def cmd_derive(args):
    family_dir = os.path.abspath(args.db_root)
    database_dir = os.path.dirname(family_dir)
    family = os.path.basename(family_dir)
    family_devices = [d for _, d in device_models(database_dir, family)]

    # A device never derives itself: drop the fabric this part already maps
    # to, so re-deriving a committed model really is a second opinion.
    try:
        own = util.get_fabric_for_part(family_dir, args.part)
    except (AssertionError, KeyError):
        own = None
    references = args.reference
    if not references:
        references = [d for d in family_devices if d != own]
        print('references: %s' % (' '.join(references) or 'none'))
    elif own in references:
        print(
            'warning: %s is the fabric %s already maps to; deriving it from '
            'itself proves nothing' % (own, args.part))
    prefer = args.prefer_reference
    not_references = [d for d in prefer if d not in references]
    if not_references:
        print(
            'ERROR: --prefer-reference %s, but the references are: %s' %
            (' '.join(not_references), ' '.join(references) or 'none'),
            file=sys.stderr)
        return 1
    part_yaml = tilegrid_model.load_part(
        os.path.join(family_dir, args.part, PART_YAML))

    if args.grid:
        grid = strip_bits(read_grid(args.grid))
    else:
        grid = tilegrid_model.load_grid(args.tiles, args.pin_func)
    print('grid: %d tiles from %s' % (len(grid), args.grid or args.tiles))

    family_models = learn_families(database_dir)
    elsewhere = learn_elsewhere(family_models, family)
    model = learn_references(family_dir, references, elsewhere, prefer)
    print('law learnt from %s' % ' '.join(model.references))
    print_rejected(model)
    print_conflicts(model)

    ok, why = tilegrid_model.column_gate(grid, part_yaml)
    print('column gate against %s: %s' % (args.part, why))
    if not ok:
        print(
            'ERROR: the grid and the part.yaml describe different devices, '
            'so the column rule does not hold here.',
            file=sys.stderr)
        return 1

    rows = tilegrid_model.clock_row_of(grid)
    used = set()
    for name, tile in grid.items():
        if name not in rows:
            continue
        _, row_position = rows[name]
        for bus in tilegrid_model.BUSES:
            used.add((tile['type'], row_position, bus))
    unsettled = [
        c for c in model.unresolved_conflicts()
        if (c.tile_type, c.row_position, c.bus) in used
    ]
    if unsettled:
        if not args.allow_reference_conflicts:
            print(
                'ERROR: %d tile geometries this grid uses are ones the '
                'reference models disagree on and no vote could settle; '
                'narrow --reference, name the one you trust with '
                '--prefer-reference, or pass --allow-reference-conflicts to '
                'take the deterministic pick.' % len(unsettled),
                file=sys.stderr)
            return 1
        print(
            'WARNING: %d tile geometries this grid uses rest on a pick no '
            'vote settled, taken because --allow-reference-conflicts was '
            'given:' % len(unsettled))
        for conflict in unsettled:
            for line in conflict.describe().split('\n'):
                print('    %s' % line)

    report = model.apply(
        grid, part_yaml, elsewhere if args.cross_family_fallback else None)
    unplaced = ', '.join(
        '%s %d' % (k, report[k])
        for k in ('no-column', 'ambiguous-column', 'column-not-in-part')
        if report[k])
    print(
        'filled %d frame addresses; %s' %
        (report['filled'], unplaced or 'no tile left unplaced'))
    if report['filled-from-other-families']:
        print(
            '%d of them borrowed from the other families, for tile types this '
            'family has no reference for' %
            report['filled-from-other-families'])
    without_bits = {t['type'] for t in grid.values() if not t.get('bits')}
    addressed = {key[0] for key in elsewhere.observations}
    addressed |= {key[0] for key in model.observations}
    notable = sorted(without_bits & addressed)
    print(
        '%d tile types got no frame address; %d of them are addressed on '
        'other devices in this database%s' % (
            len(without_bits), len(notable),
            ': ' + ' '.join(notable) if notable else ''))
    with open(args.output, 'w') as f:
        xjson.pprint(f, grid)
    print('wrote %s' % args.output)
    return 0


def cmd_compare(args):
    left = read_grid(args.left)
    right = read_grid(args.right)
    llabel, rlabel = args.labels
    counter, differences = tilegrid_model.diff_bits(left, right)
    print(
        '%s: %d tiles, %s: %d tiles, same tile names: %s' %
        (llabel, len(left), rlabel, len(right), set(left) == set(right)))
    print(
        '%d bits entries identical, %d differing, %d only in %s, %d only in %s'
        % (
            counter['identical'], counter['differing'], counter['left-only'],
            llabel, counter['right-only'], rlabel))
    for (tile_type,
         kind), count in sorted(difference_breakdown(differences).items()):
        print('    %-40s %-12s %d' % (tile_type, kind, count))
    for name, _, bus, kind, lbits, rbits in differences[:args.examples]:
        print('  %s %s (%s)' % (name, bus, kind))
        print('    %-8s %s' % (llabel, json.dumps(lbits, sort_keys=True)))
        print('    %-8s %s' % (rlabel, json.dumps(rbits, sort_keys=True)))
    return 1 if differences else 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__.split('\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='\n'.join(__doc__.split('\n')[2:]))
    commands = parser.add_subparsers(dest='command')
    commands.required = True

    calibrate = commands.add_parser(
        'calibrate',
        help='leave-one-out reproduction of every device model in a database')
    calibrate.add_argument(
        '--database-dir',
        default=os.getenv('XRAY_DATABASE_DIR'),
        required=os.getenv('XRAY_DATABASE_DIR') is None,
        help='database root, the directory holding the family directories. '
        'Defaults to XRAY_DATABASE_DIR.')
    calibrate.add_argument('--family', help='only this family')
    calibrate.add_argument('--device', help='only this device model')
    calibrate.add_argument(
        '--cross-family-fallback',
        action='store_true',
        help='for a tile type the family has no reference for, borrow the '
        'geometry from the other families instead of leaving it unaddressed')
    calibrate.add_argument(
        '--verbose',
        action='store_true',
        help='list every reference and the per-tile-type breakdown')
    calibrate.set_defaults(func=cmd_calibrate)

    derive = commands.add_parser(
        'derive', help='build a tilegrid.json for a device from its grid')
    util.db_root_arg(derive)
    util.part_arg(derive)
    derive.add_argument(
        '--tiles', help='tiles.txt, as written by 005-tilegrid')
    derive.add_argument(
        '--pin-func', help='pin_func.txt, as written by 005-tilegrid')
    derive.add_argument(
        '--grid',
        help='take the grid from an existing tilegrid.json instead of a dump; '
        'its frame addresses are discarded')
    derive.add_argument(
        '--reference',
        action='append',
        default=[],
        help='device model to learn the law from; repeatable, and a comma '
        'separated list is accepted. Defaults to every device model of the '
        'family except the one this part is already a part of.')
    derive.add_argument(
        '--prefer-reference',
        action='append',
        default=[],
        help='reference device whose geometry wins when the family vote '
        'ties, before the other families are asked; repeatable, and a comma '
        'separated list is accepted. Does not override a majority of the '
        'family; narrow --reference for that.')
    derive.add_argument(
        '--output', required=True, help='tilegrid.json to write')
    derive.add_argument(
        '--cross-family-fallback',
        action='store_true',
        help='for a tile type the family has no reference for, borrow the '
        'geometry from the other families instead of leaving it unaddressed')
    derive.add_argument(
        '--allow-reference-conflicts',
        action='store_true',
        help='derive even where the reference models disagree and no vote '
        'could settle it; the pick is deterministic (the alphabetically '
        'first tied reference) and is printed')
    derive.set_defaults(func=cmd_derive)

    compare = commands.add_parser(
        'compare', help='diff the frame addresses of two tilegrid.json files')
    compare.add_argument('left', help='a tilegrid.json')
    compare.add_argument('right', help='another tilegrid.json')
    compare.add_argument(
        '--labels', nargs=2, default=['left', 'right'], help='names to print')
    compare.add_argument(
        '--examples',
        type=int,
        default=8,
        help='how many differing entries to print in full')
    compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    if args.command == 'derive':
        if args.grid and (args.tiles or args.pin_func):
            parser.error('--grid and --tiles/--pin-func are alternatives')
        if not args.grid and not (args.tiles and args.pin_func):
            parser.error('give either --grid or both --tiles and --pin-func')
        flat = []
        for reference in args.reference:
            flat.extend(r for r in reference.split(',') if r)
        args.reference = flat
        flat = []
        for preferred in args.prefer_reference:
            flat.extend(r for r in preferred.split(',') if r)
        args.prefer_reference = flat
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
