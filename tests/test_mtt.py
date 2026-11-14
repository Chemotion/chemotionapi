"""MTT assay requests on a live ELN (M6.5). The external MTT app itself is not involved."""
import pytest

from chemotion_api import mtt

pytestmark = pytest.mark.integration


def test_mtt_request_lifecycle(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    element = col.new_generic('wrk')
    element.save()
    plate = col.new_wellplate()
    plate.save()
    link = element.create_mtt_request(plate)
    assert 'method=DoseResponse' in link and 'mtt_apps' in link

    (request,) = element.mtt_requests()
    assert (request.state_name, request.active, request.outputs) == ('initial', True, [])
    request.update(state=1, message='running')
    assert (request.state_name, request.resp_message) == ('processing', 'running')
    assert request.revoke().revoked

    assert mtt.delete_requests(instance._con, [request]) == 1
    assert element.mtt_requests() == []
    with pytest.raises(LookupError):
        mtt.delete_outputs(instance._con, [2_000_000_000])
