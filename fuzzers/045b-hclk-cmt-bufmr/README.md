# 045b-hclk-cmt-bufmr

Fuzzer for the BUFMRCE sites of `HCLK_CMT` / `HCLK_CMT_L` and the pips a
BUFMR uses there, for openXC7/nextpnr#15.

045-hclk-cmt-pips skips both: its `EXCLUDE_RE` drops `.*BUFMR` and
`.*PHSR`, and its BUFMRCE loop is a stub. So prjxray-db has no rows for:

- the pips into a BUFMRCE input, `HCLK_CMT_BUFMR_INP0/1` from
  `HCLK_CMT_CCIO0/3`, `HCLK_CMT_MUX_CLKINT_0/1` and the `HCLK_CMT_CK_IN*`
  / `HCLK_CMT_MUX_CLK_*` wires;
- the BUFMRCE site: in use, CE inversion, `CE_TYPE`, `INIT_OUT`;
- `HCLK_CMT_MUX_PHSR_PERFCLK<m>.HCLK_CMT_PHASERIN_RCLK<n>`, the PHASER_IN
  side of the performance-clock mux. 039a solves the `MMCM_MUXED` side.

## How Vivado uses a BUFMR

Measured with Vivado 2025.2 on xc7a100tcsg324-1 and xc7a35tcpg236-1:

- No pip runs from a BUFMRCE output to a BUFIO or a BUFR. Vivado routes
  `HCLK_CMT_BUFMRCE_O<n>` → `HCLK_CMT_BUFMR_PHASEREF<n>` → through the
  PHASER_IN of the CMT above (five route-through pips in
  `CMT_TOP_*_UPPER_B`, no PHASER cell) → `HCLK_CMT_PHASERIN_RCLK<k>` →
  `HCLK_CMT_MUX_PHSR_PERFCLK<m>` → `HCLK_IOI_IOCLK_PLL<m>` → BUFIO.I and
  BUFR.I. A BUFR in the region below is reached through the PHASER_IN of
  that region's CMT, over `PHASERREF_ABOVE`; one in the region above,
  through the PHASER_IN of the CMT above, over `PHASERREF_BELOW`. The
  `PHSR_PERFCLK` pip is then in the other region's HCLK_CMT.
- Each BUFMRCE site has one dedicated input: site 0 (`INP0`) takes
  `CCIO0`, site 1 (`INP1`) takes `CCIO3`. A BUFMR on the other site gets
  its clock through the fabric (`MUX_CLKINT_*`), without a warning.
- A BUFMR and a BUFMRCE with CE tied active (`CE=1`, or `CE=0` with
  `IS_CE_INVERTED=1`) and the default `CE_TYPE=SYNC`, `INIT_OUT=0` give
  identical bitstreams: Vivado folds the inversion into the constant.
  `CE_TYPE` and `INIT_OUT` are not folded: a BUFMRCE with a constant CE,
  `ASYNC` and `INIT_OUT=1` sets two bits a BUFMR doesn't.
- A BUFMR whose `O` drives nothing cannot be built: DRC REQP-1936 only
  lets `BUFMR/O` drive `BUFR/I`, `BUFIO/I` and the PHASER reference
  clocks.
- The PHASER_IN route-through bits are in `CMT_TOP_*_UPPER_B` /
  `*_LOWER_T`, which have no `bits` entry in the tilegrid. This fuzzer
  does not solve them; it only needs Vivado to route through them.

## Specimens

`make` builds `N` (default 50) randomised specimens plus five fixed ones:

| Specimen | Shape |
|---|---|
| `cal_s0` / `cal_s1` | one-hot: only BUFMRCE site 0 (or 1) of every HCLK_CMT, a BUFMR fed from its own dedicated pad, driving one BUFR in its own region |
| `neg_unused` | no BUFMR; every dedicated pad drives a BUFR directly, so `CCIOn_ACTIVE` without the BUFMR input pip |
| `neg_const_ce` | `cal_s0`'s shape with a BUFMRCE whose CE is a constant, `IS_CE_INVERTED=1`, `CE_TYPE=ASYNC`, `INIT_OUT=1` |
| `probe_above` | `cal_s0`'s shape with each BUFR in the region above |

A randomised specimen picks, per BUFMRCE site:

- a state: unused, a BUFMR, or `direct` (the dedicated pad drives a BUFR
  with no BUFMR);
- a cell: `BUFMR`, or `BUFMRCE` with a constant CE or a CE driven from a
  fabric flop, and random `CE_TYPE`, `IS_CE_INVERTED` and `INIT_OUT`;
- a source: the site's dedicated pad, a fabric flop, or a BUFG;
- a destination: a BUFR in the BUFMR's own region, or in the region
  below or above.

A site whose destination has no free BUFR is left unused, since a BUFMR
must drive something.

Every BUFR clocks two flops in its region. Only HR banks (`HCLK_IOI3`) are
used for now.

## Tags

From generate.tcl's dumps of what Vivado placed and routed
(`bufmr_sites.txt`, `design_pips.txt`):

- `HCLK_CMT_BUFMR_INP<n>.<src>` and every pip into
  `HCLK_CMT_MUX_PHSR_PERFCLK<m>`: 1 when routed in that tile, else 0.
- `BUFMRCE.BUFMRCE_X0Y<n>.IN_USE`: 1 when a BUFMR cell is on the site and
  its output is routed, 0 when no cell is on it.
- `CE_TYPE.ASYNC`, `INIT_OUT`: for every used cell, a BUFMR counting as
  `SYNC` and 0.
- `ZINV_CE`: only for a BUFMRCE whose CE is driven by a fabric flop,
  since a constant CE absorbs the inversion.
- All four are 0 on an unused site.

The names follow BUFHCE's rows in `segbits_clk_hrow_*.db`.

## Thresholds and publishing

`-c 2`, as 045 uses for the HCLK_CMT mux positions. The raw output goes
through 039a's `filter_rdb.py`: `<const0>`, zero-candidate and unresolved
tags go to `build/<tile>.notes.txt` and are not published.

Two bits Vivado sets with a BUFMR already belong to rows of the database,
in `HCLK_CMT_L` on xc7a100t:

- `27_159` is `HCLK_CMT_CCIO0_ACTIVE`. `neg_unused` and the `direct`
  state set it without a BUFMR, so it should not end up on
  `BUFMR_INP0.HCLK_CMT_CCIO0`.
- `27_174` is in `HCLK_CMT_MUX_OUT_FREQ_REF1.HCLK_CMT_MUX_CLKINT_1`, which
  045 notes it cannot decouple. If it comes back on
  `BUFMR_INP1.HCLK_CMT_MUX_CLKINT_1`, it is a bit shared by every use of
  `MUX_CLKINT_1`, and the row needs review before it is merged.

`make gate` fails unless `BUFMRCE_X0Y0.IN_USE` of `HCLK_CMT_L` comes back
with `28_187`, the bit Vivado sets for a used site 0. `make pushdb` runs
the gate, then merges only the rows that carry bits; it runs no
`maskmerge`.
