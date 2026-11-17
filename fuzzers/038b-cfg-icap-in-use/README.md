# cfg ICAP IN_USE fuzzer

Derives `CFG_CENTER_MID.ICAP.IN_USE`: the bits that enable an `ICAPE2` in
the configuration centre. Without them the configuration logic ignores the
primitive (readback returns zeros, `IPROG` does nothing, frame writes have no
effect). Introduced for artix7 and virtex7 by openXC7/prjxray-db#43; this
fuzzer measures the same bits for the remaining 7-series families.

## Method

The tile has two ICAP sites and the enable bits are **site specific**. A
Vivado build of a design that instantiates `ICAPE2` sets one three-bit
pattern or the other; a design without an `ICAPE2` sets neither:

| Site       | `ICAP.IN_USE` bits          |
|------------|-----------------------------|
| ICAP_X0Y1  | `26_2206 26_2207 27_2205`   |
| ICAP_X0Y0  | `26_2205 27_2206 27_2207`   |

The database's existing ICAP features (`ICAP_WIDTH_X16`, `ICAP_WIDTH_X8`)
were fuzzed by 038-cfg on `ICAP_X0Y1` (it excludes `ICAP_X0Y0` in `top.py`),
so `CFG_CENTER_MID.ICAP.IN_USE` is also the ICAP_X0Y1 pattern. The ICAP
change in openXC7/nextpnr#175 places `ICAPE2` on the top site, `ICAP_X0Y1`.

An `ICAPE2` also sets ~80 other bits in the tile's frames 0..25. Those are the
ICAP's data path, not the control word, and the hardware measurement in
openXC7/nextpnr#175 shows only the three control bits are needed for a working
ICAP. `generate.py` therefore keeps only frames 26 and up, which is where the
control word lives.

Three specimens separate the pattern from everything else:

| Specimen | Design                        | `ICAP.IN_USE` tag |
|----------|-------------------------------|-------------------|
| 1        | `STARTUPE2` only              | 0                 |
| 2        | `ICAPE2` at `ICAP_X0Y0`       | 0                 |
| 3        | `ICAPE2` at `ICAP_X0Y1`       | 1                 |

Bits set by either ICAP site are set in a specimen where the tag is 0 and in
one where it is 1, and the ICAP_X0Y0 pattern is set with tag 0 in specimen 2
but clear with tag 0 in specimen 1, so segmatch drops both. Only the
ICAP_X0Y1 pattern correlates with the tag.

## Usage

The database used by the fuzzer must be the prjxray-db checkout. With the
usual layout (`prjxray/database/<family>` populated), source a settings file
and run:

```sh
cd fuzzers/038b-cfg-icap-in-use
source ../../settings/artix7_50t.sh
make run
```

For a database outside `prjxray/database`, also override the variables that
`environment.sh` derives from it:

```sh
export XRAY_DATABASE_DIR=/path/to/prjxray-db
export XRAY_FAMILY_DIR=$XRAY_DATABASE_DIR/$XRAY_DATABASE
export XRAY_PART_YAML=$XRAY_FAMILY_DIR/$XRAY_PART/part.yaml
export XRAY_BITREAD="$XRAY_TOOLS_DIR/bitread --part_file $XRAY_PART_YAML"
```

Pick the part with a settings file (or set `XRAY_PART`), and set
`XRAY_VIVADO_SETTINGS` to an installed Vivado. The design has no I/O, so no
pin constraints or speed-grade choices matter.

## Results

Vivado 2024.1, raw frame diff of the `CFG_CENTER_MID` window between a design
with `STARTUPE2` only and the same design with `ICAPE2` on `ICAP_X0Y1`
(that is what the fuzzer's specimen 3 does):

| Family   | Part                 | CFG tile               | `ICAP.IN_USE` bits        | Note |
|----------|----------------------|------------------------|---------------------------|------|
| artix7   | xc7a50tcsg324-1      | `CFG_CENTER_MID_X46Y32`| `26_2206 26_2207 27_2205` | reproduces prjxray-db#43 |
| kintex7  | xc7k70tfbg676-2      | `CFG_CENTER_MID_X61Y84`| `26_2206 26_2207 27_2205` | measured here |
| spartan7 | xc7s50fgga484-1      | `CFG_CENTER_MID_X46Y32`| `26_2206 26_2207 27_2205` | measured here |
| zynq7    | xc7z010clg400-1      | `CFG_CENTER_MID_X67Y32`| `26_2206 26_2207 27_2205` | **always set**, see below |
| virtex7  | xc7vx485tffg1761-2   | `CFG_CENTER_MID_X157Y84`| `26_2206 26_2207 27_2205` | prjxray-db#43's measurement |

`ICAP_X0Y0`'s pattern on the measured parts is `26_2205 27_2206 27_2207`.

The fuzzer was run on artix7, kintex7 and spartan7.  All three segmatch runs
produced exactly:

    CFG_CENTER_MID.ICAP.IN_USE 26_2206 26_2207 27_2205

On zynq7 it produces no feature, for the reason below.

### Zynq-7

Both the no-`ICAPE2` and the `ICAPE2` bitstream set the three bits, so this
fuzzer has no correlation to solve and writes no `IN_USE` feature. The bits
are already in the zynq7 database as `ALWAYS_ON_PROP1..3` and are applied to
every bitstream through `required_features.fasm`, which is the same
observation from the other direction (SymbiFlow/prjxray#746). The
`ICAP.IN_USE` mapping is a duplicate of those bits, needed so that a FASM
that names the feature resolves.

### Virtex-7

Not rebuilt here: this machine's Vivado installs (2017.2 and 2024.1) have no
Virtex-7 device data, and the 2020.1 install the virtex7 settings refer to is
absent. The prjxray-db#43 measurement is for `xc7vx485t`; the CFG tile type
and the ICAP bit layout are the same as artix7.

## What is not covered

The 80-odd ICAP data-path bits in frames 0..25 have no features in any
family's `segbits_cfg_center_mid.db`; they are handled as `always` pseudo-pips
(`ppips_cfg_center_mid.db`). fasm2frames therefore does not emit them. The
ICAP still works without them, as measured in openXC7/nextpnr#175.
