"""Element subsystem: the :class:`ElementSet` paginated loader and the concrete element classes."""
from datetime import datetime
from typing import Optional

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.generic_element import GenericElement
from chemotion_api.elements.sample import Sample
from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.wellplate import Wellplate
from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.generic_segments import GenericSegments
from chemotion_api.connection import Connection, request_error
from requests.exceptions import RequestException


class ElementSet(list):
    """
    The ElementSet class allows you to access all elements of a type in a collection.
    You can iterate over them or filter them using an IRI filter.

    The elements are loaded page by page (``per_page`` elements per request). Iterating over the set
    loads all pages one after another. Indexing (``elements[12]``) loads the page containing the
    element and fully loads the element. Slicing (``elements[:5]``) returns a list. Negative indices are
    not supported. If an IRI filter is set, the set can only be iterated.
    ``len()`` returns the total number of elements on the server, not the size of the loaded page.
    The server limits ``per_page`` (100 in Chemotion 3.x).

    The listing contains only part of the data of each element. An element is loaded completely
    (one request) the first time its properties, segments, analyses or attachments are accessed.
    ``id``, ``name``, ``short_label`` and ``json_data`` do not trigger loading.
    """

    def __init__(self, session: Connection, element_type: dict,
                 collection_id: int | None = None, fixed_length: bool = False):
        super().__init__()
        self._load_options: dict = {}
        self._session = session
        self._element_type = element_type
        self._collection_id = collection_id
        self._page = 1
        self.max_page = 1
        self._per_page = 10
        self._iri_filter = None
        self._fixed_length = fixed_length
        # Total number of elements on the server (X-Total header), None until a page is loaded
        self._length = None

    def set_iri_filter(self, iri):
        """
        Restrict iteration to elements whose JSON-LD ``@type`` matches the given IRI.

        :param iri: IRI string (``chemotion:xxx/xxx/xxx``) used to filter the elements
        """
        self._iri_filter = iri

    def __len__(self):
        """
        :return: the total number of elements on the server, not only the ones of the loaded page
        """
        if self._fixed_length or self._length is None:
            return super().__len__()
        if self._iri_filter is None:
            return self._length
        raise TypeError("Length cannot be predicted if you use IRI typs")

    def __getitem__(self, item):
        if isinstance(item, slice):
            start = item.start if item.start is not None else 0
            stop = item.stop if item.stop is not None else len(self)
            last = stop - start
            if last <= 0 or stop < 0 or start < 0:
                raise TypeError(f"Negative index is not supported")
            per_page = self._per_page
            if item.start is not None:
                self._per_page = start
                start_page = 2
            else:
                self._per_page = min(10, last)
                start_page = 1
            res_list = []
            for x in self.iter_elements(start_page):
                res_list.append(x)
                if (len(res_list) == last):
                    break
            self._per_page = per_page
            return res_list

        if self._iri_filter is not None:
            raise TypeError(f"Index is prohibited if you use IRI types")
        if item < 0:
            raise TypeError(f"Negative index is not supported")
        page = (item // self._per_page) + 1
        if page != self._page:
            self._set_page(page)
        idx = item % self._per_page
        elm: AbstractElement = super().__getitem__(idx)
        elm.load()
        return elm

    def __iter__(self):
        yield from self.iter_elements()

    @property
    def page(self) -> int:
        """
        The currently loaded page number (1-based).

        :return: The current page number
        """
        return self._page

    @page.setter
    def page(self, page: int):
        """
        The currently loaded page number (1-based). Setting it loads that page from the server.
        """
        self._set_page(page)

    def _set_page(self, page: int) -> bool:
        if self._fixed_length:
            self._page = page
            return page == 1
        if page > 0 and page <= self.max_page:
            self._page = page
            self.load_elements(**self._load_options)
            return True
        return False

    def iter_elements(self, start_page=1):
        """
        Iterate over all elements across all pages, loading each page from the server on demand.

        Starting at ``start_page``, every page is fetched and its elements yielded; if an IRI filter
        is set only elements whose JSON-LD ``@type`` matches the filter are yielded.

        :param start_page: page number to start iterating from (1-based)

        :return: Generator over the elements
        """
        self._page = start_page - 1
        while self._set_page(self.page + 1):
            for elem in super().__iter__():
                if self._iri_filter is None or self._iri_filter == elem.json_ld['@type']:
                    yield elem

    def iter_pages(self):
        """
        Iterate over all pages, loading each from the server on demand.

        :return: Generator yielding this ElementSet once per page (with that page loaded)
        """
        self._page = 0
        while self._set_page(self.page + 1):
            yield self

    def next_page(self):
        """
        Load the next page from the server.

        :return: This ElementSet with the next page loaded
        """
        self._set_page(self.page + 1)
        return self

    def prev_page(self):
        """
        Load the previous page from the server.

        :return: This ElementSet with the previous page loaded
        """
        self._set_page(self.page - 1)
        return self

    def load_elements(self, per_page: int | None = None, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None, product_only: bool = False):
        """
        Load the current page of elements from the server into this ElementSet.

        Updates :attr:`max_page` and the total length from the server's ``X-Total-Pages`` and
        ``X-Total`` response headers, then replaces the current contents with the page's elements.

        :param per_page: number of elements per page (kept for subsequent page loads)
        :param updated_to_date: only fetch elements updated before this date/time
        :param updated_from_date: only fetch elements updated after this date/time
        :param product_only: if True only samples which are products in a reaction are returned

        :raises ValueError: if no collection_id is set on this ElementSet
        :raises RequestException: if the server responds with a non-200 status code
        """
        if per_page is not None:
            self._per_page = per_page
        if self._collection_id is None:
            raise ValueError('load_elements only works if collection_id is set!')

        self._load_options = {
            'updated_to_date': updated_to_date,
            'updated_from_date': updated_from_date,
            'product_only': product_only,
            'per_page': per_page,
        }

        segments = GenericSegments(self._session)
        payload = {'page': self.page,
                   'per_page': self._per_page,
                   'filter_created_at': False,
                   'product_only': product_only,
                   'el_type': self._element_type['name']}

        if updated_from_date:
            payload['from_date'] = int(updated_from_date.timestamp())

        if updated_to_date:
            payload['to_date'] = int(updated_to_date.timestamp())

        # Always `collection_id`. v4 has no `sync_collection_id`: Grape ignored the unknown
        # param and CollectionHelpers fell back to `klass.for_user(current_user.id)` — so reading
        # a shared collection silently returned EVERYTHING THE CALLER OWNS instead. Measured on
        # the seeded stack: collection_id=11 -> 4 samples, sync_collection_id=11 -> 193.
        payload['collection_id'] = self._collection_id
        res = self._session.get(self._get_url() + '.json',
                                data=payload)
        if res.status_code != 200:
            raise request_error(res, f'listing {self._element_type["name"]} of collection {self._collection_id}')

        try:
            self.max_page = int(res.headers.get('X-Total-Pages', 1))
            total = res.headers.get('X-Total')
            self._length = int(total) if total is not None else None
        except:
            pass
        self.clear()
        elements = res.json().get(self._get_result_key() + 's', [])
        for json_data in elements:
            element = self._get_element_class()(segments, self._session, json_data=json_data)
            # The listing contains only part of the data (e.g. no amounts)
            element.mark_partial()
            self.append(element)

    def load_element(self, id: int) -> AbstractElement:
        """
        Create an element of this set's type for the given DB id and add it to the set.

        :param id: DB id of the element to load

        :return: The created element (loaded lazily on access)
        """
        segments = GenericSegments(self._session)
        s = self._get_element_class()(segments, self._session, id=id,
                                      element_type=self._element_type['name'])
        self.append(s)
        return s

    def new_element(self, json_data: dict, **kwargs) -> AbstractElement:
        """
        Create a new element of this set's type from JSON data and add it to the set.

        :param json_data: JSON data used to initialize the element
        :param kwargs: additional keyword arguments passed to the element constructor

        :return: The newly created element
        """
        segments = GenericSegments(self._session)
        s = self._get_element_class()(segments, self._session, json_data=json_data, **kwargs)
        self.append(s)
        return s

    def _get_element_class(self) -> type[AbstractElement]:
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
