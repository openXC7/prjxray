#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
"""Convert bitread -y output into a frames file for xc7frames2bit.

Usage: bits2frm.py <bits file> <words per frame> <frames file>
"""

import collections
import sys


def main():
    bits_file, words_per_frame, frm_file = sys.argv[1:]
    words_per_frame = int(words_per_frame)

    frames = collections.defaultdict(lambda: [0] * words_per_frame)
    with open(bits_file) as f:
        for line in f:
            line = line.strip()
            if not line.startswith('bit_'):
                continue
            # bit_<frame address>_<word>_<bit>
            _, frame, word, bit = line.split('_')
            frames[int(frame, 16)][int(word)] |= 1 << int(bit)

    with open(frm_file, 'w') as f:
        for frame in sorted(frames):
            f.write(
                '0x%08x %s\n' %
                (frame, ','.join('0x%08x' % w for w in frames[frame])))


if __name__ == '__main__':
    main()
