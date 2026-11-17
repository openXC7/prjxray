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
"""Generate the three specimens of the ICAP IN_USE fuzzer.

The CFG_CENTER_MID tile has two ICAP sites.  Whether an ICAPE2 is present
changes a few bits in the tile's own frames; those are the bits recorded by
the existing 038-cfg database as ``ICAP.IN_USE``.  The bits are *site
specific*: ICAP_X0Y0 and ICAP_X0Y1 use two disjoint three bit patterns, and a
design with no ICAPE2 has neither.

Three specimens separate those patterns from everything else that an ICAPE2
turns on in the tile:

  specimen 1: no ICAPE2                  IN_USE = 0 (tagged on ICAP_X0Y1)
  specimen 2: ICAPE2 at ICAP_X0Y0        IN_USE = 0
  specimen 3: ICAPE2 at ICAP_X0Y1        IN_USE = 1

Bits that are set by any ICAPE2 (both sites) are set with the tag both 0 and 1
and are dropped by segmatch.  The X0Y0 pattern is likewise set with tag 0 in
specimen 2 but cleared with tag 0 in specimen 1, so it does not solve either.
Only the ICAP_X0Y1 pattern correlates with the tag, which is the site the
database's existing (site-less) ICAP features were fuzzed on.
"""
import json
import os

# SEEDN is the specimen number (1, 2, 3) exported by utils/genheader.sh.
ICAP_SITE_BY_SPECIMEN = {
    1: None,
    2: 'ICAP_X0Y0',
    3: 'ICAP_X0Y1',
}

STARTUP = '''\
module top();
    wire cfgmclk;

    // Fixed in every specimen: provides the configuration clock and keeps the
    // STARTUP site constant so only the ICAP bits can differ between
    // specimens.
    (* KEEP, DONT_TOUCH *)
    STARTUPE2 startupe2_i (
        .CFGCLK(),
        .CFGMCLK(cfgmclk),
        .EOS(),
        .PREQ(),
        .CLK(1'b0),
        .GSR(1'b0),
        .GTS(1'b0),
        .KEYCLEARB(1'b1),
        .PACK(1'b0),
        .USRCCLKO(1'b0),
        .USRCCLKTS(1'b1),
        .USRDONEO(1'b1),
        .USRDONETS(1'b1)
    );
'''

ICAP = '''\

    // Enabled (CSIB low, RDWRB high) like a working readback port.
    wire [31:0] icap_o;
    (* KEEP, DONT_TOUCH, LOC = "{site}" *)
    ICAPE2 #(
        .ICAP_WIDTH("X32"),
        .SIM_CFG_FILE_NAME("NONE")
    ) icap_i (
        .O(icap_o),
        .CLK(cfgmclk),
        .CSIB(1'b0),
        .I(32'd0),
        .RDWRB(1'b1)
    );
'''


def run():
    specimen = int(os.environ['SEEDN'])
    icap_site = ICAP_SITE_BY_SPECIMEN[specimen]

    print(STARTUP, end='')
    if icap_site is not None:
        print(ICAP.format(site=icap_site), end='')
    print('endmodule')

    with open('params.jl', 'w') as f:
        json.dump({'icap_site': icap_site}, f, indent=2)


if __name__ == '__main__':
    run()
