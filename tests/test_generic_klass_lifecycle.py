"""Deleting LabIMotion templates and their revisions on a live ELN (M6.1)."""
import uuid

import pytest

from chemotion_api.labImotion.items.options import SaveActionType

pytestmark = pytest.mark.integration


def test_revisions_and_delete(logged_in_instance):
    gm = logged_in_instance.generic_manager()
    suffix = uuid.uuid4().hex[:5]
    klass = gm.create_new_element(f'API delete {suffix}', 'bug', name=f'del{suffix}')
    klass.save(SaveActionType.MINOR)
    revisions = klass.revisions()
    assert [r.version for r in revisions][:2] == ['0.2', '0.1']
    with pytest.raises(ValueError, match='active version'):
        klass.delete_revision(revisions[0])
    klass.delete_revision(revisions[-1])
    assert revisions[-1].id not in {r.id for r in klass.revisions()}

    with pytest.raises(ValueError, match='pass confirm'):
        klass.delete(confirm='something else')
    klass.delete(confirm=klass.label)
    assert klass.name not in {k.name for k in gm.load_all_elements()}
