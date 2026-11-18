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
"""Run bit2fasm from a checkout.

The code lives in prjxray/bit2fasm.py so that the installed
bit2fasm console script can import it. This wrapper keeps
`python3 utils/bit2fasm.py` and `import utils.bit2fasm` working.
"""

import os
import sys

if __name__ == '__main__':
    # Running this file directly puts utils/ on sys.path, not the repo root.
    # Put the root first, so that the checkout's prjxray is used even when
    # another version of prjxray is installed, or none is.
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prjxray.bit2fasm import *  # noqa: E402,F401,F403
from prjxray.bit2fasm import main  # noqa: E402

if __name__ == '__main__':
    main()
