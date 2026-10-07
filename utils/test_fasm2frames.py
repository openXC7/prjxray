#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
# TODO: need better coverage for different tile types

from io import StringIO
import os
import os.path
import re
import unittest
import tempfile

import prjxray
import utils.fasm2frames as fasm2frames
from prjxray.util import OpenSafeFile

from textx.exceptions import TextXSyntaxError


def frm2bits(txt):
    '''
    Convert output .frm file text to set of (frame addr, word #, bit index) tuples
    '''
    bits_out = set()
    for l in txt.split('\n'):
        l = l.strip()
        if not l:
            continue
        # 0x00020500 0x00000000,0x00000000,0x00000000,...
        addr, words = l.split(' ')
        addr = int(addr, 0)
        words = words.split(',')
        assert (101 == len(words))
        for wordi, word in enumerate(words):
            word = int(word, 0)
            for biti in range(32):
                val = word & (1 << biti)
                if val:
                    bits_out.add((addr, wordi, biti))
    return bits_out


def bitread2bits(txt):
    '''
    Convert .bits text file (ie bitread output) to set of (frame addr, word #, bit index) tuples
    '''
    bits_ref = set()
    for l in txt.split('\n'):
        l = l.strip()
        if not l:
            continue
        # bit_0002050b_004_14
        m = re.match(r'bit_(.{8})_(.{3})_(.{2})', l)
        addr = int(m.group(1), 16)
        word = int(m.group(2), 10)
        bit = int(m.group(3), 10)
        bits_ref.add((addr, word, bit))
    return bits_ref


class TestStringMethods(unittest.TestCase):
    def filename_test_data(self, fname):
        return os.path.join(os.path.dirname(__file__), 'test_data', fname)

    def get_test_data(self, fname):
        with OpenSafeFile(self.filename_test_data(fname)) as f:
            return f.read()

    def fasm2frames(self, fin_data, **kw):
        with tempfile.NamedTemporaryFile(suffix='.fasm') as fin:
            fin.write(fin_data.encode('utf-8'))
            fin.flush()

            fout = StringIO()
            fasm2frames.run(
                self.filename_test_data('db'), "xc7a200tffg1156-1", fin.name,
                fout, **kw)

            return fout.getvalue()

    def test_lut(self):
        '''Simple smoke test on just the LUTs'''
        self.fasm2frames(self.get_test_data('lut.fasm'))

    def bitread_frm_equals(self, frm_fn, bitread_fn):
        fout = self.fasm2frames(self.get_test_data(frm_fn))

        # Build a list of output used bits
        bits_out = frm2bits(fout)

        # Build a list of reference used bits
        bits_ref = bitread2bits(self.get_test_data(bitread_fn))

        # Now check for equivilence vs reference design
        self.assertEqual(len(bits_ref), len(bits_out))
        self.assertEqual(bits_ref, bits_out)

    def test_lut_int(self):
        self.bitread_frm_equals('lut_int.fasm', 'lut_int/design.bits')

    def test_ff_int(self):
        self.bitread_frm_equals('ff_int.fasm', 'ff_int/design.bits')

    @unittest.skip
    def test_ff_int_op1(self):
        '''Omitted key set to '''
        self.bitread_frm_equals('ff_int_op1.fasm', 'ff_int/design.bits')

    # Same check as above, but isolated test case
    def test_opkey_01_default(self):
        '''Optional key with binary omitted value should produce valid result'''
        self.fasm2frames("CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX")

    @unittest.skip
    def test_opkey_01_1(self):
        self.fasm2frames("CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 1")

    @unittest.skip
    def test_opkey_enum(self):
        '''Optional key with enumerated value should produce syntax error'''
        try:
            # CLBLM_L.SLICEM_X0.AMUXFF.O6 !30_06 !30_07 !30_08 30_11
            self.fasm2frames("CLBLM_L_X10Y102.SLICEM_X0.AFFMUX.O6")
            self.fail("Expected syntax error")
        except TextXSyntaxError:
            pass

    def test_ff_int_0s(self):
        '''Explicit 0 entries'''
        self.bitread_frm_equals('ff_int_0s.fasm', 'ff_int/design.bits')

    def test_badkey(self):
        '''Bad key should throw syntax error'''
        try:
            self.fasm2frames("CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 2")
            self.fail("Expected syntax error")
        except TextXSyntaxError:
            pass

    @unittest.skip
    def test_dupkey(self):
        '''Duplicate key should throw syntax error'''
        try:
            self.fasm2frames(
                """\
CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 0
CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 1
""")
            self.fail("Expected syntax error")
        except TextXSyntaxError:
            pass

    @unittest.skip
    def test_sparse(self):
        '''Verify sparse equivalent to normal encoding'''
        frm_fn = 'lut_int.fasm'

        fout_sparse_txt = self.fasm2frames(
            self.get_test_data(frm_fn), sparse=True)
        bits_sparse = frm2bits(fout_sparse_txt)

        fout_full_txt = self.fasm2frames(
            self.get_test_data(frm_fn), sparse=False)
        bits_full = frm2bits(fout_full_txt)

        # Now check for equivilence vs reference design
        self.assertEquals(len(bits_sparse), len(bits_full))
        self.assertEquals(bits_sparse, bits_full)

        # Verify the full ROI is way bigger description
        # It will still be decent size though since even sparse occupies all columns in that area
        self.assertGreaterEqual(len(fout_full_txt), len(fout_sparse_txt) * 4)

    def test_stepdown_1(self):
        self.bitread_frm_equals(
            'iob/liob_stepdown.fasm', 'iob/liob_stepdown.bits')

    def test_stepdown_2(self):
        self.bitread_frm_equals(
            'iob/riob_stepdown.fasm', 'iob/riob_stepdown.bits')

    # LIOB18_X1Y10 and LIOI_X2Y10 are grid neighbours sharing baseaddr
    # 0x00421000, offset 18 (the frames of virtex7's LIOB18_X81Y10 and
    # LIOI_X82Y10, renamed so the X81 column's own glue rule stays out).
    # OBUF_HP_BANK_GLUE of IOB_Y1 is OLOGIC_Y1's OQUSED (30_41), OMUX.D1
    # (32_16) and OSERDES.DATA_RATE_TQ.BUF (33_61).
    HP_DRIVE = 'LIOB18_X1Y10.IOB_Y1.LVCMOS15_LVCMOS18.DRIVE.I12_I16_I2_I4_I6_I8\n'
    HP_OQUSED = (0x0042101e, 19, 9)
    HP_OMUX_D1 = (0x00421020, 18, 16)
    HP_TQ_BUF = (0x00421021, 19, 29)
    HP_TQ_DDR = (0x00421021, 19, 25)

    def test_hp_glue_pass_through(self):
        '''An HP output with no OLOGIC cell gets OBUF_HP_BANK_GLUE'''
        bits = frm2bits(self.fasm2frames(self.HP_DRIVE))
        for bit in (self.HP_OQUSED, self.HP_OMUX_D1, self.HP_TQ_BUF):
            self.assertIn(bit, bits)

        # ZINV_T1 is the one pass-through feature that sets none of the glue
        # bits, so here they can only come from the glue.
        bits = frm2bits(
            self.fasm2frames(
                self.HP_DRIVE + 'LIOI_X2Y10.OLOGIC_Y1.ZINV_T1\n'))
        for bit in (self.HP_OQUSED, self.HP_OMUX_D1, self.HP_TQ_BUF):
            self.assertIn(bit, bits)

    def test_hp_glue_oddr_on_tristate(self):
        '''An ODDR on T: the glue's DATA_RATE_TQ.BUF must not be injected'''
        bits = frm2bits(
            self.fasm2frames(
                self.HP_DRIVE + 'LIOI_X2Y10.OLOGIC_Y1.OQUSED\n'
                'LIOI_X2Y10.OLOGIC_Y1.OMUX.D1\n'
                'LIOI_X2Y10.OLOGIC_Y1.OSERDES.DATA_RATE_TQ.DDR\n'
                'LIOI_X2Y10.OLOGIC_Y1.OSERDES.TSRTYPE.SYNC\n'
                'LIOI_X2Y10.OLOGIC_Y1.ZINIT_TQ\n'
                'LIOI_X2Y10.OLOGIC_Y1.ZINV_T2\n'))
        self.assertIn(self.HP_TQ_DDR, bits)
        self.assertNotIn(self.HP_TQ_BUF, bits)

    def test_hp_glue_oddr_on_data(self):
        '''An ODDR on the data: the glue's OMUX.D1 must not be injected'''
        bits = frm2bits(
            self.fasm2frames(
                self.HP_DRIVE + 'LIOI_X2Y10.OLOGIC_Y1.ODDR_TDDR.IN_USE\n'
                'LIOI_X2Y10.OLOGIC_Y1.OQUSED\n'
                'LIOI_X2Y10.OLOGIC_Y1.OSERDES.DATA_RATE_OQ.DDR\n'
                'LIOI_X2Y10.OLOGIC_Y1.OSERDES.DATA_RATE_TQ.BUF\n'
                'LIOI_X2Y10.OLOGIC_Y1.ZINV_CLK\n'))
        self.assertIn(self.HP_OQUSED, bits)
        self.assertNotIn(self.HP_OMUX_D1, bits)


if __name__ == '__main__':
    unittest.main()
