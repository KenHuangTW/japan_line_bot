from app.link_extractor import extract_lodging_links


def test_extract_lodging_links_filters_supported_domains() -> None:
    text = (
        "看一下 https://www.booking.com/hotel/jp/test.html "
        "跟 https://www.agoda.com/zh-tw/test-hotel/hotel/tokyo-jp.html，"
        "這個 https://example.com/ignore 不用收。"
    )

    matches = extract_lodging_links(text, ("booking.com", "agoda.com"))

    assert [match.platform for match in matches] == ["booking", "agoda"]
    assert [match.hostname for match in matches] == ["booking.com", "agoda.com"]
