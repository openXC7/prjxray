# 039a-hclk-bufrclk-perfclk

Fuzzer for the HCLK enable buffers of the four regional-clock spokes,
and for the CMT performance-clock path that can feed them.

039 walks the same HCLK_IOI3 tiles, but its BUFRs drive nothing. A BUFR
whose output goes nowhere leaves the HCLK enable at zero, so four rows
of `segbits_hclk_l.db` were never resolvable from that population:

```
HCLK_L.ENABLE_BUFFER.HCLK_CK_BUFRCLK0
HCLK_L.ENABLE_BUFFER.HCLK_CK_BUFRCLK1
HCLK_L.ENABLE_BUFFER.HCLK_CK_BUFRCLK2
HCLK_L.ENABLE_BUFFER.HCLK_CK_BUFRCLK3
```

Here every BUFR that is IN_USE clocks a counter on two SLICEs of its own
clock region, so the regional clock crosses the spine into the fabric.
Part of the population is fed from the region's MMCM instead of from a
clock-capable pad, which is what exercises `CLK_PERF` in
`CMT_TOP_{R,L}_LOWER_B` and `HCLK_CMT_MUX_PHSR_PERFCLK` in
`HCLK_CMT`/`HCLK_CMT_L`.

Families: `hclk_l`, `hclk_r`, `hclk_cmt`, `hclk_cmt_l`,
`cmt_top_r_lower_b`, `cmt_top_l_lower_b`.

## Phase 0: what the tag is allowed to mean

Two negative specimens are built and read **before** the tagging rule is
written down, because the whole campaign depends on the answer.

`neg_unconsumed` places a BUFR and leaves its `O` open: six
`BUFR_Y0.IN_USE`, zero `HCLK_CK_BUFRCLKn->>HCLK_LEAF_CLK_B_*` pips, zero
bits in the four candidate positions. Vivado does not set the enable for
a BUFR that is merely placed.

`neg_ioi` consumes the same BUFR in an ODDR of the IOI column: six
`IN_USE`, six `HCLK_IOI_RCLK2IO2`, six `HCLK_CMT_CK_BUFRCLK2_USED`, and
still zero leaf pips and zero bits. A clock consumed inside the IOI
column never crosses the spine.

So the predicate is the routed leaf pip in that tile, not the BUFR site
and not `IN_USE` — 039's predicate would have tagged both negatives as
ones. Pad-ODDR specimens stay in the randomised population as honest
zeroes rather than being filtered out.

## Specimens

`make` builds `N` (default 50) randomised specimens plus eight fixed
ones:

| Specimen | Shape |
|---|---|
| `cal0` … `cal3` | one-hot: only that BUFRCLK index, pad-fed, on every HCLK_IOI3 |
| `neg_unconsumed` | BUFR placed, `O` open |
| `neg_ioi` | BUFR consumed by an ODDR in the IOI column |
| `neg_unused` | no BUFR |
| `neg_bufh` | BUFHCE into a CLB, no BUFR |

The one-hot specimens are the calibration: each leaves exactly one
unknown bit local to HCLK_L, which is what assigns a bit to an index
rather than to the family. `make gate` fails the run if `BUFRCLK2` does
not come back as `00_31`; nothing is merged when the gate fails.

Two further modes, `perf0` and `perf1`, drive a single MMCM `CLKOUT`
each. They are not part of `make database`: they exist to answer whether
Vivado can be pushed onto a `CLK_PERF0` position, and on xc7a100t it
cannot — it routes `CLKOUTn -> CLK_PERF3 -> MUXED3 -> PERFCLK3` whatever
output is asked for.

## Both CMT columns

`FUZZ_SIDE=L` or `FUZZ_SIDE=R` keeps the MMCM on that column.
`L` is `CMT_TOP_L_LOWER_B` / `HCLK_CMT_L`, `R` is `CMT_TOP_R_LOWER_B` /
`HCLK_CMT`. Unset, each clock region still uses its own single MMCM.

Kintex-7's second column places its BUFRs in `HCLK_IOI` over an HP
`IOI` / `IOB18` bank, not in `HCLK_IOI3`. Those tiles are walked with
the same four neighbour offsets, and the IBUF/OBUF on an `IOB18` uses
`LVCMOS18`. A specimen forced onto one column does not substitute a
pad-fed BUFR on the other column: that BUFR stays unused, so the other
column's `PERFCLK` tags stay zero.

`make database-sides` (default `SIDE_N=32`) builds, per column, 32
randomised specimens plus `specimen_calL0`..`calL3` and
`specimen_calR0`..`calR3`. Each `cal` specimen is `mmcmN`: only
BUFRCLK index N, fed by `CLKOUTN`. With `FUZZ_SIDE` set, a randomised
specimen picks `mmcm_clb` three times out of four (the other draw is
`unused`) so the column under test is actually driven; `CLKOUT` is
still `rel_y % 4`. The default `make database` specimen list, and the
mix used when `FUZZ_SIDE` is unset, are unchanged.

## Thresholds

`-c 5` for the one-bit enables, as 039 and 058 use for the rest of the
HCLK enables; `-c 2` for the CMT mux positions, as 045 uses. Neither is
lowered to make a family resolve.

## What the fuzzer refuses to publish

`filter_rdb.py` splits the raw segmatch output three ways and writes a
`.notes.txt` for everything it drops, so a refusal is visible rather
than silent:

- `<const0>` tags, never routed in this population, are reported and
  dropped. On xc7a100t all four HCLK_R enables are const0.
- A candidate bit that already belongs to a row of the database is
  stripped by name: `05_21` on `BUFRCLK3` is
  `HCLK_L.HCLK_LEAF_CLK_B_BOTL5.HCLK_CK_BUFRCLK3`, and `29_937` on
  `CLK_PERF3.CLKOUT1` is
  `MMCME2_ADV.CLKOUT1_CLKOUT1_OUTPUT_ENABLE[0]`. A correlation with an
  existing row is not a new row. `CLK_PERF3.CLKOUT1` has nothing left
  after the strip and is dropped entirely.
- A pip the specimens do route for which segmatch finds zero candidate
  bits is written to `build/ppips_*.db` as a `default` pseudo-pip, tile
  prefix included. `mergedb` has no pseudo-pip mode, so those are
  reviewed and applied to the database by hand.

`make pushdb` merges only the rows that carry bits. The fuzzer runs no
`maskmerge`: its population is far too narrow to rewrite masks that 045
and 058 built from theirs.

## Context

Rows: the companion `prjxray-db` PR. Threads:
`openXC7/nextpnr-xilinx#149` (the enables, and the review record for the
phase-0 rule and the calibration gate) and `openXC7/nextpnr-xilinx#172`
(the performance-clock path).
