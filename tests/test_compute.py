"""Compute tasks and predictions on a live ELN (M5.4).

The stack configures no compute or inference server, and NMR simulation would send structures to
nmrdb.org, so only what the ELN answers by itself is checked here: the seeded compute tasks, and the
errors when the services are missing.
"""
import pytest

pytestmark = pytest.mark.integration


def test_compute_tasks_without_a_compute_server(instance_with_collection):
    instance = instance_with_collection['instance']
    tasks = instance.compute_tasks()
    assert all(t.id and t.status for t in tasks)
    if tasks:
        with pytest.raises(ConnectionError):
            tasks[0].check()
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.save()
    with pytest.raises(PermissionError):
        instance.submit_compute_task(sample)


def test_prediction_fails_on_eln_main(logged_in_instance):
    with pytest.raises(ConnectionError):
        logged_in_instance.predict_products(['CCO'])
