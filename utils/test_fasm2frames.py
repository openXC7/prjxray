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
import sys
import unittest
import tempfile
from unittest import mock

import prjxray
from prjxray import fasm_assembler
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

    def test_sparse_no_frames(self):
        '''With nothing to set, --sparse still writes a line'''
        self.assertEqual(self.fasm2frames("", sparse=True), '# no frames\n')

    @unittest.skip
    def test_opkey_01_1(self):
        self.fasm2frames("CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 1")

    def assertSyntaxError(self, fasm_str):
        '''fasm2frames should reject fasm_str with a FASM syntax error.

        fasm's textX parser raises TextXSyntaxError, and its faster ANTLR
        parser raises a plain Exception('Parse error at ...').
        '''
        with self.assertRaises(Exception) as cm:
            self.fasm2frames(fasm_str)
        e = cm.exception
        self.assertTrue(
            isinstance(e, TextXSyntaxError)
            or str(e).startswith('Parse error'),
            "Expected syntax error, got {!r}".format(e))

    @unittest.skip
    def test_opkey_enum(self):
        '''Optional key with enumerated value should produce syntax error'''
        # CLBLM_L.SLICEM_X0.AMUXFF.O6 !30_06 !30_07 !30_08 30_11
        self.assertSyntaxError("CLBLM_L_X10Y102.SLICEM_X0.AFFMUX.O6")

    def test_ff_int_0s(self):
        '''Explicit 0 entries'''
        self.bitread_frm_equals('ff_int_0s.fasm', 'ff_int/design.bits')

    def test_badkey(self):
        '''Bad key should throw syntax error'''
        self.assertSyntaxError("CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 2")

    @unittest.skip
    def test_dupkey(self):
        '''Duplicate key should throw syntax error'''
        self.assertSyntaxError(
            """\
CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 0
CLBLM_L_X10Y102.SLICEM_X0.SRUSEDMUX 1
""")

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

    # LIOB33_SING_X0Y0 (offset 0) and LIOB33_SING_X0Y49 (offset 99) are the
    # bottom and top *_SING tiles of the 0x00400000 frames, both 2 words and
    # aliased to LIOB33 with start_offset 2 and 0. LIOB33 has IOB_Y1 in
    # words 0-1 and IOB_Y0 in words 2-3, so the site a SING tile lacks maps
    # to word -2 (bottom) or 101 (top).
    def fasm2frames_stderr(self, fin_data, **kw):
        stderr = StringIO()
        with mock.patch.object(sys, 'stderr', stderr):
            frm = self.fasm2frames(fin_data, sparse=True, **kw)
        return frm2bits(frm), stderr.getvalue()

    def assertOutsideTile(self, tile, feature, words):
        '''tile.feature warns and is left out, or fails with strict=True'''
        fasm_line = tile + '.' + feature
        message = (
            "Feature {} of tile {} has bits outside the tile ({}) from line "
            "'{}'".format(feature, tile, words, fasm_line))

        stderr = StringIO()
        with mock.patch.object(sys, 'stderr', stderr):
            frm = self.fasm2frames(fasm_line + '\n', sparse=True)
        # Word -2 used to end up in word 99 of the same frame, a bit of the
        # top SING tile. The feature's in-tile bits are left out too, and
        # its frames are not marked in use (a sparse output has no frames).
        self.assertEqual(frm, '# no frames\n')
        self.assertIn(
            'WARNING: ' + message + '; leaving the feature out',
            stderr.getvalue())

        with self.assertRaisesRegex(fasm_assembler.FasmOutOfTileBits,
                                    re.escape(message)):
            self.fasm2frames(fasm_line + '\n', strict=True)

        # XRAY_ALLOW_MISSING_FEATURES=1 lets a missing feature through, but
        # not a feature outside its tile when strict.
        with mock.patch.dict(os.environ,
                             {'XRAY_ALLOW_MISSING_FEATURES': '1'}), \
                mock.patch.object(sys, 'stderr', StringIO()), \
                self.assertRaisesRegex(fasm_assembler.FasmOutOfTileBits,
                                       re.escape(message)):
            self.fasm2frames(
                fasm_line + '\nLIOB33_X0Y1.IOB_Y0.NO_SUCH_FEATURE\n',
                strict=True)

    def test_sing_partly_outside(self):
        '''A feature with bits both in and outside the tile is left out'''
        # IN_DIFF has a bit in each site (words 2 and 0 of LIOB33), like
        # DIFF.ZIBUF_LOW_PWR, so on a bottom SING tile only one is in it.
        self.assertOutsideTile(
            'LIOB33_SING_X0Y0', 'IOB_Y0.SOMETHING.IN_DIFF',
            'word -2, but CLB_IO_CLK has words 0-1')
        # A full LIOB33 tile has both sites.
        bits, _ = self.fasm2frames_stderr(
            'LIOB33_X0Y1.IOB_Y0.SOMETHING.IN_DIFF\n')
        self.assertEqual(bits, {(0x00400000, 2, 4), (0x00400000, 4, 4)})

    def test_sing_outside_stepdown(self):
        '''A STEPDOWN left out is not copied to the rest of the bank'''
        # Otherwise LIOB33_X0Y1, LIOB33_X0Y3 and HCLK_IOI3_X1Y26 of bank 99
        # would get STEPDOWN.
        stderr = StringIO()
        with mock.patch.object(sys, 'stderr', stderr):
            frm = self.fasm2frames(
                'LIOB33_SING_X0Y0.IOB_Y1.SOMETHING.STEPDOWN\n', sparse=True)
        self.assertEqual(frm, '# no frames\n')
        self.assertIn('leaving the feature out', stderr.getvalue())

    def test_strict_missing_features_allowed(self):
        '''strict does not change XRAY_ALLOW_MISSING_FEATURES=1 alone'''
        with mock.patch.dict(os.environ, {'XRAY_ALLOW_MISSING_FEATURES': '1'}):
            bits, stderr = self.fasm2frames_stderr(
                'LIOB33_X0Y1.IOB_Y0.SOMETHING.IN\n'
                'LIOB33_X0Y1.IOB_Y0.NO_SUCH_FEATURE\n',
                strict=True)
        self.assertEqual(bits, {(0x00400000, 4, 1)})
        self.assertIn('missing-feature lines suppressed', stderr)

    def test_sing_bottom_absent_site(self):
        '''A bottom SING tile's IOB_Y1 is below the tile, not in word 99'''
        self.assertOutsideTile(
            'LIOB33_SING_X0Y0', 'IOB_Y1.SOMETHING.IN',
            'word -2, but CLB_IO_CLK has words 0-1')

    def test_sing_top_absent_site(self):
        '''A top SING tile's IOB_Y0 is past the end of the frame'''
        self.assertOutsideTile(
            'LIOB33_SING_X0Y49', 'IOB_Y0.SOMETHING.IN',
            'word 101, but CLB_IO_CLK has words 99-100')

    def test_sing_present_site(self):
        '''The site a SING tile has is set in the tile's own words'''
        for strict in (False, True):
            with self.subTest(strict=strict):
                bits, stderr = self.fasm2frames_stderr(
                    'LIOB33_SING_X0Y0.IOB_Y0.SOMETHING.IN\n'
                    'LIOB33_SING_X0Y49.IOB_Y1.SOMETHING.IN\n',
                    strict=strict)
                self.assertEqual(
                    bits, {(0x00400000, 0, 1), (0x00400000, 99, 1)})
                self.assertNotIn('outside the tile', stderr)

    def test_main_strict(self):
        '''main() --strict reports a feature outside its tile and fails'''
        fasm_line = 'LIOB33_SING_X0Y0.IOB_Y1.SOMETHING.IN'
        with tempfile.TemporaryDirectory() as d:
            fn_in = os.path.join(d, 'design.fasm')
            with open(fn_in, 'w') as f:
                f.write(fasm_line + '\n')
            argv = [
                'fasm2frames', '--db-root',
                self.filename_test_data('db'), '--part', 'xc7a200tffg1156-1',
                '--strict', fn_in,
                os.path.join(d, 'design.frm')
            ]
            stderr = StringIO()
            with mock.patch.object(sys, 'argv', argv), \
                    mock.patch.object(sys, 'stderr', stderr), \
                    self.assertRaises(SystemExit) as cm:
                fasm2frames.main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "fasm2frames: error: Feature IOB_Y1.SOMETHING.IN of tile "
                "LIOB33_SING_X0Y0 has bits outside the tile (word -2, but "
                "CLB_IO_CLK has words 0-1) from line '{}'".format(fasm_line),
                stderr.getvalue())
            self.assertNotIn('Traceback', stderr.getvalue())
            self.assertEqual(os.listdir(d), ['design.fasm'])

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

    def test_unknown_tile(self):
        '''A tile missing from the part is a lookup error, not a KeyError'''
        with self.assertRaisesRegex(fasm_assembler.FasmLookupError,
                                    'Tile CLBLM_L_X999Y999 not found'):
            self.fasm2frames('CLBLM_L_X999Y999.SLICEM_X0.AFF.ZINI\n')

    def test_not_utf8(self):
        '''Input that is not UTF-8 is a parse error'''
        with tempfile.NamedTemporaryFile(suffix='.fasm') as fin:
            fin.write(b'# caf\xe9\nCLBLM_L_X10Y102.SLICEM_X0.AFF.ZINI\n')
            fin.flush()
            with self.assertRaisesRegex(fasm_assembler.FasmParseError,
                                        'not UTF-8'):
                fasm2frames.run(
                    self.filename_test_data('db'), "xc7a200tffg1156-1",
                    fin.name, StringIO())

    def test_value_too_wide(self):
        '''A value wider than its feature is a parse error'''
        with self.assertRaisesRegex(fasm_assembler.FasmParseError,
                                    'invalid value'):
            self.fasm2frames(
                "CLBLM_L_X10Y102.SLICEM_X0.ALUT.INIT[3:0] = 4'd99\n")

    def test_main_error(self):
        '''main() reports an error and removes the output file'''
        with tempfile.TemporaryDirectory() as d:
            fn_in = os.path.join(d, 'design.fasm')
            fn_out = os.path.join(d, 'design.frm')
            with open(fn_in, 'w') as f:
                f.write('CLBLM_L_X10Y102.SLICEM_X0.NOPE\n')
            # Output from an earlier run must not survive a failed one.
            with open(fn_out, 'w') as f:
                f.write('0x00000000 0x00000000\n')
            argv = [
                'fasm2frames', '--db-root',
                self.filename_test_data('db'), '--part', 'xc7a200tffg1156-1',
                fn_in, fn_out
            ]
            stderr = StringIO()
            with mock.patch.object(sys, 'argv', argv), \
                    mock.patch.object(sys, 'stderr', stderr), \
                    self.assertRaises(SystemExit) as cm:
                fasm2frames.main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn('SLICEM_X0.NOPE not found', stderr.getvalue())
            self.assertNotIn('Traceback', stderr.getvalue())
            self.assertEqual(os.listdir(d), ['design.fasm'])

    def test_main_missing_database(self):
        '''main() reports a missing database or part without a traceback'''
        fn_in = self.filename_test_data('ff_int.fasm')
        for db_root, part, message in (
            ('/nonexistent', 'xc7a200tffg1156-1', 'does not exist'),
            (self.filename_test_data('db'), 'xc7nope',
             'Part xc7nope not found'),
        ):
            with self.subTest(db_root=db_root, part=part):
                argv = [
                    'fasm2frames', '--db-root', db_root, '--part', part, fn_in
                ]
                stderr = StringIO()
                with mock.patch.object(sys, 'argv', argv), \
                        mock.patch.object(sys, 'stderr', stderr), \
                        self.assertRaises(SystemExit) as cm:
                    fasm2frames.main()
                self.assertEqual(cm.exception.code, 1)
                self.assertIn(message, stderr.getvalue())
                self.assertNotIn('Traceback', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
