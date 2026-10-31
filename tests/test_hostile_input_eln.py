"""Hostile input aimed at the .eln exporter and the offline ingester.

The server-shape cases that need no exporter stay in test_hostile_input.py."""
import json
import logging
import tempfile
import zipfile
from pathlib import Path
import pytest


def test_a_collection_cycle_does_not_swallow_the_whole_export(tmp_path, caplog):
    """Two collections pointing at each other left `roots` empty, so every element vanished and
    the export still reported success."""
    from chemotion_api.offline import import_export_zip

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "export.json").write_text(json.dumps({
        "Collection": {"col-a": {"label": "A", "ancestry": "col-b"},
                       "col-b": {"label": "B", "ancestry": "col-a"}},
        "CollectionsSample": {"j": {"collection_id": "col-a", "sample_id": "s1"}},
        "Sample": {"s1": {"name": "must not vanish"}},
    }))

    with caplog.at_level(logging.WARNING):
        collection = import_export_zip(export_dir)

    recovered = sum(len(list(c.get_samples())) for c in collection.children)
    assert recovered == 1, "the sample must survive a cycle in the collection ancestry"
    assert "cycle" in caplog.text.lower(), "and the cycle must be reported, not hidden"


def _hostile_crate(directory: Path, names: list[str]) -> Path:
    graph = [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}},
        {"@id": "#ro-crate_created", "@type": "CreateAction", "object": {"@id": "./"},
         "instrument": {"@id": "#p"}},
        {"@id": "#p", "@type": "SoftwareApplication", "name": "chemotion-api"},
        {"@id": "./", "@type": "Dataset",
         "hasPart": [{"@id": f"f{i}.bin"} for i, _ in enumerate(names)]},
    ]
    graph += [{"@id": f"f{i}.bin", "@type": "File", "name": n} for i, n in enumerate(names)]
    path = directory / "hostile.eln"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("hostile.eln/ro-crate-metadata.json",
                   json.dumps({"@context": "https://w3id.org/ro/crate/1.1/context",
                               "@graph": graph}))
        for i, _ in enumerate(names):
            z.writestr(f"hostile.eln/f{i}.bin", b"payload")
    return path


def test_a_crate_cannot_write_outside_the_destination(tmp_path):
    """`ElnFile.extract` wrote to `dest_dir / name` with `name` straight from crate metadata.

    An absolute name made pathlib discard `dest_dir` entirely; `../` was never normalised. Note
    the crate below passes the producer check — that marker is documented and forgeable, so it is
    not a trust boundary.
    """
    from chemotion_api.offline import import_eln

    escape_target = tmp_path / "PWNED_ABS.txt"
    crate_path = _hostile_crate(tmp_path, [str(escape_target), "../../PWNED_REL.txt"])
    out = tmp_path / "out"
    out.mkdir()

    with import_eln(crate_path) as crate:
        assert crate.is_chemotion_api, "the marker is forgeable; the fix must not rely on it"
        for f in crate.root.files:
            written = f.extract(out)
            assert written.parent == out.resolve(), f"{f.name!r} escaped to {written}"

    assert not escape_target.exists(), "no file may be written outside the destination"
    assert not (tmp_path.parent / "PWNED_REL.txt").exists()


def test_a_nested_decoy_cannot_shadow_a_real_attachment(tmp_path):
    """Keyed by basename stem over any path *containing* `attachments/`, a deeper decoy won —
    and its bytes would be exported under the real attachment's name with a matching sha256."""
    from chemotion_api.offline.export_reader import ExportArchive

    archive = tmp_path / "shadow.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("export.json", json.dumps({"Sample": {}}))
        z.writestr("attachments/abc.png", b"REAL")
        z.writestr("nested/attachments/abc.txt", b"SHADOW")

    assert ExportArchive(archive).read_attachment("abc") == b"REAL"


def test_a_zip_bomb_is_refused_by_ratio_not_just_size(tmp_path):
    """A size cap alone is not a defence: 400 MB from a 400 KB archive passes a 500 MiB limit."""
    from chemotion_api.offline.export_reader import ExportArchive

    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("export.json", b'{"Sample":{}}' + b" " * (200 * 1024 * 1024))

    with pytest.raises(ValueError, match="expands"):
        ExportArchive(bomb)._read_json_zip("export.json")


def test_export_json_is_matched_exactly_not_by_suffix(tmp_path):
    """`endswith("export.json")` also matched `evil-export.json`, with namelist order deciding."""
    from chemotion_api.offline.export_reader import ExportArchive

    archive = tmp_path / "decoy.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("evil-export.json", json.dumps({"Sample": {"evil": {"name": "decoy"}}}))
        z.writestr("export.json", json.dumps({"Sample": {"real": {"name": "genuine"}}}))

    assert "real" in ExportArchive(archive)._read_json_zip("export.json")["Sample"]
