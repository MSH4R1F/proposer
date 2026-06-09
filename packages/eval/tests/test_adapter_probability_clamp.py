"""P(landlord) must never contradict the predicted class direction."""
from eval.adapter import _confidence_to_p_landlord


def test_tenant_win_low_confidence_clamps_to_half():
    # Old behaviour: 1 - 0.4 = 0.6 — a landlord-leaning probability on a
    # tenant_wins prediction. Must clamp at 0.5.
    assert _confidence_to_p_landlord("tenant_wins", 0.4) == 0.5


def test_tenant_win_high_confidence_unchanged():
    assert abs(_confidence_to_p_landlord("tenant_wins", 0.9) - 0.1) < 1e-9


def test_landlord_win_low_confidence_clamps_to_half():
    assert _confidence_to_p_landlord("landlord_wins", 0.4) == 0.5


def test_landlord_win_high_confidence_unchanged():
    assert abs(_confidence_to_p_landlord("landlord_wins", 0.9) - 0.9) < 1e-9


def test_split_and_uncertain_stay_half():
    assert _confidence_to_p_landlord("split", 0.8) == 0.5
    assert _confidence_to_p_landlord("uncertain", 0.2) == 0.5
