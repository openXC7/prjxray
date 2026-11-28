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
import codecs
import fasm
import sys

from prjxray import bitstream
from prjxray.tile_segbits_alias import TileSegbitsAlias


class FasmLookupError(Exception):
    pass


class FasmOutOfTileBits(FasmLookupError):
    '''An aliased tile's feature maps to bits outside the tile.'''
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
        decoder = codecs.getincrementaldecoder('utf-8')()
        offset = 0
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(1 << 20)
                decoder.decode(chunk, final=not chunk)
                if not chunk:
                    break
                offset += len(chunk)
    except UnicodeDecodeError as e:
        # e.start counts from the start of the bytes the decoder still
        # held, which may begin in the previous chunk.
        pending = len(e.object) - len(chunk)
        raise FasmParseError(
            'Parse error - not UTF-8: byte 0x{:02x} at offset {} (in {})'.
            format(e.object[e.start], offset - pending + e.start,
                   filename)) from None
    except OSError as e:
        raise FasmParseError(
            'Parse error - {} (in {})'.format(e.strerror, filename)) from None

    # When fasm's ANTLR parser cannot convert a value (for example one wider
    # than its feature), the exception is raised inside a ctypes callback,
    # where Python only prints it, and the parser returns None. Hold back
    # such exceptions with an unraisable hook (Python 3.8+) to report the
    # reason properly; any that turn out not to explain a failure are passed
    # on to the previous hook afterwards.
    unraisable = []
    old_hook = getattr(sys, 'unraisablehook', None)
    if old_hook is not None:
        sys.unraisablehook = unraisable.append
    try:
        lines = fasm.parse_fasm_filename(filename)
        if lines is not None:
            # The textX parser returns a generator, which raises as it goes.
            lines = list(lines)
    except (AssertionError, ValueError) as e:
        # Both parsers check that values fit with assert, and Python's int()
        # limits how many digits a value can have.
        raise FasmParseError(
            'Parse error - invalid value: {} (in {})'.format(
                e, filename)) from None
    except Exception as e:
        if not str(e).startswith('Parse error'):
            raise
        raise FasmParseError('{} (in {})'.format(e, filename)) from None
    finally:
        if old_hook is not None:
            sys.unraisablehook = old_hook

    if lines is not None or not unraisable:
        for u in unraisable:
            old_hook(u)

    if lines is None:
        e = unraisable[0].exc_value if unraisable else None
        if isinstance(e, UnicodeDecodeError):
            # It decodes its own output as ASCII, so this is non-ASCII text
            # (even in a comment).
            reason = 'non-ASCII text, which fasm cannot read'
        elif e is not None:
            reason = 'invalid value: {}'.format(e)
        else:
            reason = 'see the message above'
        raise FasmParseError(
            'Parse error - {} (in {})'.format(reason, filename))

    return lines


def init_frame_at_address(frames, addr):
    '''Set given frame to 0 if not initialized '''
    if not addr in frames:
        frames[addr] = [0 for _i in range(bitstream.FRAME_WORD_COUNT)]


class FasmAssembler(object):
    def __init__(self, db, strict=False):
        self.db = db
        self.grid = db.grid()

        # A feature that an alias maps to bits outside its tile is left out
        # entirely. That is an error when strict, else a warning.
        # XRAY_ALLOW_MISSING_FEATURES=1 does not turn the error into a
        # warning.
        self.strict = strict
        self.out_of_tile = []

        self.seen_tile = set()
        self.frames_in_use = set()

        self.frames = {}
        self.frames_line = {}

        self.feature_callback = lambda feature: None

    def set_feature_callback(self, feature_callback):
        self.feature_callback = feature_callback

    def check_out_of_tile(self):
        '''When strict, fail if a feature was left out for having bits
        outside its tile.'''
        if self.strict and self.out_of_tile:
            raise FasmOutOfTileBits('\n'.join(self.out_of_tile))

    def get_frames(self, sparse=False):
        # Also covers the features fasm2frames adds after the FASM file
        # (STEPDOWN, bank glue), whose lookup errors it may ignore.
        self.check_out_of_tile()

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
        # A negative word would index the frame from its end.
        if not 0 <= word_addr < bitstream.FRAME_WORD_COUNT:
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
        if not 0 <= word_addr < bitstream.FRAME_WORD_COUNT:
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

        try:
            feature_bits = list(
                segbits.feature_to_bits(gridinfo.bits, db_k, address))
        except KeyError:
            raise FasmLookupError(
                "Segment DB %s, key %s not found from line '%s'" %
                (gridinfo.tile_type, db_k, line))

        # Through an alias (a *_SING tile uses the segbits of the full IOB or
        # IOI tile, shifted by start_offset), a feature can map to words
        # outside the tile: words of another tile, or past the end of the
        # frame. The decoder ignores such bits (TileSegbitsAlias.match_filter),
        # so don't write them either. A tile's own segbits are left alone,
        # since some of them do have bits outside the tile's words (for
        # example virtex7 HCLK_IOI.STEPDOWN).
        aliased = isinstance(segbits, TileSegbitsAlias)

        def in_tile(block_type, bit):
            if not aliased:
                return True
            tile_bits = gridinfo.bits[block_type]
            word = bit.word_bit // bitstream.WORD_SIZE_BITS
            return tile_bits.offset <= word < tile_bits.offset + tile_bits.words

        outside = {}
        for block_type, bit in feature_bits:
            if not in_tile(block_type, bit):
                outside.setdefault(block_type, set()).add(
                    bit.word_bit // bitstream.WORD_SIZE_BITS)
        if outside:
            where = []
            for block_type, words in outside.items():
                tile_bits = gridinfo.bits[block_type]
                where.append(
                    'word %s, but %s has words %d-%d' % (
                        ', '.join(str(w) for w in sorted(words)),
                        block_type.value, tile_bits.offset,
                        tile_bits.offset + tile_bits.words - 1))
            # Leave the whole feature out, including the bits that are in
            # the tile: some aliased features (for example
            # DIFF.ZIBUF_LOW_PWR) also need the absent partner site's
            # words, and only half of such a setting is not useful.
            raise FasmOutOfTileBits(
                "Feature %s of tile %s has bits outside the tile (%s) from "
                "line '%s'" % (feature, tile, '; '.join(where), line))

        any_bits = set()
        for block_type, bit in feature_bits:
            any_bits.add(block_type)
            update_segbit(bit)

        for block_type in any_bits:
            # Mark all frames used by this tile as in use.
            bits = gridinfo.bits[block_type]
            for frame in range(bits.base_address,
                               bits.base_address + bits.frames):
                self.frames_in_use.add(frame)

    def add_fasm_line(self, line, missing_features):
        if not line.set_feature:
            return

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
        left_out = False
        for flat_set_feature in fasm.canonical_features(line.set_feature):
            address = 0
            if flat_set_feature.start is not None:
                address = flat_set_feature.start

            try:
                self.enable_feature(tile, feature, address, line_str)
            except FasmOutOfTileBits as e:
                # Kept apart from missing_features, which the caller may
                # ignore (XRAY_ALLOW_MISSING_FEATURES=1, bank glue).
                self.out_of_tile.append(str(e))
                left_out = True
                if not self.strict:
                    print(
                        'WARNING: %s; leaving the feature out' % e,
                        file=sys.stderr)
            except FasmLookupError as e:
                missing_features.append(str(e))

        # A feature left out is not reported as set, so that fasm2frames
        # does not, for example, copy its STEPDOWN to the rest of the bank.
        if not left_out:
            self.feature_callback(line.set_feature)

    def parse_fasm_filename(self, filename, extra_features=[]):
        missing_features = []
        for line in parse_fasm_file(filename):
            self.add_fasm_line(line, missing_features)

        for line in extra_features:
            self.add_fasm_line(line, missing_features)

        self.check_out_of_tile()

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
