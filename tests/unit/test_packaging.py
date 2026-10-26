"""Guards for things that only break once the package is installed from a wheel."""
import json
from pathlib import Path

import chemotion_api




def test_empty_element_templates_are_present():
    """Same class of failure: data files the runtime reads, which a packaging change can drop."""
    base = Path(chemotion_api.__file__).parent / "elements" / "empty_elements"
    for name in ("sample.json", "reaction.json", "container.json", "analyses.json"):
        assert (base / name).is_file(), f"{name} is missing from the installed package"
