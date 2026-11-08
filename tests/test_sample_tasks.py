"""Sample tasks on a live ELN (M5.5).

The stack's production config switches weighing tasks off (``ui_components.yml``), so this checks
that the client reports that clearly, and runs the whole flow only where the feature is on.
"""
import pytest

pytestmark = pytest.mark.integration


def test_weighing_task(instance_with_collection, tmp_path):
    instance = instance_with_collection['instance']
    try:
        instance.sample_tasks()
    except ConnectionError as e:
        assert 'not enabled' in str(e)
        pytest.skip('weighing_tasks is disabled on this ELN')
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.save()
    task = instance.create_sample_task(sample, 'weigh it', 1)
    scan = tmp_path / 'scale.png'
    scan.write_bytes(b'\x89PNG\r\n\x1a\n')
    task.add_scan_result(str(scan), 1.5, 'g')
    assert task.id in {t.id for t in instance.sample_tasks('done')}
