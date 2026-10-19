# FMER splash artwork

## Ownership and license

On 19 October 2026 the project owner answered the explicit request to distribute
the owner-supplied `FMER SPLASH.png` artwork and its editable source under
GPL-3.0-only with the rest of FMER:

> Yes—I own it; include under GPL-3.0-only

This grant covers that original artwork, its source and generated splash
reproductions in the firmware and documentation. See the root LICENSE for the
full GNU General Public License version 3 text. Retain this notice and attribution
to the FMER project owner. It does not license unrelated artwork, fonts, imported
banks or vendor assets, and does not authorize public publication by itself.

## Source and reproduction

The delivered original is the editable 240 × 240 raster image at the root of the
source tree, `FMER SPLASH.png` (1,615 bytes). No separate layered or vector source
was supplied or is claimed to be included. The PNG is preserved byte-for-byte.

SHA-256: `73697123943ac81da6d294466c0f0d0c1bbee4bbf4c4b2d10d096414766b96f8`

`tools/generate_fm1_visuals.py` converts the PNG into the palette and packed
pixels in `firmware/fm1/splash.h`. Run `python tools/generate_fm1_visuals.py --check`
with Pillow installed to verify the checked-in assets. The script also generates
algorithm diagrams from the separately credited MSFA routing data; this artwork
grant does not change MSFA's license.

The original PNG, generator, generated header, LICENSE and this notice accompany
both Corresponding Source.zip in Companion and the standalone public-source
snapshot. Recording this permission changes no firmware bytes or installed units.
