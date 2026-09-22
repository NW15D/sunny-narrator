import pytest


@pytest.fixture(autouse=True)
def _reset_length_calibration():
    # Learned length ratios are module-level state; keep tests independent.
    from src.utils import length_calibration
    length_calibration.reset()
    yield
    length_calibration.reset()
