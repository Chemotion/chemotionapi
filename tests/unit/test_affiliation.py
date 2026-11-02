"""Unit tests for the Affiliation dataclass (chemotion_api.user.Affiliation). Offline/pure."""
from chemotion_api.user import Affiliation


def test_from_json_maps_fields_including_reserved_from_to():
    aff = Affiliation.from_json({
        "id": 7, "organization": "KIT", "department": "IBG", "group": "NFDI4Chem",
        "country": "Germany", "from": "2020-01", "to": "2024-12",
    })
    assert aff.id == 7 and aff.organization == "KIT" and aff.country == "Germany"
    assert aff.from_date == "2020-01" and aff.to_date == "2024-12"
    assert aff.raw["group"] == "NFDI4Chem"


def test_name_joins_present_units_in_order():
    assert Affiliation(organization="KIT", department="IBG", group="NFDI").name == "KIT, IBG, NFDI"
    assert Affiliation(organization="KIT").name == "KIT"
    assert Affiliation(organization="KIT", group="G").name == "KIT, G"  # skips missing department


def test_name_empty_when_no_org():
    assert Affiliation().name == ""


def test_to_dict_uses_grape_from_to_keys():
    d = Affiliation(id=1, organization="KIT", from_date="2020", to_date=None).to_dict()
    assert d["from"] == "2020" and d["to"] is None and "from_date" not in d
