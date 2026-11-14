SBMM sample
============

A sample of a sequence-based macromolecule, such as a protein. Create one with
:meth:`chemotion_api.collection.Collection.new_sbmm_sample`, giving a UniProt accession. Fetch one
with :meth:`chemotion_api.Instance.get_sbmm_sample` and list them with
:meth:`chemotion_api.collection.Collection.get_sbmm_samples`.

``properties`` holds the sample's own fields (``name``, ``external_label``, ``purity``,
``supplier`` and others). Quantities such as ``concentration``, ``molarity`` or ``activity`` are
``{'value': …, 'unit': …}`` pairs, like a sample's amounts. The protein is available as
``macromolecule`` and is read-only.

.. code-block:: python

    s = col.new_sbmm_sample(uniprot='P69905')
    s.properties['purity'] = 0.95
    s.properties['concentration'] = {'value': 2.0, 'unit': 'g/L'}
    s.save()
    print(s.macromolecule['short_name'])

.. note::
   **Limitations.** A new sample's protein can only be chosen by UniProt accession. Proteins that
   are not in UniProt, or modified variants of one, cannot be created from this client; create
   those in the ELN's web interface. Samples created there load and save normally, and their
   protein is sent back exactly as loaded. The protein of an existing sample is read-only here.
   If either limitation affects your work, please open an issue at
   https://github.com/Chemotion/chemotionapi/issues and describe what you need.

.. autoclass:: chemotion_api.elements.sbmm_sample.SbmmSample
    :members:
