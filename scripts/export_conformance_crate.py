"""Export a fixture `.eln` crate for the conformance check. Needs no Chemotion server.

Stage one of the two-stage conformance job: this runs in the project environment (Python 3.14)
and writes a crate; `check_crate_conformance.py` then validates it in a separate 3.13 environment,
because rocrate-validator's dependencies cannot build on 3.14.

usage: export_conformance_crate.py <output.eln>
"""
import shutil
import sys
import tempfile
from pathlib import Path

from chemotion_api import Author, AuthorAffiliation
from chemotion_api.offline import import_export_zip

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "mini_export.json"


def main(out_path: str) -> int:
    workdir = Path(tempfile.mkdtemp())
    try:
        # The offline ingester reads a Chemotion export dump, so a committed fixture stands in for
        # a live server. It carries samples and reactions, which is what exercises the
        # chem-dcat-ap mapping — the part of the pipeline that produces the JSON-LD shapes the
        # RO-Crate profile constrains.
        export_dir = workdir / "export"
        export_dir.mkdir()
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
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
