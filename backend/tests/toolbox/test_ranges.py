import pytest

from app.toolbox.storage.media import byte_range


@pytest.mark.parametrize(("header", "expected"), [(None, None), ("bytes=0-9", (0, 9)), ("bytes=99-", (99, 99)), ("bytes=-8", (92, 99)), ("bytes=-999", (0, 99)), ("bytes=4-999", (4, 99))])
def test_valid_ranges(header, expected):
    assert byte_range(header, 100) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=9-4", "bytes=-0", "bytes=-", "bytes=0-1,3-5", "items=0-3", "bytes=oops", "bytes=0-" + "9" * 5000])
def test_invalid_ranges(header):
    with pytest.raises(ValueError):
        byte_range(header, 100)
