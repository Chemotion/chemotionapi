Getting Started
================


Installation/Usage:
*******************
The package has been published on PyPi, it can be installed using pip.

.. warning::
   This is the **v4-only** release line. It requires a Chemotion ELN **v4** server and refuses to
   connect to anything else; for an ELN 3.1.x server install the ``312.x`` line instead. It needs
   Python 3.14. If the version published on PyPI is still from an older line, install from
   source as below.

.. code-block:: bash

    git clone https://github.com/Chemotion/chemotionapi.git
    cd chemotionapi
    pip install .

The package uses `python-magic <https://pypi.org/project/python-magic/>`__ to detect the type of uploaded files,
so the ``libmagic`` library must also be installed (see below).

The FAIR ``.eln`` export additionally needs the semantic stack (``pydantic``, ``rdflib``,
``linkml-runtime``, ``chem_dcat_ap``, ``dcat_ap_plus``); these come in as dependencies of the package.
``PostgreSQL`` client tools are required only for the ``chemotion_api`` command line's
backup/restore subcommands, which operate on a dockerized instance's database.

The instance CLI (Example 4) additionally needs `Docker <https://docs.docker.com/>`__ with Docker Compose,
and the PostgreSQL client tools (``pg_dump``, ``pg_restore``, ``createdb``, ``dropdb``) for ``backup`` and ``restore``.
For instructions about how to install ``PostgreSQL`` please refer `here <https://www.postgresql.org/>`__.

Installing libmagic
_________________________

**Debian/Ubuntu**


.. code-block:: sh

    sudo apt-get install libmagic1

**Windows**

You'll need DLLs for libmagic. @julian-r maintains a pypi package with the DLLs, you can fetch it with:

.. code-block:: sh

    pip install python-magic-bin

**OSX**

* When using Homebrew: brew install libmagic
* When using macports: port install file

Example 1) Create a new Reaction
**************************************************
.. code-block:: python

    """
    This Example shows all necessary steps to create a new Reaction.

    1) We will login to a locally running Instance of chemotion
    2) We will create a new collection
    3) We will create 3 new samples and add some sample Properties
    4) We finally create a new Reaction.
    """
    import datetime

    from chemotion_api.elements.reaction import Reaction
    from chemotion_api.elements.sample import Sample
    from chemotion_api import Instance
    from chemotion_api.collection import RootCollection, Collection

    if __name__ == '__main__':
        # Initialize a new Instance connection
        instance = Instance('https://chemotion.dept.uni.de')
        try:
            # Test if the host is available and login using your username and password
            instance.test_connection().login('YOUR_USERNAME', 'YOUR_PASSWORD')
        except ConnectionError:
            # Exit if connection fails
            exit(1)
        except PermissionError:
            # Exit if Login fails
            exit(2)

        # Get root collection object
        root_col: RootCollection = instance.get_root_collection()
        # Get or create collection 'Main Test'
        mt_col: Collection = root_col.get_or_create_collection('Main Test')
        # Create a new Collection with the current date/time as label
        now_as_str = datetime.datetime.now().isoformat()
        project_col = mt_col.get_or_create_collection(now_as_str)

        # Create sample for Ammonium hydroxide
        sample_amm: Sample = project_col.new_sample_smiles('N.O')
        sample_amm.properties['external_label'] = "Ammonium hydroxide"
        sample_amm.save()
        # Create sample for Copper
        sample_copper: Sample = project_col.new_sample_smiles('[Cu]')
        sample_copper.properties['external_label'] = "Copper"
        sample_copper.save()
        # Create sample for product
        sample_res: Sample = project_col.new_sample_smiles('[Cu+2]([NH3])([NH3])([NH3])([NH3])[Cl-].[Cl-]')
        sample_res.save()

        # Create a new Reaction
        reaction: Reaction = project_col.new_reaction()

        # Add samples to the Reaction. Starting materials and reactants are added as splits,
        # products as copies of the samples.
        reaction.properties['starting_materials'].append(sample_amm)
        reaction.properties['reactants'].append(sample_copper)
        reaction.properties['products'].append(sample_res)

        # Add temperature profile to the Reaction
        reaction.properties['temperature'].add_time_point(hour=0,minute=0,second=0, temperature=50)
        reaction.properties['temperature'].add_time_point(hour=1,minute=0,second=0, temperature=100)
        # Save reaction
        reaction.save()

Example 2) Share a Collection
**************************************************

.. code-block:: python

    """
    This Example shows all necessary steps to share a collection.

    1) Create a group
    2) Find all users
    3) Share collection
    """

    from chemotion_api.collection import CollectionSharePermission
    from chemotion_api.user import Person, Group

    from chemotion_api import Instance

    if __name__ == '__main__':
        # Initialize a new Instance connection
        instance = Instance('https://chemotion.dept.uni.de')
        try:
            # Test if the host is available and login using your username and password
            instance.test_connection().login('YOUR_USERNAME', 'YOUR_PASSWORD')
        except ConnectionError:
            # Exit if connection fails
            exit(1)
        except PermissionError:
            # Exit if Login fails
            exit(2)
        # Get your user data
        me: Person = instance.get_user()
        # Create new group
        stg: Group = me.create_group('Test', 'Group', "STG")
        # Find all users that need to be added to the group
        users = instance.find_user_by_name('Tom') + instance.find_user_by_name('Jerry')
        # Add the user
        stg.add_users(*users)
        # Share collection with STG
        # detail_level is required: 0 discloses least, 10 every field (and lets the
        # recipients export the collection). There is no default — it is your decision.
        instance.get_root_collection().get_collection('Main Test').share(
            CollectionSharePermission.EditElements, stg, detail_level=5)

        # Revoke it again (with no users given, every share on the collection goes):
        instance.get_root_collection().get_collection('Main Test').unshare(stg)

Example 3) Upload/Load Attachment
**************************************************

.. code-block:: python

    """
    In this example we load a Research Plan and add an attachment

    1) Load a Research Plan
    2) Add an attachment
    3) Save an attachment as file
    """

    from chemotion_api.collection import CollectionSharePermission
    from chemotion_api.user import Person, Group

    from chemotion_api import Instance

    if __name__ == '__main__':
        # Initialize a new Instance connection
        instance = Instance('https://chemotion.dept.uni.de')
        try:
            # Test if the host is available and login using your username and password
            instance.test_connection().login('YOUR_USERNAME', 'YOUR_PASSWORD')
        except ConnectionError:
            # Exit if connection fails
            exit(1)
        except PermissionError:
            # Exit if Login fails
            exit(2)
        # Load the research plan with ID 1
        s = instance.get_research_plan(1)

        s.attachments.add_file('./GeneralSetup.png')
        # Save and reload the research plan. New attachments can only be loaded after reloading.
        s.save(load_after_save=True)

        # Attachments are found by their file name, without the directory
        f = s.attachments.load_attachment(filename="GeneralSetup.png")
        os.makedirs('./TEST_TO_DEL', exist_ok=True)
        f.save_file('./TEST_TO_DEL')

Example 4) Instance CLI
**************************************************

.. raw:: html

    <style>
    .warning {
        color:red;
        font-weight: bold;
        font-size: 18px;
    }
    </style>

.. role:: warning

:warning:`THIS CLI TOOLS MUST NOT BE USED FOR PRODUCTIVE INSTANCES`

THE CLI tool is only for development & test usages. For Productive Instances please use `ChemCLI <https://github.com/Chemotion/ChemOrc/>`_

.. code-block:: sh

    # This Example shows all necessary steps to back up and restore an instance.
    #
    # 1) Create a Instance
    # 2) Make a backup
    # 3) Restore the backup

    > chemotion_api --help
    Usage: chemotion_api [OPTIONS] COMMAND [ARGS]...

    Options:
      --help  Show this message and exit.

    Commands:
      available-versions    Fetch all available Version of Chemotion
      backup                Make a dump of the Chemotion PostgreSQL
      change-port           Change the port on which the ELN can be reached...
      change-postgres-port  Change the port on which the ELN DB can be...
      check                 Check all running containers
      down                  Same as docker compose down <services>
      insert-dataset        Insert a dataset.
      new                   Create a new docker-compose file with all...
      restore               Restore a ProstgreSQL dump.
      stop                  Same as docker compose stop <services>
      up                    Same as docker compose up <services>
      update-version        Updated the version of Chemotion instance

    # Create a new Instance (the first prompt asks for the docker compose file path)
    > chemotion_api new
    Your name [./docker-compose.yml]:
    Specify a version [latest]: 4.0.0
    Public ELN url [http://localhost:<ELN_PORT>]:
    Port on which the ELN can be reached [4000]:
    Port on which the Postgres DB can be reached [5432]:
    Port on which the Adminer can be reached [8080]:

    # Run Instance
    > chemotion_api up

    # Make a DB backup
    > chemotion_api backup
    Output tar dump file [<db_name>_<time_stamp>.tar]: test_dump.tar


    # Restore a DB backup
    > chemotion_api restore
    Your tar dump file: test_dump.tar


Example 5) Export a Collection to a ``.eln`` (RO-Crate)
******************************************************************

.. code-block:: python

    """
    Export a collection as a FAIR RO-Crate 1.2 .eln archive (chem-dcat-ap metadata).

    Authorship is mandatory and explicit: each author needs an ORCID iD and at least one
    ROR-identified affiliation. See :doc:`FairExport`.
    """
    from chemotion_api import Instance, Author, AuthorAffiliation

    with Instance('https://chemotion.dept.uni.de',
                  username='YOUR_USERNAME', password='YOUR_PASSWORD') as instance:
        col = instance.get_or_create_collection('My Synthesis Project')

        # Authors must be set manually (no logged-in-user default)
        col.set_authors([
            Author(name='Josiah Carberry', orcid='0000-0002-1825-0097',
                   affiliations=[AuthorAffiliation(name='Brown University',
                                                   ror='https://ror.org/05gq02987')]),
        ])

        # Analyses are annotated with measurement-technique ontology terms (embedded CHMO code -> OLS)
        col.export_eln('my_project.eln')


Example 6) Offline export from an ``export collection`` ZIP
******************************************************************

.. code-block:: python

    """
    Convert Chemotion's native "export collection" ZIP into a .eln with NO live server.
    Samples and reactions are reconstructed offline. See :doc:`OfflineIngestion`.
    """
    from chemotion_api import Author, AuthorAffiliation
    from chemotion_api.offline import import_export_zip

    col = import_export_zip('my_export_collection.zip', label='My Project')
    col.export_eln(
        'my_project.eln',
        authors=[Author(name='Josiah Carberry', orcid='0000-0002-1825-0097',
                        affiliations=[AuthorAffiliation(name='Brown University',
                                                        ror='https://ror.org/05gq02987')])],
    )

Every command has a ``--help`` option listing all of its options, e.g. ``chemotion_api backup --help``.

