def test_get_reaction_success(instance_with_test_samples: dict):

    # fetching the sample must succeed (return value itself is not inspected)
    instance_with_test_samples['instance'].get_sample(instance_with_test_samples.get('sample_ids')[0])