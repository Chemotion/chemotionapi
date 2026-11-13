Device description
===================

A device description records an instrument: its type, vendor, version, location, operators and
how it is used. Create one with
:meth:`chemotion_api.collection.Collection.new_device_description`, fetch one with
:meth:`chemotion_api.Instance.get_device_description`, and list them with
:meth:`chemotion_api.collection.Collection.get_device_descriptions`.

``properties`` holds the commonly used fields, such as ``name``, ``serial_number``,
``vendor_company_name``, ``device_type_name``, ``room`` and ``general_tags``. Every field is
optional. The ELN stores many more, such as maintenance schedules; fields the client does not
expose are kept unchanged when you save.

.. code-block:: python

    device = col.new_device_description()
    device.properties['name'] = 'NMR 400'
    device.properties['vendor_company_name'] = 'Bruker'
    device.properties['general_tags'] = ['nmr']
    device.save()

    for device in col.get_device_descriptions():
        print(device.properties['name'], device.ontology_terms())

``ontology_terms()`` returns the ontology annotations an ELN administrator picked for the device,
as ``{'iri': …, 'label': …}`` entries. If the ELN refuses to create a device description,
``save()`` raises ``ValueError`` with the server's reasons.

.. autoclass:: chemotion_api.elements.device_description.DeviceDescription
    :members:
