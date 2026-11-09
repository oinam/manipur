from manipur.tile import pyramid_version


def test_pyramid_version_follows_the_frame_bytes(tmp_path):
    frame = tmp_path / "000_000.png"
    frame.write_bytes(b"first")
    first = pyramid_version([frame], 1)
    assert pyramid_version([frame], 1) == first
    assert pyramid_version([frame], 2) != first
    frame.write_bytes(b"second")
    assert pyramid_version([frame], 1) != first
