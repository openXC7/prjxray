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
# See ../cmt_phaser.py.
import os
import runpy
os.environ["CMT_HALF"] = "lower"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cmt_phaser.py"), run_name="__main__")
