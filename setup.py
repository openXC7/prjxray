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

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="prjxray",
    version="0.0.1",
    author="SymbiFlow Authors",
    author_email="symbiflow@lists.librecores.org",
    description="Project X-Ray libraries",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/openXC7/prjxray",
    packages=['prjxray'],
    install_requires=[
        'fasm',
        'intervaltree',
        'numpy',
        'pyyaml',
        'simplejson',
    ],
    extras_require={
        # Only needed by the fuzzing-only node lookup code (prjxray.node_lookup
        # and prjxray.lib.NodeLookup), see SymbiFlow/prjxray#1624.
        'fuzzers': ['progressbar2', 'pyjson5'],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: ISC License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': ['fasm2frames=utils.fasm2frames:main'],
    })
