"""Check that a `.eln` crate conforms to RO-Crate 1.1. Exits non-zero on any violation.

Stage two of the conformance job. Runs in its own environment — deliberately NOT the project's:
roc-validator pulls dependencies that cannot build on Python 3.14, so this is invoked as

    uv run --python 3.13 --no-project --with roc-validator --with rocrate \
        python scripts/check_crate_conformance.py crate.eln

Two independent checks, mirroring what TheELNConsortium's own suite runs
(TheELNFileFormat tests/checks.py) so a crate that passes here passes there:

* **py-rocrate parses it.** A structural smoke test with teeth — it rejects anything that is not
  the flattened, reference-based RO-Crate profile (e.g. `ValueError: no @id in {...}` for a raw
  nested payload).
* **rocrate-validator reports no REQUIRED issues** against the `ro-crate-1.2` profile.

usage: check_crate_conformance.py <crate.eln>
"""
import sys
import tempfile
import zipfile
from pathlib import Path

#: A conformance crate is a few KB; anything near this is a bomb.
MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024  # 512 MiB


def _extract(eln_path: Path, into: Path) -> Path:
    with zipfile.ZipFile(eln_path) as archive:
        # Not zip-slip — CPython strips `..` and drive letters, and zipfile never recreates
        # symlinks — but there is no size accounting, so a bomb crate fills the runner's disk.
        total = sum(i.file_size for i in archive.infolist())
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise SystemExit(
                f"{path} expands to {total} bytes, above the "
                f"{MAX_TOTAL_UNCOMPRESSED}-byte limit; refusing to extract it")
        archive.extractall(into)
    # A conformant .eln has exactly one root folder holding ro-crate-metadata.json.
    roots = [p for p in into.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise SystemExit(f"FAIL  archive must contain exactly one root folder, found {len(roots)}")
    return roots[0]


def main(eln_path: str) -> int:
    crate = Path(eln_path)
    if not crate.is_file():
        print(f"FAIL  no such crate: {crate}", file=sys.stderr)
        return 1

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        crate_dir = _extract(crate, Path(tmp))

        # Two project-specific invariants, asked for in review of PR #1. Neither is an RO-Crate
        # rule, so the validator will not catch a regression in either.
        import json
        metadata = json.loads((crate_dir / "ro-crate-metadata.json").read_text())
        graph = metadata.get("@graph", [])

        # (a) Identifiers stay crate-relative: a leaked server URL makes the archive meaningless
        #     off that server, which defeats the point of exporting it.
        leaked = sorted({
            n["@id"] for n in graph
            if isinstance(n, dict) and isinstance(n.get("@id"), str)
            and "/api/v1/" in n["@id"]
        })
        if leaked:
            print(f"FAIL  absolute API IRIs leaked into the crate: {leaked[:5]}")
            failures.append("crate-relative ids")
        else:
            print("PASS  no absolute API IRIs (identifiers are crate-relative)")

        # (b) Authorship is mandatory for these exports, so the root must actually carry it.
        root = next((n for n in graph if isinstance(n, dict) and n.get("@id") == "./"), {})
        if root.get("author"):
            print("PASS  root dataset declares an author")
        else:
            print("FAIL  root dataset has no author")
            failures.append("authors present")

        from rocrate.rocrate import ROCrate
        try:
            ROCrate(crate_dir)
            print("PASS  py-rocrate parses the crate")
        except Exception as e:
            print(f"FAIL  py-rocrate cannot parse the crate: {type(e).__name__}: {e}")
            failures.append("py-rocrate")

        from rocrate_validator import models, services
        result = services.validate(services.ValidationSettings(
            rocrate_uri=crate_dir,
            profile_identifier="ro-crate-1.2",
            requirement_severity=models.Severity.REQUIRED,
        ))
        if result.has_issues():
            print("FAIL  rocrate-validator reported REQUIRED issues:")
            for issue in result.get_issues():
                print(f"          [{issue.severity.name}] {issue.check.identifier}: {issue.message}")
            failures.append("rocrate-validator")
        else:
            print("PASS  rocrate-validator: no REQUIRED issues (profile ro-crate-1.2)")

    if failures:
        print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\nRO-Crate 1.2 conformance: OK")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
