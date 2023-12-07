from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.generic_element import GenericElement
from chemotion_api.elements.sample import Sample
from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.wellplate import Wellplate
from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.generic_segments import GenericSegments
from chemotion_api.connection import Connection
from requests.exceptions import RequestException

class ElementSet(list):
    def __init__(self, session: Connection, element_type: dict,
                 collection_id: int = None, collection_is_sync: bool = False):
        super().__init__()
        self._session = session
        self._element_type = element_type
        self._collection_id = collection_id
        self._collection_is_sync = collection_is_sync
        self._page = 1
        self.max_page = 1
        self._per_page = 10

    def __getitem__(self, item):
        elm = super().__getitem__(item)
        elm.load()
        return elm

    @property
    def page(self):
        return self._page

    @page.setter
    def page(self, page: int):
        self._set_page(page)

    def _set_page(self, page: int) -> bool:
        if page > 0 and page <= self.max_page:
            self._page = page
            self.load_elements()
            return True
        return False

    def iter_elements(self):
        self._page = 0
        while self._set_page(self.page + 1):
            for elem in self:
                yield elem

    def iter_pages(self):
        self._page = 0
        while self._set_page(self.page + 1):
            yield self

    def next_page(self):
        self._set_page(self.page + 1)
        return self

    def prev_page(self):
        self._set_page(self.page - 1)
        return self

    def load_elements(self, per_page=None):
        if per_page is not None:
            self._per_page = per_page
        if self._collection_id is None:
            raise ValueError('load_elements only works if collection_id is set!')

        segments = GenericSegments(self._session)
        payload = {'page': self.page,
                   'per_page': self._per_page,
                   'filter_created_at': False,
                   'product_only': False,
                   'el_type': self._element_type['name']}
        if self._collection_is_sync:
            payload['sync_collection_id'] = self._collection_id
        else:
            payload['collection_id'] = self._collection_id
        res = self._session.get(self._get_url() + '.json',
                                data=payload)
        if res.status_code != 200:
            raise RequestException('{} -> {}'.format(res.status_code, res.text))

        try:
            self.max_page = int(res.headers.get('X-Total-Pages', 1))
        except:
            pass
        self.clear()
        elements = res.json().get(self._get_result_key() + 's', [])
        for json_data in elements:
            self.append(self._get_element_class()(segments, self._session, json_data=json_data))

    def load_element(self, id: int) -> AbstractElement:
        segments = GenericSegments(self._session)
        s = self._get_element_class()(segments, self._session, id=id,
                                      element_type=self._element_type['name'])
        self.append(s)
        return s

    def new_element(self, json_data: dict) -> AbstractElement:
        segments = GenericSegments(self._session)
        s = self._get_element_class()(segments, self._session, json_data=json_data)
        self.append(s)
        return s

    def _get_element_class(self) -> AbstractElement.__class__:
        if self._element_type['is_generic']:
            return GenericElement
        elif self._element_type['name'] == 'sample':
            return Sample
        elif self._element_type['name'] == 'reaction':
            return Reaction
        elif self._element_type['name'] == 'wellplate':
            return Wellplate
        elif self._element_type['name'] == 'research_plan':
            return ResearchPlan

        raise TypeError('Generic type "{}" cannot be found'.format(self._element_type['name']))

    def _get_result_key(self):
        if self._element_type['is_generic']:
            return 'generic_element'
        return AbstractElement.get_response_key(self._element_type['name'])

    def _get_url(self):
        return AbstractElement.get_url(self._element_type['name'])
