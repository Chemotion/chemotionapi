"""Export a fixture `.eln` crate for the conformance check. Needs no Chemotion server.

Stage one of the two-stage conformance job: this runs in the project environment (Python 3.14)
and writes a crate; `check_crate_conformance.py` then validates it in a separate 3.13 environment,
because rocrate-validator's dependencies cannot build on 3.14.

usage: export_conformance_crate.py [--shared] <output.eln>

``--shared`` exports a two-collection variant in which one sample belongs to both collections.
The plain fixture is single-collection, which makes the gate vacuous for everything about
element<->collection membership: with one collection, every shape is trivially consistent.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from chemotion_api import Author, AuthorAffiliation
from chemotion_api.offline import import_export_zip

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "mini_export.json"


def _shared_membership_dump() -> dict:
    """The fixture dump plus join tables putting one sample in two collections.

    Chemotion exports carry ``CollectionsSample``/``CollectionsReaction`` join tables; the offline
    ingester rebuilds one collection per exported collection from them, so a shared sample is
    reached through both -- which is exactly the case the crate has to be able to state.
    """
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["Collection"]["col-shared"] = {"label": "Shared Collection", "ancestry": ""}
    # A *standalone* sample: the fixture's other samples are reaction materials, and a sample
    # covered by an in-scope reaction is not listed as a standalone sample of that collection --
    # so using one of those would have produced a crate with no genuinely shared element.
    data["Sample"]["smp-shared"] = dict(data["Sample"]["smp-sm"], name="Shared Sample")
    data["CollectionsSample"] = {
        "cs-1": {"collection_id": "col-1", "sample_id": "smp-sm"},
        "cs-2": {"collection_id": "col-1", "sample_id": "smp-shared"},
        "cs-3": {"collection_id": "col-shared", "sample_id": "smp-shared"},
    }
    data["CollectionsReaction"] = {"cr-1": {"collection_id": "col-1", "reaction_id": "rxn-1"}}
    return data


def main(out_path: str, shared: bool = False) -> int:
    workdir = Path(tempfile.mkdtemp())
    try:
        # The offline ingester reads a Chemotion export dump, so a committed fixture stands in for
        # a live server. It carries samples and reactions, which is what exercises the
        # chem-dcat-ap mapping — the part of the pipeline that produces the JSON-LD shapes the
        # RO-Crate profile constrains.
        export_dir = workdir / "export"
        export_dir.mkdir()
        if shared:
            (export_dir / "export.json").write_text(
                json.dumps(_shared_membership_dump()), encoding="utf-8")
        else:
            shutil.copyfile(FIXTURE, export_dir / "export.json")

        collection = import_export_zip(export_dir)
        collection.export_eln(
            out_path,
            authors=[Author(
                name="Conformance Fixture",
                orcid="0000-0002-1825-0097",
                affiliations=[AuthorAffiliation(
                    name="Example University", ror="https://ror.org/05dxps055")],
            )],
            # No network in CI, and the embedded CHMO codes are what we want to exercise anyway.
            ontology_lookup=False,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    written = Path(out_path)
    if not written.is_file() or written.stat().st_size == 0:
        print(f"ERROR: no crate written to {out_path}", file=sys.stderr)
        return 1
    print(f"exported {out_path} ({written.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    shared_flag = "--shared" in args
    args = [a for a in args if a != "--shared"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(args[0], shared=shared_flag))
