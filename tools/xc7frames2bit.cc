/*
 * Copyright (C) 2017-2020  The Project X-Ray Authors.
 *
 * Use of this source code is governed by a ISC-style
 * license that can be found in the LICENSE file or at
 * https://opensource.org/licenses/ISC
 *
 * SPDX-License-Identifier: ISC
 */
#include <iomanip>
#include <iostream>
#include <set>
#include <type_traits>

#include <gflags/gflags.h>
#include <prjxray/xilinx/architectures.h>
#include <prjxray/xilinx/bitstream_writer.h>
#include <prjxray/xilinx/configuration.h>

DEFINE_string(part_name, "", "Name of the 7-series part");
DEFINE_string(part_file, "", "Definition file for target 7-series part");
DEFINE_string(
    frm_file,
    "",
    "File containing a list of frame deltas to be applied to the base "
    "bitstream.  Each line in the file is of the form: "
    "<frame_address> <word1>,...,<word101>.");
DEFINE_string(output_file, "", "Write bitstream to file");
DEFINE_string(architecture,
              "Series7",
              "Architecture of the provided bitstream");
DEFINE_int32(spi_buswidth,
             0,
             "SPI flash bus width the device switches to after reading the "
             "start of the bitstream: 1, 2 or 4, like Vivado's "
             "BITSTREAM.CONFIG.SPI_BUSWIDTH. 0 (the default) adds no "
             "packets for it, as Vivado does when the property is not "
             "set. Series7 only.");
DEFINE_bool(spi_32bit_addr,
            false,
            "Read the SPI flash with 32-bit addresses, like Vivado's "
            "BITSTREAM.CONFIG.SPI_32BIT_ADDR. Without --spi_buswidth "
            "the bus width is 1, as in Vivado. Series7 only.");
DEFINE_int32(configrate,
             0,
             "Master configuration clock rate in MHz, like Vivado's "
             "BITSTREAM.CONFIG.CONFIGRATE: 3, 6, 9, 12, 16, 22, 26, 33, "
             "40, 50 or 66. 0 (the default) keeps the device default, "
             "3 MHz. Series7 only.");

namespace xilinx = prjxray::xilinx;

struct Frames2BitWriter {
	template <typename T>
	int operator()(T& arg) {
		using ArchType = std::decay_t<decltype(arg)>;
		constexpr bool is_series7 =
		    std::is_same<ArchType, xilinx::Series7>::value;
		if (!is_series7 && (FLAGS_spi_buswidth ||
		                    FLAGS_spi_32bit_addr || FLAGS_configrate)) {
			std::cerr
			    << "--spi_buswidth, --spi_32bit_addr and "
			       "--configrate are only supported for Series7"
			    << std::endl;
			return 1;
		}
		if (FLAGS_spi_buswidth != 0 && FLAGS_spi_buswidth != 1 &&
		    FLAGS_spi_buswidth != 2 && FLAGS_spi_buswidth != 4) {
			std::cerr << "--spi_buswidth must be 1, 2 or 4"
			          << std::endl;
			return 1;
		}
		const std::set<int> config_rates{0,  3,  6,  9,  12, 16,
		                                 22, 26, 33, 40, 50, 66};
		if (!config_rates.count(FLAGS_configrate)) {
			std::cerr << "--configrate must be one of 3, 6, 9, 12, "
			             "16, 22, 26, 33, 40, 50 or 66"
			          << std::endl;
			return 1;
		}

		auto part = ArchType::Part::FromFile(FLAGS_part_file);
		if (!part) {
			std::cerr << "Part file " << FLAGS_part_file
			          << " not found or invalid" << std::endl;
			return 1;
		}

		// Read the frames from the input file
		xilinx::Frames<ArchType> frames;
		if (frames.readFrames(FLAGS_frm_file)) {
			std::cerr << "Frames file " << FLAGS_frm_file
			          << " not found or invalid" << std::endl;
			return 1;
		}

		if (std::is_same<ArchType, xilinx::Series7>::value ||
		    std::is_same<ArchType, xilinx::UltraScale>::value ||
		    std::is_same<ArchType, xilinx::UltraScalePlus>::value) {
			// A frame address the part does not have would still be
			// written, and every frame after it would land late.
			// This happens when the frames file was made for a
			// different part than --part_file describes.
			auto not_in_part = frames.findFramesNotInPart(part);
			for (auto& address : not_in_part) {
				std::cerr << "Frame address 0x" << std::hex
				          << std::setw(8) << std::setfill('0')
				          << static_cast<uint32_t>(address)
				          << std::dec << " is not in part file "
				          << FLAGS_part_file << std::endl;
			}
			const bool frames_fit_part = not_in_part.empty();
			if (!frames_fit_part) {
				std::cerr
				    << not_in_part.size()
				    << " frame address(es) in "
				    << FLAGS_frm_file
				    << " are not in the part; is "
				    << FLAGS_part_file
				    << " the part the frames were made for?"
				    << std::endl;
				return 1;
			}

			// In case the frames input file is missing some frames
			// that are in the tilegrid
			frames.addMissingFrames(part);
		}

		// Create data for the type 2 configuration packet with
		// information about all frames
		typename xilinx::Configuration<ArchType>::PacketData
		    configuration_packet_data(
		        xilinx::Configuration<ArchType>::
		            createType2ConfigurationPacketData(
		                frames.getFrames(), part));

		// Put together a configuration package
		typename ArchType::ConfigurationPackage configuration_package;
		xilinx::Configuration<ArchType>::createConfigurationPackage(
		    configuration_package, configuration_packet_data, part);
		if constexpr (is_series7) {
			// Vivado sets the bus width to 1 when only
			// SPI_32BIT_ADDR is given.
			if (FLAGS_spi_buswidth || FLAGS_spi_32bit_addr) {
				xilinx::Configuration<ArchType>::
				    addSpiReadOptions(configuration_package,
				                      FLAGS_spi_buswidth
				                          ? FLAGS_spi_buswidth
				                          : 1,
				                      FLAGS_spi_32bit_addr);
			}
			if (FLAGS_configrate) {
				xilinx::Configuration<ArchType>::setConfigRate(
				    configuration_package, FLAGS_configrate);
			}
		}
		// Vivado pads a bitstream for 32-bit SPI addresses with
		// 256 more 0xFF bytes before the bus width detection
		// pattern.
		const size_t extra_padding_words =
		    FLAGS_spi_32bit_addr ? 256 / sizeof(uint32_t) : 0;

		// Write bitstream
		auto bitstream_writer =
		    xilinx::BitstreamWriter<ArchType>(configuration_package);
		if (bitstream_writer.writeBitstream(
		        configuration_package, FLAGS_part_name, FLAGS_frm_file,
		        "xc7frames2bit", FLAGS_output_file,
		        extra_padding_words)) {
			std::cerr << "Failed to write bitstream" << std::endl
			          << "Exitting" << std::endl;
			return 1;
		}
		return 0;
	}
};

int main(int argc, char* argv[]) {
	gflags::SetUsageMessage(argv[0]);
	gflags::ParseCommandLineFlags(&argc, &argv, true);
	xilinx::Architecture::Container arch_container =
	    xilinx::ArchitectureFactory::create_architecture(
	        FLAGS_architecture);
	return std::visit(Frames2BitWriter(), arch_container);
}
