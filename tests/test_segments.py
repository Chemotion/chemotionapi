def test_add_segment(instance_with_test_samples):
    sample = instance_with_test_samples['main_collection'].get_samples()[0]
    e_q_d = sample.segments.get('Enzyme quality data')
    e_q_d['Required data for all enzyme functional data']['Number of independent experiments'] = 10
    sample.save()

    sample_test = instance_with_test_samples['instance'].get_sample(sample.id)
    assert 10 == sample_test.segments.get('Enzyme quality data')['Required data for all enzyme functional data']['Number of independent experiments']