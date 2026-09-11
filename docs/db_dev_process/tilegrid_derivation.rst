Deriving a tilegrid, and the gate that keeps it honest
======================================================

``utils/tilegrid_derive.py`` builds a device ``tilegrid.json`` out of a Vivado
grid dump and the device models the database already holds, without running
``005-tilegrid`` and without a bitstream.  It exists to be a *second opinion*:
run the fuzzer, derive the same device, compare.  Where the two agree the
model has been measured twice by methods that share nothing; where they
disagree, one of them is wrong and the comparison says which tile to look at.

It is also how a model built for the wrong device shows itself.  The committed
``xc7s25`` and ``xc7s75`` models were the ``xc7s50`` fabric for years; what
caught them was this tool refusing to derive them, because their grid declares
44 interconnect columns where their own ``part.yaml`` declares 38 and 54.

The law
-------

Every frame address in a tilegrid has the same shape::

    baseaddr = (block_type << 23) | (bottom << 22) | (row << 17) | (column << 7)

column
    The rank of the tile's own configuration column, counted left to right
    over the grid columns that carry an interconnect tile (``INT_L``,
    ``INT_R``, ``INT_FEEDTHRU_2``) for the ``CLB_IO_CLK`` bus, or a block-RAM
    tile (``BRAM_L``, ``BRAM_R``) for the ``BLOCK_RAM`` bus.  Which of those
    columns a tile belongs to is a fixed per-tile-type grid_x delta: a
    ``CLBLL_L`` sits one column left of its ``INT_L``, a ``DSP_R`` two columns
    right of its ``INT_R``.

    Note the feed-through columns.  Where the configuration centre interrupts
    the fabric, ``INT_FEEDTHRU_2`` sits exactly where the interconnect would;
    the column still exists in the bitstream and still consumes a column
    index.  That is why ``xc7s25`` declares 38 configuration columns in its
    bottom half but has only 32 interconnect columns.

bottom, row
    The clock-region row the tile lives in, numbered outward from the middle
    of the device.  Which rows exist in each half comes from ``part.yaml``.

offset, words, frames
    A fixed function of the tile type and of the tile's vertical position
    inside its clock-region row.  ``frames`` is capped by the column's own
    ``frame_count``, exactly as ``fuzzers/005-tilegrid/util.py`` caps it.

The per-tile-type deltas and geometries are not written down anywhere in the
tool: they are learned from the device models in the database, which is to say
from bitstreams that ``005-tilegrid`` measured on real silicon.  The law is
learned per family, because tile geometry does differ between families.

The gate
--------

A law that cannot rebuild the models we already trust has no business building
one we cannot check, so::

    utils/tilegrid_derive.py calibrate --database-dir database

leaves one device model out at a time, learns the law from the rest of its
family, rebuilds it from its grid alone and diffs it against the committed
file.  It needs no Vivado.  Against openXC7/prjxray-db at the merge of #15,
**11 of the 17 device models come out byte for byte identical, 500405
``bits`` entries in all**:

======== =============================================== ===============
family   device models reproduced exactly                bits entries
======== =============================================== ===============
artix7   xc7a100t, xc7a50t                                        29834
kintex7  xc7k70t, xc7k160t, xc7k325t, xc7k420t, xc7k480t          287790
spartan7 xc7s50                                                   10342
zynq7    xc7z030, xc7z045, xc7z100                                172439
======== =============================================== ===============

The remaining six are accounted for, and the same command prints why:

``xc7vx485t`` (skipped)
    The only virtex7 device model there is; nothing to learn the law from.

``xc7z010`` (refused)
    Its PS7 swallows 24 configuration columns down the left-hand side, so the
    column rule does not hold on it at all: 38 interconnect columns in the
    grid against 56 in ``part.yaml``.  The tool refuses the device rather than
    deriving nonsense, and refuses to learn from it too.

``xc7a200t`` (220 entries missing)
    The only artix7 device with GTP transceivers in the middle of the die.  No
    other artix7 model carries ``GTP_*_MID_*``, so the law has nothing to
    learn their geometry from and leaves them unaddressed.

``xc7z020`` (159 entries missing)
    The only zynq7 device model with a right-hand high-range I/O column, now
    that ``xc7z010`` is refused.  Every reference it has puts that kind of
    tile on the *left*, so the tool cannot tell which side of ``RIOB33`` its
    interconnect column is on -- and does not guess.

``xc7s25`` (7 entries differ)
    Six upper ``*_SING`` tiles differ in ``alias.start_offset`` alone, where
    the derivation says 0 and the fuzzed model says 2.  This is a real
    inconsistency in the database, not in the law: ``generate_full.py`` has
    written 2 since the VC707 fix, and every model committed before ``xc7s25``
    still says 0.  The seventh is ``MONITOR_BOT_FUJI2``, a XADC variant no
    other spartan7 device has.

``xc7s100`` (7 entries differ)
    This one is worth reading as a result rather than a limitation: the model
    was fuzzed before prjxray#16, so it carries the fingerprint of the
    site-type-off-a-placed-design bug.  ``CLK_BUFG_BOT_R`` sits at offset 98
    where the derivation and thirteen other device models say 93,
    ``CFG_CENTER_MID`` has no address at all, and five ``LIOB33`` tiles have
    none either -- the five whose sites read back as plain ``IOB33`` because
    the ROI design had bound them.

``utils/test_tilegrid_derive.py`` runs the same calibration as a test, with
that table written down: any device model that starts differing in a *new* way
fails it.  It skips when there is no database to calibrate against, since the
repository itself carries only the mapping files.

Where the references disagree
-----------------------------

Two reference models can contradict each other -- that is what a wrong model
looks like from the inside.  The tool settles a disagreement in four steps:

1. the geometry the most devices of the family agree on wins;
2. if the family is split evenly, a reference named with
   ``--prefer-reference`` wins outright.  An explicit choice beats the proxy
   votes below, which can be *stale*: on the ``*_SING`` tiles'
   ``alias.start_offset``, every device model committed before ``xc7s25``
   still votes the 0 that ``generate_full.py`` has not written since the
   VC707 fix.  A preference never overrides a majority of the family itself
   -- narrow ``--reference`` for that;
3. with nothing preferred, the models of the *other* families break the tie;
4. if nothing breaks it, the alphabetically first of the tied references
   wins -- a fixed rule, never the order the references happened to be given
   in.  The conflict is reported as ``arbitrary``, and ``derive`` refuses to
   proceed on a geometry its grid actually uses unless told to, with
   ``--allow-reference-conflicts``; then it prints each such pick, what won,
   and what the alternative was.

Whichever way it goes, the disagreement is printed with the vote::

    CLK_BUFG_BOT_R row_position=47 CLB_IO_CLK -- resolved by other families
        {"frames": 30, "offset": 93, "words": 8} xc7s50 (+13 elsewhere)
        {"frames": 30, "offset": 98, "words": 3} xc7s100

Mind that the tie-breaking model is only as complete as the database you
point at: run ``derive`` against a family-only checkout and step 3 has nobody
left to ask, so every family tie lands on step 4.  The pick is still
deterministic and is still printed, but if you *know* which reference to
trust -- the freshly fuzzed one, say -- this is what ``--prefer-reference``
is for.

Adding a device
---------------

The tool never invents.  A tile type no reference model of the family carries
gets no address at all, and ``derive`` says so at the end of its run.  With
``--cross-family-fallback`` it will borrow such a geometry from the other
families and count those entries separately; that is worth having for a new
device (on ``xc7z020`` it fills the whole right-hand I/O column correctly, 156
entries), and worth being careful with (it also addresses hard blocks such as
``GTP_*`` and ``PCIE_*`` that the committed models deliberately leave alone).

The flow for a device the database does not have yet, alongside
:doc:`newpart`::

    # 1. the grid, straight out of Vivado.  No ROI design, no settings file:
    #    005-tilegrid reads the grid off a device with nothing placed on it,
    #    and this runs that same tcl on its own.
    source settings/<family>.sh
    utils/dump_grid.sh <part> work/<part>

    # 2. the derived model, and what it could not address
    utils/tilegrid_derive.py derive --db-root database/<family> --part <part> \
        --tiles work/<part>/tiles.txt --pin-func work/<part>/pin_func.txt \
        --output work/<part>/derived.json

    # 3. the fuzzer, which is still what the database ships
    make -j$(nproc) db-part-only-<new_device>

    # 4. the two against each other
    utils/tilegrid_derive.py compare database/<family>/<device>/tilegrid.json \
        work/<part>/derived.json --labels fuzzed derived

Step 4 is the point of the exercise.  ``compare`` exits non-zero when anything
differs, so it can be a gate; every difference it prints is either a bug in
the fuzzer run, a gap in the database, or a tile type the law could not learn,
and it is worth knowing which before the model is committed.

The same three commands cross-check a model that is already committed: give
``derive`` the committed ``tilegrid.json`` with ``--grid`` instead of a fresh
dump, and it will rebuild the frame addresses from the grid the model itself
carries.
