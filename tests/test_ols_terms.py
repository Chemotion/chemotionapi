"""OLS terms on a live ELN (M6.6).

The stack's database holds no imported ontology, so the ELN serves its built-in term lists. The
admin routes rewrite those lists from the database, so they are only checked for their guards here.
"""
import pytest

from chemotion_api import Instance

pytestmark = pytest.mark.integration


def _find(nodes, term_id):
    for node in nodes:
        # The built-in lists carry the id in 'term_id' or only in 'value' ("CHMO:0000595 | label").
        if node.get('term_id') == term_id or str(node.get('value') or '').strip().startswith(f'{term_id} |'):
            return node
        found = _find(node.get('children') or [], term_id)
        if found:
            return found
    return None


def test_term_lists(logged_in_instance):
    chmo = logged_in_instance.ols_terms('chmo', edited=False)
    assert _find(chmo, 'CHMO:0000595')
    assert logged_in_instance.ols_terms('rxno')
    with pytest.raises(ValueError):
        logged_in_instance.ols_terms('nope')


def test_switching_terms_without_an_imported_ontology_is_refused(config_login, logged_in_instance):
    admin = Instance(config_login['ELN_URL']).login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS'])
    with pytest.raises(ValueError, match='import the ontology first'):
        admin.get_user().set_ols_terms_enabled('chmo', disable=['CHMO:0000595'])
    assert _find(logged_in_instance.ols_terms('chmo', edited=False), 'CHMO:0000595')
    assert not hasattr(logged_in_instance.get_user(), 'set_ols_terms_enabled')
