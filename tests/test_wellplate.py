import pytest
from requests import RequestException




@pytest.fixture()
def instance_with_test_wellplate(instance_with_test_samples):
    wp = instance_with_test_samples['main_collection'].new_wellplate()
    wp.properties['name'] = 'Api Test WP'
    wp.save()
    yield instance_with_test_samples | {
        'wp': wp
    }

def test_get_wellplate_success(instance_with_test_wellplate: dict):
    wp = instance_with_test_wellplate['instance'].get_wellplate(instance_with_test_wellplate['wp'].id)
    assert wp.properties['name'] == 'Api Test WP'


def test_set_wellplate_success(instance_with_test_wellplate: dict):
    wp = instance_with_test_wellplate['wp']
    logged_in_instance = instance_with_test_wellplate['instance']
    s1 = logged_in_instance.get_sample(instance_with_test_wellplate.get('sample_ids')[0])
    s2 = logged_in_instance.get_sample(instance_with_test_wellplate.get('sample_ids')[1])
    wp.wells[0]['A'] = s2
    wp.wells[0]['b'] = s1
    wp.wells[1]['b'] = s1

    wp.save()

    new_id = wp.json_data['wells'][0]['sample']['id']
    assert new_id != instance_with_test_wellplate.get('sample_ids')[1]
    assert wp.json_data['wells'][12]['sample']['id'] != wp.json_data['wells'][13]['sample']['id']

    wp.wells[0]['A'] = None
    wp.wells[0]['B'] = None
    wp.save()
    with pytest.raises(RequestException) as e:
        logged_in_instance.get_sample(new_id)
