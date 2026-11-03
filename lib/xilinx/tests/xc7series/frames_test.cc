/*
 * Copyright (C) 2017-2020  The Project X-Ray Authors.
 *
 * Use of this source code is governed by a ISC-style
 * license that can be found in the LICENSE file or at
 * https://opensource.org/licenses/ISC
 *
 * SPDX-License-Identifier: ISC
 */
#include <fstream>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include <prjxray/xilinx/architectures.h>
#include <prjxray/xilinx/frames.h>
#include <prjxray/xilinx/xc7series/part.h>

using namespace prjxray::xilinx;

TEST(FramesTest, FillInMissingFrames) {
	std::vector<xc7series::FrameAddress> test_part_addresses = {
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 0),
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 1),
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 2),
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 3),
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 4)};

	xc7series::Part test_part(0x1234, test_part_addresses);

	Frames<Series7> frames;
	frames.getFrames().emplace(std::make_pair(
	    xc7series::FrameAddress(2), std::vector<uint32_t>(101, 0xCC)));
	frames.getFrames().emplace(std::make_pair(
	    xc7series::FrameAddress(3), std::vector<uint32_t>(101, 0xDD)));
	frames.getFrames().emplace(std::make_pair(
	    xc7series::FrameAddress(4), std::vector<uint32_t>(101, 0xEE)));

	ASSERT_EQ(frames.getFrames().size(), 3);
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[2]),
	          std::vector<uint32_t>(101, 0xCC));
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[3]),
	          std::vector<uint32_t>(101, 0xDD));
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[4]),
	          std::vector<uint32_t>(101, 0xEE));

	frames.addMissingFrames(test_part);

	ASSERT_EQ(frames.getFrames().size(), 5);
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[0]),
	          std::vector<uint32_t>(101, 0));
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[1]),
	          std::vector<uint32_t>(101, 0));
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[2]),
	          std::vector<uint32_t>(101, 0xCC));
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[3]),
	          std::vector<uint32_t>(101, 0xDD));
	EXPECT_EQ(frames.getFrames().at(test_part_addresses[4]),
	          std::vector<uint32_t>(101, 0xEE));
}

TEST(FramesTest, FindFramesNotInPart) {
	std::vector<xc7series::FrameAddress> test_part_addresses = {
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 0),
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 1),
	    xc7series::FrameAddress(xc7series::BlockType::CLB_IO_CLK, false, 0,
	                            0, 2)};

	xc7series::Part test_part(0x1234, test_part_addresses);

	// Minor 3 is past the end of column 0, and the part has no row 1.
	xc7series::FrameAddress past_column_end(
	    xc7series::BlockType::CLB_IO_CLK, false, 0, 0, 3);
	xc7series::FrameAddress missing_row(xc7series::BlockType::CLB_IO_CLK,
	                                    false, 1, 0, 0);

	Frames<Series7> frames;
	frames.getFrames().emplace(std::make_pair(
	    test_part_addresses[1], std::vector<uint32_t>(101, 0xCC)));
	frames.getFrames().emplace(
	    std::make_pair(past_column_end, std::vector<uint32_t>(101, 0xDD)));
	frames.getFrames().emplace(
	    std::make_pair(missing_row, std::vector<uint32_t>(101, 0xEE)));

	auto not_in_part = frames.findFramesNotInPart(test_part);

	ASSERT_EQ(not_in_part.size(), 2);
	EXPECT_EQ(static_cast<uint32_t>(not_in_part[0]),
	          static_cast<uint32_t>(past_column_end));
	EXPECT_EQ(static_cast<uint32_t>(not_in_part[1]),
	          static_cast<uint32_t>(missing_row));

	// Frames that are all in the part give an empty list.
	frames.getFrames().erase(past_column_end);
	frames.getFrames().erase(missing_row);
	EXPECT_TRUE(frames.findFramesNotInPart(test_part).empty());
}

namespace {
std::string WriteFramesFile(const std::string& name, const std::string& text) {
	std::string path = testing::TempDir() + name;
	std::ofstream(path) << text;
	return path;
}
}  // namespace

TEST(FramesTest, ReadFramesRefusesEmptyFile) {
	Frames<Series7> frames;
	EXPECT_NE(frames.readFrames(WriteFramesFile("empty.frm", "")), 0);
}

TEST(FramesTest, ReadFramesRefusesShortFrame) {
	// The last line of a file cut short.
	Frames<Series7> frames;
	EXPECT_NE(frames.readFrames(WriteFramesFile(
	              "short.frm", "0x00000000 0x00000001,0x00000002\n")),
	          0);
}

TEST(FramesTest, ReadFramesAcceptsNoFrames) {
	Frames<Series7> frames;
	EXPECT_EQ(
	    frames.readFrames(WriteFramesFile("none.frm", "# no frames\n")), 0);
	EXPECT_TRUE(frames.getFrames().empty());
}

TEST(FramesTest, ReadFramesReadsFrame) {
	std::string line = "0x00000002 0x00000001";
	for (int i = 1; i < 101; i++) {
		line += ",0x00000000";
	}
	Frames<Series7> frames;
	EXPECT_EQ(frames.readFrames(WriteFramesFile("one.frm", line + "\n")),
	          0);
	EXPECT_EQ(frames.getFrames().size(), 1);
}
