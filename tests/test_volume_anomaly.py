from ingestion.volume_anomaly import evaluate

NORMAL_WEEK = [372, 370, 316, 289, 256, 188, 197]


def test_spike_is_flagged():
    result = evaluate(1168, NORMAL_WEEK)
    assert result["status"] == "fail"
    assert result["ratio_to_median"] > 4


def test_drop_is_flagged():
    assert evaluate(60, NORMAL_WEEK)["status"] == "fail"


def test_normal_day_passes():
    assert evaluate(300, NORMAL_WEEK)["status"] == "pass"


def test_statistically_odd_but_small_change_passes():
    # very stable week -> tiny MAD -> high z-score, but +32% is not worth an alert
    stable = [288, 322, 311, 302, 314, 243, 276]
    result = evaluate(400, stable)
    assert abs(result["robust_z"]) > 3.5
    assert result["status"] == "pass"


def test_missing_days_are_not_treated_as_zero_sales():
    with_gap = [372, 0, 316, 289, 0, 188, 197]
    assert evaluate(300, with_gap)["status"] == "pass"


def test_not_enough_history_is_skipped():
    assert evaluate(300, [0, 0, 0, 0, 0, 250, 260])["status"] == "skipped"


def test_one_past_anomaly_does_not_mask_the_next():
    # the 1168 spike sits in the baseline; the median keeps the baseline honest
    after_spike = [370, 316, 289, 256, 188, 197, 1168]
    assert evaluate(1100, after_spike)["status"] == "fail"
