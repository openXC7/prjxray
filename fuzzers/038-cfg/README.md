# cfg fuzzer

This fuzzer solves some of the bits in the CFG_CENTER_MID tile
The tile contains sites of the following types: BSCAN, USR_ACCESS, CAPTURE, STARTUP, FRAME_ECC, DCIRESET and ICAP.
DCIRESET and USR_ACCESS don't really have any parameters.
The parameters on CAPTURE and FRAME_ECC don't toggle any bits in the bitstream.

The last two specimens (25 and 26) leave the ICAPE2 out, so the fuzzer also
derives `ICAP.IN_USE`: `26_2206 26_2207 27_2205` on every other 7-series
family.  Every other specimen places the ICAPE2 at `ICAP_X0Y1`, which is the
site these database features use; `gen_sites()` excludes `ICAP_X0Y0`.
On Zynq the three bits are set in every bitstream, with or without an
ICAPE2, so they solve as a const1 and `add_constant_bits.py` adds the
feature under both its names.
