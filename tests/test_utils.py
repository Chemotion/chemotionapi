from chemotion_api.utils import TypedList


def test_type_list():


    a = TypedList(int, [1,2,3])
    a.append(1)
    a.extend([6,7,8])
    a[0] = 3
    a += [9]
    b = a + [10]
    assert a == [3,2,3,1,6,7,8,9]
    assert b == [3,2,3,1,6,7,8,9,10]
    try:
        a[4] = 3.5
        assert False
    except TypeError:
        assert True