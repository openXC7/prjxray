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
import fasm
import sys

from prjxray import bitstream


class FasmLookupError(Exception):
    pass


class FasmInconsistentBits(Exception):
    pass


class FasmParseError(Exception):
    '''The FASM input could not be parsed.

    The message starts with 'Parse error', like the errors raised by fasm's
    ANTLR parser.
    '''
    pass


def parse_fasm_file(filename):
    '''Parse a FASM file, raising FasmParseError for input fasm rejects.'''
    # fasm's ANTLR parser aborts the whole process on input that is not
    # UTF-8, so check that first.
    try:
        with open(filename, 'rb') as f:
            f.read().decode('utf-8')
    except UnicodeDecodeError as e:
        raise FasmParseError(
            'Parse error - not UTF-8: byte 0x{:02x} at offset {} (in {})'.
            format(e.object[e.start], e.start, filename)) from None
    except OSError as e:
        raise FasmParseError(
            'Parse error - {} (in {})'.format(e.strerror, filename)) from None

    # When fasm's ANTLR parser cannot convert a value (for example one wider
    # than its feature), the exception is raised inside a ctypes callback,
    # where Python only prints it, and the parser returns None. Catch it
    # with an unraisable hook to report it properly.
    callback_errors = []
    old_hook = sys.unraisablehook
    sys.unraisablehook = lambda u: callback_errors.append(u.exc_value)
    try:
        lines = fasm.parse_fasm_filename(filename)
    except Exception as e:
        if not str(e).startswith('Parse error'):
            raise
        raise FasmParseError('{} (in {})'.format(e, filename)) from None
    finally:
        sys.unraisablehook = old_hook

    if lines is None:
        reason = str(callback_errors[0]) if callback_errors else 'unknown'
        raise FasmParseError(
            'Parse error - invalid value: {} (in {})'.format(
                reason, filename))

    return lines


def init_frame_at_address(frames, addr):
    '''Set given frame to 0 if not initialized '''
    if not addr in frames:
        frames[addr] = [0 for _i in range(bitstream.FRAME_WORD_COUNT)]


class FasmAssembler(object):
    def __init__(self, db):
        self.db = db
        self.grid = db.grid()

        self.seen_tile = set()
        self.frames_in_use = set()

        self.frames = {}
        self.frames_line = {}

        self.feature_callback = lambda feature: None

    def set_feature_callback(self, feature_callback):
        self.feature_callback = feature_callback

    def get_frames(self, sparse=False):
        if not sparse:
            frames = self.frames_init()
        else:
            # Even in sparse mode, zero all frames for any tile that is
            # setting a bit.  This handles the case where the tile has
            # multiple frames, but the FASM only specifies some of the frames.
            frames = {}
            for frame in self.frames_in_use:
                init_frame_at_address(frames, frame)

        for (frame_addr, word_addr, bit_index), is_set in self.frames.items():
            init_frame_at_address(frames, frame_addr)

            if word_addr >= 101:
                print(f"get_frames: invalid word address {word_addr} in line: {self.frames_line[(frame_addr, word_addr, bit_index)]}", file=sys.stderr)
            if frame_addr not in frames:
                print(f"get_frames: invalid frame address {frame_addr:x8}", file=sys.stderr)
            if is_set:
                frames[frame_addr][word_addr] |= 1 << bit_index

        return frames

    def frames_init(self):
        '''Set all frames to 0'''
        frames = {}

        for bits_info in self.grid.iter_all_frames():
            for coli in range(bits_info.bits.frames):
                init_frame_at_address(
                    frames, bits_info.bits.base_address + coli)

        return frames

    def frame_set(self, frame_addr, word_addr, bit_index, line):
        '''Set given bit in given frame address and word'''
        assert bit_index is not None

        key = (frame_addr, word_addr, bit_index)
        if word_addr >= 101:
            print(f"frame_set: invalid word address {word_addr} in line: {line}", file=sys.stderr)
            return
        if key in self.frames:
            if self.frames[key] != 1:
                raise FasmInconsistentBits(
                    'FASM line "{}" wanted to set bit {} but was cleared by FASM line "{}"'
                    .format(
                        line,
                        key,
                        self.frames_line[key],
                    ))
            return

        self.frames[key] = 1
        self.frames_line[key] = line

    def frame_clear(self, frame_addr, word_addr, bit_index, line):
        '''Set given bit in given frame address and word'''
        assert bit_index is not None

        key = (frame_addr, word_addr, bit_index)
        if word_addr >= 101:
            print(f"frame_clear: invalid word address {word_addr} in line: {line}", file=sys.stderr)
            return
        if key in self.frames:
            if self.frames[key] != 0:
                raise FasmInconsistentBits(
                    'FASM line "{}" wanted to clear bit {} but was set by FASM line "{}"'
                    .format(
                        line,
                        key,
                        self.frames_line[key],
                    ))
            return

        self.frames[key] = 0
        self.frames_line[key] = line

    def enable_feature(self, tile, feature, address, line):
        try:
            gridinfo = self.grid.gridinfo_at_tilename(tile)
        except KeyError:
            raise FasmLookupError(
                "Tile %s not found in the tile grid (wrong part?) from line "
                "'%s'" % (tile, line)) from None

        def update_segbit(bit):
            '''Set or clear a single bit in a segment at the given word column and word bit position'''

            frame_addr = bit.word_column
            word_addr = bit.word_bit // bitstream.WORD_SIZE_BITS
            bit_index = bit.word_bit % bitstream.WORD_SIZE_BITS

            if bit.isset:
                self.frame_set(frame_addr, word_addr, bit_index, line)
            else:
                self.frame_clear(frame_addr, word_addr, bit_index, line)

        segbits = self.grid.get_tile_segbits_at_tilename(tile)

        self.seen_tile.add(tile)

        db_k = '%s.%s' % (gridinfo.tile_type, feature)

        any_bits = set()

        try:
            for block_type, bit in segbits.feature_to_bits(gridinfo.bits, db_k,
                                                           address):
                any_bits.add(block_type)
                update_segbit(bit)
        except KeyError:
            raise FasmLookupError(
                "Segment DB %s, key %s not found from line '%s'" %
                (gridinfo.tile_type, db_k, line))

        for block_type in any_bits:
            # Mark all frames used by this tile as in use.
            bits = gridinfo.bits[block_type]
            for frame in range(bits.base_address,
                               bits.base_address + bits.frames):
                self.frames_in_use.add(frame)

    def add_fasm_line(self, line, missing_features):
        if not line.set_feature:
            return

        self.feature_callback(line.set_feature)

        line_strs = tuple(fasm.fasm_line_to_string(line))
        assert len(line_strs) == 1
        line_str = line_strs[0]

        parts = line.set_feature.feature.split('.')
        tile = parts[0]
        feature = '.'.join(parts[1:])

        # canonical_features flattens multibit feature enables to only
        # single bit features, which is what enable_feature expects.
        #
        # canonical_features also filters out features that are not enabled,
        # which are no-ops.
        for flat_set_feature in fasm.canonical_features(line.set_feature):
            address = 0
            if flat_set_feature.start is not None:
                address = flat_set_feature.start

            try:
                self.enable_feature(tile, feature, address, line_str)
            except FasmLookupError as e:
                missing_features.append(str(e))

    def parse_fasm_filename(self, filename, extra_features=[]):
        missing_features = []
        for line in parse_fasm_file(filename):
            self.add_fasm_line(line, missing_features)

        for line in extra_features:
            self.add_fasm_line(line, missing_features)

        if missing_features:
            # Allow the assembler to keep going when only a small number of
            # niche segbits (e.g. IOB_Y1.IBUF_HP_BANK_GLUE — not yet fuzzed
            # for the slave side) are missing.  The resulting bitstream is
            # missing those bits — Vivado's silicon defaults usually cover
            # them — and the user gets a console warning per missing line.
            # Set XRAY_ALLOW_MISSING_FEATURES=1 to opt in.
            import os
            if os.environ.get("XRAY_ALLOW_MISSING_FEATURES") == "1":
                import sys
                print("WARNING: " + str(len(missing_features))
                        + " missing-feature lines suppressed by "
                        "XRAY_ALLOW_MISSING_FEATURES=1:", file=sys.stderr)
                for m in missing_features:
                    print("  " + m, file=sys.stderr)
                return
            raise FasmLookupError('\n'.join(missing_features))

    def mark_roi_frames(self, roi):
        for tile in roi.gen_tiles():
            gridinfo = self.grid.gridinfo_at_tilename(tile)

            for block_type in gridinfo.bits:
                bits = gridinfo.bits[block_type]
                for frame in range(bits.base_address,
                                   bits.base_address + bits.frames):
                    self.frames_in_use.add(frame)
