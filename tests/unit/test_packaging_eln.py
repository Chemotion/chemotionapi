"""The exporter's vendored data files ship in the wheel."""
import json
from pathlib import Path
import chemotion_api


def test_the_vendored_ro_crate_context_is_present_and_parses():
    """`export_eln` compacts against this file so a supposedly offline export makes no network
    call. If it is missing from the distribution the code falls back to the canonical URL and
    rdflib fetches it at export time — silently, from every installed copy."""
    path = Path(chemotion_api.__file__).parent / "data" / "ro-crate-context.jsonld"
    assert path.is_file(), f"{path} is missing; an offline export would fetch the context remotely"
    assert "@context" in json.loads(path.read_text()), "vendored context has no @context key"
