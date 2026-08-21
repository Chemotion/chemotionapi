Getting Started
================


Installation/Usage:
*******************
The package has been published on PyPi, it can be install using pip.

.. code-block:: bash

    pip install chemotion-api

``imagemagick`` & ``PostgreSQL`` must also be installed.
For instructions about how to install, as well as the full documentation of, ``imagemagick`` please refer `here <https://imagemagick.org/index.php>`__.
For instructions about how to install, as well as the full documentation of, ``PostgreSQL`` please refer `here <https://www.postgresql.org/>`__.

Installing imagemagick
_________________________

To prevent problems!

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

Example 1) Create a new Reacton
**************************************************
.. code-block:: python

    """
    This Example shows all necessary steps to create a new Reaction.

    1) We will login to a locally running Instance of chemotion
    2) We will create a new collection
    3) We will create 2 new samples and add some sample Properties
    4) We finally crate a new Reaction.
    """
    import datetime

    from chemotion_api.elements.reaction import Reaction
    from chemotion_api.elements.sample import Sample
    from chemotion_api import Instance
    from chemotion_api.collection import RootCollection, Collection

    if __name__ == '__main__':
        # Initialize a new Instance connection
        instance = Instance('http://localhost:3354')
        try:
            # Test if the host is available and login using your username and password
            instance.test_connection().login('MSU', '1234qweR!')
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

        # Create a new Reacton
        reaction: Reaction = project_col.new_reaction()

        # Add sample to the Reacton
        reaction.properties['starting_materials'].append(sample_amm)
        reaction.properties['reactants'].append(sample_copper)
        reaction.properties['products'].append(sample_res)

        # Add temperature profile to the Reacton
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
    2) Find all user
    3) Share collection
    """

    from chemotion_api.collection import CollectionSharePermission
    from chemotion_api.user import Person, Group

    from chemotion_api import Instance

    if __name__ == '__main__':
        # Initialize a new Instance connection
        instance = Instance('http://localhost:3354')
        try:
            # Test if the host is available and login using your username and password
            instance.test_connection().login('MSU', '1234qweR!')
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
        instance.get_root_collection().get_collection('Main Test').share(CollectionSharePermission.EditElements, stg)
        # Save reaction
        reaction.save()

Example 3) Upload/Load Attachment
**************************************************

.. code-block:: python

    """
    In This example we load a Research Plan and add an attachment

    1) Load a Research Plan
    2) Add an attachment
    3) Save an attachment as file
    """

    from chemotion_api.collection import CollectionSharePermission
    from chemotion_api.user import Person, Group

    from chemotion_api import Instance

    if __name__ == '__main__':
        # Initialize a new Instance connection
        instance = Instance('http://localhost:3354')
        try:
            # Test if the host is available and login using your username and password
            instance.test_connection().login('MSU', '1234qweR!')
        except ConnectionError:
            # Exit if connection fails
            exit(1)
        except PermissionError:
            # Exit if Login fails
            exit(2)
        # Get your user data
        s = instance.get_research_plan(1)

        s.attachments.add_file('./GeneralSetup.png')
        s.save()

        f = s.attachments.load_attachment(filename="./GeneralSetup.png")
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

    # This Example shows all necessary steps to share a collection.
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
      change-port           Change the from the host system available port of...
      change-postgres-port  Update the Chemotion version in a docker compose...
      check                 Check all running containers
      down                  Same as docker-compose down <services>
      new                   Create a new docker-compose file and all needed...
      restore               Restore a ProstgreSQL dump.
      stop                  Same as docker-compose stop <services>
      up                    Same as docker-compose up <services>
      update-version        Updated the version of a docker-compose file

    # Create a new Instance
    > chemotion_api new
    Your name [./docker-compose.yml]:
    Specify a version [latest]: 1.9.3
    Public ELN url [http://localhost:<ELN_PORT>]:
    Port on which the ELN can be reached [4000]:
    Port on which the PostgreSQL can be reached [5432]:
    Port on which the Adminer can be reached [8080]:

    # Run Instance
    > chemotion_api up

    # Make a DB backup
    > chemotion_api backup
    Your tar dump file [<db_name>_<time_stamp>.tar]: test_dump.tar


    # Restore a DB backup
    > chemotion_api chemotion_api restore
    Your tar dump file: test_dump.tar

