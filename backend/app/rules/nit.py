"""NIT check digit (dígito de verificación) — DIAN modulo-11 algorithm."""

from __future__ import annotations

from app.models import Finding, Party, Severity
from app.rules.base import RuleContext, finding, rule

_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
NIT_SCHEME = "31"


def nit_check_digit(nit: str) -> str:
    """Compute the DV of a NIT. Weights are applied right-to-left."""
    digits = nit.strip()
    if not digits.isdigit() or len(digits) > len(_WEIGHTS):
        raise ValueError(f"NIT inválido: {nit!r}")
    total = sum(int(d) * w for d, w in zip(reversed(digits), _WEIGHTS, strict=False))
    remainder = total % 11
    return str(remainder if remainder in (0, 1) else 11 - remainder)


def _check_party(party: Party, label: str, code_prefix: str) -> list[Finding]:
    if not party.nit:
        return []  # reported by the structure rule
    if not party.nit.isdigit():
        return [
            finding(
                f"{code_prefix}_NIT_FORMAT",
                Severity.ERROR,
                f"La identificación del {label} debe contener solo dígitos (sin puntos ni DV).",
                field=f"{label}.nit",
                actual=party.nit,
            )
        ]
    if party.id_scheme != NIT_SCHEME:
        return []  # cédulas and other IDs have no check digit
    expected = nit_check_digit(party.nit)
    if party.check_digit != expected:
        return [
            finding(
                f"{code_prefix}_DV_INVALID",
                Severity.ERROR,
                f"El dígito de verificación del NIT del {label} no corresponde.",
                field=f"{label}.check_digit",
                expected=expected,
                actual=party.check_digit,
            )
        ]
    return []


@rule("nit_check_digits")
def check_nits(ctx: RuleContext) -> list[Finding]:
    inv = ctx.invoice
    return _check_party(inv.supplier, "emisor", "SUPPLIER") + _check_party(
        inv.customer, "adquiriente", "CUSTOMER"
    )
