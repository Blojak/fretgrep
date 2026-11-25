"""Tests for the logo."""
# pylint: disable=missing-function-docstring

from pathlib import Path

from fretgrep import banner

LOGO = Path(__file__).parents[1] / "docs" / "logo.svg"


def test_readme_logo_is_up_to_date():
    # After changing the logo: python -c "from fretgrep import banner;
    # open('docs/logo.svg', 'w').write(banner.svg())"
    assert LOGO.read_text(encoding="utf-8") == banner.svg()


def test_svg_keeps_text_and_colours():
    image = banner.svg()

    assert image.count("<text ") == 6
    assert '<tspan class="match">●</tspan>' in image
    assert banner.TAGLINE in image and "\033" not in image
