# Copyright (C) 2017-2026  The Project X-Ray Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
export XRAY_DATABASE="zynq7"
# CLG485 is the only package of the xc7z015, so it is the fully bonded one.
export XRAY_PART="xc7z015clg485-2"
export XRAY_ROI_FRAMES="0x00000000:0xffffffff"

# All CLB's in part, all BRAM's in part, all DSP's in part.
# Bounding boxes from Vivado get_sites (11550 SLICE, 190 RAMB18, 95 RAMB36,
# 160 DSP48).
export XRAY_ROI_TILEGRID="SLICE_X0Y0:SLICE_X105Y149 RAMB18_X0Y0:RAMB18_X4Y59 RAMB36_X0Y0:RAMB36_X4Y29 DSP48_X0Y0:DSP48_X3Y59"

export XRAY_EXCLUDE_ROI_TILEGRID=""

# Only the left side has an IOI3 tile on row 9: the bottom right of the die
# is the GTP quad (bank 112) instead of an HR bank.
export XRAY_IOI3_TILES="LIOI3_X0Y9"
# The PS sits in the same place as on the xc7z020: the INT_L column next to
# INT_INTERFACE_PSS_L is X18, rows Y50-Y149, so use the same tile.
export XRAY_PS7_INT="INT_L_X18Y100"

# These settings must remain in sync
# Bottom-left clock region (X0Y0), as for the xc7z020; the column layout
# differs from the xc7z020, so only BRAM/DSP columns 0-1 fall inside it.
export XRAY_ROI="SLICE_X0Y0:SLICE_X49Y49 RAMB18_X0Y0:RAMB18_X1Y19 RAMB36_X0Y0:RAMB36_X1Y9 IOB_X0Y0:IOB_X0Y49 DSP48_X0Y0:DSP48_X1Y19"

# GRID_POINT_X/Y of the ROI above (SLICE_X49Y49 is in CLBLL_L_X30Y49, grid
# column 76).
export XRAY_ROI_GRID_X1="0"
export XRAY_ROI_GRID_X2="79"
# Include VBRK / VTERM
export XRAY_ROI_GRID_Y1="105"
export XRAY_ROI_GRID_Y2="155"

source $(dirname ${BASH_SOURCE[0]})/../utils/environment.sh

env=$(python3 ${XRAY_UTILS_DIR}/create_environment.py)
ENV_RET=$?
if [[ $ENV_RET != 0 ]] ; then
	return $ENV_RET
fi
eval $env
