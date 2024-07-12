import typing

from typing import TypeVar
from chemotion_api.collection import RootCollection
from chemotion_api.element_manager import ElementManager
from chemotion_api.user import User, Admin, Person, Device, Group, DeviceManager
from urllib.parse import urlparse
from chemotion_api.elements import ElementSet, Wellplate, Sample, Reaction, GenericElement, ResearchPlan, \
    AbstractElement
from chemotion_api.elements.sample import MoleculeManager
from chemotion_api.connection import Connection

TInstance = TypeVar("TInstance", bound="Instance")


class Instance:
    """
    The instance object is the core object of the Chemotion API. In order for the API to work,
    a connection to a Chmotion must first be established.
    an Instance object manges such a connection. To initializes an instance it needs
    the host URL of the chemotion server as a string.

    :param host_url: URL for the new :class:`Request` object

    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")


    """

    def __init__(self, host_url: str):
        self._con = Connection(host_url)
        self._root_col = None
        self.element_manager = ElementManager(self._con)

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
        The token property returns the JWT (java web token)

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

    def test_connection(self) -> TInstance:
        """
        This test_connection methode simply test if the connection to a chemotion instance can be established.
        The instance does not need to be logged in to use this methode.

        :return: the instance self

        :raises ConnectionError: if the connection cannot be established.
        """
        ping_url = "/api/v1/public/ping"
        res = self._con.get(url_path=ping_url)
        if res.status_code != 204:
            raise ConnectionError('Could not ping the Chemotion instance: {}'.format(self.host_url))
        return self

    def get_all_types(self) -> list[str]:
        """
        Generates a list af all JSON LD types in the system.
        :return: List of JSON LD types
        """
        return self.element_manager.all_types

    def login(self, user: str, password: str) -> TInstance:
        """
        This login methode allows you to log in to a chemotion instance.
         To do this, you need a valid chemotion user (abbreviation name or e-mail) and password.

        :param user: abbreviation name or e-mail of a chemotion user
        :param password: The password of the user

        :return: the instance itself

        :raise ConnectionError: if the logging was not successful.
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

    def login_token(self, jwt_token: str) -> TInstance:
        """
        You can use this login_token method to log in to a chemotion instance.
        To do this, you need a valid chemotion jwt token. This token can be generated using the
        get_token method.

        :param jwt_token: a Java Web Token.

        :return: the instance itself

        :raise ConnectionError: if the logging was not successful.
        """

        self._con.set_bearer_token(jwt_token)
        return self

    def get_user(self) -> Admin | Person | Group | Device:
        """
        This get_user methode initializes a new User object. The user object allows you to read and edit your user data.

        :return: a new User instance

        :raise PermissionError: if the userdata cannot be fetched. Make sure that you are logged in.
        """
        u = User.load_me(self._con)
        return u

    def find_user_by_name(self, name: str) -> list[Person]:
        """
        This find_user_by_name methode finds all user by name and returns the three top matches.

        :param name: Potential name or name snippet of a user
        :return: list u matching user

        :raise PermissionError: if the userdata cannot be fetched. Make sure that you are logged in.
        """

        return self.get_user().find_user_by_name(self._con, name)

    def get_root_collection(self, reload=True) -> RootCollection:
        """
        The root collection can be compared to the all collection in the web client of Chemotion.
        Within this python client it is needed to navigate through all collections. A collection is foundtion of fetching
        and creating new elements.

        :param reload: If ture caned information are ignored
        :return:
        """
        if reload or self._root_col is None:
            self._root_col = RootCollection(self._con)
            self._root_col.set_element_manager(self.element_manager)
            self._root_col.load_collection()
            self._root_col.load_sync_collection()
        return self._root_col

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
        :return: a Reacton object
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        e = ElementSet(self._con, self.all_element_classes.get('reaction'))
        return typing.cast(Reaction, e.load_element(id))

    def get_wellplate(self, id: int) -> Wellplate:
        """
        Fetches data of one Wellplate object from the Chemotion server.
        It automatically parses the data into a Python-Wellplate-Object. However, you need to know the correct internally used ID
        of the Wellplate to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param id: The Database ID of the desired Element
        :return: a Reacton object
        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        e = ElementSet(self._con, self.all_element_classes.get('wellplate'))
        return typing.cast(Wellplate, e.load_element(id))

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
        e = ElementSet(self._con, self.all_element_classes.get('research_plan'))
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
        e = ElementSet(self._con, self.all_element_classes.get('sample'))
        return typing.cast(Sample, e.load_element(id))

    def get_generic_by_name(self, name: str, id: int) -> GenericElement:
        """
        Fetches data of one Generic object from the Chemotion server. Which generic element type
        It automatically parses the data into a Python-Generic-Object. However, you need to know the correct internally used ID
        of the Generic element to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param name: The name of the Genetic Element
        :param id: The Database ID of the desired Element
        :return: a Sample object

        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        elem = self.all_element_classes.get(name)
        if elem is None:
            raise ValueError(f'Could not find a generic element under the name: "{name}"')
        e = ElementSet(self._con, elem)
        return typing.cast(GenericElement, e.load_element(id))

    def get_generic_by_label(self, label: str, id: int) -> GenericElement:
        """
        Fetches data of one Generic object from the Chemotion server. Which generic element type
        It automatically parses the data into a Python-Generic-Object. However, you need to know the correct internally used ID
        of the Generic element to be able to fetch it. Other methods to get Elements from Chemotion
        are accessible via the Collection objects

        :param label: The label of the Genetic Element
        :param id: The Database ID of the desired Element
        :return: a Sample object

        :raises RequestException: (requests.exceptions.RequestException) if the information cannot be fetched. Make sure that your connection is active and you are logged in.
        """
        for (elem_name, elem) in self.all_element_classes.items():
            if elem['label'] == label:
                return self.get_generic_by_name(elem_name, id)
        raise ValueError(f'Could not find a generic element with the label: "{label}"')

    def get_json_ld_id(self, id: str) -> AbstractElement:
        """
        Use python client internal JSON LD id to fetch element from Chemtion.
        :param id: JSON LD ID string starting with host url of the element
        :return: the requested element

        :raises ValueError: if the information cannot be fetched. Make sure that your connection is active and the ID is correct.
        """
        o = urlparse(id)
        if not self._con.host_url.startswith(f'{o.scheme}://{o.hostname}'):
            raise ValueError('Host dose not fit!')
        path_array = o.path.split('/')
        elem = self.all_element_classes.get(path_array[-2][:-1])
        if elem is None:
            raise ValueError(f'Could not find a generic element under the name: "{path_array[-2]}"')
        e = ElementSet(self._con, elem)
        return e.load_element(int(path_array[-1][:-5]))

    def molecule(self) -> MoleculeManager:
        """
        Returns a MoleculeManager instance. This instance allows to create and
        fetch Molecules form the instance
        :return: a MoleculeManager instance
        """
        return MoleculeManager(self._con)

    def get_solvent_list(self) -> list[str]:
        """
        Returns a list of all pre implemented solvents.
        :return: a list of all pre implemented solvents
        """
        return list(ElementManager.get_solvent_list().keys())
