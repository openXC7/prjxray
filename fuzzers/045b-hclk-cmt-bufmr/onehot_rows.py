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
"""Rows for HCLK_CMT_MUX_PHSR_PERFCLK<m>.HCLK_CMT_PHASERIN_RCLK<n>.

segmatch keeps only the bits that are 1 exactly when a tag is 1. Every bit
of these 16 pips is shared with others: a source bit per RCLK<n> (common to
the four PERFCLK<m>), and a row/column code per PERFCLK<m> that the MMCM
inputs of the same mux use too. So segmatch gives them one bit, or none
(<0 candidates> for all four RCLK2 positions).

The onehot_perf specimens (specimen_P_*) have exactly one of these pips per
HCLK_CMT tile, with the route fixed by generate.tcl. A pip's row is the
bits set in every tile, of any specimen, that has the pip, minus the bits
set in every one-hot tile (the BUFMRCE site and its pad, which all of them
share).

Nothing is written, and the script fails, unless:

- all 16 pips have a row, each from at least MIN_ONEHOT one-hot tiles that
  have it and no other of the 16;
- no row has a bit of a seed-database row outside this mux (a correlation
  with an existing row is not a new row: if one is left after the
  intersection, the population can't tell them apart);
- every bit common to all one-hot tiles belongs to a row, of the seed
  database or of SEGBITS_IN, so no PHASER_IN bit is lost in the
  subtraction;
- the rows explain every tile of every specimen: in each HCLK_CMT tile,
  the union of the rows of the pips routed there equals the bits of those
  rows that are set.

Usage:
  onehot_rows.py FAMILY SEGBITS_IN SEGBITS_OUT NOTES SEED_DB SPECIMEN_DIR...

FAMILY is hclk_cmt or hclk_cmt_l. SEGBITS_IN is filter_rdb.py's output for
it: its PHASERIN rows are replaced and its other rows copied unchanged.
SEED_DB is the database's segbits file for FAMILY. The specimen
directories are the ones segmatch was given. What was done is appended to
NOTES.
"""
import os
import re
import sys

TAG_RE = re.compile(
    r"^HCLK_CMT\.HCLK_CMT_MUX_PHSR_PERFCLK[0-9]\.HCLK_CMT_PHASERIN_RCLK[0-9]$")
EXPECTED = [
    "HCLK_CMT.HCLK_CMT_MUX_PHSR_PERFCLK{}.HCLK_CMT_PHASERIN_RCLK{}".format(m, n)
    for m in range(4) for n in range(4)
]

# A pip needs this many one-hot tiles before its row is trusted.
MIN_ONEHOT = 4


def load_segdata(path):
    segs = []
    cur = None
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


def row_bits(lines, skip_phsr):
    """Bits of segbits lines, optionally without the PHSR_PERFCLK mux's."""
    bits = set()
    for line in lines:
        w = line.split()
        if len(w) < 2 or (skip_phsr and ".HCLK_CMT_MUX_PHSR_PERFCLK" in w[0]):
            continue
        bits |= {b.lstrip("!") for b in w[1:]}
    return bits


def fail(errors, family):
    for e in errors:
        print("{}: {}".format(family, e), file=sys.stderr)
    print("{}: nothing written".format(family), file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 7:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    family, fn_in, fn_out, fn_notes, fn_seed = sys.argv[1:6]
    specimens = sys.argv[6:]
    notes = []

    segfile = "segdata_{}.txt".format(family)
    all_segs, onehot_segs = [], []
    for d in specimens:
        segs = load_segdata(os.path.join(d, segfile))
        all_segs.extend(segs)
        if os.path.basename(os.path.normpath(d)).startswith("specimen_P_"):
            onehot_segs.extend(segs)
    if not onehot_segs:
        fail(["no onehot_perf (specimen_P_*) specimens"], family)

    with open(fn_in) as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    kept = [l for l in lines if not TAG_RE.match(l.split()[0])]
    for l in lines:
        if TAG_RE.match(l.split()[0]):
            notes.append("replace segmatch row: " + l)

    seed_lines = []
    if os.path.exists(fn_seed):
        with open(fn_seed) as f:
            seed_lines = [l for l in f if l.strip()]
    seed_other = row_bits(seed_lines, skip_phsr=True)
    explained = row_bits(seed_lines, skip_phsr=False) | row_bits(kept, False)

    errors = []
    common = set.intersection(*[s["bits"] for s in onehot_segs])
    unexplained = sorted(common - explained)
    if unexplained:
        errors.append(
            "bits common to every one-hot tile belong to no row: {}".format(
                " ".join(unexplained)))

    def routed(s):
        return [t for t, v in s["tags"].items() if v and TAG_RE.match(t)]

    rows = {}
    for t in EXPECTED:
        on_onehot = [s for s in onehot_segs if s["tags"].get(t) == 1]
        alone = [s for s in on_onehot if routed(s) == [t]]
        if len(alone) < MIN_ONEHOT:
            errors.append(
                "{} one-hot tiles have only {}, need {}".format(
                    len(alone), t, MIN_ONEHOT))
            continue
        on_all = [s for s in all_segs if s["tags"].get(t) == 1]
        bits = set.intersection(*[s["bits"] for s in on_all]) - common
        if not bits:
            errors.append("no bits: " + t)
            continue
        clash = bits & seed_other
        if clash:
            errors.append(
                "{} keeps {}, bits of rows the seed database already has".
                format(t, " ".join(sorted(clash))))
            continue
        rows[t] = bits
        notes.append(
            "one-hot row from {} one-hot and {} other tiles: {} {}".format(
                len(alone),
                len(on_all) - len(on_onehot), t, " ".join(sorted(bits))))
    if errors:
        fail(errors, family)

    group = set().union(*rows.values())
    for i, s in enumerate(all_segs):
        r = routed(s)
        want = set().union(*[rows[t] for t in r]) if r else set()
        got = s["bits"] & group
        if want != got:
            errors.append(
                "segment {}: pips {} predict {} but has {}".format(
                    i, r, sorted(want), sorted(got)))
    if errors:
        fail(errors, family)
    notes.append(
        "one-hot rows: all {} pips, checked against all {} segments".format(
            len(rows), len(all_segs)))

    out = kept + [
        "{} {}".format(t, " ".join(sorted(b))) for t, b in sorted(rows.items())
    ]
    with open(fn_out, "w") as f:
        for l in sorted(out):
            f.write(l + "\n")
    with open(fn_notes, "a") as f:
        for n in notes:
            f.write(n + "\n")
    for n in notes:
        print("  " + n, file=sys.stderr)


if __name__ == "__main__":
    main()
