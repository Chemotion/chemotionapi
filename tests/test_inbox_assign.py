"""Inbox assignment on a live ELN (M3.3)."""
import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def inbox_file(logged_in_instance, tmp_path):
    name = f'api_test_{uuid.uuid4().hex[:8]}'
    path = tmp_path / f'{name}.txt'
    path.write_text('1H NMR (400 MHz, CDCl3)')
    logged_in_instance.inbox.upload(str(path))
    att = next(a for a in logged_in_instance.inbox.unlinked_attachments() if a['filename'] == path.name)
    return name, att


def test_assign_an_inbox_file_to_a_sample(instance_with_collection, inbox_file):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    name, att = inbox_file
    sample = col.new_sample_smiles('CCO')
    sample.save()
    assert [s['id'] for s in instance.inbox.search_samples(sample.short_label)] == [sample.id]

    dataset = instance.inbox.assign(att, sample)
    assert dataset['name'] == name
    sample.load()
    analysis = sample.analyses.by_name(name)
    assert [a['filename'] for a in analysis.datasets[0].attachments] == [f'{name}.txt']
    assert att['id'] not in {a['id'] for a in instance.inbox.unlinked_attachments()}


def test_assign_an_inbox_file_to_a_reaction(instance_with_collection, inbox_file):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    name, att = inbox_file
    reaction = col.new_reaction()
    reaction.save()
    assert reaction.id in {r['id'] for r in instance.inbox.search_reactions(reaction.short_label)}
    instance.inbox.assign(att, reaction)
    reaction.load()
    assert name in [a['name'] for a in reaction.analyses]
