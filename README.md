# Project X-Ray

[![Documentation Status](https://img.shields.io/readthedocs/prjxray?longCache=true&style=flat-square&logo=ReadTheDocs&logoColor=fff)](http://prjxray.readthedocs.org/)
[![License](https://img.shields.io/github/license/f4pga/prjxray.svg?longCache=true&style=flat-square&label=License)](https://github.com/f4pga/prjxray/blob/master/LICENSE)
![GitHub Actions](https://img.shields.io/github/actions/workflow/status/f4pga/prjxray/Automerge.yml?branch=master&longCache=true&style=flat-square&label=GHA&logo=Github%20Actions&logoColor=fff)

Documenting the Xilinx 7-series bit-stream format.

This repository contains both tools and scripts which allow you to document the
bit-stream format of Xilinx 7-series FPGAs.

> **Virtex-7 / VC707 users:** see [**Virtex-7 Port
> Status**](#virtex-7-port-status-virtex7-support-branch) below for the
> `virtex7-support` branch — different Vivado version, working open flow
> on `xc7vx485tffg1761-2`, and device-specific patches. The Quickstart
> Guide that follows assumes the upstream Artix-7 / 2017.2 path.

More documentation can be found published on [prjxray ReadTheDocs site](https://prjxray.readthedocs.io/en/latest/) - this includes;
 * [Highlevel Bitstream Architecture](https://prjxray.readthedocs.io/en/latest/architecture/overview.html)
 * [Overview of DB Development Process](https://prjxray.readthedocs.io/en/latest/db_dev_process/index.html)

# Quickstart Guide
Instructions were originally written for Ubuntu 16.04. Please let us know if you have information on other distributions.

### Step 1: ###
Install Vivado 2017.2. If you did not install to /opt/Xilinx default, then set the environment variable
XRAY_VIVADO_SETTINGS to point to the settings64.sh file of the installed vivado version, ie

    export XRAY_VIVADO_SETTINGS=/opt/Xilinx/Vivado/2017.2/settings64.sh

Do not source the settings64.sh in your shell, since this adds directories of
the Vivado installation at the beginning of your PATH and LD_LIBRARY_PATH
variables, which will likely interfere with or break non-Vivado applications in
that shell. The Vivado wrapper utils/vivado.sh makes sure that the environment
variables from XRAY_VIVADO_SETTINGS are automatically sourced in a separate
shell that is then only used to run Vivado to avoid these problems.

**Why 2017.2?** Currently the fuzzers only work on `2017.2`, see [Issue #14 on prjxray](https://github.com/f4pga/prjxray/issues/14).

**Is 2017.2 really required?** Yes, only `2017.2` works. Until Issue #14 is solved, **only** `2017.2` works and will be supported.

### Step 2: ###
Clone the ``prjxray`` repository and its submodules:

```bash
git clone git@github.com:f4pga/prjxray.git
cd prjxray
git submodule update --init --recursive
```

### Step 3: ###
Install CMake:

```bash
sudo apt-get install cmake # version 3.5.0 or later required,
                           # for Ubuntu Trusty pkg is called cmake3
```

### Step 4: ###
Build the C++ tools, in the prjxray root directory run:

```bash
make build
```

### Step 5: ###
Choose one of the following options:

(Option 1) - Install the Python environment locally

```bash
sudo apt-get install virtualenv python3 python3-pip python3-virtualenv python3-yaml
make env
```

(Option 2) - Install the Python environment globally

```bash
sudo apt-get install python3 python3-pip python3-yaml
sudo -H pip3 install -r requirements.txt
```

This step is known to fail with a compiler error while building the `pyjson5`
library when using Arch Linux and Fedora. If this occurs, `pyjson5` needs one
change to build correctly:

```bash
git clone https://github.com/Kijewski/pyjson5.git
cd pyjson5
sed -i 's/char \*PyUnicode/const char \*PyUnicode/' src/_imports.pyx
sudo make
```

This might give you an error about `sphinx_autodoc_typehints` but it should
correctly build and install pyjson5. After this, run either option 1 or 2 again.

### Step 6: ###

Prepare the database with static part information, which are needed by the
fuzzers, either for all device families

```bash
make db-prepare-parts
```

or only for a selected one

```bash
make db-prepare-artix7
```

### Step 7: ###
Always make sure to set the environment for the device you are working on before
running any other commands:

```bash
source settings/artix7.sh
```

### Step 8: ###

(Option 1, recommended) - Download a current stable version (you can use the
Python API with a pre-generated database)

```bash
./download-latest-db.sh
```

(Option 2) - (Re-)create the entire database (this will take a very long time!)

```bash
cd fuzzers
make -j$(nproc)
```

### Step 9: ###
Pick a fuzzer (or write your own), from the ``prjxray`` root dir, run:

```bash
cd fuzzers/010-clb-lutinit
make -j$(nproc) run
```

### Step 10: ###
Create HTML documentation, from the ``prjxray`` root dir, run:

```
cd htmlgen
python3 htmlgen.py
```

# C++ Development

Tests are not built by default.  Setting the PRJXRAY\_BUILD\_TESTING option to
ON when running cmake will include them. From the ``prjxray`` root dir, run:

```bash
mkdir -p build
cd build
cmake -DPRJXRAY_BUILD_TESTING=ON ..
make
```

The default C++ build configuration is for releases (optimizations enabled, no
debug info). A build configuration for debugging (no optimizations, debug info)
can be chosen via the CMAKE\_BUILD\_TYPE option. From the ``prjxray`` root dir, run:

```bash
mkdir -p build
cd build
cmake -DCMAKE_BUILD_TYPE=ON ..
make
```

The options to build tests and use a debug build configuration are independent
to allow testing that optimizations do not cause bugs.  The build configuration
and build tests options may be combined to allow all permutations.

# Process

The documentation is done through a "black box" process were Vivado is asked to
generate a large number of designs which then used to create bitstreams. The
resulting bit streams are then cross correlated to discover what different bits
do.

## Parts

### [Minitests](minitests)

There are also "minitests" which are designs which can be viewed by a human in
Vivado to better understand how to generate more useful designs.

### [Experiments](experiments)

Experiments are like "minitests" except are only useful for a short period of
time. Files are committed here to allow people to see how we are trying to
understand the bitstream.

When an experiment is finished with, it will be moved from this directory into
the latest "prjxray-experiments-archive-XXXX" repository.

### [Fuzzers](fuzzers)

Fuzzers are the scripts which generate the large number of bitstream.

They are called "fuzzers" because they follow an approach similar to the
[idea of software testing through fuzzing](https://en.wikipedia.org/wiki/Fuzzing).

### [Tools](tools) & [Libs](lib)

Tools & libs are useful tools (and libraries) for converting the resulting
bitstreams into various formats.

Binaries in the tools directory are considered more mature and stable then
those in the [utils](utils) directory and could be actively used in other
projects.

### [Utils](utils)

Utils are various tools which are still highly experimental. These tools should
only be used inside this repository.

### [Third Party](third_party)

Third party contains code not developed as part of Project X-Ray.


# Database

Running the all fuzzers in order will produce a database which documents the
bitstream format in the [database](database) directory.

As running all these fuzzers can take significant time,
[Tim 'mithro' Ansell <me@mith.ro>](https://github.com/mithro) has graciously
agreed to maintain a copy of the database in the
[prjxray-db](https://github.com/f4pga/prjxray-db) repository.

Please direct enquires to [Tim](mailto:me@mith.ro) if there are any issues with
it.

# Current Focus

Current the focus has been on the Artix-7 50T part. This structure is common
between all footprints of the 15T, 35T and 50T varieties.

We have also started experimenting with the Kintex-7 and Virtex-7 parts.

The aim is to eventually document all parts in the Xilinx 7-series FPGAs but we
can not do this alone, **we need your help**!

## Virtex-7 Port Status (`virtex7-support` branch)

This branch ports the openXC7 prjxray flow to **Virtex-7 `xc7vx485tffg1761-2`**
(VC707 board), modelled on the Kintex-7 sub-flow. The original goal — a fully
open-source bit→DCP / fasm→bit round-trip on a Virtex-7 HP-only part — has
been met for the four VC707 reference designs (`rst_to_led`, `counter`,
`counter_bufr`, `telegraph`) and end-to-end for the PicoSoC UART demo running
on real silicon.

The work spans four sibling branches on the openXC7 GitHub:

| Repo | Branch | Carries |
|---|---|---|
| openXC7/prjxray | `virtex7-support` | this DB tree + `fasm2frames.py` bank-glue rules |
| openXC7/nextpnr-xilinx-meta | `virtex7-support` | per-site metadata + `wire_intents.json` |
| openXC7/nextpnr-xilinx | `virtex7-support` | RAM128/256X1S packing + INT-tile constant-net bridge |
| openXC7/demo-projects | `virtex7-branch` | VC707 reference `.bit` files + sources |

> **Vivado version.** This port was developed and validated against
> **Vivado 2020.1**. Other 2018+ releases may well work — the fuzzers and
> Tcl helpers are not knowingly using any 2020.1-specific feature — but the
> upstream-recommended **2017.2 is too old** for Virtex-7 here: it predates
> the device support files we need (`xc7vx485tffg1761-2` HP-bank IOB18
> behaviour, several `HCLK_IOI`/`CMT` properties the fuzzers query, the
> `write_pip_txtdata` bulk-fetch paths the `utils.tcl` patch exercises).
> Set `XRAY_VIVADO_SETTINGS` accordingly:
>
>     export XRAY_VIVADO_SETTINGS=/opt/Xilinx/Vivado/2020.1/settings64.sh

### Achievements

- **End-to-end open flow on real hardware (VC707):**
  - 8-bit skew-tolerant counter blinks on VC707 with reset debounce.
  - 200 MHz LVDS sysclk variant (`counter_bufr`) runs via IBUFDS + BUFR.
  - `telegraph` UART smoke test prints `ABCDEFG` at 115200 baud on
    `/dev/ttyUSB0`, bit-equivalent to the Vivado reference.
  - **PicoSoC** (`picorv32/picosoc`) running on VC707 at 125 MHz from the
    SGMIICLK crystal — BRAM-resident firmware prints
    `PicoSoC alive on VC707 @ 125 MHz`, LEDs walk a pattern.
- **All four reference designs at 0/0 bit-difference** vs Vivado, with **zero
  `.frm` patches** — the bank-glue rules are now codified as DB entries plus
  auto-inject in `utils/fasm2frames.py`.
- **Cross-family segbits/ppips transplant** from the openXC7
  [`prjxray-db`](https://github.com/openXC7/prjxray-db) Kintex-7 tree into
  `database/virtex7/`: ~39 381 segbits + ~12 273 ppips entries, plus targeted
  key copies for `clk_hrow_*`, `clk_bufg_*`, `hclk_cmt*`, `io_int_interface_*`
  (≈51 k entries total). Pre-transplant tree backed up at
  `database/virtex7.before_transplant/`.
- **HP-bank glue codified — 7 new segbits entries + auto-inject:**
  - `LIOB18.IOB_Y0.IBUF_HP_BANK_GLUE` (1 bit)
  - `LIOB18.IOB_Y0.OBUF_HP_BANK_GLUE` (3 bits)
  - `LIOB18.IOB_Y1.OBUF_HP_BANK_GLUE` (3 bits)
  - `RIOB18.IOB_Y0.IBUFDS_BANK_GLUE` (7 bits, LVDS pair root)
  - `INT_L.IOB_COL_OBUF_CASCADE_Y1` (3 bits, Y1 OBUF column carry)
  - `INT_L.IOB_COL_BANK_ACTIVE` (3 bits, bank-active marker)
  - `INT_L.GFAN_TIE_ROOT_GLUE` (1 bit, OBUF T-tie GND routing)
  - Plus 14 silicon-default bits added as IOB18 `default` entries (`PUDC_B`
    cascade, DCI cascade, slew/drive defaults Vivado emits unconditionally).
- **`utils/fasm2frames.py` bank-glue auto-inject** — direction-aware
  walk over the FASM stream classifies each LIOB18 site as input / output /
  diff-input from feature names (`IN_ONLY`, `.IN`, `IBUFDISABLE` → in;
  `.DRIVE.` → out; `IN_DIFF` → diff_in) and injects the matching glue
  features before frame assembly. `PUDC_B` template emission rewritten for
  HP-bank IOSTANDARDs (10 features cover Y0 + Y1 default state). The
  `pudc_b_tile_site` is resolved unconditionally so the HP-bank walk skips it.
- **11 fuzzers patched** for HP-bank / virtex7-grid awareness:
  - `037-iob18-pips` — left-side mirror sites (LIOI / LIOI_TBYTESRC /
    LIOI_TBYTETERM), `top.py` NOT_INCLUDED_TILES for `*_SING`, generate-side
    tile-type normalization, `ioi_pip_list.tcl` LIOI emission.
  - `039-hclk-config` — virtex7 split (HCLK_IOI vs HCLK_IOI3),
    `XRAY_IOSTANDARD` env var, IOB18M / IOB33M alternation in `top.py`.
  - `047a-hclk-idelayctrl-pips` — accepts both HCLK_IOI and HCLK_IOI3.
  - `034 / 034b / 041 / 043 / 044 / 045 / 046` — removed local
    `write_pip_txtdata` overrides that shadowed the patched `utils.tcl`
    bulk-fetch (~4× faster per specimen on xc7vx485t).
- **`utils/utils.tcl` bulk-fetch patch** for `write_pip_txtdata` —
  per-net `foreach pip` → bulk `get_pips` + bulk `get_property IS_DIRECTIONAL`
  + cached `dst_wire_to_num_pips`. ~4× speed-up; on
  `xc7vx485tffg1761-2` cuts `041-clk-hrow-pips`/`045-hclk-cmt-pips` specimens
  from ~1.5 h to ~25 min each.
- **`utils/fasm2frames.py` HP-bank fix** — was hard-coded to `HCLK_IOI3_*`
  tile prefix; now probes the grid for whichever of `HCLK_IOI_` / `HCLK_IOI3_`
  exists. STEPDOWN bank-anchor check widened accordingly.
- **`utils/mergedb.sh` extended** with LIOI / LIOI_TBYTESRC / LIOI_TBYTETERM
  / LIOB18 / mask_liob18 cases.
- **RapidWright `json2dcp.jar` rebuilt** against modern RapidWright (2025.2.1)
  and patched for virtex7 — verified `rst_to_led_routed.json` → 1.38 MB DCP
  that loads back cleanly on `xc7vx485tffg1761-2`.
- **nextpnr-xilinx companion patches** (on its `virtex7-support` branch):
  - `xilinx/pack_dram.cc` — RAM128X1S / RAM256X1S single-port distributed RAM
    packing (mirrors the SPO half of the dual-port families); needed by
    PicoSoC's BRAM-fallback synthesis.
  - `xilinx/python/nextpnr_structs.py` — bridges `PSEUDO_GND_WIRE_ROW` /
    `PSEUDO_VCC_WIRE_ROW` to the INT tile's `GND_WIRE` / `VCC_WIRE` via
    `CONST_DRIVER` pseudo-pips, so the router can find a route for OBUF
    T-tie nets to the global GND.

### Virtex-7 architecture discoveries

These are the things that turned out to be **different on Virtex-7**, not
inherited automatically by transplanting the Kintex-7 sub-flow. Some are
silicon-level facts that prjxray was never set up to capture; others are
nextpnr-xilinx assumptions that broke at scale.

- **HP-bank ≠ HR-bank silicon.** Virtex-7 `xc7vx485t` is HP-bank-only
  (`IOB18` family using `INBUF_DCIEN` / `OUTBUF_DCIEN`), whereas Kintex-7
  parts on the openXC7 path are mostly HR (`IOB33` family using
  `IBUF` / `OBUF`). The HR and HP IO logic share the same prjxray feature
  syntax but **encode different silicon bits**, and the surrounding clock
  region differs:
  - HR uses `HCLK_IOI3_*` tiles.
  - HP uses `HCLK_IOI_*` tiles.
  - The IO-related fasm tools were hard-coded to `HCLK_IOI3_*` and silently
    dropped HP-bank features until probed; `fasm2frames.py` and several
    fuzzers now branch on a runtime grid probe.
- **L/R-side mirror.** The VC707 IO column lives on the **left** side
  (`LIOB18_X81*` / `LIOI_X*`) — most Kintex-7 reference designs used the
  right-side mirror. The 037-iob18-pips fuzzer had to learn left-side
  emission (it had only ever exercised RIOB18).
- **"Bank glue" — the silicon enables Vivado sets that no prjxray feature
  emits.** A correct prjxray-driven bitstream for an HP-bank design is a
  proper *subset* of what Vivado emits because Vivado writes ~14 extra bits
  per bank-in-use that the prjxray feature schema never claimed. These are
  not user-visible (no fasm feature corresponds to them) but the HP-bank
  IOB silicon **will not drive** without them. Categories:
  - **Tile-in-use markers** in `INT_L_X62Y*` and `INT_L_X32Y49` — three bits
    that indicate "this bank's OBUF column is live" / "DCI cascade is live".
  - **Y0 vs Y1 OBUF cascade** — `LIOB18.IOB_Y0.OBUF_HP_BANK_GLUE` and
    `.IOB_Y1.OBUF_HP_BANK_GLUE` are independent 3-bit groups. Crucially the
    Y1 column's 3 bits also have to be cascaded into the next INT_L row up
    (`INT_L.IOB_COL_OBUF_CASCADE_Y1`).
  - **`PUDC_B` cascade.** The HP-bank `PUDC_B` pin (`LIOB18_X81Y97` on
    `xc7vx485tffg1761-2`) controls bank-wide auto-pullup behaviour at boot
    and **always** appears in the bitstream with 10 silicon-default features,
    even when the user never references it. We now emit those features
    unconditionally from `fasm2frames.py`.
  - **IBUFDS pair root.** A differential IBUFDS uses the Master IOB
    (`Y0`) as the live pin and emits 7 silicon-enable bits there
    (`RIOB18.IOB_Y0.IBUFDS_BANK_GLUE`). The Slave (`Y1`) stays in default
    state. Without these the LVDS receiver does not enable.
  - Heuristic gotcha: our first cut classified OBUFs by `.SLEW.`; that gave
    false positives because Vivado emits `SLEW.SLOW` on default-state IBUFs
    too. The reliable OBUF marker is `.DRIVE.`.
- **`HCLK_L.ENABLE_BUFFER.HCLK_CK_BUFRCLK0..3`** — the regional-clock
  enable buffers, one bit each. nextpnr-xilinx gathers every used
  `HCLK_CK_*` wire but emits only the `BUFHCLK` ones
  (`himbaechel/uarch/xilinx/fasm.cc`), so these never reach the FASM;
  `fasm2frames.py` injects them for each BUFR channel the stream uses.
  Measured by fuzzer `039a-hclk-bufrclk-perfclk` on `xc7vx485tffg1761-2`:
  `00_23`, `01_23`, `00_31`, `01_31` — the same bits artix7, kintex7,
  spartan7 and zynq7 carry. They are **not** consecutive in minor 1.
  This replaces the earlier hand-made `HCLK_L.HCLK_LEAF_BUFRCLK3_ACTIVE`
  row, which named the same bit (`01_31`) as a local feature and whose
  "minor 1 bit 28+ch" rule was right only for channel 3.

- **`INT_L.GFAN_TIE_ROOT_GLUE`** — OBUF `T` (tristate) input must be tied
  to GND for non-tristate use. Vivado routes that GND from the **next
  INT_L row up** via the `GFAN0.GND_WIRE` pseudo-pip; the routing-graph
  signature requires one extra bit at `26_018` in `INT_L_X62Y(N+10)`. We
  detect any `INT_L_X62Y*.GFAN0.GND_WIRE` in the FASM and inject the
  root-row glue automatically. This is the last residual that brought all
  four reference designs to 0/0 vs Vivado on raw open flow.
- **`fasm2bels` chokes on `NOCLKINV`** — the `xc7vx485t` connection
  database builds (14 min, 4.2 GB, 56.8 M wires), but `clb_models.py` does
  not yet handle the `NOCLKINV` packer feature that nextpnr-xilinx emits
  for HP-bank SLICEs. Asserted as `{NOCLKINV}`. Phase B (`fasm2bels`
  virtex7 port) is paused on this.
- **nextpnr-xilinx OBUF T-tie convergence.** Within nextpnr the router
  cannot find a path from `NULL_X0Y364/PSEUDO_GND_WIRE_GLBL` to the LIOB18
  OBUF `TRI` pin because the constant-net source lives outside the INT
  tile graph. Fixed at chipdb-build time by `nextpnr_structs.py`:
  emit `CONST_DRIVER` pseudo-pips that bridge `PSEUDO_GND_WIRE_ROW` /
  `PSEUDO_VCC_WIRE_ROW` into each INT tile's `GND_WIRE` / `VCC_WIRE`.
- **nextpnr-xilinx Y137/Y138 chipdb wire mapping** — still open. Two LIOB18
  rows present in the chipdb point at wires that the architecture
  assignment then loses track of. Functional impact zero (our
  `fasm2frames.py` covers the silicon-enable side); but the bug is real and
  filed at task #31.
- **PicoSoC needed RAM128X1S / RAM256X1S packing.** PicoSoC's
  default `picorv32_pcpi_div` synthesises into single-port distributed RAM.
  nextpnr-xilinx had packers only for the dual-port `RAM128X1D` /
  `RAM256X1D` variants; the SP packers are mirrors of the SPO half of
  those, added on this branch.

### Goals (remaining)

- **Codify the 228-bit PicoSoC CLB-glue family** (relative offsets
  `30_006 / 30_011 / 30_020 / 30_022 / 30_040 / 30_045 / 30_052 / 30_056`
  + `31_040 / 31_043`) — per-SLICE "in use" bits that show up only when a
  SLICE is occupied. Would push PicoSoC's bit-diff vs Vivado to zero.
- **Restore the 236 missing IOI features** (IDELAY / OSERDES / OQ) into
  `segbits_lioi.db` — currently we have HR-side coverage transplanted but
  the HP-side variants need their own segdata.
- **`fasm2bels` virtex7 port** — past the `NOCLKINV` block, then through
  HP-bank IOB BEL substitutions (sketched in `models/iob_models.py`).
- **Y137/Y138 chipdb wire mapping** in nextpnr-xilinx — for parity with
  Vivado's checkpoint format.

### Cross-cutting open TODOs

- Expand the virtex7 ROI (small ROI was sufficient for the IO / HCLK
  fuzzers but the CMT / DSP / GTX fuzzers will want more).
- Vivado DRC cross-check of nextpnr output.
- Exclude `GTX_INT_INTERFACE` pips from the virtex7 chipdb.
- Bits info for `CFG_CENTER` / `*_SING` tiles.

### Constraints

- Patches must **not** regress other families (artix7 / kintex7 / zynq7 /
  spartan7). The HP-bank additions are gated on tile-type prefix so the
  HR-bank paths stay byte-identical.
- Build artefacts under `fuzzers/*/build/` are **retained** for debugging
  — `make clean` is not invoked between fuzzer iterations.

## Adding a new part to an existing family

We have written a [detailed guide](https://f4pga.readthedocs.io/projects/prjxray/en/latest/db_dev_process/newpart.html) that walks through the process of adding a new part to an existing family.

## TODO List

 - [ ] Write a TODO list


# Contributing

There are a couple of guidelines when contributing to Project X-Ray which are
listed here.

### Sending

All contributions should be sent as
[GitHub Pull requests](https://help.github.com/articles/creating-a-pull-request-from-a-fork/).

### License

All software (code, associated documentation, support files, etc) in the
Project X-Ray repository are licensed under the very permissive
[ISC Licence](https://opensource.org/licenses/ISC). A copy can be found in the [`LICENSE`](LICENSE) file.

All new contributions must also be released under this license.

### Code of Conduct

By contributing you agree to the [code of conduct](CODE_OF_CONDUCT.md). We
follow the open source best practice of using the [Contributor
Covenant](https://www.contributor-covenant.org/) for our Code of Conduct.

### Sign your work

To improve tracking of who did what, we follow the Linux Kernel's
["sign your work" system](https://github.com/wking/signed-off-by).
This is also called a
["DCO" or "Developer's Certificate of Origin"](https://developercertificate.org/).

**All** commits are required to include this sign off and we use the
[Probot DCO App](https://github.com/probot/dco) to check pull requests for
this.

The sign-off is a simple line at the end of the explanation for the
patch, which certifies that you wrote it or otherwise have the right to
pass it on as a open-source patch.  The rules are pretty simple: if you
can certify the below:

        Developer's Certificate of Origin 1.1

        By making a contribution to this project, I certify that:

        (a) The contribution was created in whole or in part by me and I
            have the right to submit it under the open source license
            indicated in the file; or

        (b) The contribution is based upon previous work that, to the best
            of my knowledge, is covered under an appropriate open source
            license and I have the right under that license to submit that
            work with modifications, whether created in whole or in part
            by me, under the same open source license (unless I am
            permitted to submit under a different license), as indicated
            in the file; or

        (c) The contribution was provided directly to me by some other
            person who certified (a), (b) or (c) and I have not modified
            it.

	(d) I understand and agree that this project and the contribution
	    are public and that a record of the contribution (including all
	    personal information I submit with it, including my sign-off) is
	    maintained indefinitely and may be redistributed consistent with
	    this project or the open source license(s) involved.

then you just add a line saying

	Signed-off-by: Random J Developer <random@developer.example.org>

using your real name (sorry, no pseudonyms or anonymous contributions.)

You can add the signoff as part of your commit statement. For example:

    git commit --signoff -a -m "Fixed some errors."

*Hint:* If you've forgotten to add a signoff to one or more commits, you can use the
following command to add signoffs to all commits between you and the upstream
master:

    git rebase --signoff upstream/master

### Contributing to the docs

In addition to the above contribution guidelines, see the guide to
[updating the Project X-Ray docs](UPDATING-THE-DOCS.md).
