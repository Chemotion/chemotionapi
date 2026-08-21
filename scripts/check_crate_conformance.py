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
* **rocrate-validator reports no REQUIRED issues** against the `ro-crate-1.1` profile.

usage: check_crate_conformance.py <crate.eln>
"""
import sys
import tempfile
import zipfile
from pathlib import Path


def _extract(eln_path: Path, into: Path) -> Path:
    with zipfile.ZipFile(eln_path) as archive:
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
            profile_identifier="ro-crate-1.1",
            requirement_severity=models.Severity.REQUIRED,
        ))
        if result.has_issues():
            print("FAIL  rocrate-validator reported REQUIRED issues:")
            for issue in result.get_issues():
                print(f"          [{issue.severity.name}] {issue.check.identifier}: {issue.message}")
            failures.append("rocrate-validator")
        else:
            print("PASS  rocrate-validator: no REQUIRED issues (profile ro-crate-1.1)")

    if failures:
        print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\nRO-Crate 1.1 conformance: OK")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
