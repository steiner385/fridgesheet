"""The QR code the Settings page shows when the LAN toggle is on.

Rendered server-side as inline SVG: there is no JavaScript test harness in this repo, and a
URL naming the household's LAN must never be sent to a remote chart service to be drawn.

`ElementTree.fromstring` below parses only what `qr.svg` just produced, one line earlier, to
assert it is well-formed -- it is never fed untrusted input, so the XXE and entity-expansion
hazards that make `defusedxml` the right default elsewhere do not apply, and adding a test
dependency for a threat model this test does not have would be noise. If this file ever
parses XML from anywhere else, that stops being true.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from fridgesheet import qr


def test_svg_is_a_standalone_element_a_page_can_inline():
    out = qr.svg("http://192.168.1.42:8433/")
    assert out.startswith("<svg") and out.rstrip().endswith("</svg>")
    ET.fromstring(out)                       # parses as XML, so a template can inline it safely
    assert "<script" not in out.lower()


def test_the_svg_scales_to_the_size_asked_for():
    small, large = qr.svg("http://192.168.1.42:8433/", size_px=80), qr.svg("http://192.168.1.42:8433/", size_px=320)
    assert 'width="80"' in small and 'height="80"' in small
    assert 'width="320"' in large and 'height="320"' in large


def test_different_urls_make_different_codes():
    """A cached or hard-coded image would pass every other test in this file."""
    a = qr.svg("http://192.168.1.42:8433/")
    b = qr.svg("http://192.168.1.99:8433/")
    assert a != b


def test_a_long_url_still_encodes():
    """The LAN URL is short, but nothing stops a future caller passing something longer, and
    silently truncating a QR code produces one that scans to the wrong address."""
    out = qr.svg("http://" + "a" * 200 + ".example.org:8433/some/deep/path")
    ET.fromstring(out)


def test_empty_text_is_refused_rather_than_drawn():
    """A blank QR is a code that scans to nothing; the caller has a bug and should hear about it."""
    with pytest.raises(ValueError):
        qr.svg("")


def test_nothing_in_the_svg_reaches_the_network():
    out = qr.svg("http://192.168.1.42:8433/")
    assert not re.search(r"https?://(?!www\.w3\.org)", out), "the SVG must not reference a remote resource"
