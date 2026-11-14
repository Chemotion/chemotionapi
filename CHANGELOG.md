# Changelog

The version scheme tracks the server: `312.x.y` ↔ ELN 3.1.2, `211.x.y` ↔ ELN 2.1.1.
For an ELN v4 server, use the `4xx` line instead.

## 🚨 312.1.0 — wrong-type generic elements, and four device methods that never worked

### Fixed: `get_generic_by_name()` could return an element of the wrong type ([#14])

Asking for one generic type and passing the id of another returned the other element, silently:

```python
instance.get_generic_by_name("elyte", 2).klass_name   # -> "ecell"
```

The name was only checked against the list of types the server knows; it never constrained the
lookup. The server resolves a generic element **by id alone**, so the id decided what came back
and the caller got an object of the wrong type with nothing to indicate it. Both methods now
verify the element's `klass_name` and raise `ValueError` naming both types.

`get_generic_by_label()` delegated to the same path and had the same bug, as the report suspected.

Reported by **@SebaWitt**. Also present on the v4 line and fixed there.

[#14]: https://github.com/Chemotion/chemotionapi/issues/14

### Removed: four device methods that never worked

**Breaking, but only for calls that could not have succeeded.** Four public methods are gone.
Three posted to a route no Chemotion release serves, so every call raised `ConnectionError` on a
404:

| Removed | Called |
|---|---|
| `DeviceManager.get_jwt_for_device()` | `GET /api/v1/devices/remote/jwt/:id` |
| `DeviceManager.create_new_device()` | `POST /api/v1/devices/remote/create` |
| `Device.get_jwt()` | (via `get_jwt_for_device`) |

Checked against ELN 3.1.1, 3.1.2, 3.1.3, 4.0.0 and 4.0.1: the `devices/remote` namespace exists
in none of them, and appears in no version of the server's own Swagger document.

**Neither could be repaired in place.** There is no device-JWT route in any release. And
`POST /api/v1/devices` describes an *instrument* — `title`, `code`, `types`, `samples` — not the
device-*user* these methods took (`first_name`, `last_name`, `name_abbreviation`), so pointing
them at it would have changed what they mean rather than fixed them.

The fourth, `AdminMenu.greate_device()`, reached a real route — `POST
/api/v1/admin/group_device/create` — which cannot create a device (see `Admin.create_device()`
below). Against ELN 3.1.2 it returned `{'error': 'Validation failed: Name Please enter a name'}`
from a `201`, so a caller saw a dict and no exception: the failure was silent. `AdminMenu` remains
as an empty class, so an import of it keeps working.

`DeviceManager` itself remains: `add_users_to_group()` and `add_users_to_group_by_id()` use
`PUT /api/v1/admin/group_device/update/:id`, which is real and unaffected.

### If you called these

To create a device user, use **`Admin.create_device()`** — whose signature changed in this
release, because it was broken too:

```python
admin = instance.get_user()                         # an Admin, when logged in as one
device = admin.create_device("Device Name", "ABC")  # was (first_name, last_name, abbreviation)
```

It posted to `/api/v1/admin/group_device/create` with `rootType: 'Device'`, supplying
`first_name`/`last_name`. But `Device` has `validates :name, presence: true` and that endpoint
declares no `name` parameter, so Grape's `declared` dropped any attempt to pass one. **Every call
failed** with `Validation failed: Name Please enter a name`. It now posts to
`/api/v1/admin_devices`, which takes `name` and `name_abbreviation` (plus optional `email` and
`serial_number`).

`Admin.create_group()` is unaffected and still uses the group endpoint: groups carry no such
validation.

It also raises on a rejected create. The device endpoint answers a duplicate `name_abbreviation`
with **`201` and an `errors` body** — plural, where the group endpoint uses `error` — so checking
the status code, or only the singular key, reads a failure as a success.

There is no replacement for `get_jwt_for_device()` / `Device.get_jwt()`, because the server
offers none.

### Changed: a success reply that reports a failure now raises

The ELN answers some refused requests with a success status and the reason in the body:
`{"errors": …}`, `{"error": …}` or `{"success": false}`. A method that checked only the status code
read these as success. The connection now checks every JSON reply and raises
`ChemotionRejectedError`, with the server's reason in its message and the decoded reply in `body`.
It is a `ConnectionError` and a `ValueError` as well, so existing handlers keep catching it. Empty
values (`{"error": 0}`, `{"errors": []}`) count as success.

### Fixed: five results that were wrong without an error

- **`ElementSet.page = n` loads page `n`.** It was ignored for any page not yet seen: before the
  first load every page but the first was refused, and the set stayed where it was without a word.
  A page that does not exist now raises `IndexError`. Page 1 of an empty collection is fine.
- **The inbox lists each sender box once.** With exactly 20, 40, … boxes it requested one page too
  many, which the server answers with page 1 again, so every box appeared twice.
- **`insert-dataset` inserts the dataset, or says why not.** The term's label and definition, which
  come from the EBI ontology service, were pasted into the SQL statement: an apostrophe, common in
  definitions, broke it, and psql's exit code was never checked. They are now passed as psql
  variables, and a failure raises `ChildProcessError` with psql's message.
- **A molecule assigned to a sample from a listing is kept.** Setting `sample.molecule` on a
  sample obtained by iterating a collection loaded the sample's full record afterwards, which
  replaced the new molecule with the stored one.
- **Image lookup by version picks that version.** Matching by ending let version `1.2` select the
  `eln-1.1.2` image. Versions now match exactly, every page of Docker Hub's tag list is read, and
  the requests time out instead of hanging. With no `eln-` tag at all, it raises `LookupError`.

### Also

- **Joining collection paths no longer drops the segments after an absolute one.**
  `'a', '/b', 'c', 'd'` gave `/b/`; it now gives `/b/c/d`. A later absolute segment still resets
  the path, so `'a', '/b', '/c', 'd'` gives `/c/d`.
- **Three tests were deleted and one added.** `test_get_admin_devices` was a bare `pass` over a
  commented-out body; `test_create_devices` was a `# TODO` followed by `return`; and
  `test_get_user` asserted that `create_new_device` *raises*, which held only because the route
  404s. All three read as coverage — in the file and in a collected-test count — while asserting
  nothing about the code. That is how these endpoints went unnoticed for four releases.
  `test_create_device_and_delete` replaces them, covering `Admin.create_device()` against the
  real route, including the duplicate-abbreviation case the server answers with `201` and an
  `errors` body.
