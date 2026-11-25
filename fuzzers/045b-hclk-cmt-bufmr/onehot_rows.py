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
HCLK_CMT tile, with the route fixed by generate.tcl. A pip's row is then
the bits set in every one-hot tile that has it, minus:

- the bits set in every one-hot tile (the BUFMRCE site and its pad, which
  all of them share);
- the bits of rows the seed database already has for this tile type,
  other than the HCLK_CMT_MUX_PHSR_PERFCLK rows, whose code bits these
  pips do share. A correlation with an existing row is not a new row: with
  four one-hot tiles per pip in HCLK_CMT_L, a BUFR's
  HCLK_CMT_CK_BUFRCLK<n>_USED bit can be set in all four by chance.

The rows are only written if they explain every specimen of the run: in
each HCLK_CMT tile of each specimen, the union of the rows of the pips
routed there must equal the bits of those rows that are set. If one tile
disagrees, nothing is written and the script fails.

Usage: onehot_rows.py BUILD_DIR FAMILY SEGBITS_IN SEGBITS_OUT NOTES SEED_DB

SEED_DB is the database's segbits file for FAMILY.

SEGBITS_IN is filter_rdb.py's output for FAMILY (hclk_cmt or hclk_cmt_l).
Its PHASERIN rows are replaced, its other rows are copied unchanged, and
what was done is appended to NOTES.
"""
import glob
import os
import re
import sys

TAG_RE = re.compile(
    r"^HCLK_CMT\.HCLK_CMT_MUX_PHSR_PERFCLK[0-9]\.HCLK_CMT_PHASERIN_RCLK[0-9]$")

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


def seed_row_bits(fn):
    """Bits of the seed database's rows, except the PHSR_PERFCLK mux's."""
    bits = set()
    if not os.path.exists(fn):
        return bits
    with open(fn) as f:
        for line in f:
            w = line.split()
            if len(w) < 2 or ".HCLK_CMT_MUX_PHSR_PERFCLK" in w[0]:
                continue
            bits |= {b.lstrip("!") for b in w[1:]}
    return bits


def main():
    build, family, fn_in, fn_out, fn_notes, fn_seed = sys.argv[1:7]
    notes = []
    known = seed_row_bits(fn_seed)

    specimens = sorted(
        d for d in glob.glob(os.path.join(build, "specimen_*"))
        if os.path.isdir(d))
    onehot = [d for d in specimens if os.path.basename(d).startswith(
        "specimen_P_")]
    segfile = "segdata_{}.txt".format(family)

    all_segs = []
    for d in specimens:
        fn = os.path.join(d, segfile)
        if os.path.exists(fn):
            all_segs.extend(load_segdata(fn))
    onehot_segs = []
    for d in onehot:
        fn = os.path.join(d, segfile)
        if os.path.exists(fn):
            onehot_segs.extend(load_segdata(fn))

    with open(fn_in) as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    kept = [l for l in lines if not TAG_RE.match(l.split()[0])]
    for l in lines:
        if TAG_RE.match(l.split()[0]):
            notes.append("replace segmatch row: " + l)

    rows = {}
    if not onehot_segs:
        notes.append(
            "no onehot_perf specimens: no PHASERIN rows written (segmatch "
            "cannot give their shared bits)")
    else:
        common = set.intersection(*[s["bits"] for s in onehot_segs])
        tags = sorted({t for s in onehot_segs for t in s["tags"]
                       if TAG_RE.match(t)})
        for t in tags:
            on = [s for s in onehot_segs if s["tags"].get(t) == 1]
            if len(on) < MIN_ONEHOT:
                notes.append(
                    "drop, only {} one-hot tiles: {}".format(len(on), t))
                continue
            # A one-hot tile has this pip and no other of the family.
            others = [
                s for s in on if sum(
                    v for k, v in s["tags"].items() if TAG_RE.match(k)) != 1
            ]
            if others:
                notes.append(
                    "drop, {} one-hot tiles have more than one of these "
                    "pips: {}".format(len(others), t))
                continue
            bits = set.intersection(*[s["bits"] for s in on]) - common
            if bits & known:
                notes.append(
                    "strip {} from {}: they belong to rows of the seed "
                    "database".format(" ".join(sorted(bits & known)), t))
                bits -= known
            if not bits:
                notes.append("drop, no bits: " + t)
                continue
            rows[t] = bits

        group = set().union(*rows.values()) if rows else set()
        mismatches = []
        for i, s in enumerate(all_segs):
            routed = [t for t, v in s["tags"].items() if v and TAG_RE.match(t)]
            if any(t not in rows for t in routed):
                # A pip without a row: this tile can't be checked.
                continue
            want = set().union(*[rows[t] for t in routed]) if routed else set()
            got = s["bits"] & group
            if want != got:
                mismatches.append(
                    "segment {}: pips {} predict {} but has {}".format(
                        i, routed, sorted(want), sorted(got)))
        if mismatches:
            for m in mismatches:
                print(m, file=sys.stderr)
            print(
                "{}: {} of {} segments disagree with the one-hot rows; "
                "nothing written".format(
                    family, len(mismatches), len(all_segs)),
                file=sys.stderr)
            sys.exit(1)
        notes.append(
            "one-hot rows: {} pips from {} one-hot segments, checked "
            "against all {} segments".format(
                len(rows), len(onehot_segs), len(all_segs)))

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
