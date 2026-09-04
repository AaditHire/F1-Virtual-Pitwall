from f1_pitwall.radio import RadioCategory, classify_radio


def test_radio_classifier_finds_multiple_signals() -> None:
    signal = classify_radio("Box now, rain expected and traffic at pit exit")
    assert RadioCategory.STRATEGY in signal.categories
    assert RadioCategory.WEATHER in signal.categories
    assert RadioCategory.TRAFFIC in signal.categories


def test_radio_classifier_has_other_fallback() -> None:
    assert classify_radio("Copy that").categories == (RadioCategory.OTHER,)
