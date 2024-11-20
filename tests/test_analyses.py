import os.path

from chemotion_api import Instance


def test_analyses(instance_with_test_samples: dict):
    instance: Instance = instance_with_test_samples['instance']
    sample_id: int = instance_with_test_samples['sample_ids'][0]
    s = instance.get_sample(sample_id)
    ana = s.analyses
    ana.add_analyses('T1')
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    ana.add_analyses('T2').add_dataset(os.path.join(data_dir, 'SG-V3545-6-13.cif'))
    s.save()

    s = instance.get_sample(sample_id)
    ana = s.analyses

    d1 = ana.by_name('T2').dataset_by_name('SG-V3545-6-13.cif')
    os.makedirs('./TO_DEL', exist_ok=True)
    assert [a['filename'] for a in d1.attachments] == ['SG-V3545-6-13.cif']