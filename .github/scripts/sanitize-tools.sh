#!/usr/bin/env bash
#
# Copyright (C) 2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

# Run the C++ tools, built with -fsanitize=address,undefined, on the tool
# test data: bitread/bits2rbt, xc7frames2bit and xc7patch round trips that
# must give back the same bits, bittool, frame_address_decoder, truncated
# bitstreams and malformed frames files.
#
# Fails if any run produces an AddressSanitizer, LeakSanitizer or
# UndefinedBehaviorSanitizer report, if a tool fails or produces no bits on
# the valid test data, or if a round trip changes the bits. Damaged inputs
# may make a tool exit with an error; that is expected.
#
# Usage: sanitize-tools.sh <sanitizer build dir>

set -u
BUILD=$(realpath "$1")
TOOLS=$BUILD/tools
REPO=$(realpath "$(dirname "$0")/../..")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

export ASAN_OPTIONS=detect_leaks=1:halt_on_error=1
export UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1

tar -xzf "$REPO/lib/test_data/ToolsTestData.tar.gz" -C "$WORK"
DATA=$WORK/Series7
PART=$DATA/part.yaml

failures=0
runs=0

fail() {
	failures=$((failures + 1))
	echo "::error::$1"
}

# Run a command, logging its output. Fails on a sanitizer report.
# Sets rc to the command's exit status.
run() {
	local label=$1
	shift
	runs=$((runs + 1))
	log=$WORK/run-$runs.log
	# The subshell keeps the shell's "Aborted" notice for a tool that
	# dies on a damaged input out of the job log.
	("$@" > "$log" 2>&1) 2> /dev/null
	rc=$?
	if grep -qE "ERROR: (Address|Leak)Sanitizer|runtime error:" "$log"; then
		fail "sanitizer report from $label"
		cat "$log"
		return 1
	fi
	return 0
}

# A run on valid input: the command must also succeed.
expect_ok() {
	local label=$1
	run "$@" || return
	if [ "$rc" -ne 0 ]; then
		fail "$label exited with status $rc"
		cat "$log"
	else
		echo "ok: $label"
	fi
}

# A run on damaged input: an error exit is fine, a sanitizer report is not.
expect_handled() {
	local label=$1
	run "$@" && echo "ok: $label (exit status $rc)"
}

# A bitread -y output must contain set bits.
expect_bits() {
	if ! grep -q '^bit_' "$1" 2> /dev/null; then
		fail "$2 produced no bits"
		return 1
	fi
}

# The set bits in a bitread -y output, sorted.
bits() {
	grep '^bit_' "$1" | sort
}

same_bits() {
	expect_bits "$1" "the original bitread" || return
	expect_bits "$2" "$3" || return
	if ! diff <(bits "$1") <(bits "$2") > /dev/null; then
		fail "$3 changed the bits"
	else
		echo "ok: $3 gives the same bits"
	fi
}

for name in design bram; do
	BIT=$DATA/$name.bit
	OUT=$WORK/$name
	expect_ok "bitread $name.bit" "$TOOLS/bitread" -part_file "$PART" \
		-architecture Series7 -y -o "$OUT.bits" -aux "$OUT.aux" "$BIT"
	expect_ok "bits2rbt $name.bit" "$TOOLS/bits2rbt/bits2rbt" -arch Series7 \
		-aux "$OUT.aux" -o "$OUT.rbt" "$OUT.bits"

	if ! python3 "$REPO/.github/scripts/bits2frm.py" "$OUT.bits" 101 \
		"$OUT.frm" || [ ! -s "$OUT.frm" ]; then
		fail "bits2frm.py produced no frames for $name"
		continue
	fi

	expect_ok "xc7frames2bit $name" "$TOOLS/xc7frames2bit" --part_file="$PART" \
		--part_name=test --frm_file="$OUT.frm" --output_file="$OUT.rt.bit"
	expect_ok "bitread $name round trip" "$TOOLS/bitread" -part_file "$PART" \
		-architecture Series7 -y -o "$OUT.rt.bits" "$OUT.rt.bit"
	same_bits "$OUT.bits" "$OUT.rt.bits" "xc7frames2bit on $name"

	expect_ok "xc7patch $name" "$TOOLS/xc7patch" --part_file="$PART" \
		--part_name=test --bitstream_file="$BIT" --frm_file="$OUT.frm" \
		--output_file="$OUT.p.bit"
	expect_ok "bitread $name patched" "$TOOLS/bitread" -part_file "$PART" \
		-architecture Series7 -y -o "$OUT.p.bits" "$OUT.p.bit"
	same_bits "$OUT.bits" "$OUT.p.bits" "xc7patch on $name"

	for cmd in list_config_packets get_device_id; do
		expect_ok "bittool $cmd $name.bit" "$TOOLS/bittool" "$cmd" "$BIT" \
			Series7
	done

	cut -d' ' -f1 "$OUT.frm" > "$OUT.addrs"
	expect_ok "frame_address_decoder $name" "$TOOLS/frame_address_decoder" \
		"$OUT.addrs"
done

# dump_debugbitstream_frame_addresses needs a debug bitstream.
expect_ok "bittool dump_debugbitstream_frame_addresses" "$TOOLS/bittool" \
	dump_debugbitstream_frame_addresses \
	"$REPO/lib/test_data/configuration_test.debug.bit" Series7

# Truncated bitstreams, cut before, inside and at the end of the
# configuration data, at and off word boundaries.
BIT=$DATA/design.bit
SIZE=$(stat -c %s "$BIT")
for cut in 0 3 16 100 1000 1001 $((SIZE / 2)) $((SIZE - 7)) $((SIZE - 1)); do
	head -c "$cut" "$BIT" > "$WORK/cut.bit"
	expect_handled "bitread on the first $cut bytes" "$TOOLS/bitread" -part_file "$PART" \
		-architecture Series7 -y -o "$WORK/cut.bits" "$WORK/cut.bit"
	expect_handled "bittool on the first $cut bytes" "$TOOLS/bittool" \
		list_config_packets "$WORK/cut.bit" Series7
done

# Malformed frames files.
FRAME=$(head -1 "$WORK/design.frm")
WORDS=${FRAME#* }
printf '%s\n' "${FRAME%,*}" > "$WORK/bad-100-words.frm"
printf '%s,0x0\n' "$FRAME" > "$WORK/bad-102-words.frm"
printf '%s zz,%s\n' "${FRAME%% *}" "${WORDS#*,}" > "$WORK/bad-word.frm"
printf 'zz %s\n' "$WORDS" > "$WORK/bad-address.frm"
printf '0x00000000\n' > "$WORK/bad-address-only.frm"
printf '\n' > "$WORK/bad-empty-line.frm"
printf '%s' "$FRAME" > "$WORK/bad-no-newline.frm"
printf '0xffffffff %s\n' "$WORDS" > "$WORK/bad-not-in-part.frm"
for frm in "$WORK"/bad-*.frm; do
	expect_handled "xc7frames2bit on $(basename "$frm")" "$TOOLS/xc7frames2bit" \
		--part_file="$PART" --part_name=test --frm_file="$frm" \
		--output_file="$WORK/bad.bit"
done

echo "$runs runs, $failures failures"
[ "$failures" -eq 0 ]
