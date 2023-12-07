def test_add_segment(instance_with_test_samples):
    sample = instance_with_test_samples['main_collection'].get_samples()[-1]
    e_q_d = sample.segments.get('ApiTester')
    e_q_d['One']['Text'] = '10'
    sample.save()

    sample_test = instance_with_test_samples['instance'].get_sample(sample.id)
    assert '10' == sample_test.segments.get('ApiTester')['One']['Text']