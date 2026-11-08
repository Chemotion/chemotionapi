Data in and out
===============

Collection export and import, sample import, table exports, reports, the inbox and ELN-to-ELN
transfer. Exports, imports and reports run as background jobs on the server; the client starts the
job and waits for its notification (``timeout=`` seconds), since the server does not return a job id.

Collection export and import
----------------------------

.. code-block:: python

    collection.export_zip('project.zip')                   # the ELN's native archive
    new_collections = instance.import_zip('project.zip')

.. automethod:: chemotion_api.collection.AbstractCollection.export_zip
    :no-index:
.. automethod:: chemotion_api.Instance.import_zip
    :no-index:

Importing samples
-----------------

.. code-block:: python

    result = collection.import_samples('samples.sdf')      # .sdf, .mol, .csv, .xlsx
    assert result.ok, result.message

.. automethod:: chemotion_api.collection.AbstractCollection.import_samples

Table exports
-------------

.. code-block:: python

    collection.export_elements('table.xlsx', sample, reaction)            # or file_format='sdf'
    collection.export_reaction_smiles('reactions.csv', reaction, notation='SM>>P')
    reaction.export_samples_excel('reaction_samples.xlsx')
    wellplate.download_template('plate.xlsx'); wellplate.import_spreadsheet('plate.xlsx')

.. autodata:: chemotion_api.reports.DEFAULT_EXPORT_COLUMNS
.. autodata:: chemotion_api.reports.REACTION_SMILES_NOTATIONS

Reports
-------

.. code-block:: python

    archive = instance.create_report(reaction, sample, file_name='Weekly',
                                     reaction_settings={'variations': False})
    archive.download('weekly.docx')
    reaction.report_docx('reaction.docx')       # generated right away

.. autofunction:: chemotion_api.reports.report_payload
.. autoclass:: chemotion_api.reports.Archive
    :members: download, refresh, delete

The inbox
---------

.. code-block:: python

    instance.inbox.upload('nmr.zip')
    file = instance.inbox.unlinked_attachments()[0]
    instance.inbox.assign(file, sample)          # becomes a new analysis of the sample

.. automethod:: chemotion_api.inbox.Inbox.assign

Analyses without the element
----------------------------

``element.save_analyses()`` saves names, status, content, dataset metadata and new files of the
analyses only; ``element.delete_analysis(analysis)`` deletes one right away.

Transfer to another ELN or the repository
-----------------------------------------

.. code-block:: python

    token = receiving_collection.gate_token(origin='https://sender.example.org')   # on the receiver
    collection.register_gate('https://receiver.example.org/', token)             # on the sender
    collection.check_transmission('https://receiver.example.org/')
    collection.transmit('https://receiver.example.org/')

The target has no default: the server's default is the public Chemotion Repository.
