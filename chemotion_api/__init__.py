"""Public entry point for the Chemotion API client.

The package exposes :class:`Instance`, the facade for connecting to a Chemotion ELN server and
reaching every other part of the client: collections and elements, users/groups/devices, molecule
and generic managers, sample/reaction search, and the inbox. Typical use is::

    from chemotion_api import Instance
    instance = Instance("https://my.chemotion").test_connection().login("user", "password")
    root = instance.get_root_collection()

"""

import logging as _logging
import typing
from typing import TypeVar, Optional, Self

# Library logging hygiene: attach a NullHandler so importing chemotion_api never emits log
# output unless the consuming application configures handlers itself.
_logging.getLogger(__name__).addHandler(_logging.NullHandler())

from chemotion_api.collection import RootCollection, Collection
from chemotion_api.converter import ProfileManager
from chemotion_api.element_manager import ElementManager
from chemotion_api.inbox import Inbox
from chemotion_api.labImotion import GenericManager
from chemotion_api.search.reaction import ReactionSearcher
from chemotion_api.search.sample import SampleSearcher
from chemotion_api.search.structure import StructureSearcher
from chemotion_api.user import User, Admin, Person, Device, Group, DeviceManager, Affiliation, UserLabel
from urllib.parse import quote, urlparse
from chemotion_api.elements import ElementSet, Wellplate, Sample, Reaction, GenericElement, ResearchPlan, Screen, CellLine, DeviceDescription, SbmmSample, \
    AbstractElement
from chemotion_api.elements.sample import MoleculeManager
from chemotion_api.connection import Connection, request_error
from chemotion_api.elements import literature, research_plan
from chemotion_api import chemicals, compute, reports, vessels
from chemotion_api.text_templates import TextTemplates
from chemotion_api.spectra import Spectra
from chemotion_api.schema_manager import SUPPORTED_ELN_MAJOR, UnsupportedServerVersion

TInstance = TypeVar("TInstance", bound="Instance")


class Instance:
    """
    The instance object is the core object of the Chemotion API. In order for the API to work,
    a connection to a Chemotion server must first be established.
    An Instance object manages such a connection. To initialize an instance it needs
    the host URL of the Chemotion server as a string.

    :param host_url: URL of the Chemotion server (e.g. ``'http://localhost:3000'``) or an existing
        :class:`chemotion_api.connection.Connection`
    :param verify_ssl: If False, the SSL certificate of the server is not verified

    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")


    """

    def __init__(self, host_url: str | Connection, verify_ssl: bool = True, username: str | None = None, password: str | None = None):
        if isinstance(host_url, Connection):
            self._con = host_url
        else:
            self._con = Connection(host_url, verify_ssl)
        self._root_col: RootCollection | None = None
        self._inbox: Inbox | None = None
        self.element_manager = ElementManager(self._con)
        if username and password:
            self.test_connection()
            self.login(username, password)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, "_con") and hasattr(self._con, "close"):
            try:
                self._con.close()
            except Exception:
                pass

    @property
    def host_url(self) -> str:
        """
        The url as string of the instance

        :return: host URL
        """
        return self._con.host_url

    @property
    def token(self) -> str:
        """
        The token property returns the JWT (JSON Web Token) of the current login

        :return: JWT
        """

        return self._con.bearer_token

    @property
    def device_manager(self) -> DeviceManager:
        """
        A DeviceManager instance

        :return: DeviceManager
        """
        return DeviceManager(self._con)

    @property
    def inbox(self) -> Inbox:
        """
        Get the data file inbox

        :return: Inbox Object
        """
        if self._inbox is None:
            self._inbox = Inbox(self._con)
        return self._inbox

    def test_connection(self) -> Self:
        """
        This test_connection method simply tests if the connection to a Chemotion instance can be established.
        The instance does not need to be logged in to use this method.

        It also verifies that the instance runs a supported ELN major version. Both checks are
        unauthenticated, so an incompatible server is reported before any credentials are sent.

        :return: the instance self

        :raises ConnectionError: if the connection cannot be established.
        :raises UnsupportedServerVersion: if the instance is not a supported ELN version.
        """
        ping_url = "/api/v1/public/ping"
        res = self._con.get(url_path=ping_url)
        if res.status_code != 204:
            raise ConnectionError(f'Could not ping the Chemotion instance: {self.host_url}')
        # Accessing schema_manager fetches /about and applies the version gate. Doing it here means
        # a v3 server fails with a clear message instead of surfacing later as a confusing 400 from
        # an endpoint v4 moved.
        self._con.schema_manager  # noqa: B018  (property access performs the check)
        return self

    def get_all_types(self) -> list[str]:
        """
        Generates a list of all JSON-LD types (IRIs) in the system.

        :return: List of JSON-LD types
        """
        return self.element_manager.all_types

    def login(self, user: str, password: str) -> Self:
        """
        This login method allows you to log in to a Chemotion instance.
        To do this, you need a valid Chemotion user (name abbreviation or e-mail) and password.

        :param user: name abbreviation or e-mail of a Chemotion user
        :param password: The password of the user

        :return: the instance itself

        :raise PermissionError: if the login was not successful.
        """

        payload = {'username': user, 'password': password}
        login_url = "/api/v1/public/token"

        res = self._con.post(url_path=login_url,
                             headers=self._con.get_default_session_header(),
                             data=payload)

        if res.status_code != 201:
            raise PermissionError('Could not login!!')
        self._con.set_bearer_token(res.json()['token'])
        return self

    def login_token(self, jwt_token: str) -> Self:
        """
        You can use this login_token method to log in to a Chemotion instance.
        To do this, you need a valid Chemotion JWT. The token of a logged-in instance can be read
        with the :attr:`token` property; a token for a device can be generated with the
        :attr:`device_manager`.

        The token is not checked by this method. An invalid token causes the following requests to fail.

        :param jwt_token: a JSON Web Token.

        :return: the instance itself
        """

        self._con.set_bearer_token(jwt_token)
        return self

    def get_profile_manager(self) -> ProfileManager:
        """
        Returns a ProfileManager used to list, create and delete converter profiles.
        Converter profiles are needed to fill the metadata of a dataset automatically on upload.

        :return: a ProfileManager
        """
        return ProfileManager(self._con)

    def get_user(self) -> Admin | Person | Group | Device:
        """
        This get_user method initializes a new User object. The user object allows you to read and edit your user data.

        :return: a new User instance

        :raise PermissionError: if the userdata cannot be fetched. Make sure that you are logged in.
        """
        u = User.load_me(self._con)
        return u

    def get_affiliations(self) -> list[Affiliation]:
        """Return the logged-in user's affiliations (organization, department, group, country)
        as exposed by Grape (`/api/v1/affiliations`).

        :raise PermissionError: if the userdata cannot be fetched. Make sure that you are logged in.
        """
        return self.get_user().get_affiliations()

    def get_user_labels(self, refresh: bool = False) -> list[UserLabel]:
        """Return the user labels visible to the logged-in user
        (`/api/v1/user_labels/list_labels`).

        Elements expose their labels as bare ids; this is the id-to-title map. To resolve the
        labels of a specific element use its ``user_labels_resolved`` property instead, which
        reuses the same cached list.

        :param refresh: drop the cached labels and fetch them again.
        :raise PermissionError: if the labels cannot be fetched. Make sure that you are logged in.
        """
        return self.get_user().get_user_labels(refresh=refresh)

    def suggestions(self, query: str, element_type: str = 'all', collection_id: int | None = None) -> list[dict]:
        """
        Search-box suggestions for ``query``, as the UI's autocomplete shows them
        (``GET /api/v1/suggestions/:element_type``): ``{'name', 'search_by_method'}`` dicts, where
        ``search_by_method`` says what matched, e.g. ``'sample_short_label'`` or ``'iupac_name'``.
        For generic elements ``name`` is a dict (``{'klass', 'label', 'name', 'icon'}``).

        :param element_type: ``'all'``, ``'samples'``, ``'reactions'``, ``'wellplates'``,
            ``'screens'``, … (the server's list).
        :param collection_id: the collection to suggest from; defaults to "All".
        """
        if not query:
            return []
        cid = collection_id if collection_id is not None else self.get_root_collection().id
        res = self._con.get(f'/api/v1/suggestions/{element_type}', params={'query': query, 'collection_id': str(cid)})
        if res.status_code != 200:
            raise request_error(res, f'suggestions for {query!r}')
        return (res.json() or {}).get('suggestions') or []

    def doi_metadata(self, doi: str) -> dict:
        """
        BibTeX metadata for a DOI, fetched by the server from doi.org
        (``GET /api/v1/literatures/doi/metadata``): ``{'bibtex': str, 'BTjson': dict}``.

        :raises ValueError: if ``doi`` is not a DOI.
        :raises RequestException: if doi.org cannot be reached or does not know the DOI.
        """
        return literature.doi_metadata(self._con, doi)

    def report_templates(self) -> list[reports.ReportTemplate]:
        """The server's report templates (``GET /api/v1/report_templates``)."""
        return reports.report_templates(self._con)

    def create_report(self, *elements, template: str | int | reports.ReportTemplate = 'standard',
                      wait: bool = True, timeout: float = 300, **options) -> reports.Archive:
        """
        Generates a report of samples and reactions, as the UI's *Report* tab does
        (``POST /api/v1/reports``). The server generates it in a background job and keeps it as
        an :class:`~chemotion_api.reports.Archive`; with ``wait`` this returns once it is ready.

        Usage::

        >>> archive = instance.create_report(reaction, sample, file_name='Weekly',
        ...                                  reaction_settings={'variations': False})
        >>> archive.download('weekly.docx')

        :param template: ``'standard'`` (default), ``'supporting_information'``,
            ``'supporting_information_std_rxn'``, ``'spectrum'``, ``'rxn_list_xlsx'``,
            ``'rxn_list_csv'``, ``'rxn_list_html'``, or a template from :meth:`report_templates`.
        :param options: see :func:`chemotion_api.reports.report_payload`.
        """
        return reports.create_report(self._con, elements, template, wait=wait, timeout=timeout, **options)

    def report_archives(self) -> list[reports.Archive]:
        """Your generated reports, newest first, as the UI's *Archive* tab lists them."""
        return reports.archives(self._con)

    def research_plan_table_schemas(self) -> list[dict]:
        """Your saved research-plan table layouts: ``{'id', 'name', 'value'}`` dicts."""
        return research_plan.load_table_schemas(self._con)

    def save_research_plan_table_schema(self, name: str, table) -> dict:
        """Save a research-plan table's layout under ``name``, to reuse in other plans."""
        return research_plan.save_table_schema(self._con, name, table)

    def delete_research_plan_table_schema(self, schema_id: int) -> None:
        """Delete one of your saved research-plan table layouts."""
        research_plan.delete_table_schema(self._con, schema_id)

    def text_templates(self) -> TextTemplates:
        """The rich-text editors' text templates: predefined, personal, and your toolbars.
        See :class:`chemotion_api.text_templates.TextTemplates`."""
        return TextTemplates(self._con)

    def save_user_label(self, label: UserLabel) -> UserLabel:
        """Create a user label, or update one of your own. See
        :meth:`chemotion_api.user.User.save_user_label`.

        >>> label = instance.save_user_label(UserLabel(title='to check', color='#ff0000'))
        >>> collection.update_user_labels(*samples, add=[label])
        """
        return self.get_user().save_user_label(label)

    def find_user_by_name(self, name: str) -> list[Person]:
        """
        This find_user_by_name method finds all users by name and returns the three top matches.

        :param name: Potential name or name snippet of a user
        :return: list of matching users

        :raise PermissionError: if the userdata cannot be fetched. Make sure that you are logged in.
        """

        return self.get_user().find_user_by_name(self._con, name)


    def get_root_collection(self, reload=True) -> RootCollection:
        """
        The root collection can be compared to the 'All' collection in the web client of Chemotion.
        Within this python client it is needed to navigate through all collections. A collection is the foundation for fetching
        and creating new elements.

        :param reload: If true, cached information is ignored and the collection tree is fetched again
        :return: the root collection
        """
        if reload or self._root_col is None:
            self._root_col = RootCollection(self._con)
            self._root_col.set_element_manager(self.element_manager)
            self._root_col.load_collection()
            self._root_col.load_sync_collection()
        return typing.cast(RootCollection, self._root_col)

    def get_collection_by_id(self, collection_id: int) -> Collection:
        """
        Find a collection by its id.
        Within this python client it is needed to navigate through all sub collections. A collection is the foundation for fetching
        and creating new elements.

        :param collection_id: DB id of the collection
        :return: the collection

        :raises IndexError: if no owned collection has this id
        """
        return typing.cast(Collection, self.get_root_collection().find(id=collection_id)[0])

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> Collection:
        """
        Gets a collection a path points to from the root collection.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account

        :return: Collection the path points to
        """
        return typing.cast(Collection, self.get_root_collection().get_collection(col_path, case_insensitive))

    def get_or_create_collection(self, col_path: str | list[str],
                                 case_insensitive: bool = False) -> Collection:
        """
        Gets or creates a collection the col_path path points to from the root collection.
        If the collection needs to be created the collection is saved right away.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account

        :return: Collection the path points to
        """
        return typing.cast(Collection, self.get_root_collection().get_or_create_collection(col_path, case_insensitive))


    def get_collection_of_element(self, element: AbstractElement):
        """
        Find a collection from its element. If the element is in several collections, the first one is returned.
        Within this python client it is needed to navigate through all sub collections. A collection is the foundation for fetching
        and creating new elements.

        :param element: An element (Sample, Reaction, ...) accessible by your account (needs to be saved!)
        :return: the collection of the element

        :raises KeyError: if the collection cannot be found
        """
        try:
            try:
                collection_id = typing.cast(dict, element.json_data)['tag']['taggable_data']['collection_labels'][0]["id"]
            except (KeyError, IndexError):
                element.load()
                collection_id = typing.cast(dict, element.json_data)['tag']['taggable_data']['collection_labels'][0]["id"]
            return self.get_collection_by_id(collection_id)
        except KeyError:
            raise KeyError(f'Could not find collection of {element}')

    def search_sample(self) -> SampleSearcher:
        """
        This function returns a SampleSearcher object, which facilitates the search for samples.
        The user has the option to set the maximum number of results and the collection to search in.
        In addition, search conditions can be added and connected with 'or' or 'and'. It is necessary
        to specify the matching type for each condition. Upon making the final call to the method,
        the search will be executed.

        Usage::

        >>> from chemotion_api import Instance
        >>> import logging
        >>> from chemotion_api.search.utils import EnumMatch, EnumConnector
        >>>
        >>> try:
        >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
        >>> except ConnectionError as e:
        >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
        >>> (instance.search_sample().
        >>>  add_search_condition(EnumMatch.LIKE, EnumConnector.OR, name='My Sample', private_note="My note").
        >>>  add_search_condition(EnumMatch.EXACT, EnumConnector.AND, short_label="USER").
        >>>  find_max(5).
        >>>  request())

        :return: SampleSearcher
        """
        return SampleSearcher(self._con, self.element_manager, self.get_root_collection().id)

    def search_reaction(self) -> ReactionSearcher:
        """
        This function returns a ReactionSearcher object, which facilitates the search for reaction.
        The user has the option to set the maximum number of results and the collection to search in.
        In addition, search conditions can be added and connected with 'or' or 'and'. It is necessary
        to specify the matching type for each condition. Upon making the final call to the method,
        the search will be executed.

        Usage::

        >>> from chemotion_api import Instance
        >>> import logging
        >>> from chemotion_api.search.utils import EnumMatch, EnumConnector
        >>>
        >>> try:
        >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
        >>> except ConnectionError as e:
        >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
        >>> (instance.search_reaction().
        >>>  add_search_condition(EnumMatch.LIKE, EnumConnector.OR, name='My Sample', private_note="My note").
        >>>  add_search_condition(EnumMatch.EXACT, EnumConnector.AND, short_label="USER").
        >>>  add_search_condition(EnumMatch.BIGGER_THAN, EnumConnector.AND, temperature_in_c=30).
        >>>  find_max(5).
        >>>  request())

        :return: ReactionSearcher
        """
        return ReactionSearcher(self._con, self.element_manager, self.get_root_collection().id)

    def search_structure(self) -> StructureSearcher:
        """
        Returns a :class:`~chemotion_api.search.structure.StructureSearcher` for substructure and
        similarity searches, the UI's structure search. Results cover every element type: the
        matching samples and the reactions, wellplates, screens, research plans and generic
        elements associated with them.

        Usage::

        >>> result = instance.search_structure().substructure('c1ccccc1O').find_max(50).request()
        >>> phenols = list(result.samples)
        >>> similar = instance.search_structure().similar('CCO', threshold=0.8).request()

        :return: StructureSearcher
        """
        return StructureSearcher(self._con, self.element_manager, self.get_root_collection().id)

    @property
    def all_element_classes(self) -> dict[str, dict[str, str]]:
        """
        This all_element_classes fetches all information about all elements such as
         Sample, Reaction, Wellplate and Research plan and all generic elements

        :return: a dictionary which contains all information about all elements

        :raise RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        return self.element_manager.all_classes

    def get_reaction(self, id: int) -> Reaction:
        """
        Fetches data of one Reaction object from the Chemotion server.
        It automatically parses the data into a Python-Reaction-Object. However, you need to know the correct internally used ID
        of the Reaction to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param id: The Database ID of the desired Element
        :return: a Reaction object
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('reaction')))
        return typing.cast(Reaction, e.load_element(id))

    def get_wellplate(self, id: int) -> Wellplate:
        """
        Fetches data of one Wellplate object from the Chemotion server.
        It automatically parses the data into a Python-Wellplate-Object. However, you need to know the correct internally used ID
        of the Wellplate to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param id: The Database ID of the desired Element
        :return: a Wellplate object
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('wellplate')))
        return typing.cast(Wellplate, e.load_element(id))

    def get_screen(self, id: int) -> Screen:
        """
        Fetches data of one Screen object from the Chemotion server.

        :param id: The Database ID of the desired Element
        :return: a Screen object
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('screen')))
        return typing.cast(Screen, e.load_element(id))

    def get_cell_line(self, id: int) -> CellLine:
        """
        Fetches one cell line sample from the Chemotion server.

        :param id: The Database ID of the desired Element
        """
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('cell_line')))
        return typing.cast(CellLine, e.load_element(id))

    def cell_line_materials(self) -> list[dict]:
        """All cell line materials (``{'id', 'name', 'source'}``), as the cell line editor's name list offers them."""
        from chemotion_api.elements.cell_line import material_names
        return material_names(self._con)

    def get_device_description(self, id: int) -> DeviceDescription:
        """Fetches one device description from the Chemotion server."""
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('device_description')))
        return typing.cast(DeviceDescription, e.load_element(id))

    def device_ontologies(self) -> list[dict]:
        """The ontology terms the device description editor offers."""
        from chemotion_api.elements.device_description import ontologies
        return ontologies(self._con)

    def get_sbmm_sample(self, id: int) -> SbmmSample:
        """Fetches one sequence-based macromolecule sample from the Chemotion server."""
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('sequence_based_macromolecule_sample')))
        return typing.cast(SbmmSample, e.load_element(id))

    def search_macromolecules(self, term: str, field: str = 'accession') -> list[dict]:
        """Search this ELN's sequence-based macromolecules and UniProt. See
        :func:`chemotion_api.elements.sbmm.search_macromolecules`."""
        from chemotion_api.elements.sbmm import search_macromolecules
        return search_macromolecules(self._con, term, field)

    def get_macromolecule(self, identifier: int | str, source: str = 'eln') -> dict:
        """A macromolecule by ELN id (``source='eln'``) or UniProt accession (``source='uniprot'``)."""
        from chemotion_api.elements.sbmm import load_macromolecule
        return load_macromolecule(self._con, identifier, source)

    def set_inventory_label(self, prefix: str, name: str, counter: int, *collections) -> list[dict]:
        """Give collections an inventory label: their inventory samples are then labelled
        ``<prefix>-<n>``, counting on from ``counter``. :return: your inventories afterwards."""
        return chemicals.set_inventory_label(self._con, prefix, name, counter, [c.id for c in collections])

    def inventory_collections(self) -> list[dict]:
        """Your collections grouped by inventory label."""
        return chemicals.inventory_collections(self._con)

    def find_safety_sheets(self, name: str | None = None, molecule=None, **options) -> dict:
        """Look up safety data sheets at chemical vendors. See
        :func:`chemotion_api.chemicals.find_safety_sheets`; ``molecule`` is a Molecule or its id."""
        molecule_id = getattr(molecule, 'id', molecule)
        return chemicals.find_safety_sheets(self._con, name, molecule_id, **options)

    def download_safety_sheet(self, path: str, file_path: str) -> str:
        """Save a stored safety data sheet (a ``Chemical.safety_sheets`` path) to ``file_path``."""
        return chemicals.download_safety_sheet(self._con, path, file_path)

    def extract_safety_sheet(self, path: str) -> dict:
        """The H/P statements and section 9 properties of a stored safety data sheet."""
        return chemicals.extract_safety_sheet(self._con, path)

    def spectra(self) -> Spectra:
        """Spectra processing through the ELN's ChemSpectra service. See :class:`chemotion_api.spectra.Spectra`."""
        return Spectra(self._con)

    def simulate_nmr(self, molecule) -> dict:
        """Simulated 1H and 13C NMR spectra of a molecule (from nmrdb.org, via the ELN)."""
        return compute.simulate_nmr(self._con, molecule)

    def predict_products(self, reactants) -> object:
        """Forward reaction prediction from reactant SMILES (needs the ELN's inference server)."""
        return compute.predict_products(self._con, reactants)

    def predict_reactants(self, products) -> object:
        """Retrosynthesis from product SMILES (needs the ELN's inference server)."""
        return compute.predict_reactants(self._con, products)

    def compute_tasks(self) -> list[compute.ComputeTask]:
        """Your quantum-chemistry compute tasks, newest first."""
        return compute.compute_tasks(self._con)

    def submit_compute_task(self, sample) -> compute.ComputeTask | None:
        """Send a sample's molecule to the ELN's compute server. See :func:`chemotion_api.compute.submit_compute_task`."""
        return compute.submit_compute_task(self._con, sample)

    def vessel_templates(self) -> list[vessels.VesselTemplate]:
        """All vessel templates on the ELN."""
        return vessels.templates(self._con)

    def new_vessel_template(self, name: str, **fields) -> vessels.VesselTemplate:
        """An unsaved vessel template; set fields and call ``save()``.

        :param fields: ``vessel_type``, ``material_type``, ``material_details``, ``volume_amount``,
            ``volume_unit``, ``details``.
        """
        return vessels.VesselTemplate(name=name, **fields, _session=self._con)

    def get_vessel_template(self, id: str) -> vessels.VesselTemplate:
        return vessels.load_template(self._con, id)

    def get_vessel(self, id: str) -> vessels.Vessel:
        """One vessel, by its UUID."""
        return vessels.load_vessel(self._con, id)

    def get_research_plan(self, id: int) -> ResearchPlan:
        """
        Fetches data of one Research Plan object from the Chemotion server.
        It automatically parses the data into a Python-ResearchPlan-Object. However, you need to know the correct internally used ID
        of the Research Plan to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param id: The Database ID of the desired Element
        :return: a ResearchPlan object
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('research_plan')))
        return typing.cast(ResearchPlan, e.load_element(id))

    def get_sample(self, id: int) -> Sample:
        """
        Fetches data of one Sample object from the Chemotion server.
        It automatically parses the data into a Python-Sample-Object. However, you need to know the correct internally used ID
        of the Sample to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param id: The Database ID of the desired Element
        :return: a Sample object
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        e = ElementSet(self._con, typing.cast(dict, self.all_element_classes.get('sample')))
        return typing.cast(Sample, e.load_element(id))

    def find_sample_by_short_label(self, short_label: str) -> Sample | None:
        """
        Finds one of your samples by its short label, e.g. ``'API-12-1'``.

        ``GET /api/v1/samples/findByShortLabel/:short_label``, the UI's short-label search. The
        server only looks at samples you own that are in one of your collections, so a sample
        shared with you is not found.

        :param short_label: the sample's short label, matched exactly.
        :return: the loaded sample, or ``None`` if none matches.
        :raises RequestException: if the lookup or loading the sample fails.
        """
        sample_id = self._find_id_by_short_label('samples', 'sample_id', short_label)
        return None if sample_id is None else self.get_sample(sample_id)

    def find_reaction_by_short_label(self, short_label: str) -> Reaction | None:
        """
        Finds one of your reactions by its short label, e.g. ``'API-R3'``.

        ``GET /api/v1/reactions/findByShortLabel/:short_label``. As for samples, only reactions
        you own that are in one of your collections are found.

        :param short_label: the reaction's short label, matched exactly.
        :return: the loaded reaction, or ``None`` if none matches.
        :raises RequestException: if the lookup or loading the reaction fails.
        """
        reaction_id = self._find_id_by_short_label('reactions', 'reaction_id', short_label)
        return None if reaction_id is None else self.get_reaction(reaction_id)

    def _find_id_by_short_label(self, route: str, id_key: str, short_label: str) -> int | None:
        if not short_label:
            raise ValueError('A short label is required.')
        # `.json` pins the format, so a label containing a dot is not read as an extension.
        res = self._con.get(f'/api/v1/{route}/findByShortLabel/{quote(short_label, safe="")}.json')
        if res.status_code != 200:
            raise request_error(res, f'finding {route} by short label {short_label!r}')
        return (res.json() or {}).get(id_key)

    def get_generic_by_name(self, name: str, id: int) -> GenericElement:
        """
        Fetches data of one Generic object from the Chemotion server. The generic element type is
        given by its system-internal name.
        It automatically parses the data into a Python-Generic-Object. However, you need to know the correct internally used ID
        of the Generic element to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param name: The name of the Generic Element type
        :param id: The Database ID of the desired Element
        :return: a GenericElement object

        :raises ValueError: if no generic element type has this name
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        elem = self.all_element_classes.get(name)
        if elem is None:
            raise ValueError(f'Could not find a generic element under the name: "{name}"')
        e = ElementSet(self._con, elem)
        return typing.cast(GenericElement, e.load_element(id))

    def get_generic_by_label(self, label: str, id: int) -> GenericElement:
        """
        Fetches data of one Generic object from the Chemotion server. The generic element type is
        given by its human-readable label.
        It automatically parses the data into a Python-Generic-Object. However, you need to know the correct internally used ID
        of the Generic element to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param label: The label of the Generic Element type
        :param id: The Database ID of the desired Element
        :return: a GenericElement object

        :raises ValueError: if no generic element type has this label
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        for (elem_name, elem) in self.all_element_classes.items():
            if elem['label'] == label:
                return self.get_generic_by_name(elem_name, id)
        raise ValueError(f'Could not find a generic element with the label: "{label}"')

    def get_json_ld_id(self, id: str) -> AbstractElement:
        """
        Use the python client internal JSON-LD id (``element.json_ld['@id']``) to fetch an element from Chemotion.

        :param id: JSON-LD ID string starting with the host url of the element
        :return: the requested element

        :raises ValueError: if the information cannot be fetched. Make sure that your connection is active and the ID is correct.
        """
        o = urlparse(id)
        if not self._con.host_url.startswith(f'{o.scheme}://{o.hostname}'):
            raise ValueError('Host does not fit!')
        path_array = o.path.split('/')
        elem = self.all_element_classes.get(path_array[-2][:-1])
        if elem is None:
            raise ValueError(f'Could not find a generic element under the name: "{path_array[-2]}"')
        e = ElementSet(self._con, elem)
        return e.load_element(int(path_array[-1][:-5]))

    def molecule(self) -> MoleculeManager:
        """
        Returns a MoleculeManager instance. This instance allows to create and
        fetch Molecules from the instance

        :return: a MoleculeManager instance
        """
        return MoleculeManager(self._con)

    def get_solvent_list(self) -> list[str]:
        """
        Returns a list of all predefined solvents. The names can be used with
        :meth:`chemotion_api.collection.Collection.new_solvent` and
        :meth:`chemotion_api.elements.sample.SolventList.add_new_name`.

        :return: a list of all predefined solvent names
        """
        return list(ElementManager.get_solvent_list().keys())

    def generic_manager(self) -> GenericManager:
        """
        Returns a GenericManager used to load, edit and write the templates (LabIMotion) of
        generic elements, segments and datasets.

        :return: a GenericManager
        """
        return GenericManager(self._con, self.element_manager)
