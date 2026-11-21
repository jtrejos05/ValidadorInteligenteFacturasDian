import pytest

from app.rules.nit import nit_check_digit


@pytest.mark.parametrize(
    ("nit", "dv"),
    [
        ("800197268", "4"),  # DIAN's own NIT: 800.197.268-4
        ("899999068", "1"),  # Ecopetrol: 899.999.068-1
        ("860034313", "7"),  # Banco Davivienda: 860.034.313-7
        ("900373115", "3"),
    ],
)
def test_known_check_digits(nit, dv):
    assert nit_check_digit(nit) == dv


@pytest.mark.parametrize("bad", ["", "12A45", "900.373.115", "1234567890123456"])
def test_rejects_invalid_input(bad):
    with pytest.raises(ValueError):
        nit_check_digit(bad)
