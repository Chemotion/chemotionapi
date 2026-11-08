"""NMR simulation, reaction prediction and quantum-chemistry compute tasks (M5.4).

All three run on services outside the ELN, which must be configured on the server:

* **NMR simulation** asks nmrdb.org for 1H and 13C spectra of a molecule and caches them.
* **Reaction prediction** (forward: products, retro: reactants) needs the inference server and the
  ``reactionPrediction`` feature for the user.
* **Compute tasks** send a sample's molecule to the compute server (``compute_config``), which
  computes orbital energies, potentials, a TDDFT spectrum, …; the result comes back as a task.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: The computed properties a finished task carries.
RESULT_FIELDS = ('homo', 'lumo', 'ea', 'dipol_debye', 'max_potential', 'min_potential', 'mean_potential',
                 'mean_abs_potential', 'tddft', 'data')


def simulate_nmr(session: Connection, molecule) -> dict[str, Any]:
    """Simulated 1H and 13C NMR spectra of a molecule, from nmrdb.org
    (``GET /api/v1/simulation/nmrdb``): ``{'response_1h': ..., 'response_13c': ...}``.

    :param molecule: a :class:`~chemotion_api.elements.sample.Molecule` or its id. The server sends
        its structure to nmrdb.org.
    """
    molecule_id = molecule if isinstance(molecule, int) else molecule.id
    res = session.get('/api/v1/simulation/nmrdb', params={'molecule_id': molecule_id})
    if res.status_code != 200:
        raise request_error(res, f'simulating NMR spectra of molecule {molecule_id}')
    return res.json()


def _predict(session: Connection, kind: str, smiles: Iterable[str]) -> Any:
    smis = list(smiles)
    if not smis:
        raise ValueError('Give at least one SMILES.')
    res = session.post(f'/api/v1/prediction/{kind}', data={'smis': smis})
    if res.status_code == 500:
        raise ConnectionError('The ELN failed to run the prediction. On ELN main the route always fails '
                              '(its permission check returns from a Grape before block); otherwise the '
                              'inference server is missing.')
    if res.status_code not in (200, 201):
        raise request_error(res, f'predicting {kind}')
    answer = res.json()
    if isinstance(answer, dict) and answer.get('error'):
        raise ConnectionError(answer['error'])
    return answer


def predict_products(session: Connection, reactants: Iterable[str]) -> Any:
    """Forward reaction prediction: likely products of the reactants (SMILES)
    (``POST /api/v1/prediction/products``)."""
    return _predict(session, 'products', reactants)


def predict_reactants(session: Connection, products: Iterable[str]) -> Any:
    """Retrosynthesis: likely reactants for the products (SMILES) (``POST /api/v1/prediction/reactants``)."""
    return _predict(session, 'reactants', products)


@dataclass
class ComputeTask:
    """A computation of a sample's molecule. ``status`` is e.g. ``'pending'``, ``'success'`` or
    ``'revoked'``; the results are in :data:`RESULT_FIELDS` once it has finished."""
    id: int
    sample_id: int | None
    status: str | None
    results: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _session: Connection | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: dict[str, Any], session: Connection | None = None) -> ComputeTask:
        return cls(id=data['id'], sample_id=data.get('sample_id'), status=data.get('status'),
                   results={k: data.get(k) for k in RESULT_FIELDS if data.get(k) is not None}, raw=data,
                   _session=session)

    def _con(self) -> Connection:
        if self._session is None:
            raise ValueError('Not attached to a server connection.')
        return self._session

    def _ask(self, action: str) -> ComputeTask:
        res = self._con().get(f'/api/v1/compute_tasks/{self.id}/{action}')
        if res.status_code == 401:
            raise PermissionError(f'Compute task {self.id} is not yours.')
        if res.status_code == 500:
            raise ConnectionError('The ELN could not reach its compute server (is compute_config set?).')
        if res.status_code != 200:
            raise request_error(res, f'{action} of compute task {self.id}')
        self.__dict__.update(ComputeTask.from_json(res.json()[action], self._session).__dict__)
        return self

    def check(self) -> ComputeTask:
        """Ask the compute server for this task's status and update it (``GET /compute_tasks/:id/check``)."""
        return self._ask('check')

    def revoke(self) -> ComputeTask:
        """Cancel the task on the compute server (``GET /compute_tasks/:id/revoke``)."""
        return self._ask('revoke')

    def delete(self) -> None:
        """Delete the task and its results (``DELETE /compute_tasks/:id``)."""
        res = self._con().delete(f'/api/v1/compute_tasks/{self.id}')
        if res.status_code == 401:
            raise PermissionError(f'Compute task {self.id} is not yours.')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting compute task {self.id}')


def compute_tasks(session: Connection) -> list[ComputeTask]:
    """Your compute tasks, newest first (``GET /api/v1/compute_tasks/all``)."""
    res = session.get('/api/v1/compute_tasks/all')
    if res.status_code != 200:
        raise request_error(res, 'loading your compute tasks')
    return [ComputeTask.from_json(t, session) for t in res.json().get('compute_tasks') or []]


def submit_compute_task(session: Connection, sample) -> ComputeTask | None:
    """Send the sample's molecule to the compute server (``POST /api/v1/molecules/compute``).

    The server answers without the task; the newest task of the sample is returned.

    :raises PermissionError: if the server has no compute configuration or does not allow you.
    """
    if getattr(sample, 'id', None) is None:
        raise ValueError('Save the sample first.')
    res = session.post('/api/v1/molecules/compute', data={'sampleId': sample.id})
    text = res.text or ''
    if 'No computation configuration' in text or 'Unauthorized' in text:
        raise PermissionError(f'The ELN does not run computations for you: {text}')
    if res.status_code not in (200, 201, 204):
        raise request_error(res, f'submitting sample {sample.id} for computation')
    return next((t for t in compute_tasks(session) if t.sample_id == sample.id), None)
