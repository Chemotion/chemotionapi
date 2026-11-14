"""Attachment management on a live ELN (M3.4)."""
import pytest

from chemotion_api.elements.attachments import delete_attachments, load_files, load_thumbnails

pytestmark = pytest.mark.integration


@pytest.fixture()
def dataset_file(instance_with_collection, tmp_path):
    col = instance_with_collection['main_collection']
    path = tmp_path / 'spectrum.txt'
    path.write_text('x,y\n1,2\n')
    sample = col.new_sample_smiles('CCO')
    sample.analyses.add_analyses('NMR').add_dataset(str(path))
    sample.save()
    sample.load()
    return instance_with_collection['instance'], sample, sample.analyses.by_name('NMR').datasets[0].attachments[0]


def test_bulk_reads(dataset_file):
    instance, _, att = dataset_file
    assert load_files(instance._con, [att]) == {att['id']: b'x,y\n1,2\n'}
    assert load_thumbnails(instance._con, [att]) == {att['id']: None}
    assert att.load_thumbnail() is None
    with pytest.raises(ValueError, match='cannot be shown as an image'):
        att.load_image()


def test_unlink_moves_the_file_to_the_inbox_then_delete(dataset_file):
    instance, sample, att = dataset_file
    att.unlink()
    assert att['id'] in {a['id'] for a in instance.inbox.unlinked_attachments()}
    sample.load()
    assert sample.analyses.by_name('NMR').datasets[0].attachments.attachment_data == []
    assert delete_attachments(instance._con, [att]) == [att['id']]
    assert att['id'] not in {a['id'] for a in instance.inbox.unlinked_attachments()}
