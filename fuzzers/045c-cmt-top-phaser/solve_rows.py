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
"""Rows of the PHASER_IN route-throughs and reference muxes of one tile type.

segmatch keeps only bits that are 1 exactly when a tag is 1, and the
reference mux is a code: "own region" sets one bit for both own inputs,
"input 1" sets one bit for own, above and below alike, and "region below,
input 0" sets none. So the rows are read off the specimens instead:

- a PHASER_IN's candidate bits are those set in some tile where it
  carried a route and in none where it did not;
- the route-through row is the candidate bits set in every tile whose
  PHASER_IN carried a route;
- an input's row is the candidate bits set in every tile whose route
  took that input, minus the route-through row; an input whose row is empty is
  written as the mux's other bits cleared.

Nothing is written, and the script fails, unless every route-through and
every input of interest (all but DQS_TO_PHASER, which these specimens
never drive) was seen in at least MIN_SEEN tiles, no bit belongs to two
PHASER_INs, at most one input has an empty row, and every tile of every
specimen is explained: for each PHASER_IN, the bits of its rows that are
set are exactly the rows of its route-through and of the input it took.

Usage: solve_rows.py SEGDATA_NAME OUT NOTES SPECIMEN_DIR...
"""
import os
import re
import sys

MIN_SEEN = 3
RT_RE = re.compile(r"^(?P<p>[^.]+)\.CMT_PHASER_IN_(?P<x>CA|DB)_RCLK\.CMT_PHASER_IN_(?P=x)_PHASEREFCLK$")
MUX_RE = re.compile(r"^(?P<p>[^.]+)\.(?P<mux>CMT_PHASERREF(?:_DOWN)?_PHASERIN_(?P<l>[ABCD]))\.(?P<src>\S+)$")
# PHASER_IN letter -> its route-through (CA or DB)
RT_OF = {"A": "CA", "C": "CA", "B": "DB", "D": "DB"}


def load(path):
    segs, cur = [], None
    with open(path) as f:
        for line in f:
            w = line.split()
            if not w:
                continue
            if w[0] == "seg":
                cur = {"bits": set(), "tags": {}}
                segs.append(cur)
            elif w[0] == "bit":
                cur["bits"].add(w[1])
            elif w[0] == "tag":
                cur["tags"][w[1]] = int(w[2])
    return segs


def main():
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    name, fn_out, fn_notes = sys.argv[1:4]
    segs = []
    for d in sys.argv[4:]:
        p = os.path.join(d, "segdata_{}.txt".format(name))
        if os.path.exists(p):
            segs.extend(load(p))
    errors, notes, rows = [], [], {}
    if not segs:
        errors.append("no segments")
    tags = sorted(set(t for s in segs for t in s["tags"]))

    groups = {}  # route-through tag -> [mux input tags]
    for t in tags:
        m = RT_RE.match(t)
        if m:
            groups.setdefault(t, [])
    for t in tags:
        m = MUX_RE.match(t)
        if m:
            rt = "{}.CMT_PHASER_IN_{x}_RCLK.CMT_PHASER_IN_{x}_PHASEREFCLK".format(
                m.group("p"), x=RT_OF[m.group("l")])
            groups.setdefault(rt, []).append(t)

    def on(tag):
        return [s for s in segs if s["tags"].get(tag) == 1]

    group_bits = {}
    for rt, inputs in sorted(groups.items()):
        have = on(rt)
        if len(have) < MIN_SEEN:
            errors.append("{}: seen in {} tiles, need {}".format(rt, len(have), MIN_SEEN))
            continue
        # A PHASER_IN's candidate bits: set in some tile where it carried a
        # route, never in one where it did not. That keeps out the other
        # PHASER_IN's bits and anything else the tiles happen to share.
        cand = set().union(*[s["bits"] for s in have]) - set().union(
            *[s["bits"] for s in segs if s["tags"].get(rt) == 0])
        rt_row = set.intersection(*[s["bits"] for s in have]) & cand
        rows[rt] = rt_row
        empty = []
        mux_bits = set()
        for t in inputs:
            if "DQS_TO_PHASER" in t:
                notes.append("not solved, never driven: " + t)
                continue
            seen = on(t)
            if len(seen) < MIN_SEEN:
                errors.append("{}: seen in {} tiles, need {}".format(t, len(seen), MIN_SEEN))
                continue
            row = (set.intersection(*[s["bits"] for s in seen]) & cand) - rt_row
            rows[t] = row
            mux_bits |= row
            if not row:
                empty.append(t)
        if len(empty) > 1:
            errors.append("more than one input with no bits: " + " ".join(empty))
        for t in empty:
            rows[t] = {"!" + b for b in mux_bits}
        group_bits[rt] = rt_row | mux_bits
        notes.append("{}: route-through {} from {} tiles".format(rt, " ".join(sorted(rt_row)), len(have)))

    owners = {}
    for rt, bits in group_bits.items():
        for b in bits:
            if b in owners:
                errors.append("bit {} in both {} and {}".format(b, owners[b], rt))
            owners[b] = rt
    if errors:
        for e in errors:
            print("{}: {}".format(name, e), file=sys.stderr)
        print("{}: nothing written".format(name), file=sys.stderr)
        sys.exit(1)

    for i, s in enumerate(segs):
        for rt, inputs in groups.items():
            if rt not in group_bits:
                continue
            got = s["bits"] & group_bits[rt]
            want = set()
            if s["tags"].get(rt) == 1:
                want |= rows[rt]
                for t in inputs:
                    if s["tags"].get(t) == 1 and t in rows:
                        want |= {b for b in rows[t] if not b.startswith("!")}
            if got != want:
                errors.append("segment {} {}: rows predict {} but has {}".format(
                    i, rt, sorted(want), sorted(got)))
    if errors:
        for e in errors[:20]:
            print("{}: {}".format(name, e), file=sys.stderr)
        print("{}: {} segments disagree; nothing written".format(name, len(errors)), file=sys.stderr)
        sys.exit(1)

    notes.append("{} rows, checked against {} segments".format(len(rows), len(segs)))
    with open(fn_out, "w") as f:
        for t in sorted(rows):
            bits = sorted(rows[t], key=lambda b: b.lstrip("!"))
            f.write("{} {}\n".format(t, " ".join(bits)))
    with open(fn_notes, "w") as f:
        for n in notes:
            f.write(n + "\n")
    for n in notes:
        print("  " + n, file=sys.stderr)


if __name__ == "__main__":
    main()
