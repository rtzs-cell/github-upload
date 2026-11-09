import numpy as np

from sionna_radar.cir_noise import inject_complex_awgn


def test_disabled_noise_is_bitwise_unchanged() -> None:
    values = np.ones((2, 4, 1), dtype=np.complex64)
    valid = np.ones((2, 4), dtype=bool)
    noisy, summary = inject_complex_awgn(values, valid, enabled=False)
    np.testing.assert_array_equal(noisy, values)
    assert summary["enabled"] is False


def test_awgn_is_reproducible_and_hits_requested_snr() -> None:
    values = np.ones((4, 512), dtype=np.complex64)
    valid = np.ones((4, 512), dtype=bool)
    first, first_summary = inject_complex_awgn(values, valid, enabled=True, snr_db=15.0, seed=77)
    second, second_summary = inject_complex_awgn(values, valid, enabled=True, snr_db=15.0, seed=77)
    np.testing.assert_array_equal(first, second)
    assert first_summary == second_summary
    assert abs(first_summary["realized_snr_db"] - 15.0) < 0.5
    assert not np.array_equal(first, values)


def test_awgn_does_not_touch_invalid_entries() -> None:
    values = np.ones((2, 3), dtype=np.complex64)
    valid = np.asarray([[True, False, True], [False, True, False]])
    noisy, _ = inject_complex_awgn(values, valid, enabled=True, snr_db=10.0, seed=3)
    np.testing.assert_array_equal(noisy[~valid], values[~valid])
