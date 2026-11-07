"""ELN-to-ELN transfer through the gate on a live ELN (M3.9).

The stack's ELN stands in for the receiving side, reached from inside its container. It can issue
and validate transfer tokens, so the check runs end to end. The transfer itself posts to
``/gate/received`` and ``/gate/receiving_chunk``, routes only the Chemotion Repository has, so
against an ELN it fails, and the test pins that this failure reaches the caller.
"""
import os

import pytest

pytestmark = pytest.mark.integration

#: The stack's ELN as its own server sees it (localhost resolves to ::1 there, which it does not bind).
INTERNAL_URL = os.getenv('ELN_INTERNAL_URL', 'http://127.0.0.1:4000/')


@pytest.fixture()
def gate(instance_with_collection, config_login):
    root = instance_with_collection['instance'].get_root_collection()
    outgoing = instance_with_collection['main_collection']
    incoming = root.get_or_create_collection(instance_with_collection['name'] + '_in')
    root.save()
    token = incoming.gate_token(config_login['ELN_URL'])
    outgoing.register_gate(INTERNAL_URL, token)
    return outgoing, incoming


def test_check_and_transmit(gate):
    outgoing, _ = gate
    sample = outgoing.new_sample_smiles('CCO')
    sample.save()
    try:
        answer = outgoing.check_transmission(INTERNAL_URL)
    except ConnectionError as e:
        if 'Connection refused' in str(e):
            pytest.skip(f'The ELN cannot reach itself at {INTERNAL_URL}; set ELN_INTERNAL_URL.')
        raise
    assert answer['target'] == INTERNAL_URL and answer['expire_at']
    with pytest.raises(ConnectionError, match='404'):
        outgoing.transmit(INTERNAL_URL, timeout=180)


def test_an_unregistered_target_is_refused(gate):
    outgoing, _ = gate
    # The same server under another address: reachable, but no token is registered for it.
    with pytest.raises(ConnectionError, match='Token missing'):
        outgoing.check_transmission(INTERNAL_URL.replace('127.0.0.1', '0.0.0.0'))
