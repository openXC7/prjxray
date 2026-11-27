# 045c-cmt-top-phaser

Fuzzer for the PHASER_IN route-throughs and reference-input muxes of the
`CMT_TOP_*_UPPER_B` (PHASER_IN C and D) and `CMT_TOP_*_LOWER_T` (PHASER_IN A
and B) tiles, for openXC7/nextpnr#15.

A BUFMR's only way to a BUFR or BUFIO goes through one of these PHASER_INs:

    HCLK_CMT_BUFMRCE_O<k> -> HCLK_CMT_BUFMR_PHASEREF<k>
      -> the PHASER_IN's reference mux (CMT_PHASERREF[_DOWN]_PHASERIN_<X>)
      -> CMT_PHASER_IN_<CA|DB>_PHASEREFCLK -> CMT_PHASER_IN_<CA|DB>_RCLK
      -> CMT_PHASER_IN_<X>_RCLK<n> -> HCLK_CMT_PHASERIN_RCLK<n>
      -> HCLK_CMT_MUX_PHSR_PERFCLK<m> -> HCLK_IOI_IOCLK_PLL<m> -> BUFR / BUFIO

The HCLK_CMT side (the BUFMRCE sites, `PHSR_PERFCLK`) is 045b's. This
fuzzer writes, per tile type:

- the route-through, `CMT_PHASER_IN_<CA|DB>_RCLK.CMT_PHASER_IN_<CA|DB>_PHASEREFCLK`;
- the reference mux's six BUFMR inputs, `PHASERREF0/1` (the region's own
  BUFMRs), `PHASERREF_ABOVE0/1` and `PHASERREF_BELOW0/1` (those of the
  region above and below).

It needs the tilegrid's `bits` entries for these tiles, which 005-tilegrid's
`cmt_upper_b` and `cmt_lower_t` add: UPPER_B is words 55..73 of the CMT
column, LOWER_T words 27..45.

## What the bits look like

Measured on xc7a100t with Vivado 2025.2, by forcing each input in turn
(see `gate_rows.txt`). In UPPER_B, for PHASER_IN C:

| row | bits |
|---|---|
| route-through | `28_120 29_123` |
| `PHASERREF0` | `29_155` |
| `PHASERREF1` | `28_155 29_155` |
| `PHASERREF_ABOVE0` | `28_156` |
| `PHASERREF_ABOVE1` | `28_155 28_156` |
| `PHASERREF_BELOW0` | (none) |
| `PHASERREF_BELOW1` | `28_155` |

So `29_W_27` means "own region", `28_W_28` "region above", neither "region
below", and `28_W_27` "input 1", one word above the route-through bits.
PHASER_IN D (UPPER_B) and A (LOWER_T) use the same code at `28_344 29_347`
/ word 379, and B (LOWER_T) at `28_568 29_571` / word 603. The
route-through bits are a real enable: the route-through pips were listed
as `always` ppips, so a route through a PHASER_IN without them doesn't
work. 071-ppips no longer lists them, and `pushdb` removes them from the
ppips files.

## Specimens

`make` builds `N` (default 40) specimens. In each, `top.py` picks at
random, per clock region, which PHASER_INs carry a route, from which mux
input, and which `PHSR_PERFCLK` each takes. Each BUFMR drives one BUFR,
each PHASER_IN carries at most one route, and each PERFCLK of a region at
most one. `generate.tcl` places each BUFR on a site its PERFCLK reaches and
fixes every route through the named wires (`utils/cmt_phaser_routes.tcl`),
then dumps the routed CMT pips (`design_pips.txt`), from which `generate.py`
tags. `forced_check.txt` records whether each route took its mux input.

## Solving

segmatch can't solve the mux: its bits are a code shared between inputs.
`solve_rows.py` reads the rows off the specimens:

- a PHASER_IN's candidate bits are those set in some tile where it carried
  a route and in none where it did not;
- the route-through row is the candidate bits set in every tile whose
  PHASER_IN carried a route;
- an input's row is the candidate bits set in every tile whose route took
  it, minus the route-through row. The one input with no bits
  (`PHASERREF_BELOW0`) is written as the mux's other bits cleared.

It writes nothing, and fails, unless every route-through and input was seen
in at least three tiles, no bit belongs to two PHASER_INs, and the rows
explain every tile of every specimen.

## Gate and publishing

`make gate` fails unless every forced route took its input, the R tiles'
rows are exactly those of `gate_rows.txt`, and every tile type has its 14
rows. `make pushdb` runs the gate, merges the four new segbits files, and
removes the route-through pips from the ppips files.

## Not covered

- **`DQS_TO_PHASER`**, the reference mux's seventh input (from the IO
  column's DQS): these specimens never drive it.
- **PHASER_OUT's reference muxes**: no route from a PHASER_OUT reaches a
  BUFR, so this method can't reach them.
- **Other families**: only artix7 (xc7a100t) has been run.
