"""Static enforcement of AC #2.

The private symbols `_send_rejection_impl`, `_send_offer_impl`, and
`_publish_job_impl` (spec: rejections, offers, external publications) live in
`orchestrator/side_effects.py`. The only module allowed to reference them is
`orchestrator/gates.py`, which verifies a closed, approved `NeedsAttention`
row exists before invoking them.

This test scans every `.py` file under `orchestrator/` and asserts the
invariant. It is the AC #2 test: "no path exists in code where a rejection
email is sent without a validated human gate".
"""

from __future__ import annotations

import ast
from pathlib import Path

SENSITIVE_SYMBOLS = (
    "_send_rejection_impl",
    "_send_offer_impl",
    "_publish_job_impl",
)


def _orchestrator_files() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    root = here / "orchestrator"
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _references_in(path: Path, symbols: tuple[str, ...]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in symbols:
            hits.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in symbols:
            hits.add(node.attr)
        elif isinstance(node, ast.alias) and node.name in symbols:
            hits.add(node.name)
    return hits


def test_sensitive_symbols_only_referenced_from_gates_or_side_effects():
    allowed = {"gates.py", "side_effects.py"}
    for path in _orchestrator_files():
        if path.name in allowed:
            continue
        refs = _references_in(path, SENSITIVE_SYMBOLS)
        assert not refs, (
            f"{path} references sensitive symbol(s) {refs}. "
            f"Sensitive side effects may only be invoked through orchestrator.gates."
        )


def test_gates_module_uses_the_sensitive_symbols():
    """Sanity: the invariant would trivially pass if `gates.py` didn't import them."""
    gates_path = Path(__file__).resolve().parent.parent / "orchestrator" / "gates.py"
    refs = _references_in(gates_path, SENSITIVE_SYMBOLS)
    assert refs == set(SENSITIVE_SYMBOLS), f"gates.py must reference all of {SENSITIVE_SYMBOLS}, saw {refs}"
