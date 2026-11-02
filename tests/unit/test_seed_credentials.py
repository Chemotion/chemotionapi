"""The committed test seed must stay a fixture of this repository alone.

`tests/data/test.sql` seeds the integration stack. Its password hashes are pinned here so that
replacing the seed is always a deliberate, reviewed act rather than something that happens as a
side effect of a backup or a stack upgrade. No network, no server, no fixtures.

What it deliberately does *not* object to: the seed's documented plaintexts for `api@kit.edu`,
`admin@kit.edu` and `eln-admin@kit.edu`, and the matching `ELN_PASS`/`ELN_ADMIN_PASS` in
`tests/config.json.sample`. Those are preserved on purpose and unlock nothing outside a
developer's throwaway docker stack.

Why a fingerprint rather than comparing against the dumps: `tests/data/dumps/` is gitignored and
in practice holds dumps taken *from our own seeded stack*, which share the seed's hashes by
definition. Comparing against those reports a problem on every developer machine that has ever
run a backup. Pinning the hash set catches the thing that matters — the seed changing — with no
false positives.

If this test fails, do not update the fingerprint to make it pass until you know where the new
seed came from.
"""
import hashlib
import re
from pathlib import Path

import pytest

_SEED = Path(__file__).resolve().parents[1] / "data" / "test.sql"

#: bcrypt, as PostgreSQL stores it in `users.encrypted_password`.
_BCRYPT = re.compile(r"\$2[aby]\$[0-9]+\$[A-Za-z0-9./]{53}")

#: sha256 over the seed's sorted, de-duplicated hash set. Safe to commit: it is a fingerprint of
#: *which* credentials the seed carries and discloses none of them.
#:
#: Updating this constant is the point — it cannot happen by accident. If you regenerate the seed,
#: re-derive it and satisfy yourself the new hashes came from a throwaway database:
#:
#:     python -c "import hashlib,re,pathlib; \
#:       h=sorted(set(re.findall(r'[$]2[aby][$][0-9]+[$][A-Za-z0-9./]{53}', \
#:       pathlib.Path('tests/data/test.sql').read_text()))); \
#:       print(hashlib.sha256('\n'.join(h).encode()).hexdigest())"
_EXPECTED_FINGERPRINT = "d39760234cbcde287062781be978d8831ab829a311c7cc5b0104bf1fc45d4b29"
_EXPECTED_COUNT = 9


@pytest.mark.skipif(not _SEED.is_file(), reason="no seed in this tree")
def test_the_seed_carries_exactly_the_credentials_we_re_salted():
    """Any change to the seed's password hashes has to be a conscious one."""
    hashes = sorted(set(_BCRYPT.findall(_SEED.read_text(encoding="utf-8", errors="replace"))))
    digest = hashlib.sha256("\n".join(hashes).encode()).hexdigest()
    assert len(hashes) == _EXPECTED_COUNT, (
        f"the seed now has {len(hashes)} password hashes, not {_EXPECTED_COUNT}"
    )
    assert digest == _EXPECTED_FINGERPRINT, (
        "tests/data/test.sql's password hashes changed. If you regenerated the seed, confirm the "
        "new hashes did not come from a real instance, then update _EXPECTED_FINGERPRINT. "
        "See this module's docstring for why that matters."
    )
