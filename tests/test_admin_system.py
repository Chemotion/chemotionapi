"""System administration on a live ELN (M7.6). Nothing here restarts real jobs or runs admin tasks."""
import pytest

from chemotion_api import Instance

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin(config_login):
    return Instance(config_login['ELN_URL']).login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS']).get_user()


def test_disk_jobs_matrix(admin):
    disk = admin.disk_usage()
    assert 0 <= disk['percent_used'] <= 100 and disk['mb_available'] > 0
    assert all('id' in job and 'queue' in job for job in admin.jobs())
    with pytest.raises(LookupError):
        admin.restart_job(2_000_000_000)
    with pytest.raises(ValueError):
        admin.queue_admin_task('drop_everything')

    matrix = next(m for m in admin.matrices() if m['name'] == 'computedProp')
    try:
        admin.update_matrix(matrix, label='API test label')
        assert next(m for m in admin.matrices() if m['id'] == matrix['id'])['label'] == 'API test label'
    finally:
        admin.update_matrix(matrix, label=matrix['label'] or 'computedProp')


def test_info_support_links(admin):
    link = admin.add_info_support_link('API help', 'https://example.org/help')
    try:
        assert admin.update_info_support_link(link, position=3)['position'] == 3
        assert link['id'] in {x['id'] for x in admin.info_support_links()}
    finally:
        admin.delete_info_support_link(link)
    assert link['id'] not in {x['id'] for x in admin.info_support_links()}
