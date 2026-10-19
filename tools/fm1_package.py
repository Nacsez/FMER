#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments
"""FMER build-only package format code, derived from pinned SLOOP/Felucca.

  flash.bin  head [0, 0x4000): flash header (JieLi SDK default values), JLFS
             entries, the SDK SPL (uboot.boot, Apache-2.0) and an isd_config
             blob that decodes to the chip key. The update loader never writes
             the head.
             app area 0x4000..: app_area_head, app.bin, the SDK cfg_tool.bin and
             eq_cfg_hw.bin, the region descriptors; SFC-encrypted with the chip key
  ota.bin    the Felucca update loader (firmware/loader)

The SDK files come from the JieLi AC79 SDK (AC79_SDK, or --sdk).
All integrity checks in the format are CRC16 (poly 0x1021, init 0).

  fm1pkg_make.py APP.bin OTA.bin OUT.fwsc [--product FM-1_9XY] [--sdk DIR]
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import struct
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SDK = ROOT / "third_party/acquired/fm1-sdk-assets/official"
STOCK_APP_PATH = ROOT / "third_party/acquired/stock-v15-reference/stock-v15-app-encrypted.bin"
STOCK_APP_SHA256 = "6edf3c37fb5bbbc33607c89375ee024d5477c17914d72221c8c68e58a8255686"
PUBLISHED_TEMPLATE = "published-v15"
TEST01_TEMPLATE = "test01-v15-20261005"
TEST01_BACKUP = ROOT / "private/rom-backups/20261005T224904.338856Z-73a54834"
TEST01_DUMP_SHA256 = "acb1e08e1c8360bcb0f1719b5940f57c473462c5ee1e8a7a4404c611a7ba9c88"
TEST01_REPORT_SHA256 = "546e218c111ef0772cdc8f464061a619e35f6201cf623ffe492edcb22f1dc7c3"
TEST01_APP_SHA256 = "8c1d13a5934eb3c70a5fec644577618a31b2a96c8748a7b692c506a86505dbb1"
TEST01_APP_SLOT = 0x8DD1C
CITRINE_TEMPLATE = "citrine-v15-20261015"
CITRINE_BACKUP = ROOT / "private/Citrine/rom-backups/20261015T132221.635992Z-3a08230b"
CITRINE_DUMP_SHA256 = "4c4cd71657c9f5665adb4561ae22aa47f219d46cf28a836eb07fcf191f4bd3a7"
CITRINE_REPORT_SHA256 = "9c93f91d6f890b3a87cd571bfac9823b73885911b8fc62373bbc7c6770565a37"
CITRINE_APP_SHA256 = TEST01_APP_SHA256
PRODUCT = "FM-1_701"
NEXT_PRODUCT = "FM-1_702"
CURRENT_PRODUCT = "FM-1_703"
BUILD_PRODUCT = "FM-1_704"
LATEST_PRODUCT = "FM-1_705"
DEVELOPMENT_PRODUCT = "FM-1_706"
CANDIDATE_PRODUCT = "FM-1_707"
INSTRUMENT_PRODUCT = "FM-1_708"
BANK_PRODUCT = "FM-1_709"
MIDI_PRODUCT = "FM-1_710"
WORKSPACE_PRODUCT = "FM-1_711"
FX_PRODUCT = "FM-1_712"
OPTIMIZED_FX_PRODUCT = "FM-1_713"
FINAL_FX_PRODUCT = "FM-1_714"
SHOWCASE_PRODUCT = "FM-1_715"
TIMBRE_PRODUCT = "FM-1_716"
VISUAL_PRODUCT = "FM-1_717"
REACTIVE_PRODUCT = "FM-1_718"
WORKSTATION_PRODUCT = "FM-1_719"
PROJECT_PRODUCT = "FM-1_720"
PERFORMANCE_PRODUCT = "FM-1_721"
SYNC_PRODUCT = "FM-1_722"
CLEANUP_PRODUCT = "FM-1_723"
PREVIEW_PRODUCT = "FM-1_724"
ROUTING_PRODUCT = "FM-1_728"
SONG_PRODUCT = "FM-1_730"
LINK_PRODUCT = "FM-1_731"
REFINEMENT_PRODUCT = "FM-1_733"
NAVIGATION_PRODUCT = "FM-1_734"
INSTALLED_731_PACKAGE = ROOT / "artifacts/development-731/package-malachite-final/fmer-candidate.fwsc"
INSTALLED_731_PACKAGE_SHA256 = "d60e3f46f5c2b995e36048e8fbc5a4173f7bcbb4f965b527f5f41094c00468b5"
INSTALLED_731_APP_SHA256 = "88ccb14c89a463d3717a637440de78047f046a9ef2f486c1fee31898beabd143"
INSTALLED_731_JOURNAL = ROOT / "artifacts/development-731/flash/Malachite/20261015T174043.163807Z/events.jsonl"
INSTALLED_731_JOURNAL_SHA256 = "4627106984ceb0400a96d51c5fb3950923ba2c9fc9fbfb4fb05aa7c2127fb2dc"
INSTALLED_CITRINE_731_PACKAGE = ROOT / "artifacts/development-731/package-citrine-final/fmer-candidate.fwsc"
INSTALLED_CITRINE_731_PACKAGE_SHA256 = "3a4dd986550fe5d7cd6f8bf625585083a9f1e0fadbdd1dc55a7983b1051e3e72"
INSTALLED_CITRINE_731_APP_SHA256 = "56b8784b7b1482c82a1d0dcf0668540429cf7fed5feb274a19c97912cc76643b"
INSTALLED_CITRINE_731_JOURNAL = ROOT / "artifacts/development-731/flash/Citrine/20261015T173524.778286Z/events.jsonl"
INSTALLED_CITRINE_731_JOURNAL_SHA256 = "c25ecc42355223ad8551295059539614cb3d9a18e9334f8fb40c9263151222e1"
INSTALLED_730_PACKAGE = ROOT / "artifacts/development-730/package-ready/fmer-candidate.fwsc"
INSTALLED_730_PACKAGE_SHA256 = "d001df15ddb0947a4d7bc9c364426fcef9e1424caf7817b9b3d652070e28ca39"
INSTALLED_730_APP_SHA256 = "4836062c0c8a62b618a806ba111ccfb3b8fecaf776c66fc8be256ffbb91519fb"
INSTALLED_730_JOURNAL = ROOT / "artifacts/fm1-flash/20261015T061123.862211Z-9b977213/events.jsonl"
INSTALLED_730_JOURNAL_SHA256 = "9de056505c2551d0bcb6ab6a3ef41182aee40b476d441c1598e6c7a3d9f750d4"
INSTALLED_CITRINE_730_PACKAGE = ROOT / "artifacts/citrine-acquisition/package730-stock-record/fmer-candidate.fwsc"
INSTALLED_CITRINE_730_PACKAGE_SHA256 = "c8c758d24cd434cd03044770c401eaa9530768e9f3daec4f9aa065cd46258532"
INSTALLED_CITRINE_730_APP_SHA256 = "1fcbae6a1933f971d3dfdf9c675515da8e5cc7d8f33a0b94975c322150e95a42"
INSTALLED_CITRINE_730_JOURNAL = ROOT / "artifacts/citrine-acquisition/flash/20261015T155904.248873Z-77271d5d/events.jsonl"
INSTALLED_CITRINE_730_JOURNAL_SHA256 = "a355746a2c5521015f87b66f5e362f88f2a7d4867900e56952d755e233074385"
INSTALLED_729_RELEASE2_PACKAGE = ROOT / "artifacts/development-729/package-release2/fmer-candidate.fwsc"
INSTALLED_729_RELEASE2_PACKAGE_SHA256 = "e508837c759d713439a2b67f98a2908aaa7acd1c05cc3144a6c665a959f1ddd5"
INSTALLED_729_RELEASE2_APP_SHA256 = "9d583baa5bdacbc27bee725ec96bf8132629208a1c54fa37f66498d63c48077d"
INSTALLED_729_RELEASE2_JOURNAL = ROOT / "artifacts/fm1-flash/20261015T013713.354955Z-7a26b92f/events.jsonl"
INSTALLED_729_RELEASE2_JOURNAL_SHA256 = "40fc3ed6024efc7a7cbe87602379e7fbe14987135e4bd0e5751835ff3fd317ca"
DEFAULTS_PRODUCT = "FM-1_729"
INSTALLED_729_RELEASE1_PACKAGE = ROOT / "artifacts/development-729/package-final3/fmer-candidate.fwsc"
INSTALLED_729_RELEASE1_PACKAGE_SHA256 = "fc51db994a7026438bac5f83778636aa72e1e324c1372e7d9422a521906b43fe"
INSTALLED_729_RELEASE1_APP_SHA256 = "130801d103cd975a5a485e7643c18e76ddbb25a1db637e49807af0e2f6a4681a"
INSTALLED_729_RELEASE1_JOURNAL = ROOT / "artifacts/fm1-flash/20261015T012607.902103Z-b2bd5e31/events.jsonl"
INSTALLED_729_RELEASE1_JOURNAL_SHA256 = "7f49009ce2c3b1054d6da86b53f7c11810c35e85506dd265300597768d250259"
INSTALLED_728_RELEASE3_PACKAGE = ROOT / "artifacts/development-728/package-release3/fmer-candidate.fwsc"
INSTALLED_728_RELEASE3_PACKAGE_SHA256 = "fc02e0f03e5aa9ffaa0ac91e10811862f5be01309045a7325ac92aebfca91b78"
INSTALLED_728_RELEASE3_APP_SHA256 = "2abcab661b8de0b071915da36692b6198e87e275892e3b0881512e1fc6bde222"
INSTALLED_728_RELEASE3_JOURNAL = ROOT / "artifacts/fm1-flash/20261015T001930.945040Z-f693e8bd/events.jsonl"
INSTALLED_728_RELEASE3_JOURNAL_SHA256 = "828ef7e88990b6a87efa10974749ca231cf7824fdbd08e47510ae0d7f5397fb4"
INSTALLED_728_RELEASE1_PACKAGE = ROOT / "artifacts/development-728/package-final/fmer-candidate.fwsc"
INSTALLED_728_RELEASE1_PACKAGE_SHA256 = "1ceba1bb01e55d42a38662dd2cfa9ef663cf98e075f5e6379c5047cb87fbd49f"
INSTALLED_728_RELEASE1_APP_SHA256 = "4da3045304fc0f2c86ac95b91af0807873689e07c6190783dd39189386291881"
INSTALLED_728_RELEASE1_JOURNAL = ROOT / "artifacts/fm1-flash/20261014T235608.287676Z-cfe5aae6/events.jsonl"
INSTALLED_728_RELEASE1_JOURNAL_SHA256 = "ba0d8d51e54565136a5cc10d5566be0239ec160389375213c2408bae3e307561"
WORKFLOW_PRODUCT = "FM-1_727"
POLISH_PRODUCT = "FM-1_726"
RELEASE_PRODUCT = "FM-1_725"
SUPPORTED_PRODUCTS = (PRODUCT, NEXT_PRODUCT, CURRENT_PRODUCT, BUILD_PRODUCT, LATEST_PRODUCT, DEVELOPMENT_PRODUCT, CANDIDATE_PRODUCT, INSTRUMENT_PRODUCT, BANK_PRODUCT, MIDI_PRODUCT, WORKSPACE_PRODUCT, FX_PRODUCT, OPTIMIZED_FX_PRODUCT, FINAL_FX_PRODUCT, SHOWCASE_PRODUCT, TIMBRE_PRODUCT, VISUAL_PRODUCT, REACTIVE_PRODUCT, WORKSTATION_PRODUCT, PROJECT_PRODUCT, PERFORMANCE_PRODUCT, SYNC_PRODUCT, CLEANUP_PRODUCT, PREVIEW_PRODUCT, RELEASE_PRODUCT, POLISH_PRODUCT, WORKFLOW_PRODUCT, ROUTING_PRODUCT, DEFAULTS_PRODUCT, SONG_PRODUCT, LINK_PRODUCT, REFINEMENT_PRODUCT, NAVIGATION_PRODUCT)
INSTALLED_727_PACKAGE = ROOT / "artifacts/development-727/package-final/fmer-candidate.fwsc"
INSTALLED_727_PACKAGE_SHA256 = "e803ce691ab9a39b4aa4b3f8ac1cca3af53df3f9ccf5451bec2c6c8460f6710a"
INSTALLED_727_APP_SHA256 = "18ed7e1b8c70b5e844213c78e3aaaa61d5271c53fe68e53a1507d5cd658b91dc"
INSTALLED_727_JOURNAL = ROOT / "artifacts/fm1-flash/20261014T222943.841162Z-965daf75/events.jsonl"
INSTALLED_727_JOURNAL_SHA256 = "b754bd8d334d56a8961640c2d349eeac0f20ee1a36ff94549231eb8de29585ec"
INSTALLED_726_PACKAGE = ROOT / "artifacts/development-726/package5/fmer-candidate.fwsc"
INSTALLED_726_PACKAGE_SHA256 = "ef3fe30b4bdfe795a7fb55875b6d9e5a5eda97d80f0276753788634626c19289"
INSTALLED_726_APP_SHA256 = "81d5637fe71551aa849801a6ed951f3965467eeb0a5c2517d556598ef086ca77"
INSTALLED_726_JOURNAL = ROOT / "artifacts/fm1-flash/20261014T020110.915048Z-26974e68/events.jsonl"
INSTALLED_726_JOURNAL_SHA256 = "a52d16263ffcd60ffdf74c19f2ded9359a5f43bf17bbfd7c7a7c0509c77e8b99"
INSTALLED_724_RELEASE3_PACKAGE = ROOT / "artifacts/development-724/package-release3/fmer-candidate.fwsc"
INSTALLED_724_RELEASE3_PACKAGE_SHA256 = "a836f705239ffed971abcad7448b33b24b39458f2dfe12422c295730b5b9c37e"
INSTALLED_724_RELEASE3_APP_SHA256 = "79fa5a62e1b82e80b4dc4cb89a44216d4bbc97e5fa2ba3cfa08cb854e85472c5"
INSTALLED_724_RELEASE3_JOURNAL = ROOT / "artifacts/fm1-flash/20261012T122513.335210Z-362e0afd/events.jsonl"
INSTALLED_724_RELEASE3_JOURNAL_SHA256 = "4d512f67125e8aac36166fe523df3dcebcfb34d5c3bf5e078ca9b87d90f3374e"
INSTALLED_723_RELEASE4_PACKAGE = ROOT / "artifacts/development-723/package-release4/fmer-candidate.fwsc"
INSTALLED_723_RELEASE4_PACKAGE_SHA256 = "2bc16532519134498f2d255d01cf1ed6e9fa26a9cb80e1d2743aa470c04205c0"
INSTALLED_723_RELEASE4_APP_SHA256 = "4aa014a91d7ed22bbc0c78ab2350902c45763a92fc3f06588fa728414a3bd5c5"
INSTALLED_723_RELEASE4_JOURNAL = ROOT / "artifacts/fm1-flash/20261012T061955.384412Z-75f29d0c/events.jsonl"
INSTALLED_723_RELEASE4_JOURNAL_SHA256 = "1be78250336aa8175989813a6a5b151ba487fcd46dfbb4bb59074b5810d56f84"
INSTALLED_722_RELEASE2_PACKAGE = ROOT / "artifacts/development-722/package-release2/fmer-candidate.fwsc"
INSTALLED_722_RELEASE2_PACKAGE_SHA256 = "7dc33dda06d5c6d75acacdb58001f57a91dc93fedea1550a2d5a26ddf9f040a8"
INSTALLED_722_RELEASE2_APP_SHA256 = "35c76af05a26214644864db82c3af32f57c27c0af9db63c9a1ed4191b1f0f257"
INSTALLED_722_RELEASE2_JOURNAL = ROOT / "artifacts/fm1-flash/20261012T014130.384520Z-3c6cf69a/events.jsonl"
INSTALLED_722_RELEASE2_JOURNAL_SHA256 = "a6a5de4d67e173e52da3722a33ee2e973e6a597c79675a02b27444b8815aee67"
INSTALLED_722_RELEASE1_PACKAGE = ROOT / "artifacts/development-722/package-release1/fmer-candidate.fwsc"
INSTALLED_722_RELEASE1_PACKAGE_SHA256 = "0ef9f457d7513bc9252070ab3b375c5e883c79b57efd666dd2cbbf60e2fd09fb"
INSTALLED_722_RELEASE1_APP_SHA256 = "2d6a0d916b008bcb191f30f1a7dac75d28019c328c3d5c77bcd1a0c2c7be8640"
INSTALLED_722_RELEASE1_JOURNAL = ROOT / "artifacts/fm1-flash/20261012T013018.175157Z-4b2ee2f4/events.jsonl"
INSTALLED_722_RELEASE1_JOURNAL_SHA256 = "d6a28fc998aa133345c114383813b6cd070a246047398eb6bc86d8638de66954"
INSTALLED_721_PACKAGE = ROOT / "artifacts/development-721/package-release1/fmer-candidate.fwsc"
INSTALLED_721_PACKAGE_SHA256 = "b331220eab6984d390c9e667eda62302dea0e776325ba80696d6308d91015edb"
INSTALLED_721_APP_SHA256 = "a797339fb5a21a44534f6e9297fbfff124406951fbbcc9226031af70a4719664"
INSTALLED_721_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T215436.525161Z-6a08b7f7/events.jsonl"
INSTALLED_721_JOURNAL_SHA256 = "bf2192351f4bb1dba79342f6e6de2aee5116d8817198c3f279d9b1c47d54a14c"
INSTALLED_720_RELEASE6_PACKAGE = ROOT / "artifacts/development-720/package-release6/fmer-candidate.fwsc"
INSTALLED_720_RELEASE6_PACKAGE_SHA256 = "2afc1f61212f49b9884a5f862d3d8c9ff3ad02cf8a3f86e55fce64aa3a2f2124"
INSTALLED_720_RELEASE6_APP_SHA256 = "00d3c2533c82dd3bd87d5ef170070c2a1bd43b153aaff9b6d5666c5375e33489"
INSTALLED_720_RELEASE6_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T174946.265044Z-c8a798ff/events.jsonl"
INSTALLED_720_RELEASE6_JOURNAL_SHA256 = "f669567f68aa202b59cee339434c1868b93df246023c7c8969b8d221aeb6813e"
INSTALLED_719_INLINE_PACKAGE = ROOT / "artifacts/development-719/package-inline/fmer-candidate.fwsc"
INSTALLED_719_INLINE_PACKAGE_SHA256 = "12e354e13669b99e9ab2210c23d6049f48d7817506fef4445ab2abb6f125b1b1"
INSTALLED_719_INLINE_APP_SHA256 = "66faf3ff51d3c3c240baa7bfd170cc2b551124b13164af8b0e42d1f965b2a631"
INSTALLED_719_INLINE_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T091630.389807Z-9fb7a6f8/events.jsonl"
INSTALLED_719_INLINE_JOURNAL_SHA256 = "d96e5368b6e470c5931384e48d74878cdca3719796b477660b9038d4932eb456"
INSTALLED_720_RELEASE4_PACKAGE = ROOT / "artifacts/development-720/package-release4/fmer-candidate.fwsc"
INSTALLED_720_RELEASE4_PACKAGE_SHA256 = "24151d0f9a5c32417e6019e817935f5b5de8b26116d779057561bb9faaf0fcd1"
INSTALLED_720_RELEASE4_APP_SHA256 = "c00da676063a1e02e70cfdbb7d5a0d2932f1e9d8dcc5cd0a4b78530caa358e85"
INSTALLED_720_RELEASE4_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T170752.687223Z-39d2c411/events.jsonl"
INSTALLED_720_RELEASE4_JOURNAL_SHA256 = "bfe086ed630f40568b293a155b2368821301f731ec5e146960431febca9f809d"
INSTALLED_720_RELEASE5_PACKAGE = ROOT / "artifacts/development-720/package-release5/fmer-candidate.fwsc"
INSTALLED_720_RELEASE5_PACKAGE_SHA256 = "be8ffbea9fe5cb9e715bca9e7d9406da0e8815fb8a20189668100e4a4a9a4e21"
INSTALLED_720_RELEASE5_APP_SHA256 = "1925b91e4a55e428e8510a50838283373f93b34f7530ebcb6990841151359aa5"
INSTALLED_720_RELEASE5_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T172546.689807Z-3c50185b/events.jsonl"
INSTALLED_720_RELEASE5_JOURNAL_SHA256 = "c8d4e31b3ad428f3539dfa0451adfbf6c2c78e8b2f09d714be390f51e01028e3"
INSTALLED_719_PACKAGE = ROOT / "artifacts/development-719/package-release/fmer-candidate.fwsc"
INSTALLED_719_PACKAGE_SHA256 = "e9b9b7bf6c233752917f161f4c6f7bedcac35dc516124c659d7500dbba299a84"
INSTALLED_719_APP_SHA256 = "b5de5fa67e7df85c99ab72f35558eac1af584ec736c679de1b83e4fde78ce270"
INSTALLED_719_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T072619.315325Z-20eb6e42/events.jsonl"
INSTALLED_719_JOURNAL_SHA256 = "fca1fd2a1789d2f788031cad5e53526f8f59682b55ce16e937bd25b6d5aef1a6"
INSTALLED_719_CORRECTED_PACKAGE = ROOT / "artifacts/development-719/package-corrected/fmer-candidate.fwsc"
INSTALLED_719_CORRECTED_PACKAGE_SHA256 = "5478b24942aa8b3a1febd8d3252f1277155c539c7ac1393da464c78e9b925f2e"
INSTALLED_719_CORRECTED_APP_SHA256 = "a40b0617ea8e80a8ded866fd0a7090f817bc0c37444aa44f20e07b88494d5d29"
INSTALLED_719_CORRECTED_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T074448.837213Z-d5326164/events.jsonl"
INSTALLED_719_CORRECTED_JOURNAL_SHA256 = "49864627a85fa8d9a9859fe38a9cd7c2ec82cc5fcb064529b212d5aea41de9fe"
INSTALLED_719_FINAL_PACKAGE = ROOT / "artifacts/development-719/package-final/fmer-candidate.fwsc"
INSTALLED_719_FINAL_PACKAGE_SHA256 = "9717e6ead972a2d2487dd3af80b1f4a8845005341b5552f3b814c1771a52e50b"
INSTALLED_719_FINAL_APP_SHA256 = "333d874707ef788ce44b3fc218e1217b1961579bd4b1622fe56f835be31c6ef3"
INSTALLED_719_FINAL_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T080504.356113Z-1b414c08/events.jsonl"
INSTALLED_719_FINAL_JOURNAL_SHA256 = "1bbbdc3e025946cd7966a8dd594aa631a20bdf2c77ec9e5098bdbd43100f5492"
INSTALLED_719_OPTIMIZED_PACKAGE = ROOT / "artifacts/development-719/package-optimized/fmer-candidate.fwsc"
INSTALLED_719_OPTIMIZED_PACKAGE_SHA256 = "425eb83f0f67f6eb5dca1b8772f0e21d80fbc8ed8302aba3281d4f88e7071ece"
INSTALLED_719_OPTIMIZED_APP_SHA256 = "467efd7fc0dce81a7410ec790e136800a7ef989f13313792d4378b5a753e6348"
INSTALLED_719_OPTIMIZED_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T083001.100479Z-6726a18c/events.jsonl"
INSTALLED_719_OPTIMIZED_JOURNAL_SHA256 = "f847ceeb03865e267230333e40d3b73462e40d5df3b0d5e925a128dbbe8ce21e"
INSTALLED_719_ARITHMETIC_PACKAGE = ROOT / "artifacts/development-719/package-arithmetic/fmer-candidate.fwsc"
INSTALLED_719_ARITHMETIC_PACKAGE_SHA256 = "c831751ae34d6c7166bcf80efd6c614f48791a1954476913fbc71114ab21a2e8"
INSTALLED_719_ARITHMETIC_APP_SHA256 = "a2fe6e71ed513a81b41f7e52a633434768cfc7c8da9107bec0046e1f896177f1"
INSTALLED_719_ARITHMETIC_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T085038.249692Z-32152b23/events.jsonl"
INSTALLED_719_ARITHMETIC_JOURNAL_SHA256 = "77a7f4a877d9e04d3a45b446d47f2bce1e51b17919e62740c874c70040bb00c0"
INSTALLED_719_PHASER_PACKAGE = ROOT / "artifacts/development-719/package-phaser/fmer-candidate.fwsc"
INSTALLED_719_PHASER_PACKAGE_SHA256 = "133ecd05fb8dfc30005d835054a070bcd0fdd1122b8befab4bc11a5634905544"
INSTALLED_719_PHASER_APP_SHA256 = "ed7ced0f9844d9b0a22b37cb5431e9bd95984a16406bdedcc1b1511edfc7df10"
INSTALLED_719_PHASER_JOURNAL = ROOT / "artifacts/fm1-flash/20261011T090734.245831Z-32c187b6/events.jsonl"
INSTALLED_719_PHASER_JOURNAL_SHA256 = "bdcbf5a6c7ef38f9f0144c993afb67055b9c1e29d50a766a2785a7e63f2b8032"
INSTALLED_718_PACKAGE = ROOT / "artifacts/development-718/package-final/fmer-candidate.fwsc"
INSTALLED_718_PACKAGE_SHA256 = "bf2265e0cc3bd615d405873e0925cd97c95f0bf9b75805e452f10330dbf4f2bc"
INSTALLED_718_APP_SHA256 = "43a3f8c62e87f08bcc9ebfc7355185d523fc53e2c1dc8bb25d33a8693ae1e98e"
INSTALLED_718_JOURNAL = ROOT / "artifacts/fm1-flash/20261010T011920.233099Z-2d17c3dc/events.jsonl"
INSTALLED_718_JOURNAL_SHA256 = "c3503fc0b63043ab2d15d17071979afa3dc91fd037d02c76facbec2702ea0f70"
INSTALLED_717_PACKAGE = ROOT / "artifacts/development-717/package-release/fmer-candidate.fwsc"
INSTALLED_717_PACKAGE_SHA256 = "de7207b42ad2b5c5071943a59542d4f358a3c23dc8363d5e4bce7732e0fd155e"
INSTALLED_717_APP_SHA256 = "70188a7c52bf525ea020b5c6f97f1ba8a8c1658d36395153744ee480f9f98d58"
INSTALLED_717_JOURNAL = ROOT / "artifacts/fm1-flash/20261010T001753.744967Z-06cb1427/events.jsonl"
INSTALLED_717_JOURNAL_SHA256 = "8d5b6401c6079991bd1e380bff8a498a3ae821eb1c2d9c32d2af0382df71dd49"
INSTALLED_716_PACKAGE = ROOT / "artifacts/development-716/package-release/fmer-candidate.fwsc"
INSTALLED_716_PACKAGE_SHA256 = "d986a26c8bffcf2256ede25ca5e0fedbd52d98d8019995b509092e527d8ac948"
INSTALLED_716_APP_SHA256 = "351ded7c97b7b6ed82f0cd77a760218542908c6a4b3cdd5d832375a3c1eee29e"
INSTALLED_716_JOURNAL = ROOT / "artifacts/fm1-flash/20261009T164638.314121Z-8cb8c8ef/events.jsonl"
INSTALLED_716_JOURNAL_SHA256 = "2f51e349899af470c6b305d37d387cf61acd65063d372cd06ac301c14343365a"
INSTALLED_715_PACKAGE = ROOT / "artifacts/development-715/package-release/fmer-candidate.fwsc"
INSTALLED_715_PACKAGE_SHA256 = "006f28b97d9e5be5418033846b49e26568654d9285329aaf6ac2cac4322b8f36"
INSTALLED_715_APP_SHA256 = "e3c50e4cbe43f91a766bd3dbe6af843055c155d8ff04f6726037b88aa9d87bdb"
INSTALLED_715_JOURNAL = ROOT / "artifacts/fm1-flash/20261009T160743.428073Z-646745d0/events.jsonl"
INSTALLED_715_JOURNAL_SHA256 = "96566277ec1d95077a682c1e0d02d8e0b866b13b33a6c42f212cb29a2fd54985"
INSTALLED_714_PACKAGE = ROOT / "artifacts/development-714/package/fmer-candidate.fwsc"
INSTALLED_714_PACKAGE_SHA256 = "bc183cc8bb9f7b5e76a8adbbc81db2bfbcf7d597266a2d990e1cd014fb402652"
INSTALLED_714_APP_SHA256 = "ea6778cc16472e2a505dae207db08bed27653cd9887dd337eadaab12841a8f39"
INSTALLED_714_JOURNAL = ROOT / "artifacts/fm1-flash/20261008T141120.895486Z-75958055/events.jsonl"
INSTALLED_714_JOURNAL_SHA256 = "6d85c86ea274889f988e3b5c039710ce12305015e959e2ac8d8b352154343fff"
INSTALLED_713_PACKAGE = ROOT / "artifacts/development-713/package/fmer-candidate.fwsc"
INSTALLED_713_PACKAGE_SHA256 = "e6581e1b1f40bec0f968b13a0deefa101544b3010800fcba0aa91959830defb0"
INSTALLED_713_APP_SHA256 = "809b1ccca9d8e11d5e886e86968cb2383de61ef7cdf4b7428f2daa8d3e733583"
INSTALLED_713_JOURNAL = ROOT / "artifacts/fm1-flash/20261008T135511.733718Z-a75b18ac/events.jsonl"
INSTALLED_713_JOURNAL_SHA256 = "3292fddeadad5a7690aa5e228bcd11dac20d377862dab928e25a0800eb80ab9e"
INSTALLED_712_PACKAGE = ROOT / "artifacts/development-712/package/fmer-candidate.fwsc"
INSTALLED_712_PACKAGE_SHA256 = "acd127368e9461d79997e65170d9b0c8ba311c09039ab4edd086855e90990584"
INSTALLED_712_APP_SHA256 = "4fe5cf277852fa6294e83d233a40a00204b7ed09dec912e276ce1c5b07bd6f91"
INSTALLED_712_JOURNAL = ROOT / "artifacts/fm1-flash/20261008T134512.739199Z-b6f1c4be/events.jsonl"
INSTALLED_712_JOURNAL_SHA256 = "988d81fbeb6f359f2611312c643353afe5c94cdf85016b98ad89acc8f8c0ae15"
INSTALLED_711_PACKAGE = ROOT / "artifacts/development-711/package/fmer-candidate.fwsc"
INSTALLED_711_PACKAGE_SHA256 = "187d3e8214b2be421f9ade3d7027ed5c6dfb4907a51120debfa03d50118b986e"
INSTALLED_711_APP_SHA256 = "10b8d3a763217796fd368937ef8b5844fc360a2ec77e48840bb3e9c5cebd570d"
INSTALLED_711_JOURNAL = ROOT / "artifacts/fm1-flash/20261008T123144.159018Z-2655b73a/events.jsonl"
INSTALLED_711_JOURNAL_SHA256 = "bdcc3b3873e639cf81b7438505f23bda0c3cffc996f5db105d6b52b5e1a5457d"
INSTALLED_710_PACKAGE = ROOT / "artifacts/development-710/package/fmer-candidate.fwsc"
INSTALLED_710_PACKAGE_SHA256 = "7f76dca527182b74acc98a267d9e20a482c2dc0d198432939451a41910e5a1bb"
INSTALLED_710_APP_SHA256 = "0dd7dc6b71dbc8e7e9372f27ebf43ea23fa5cfd5766b7366df6d6c9824bf2470"
INSTALLED_710_JOURNAL = ROOT / "artifacts/fm1-flash/20261008T035649.288299Z-818cec4f/events.jsonl"
INSTALLED_710_JOURNAL_SHA256 = "1f2a96fe0e2e4fed208438a10d3066fca593853bb8de907fb6d4c0e554d54264"
INSTALLED_709_PACKAGE = ROOT / "artifacts/fm1-package/709-20261008-final/fmer-candidate.fwsc"
INSTALLED_709_PACKAGE_SHA256 = "f64592b755531b95d512c35ba440702896fda5e6c32f7c2a903b84c785dc7445"
INSTALLED_709_APP_SHA256 = "94cd6feb437da5c11926c389982b29aed748fec57b685a5312b0f5ce264f9c10"
INSTALLED_709_JOURNAL = ROOT / "artifacts/fm1-flash/20261008T014155.636033Z-4b16605e/events.jsonl"
INSTALLED_709_JOURNAL_SHA256 = "387584c680d9041648576729d4f32ad72cbd84cc27980be178521e5881a47238"
INSTALLED_708_PACKAGE = ROOT / "artifacts/fm1-package/708-20261007/fmer-candidate.fwsc"
INSTALLED_708_PACKAGE_SHA256 = "6a8a6d3d8447a6a144597140e730a30eefd0be7f0c2a581731d785d691ffcbc1"
INSTALLED_708_APP_SHA256 = "15dd5faf324bea122663c6beb917ae6cf4cafceea3b59bbe8a8994127d9cea9b"
INSTALLED_708_JOURNAL = ROOT / "artifacts/fm1-flash/20261007T123245.251665Z-e033e6a5/events.jsonl"
INSTALLED_708_JOURNAL_SHA256 = "0a1c4dbd722ec54bd27792bef15895da0180b0d3f192a2e64f526fb3cbaaf384"
INSTALLED_701_PACKAGE = ROOT / "artifacts/fm1-package/20261005T225643.297157Z-8c8abeb1/fmer-candidate.fwsc"
INSTALLED_701_PACKAGE_SHA256 = "bd6b8a2711585759356cff9f0a7ffa8ad3c760ca0c32af27048852ec58a645ab"
INSTALLED_701_APP_SHA256 = "58e24ef3adffc89ea829b042c91b7f45c12d1bc3075501a72a5322ad2541b224"
INSTALLED_701_JOURNAL = ROOT / "artifacts/fm1-flash/20261005T230158.230296Z-8e6ee604/events.jsonl"
INSTALLED_701_JOURNAL_SHA256 = "2a219fc3f7f25740a76401c91f8e07332ba1e16e690bf0f352488103339f3e8d"
INSTALLED_702_PACKAGE = ROOT / "artifacts/fm1-package/20261006T120519.818059Z-e1cd95e2/fmer-candidate.fwsc"
INSTALLED_702_PACKAGE_SHA256 = "bc4446f4c7c15426e0637000a904eecdf96c1eaf5531cfd0a6f0f1274b9c9f71"
INSTALLED_702_APP_SHA256 = "eb282075f719e35d873ea681b539061aefc69b2a5c7127c76eb6af3c1f3dec18"
INSTALLED_702_JOURNAL = ROOT / "artifacts/fm1-flash/20261006T120905.375815Z-6bcdfc88/events.jsonl"
INSTALLED_702_JOURNAL_SHA256 = "0bc36ece5182550b5d284e5234d72c32484f1bd84d1ab02a5d833476b2bff3cf"
INSTALLED_703_PACKAGE = ROOT / "artifacts/fm1-package/20261006T130736.693694Z-43c5ad15/fmer-candidate.fwsc"
INSTALLED_703_PACKAGE_SHA256 = "df125502636703711219c780d5e2385dee65b081332861c627eea580d4318284"
INSTALLED_703_APP_SHA256 = "2f39373014d2ebda6e9ec39378b8f5cb95645149e1a4ccd65c29f8b80bdd6df9"
INSTALLED_703_JOURNAL = ROOT / "artifacts/fm1-flash/20261006T131228.274806Z-483a8173/events.jsonl"
INSTALLED_703_JOURNAL_SHA256 = "ef2490c64c0cfe498bdcaa29b601ff079be28583a06871467655f6f2f7e85d0c"
INSTALLED_704_PACKAGE = ROOT / "artifacts/fm1-package/20261006T142741.491088Z-650f0bcb/fmer-candidate.fwsc"
INSTALLED_704_PACKAGE_SHA256 = "60dea90e94377af318e452f08282812df4305baeaa2ab5b98a060e9fc4e61f37"
INSTALLED_704_APP_SHA256 = "42d72be4193fcf463c6f14f093ffb6742f3b144603d27ed77e10cabdfadb301a"
INSTALLED_704_JOURNAL = ROOT / "artifacts/fm1-flash/20261006T143659.670098Z-cf92f425/events.jsonl"
INSTALLED_704_JOURNAL_SHA256 = "2f85d5572504d1d26d0702df86fd4cdb5c6368947b4ccf171da173ca6f04a21b"
INSTALLED_705_PACKAGE = ROOT / "artifacts/fm1-package/20261006T161810.257745Z-c36415f7/fmer-candidate.fwsc"
INSTALLED_705_PACKAGE_SHA256 = "312d045e7d9fe67ce42242e9563eb1d9c42583cde9a906c4535518fc3898840a"
INSTALLED_705_APP_SHA256 = "4ea2802643c0876b530a681d30a1e6e57320cf17eeb14e93281b6628b9e33d5b"
INSTALLED_705_JOURNAL = ROOT / "artifacts/fm1-flash/20261006T162334.491773Z-80341d33/events.jsonl"
INSTALLED_705_JOURNAL_SHA256 = "a09d8b0f183be585c3e6a9b8b4bbe0d5330ce60b0ac371f22e6625e2043684a2"
INSTALLED_706_PACKAGE = ROOT / "artifacts/fm1-package/20261006T173928.902464Z-68913b6c/fmer-candidate.fwsc"
INSTALLED_706_PACKAGE_SHA256 = "bc6e3f238a2caf143b8f296c659a2b0d43090a961c96cd1b65108731cd2546b5"
INSTALLED_706_APP_SHA256 = "6ec300fec0023828cdfb55df57914e547f90d66c0050ffdabe6a7ab84329feea"
INSTALLED_706_JOURNAL = ROOT / "artifacts/fm1-flash/20261006T174657.189904Z-7b7508d8/events.jsonl"
INSTALLED_706_JOURNAL_SHA256 = "c514b429a3d8a741dbef84aef4e81aa2420e0aa81f7911f0dae8592c3736c265"
INSTALLED_707_PACKAGE = ROOT / "artifacts/fm1-package/707-20261006-native-fixed/fmer-candidate.fwsc"
INSTALLED_707_PACKAGE_SHA256 = "31050c6041152f44f0ffda60c26c96c0194ee88de235b21557223157ac4fdfd1"
INSTALLED_707_APP_SHA256 = "47e95182ae17d3bdbee4cdb563c8c5fedfcb0a4fe58d72d56600185de7c5f541"
INSTALLED_707_JOURNAL = ROOT / "artifacts/fm1-flash/20261006T193437.870002Z-02900109/events.jsonl"
INSTALLED_707_JOURNAL_SHA256 = "7d497b3706d14057f1a268717c07fdd99a1d99612343819aff35746d8e82350b"
LOADER_LOAD = 0x01C0A800
LOADER_LIMIT = 0x14000
LOADER_MARKER = b"FELUCCA-LOADER-1"
LOADER_NAME = b"usb_hid_ota.bin\0"
SDK_SHA256 = {
    "uboot.boot": "4e3b4c220dc96641cb5a723f41e68ce41d5261ae9434bb33fbd7f2c59976ded4",
    "cfg_tool.bin": "276579954f076886a6a7694f65dc71c034a63a2c204b76749065c0ac7b010d1b",
    "cfg/eq_cfg_hw.bin": "41167491bffed4651750719c973d2758adeb9021a5670d02d6a53c85ed80ea7d",
}

APP_SLOT = 0x8DFBC
FLASH_SIZE = 0x93000
KEY = 0x980F
# flash header: JieLi SDK defaults (burner_size 544, VID "0.01", flash_size 0xFF000,
# fs_ver 0x10, PID "AC791N_STORY"), plain, without its CRC
FLASH_HDR = bytes.fromhex("20022f104cc900f00f001010a4ff4e5d0b41e0cd781dc856417fb367cf9f")
UFW_CHIP = b"AC791N"
SDK = None


def _crc_table():
    t = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else (c << 1)
        t.append(c & 0xFFFF)
    return t


_T = _crc_table()


def crc16(data, crc=0):
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _T[((crc >> 8) ^ b) & 0xFF]
    return crc


def enc(buf, off, size, key=0xFFFF):
    """JieLi ENC stream cipher (in place)"""
    for i in range(size):
        buf[off + i] ^= key & 0xFF
        key = ((key << 1) ^ (0x1021 if key & 0x8000 else 0)) & 0xFFFF


def sfc(buf, off, size, base, key):
    """SFC cipher: ENC per 32-byte block, key mixed with the block address"""
    for i in range(0, size, 32):
        enc(buf, off + i, min(size - i, 32), key ^ ((off + i - base) >> 2))


def chipkey_decode(d):
    """chip key from the 32-byte isd_config blob"""
    thesum = sum(d[:16]) & 0xFF
    thesum = 0xAA if thesum >= 0xE0 else 0x55 if thesum <= 0x10 else thesum
    return sum(1 << i for i in range(16) if (d[16 + i] ^ d[15 - i]) < thesum)


def entry(dcrc, offset, size, flags, resvd, index, name, fill=0xFF):
    if isinstance(name, bytes):                     # 16 raw bytes: name + the packer's trailing fields
        nm = name
    else:
        nm = name.encode() + b"\0"
        nm = nm + bytes([fill]) * (16 - len(nm))
    body = struct.pack("<HIIBBH16s", dcrc, offset & 0xFFFFFFFF, size & 0xFFFFFFFF, flags, resvd, index, nm)
    return struct.pack("<H", crc16(body)) + body


def key_blob(key):
    """32 bytes that chipkey_decode() turns into `key` (+ CRC16)"""
    d = bytearray([0x10] * 16) + bytearray(16)        # sum 0 -> threshold 0x55
    for i in range(16):
        d[16 + i] = d[15 - i] ^ (0x00 if key >> i & 1 else 0xFF)
    assert chipkey_decode(bytes(d)) == key
    return bytes(d) + struct.pack("<H", crc16(d))


def sdk_file(rel):
    root = Path(SDK or DEFAULT_SDK)
    path = root / "cpu" / "wl82" / "tools" / rel
    try:
        data = path.read_bytes()
    except OSError as e:
        raise ValueError(f"Required SDK input missing: {path}: {e.strerror}") from e
    if hashlib.sha256(data).hexdigest() != SDK_SHA256[rel]:
        raise ValueError(f"SDK SHA-256 mismatch: {rel}")
    return data


def _format_flash_image(app, key):
    spl = sdk_file("uboot.boot")                         # SDK SPL, BANKCB-encoded as in the SDK
    cfg_tool = sdk_file("cfg_tool.bin")
    eq = sdk_file("cfg/eq_cfg_hw.bin")
    isd = key_blob(key) + b"[FMER]\r\n"
    f = bytearray(b"\xFF" * FLASH_SIZE)
    # ---- head
    spl_off = 0xA0
    isd_off = spl_off + len(spl)
    if isd_off + len(isd) > 0x4000:
        raise ValueError("SDK head exceeds protected region")
    f[spl_off:spl_off + len(spl)] = spl
    f[isd_off:isd_off + len(isd)] = isd
    top = (entry(crc16(spl), spl_off, len(spl), 0x00, 0x00, 0, "uboot.boot") +
           entry(crc16(isd), isd_off, len(isd), 0x02, 0x80, 0, "isd_config.ini") +
           entry(0xFFFF, 0x4000, 0xFFFFFFFF, 0x81, 0xFF, 0, "app_dir_head") +
           entry(0xFFFF, 0xFF000, 0x1000, 0x12, 0x01, 0xFFFF, "key_mac"))
    hdr = struct.pack("<H", crc16(FLASH_HDR)) + FLASH_HDR
    head = bytearray(hdr + top)
    for o in range(0, len(head), 32):                   # header and each JLFS entry: ENC 0xFFFF
        enc(head, o, 32)
    f[0:len(head)] = head
    # ---- app area (plain first, then SFC)
    if not 4 <= len(app) <= APP_SLOT or app[:4] != bytes.fromhex("04818000"):
        raise ValueError("App size or entry instruction does not match FM-1 startup")
    app = app + b"\xFF" * (APP_SLOT - len(app))
    blk = 0x120 + APP_SLOT + len(cfg_tool)              # app_area_head block size
    area = bytearray(b"\xFF" * blk)
    area[0x120:0x120 + APP_SLOT] = app
    area[0x120 + APP_SLOT:blk] = cfg_tool
    ents = [entry(crc16(app), 0x120, APP_SLOT, 0x82, 0xFF, 0, "app.bin"),
            entry(crc16(cfg_tool), 0x120 + APP_SLOT, len(cfg_tool), 0x82, 0xFF, 0, "cfg_tool.bin"),
            # region descriptors; the bytes after the names are SDK packer fields (VM size, "CODE", "AUTO")
            entry(0xFFFF, 0x93000, 352256, 0x12, 0x80, 0, bytes.fromhex("564d00ffffffffffffffffff00800000")),
            entry(0xFFFF, 0, FLASH_SIZE, 0x92, 0x82, 0, bytes.fromhex("5052435400ffffffffffffff434f4445")),
            entry(0xFFFF, 0xE9000, 0x1000, 0x92, 0x80, 0, bytes.fromhex("4254494600ffffffffffffff4155544f")),
            entry(0xFFFF, 0xEA000, 0x12000, 0x92, 0x81, 1, "USR")]
    area[32:32 + len(b"".join(ents))] = b"".join(ents)
    area[0:32] = entry(crc16(area[32:blk]), 0x02000120, blk, 0x83, 0xFF, 0, "app_area_head")
    # nested cfg directory right after the block: SDK default EQ table
    eq_e = entry(crc16(eq), 0x40, len(eq), 0x82, 0xFF, 1, "eq_cfg_hw.bin")
    cfg_body = eq_e + eq
    cfg = entry(crc16(cfg_body), 0x20, 0x20 + len(cfg_body), 0x83, 0xFF, 1, "cfg") + cfg_body
    region = bytearray(area + cfg)
    sfc(region, 0, len(region), 0, key)
    if 0x4000 + len(region) > FLASH_SIZE:          # (the update loader writes up to FLASH_SIZE only)
        raise ValueError("App area exceeds protected write boundary")
    f[0x4000:0x4000 + len(region)] = region
    return bytes(f)


def stock_app_reference() -> bytes:
    data = STOCK_APP_PATH.read_bytes()
    if len(data) != 0x8F000 or hashlib.sha256(data).hexdigest() != STOCK_APP_SHA256:
        raise ValueError("Official V15 app/calibration reference SHA-256 mismatch")
    return data


def test01_flash_reference() -> bytes:
    """Admit only the independently reviewed, twice-read Test01 backup.

    The full report and both full flash reads are pinned, not user-selectable
    template inputs. Missing/mutated evidence cannot fall back to another unit.
    This is the original app after loader staging, not a pre-staging VM backup.
    """
    return _unit_flash_reference(TEST01_BACKUP, TEST01_REPORT_SHA256, TEST01_DUMP_SHA256, TEST01_APP_SHA256)


def citrine_flash_reference() -> bytes:
    """Exact Citrine pre-staging capture; never fall back to another unit."""
    return _unit_flash_reference(CITRINE_BACKUP, CITRINE_REPORT_SHA256, CITRINE_DUMP_SHA256, CITRINE_APP_SHA256)


def _unit_flash_reference(directory, report_sha, dump_sha, app_sha) -> bytes:
    report_bytes = (directory / "report.json").read_bytes()
    if hashlib.sha256(report_bytes).hexdigest() != report_sha:
        raise ValueError("Test01 backup report SHA-256 mismatch")
    report = json.loads(report_bytes)
    if (report.get("status") != "verified_double_dump"
            or report.get("comparison", {}).get("byte_equal") is not True
            or report.get("comparison", {}).get("sha256") != dump_sha
            or report.get("loader", {}).get("chip_key") != KEY
            or report.get("loader", {}).get("device_type") != 3
            or report.get("loader", {}).get("flash_id") != 0x856014):
        raise ValueError("Test01 backup identity or double-read evidence mismatch")
    events = (directory / "events.jsonl").read_bytes()
    if hashlib.sha256(events).hexdigest() != report.get("events_sha256"):
        raise ValueError("Test01 backup event journal SHA-256 mismatch")
    copies = []
    for number in (1, 2):
        with (directory / f"flash-pass-{number}.bin").open("rb") as stream:
            data = stream.read(0x100001)
        if len(data) != 0x100000 or hashlib.sha256(data).hexdigest() != dump_sha:
            raise ValueError(f"Test01 backup pass {number} size or SHA-256 mismatch")
        copies.append(data)
    if copies[0] != copies[1] or hashlib.sha256(copies[0][0x4000:FLASH_SIZE]).hexdigest() != app_sha:
        raise ValueError("Test01 backup app fingerprint or full byte equality mismatch")
    return copies[0][:FLASH_SIZE]


def app_layout(raw: bytes, expected_slot: int) -> tuple[bytearray, dict]:
    """Validate the known JLFS tree without replacing any template metadata."""
    if len(raw) != FLASH_SIZE - 0x4000:
        raise ValueError("App template has an unsupported extent")
    region = bytearray(raw)
    sfc(region, 0, len(region), 0, KEY)
    headers = [jlfs_header(region[offset:offset+32]) for offset in range(0, 224, 32)]
    area, app, cfg_tool, vm, prct, btif, usr = headers
    name = lambda h: h[7].split(b"\0", 1)[0]
    if (area[2], name(area), area[4]) != (0x02000120, b"app_area_head", 0x83):
        raise ValueError("App-area layout mismatch")
    if (app[2], app[3], name(app), app[4]) != (0x120, expected_slot, b"app.bin", 0x82):
        raise ValueError("App payload layout mismatch")
    app_end, area_end = app[2] + app[3], area[3]
    if (cfg_tool[2], cfg_tool[3], name(cfg_tool), cfg_tool[4]) != (app_end, 383, b"cfg_tool.bin", 0x82):
        raise ValueError("cfg_tool layout mismatch")
    if not 0x120 < app_end < area_end == cfg_tool[2] + cfg_tool[3] <= len(region) - 64:
        raise ValueError("App/cfg_tool extent exceeds the template")
    for actual, expected in [(vm, (0x93000, 352256, b"VM")), (prct, (0, FLASH_SIZE, b"PRCT")),
                             (btif, (0xE9000, 0x1000, b"BTIF")), (usr, (0xEA000, 0x12000, b"USR"))]:
        if (actual[2], actual[3], name(actual)) != expected:
            raise ValueError("Protected partition descriptor mismatch")
    for header, start, end in [(area, 32, area_end), (app, app[2], app_end),
                               (cfg_tool, cfg_tool[2], area_end)]:
        if crc16(region[start:end]) != header[1]:
            raise ValueError("App/cfg_tool nested data CRC mismatch")
    cfg = jlfs_header(region[area_end:area_end+32])
    eq = jlfs_header(region[area_end+32:area_end+64])
    cfg_end = area_end + cfg[3]
    eq_start, eq_end = area_end + eq[2], area_end + eq[2] + eq[3]
    if (name(cfg), cfg[2], cfg[4], name(eq), eq[2], eq[4]) != (b"cfg", 32, 0x83, b"eq_cfg_hw.bin", 64, 0x82):
        raise ValueError("Calibration directory layout mismatch")
    if not area_end + 64 <= eq_start < eq_end == cfg_end <= len(region):
        raise ValueError("Calibration extent exceeds the template")
    if crc16(region[area_end+32:cfg_end]) != cfg[1] or crc16(region[eq_start:eq_end]) != eq[1]:
        raise ValueError("Calibration data CRC mismatch")
    return region, {"app_offset": app[2], "app_slot_bytes": expected_slot, "area_bytes": area_end,
                    "cfg_tool_offset": cfg_tool[2], "cfg_tool_bytes": cfg_tool[3],
                    "cfg_offset": area_end, "cfg_bytes": cfg[3], "eq_offset": eq_start,
                    "eq_bytes": eq[3], "eq_sha256": hashlib.sha256(region[eq_start:eq_end]).hexdigest()}


def flash_image(app, key, template=PUBLISHED_TEMPLATE):
    """Preserve the complete original cfg/EQ/descriptor/padding region byte-for-byte.

    Only app.bin payload and the two affected JLFS header/data CRC pairs change.
    Generic SDK EQ defaults are checked as a pinned dependency but never emitted.
    """
    if template == PUBLISHED_TEMPLATE:
        result = bytearray(_format_flash_image(app, key))
        reference, slot = stock_app_reference(), APP_SLOT
    elif template in (TEST01_TEMPLATE, CITRINE_TEMPLATE):
        if key != KEY:
            raise ValueError("Exact-unit template chip key mismatch")
        for rel in SDK_SHA256:
            sdk_file(rel)  # Retain SDK hard pins; no generic calibration is emitted.
        result = bytearray(citrine_flash_reference() if template == CITRINE_TEMPLATE else test01_flash_reference())
        reference, slot = bytes(result[0x4000:]), TEST01_APP_SLOT
    else:
        raise ValueError("Unknown audited template")
    region, layout = app_layout(reference, slot)
    block_size = layout["area_bytes"]
    if not 4 <= len(app) <= slot or app[:4] != bytes.fromhex("04818000"):
        raise ValueError("App size or entry instruction exceeds the selected template")
    padded = app + b"\xFF"*(slot-len(app))
    region[0x120:0x120+slot] = padded
    struct.pack_into("<H", region, 34, crc16(padded))
    struct.pack_into("<H", region, 32, crc16(region[34:64]))
    struct.pack_into("<H", region, 2, crc16(region[32:block_size]))
    struct.pack_into("<H", region, 0, crc16(region[2:32]))
    sfc(region, 0, len(region), 0, key)
    if key == KEY:
        for start, end in [(4, 32), (36, 0x120), (0x120+slot, len(region))]:
            if region[start:end] != reference[start:end]:
                raise ValueError("Package changes stock metadata or calibration outside app CRC/payload")
    result[0x4000:] = region
    return bytes(result)


def ufw(flash, ota, product):
    files = [(0, "flash.bin", flash), (100, "ota.bin", ota)]
    off, ents, data = 0x400, [], bytearray()
    for i, (typ, name, d) in enumerate(files):
        off = (off + 0xFF) & ~0xFF
        e = bytearray(0x50)
        struct.pack_into("<HHHHIII", e, 0, typ, i, crc16(d), 0, off, len(d), (len(d) + 31) & ~31)
        e[0x40:0x40 + len(name)] = name.encode()
        ents.append((e, off, d))
        off += len(d)
    total = off
    hdr = bytearray(0x40)
    struct.pack_into("<IH", hdr, 4, total, len(files))
    struct.pack_into("<HHH", hdr, 10, 0x0004, 0x0200, 0)     # header fields as written by the SDK packer
    hdr[16:16 + len(UFW_CHIP)] = UFW_CHIP
    lst = bytearray()
    for e, _, _ in ents:
        x = bytearray(e)
        enc(x, 0, 0x50)
        lst += x
    struct.pack_into("<H", hdr, 2, crc16(lst))
    struct.pack_into("<H", hdr, 0, crc16(hdr[2:0x40]))
    enc(hdr, 0, 0x40)
    logical = bytearray(b"\xFF" * total)
    logical[0:0x40] = hdr
    logical[0x40:0x40 + len(lst)] = lst
    for e, o, d in ents:
        logical[o:o + len(d)] = d
    # .fwsc: one marker byte after each of the first 20 0x2F-byte blocks (the identity)
    if len(product) > 20 or any((ord(c) + i + 1) & 0xFF == 0x7D for i, c in enumerate(product)):
        raise ValueError("Invalid package product marker")
    raw = bytearray()
    for i in range(20):
        ch = product[i] if i < len(product) else None
        m = (ord(ch) + i + 1) & 0xFF if ch else 0x7D
        raw += logical[i * 0x2F:(i + 1) * 0x2F] + bytes([m])
    raw += logical[20 * 0x2F:]
    return bytes(raw)



# LZ4 encoder derived from the same pinned GPL-3.0-only source.
def _len_bytes(n):
    out = bytearray()
    while n >= 255:
        out.append(255)
        n -= 255
    out.append(n)
    return out


def lz4_compress(src: bytes) -> bytes:
    n, out, table = len(src), bytearray(), {}
    anchor, i = 0, 0
    limit = n - 12                                  # matches must start before this
    while i < limit:
        key = src[i:i + 4]
        cand = table.get(key)
        table[key] = i
        if cand is None or i - cand > 65535:
            i += 1
            continue
        mlen = 4                                    # extend; leave the last 5 bytes as literals
        while i + mlen < n - 5 and src[cand + mlen] == src[i + mlen]:
            mlen += 1
        lit = src[anchor:i]
        tok = (min(len(lit), 15) << 4) | min(mlen - 4, 15)
        out.append(tok)
        if len(lit) >= 15:
            out += _len_bytes(len(lit) - 15)
        out += lit
        off = i - cand
        out += bytes((off & 0xFF, off >> 8))
        if mlen - 4 >= 15:
            out += _len_bytes(mlen - 4 - 15)
        i += mlen
        anchor = i
    lit = src[anchor:]                              # final literal run
    out.append(min(len(lit), 15) << 4)
    if len(lit) >= 15:
        out += _len_bytes(len(lit) - 15)
    out += lit
    return bytes(out)


def lz4_decompress(block: bytes, expected: int) -> bytes:
    """Strict bounded block decoder; never accepts truncated literals or zero offsets."""
    if not 0 < expected <= 4096 or not 0 < len(block) <= 4096:
        raise ValueError("Invalid LZ4 block bound")
    out, pos = bytearray(), 0

    def length(initial):
        nonlocal pos
        result = initial
        if initial == 15:
            while True:
                if pos >= len(block):
                    raise ValueError("Truncated LZ4 length")
                extra = block[pos]
                pos += 1
                result += extra
                if result > expected:
                    raise ValueError("LZ4 expansion exceeds declared size")
                if extra != 255:
                    break
        return result

    while pos < len(block):
        token = block[pos]
        pos += 1
        literals = length(token >> 4)
        if literals > len(block) - pos or literals > expected - len(out):
            raise ValueError("Truncated or excessive LZ4 literals")
        out += block[pos:pos + literals]
        pos += literals
        if pos == len(block):
            if token & 15:
                raise ValueError("Final LZ4 token has a match")
            break
        if len(block) - pos < 2:
            raise ValueError("Truncated LZ4 offset")
        offset = int.from_bytes(block[pos:pos + 2], "little")
        pos += 2
        if offset == 0 or offset > len(out):
            raise ValueError("Invalid LZ4 offset")
        count = length(token & 15) + 4
        if count > expected - len(out):
            raise ValueError("LZ4 match exceeds declared size")
        for _ in range(count):
            out.append(out[-offset])
    if len(out) != expected:
        raise ValueError("LZ4 output size mismatch")
    return bytes(out)


def loader_wrap(image: bytes) -> bytes:
    if not 32 <= len(image) <= 0x8000 or LOADER_MARKER not in image[:68]:
        raise ValueError("Loader image lacks bounded startup admission marker")
    blocks = bytearray()
    for off in range(0, len(image), 4096):
        raw = image[off:off + 4096]
        compressed = lz4_compress(raw)
        if lz4_decompress(compressed, len(raw)) != raw:
            raise ValueError("Loader compression failed round trip")
        blocks += struct.pack("<II", len(compressed), len(raw)) + compressed
    inner = entry(crc16(image), len(image), LOADER_LOAD, 0, 0, 0, LOADER_NAME)
    body = inner + blocks
    if len(body) > 0x4E00:
        raise ValueError("Compressed loader exceeds OTA staging capacity")
    wrapped = entry(crc16(body), 0x20, len(body), 0x41, 0, 0, LOADER_NAME) + body
    # Existing first-stage firmware checks literal marker within this interval.
    if LOADER_MARKER not in wrapped[0x48:0x48 + 64]:
        raise ValueError("Compressed loader marker is outside first-stage admission window")
    if validate_loader(wrapped) != image:
        raise ValueError("Loader container did not round trip")
    return wrapped


def jlfs_header(data: bytes) -> tuple:
    if len(data) < 32 or crc16(data[2:32]) != int.from_bytes(data[:2], "little"):
        raise ValueError("JLFS header CRC mismatch")
    return struct.unpack_from("<HHIIBBH16s", data)


def validate_loader(data: bytes) -> bytes:
    if not 72 <= len(data) <= 0x4E20:
        raise ValueError("Invalid loader container length")
    _, checksum, offset, size, flag, reserved, index, name = jlfs_header(data)
    if (offset, size, flag, reserved, index, name) != (32, len(data)-32, 0x41, 0, 0, LOADER_NAME):
        raise ValueError("Invalid outer loader fields")
    if crc16(data[32:]) != checksum:
        raise ValueError("Loader body CRC mismatch")
    _, checksum, total, address, flag, reserved, index, name = jlfs_header(data[32:])
    if not 32 <= total <= 0x8000 or address != LOADER_LOAD or (flag, reserved, index) != (0, 0, 0) or name != LOADER_NAME:
        raise ValueError("Invalid loader RAM address or size")
    image, pos = bytearray(), 64
    while pos < len(data):
        if len(data)-pos < 8:
            raise ValueError("Truncated loader block header")
        compressed, unpacked = struct.unpack_from("<II", data, pos)
        pos += 8
        if compressed > len(data)-pos or unpacked != min(4096, total-len(image)):
            raise ValueError("Invalid loader block extent")
        image += lz4_decompress(data[pos:pos+compressed], unpacked)
        pos += compressed
    if len(image) != total or crc16(image) != checksum:
        raise ValueError("Loader decompressed size or CRC mismatch")
    if LOADER_MARKER not in image[:68] or LOADER_MARKER not in data[0x48:0x48+64]:
        raise ValueError("Loader startup admission marker absent")
    return bytes(image)


def extract_elf(data: bytes, kind: str) -> tuple[bytes, dict]:
    """Extract allocated PROGBITS by ELF PT_LOAD physical address, including RAM LMAs."""
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected ELF32 little-endian pi32v2 executable")
    etype, machine, version, address, phoff, shoff = struct.unpack_from("<HHIIII", data, 16)
    ehsize, phsize, phnum, shsize, shnum, shnames = struct.unpack_from("<HHHHHH", data, 40)
    base, maximum = (LOADER_LOAD, LOADER_LIMIT) if kind == "loader" else (0x02000120, APP_SLOT)
    if (etype, machine, version, address, ehsize, phsize, shsize) != (2, 0xF1, 1, base, 52, 32, 40):
        raise ValueError("ELF architecture, entry or table shape mismatch")
    if not 0 < phnum <= 32 or not 0 < shnum <= 256 or shnames >= shnum:
        raise ValueError("ELF table count exceeds bounds")
    if phoff > len(data)-phnum*32 or shoff > len(data)-shnum*40:
        raise ValueError("Truncated ELF tables")
    segments = [struct.unpack_from("<IIIIIIII", data, phoff+i*32) for i in range(phnum)]
    sections = [struct.unpack_from("<IIIIIIIIII", data, shoff+i*40) for i in range(shnum)]
    name_section = sections[shnames]
    names = data[name_section[4]:name_section[4]+name_section[5]]
    chunks, report = [], []
    for section in sections:
        nameoff, typ, flags, vma, off, size, _, _, _, _ = section
        if not flags & 2 or not size:
            continue
        if vma + size > 0x100000000:
            raise ValueError("ELF address overflow")
        name = names[nameoff:].split(b"\0", 1)[0].decode("ascii", errors="strict")
        if kind == "loader" and not LOADER_LOAD <= vma <= LOADER_LOAD+LOADER_LIMIT-size:
            raise ValueError("Allocated loader section lies outside its RAM region")
        if typ == 8:  # SHT_NOBITS has no package bytes.
            report.append({"name": name, "vma": vma, "bytes": size, "noload": True})
            continue
        if typ != 1 or off > len(data)-size:
            raise ValueError("Unsupported or truncated allocated ELF section")
        matches = [p for p in segments if p[0] == 1 and p[1] <= off and off+size <= p[1]+p[4]
                   and p[2] <= vma and vma+size <= p[2]+p[5] and off-p[1] == vma-p[2]]
        if len(matches) != 1:
            raise ValueError("ELF section does not have a unique load address")
        p = matches[0]
        lma = p[3] + vma-p[2]
        if not base <= lma <= base+maximum-size:
            raise ValueError("ELF load address is outside the application/loader slot")
        chunks.append((lma-base, data[off:off+size]))
        report.append({"name": name, "vma": vma, "lma": lma, "bytes": size, "noload": False})
    chunks.sort()
    if not chunks or chunks[0][0] != 0:
        raise ValueError("ELF has no image at the required entry point")
    image = bytearray()
    for off, chunk in chunks:
        if off < len(image):
            raise ValueError("ELF load sections overlap")
        image += b"\xff"*(off-len(image)) + chunk
    if kind == "app" and image[:4] != bytes.fromhex("04818000"):
        raise ValueError("App entry instruction mismatch")
    return bytes(image), {"entry": address, "sections": report, "bytes": len(image)}


def decode_package(raw: bytes) -> tuple[str, bytes, dict]:
    if not 1044 <= len(raw) <= 0x100000:
        raise ValueError("Invalid package extent")
    product, ended, logical = bytearray(), False, bytearray()
    for i in range(20):
        logical += raw[i*48:i*48+47]
        marker = raw[i*48+47]
        if marker == 0x7D:
            ended = True
        elif ended:
            raise ValueError("Noncontiguous package identity")
        else:
            ch = (marker-i-1) & 255
            if not 32 <= ch < 127:
                raise ValueError("Non-ASCII package identity")
            product.append(ch)
    logical += raw[960:]
    product = product.decode("ascii")
    if product not in SUPPORTED_PRODUCTS:
        raise ValueError("Unexpected package identity")
    header = bytearray(logical[:64])
    enc(header, 0, 64)
    total, count = struct.unpack_from("<IH", header, 4)
    if total != len(logical) or count != 2 or header[16:32].rstrip(b"\0") != UFW_CHIP:
        raise ValueError("Package header extent, entries or chip mismatch")
    if struct.unpack_from("<HHH", header, 10) != (4, 0x200, 0):
        raise ValueError("Unexpected UFW format fields")
    if crc16(header[2:]) != int.from_bytes(header[:2], "little") or crc16(logical[64:224]) != int.from_bytes(header[2:4], "little"):
        raise ValueError("Package header/list CRC mismatch")
    files, intervals = {}, []
    for i, (expected_type, expected_name) in enumerate([(0, "flash.bin"), (100, "ota.bin")]):
        entry_data = bytearray(logical[64+i*80:144+i*80])
        enc(entry_data, 0, 80)
        typ, idx, checksum, reserved, off, size, padded = struct.unpack_from("<HHHHIII", entry_data)
        name = bytes(entry_data[64:]).rstrip(b"\0")
        if (typ, idx, reserved, name) != (expected_type, i, 0, expected_name.encode()):
            raise ValueError("Unexpected package entry")
        if off < 1024 or off & 255 or size == 0 or padded != (size+31)&~31 or off > len(logical)-size:
            raise ValueError("Package entry lies outside logical image")
        if any(off < end and start < off+size for start, end in intervals):
            raise ValueError("Overlapping package entries")
        intervals.append((off, off+size))
        payload = bytes(logical[off:off+size])
        if crc16(payload) != checksum:
            raise ValueError(f"Package payload CRC mismatch: {expected_name}")
        files[expected_name] = {"offset": off, "bytes": size, "crc16": checksum, "payload": payload}
    if max(end for _, end in intervals) != len(logical):
        raise ValueError("Trailing package bytes")
    return product, bytes(logical), files


def _installed_reference(identity, package_path, package_hash, journal_path, journal_hash, app_hash, template=TEST01_TEMPLATE) -> bytes:
    """Expected current bytes from the exact package whose installation completed.

    This is a package-derived fingerprint, not a new physical flash readback.
    Stock calibration still comes from the immutable double-read backup.
    """
    raw = package_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != package_hash:
        raise ValueError(f"Installed {identity} package SHA-256 mismatch")
    events_raw = journal_path.read_bytes()
    if hashlib.sha256(events_raw).hexdigest() != journal_hash:
        raise ValueError(f"Installed {identity} flash journal SHA-256 mismatch")
    events = [json.loads(line) for line in events_raw.splitlines()]
    if (not events or events[-1].get("event") != "completed" or events[-1].get("identity") != identity or
            events[0].get("package", {}).get("package_sha256") != package_hash):
        raise ValueError(f"Installed {identity} successful transition evidence is missing")
    report = validate_package(raw, template)
    product, _, files = decode_package(raw)
    if product != identity or report["template"] != template:
        raise ValueError(f"Installed {identity} origin identity/template mismatch")
    app = files["flash.bin"]["payload"][0x4000:FLASH_SIZE]
    if hashlib.sha256(app).hexdigest() != app_hash:
        raise ValueError(f"Installed {identity} raw application SHA-256 mismatch")
    return app


def installed_701_reference() -> bytes:
    return _installed_reference(PRODUCT, INSTALLED_701_PACKAGE, INSTALLED_701_PACKAGE_SHA256,
                                INSTALLED_701_JOURNAL, INSTALLED_701_JOURNAL_SHA256, INSTALLED_701_APP_SHA256)


def installed_702_reference() -> bytes:
    return _installed_reference(NEXT_PRODUCT, INSTALLED_702_PACKAGE, INSTALLED_702_PACKAGE_SHA256,
                                INSTALLED_702_JOURNAL, INSTALLED_702_JOURNAL_SHA256, INSTALLED_702_APP_SHA256)


def installed_703_reference() -> bytes:
    return _installed_reference(CURRENT_PRODUCT, INSTALLED_703_PACKAGE, INSTALLED_703_PACKAGE_SHA256,
                                INSTALLED_703_JOURNAL, INSTALLED_703_JOURNAL_SHA256, INSTALLED_703_APP_SHA256)


def installed_704_reference() -> bytes:
    return _installed_reference(BUILD_PRODUCT, INSTALLED_704_PACKAGE, INSTALLED_704_PACKAGE_SHA256,
                                INSTALLED_704_JOURNAL, INSTALLED_704_JOURNAL_SHA256, INSTALLED_704_APP_SHA256)


def installed_705_reference() -> bytes:
    return _installed_reference(LATEST_PRODUCT, INSTALLED_705_PACKAGE, INSTALLED_705_PACKAGE_SHA256,
                                INSTALLED_705_JOURNAL, INSTALLED_705_JOURNAL_SHA256, INSTALLED_705_APP_SHA256)


def installed_706_reference() -> bytes:
    return _installed_reference(DEVELOPMENT_PRODUCT, INSTALLED_706_PACKAGE, INSTALLED_706_PACKAGE_SHA256,
                                INSTALLED_706_JOURNAL, INSTALLED_706_JOURNAL_SHA256, INSTALLED_706_APP_SHA256)


def installed_707_reference() -> bytes:
    return _installed_reference(CANDIDATE_PRODUCT, INSTALLED_707_PACKAGE, INSTALLED_707_PACKAGE_SHA256,
                                INSTALLED_707_JOURNAL, INSTALLED_707_JOURNAL_SHA256, INSTALLED_707_APP_SHA256)


def installed_708_reference() -> bytes:
    return _installed_reference(INSTRUMENT_PRODUCT, INSTALLED_708_PACKAGE, INSTALLED_708_PACKAGE_SHA256,
                                INSTALLED_708_JOURNAL, INSTALLED_708_JOURNAL_SHA256, INSTALLED_708_APP_SHA256)

def installed_709_reference() -> bytes:
    return _installed_reference(BANK_PRODUCT, INSTALLED_709_PACKAGE, INSTALLED_709_PACKAGE_SHA256,
                                INSTALLED_709_JOURNAL, INSTALLED_709_JOURNAL_SHA256, INSTALLED_709_APP_SHA256)

def installed_710_reference() -> bytes:
    return _installed_reference(MIDI_PRODUCT, INSTALLED_710_PACKAGE, INSTALLED_710_PACKAGE_SHA256,
                                INSTALLED_710_JOURNAL, INSTALLED_710_JOURNAL_SHA256, INSTALLED_710_APP_SHA256)

def installed_711_reference() -> bytes:
    return _installed_reference(WORKSPACE_PRODUCT, INSTALLED_711_PACKAGE, INSTALLED_711_PACKAGE_SHA256,
                                INSTALLED_711_JOURNAL, INSTALLED_711_JOURNAL_SHA256, INSTALLED_711_APP_SHA256)


def installed_712_reference() -> bytes:
    return _installed_reference(FX_PRODUCT, INSTALLED_712_PACKAGE, INSTALLED_712_PACKAGE_SHA256,
                                INSTALLED_712_JOURNAL, INSTALLED_712_JOURNAL_SHA256, INSTALLED_712_APP_SHA256)


def installed_713_reference() -> bytes:
    return _installed_reference(OPTIMIZED_FX_PRODUCT, INSTALLED_713_PACKAGE, INSTALLED_713_PACKAGE_SHA256,
                                INSTALLED_713_JOURNAL, INSTALLED_713_JOURNAL_SHA256, INSTALLED_713_APP_SHA256)


def installed_714_reference() -> bytes:
    return _installed_reference(FINAL_FX_PRODUCT, INSTALLED_714_PACKAGE, INSTALLED_714_PACKAGE_SHA256,
                                INSTALLED_714_JOURNAL, INSTALLED_714_JOURNAL_SHA256, INSTALLED_714_APP_SHA256)


def installed_715_reference() -> bytes:
    return _installed_reference(SHOWCASE_PRODUCT, INSTALLED_715_PACKAGE, INSTALLED_715_PACKAGE_SHA256,
                                INSTALLED_715_JOURNAL, INSTALLED_715_JOURNAL_SHA256, INSTALLED_715_APP_SHA256)


def installed_716_reference() -> bytes:
    return _installed_reference(TIMBRE_PRODUCT, INSTALLED_716_PACKAGE, INSTALLED_716_PACKAGE_SHA256,
                                INSTALLED_716_JOURNAL, INSTALLED_716_JOURNAL_SHA256, INSTALLED_716_APP_SHA256)


def installed_717_reference() -> bytes:
    return _installed_reference(VISUAL_PRODUCT, INSTALLED_717_PACKAGE, INSTALLED_717_PACKAGE_SHA256,
                                INSTALLED_717_JOURNAL, INSTALLED_717_JOURNAL_SHA256, INSTALLED_717_APP_SHA256)


def installed_718_reference() -> bytes:
    return _installed_reference(REACTIVE_PRODUCT, INSTALLED_718_PACKAGE, INSTALLED_718_PACKAGE_SHA256,
                                INSTALLED_718_JOURNAL, INSTALLED_718_JOURNAL_SHA256, INSTALLED_718_APP_SHA256)


def installed_719_reference() -> bytes:
    # This immutable initial719 package admits718. Its own validation therefore
    # takes the historical branch below and cannot recurse through this helper.
    return _installed_reference(WORKSTATION_PRODUCT, INSTALLED_719_PACKAGE, INSTALLED_719_PACKAGE_SHA256,
                                INSTALLED_719_JOURNAL, INSTALLED_719_JOURNAL_SHA256, INSTALLED_719_APP_SHA256)


def installed_719_corrected_reference() -> bytes:
    # The frozen corrected719 loader admits only initial719. Validation walks
    # backward through that explicit predecessor, never through this helper.
    return _installed_reference(WORKSTATION_PRODUCT, INSTALLED_719_CORRECTED_PACKAGE,
                                INSTALLED_719_CORRECTED_PACKAGE_SHA256, INSTALLED_719_CORRECTED_JOURNAL,
                                INSTALLED_719_CORRECTED_JOURNAL_SHA256, INSTALLED_719_CORRECTED_APP_SHA256)


def installed_719_final_reference() -> bytes:
    # This exact third719 package admits corrected719, retaining a finite chain.
    return _installed_reference(WORKSTATION_PRODUCT, INSTALLED_719_FINAL_PACKAGE,
                                INSTALLED_719_FINAL_PACKAGE_SHA256, INSTALLED_719_FINAL_JOURNAL,
                                INSTALLED_719_FINAL_JOURNAL_SHA256, INSTALLED_719_FINAL_APP_SHA256)


def installed_719_optimized_reference() -> bytes:
    # The fourth719 loader points strictly backward to the pinned third image.
    return _installed_reference(WORKSTATION_PRODUCT, INSTALLED_719_OPTIMIZED_PACKAGE,
                                INSTALLED_719_OPTIMIZED_PACKAGE_SHA256, INSTALLED_719_OPTIMIZED_JOURNAL,
                                INSTALLED_719_OPTIMIZED_JOURNAL_SHA256, INSTALLED_719_OPTIMIZED_APP_SHA256)


def installed_719_arithmetic_reference() -> bytes:
    # Fifth719 points strictly backward to the fourth installed image.
    return _installed_reference(WORKSTATION_PRODUCT, INSTALLED_719_ARITHMETIC_PACKAGE,
                                INSTALLED_719_ARITHMETIC_PACKAGE_SHA256, INSTALLED_719_ARITHMETIC_JOURNAL,
                                INSTALLED_719_ARITHMETIC_JOURNAL_SHA256, INSTALLED_719_ARITHMETIC_APP_SHA256)


def installed_719_phaser_reference() -> bytes:
    # Sixth719 points strictly backward to the fifth installed image.
    return _installed_reference(WORKSTATION_PRODUCT, INSTALLED_719_PHASER_PACKAGE,
                                INSTALLED_719_PHASER_PACKAGE_SHA256, INSTALLED_719_PHASER_JOURNAL,
                                INSTALLED_719_PHASER_JOURNAL_SHA256, INSTALLED_719_PHASER_APP_SHA256)


def installed_719_inline_reference() -> bytes:
    # The seventh719 image points strictly backward to the sixth. This is the
    # reviewed initial720 origin, proven by exact bytes and its completed journal.
    return _installed_reference(WORKSTATION_PRODUCT, INSTALLED_719_INLINE_PACKAGE,
                                INSTALLED_719_INLINE_PACKAGE_SHA256, INSTALLED_719_INLINE_JOURNAL,
                                INSTALLED_719_INLINE_JOURNAL_SHA256, INSTALLED_719_INLINE_APP_SHA256)


def installed_720_release4_reference() -> bytes:
    # Exact first installed720; its own loader points backward to seventh719.
    # Same identity is insufficient: both package and completed journal are pinned.
    return _installed_reference(PROJECT_PRODUCT, INSTALLED_720_RELEASE4_PACKAGE,
                                INSTALLED_720_RELEASE4_PACKAGE_SHA256, INSTALLED_720_RELEASE4_JOURNAL,
                                INSTALLED_720_RELEASE4_JOURNAL_SHA256, INSTALLED_720_RELEASE4_APP_SHA256)


def installed_720_release5_reference() -> bytes:
    # Exact second installed720; its loader admits only the first installed720.
    return _installed_reference(PROJECT_PRODUCT, INSTALLED_720_RELEASE5_PACKAGE,
                                INSTALLED_720_RELEASE5_PACKAGE_SHA256, INSTALLED_720_RELEASE5_JOURNAL,
                                INSTALLED_720_RELEASE5_JOURNAL_SHA256, INSTALLED_720_RELEASE5_APP_SHA256)


def installed_721_reference() -> bytes:
    return _installed_reference(PERFORMANCE_PRODUCT,INSTALLED_721_PACKAGE,
        INSTALLED_721_PACKAGE_SHA256,INSTALLED_721_JOURNAL,
        INSTALLED_721_JOURNAL_SHA256,INSTALLED_721_APP_SHA256)


def installed_720_release6_reference() -> bytes:
    return _installed_reference(PROJECT_PRODUCT,INSTALLED_720_RELEASE6_PACKAGE,
        INSTALLED_720_RELEASE6_PACKAGE_SHA256,INSTALLED_720_RELEASE6_JOURNAL,
        INSTALLED_720_RELEASE6_JOURNAL_SHA256,INSTALLED_720_RELEASE6_APP_SHA256)


def transition_profile(product: str, template: str, loader: bytes | None = None) -> dict:
    if product == REFINEMENT_PRODUCT:
        if template not in (TEST01_TEMPLATE,CITRINE_TEMPLATE):
            raise ValueError('733 requires exact installed unit template')
        prefix='INSTALLED_CITRINE_731' if template==CITRINE_TEMPLATE else 'INSTALLED_731'
        digest=globals()[prefix+'_APP_SHA256']; package=globals()[prefix+'_PACKAGE_SHA256']
        known={v for k,v in globals().items() if k.endswith('_APP_SHA256') and isinstance(v,str)}
        if not isinstance(loader,bytes) or loader.count(bytes.fromhex(digest))!=1 or any(bytes.fromhex(v) in loader for v in known if v!=digest):
            raise ValueError('733 requires exactly this unit installed731 fingerprint')
        _installed_reference(LINK_PRODUCT,globals()[prefix+'_PACKAGE'],package,
            globals()[prefix+'_JOURNAL'],globals()[prefix+'_JOURNAL_SHA256'],digest,template)
        return dict(origin_identity=LINK_PRODUCT,loader_identity='ota-'+product,origin_app_sha256=digest,origin_package_sha256=package)
    if product == LINK_PRODUCT:
        if template not in (TEST01_TEMPLATE,CITRINE_TEMPLATE):
            raise ValueError('731 requires exact installed unit template')
        prefix='INSTALLED_CITRINE_730' if template==CITRINE_TEMPLATE else 'INSTALLED_730'
        digest=globals()[prefix+'_APP_SHA256']; package=globals()[prefix+'_PACKAGE_SHA256']
        known={v for k,v in globals().items() if k.endswith('_APP_SHA256') and isinstance(v,str)}
        if not isinstance(loader,bytes) or loader.count(bytes.fromhex(digest))!=1 or any(bytes.fromhex(v) in loader for v in known if v!=digest):
            raise ValueError('731 requires exactly this unit installed730 fingerprint')
        _installed_reference(SONG_PRODUCT,globals()[prefix+'_PACKAGE'],package,
            globals()[prefix+'_JOURNAL'],globals()[prefix+'_JOURNAL_SHA256'],digest,template)
        return dict(origin_identity=SONG_PRODUCT,loader_identity='ota-'+product,origin_app_sha256=digest,origin_package_sha256=package)
    if template == CITRINE_TEMPLATE:
        if product != SONG_PRODUCT:
            raise ValueError("Citrine capture qualifies only the stock V15 to730 transition")
        known = {value for name, value in globals().items()
                 if name.endswith('_APP_SHA256') and isinstance(value, str)}
        if (not isinstance(loader, bytes) or loader.count(bytes.fromhex(CITRINE_APP_SHA256)) != 1
                or any(bytes.fromhex(value) in loader for value in known if value != CITRINE_APP_SHA256)):
            raise ValueError("Citrine loader requires one exact stock fingerprint, no mixed origins")
        citrine_flash_reference()
        return dict(origin_identity="FM-1_015", loader_identity="ota-" + product,
                    origin_app_sha256=CITRINE_APP_SHA256, origin_package_sha256=None)
    if product == PRODUCT:
        origin_hash = TEST01_APP_SHA256 if template == TEST01_TEMPLATE else STOCK_APP_SHA256
        return {"origin_identity": "FM-1_015", "loader_identity": "ota-" + PRODUCT,
                "origin_app_sha256": origin_hash, "origin_package_sha256": None}
    if product not in SUPPORTED_PRODUCTS[1:] or template != TEST01_TEMPLATE:
        raise ValueError("Successor requires the exact Test01 template and explicitly known installed origin")
    if product == NEXT_PRODUCT:
        installed_701_reference()
        origin, digest, package = PRODUCT, INSTALLED_701_APP_SHA256, INSTALLED_701_PACKAGE_SHA256
    elif product == CURRENT_PRODUCT:
        installed_702_reference()
        origin, digest, package = NEXT_PRODUCT, INSTALLED_702_APP_SHA256, INSTALLED_702_PACKAGE_SHA256
    elif product == BUILD_PRODUCT:
        installed_703_reference()
        origin, digest, package = CURRENT_PRODUCT, INSTALLED_703_APP_SHA256, INSTALLED_703_PACKAGE_SHA256
    elif product == LATEST_PRODUCT:
        installed_704_reference()
        origin, digest, package = BUILD_PRODUCT, INSTALLED_704_APP_SHA256, INSTALLED_704_PACKAGE_SHA256
    elif product == DEVELOPMENT_PRODUCT:
        installed_705_reference()
        origin, digest, package = LATEST_PRODUCT, INSTALLED_705_APP_SHA256, INSTALLED_705_PACKAGE_SHA256
    elif product == CANDIDATE_PRODUCT:
        installed_706_reference()
        origin, digest, package = DEVELOPMENT_PRODUCT, INSTALLED_706_APP_SHA256, INSTALLED_706_PACKAGE_SHA256
    elif product == INSTRUMENT_PRODUCT:
        installed_707_reference()
        origin, digest, package = CANDIDATE_PRODUCT, INSTALLED_707_APP_SHA256, INSTALLED_707_PACKAGE_SHA256
    elif product == BANK_PRODUCT:
        installed_708_reference()
        origin, digest, package = INSTRUMENT_PRODUCT, INSTALLED_708_APP_SHA256, INSTALLED_708_PACKAGE_SHA256
    elif product == MIDI_PRODUCT:
        installed_709_reference()
        origin,digest,package=BANK_PRODUCT,INSTALLED_709_APP_SHA256,INSTALLED_709_PACKAGE_SHA256
    elif product == WORKSPACE_PRODUCT:
        installed_710_reference()
        origin,digest,package=MIDI_PRODUCT,INSTALLED_710_APP_SHA256,INSTALLED_710_PACKAGE_SHA256
    elif product == FX_PRODUCT:
        installed_711_reference()
        origin,digest,package=WORKSPACE_PRODUCT,INSTALLED_711_APP_SHA256,INSTALLED_711_PACKAGE_SHA256
    elif product == OPTIMIZED_FX_PRODUCT:
        installed_712_reference()
        origin,digest,package=FX_PRODUCT,INSTALLED_712_APP_SHA256,INSTALLED_712_PACKAGE_SHA256
    elif product == FINAL_FX_PRODUCT:
        installed_713_reference()
        origin,digest,package=OPTIMIZED_FX_PRODUCT,INSTALLED_713_APP_SHA256,INSTALLED_713_PACKAGE_SHA256
    elif product == SHOWCASE_PRODUCT:
        installed_714_reference()
        origin,digest,package=FINAL_FX_PRODUCT,INSTALLED_714_APP_SHA256,INSTALLED_714_PACKAGE_SHA256
    elif product == TIMBRE_PRODUCT:
        installed_715_reference()
        origin,digest,package=SHOWCASE_PRODUCT,INSTALLED_715_APP_SHA256,INSTALLED_715_PACKAGE_SHA256
    elif product == VISUAL_PRODUCT:
        installed_716_reference()
        origin,digest,package=TIMBRE_PRODUCT,INSTALLED_716_APP_SHA256,INSTALLED_716_PACKAGE_SHA256
    elif product == REACTIVE_PRODUCT:
        installed_717_reference()
        origin,digest,package=VISUAL_PRODUCT,INSTALLED_717_APP_SHA256,INSTALLED_717_PACKAGE_SHA256
    elif product == SYNC_PRODUCT:
        digest=INSTALLED_722_RELEASE1_APP_SHA256
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            admitted=(INSTALLED_721_APP_SHA256,INSTALLED_722_RELEASE1_APP_SHA256)
            found=[value for value in known if bytes.fromhex(value) in loader] if isinstance(loader,bytes) else []
            if len(found)!=1 or found[0] not in admitted or loader.count(bytes.fromhex(found[0]))!=1:
                raise ValueError('722 requires one unique, pinned721 or initial722 origin; no mixed or generic origins')
            digest=found[0]
        if digest==INSTALLED_721_APP_SHA256:
            installed_721_reference();origin,package=PERFORMANCE_PRODUCT,INSTALLED_721_PACKAGE_SHA256
        else:
            _installed_reference(SYNC_PRODUCT,INSTALLED_722_RELEASE1_PACKAGE,INSTALLED_722_RELEASE1_PACKAGE_SHA256,
                INSTALLED_722_RELEASE1_JOURNAL,INSTALLED_722_RELEASE1_JOURNAL_SHA256,INSTALLED_722_RELEASE1_APP_SHA256)
            origin,package=SYNC_PRODUCT,INSTALLED_722_RELEASE1_PACKAGE_SHA256
    elif product == SONG_PRODUCT:
        digest=INSTALLED_729_RELEASE2_APP_SHA256
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            if not isinstance(loader,bytes) or loader.count(bytes.fromhex(digest))!=1 or any(bytes.fromhex(value) in loader for value in known if value!=digest):
                raise ValueError('730 requires exactly the installed729 release2 origin; no alternate origin admitted')
        _installed_reference(DEFAULTS_PRODUCT,INSTALLED_729_RELEASE2_PACKAGE,INSTALLED_729_RELEASE2_PACKAGE_SHA256,INSTALLED_729_RELEASE2_JOURNAL,INSTALLED_729_RELEASE2_JOURNAL_SHA256,digest)
        origin,package=DEFAULTS_PRODUCT,INSTALLED_729_RELEASE2_PACKAGE_SHA256
    elif product == DEFAULTS_PRODUCT:
        digest=INSTALLED_729_RELEASE1_APP_SHA256
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            allowed={INSTALLED_728_RELEASE3_APP_SHA256,INSTALLED_729_RELEASE1_APP_SHA256}
            found=[value for value in allowed if isinstance(loader,bytes) and loader.count(bytes.fromhex(value))==1]
            if len(found)!=1 or any(bytes.fromhex(value) in loader for value in known if value!=found[0]):
                raise ValueError('729 requires one exact installed728 release3 or initial729 fingerprint; no mixed origins')
            digest=found[0]
        if digest==INSTALLED_728_RELEASE3_APP_SHA256:
            _installed_reference(ROUTING_PRODUCT,INSTALLED_728_RELEASE3_PACKAGE,INSTALLED_728_RELEASE3_PACKAGE_SHA256,INSTALLED_728_RELEASE3_JOURNAL,INSTALLED_728_RELEASE3_JOURNAL_SHA256,digest)
            origin,package=ROUTING_PRODUCT,INSTALLED_728_RELEASE3_PACKAGE_SHA256
        else:
            _installed_reference(DEFAULTS_PRODUCT,INSTALLED_729_RELEASE1_PACKAGE,INSTALLED_729_RELEASE1_PACKAGE_SHA256,INSTALLED_729_RELEASE1_JOURNAL,INSTALLED_729_RELEASE1_JOURNAL_SHA256,digest)
            origin,package=DEFAULTS_PRODUCT,INSTALLED_729_RELEASE1_PACKAGE_SHA256
    elif product == ROUTING_PRODUCT:
        digest=INSTALLED_728_RELEASE1_APP_SHA256
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            allowed={INSTALLED_727_APP_SHA256,INSTALLED_728_RELEASE1_APP_SHA256}
            found=[value for value in allowed if isinstance(loader,bytes) and loader.count(bytes.fromhex(value))==1]
            if len(found)!=1 or any(bytes.fromhex(value) in loader for value in known if value!=found[0]):
                raise ValueError('728 requires one exact installed727 or initial728 fingerprint; no mixed origins')
            digest=found[0]
        if digest==INSTALLED_727_APP_SHA256:
            _installed_reference(WORKFLOW_PRODUCT,INSTALLED_727_PACKAGE,INSTALLED_727_PACKAGE_SHA256,INSTALLED_727_JOURNAL,INSTALLED_727_JOURNAL_SHA256,digest)
            origin,package=WORKFLOW_PRODUCT,INSTALLED_727_PACKAGE_SHA256
        else:
            _installed_reference(ROUTING_PRODUCT,INSTALLED_728_RELEASE1_PACKAGE,INSTALLED_728_RELEASE1_PACKAGE_SHA256,INSTALLED_728_RELEASE1_JOURNAL,INSTALLED_728_RELEASE1_JOURNAL_SHA256,digest)
            origin,package=ROUTING_PRODUCT,INSTALLED_728_RELEASE1_PACKAGE_SHA256
    elif product == WORKFLOW_PRODUCT:
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            if (not isinstance(loader,bytes) or loader.count(bytes.fromhex(INSTALLED_726_APP_SHA256))!=1 or
                any(bytes.fromhex(value) in loader for value in known if value!=INSTALLED_726_APP_SHA256)):
                raise ValueError('727 requires exactly one installed726 origin fingerprint, without alternate origins')
        _installed_reference(POLISH_PRODUCT,INSTALLED_726_PACKAGE,INSTALLED_726_PACKAGE_SHA256,INSTALLED_726_JOURNAL,INSTALLED_726_JOURNAL_SHA256,INSTALLED_726_APP_SHA256)
        origin,digest,package=POLISH_PRODUCT,INSTALLED_726_APP_SHA256,INSTALLED_726_PACKAGE_SHA256
    elif product == POLISH_PRODUCT:
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            if (not isinstance(loader,bytes) or loader.count(bytes.fromhex(INSTALLED_724_RELEASE3_APP_SHA256))!=1 or
                any(bytes.fromhex(value) in loader for value in known if value!=INSTALLED_724_RELEASE3_APP_SHA256)):
                raise ValueError('726 requires exactly one installed724 release3 origin fingerprint, without alternate origins')
        _installed_reference(PREVIEW_PRODUCT,INSTALLED_724_RELEASE3_PACKAGE,INSTALLED_724_RELEASE3_PACKAGE_SHA256,INSTALLED_724_RELEASE3_JOURNAL,INSTALLED_724_RELEASE3_JOURNAL_SHA256,INSTALLED_724_RELEASE3_APP_SHA256)
        origin,digest,package=PREVIEW_PRODUCT,INSTALLED_724_RELEASE3_APP_SHA256,INSTALLED_724_RELEASE3_PACKAGE_SHA256
    elif product == RELEASE_PRODUCT:
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            if (not isinstance(loader,bytes) or loader.count(bytes.fromhex(INSTALLED_724_RELEASE3_APP_SHA256))!=1 or
                any(bytes.fromhex(value) in loader for value in known if value!=INSTALLED_724_RELEASE3_APP_SHA256)):
                raise ValueError('725 requires exactly one installed724 release3 origin fingerprint, without alternate origins')
        _installed_reference(PREVIEW_PRODUCT,INSTALLED_724_RELEASE3_PACKAGE,INSTALLED_724_RELEASE3_PACKAGE_SHA256,INSTALLED_724_RELEASE3_JOURNAL,INSTALLED_724_RELEASE3_JOURNAL_SHA256,INSTALLED_724_RELEASE3_APP_SHA256)
        origin,digest,package=PREVIEW_PRODUCT,INSTALLED_724_RELEASE3_APP_SHA256,INSTALLED_724_RELEASE3_PACKAGE_SHA256
    elif product == PREVIEW_PRODUCT:
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            if (not isinstance(loader,bytes) or loader.count(bytes.fromhex(INSTALLED_723_RELEASE4_APP_SHA256))!=1 or
                any(bytes.fromhex(value) in loader for value in known if value!=INSTALLED_723_RELEASE4_APP_SHA256)):
                raise ValueError('724 requires exactly one installed723 release4 origin fingerprint, without alternate origins')
        _installed_reference(CLEANUP_PRODUCT,INSTALLED_723_RELEASE4_PACKAGE,INSTALLED_723_RELEASE4_PACKAGE_SHA256,INSTALLED_723_RELEASE4_JOURNAL,INSTALLED_723_RELEASE4_JOURNAL_SHA256,INSTALLED_723_RELEASE4_APP_SHA256)
        origin,digest,package=CLEANUP_PRODUCT,INSTALLED_723_RELEASE4_APP_SHA256,INSTALLED_723_RELEASE4_PACKAGE_SHA256
    elif product == CLEANUP_PRODUCT:
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            if (not isinstance(loader,bytes) or loader.count(bytes.fromhex(INSTALLED_722_RELEASE2_APP_SHA256))!=1 or
                any(bytes.fromhex(value) in loader for value in known if value!=INSTALLED_722_RELEASE2_APP_SHA256)):
                raise ValueError('723 requires exactly one installed722 release2 origin fingerprint, without alternate origins')
        _installed_reference(SYNC_PRODUCT,INSTALLED_722_RELEASE2_PACKAGE,INSTALLED_722_RELEASE2_PACKAGE_SHA256,INSTALLED_722_RELEASE2_JOURNAL,INSTALLED_722_RELEASE2_JOURNAL_SHA256,INSTALLED_722_RELEASE2_APP_SHA256)
        origin,digest,package=SYNC_PRODUCT,INSTALLED_722_RELEASE2_APP_SHA256,INSTALLED_722_RELEASE2_PACKAGE_SHA256
    elif product == PERFORMANCE_PRODUCT:
        if loader is not None:
            known={value for name,value in globals().items() if name.startswith('INSTALLED_') and name.endswith('_APP_SHA256')}
            if (not isinstance(loader,bytes) or loader.count(bytes.fromhex(INSTALLED_720_RELEASE6_APP_SHA256))!=1 or
                any(bytes.fromhex(value) in loader for value in known if value!=INSTALLED_720_RELEASE6_APP_SHA256)):
                raise ValueError('721 requires exactly one installed720 release6 origin fingerprint, without alternate origins')
        installed_720_release6_reference()
        origin,digest,package=PROJECT_PRODUCT,INSTALLED_720_RELEASE6_APP_SHA256,INSTALLED_720_RELEASE6_PACKAGE_SHA256
    elif product == PROJECT_PRODUCT:
        origins = (
            (WORKSTATION_PRODUCT, INSTALLED_719_INLINE_APP_SHA256, INSTALLED_719_INLINE_PACKAGE_SHA256,
             installed_719_inline_reference),
            (PROJECT_PRODUCT, INSTALLED_720_RELEASE4_APP_SHA256, INSTALLED_720_RELEASE4_PACKAGE_SHA256,
             installed_720_release4_reference),
            (PROJECT_PRODUCT, INSTALLED_720_RELEASE5_APP_SHA256, INSTALLED_720_RELEASE5_PACKAGE_SHA256,
             installed_720_release5_reference),
        )
        selected = 0  # Historical two-argument719-inline profile stays unchanged.
        if loader is not None:
            older = (INSTALLED_718_APP_SHA256, INSTALLED_719_APP_SHA256, INSTALLED_719_CORRECTED_APP_SHA256,
                     INSTALLED_719_FINAL_APP_SHA256, INSTALLED_719_OPTIMIZED_APP_SHA256,
                     INSTALLED_719_ARITHMETIC_APP_SHA256, INSTALLED_719_PHASER_APP_SHA256)
            if not isinstance(loader, bytes):
                raise ValueError('720 loader origin fingerprint is missing, unknown or ambiguous')
            counts = tuple(loader.count(bytes.fromhex(entry[1])) for entry in origins)
            if (sum(counts) != 1 or
                    any(bytes.fromhex(digest) in loader for digest in older)):
                raise ValueError('720 loader origin fingerprint is missing, unknown or ambiguous')
            selected = counts.index(1)
        origin, digest, package, verify_origin = origins[selected]
        verify_origin()
    else:
        # Seven exact predecessor packages are reviewed for719. Their immutable
        # loader digests make same-version validation a finite backward chain.
        # Never infer permission from the version label or an arbitrary hash.
        origins = (
            (REACTIVE_PRODUCT, INSTALLED_718_APP_SHA256, INSTALLED_718_PACKAGE_SHA256, installed_718_reference),
            (WORKSTATION_PRODUCT, INSTALLED_719_APP_SHA256, INSTALLED_719_PACKAGE_SHA256, installed_719_reference),
            (WORKSTATION_PRODUCT, INSTALLED_719_CORRECTED_APP_SHA256, INSTALLED_719_CORRECTED_PACKAGE_SHA256,
             installed_719_corrected_reference),
            (WORKSTATION_PRODUCT, INSTALLED_719_FINAL_APP_SHA256, INSTALLED_719_FINAL_PACKAGE_SHA256,
             installed_719_final_reference),
            (WORKSTATION_PRODUCT, INSTALLED_719_OPTIMIZED_APP_SHA256, INSTALLED_719_OPTIMIZED_PACKAGE_SHA256,
             installed_719_optimized_reference),
            (WORKSTATION_PRODUCT, INSTALLED_719_ARITHMETIC_APP_SHA256, INSTALLED_719_ARITHMETIC_PACKAGE_SHA256,
             installed_719_arithmetic_reference),
            (WORKSTATION_PRODUCT, INSTALLED_719_PHASER_APP_SHA256, INSTALLED_719_PHASER_PACKAGE_SHA256,
             installed_719_phaser_reference),
        )
        selected = 0  # Preserve the historical two-argument718-origin profile.
        if loader is not None:
            if not isinstance(loader, bytes):
                raise ValueError('719 loader origin fingerprint is missing, unknown or ambiguous')
            counts = tuple(loader.count(bytes.fromhex(entry[1])) for entry in origins)
            if sum(counts) != 1:
                raise ValueError('719 loader origin fingerprint is missing, unknown or ambiguous')
            selected = counts.index(1)
        origin, digest, package, verify_origin = origins[selected]
        verify_origin()
    return {"origin_identity": origin, "loader_identity": "ota-" + product,
            "origin_app_sha256": digest, "origin_package_sha256": package}


def validate_package(raw: bytes, template=None) -> dict:
    product, logical, files = decode_package(raw)
    flash = files["flash.bin"]["payload"]
    if len(flash) != FLASH_SIZE:
        raise ValueError("Unexpected flash.bin write extent")
    region = bytearray(flash[0x4000:])
    sfc(region, 0, len(region), 0, KEY)
    slot = jlfs_header(region[32:64])[3]
    loader = validate_loader(files["ota.bin"]["payload"])
    if template is None:
        template = {APP_SLOT: PUBLISHED_TEMPLATE, TEST01_APP_SLOT: TEST01_TEMPLATE}.get(slot)
        if product == SONG_PRODUCT and bytes.fromhex(CITRINE_APP_SHA256) in loader:
            template = CITRINE_TEMPLATE
        if product == LINK_PRODUCT and bytes.fromhex(INSTALLED_CITRINE_730_APP_SHA256) in loader:
            template = CITRINE_TEMPLATE
        if product == REFINEMENT_PRODUCT and bytes.fromhex(INSTALLED_CITRINE_731_APP_SHA256) in loader:
            template = CITRINE_TEMPLATE
    expected_slot = {PUBLISHED_TEMPLATE: APP_SLOT, TEST01_TEMPLATE: TEST01_APP_SLOT, CITRINE_TEMPLATE: TEST01_APP_SLOT}.get(template)
    if expected_slot is None or slot != expected_slot:
        raise ValueError("Unsupported package template/app slot")
    _, layout = app_layout(flash[0x4000:], expected_slot)
    app = bytes(region[0x120:0x120+slot])
    # Rebuild enforces every nested JLFS CRC/descriptor, SDK asset and protected-head byte.
    if flash_image(app, KEY, template) != flash:
        raise ValueError("Flash image does not match canonical FMER map and SDK bytes")
    transition = transition_profile(product, template, loader)
    if product != PRODUCT:
        if ((transition["loader_identity"] + "\0").encode("ascii") not in loader or
                bytes.fromhex(transition["origin_app_sha256"]) not in loader):
            raise ValueError(f"{product} loader identity or admitted-origin fingerprint is missing")
        if (product + "\0").encode("ascii") not in app:
            raise ValueError(f"{product} application identity is missing")
    loader_hash = hashlib.sha256(loader).hexdigest()
    qualification = ROOT / "firmware/fm1/loader" / ("CITRINE_QUALIFICATION.json" if template == CITRINE_TEMPLATE else "QUALIFICATION.json")
    report_sha = CITRINE_REPORT_SHA256 if template == CITRINE_TEMPLATE else TEST01_REPORT_SHA256
    dump_sha = CITRINE_DUMP_SHA256 if template == CITRINE_TEMPLATE else TEST01_DUMP_SHA256
    qualified = False
    if qualification.is_file():
        review = json.loads(qualification.read_text(encoding="utf-8"))
        qualified = (review.get("runtime_preflight_qualified") is True and review.get("loader_sha256") == loader_hash
                     and review.get("package_sha256") == hashlib.sha256(raw).hexdigest()
                     and review.get("template") == template
                     and (review.get("origin_app_sha256") or review.get("stock_app_reference_sha256")) == transition["origin_app_sha256"])
        if product != PRODUCT and any(review.get(key) != value for key, value in transition.items()):
            qualified = False
        if product != PRODUCT and (review.get("schema") != 3 or review.get("product") != product):
            qualified = False
        if product != PRODUCT and review.get("reference_backup_report_sha256") != report_sha:
            qualified = False
        if template in (TEST01_TEMPLATE, CITRINE_TEMPLATE) and review.get("reference_backup_sha256") != dump_sha:
            qualified = False
        for item in review.get("source_files", []):
            source = (ROOT/item["path"]).resolve()
            if not source.is_relative_to(ROOT) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
                qualified = False
        if not review.get("source_files"):
            qualified = False
    return {"product": product, "logical_bytes": len(logical), "package_sha256": hashlib.sha256(raw).hexdigest(),
            "app_sha256_padded": hashlib.sha256(app).hexdigest(), "loader_sha256": hashlib.sha256(loader).hexdigest(),
            "loader_image_bytes": len(loader), "runtime_preflight_qualified": qualified,
            "stock_app_reference_sha256": TEST01_APP_SHA256 if template in (TEST01_TEMPLATE, CITRINE_TEMPLATE) else STOCK_APP_SHA256,
            **transition, "raw_app_sha256": hashlib.sha256(flash[0x4000:]).hexdigest(),
            "template": template, "template_layout": layout, "stock_calibration_preserved": True,
            "reference_backup_sha256": dump_sha if template in (TEST01_TEMPLATE, CITRINE_TEMPLATE) else None,
            "reference_backup_report_sha256": report_sha if template in (TEST01_TEMPLATE, CITRINE_TEMPLATE) else None,
            "protected_head_preserved_from_backup": template in (TEST01_TEMPLATE, CITRINE_TEMPLATE),
            "allowed_raw_flash_changes": [[0x4000, 0x4004], [0x4020, 0x4024], [0x4120, 0x4120+slot]],
            "files": {name: {k: v for k, v in f.items() if k != "payload"} for name, f in files.items()},
            "app_write_range": [0x4000, 0x93000], "head_written": False,
            "target_executed": False, "hardware_qualified": False}


def build_loader(output: Path, toolchain: Path, lock: dict, template=TEST01_TEMPLATE, *, stock_v15=False, portable=False) -> bytes:
    import target_probe
    target_probe.verify_files(toolchain, lock["toolchain"]["files"])
    source = ROOT / "firmware/fm1/loader"
    output.mkdir(parents=True, exist_ok=False)
    compiler = str(toolchain / "bin/clang.exe")
    flags = [compiler, "-target", "pi32v2", "-mcpu=r3", "-Os", "-fno-common", "-ffunction-sections",
             "-fdata-sections", "-fno-builtin", "-Wall", "-Wno-unused-function", "-D__GCC_PI32V2__",
             "-resource-dir", str(toolchain / "lib/clang/4.0.1"), "-isystem", str(toolchain / "pi32v2-include"),
             "-I", str(source / "hal")]
    if portable:
        flags.append("-DFMER_PORTABLE_INSTALL=1")
    if stock_v15:
        if template != CITRINE_TEMPLATE:
            raise ValueError('Stock loader requires the reviewed V15 layout')
        flags.append("-DFMER_CITRINE_STOCK=1")
    elif template == CITRINE_TEMPLATE:
        flags.append("-DFMER_CITRINE_733=1")
    commands = []

    def run(name, command):
        result = target_probe.run_logged(command, output / (name+".json"))
        commands.append({"log": name+".json", "exit_code": result["exit_code"]})
        if result["exit_code"] != 0:
            raise ValueError("Loader build failed: "+str(output / (name+".json")))
        return result

    for stem, suffix in [("crt0_ldr", ".S"), ("loader", ".c")]:
        run(stem, flags+["-c", str(source/(stem+suffix)), "-o", str(output/(stem+".o"))])
    elf = output / "loader.elf"
    run("link", [str(toolchain/"bin/pi32v2-ld.exe"), "-m", "elf32pi32v2", "--gc-sections", "-e", "_start",
                 "-T", str(source/"loader.ld"), "-Map", str(output/"loader.map"), "-o", str(elf),
                 str(output/"crt0_ldr.o"), str(output/"loader.o")])
    if run("undefined", [str(toolchain/"bin/llvm-nm.exe"), "--undefined-only", str(elf)])["stdout"].strip():
        raise ValueError("Loader has unresolved symbols")
    image, report = extract_elf(elf.read_bytes(), "loader")
    wrapped = loader_wrap(image)
    (output/"loader.bin").write_bytes(image)
    (output/"ota.bin").write_bytes(wrapped)
    report.update(commands=commands, elf_sha256=target_probe.sha256(elf), image_sha256=hashlib.sha256(image).hexdigest(),
                  ota_sha256=hashlib.sha256(wrapped).hexdigest(), target_executed=False,
                  source_files=[{"path": p.relative_to(ROOT).as_posix(), "sha256": target_probe.sha256(p)}
                                for p in sorted(source.rglob("*")) if p.is_file() and not p.name.endswith("QUALIFICATION.json")])
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return wrapped


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build and validate an FMER candidate package; never contacts a device")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--app-elf", type=Path)
    modes.add_argument("--validate", type=Path)
    modes.add_argument("--loader-only", action="store_true")
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    parser.add_argument("--toolchain-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--template", choices=(PUBLISHED_TEMPLATE, TEST01_TEMPLATE, CITRINE_TEMPLATE), default=None)
    parser.add_argument("--product", choices=SUPPORTED_PRODUCTS, default=REFINEMENT_PRODUCT)
    args = parser.parse_args(argv)
    global SDK
    SDK = args.sdk.resolve()
    report = {"success": False, "device_opened": False, "device_writes": False,
              "hardware_qualified": False, "created_utc": datetime.now(timezone.utc).isoformat()}
    output = None
    try:
        for rel in SDK_SHA256:
            sdk_file(rel)
        if args.validate:
            report.update(validate_package(args.validate.read_bytes(), args.template), success=True)
        else:
            if args.app_elf and args.product != REFINEMENT_PRODUCT:
                raise ValueError("Current sources build733 only; retained701..724 packages are validation-only")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")+"-"+uuid.uuid4().hex[:8]
            output = (args.out or ROOT/"artifacts/fm1-package"/stamp).resolve()
            output.mkdir(parents=True, exist_ok=False)
            lock = json.loads((ROOT/"evidence/target-toolchain.json").read_text(encoding="utf-8"))
            toolchain = (args.toolchain_root or ROOT/lock["toolchain"]["local_root"]).resolve()
            ota = build_loader(output/"loader", toolchain, lock, args.template or TEST01_TEMPLATE)
            if args.app_elf:
                app, app_report = extract_elf(args.app_elf.read_bytes(), "app")
                template = args.template or TEST01_TEMPLATE
                raw = ufw(flash_image(app, KEY, template), ota, args.product)
                report.update(validate_package(raw, template), app_elf=str(args.app_elf.resolve()), app=app_report,
                              app_elf_sha256=hashlib.sha256(args.app_elf.read_bytes()).hexdigest())
                (output/"app.bin").write_bytes(app)
                (output/"fmer-candidate.fwsc").write_bytes(raw)
            report.update(success=True, output=str(output), sdk_sha256=SDK_SHA256,
                          toolchain_lock_sha256=hashlib.sha256((ROOT/"evidence/target-toolchain.json").read_bytes()).hexdigest())
    except (OSError, ValueError, KeyError, struct.error) as error:
        report["error"] = str(error)
    if output and output.is_dir():
        (output/"report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


