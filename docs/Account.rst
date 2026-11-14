Account and profile
===================

.. code-block:: python

    profile = instance.profile()
    profile.show_external_name = True
    profile.save()
    instance.save_ketcher_options({'showAtomIds': True})
    instance.set_short_label_counter('samples', 100)

API tokens are long-lived credentials for scripts (``Instance(url).login_token(token)``). The ELN
issues them only for accounts with two-factor login, against a current one-time password:

.. code-block:: python

    if not instance.two_factor_enabled():
        instance.request_two_factor_change()      # the ELN emails the confirmation link
    token = instance.create_api_token(otp='123456', name='CI', expires_in_days=90)

.. autoclass:: chemotion_api.profile.Profile
    :members:
.. automodule:: chemotion_api.account
    :members: ApiToken, OtpRequired, create_api_token, revoke_api_token
.. automodule:: chemotion_api.scifinder
    :members: ScifinderCredential, search
