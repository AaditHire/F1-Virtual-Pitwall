"""Package-level smoke tests."""

import f1_pitwall


def test_package_is_importable() -> None:
    """The installed source package can be imported."""
    assert f1_pitwall.__doc__ == "F1 Virtual Pit Wall."
