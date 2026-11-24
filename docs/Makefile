# Copyright (C) 2017-2020  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
# Minimal makefile for Sphinx documentation
#

MAKEDIR := $(dir $(lastword $(MAKEFILE_LIST)))

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SPHINXAUTOBUILD   = sphinx-autobuild
SPHINXPROJ    = ProjectX-Ray
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

livehtml:
	@$(SPHINXAUTOBUILD) -b html --ignore \*.swp --ignore \*~ $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html"

.PHONY: help livehtml Makefile

# Update fuzzer / minitest markdown links.
#
# $(call update-links,DIR) links every DIR/*/README.md into
# db_dev_process/DIR as NAME.md, NAME being the directory name without its
# NNN- prefix. Only missing links are created and only dangling ones are
# removed, so the links that are already right are left untouched and
# sphinx-autobuild does not rebuild their pages on every run.
define update-links
	@mkdir -p $(MAKEDIR)/db_dev_process/$(1)
	@cd $(MAKEDIR)/db_dev_process/$(1) && \
		for l in *.md; do \
			if [ -L $$l ] && [ ! -e $$l ]; then \
				echo "Removing stale $$l"; \
				rm -f $$l; \
			fi; \
		done; \
		for i in ../../../$(1)/*; do \
			n=$$(basename $$i | sed -e's/^[0-9][0-9][0-9]-//'); \
			if [ ! -d $$i ]; then \
				continue; \
			fi; \
			if [ ! -e $$i/README.md ]; then \
				echo "Missing $$i/README.md"; \
			elif [ ! -e $${n}.md ]; then \
				echo "Linking $$i/README.md"; \
				ln -s $$i/README.md $${n}.md; \
			fi; \
		done
endef

fuzzers-links:
	$(call update-links,fuzzers)

minitests-links:
	$(call update-links,minitests)

links: fuzzers-links minitests-links
	@true

.PHONY: fuzzers-links minitests-links links

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
