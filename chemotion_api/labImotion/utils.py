import itertools
import re
import string
from abc import ABC, abstractmethod


def all_instances_of(lst: list, cls: type):
    return isinstance(lst, list) and all(isinstance(item, cls) for item in lst)

class ChemotionSerializable(ABC):
    @abstractmethod
    def to_dict(self) -> dict:
        pass


def generate_pkg_info():
    return {
        'pkg': {
            "name": "chem-generic-ui",
            "version": "1.4.4"
        }
    }

def generate_key(label: str, existing: list[str], max_len: int = 22, fallback: str = 'key') -> str:
    """
    Generates a template key from a label: lowercase letters joined by single underscores, starting and
    ending with a letter, at least three characters long and not in ``existing``. On a collision a letter
    suffix is appended ('strain' -> 'strain_a').

    >>> generate_key('Incubation temperature (°C)', [], max_len=40)
    'incubation_temperature_c'
    """
    base = re.sub(r'[^a-z]+', '_', label.lower()).strip('_') or fallback
    if len(base) < 3:
        base = (base + '_' + fallback)[:max_len]
    for suffix in _letter_suffixes():
        candidate = base[:max_len - len(suffix)].rstrip('_') + suffix
        if candidate not in existing:
            return candidate
    raise AssertionError('unreachable')


def _letter_suffixes():
    yield ''
    for length in itertools.count(1):
        for letters in itertools.product(string.ascii_lowercase, repeat=length):
            yield '_' + ''.join(letters)
