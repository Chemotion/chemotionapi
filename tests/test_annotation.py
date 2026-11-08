"""Image annotation on a live ELN (M5.3)."""
import struct
import zlib

import pytest

pytestmark = pytest.mark.integration


def _png(width=4, height=4) -> bytes:
    raw = b''.join(b'\x00' + b'\xff\x00\x00' * width for _ in range(height))

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def test_annotate_an_image(instance_with_collection, tmp_path):
    path = tmp_path / 'tlc.png'
    path.write_bytes(_png())
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.analyses.add_analyses('TLC').add_dataset(str(path))
    sample.save()
    sample.load()
    image = sample.analyses.by_name('TLC').datasets[0].attachments[0]

    svg = image.load_annotation()
    assert f'/api/v1/attachments/image/{image["id"]}' in svg
    image.save_annotation(svg.replace('</svg>', '<rect x="1" y="1" width="2" height="2" stroke="black"/></svg>'))
    assert '<rect' in image.load_annotation()
    assert image.load_image().startswith(b'\x89PNG')


def test_a_text_file_cannot_be_annotated(instance_with_collection, tmp_path):
    path = tmp_path / 'notes.txt'
    path.write_text('x')
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.analyses.add_analyses('notes').add_dataset(str(path))
    sample.save()
    sample.load()
    with pytest.raises(ValueError, match='cannot be annotated'):
        sample.analyses.by_name('notes').datasets[0].attachments[0].load_annotation()
