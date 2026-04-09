from app.link_extractor import extract_lodging_links


def test_extract_lodging_links_filters_supported_domains() -> None:
    text = (
        "看一下 https://www.booking.com/hotel/jp/test.html "
        "跟 https://www.agoda.com/zh-tw/test-hotel/hotel/tokyo-jp.html，"
        "還有 https://www.airbnb.com/rooms/123456789?check_in=2026-04-10，"
        "這個 https://example.com/ignore 不用收。"
    )

    matches = extract_lodging_links(
        text,
        ("booking.com", "agoda.com", "airbnb.com"),
    )

    assert [match.platform for match in matches] == ["booking", "agoda", "airbnb"]
    assert [match.hostname for match in matches] == [
        "booking.com",
        "agoda.com",
        "airbnb.com",
    ]


def test_extract_lodging_links_accepts_airbnb_tw_hostname() -> None:
    text = "看這間 https://www.airbnb.com.tw/rooms/1501215477047936529?check_in=2026-06-01"

    matches = extract_lodging_links(text, ("airbnb.com",))

    assert [match.platform for match in matches] == ["airbnb"]
    assert [match.hostname for match in matches] == ["airbnb.com.tw"]
