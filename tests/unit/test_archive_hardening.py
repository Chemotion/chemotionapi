"""Archive-handling hardening found by the pre-release security review.

Common thread: a guard existed, but only on one of the several code paths that needed it, or it
was written more loosely than its own comment claimed.
"""
import io
import json
import os
import zipfile

import pytest

from chemotion_api.offline.export_reader import (
    MAX_COMPRESSION_RATIO, MAX_ZIP_MEMBER_SIZE, ExportArchive)

DUMP = {"Sample": {"s1": {"name": "A"}},
        "Attachment": {"a1": {"identifier": "ab12cd", "filename": "real.png",
                              "attachable_id": "c1"}}}


def _zip(tmp_path, members, name="export.zip"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as z:
        for member, data in members.items():
            z.writestr(member, data)
    return path


def test_nested_attachments_decoy_is_ignored(tmp_path):
    """`parts[-2] == "attachments"` matched at ANY depth, so `docs/attachments/ab12cd.png`
    shadowed the genuine `attachments/ab12cd.png`; which won came down to central-directory
    order, which whoever wrote the archive controls. The swapped bytes then get a correct
    sha256, so the crate's own integrity data would certify the swap."""
    archive = _zip(tmp_path, {
        "docs/attachments/ab12cd.png": b"DECOY",
        "export.json": json.dumps(DUMP),
        "attachments/ab12cd.png": b"REAL",
    })
    ea = ExportArchive(archive)
    assert ea.read_attachment("ab12cd") == b"REAL"
    assert b"".join(ea.iter_attachment("ab12cd")) == b"REAL"
    ea.close()


def test_attachments_are_found_beside_a_nested_export_json(tmp_path):
    """A real archive may be wrapped in one root folder; attachments sit beside export.json."""
    archive = _zip(tmp_path, {
        "wrapper/export.json": json.dumps(DUMP),
        "wrapper/attachments/ab12cd.png": b"REAL",
        "wrapper/deeper/attachments/ab12cd.png": b"DECOY",
    })
    ea = ExportArchive(archive)
    assert ea.read_attachment("ab12cd") == b"REAL"
    ea.close()


def test_nested_export_json_decoy_loses_to_the_shallower_one(tmp_path):
    """The comment claimed the same shallowest-wins tiebreak as the other two locators; it was
    raw namelist() order, which the archive author picks."""
    archive = _zip(tmp_path, {
        "payload/export.json": json.dumps({"Sample": {"evil": {"name": "DECOY"}}}),
        "export.json": json.dumps(DUMP),
    })
    ea = ExportArchive(archive)
    assert list(ea.export_data["Sample"]) == ["s1"]
    ea.close()


def _bomb_zip(tmp_path, member, ratio_bytes=64 * 1024 * 1024):
    path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("export.json", json.dumps(DUMP))
        z.writestr(member, b"\0" * ratio_bytes)      # compresses ~1000x
    return path


def test_iter_attachment_enforces_the_same_limits_as_read_attachment(tmp_path):
    """`iter_attachment` had NO cap — and it is the path `export_eln` takes for every offline
    attachment, since `_write_crate_zip_inner` prefers `iter_file()`. Streaming bounds memory,
    not the bytes written into the output crate."""
    archive = _bomb_zip(tmp_path, "attachments/ab12cd.png")
    ea = ExportArchive(archive)
    with pytest.raises(ValueError, match="above the .* limit"):
        b"".join(ea.iter_attachment("ab12cd"))
    ea.close()


def test_read_attachment_still_refuses_the_bomb(tmp_path):
    archive = _bomb_zip(tmp_path, "attachments/ab12cd.png")
    ea = ExportArchive(archive)
    with pytest.raises(ValueError, match="above the .* limit"):
        ea.read_attachment("ab12cd")
    ea.close()


def test_ontology_patch_refuses_a_bomb_in_the_metadata(tmp_path):
    """The third ZIP reader in the package, and the only one that stayed unguarded."""
    from chemotion_api.ontology_patch import patch_eln_ontology

    path = tmp_path / "bomb.eln"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("crate/ro-crate-metadata.json",
                   json.dumps({"@graph": [{"@id": "x", "pad": "A" * (64 * 1024 * 1024)}]}))
    with pytest.raises(ValueError, match="above the .* limit|exceeding the"):
        patch_eln_ontology(str(path), {"sample": "http://example.org/S"},
                           output_path=str(tmp_path / "out.eln"))


def test_crate_directory_read_is_size_capped(tmp_path, monkeypatch):
    """The ZIP branch was capped; the extracted-directory branch was a bare read_bytes()."""
    import chemotion_api.offline.eln_reader as mod

    crate = tmp_path / "crate"
    crate.mkdir()
    (crate / "ro-crate-metadata.json").write_text(json.dumps({
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [{"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
                    "about": {"@id": "./"}},
                   {"@id": "./", "@type": "Dataset", "name": "C",
                    "hasPart": [{"@id": "big.bin"}]},
                   {"@id": "big.bin", "@type": "File", "name": "big.bin"}]}))
    (crate / "big.bin").write_bytes(b"x" * 4096)

    monkeypatch.setattr(mod, "MAX_ZIP_MEMBER_SIZE", 1024)
    with mod.ElnCrate(crate) as opened:
        with pytest.raises(ValueError, match="exceeding the"):
            opened.read_file("big.bin")


def test_crate_directory_does_not_follow_symlinks_out_of_the_crate(tmp_path):
    """rglob descends through symlinked directories, so a crate could enumerate — and then hand
    a caller the bytes of — files outside itself."""
    import chemotion_api.offline.eln_reader as mod

    secret_dir = tmp_path / "outside"
    secret_dir.mkdir()
    (secret_dir / "id_rsa").write_text("PRIVATE KEY")

    crate = tmp_path / "crate"
    crate.mkdir()
    (crate / "ro-crate-metadata.json").write_text(json.dumps({
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [{"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
                    "about": {"@id": "./"}},
                   {"@id": "./", "@type": "Dataset", "name": "C"}]}))
    try:
        (crate / "payload").symlink_to(secret_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    with mod.ElnCrate(crate) as opened:
        assert not any("id_rsa" in m for m in opened._members)
