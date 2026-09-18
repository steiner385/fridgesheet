"""A QR code as inline SVG, for the LAN address a phone needs.

Server-side and offline on purpose. The text encoded here is the address of the household's
own machine on its own network; handing that to a remote chart service to be drawn would put
it somewhere the spec promises nothing goes (section 8: the server talks only to OneLogin,
Canvas and HAC). Inline SVG also means no image file to write, serve or clean up, and no
client-side code -- this repo has no JavaScript test harness.
"""
from __future__ import annotations

import io

import segno


def svg(text: str, *, size_px: int = 160) -> str:
    """`text` as a QR code: a complete `<svg>` element, sized `size_px` square.

    Raises `ValueError` on empty text -- a blank code scans to nothing, which is a caller's
    bug worth hearing about rather than a blank square on a page.
    """
    if not text:
        raise ValueError("a QR code needs something to encode")
    buf = io.BytesIO()  # segno's SVG writer writes bytes, not str -- a StringIO here raises TypeError
    segno.make(text, error="m").save(
        buf, kind="svg", xmldecl=False, svgns=True, svgclass=None, lineclass=None,
        scale=1, border=4,  # the QR spec's required quiet zone (segno's own default for QR
                             # codes); a camera reading this off a phone in a kitchen, at an
                             # angle, under mixed light, needs that margin -- a bench decode at
                             # a smaller border proves the symbol is valid, not that it is robust.
        omitsize=True,  # no width/height baked into module units; a viewBox is emitted instead,
                         # which is what lets the width/height we add below actually scale the
                         # drawing -- omitsize=False (as one might expect) sizes the element in
                         # modules with no viewBox at all, so replacing that width/height with
                         # size_px would leave the QR drawn tiny in one corner of the box.
    )
    out = buf.getvalue().decode("utf-8")
    return out.replace("<svg ", f'<svg width="{size_px}" height="{size_px}" ', 1)
