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
"""Tag one specimen of the ICAP IN_USE fuzzer.

Only the CFG_CENTER_MID control frames are of interest; the ICAP's data
routing lives in frames 0..25 and is unrelated to IN_USE.
"""
import json

from prjxray.segmaker import Segmaker


def bitfilter(frame, word):
    return frame >= 26


def run():
    with open('params.jl') as f:
        icap_site = json.load(f)['icap_site']

    segmk = Segmaker('design.bits')

    if icap_site is None:
        # No ICAPE2: leave the tag on the ICAP1 site so the feature exists in
        # every specimen, with value 0.
        segmk.add_site_tag('ICAP_X0Y1', 'IN_USE', False)
    else:
        # The database's ICAP features are fuzzed on ICAP_X0Y1, so that is
        # the site whose pattern defines CFG_CENTER_MID.ICAP.IN_USE.
        segmk.add_site_tag(icap_site, 'IN_USE', icap_site == 'ICAP_X0Y1')

    segmk.compile(bitfilter=bitfilter)
    segmk.write()


if __name__ == '__main__':
    run()
