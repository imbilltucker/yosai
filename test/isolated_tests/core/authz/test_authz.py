import pytest
import collections
import itertools
from unittest import mock

from yosai.core import (
    DefaultPermission,
    IndexedAuthorizationInfo,
    ModularRealmAuthorizer,
    UnauthorizedException,
    event_bus,
    realm_abcs,
)

# -----------------------------------------------------------------------------
# ModularRealmAuthorizer Tests
# -----------------------------------------------------------------------------

@mock.patch.object(ModularRealmAuthorizer, 'register_cache_clear_listener')
def test_mra_init_realms(mock_rccl, modular_realm_authorizer_patched):
    mra = modular_realm_authorizer_patched

    mock_authz_realm = mock.create_autospec(realm_abcs.AuthorizingRealm)
    faux_realm = type('FauxRealm', (object,), {})()
    realms = (mock_authz_realm, faux_realm,)
    mra.init_realms(realms)
    mock_rccl.assert_called_once_with()


def test_mra_assert_realms_configured_success(modular_realm_authorizer_patched):
    """
    unit tested:  assert_realms_configured

    test case: if the realms attribute isn't set, an exception raises
    """
    mra = modular_realm_authorizer_patched
    assert mra.assert_realms_configured() is None


def test_mra_assert_realms_configured_fail(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  assert_realms_configured

    test case:  if the realms attribute isn't set, an exception raises
    """
    mra = modular_realm_authorizer_patched
    monkeypatch.setattr(mra, 'realms', None)
    with pytest.raises(ValueError):
        mra.assert_realms_configured()


def test_mra_private_has_role_true_and_false(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  _has_role

    test case:
    confirms that _has_role iterates over the authorizing realms and yields
    a value from each realm consisting of a tuple(roleid, Boolean)
    """
    mra = modular_realm_authorizer_patched

    def has_role_yields_true(identifiers, roleid_s):
        for x in roleid_s:
            yield (x, True)

    def has_role_yields_false(identifiers, roleid_s):
        for x in roleid_s:
            yield (x, False)

    # there are three realms set for this fixture:
    monkeypatch.setattr(mra.realms[0], 'has_role', has_role_yields_false)
    monkeypatch.setattr(mra.realms[1], 'has_role', has_role_yields_false)
    monkeypatch.setattr(mra.realms[2], 'has_role', has_role_yields_true)

    result = {(roleid, hasrole) for roleid, hasrole in
              mra._has_role('identifiers', {'roleid123'})}
    assert result == {('roleid123', False), ('roleid123', True)}


def test_mra_private_is_permitted_true_and_false(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  _is_permitted

    test case:
    confirms that _is_permitted iterates over the authorizing realms and yields
    a value from each realm consisting of a tuple(Permission, Boolean)
    """
    mra = modular_realm_authorizer_patched

    def is_permitted_yields_true(identifiers, permission_s):
        for x in permission_s:
            yield (x, True)

    def is_permitted_yields_false(identifiers, permission_s):
        for x in permission_s:
            yield (x, False)

    # there are three realms set for this fixture:
    monkeypatch.setattr(mra.realms[0], 'is_permitted', is_permitted_yields_false)
    monkeypatch.setattr(mra.realms[1], 'is_permitted', is_permitted_yields_false)
    monkeypatch.setattr(mra.realms[2], 'is_permitted', is_permitted_yields_true)

    result = {(permission, ispermitted) for permission, ispermitted in
              mra._is_permitted('identifiers', {'permission1'})}
    assert result == {('permission1', False), ('permission1', True)}


def test_mra_is_permitted_succeeds(modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  is_permitted

    test case:
    - for each permission passed, passes the permission to the private _is_permitted
      method
    - every authorizing realms is consulted for each permission and only one realm needs
      to return true in order for the permission to be granted
    """
    mra = modular_realm_authorizer_patched

    def is_permitted_yields_true(identifiers, permission_s):
        for x in permission_s:
            yield (x, True)

    def is_permitted_yields_false(identifiers, permission_s):
        for x in permission_s:
            yield (x, False)

    # there are three realms set for this fixture:
    monkeypatch.setattr(mra.realms[0], 'is_permitted', is_permitted_yields_false)
    monkeypatch.setattr(mra.realms[1], 'is_permitted', is_permitted_yields_false)
    monkeypatch.setattr(mra.realms[2], 'is_permitted', is_permitted_yields_true)

    with mock.patch.object(mra, 'assert_realms_configured') as mra_arc:
        mra_arc.return_value = None

        with mock.patch.object(mra, 'notify_event') as mra_nr:
            mra_nr.return_value = None

            results = mra.is_permitted('identifiers', ['permission1', 'permission2'], False)

            mra_arc.assert_called_once_with()

            assert set(results) == set([('permission1', True), ('permission2', True)])


def test_mra_is_permitted_fails(modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  is_permitted

    test case:
    - for each permission passed, passes the permission to the private _is_permitted
      method
    - every authorizing realms is consulted for each permission and only one realm needs
      to return true in order for the permission to be granted
    """
    mra = modular_realm_authorizer_patched

    def is_permitted_yields_false(identifiers, permission_s):
        for x in permission_s:
            yield (x, False)

    # there are three realms set for this fixture:
    monkeypatch.setattr(mra.realms[0], 'is_permitted', is_permitted_yields_false)
    monkeypatch.setattr(mra.realms[1], 'is_permitted', is_permitted_yields_false)
    monkeypatch.setattr(mra.realms[2], 'is_permitted', is_permitted_yields_false)

    with mock.patch.object(mra, 'assert_realms_configured') as mra_arc:
        mra_arc.return_value = None

        results = mra.is_permitted('identifiers', {'permission1', 'permission2'}, False)

        mra_arc.assert_called_once_with()
        assert set(results) == set([('permission1', False), ('permission2', False)])


@pytest.mark.parametrize('mock_results, logical_operator, expected',
                         [({('permission1', True), ('permission2', True)}, all, True),
                          ({('permission1', True), ('permission2', False)}, all, False),
                          ({('permission1', False), ('permission2', False)}, all, False),
                          ({('permission1', True), ('permission2', True)}, any, True),
                          ({('permission1', True), ('permission2', False)}, any, True),
                          ({('permission1', False), ('permission2', False)}, any, False)])
def test_mra_is_permitted_collective(
        modular_realm_authorizer_patched, monkeypatch, mock_results,
        logical_operator, expected):
    """
    unit tested:  is_permitted_collective

    test case:
    a collection of permissions receives a single Boolean
    """
    mra = modular_realm_authorizer_patched
    monkeypatch.setattr(mra, 'is_permitted', lambda x,y,log_results: mock_results)
    with mock.patch.object(mra, 'assert_realms_configured') as mra_arc:
        mra_arc.return_value = None
        with mock.patch.object(mra, 'notify_event') as mra_ne:
            mra_ne.return_value = None

            results = mra.is_permitted_collective({'identifiers'},
                                                  ['perm1', 'perm2'],
                                                  logical_operator)
            mra_arc.assert_called_once_with()
            assert results == expected
            if expected is True:
                mra_ne.assert_called_once_with({'identifiers'},
                                               ['perm1', 'perm2'],
                                               'AUTHORIZATION.GRANTED',
                                               logical_operator)

            else:
                mra_ne.assert_called_once_with({'identifiers'},
                                               ['perm1', 'perm2'],
                                               'AUTHORIZATION.DENIED',
                                               logical_operator)



def test_mra_check_permission_collection_raises(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  check_permission

    test case:
    check_permission raises an exception if any permission isn't entitled
    """
    mra = modular_realm_authorizer_patched
    monkeypatch.setattr(mra, 'is_permitted_collective', lambda x,y,z: False)
    with mock.patch.object(mra, 'assert_realms_configured') as mra_arc:
        mra_arc.return_value = None

        with pytest.raises(UnauthorizedException):
            mra.check_permission('arbitrary_identifiers', ['perm1', 'perm2'], all)
            mra_arc.assert_called_once_with()


def test_mra_check_permission_collection_succeeds(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  check_permission

    test case:
    check_permission raises an exception if any permission isn't entitled,
    and nothing returned if success
    """
    mra = modular_realm_authorizer_patched
    monkeypatch.setattr(mra, 'is_permitted_collective', lambda x,y,z: True)

    with mock.patch.object(mra, 'assert_realms_configured') as mra_arc:
        mra_arc.return_value = None

        mra.check_permission('arbitrary_identifiers', ['perm1', 'perm2'], all)
        mra_arc.assert_called_once_with()


def test_mra_has_role_succeeds(modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  has_role

    test case:
    - for each roleid passed, passes the roleid to the private _has_role
      method
    - every authorizing realm is consulted for each roleid and only one realm needs
      to return true in order for the has_role request to be granted
    """
    mra = modular_realm_authorizer_patched

    def has_role_yields_true(identifiers, roleid_s):
        for x in roleid_s:
            yield (x, True)

    def has_role_yields_false(identifiers, roleid_s):
        for x in roleid_s:
            yield (x, False)

    # there are three realms set for this fixture:
    monkeypatch.setattr(mra.realms[0], 'has_role', has_role_yields_false)
    monkeypatch.setattr(mra.realms[1], 'has_role', has_role_yields_false)
    monkeypatch.setattr(mra.realms[2], 'has_role', has_role_yields_true)

    with mock.patch.object(mra, 'assert_realms_configured') as mra_arc:
        mra_arc.return_value = None

        with mock.patch.object(mra, 'notify_event') as mra_nr:
            mra_nr.return_value = None

            results = mra.has_role('identifiers', {'roleid1', 'roleid2'})

            mra_arc.assert_called_once_with()

            assert set(results) == set([('roleid1', True), ('roleid2', True)])


def test_mra_has_role_fails(modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  has_role

    test case:
    - for each roleid passed, passes the roleid to the private _has_role
      method
    - every authorizing realm is consulted for each roleid and only one realm needs
      to return true in order for the has_role request to be granted
    """
    mra = modular_realm_authorizer_patched

    def has_role_yields_false(identifiers, roleid_s):
        for x in roleid_s:
            yield (x, False)

    # there are three realms set for this fixture:
    monkeypatch.setattr(mra.realms[0], 'has_role', has_role_yields_false)
    monkeypatch.setattr(mra.realms[1], 'has_role', has_role_yields_false)
    monkeypatch.setattr(mra.realms[2], 'has_role', has_role_yields_false)

    with mock.patch.object(mra, 'assert_realms_configured') as mra_arc:
        mra_arc.return_value = None

        with mock.patch.object(mra, 'notify_event') as mock_nr:
            mock_nr.return_value = None

            results = mra.has_role('identifiers', {'roleid1', 'roleid2'})

            mra_arc.assert_called_once_with()
            assert set(results) == set([('roleid1', False), ('roleid2', False)])


@pytest.mark.parametrize('param1, param2, logical_operator, expected',
                         [({('roleid1', False)}, {('roleid2', True)}, all, False),
                          ({('roleid1', True)}, {('roleid2', True)}, all, True),
                          ({('roleid1', True)}, {('roleid2', False)}, all, False),
                          ({('roleid1', False)}, {('roleid2', True)}, any, True),
                          ({('roleid1', True)}, {('roleid2', True)}, any, True),
                          ({('roleid1', True)}, {('roleid2', False)}, any, True)])
def test_mra_has_role_collective(
        modular_realm_authorizer_patched, monkeypatch, param1, param2,
        logical_operator, expected):
    """
    unit tested:  has_role_collective

    test case:
    a collection of roleids receives a single Boolean
    """
    mra = modular_realm_authorizer_patched

    monkeypatch.setattr(mra.realms[0], 'has_role', lambda x, y: param1)
    monkeypatch.setattr(mra.realms[1], 'has_role', lambda x, y: param1)
    monkeypatch.setattr(mra.realms[2], 'has_role', lambda x, y: param2)

    with mock.patch.object(ModularRealmAuthorizer, 'assert_realms_configured') as arc:
        arc.return_value = None

        with mock.patch.object(mra, 'notify_event') as mra_ne:
            mra_ne.return_value = None
            result = mra.has_role_collective('arbitrary_identifiers',
                                             ['roleid1', 'roleid2'],
                                             logical_operator)

            if expected is True:
                mra_ne.assert_called_once_with('arbitrary_identifiers',
                                               ['roleid1', 'roleid2'],
                                               'AUTHORIZATION.GRANTED',
                                               logical_operator)

            else:
                mra_ne.assert_called_once_with('arbitrary_identifiers',
                                               ['roleid1', 'roleid2'],
                                               'AUTHORIZATION.DENIED',
                                               logical_operator)

            assert result == expected and arc.called


def test_mra_check_role_raises(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  check_role

    test case:
    check_role raises an exception if any permission isn't entitled,
    and nothing returned if success
    """
    mra = modular_realm_authorizer_patched
    monkeypatch.setattr(mra, 'has_role_collective', lambda x,y,z: False)
    with mock.patch.object(ModularRealmAuthorizer, 'assert_realms_configured') as arc:
        arc.return_value = None
        with pytest.raises(UnauthorizedException):
            mra.check_role('arbitrary_identifiers', ['roleid1', 'roleid2'], all)

            arc.assert_called_once_with()


def test_mra_check_role_true(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  check_role

    test case:
    check_role raises an exception if any permission isn't entitled,
    and nothing returned if success
    """

    mra = modular_realm_authorizer_patched
    monkeypatch.setattr(mra, 'has_role_collective', lambda x,y,z: True)
    with mock.patch.object(ModularRealmAuthorizer, 'assert_realms_configured') as arc:
        arc.return_value = None

        mra.check_role('identifiers', 'roleid_s', all)
        arc.assert_called_once_with()


def test_mraa_session_clears_cache(
        modular_realm_authorizer_patched, monkeypatch):

    mra = modular_realm_authorizer_patched
    mock_authz_realm = mock.create_autospec(realm_abcs.AuthorizingRealm)
    monkeypatch.setattr(mra, 'realms', (mock_authz_realm,))
    mock_items = mock.MagicMock(identifier='identifier')
    mra.session_clears_cache(items=mock_items)

    mock_authz_realm.clear_cached_authorization_info.\
        assert_called_once_with(mock_items.identifier)


def test_mraa_authc_clears_cache(modular_realm_authorizer_patched, monkeypatch):
    mra = modular_realm_authorizer_patched
    mock_authz_realm = mock.create_autospec(realm_abcs.AuthorizingRealm)
    monkeypatch.setattr(mra, 'realms', (mock_authz_realm,))

    mra.authc_clears_cache('identifier')

    mock_authz_realm.clear_cached_authorization_info.\
        assert_called_once_with('identifier')


def test_mra_register_cache_clear_listener(
        modular_realm_authorizer_patched, monkeypatch):
    mra = modular_realm_authorizer_patched
    mock_bus = mock.create_autospec(event_bus)
    monkeypatch.setattr(mra, 'event_bus', mock_bus)

    mra.register_cache_clear_listener()

    calls = [mock.call(mra.session_clears_cache, 'SESSION.STOP'),
             mock.call(mra.session_clears_cache, 'SESSION.EXPIRE'),
             mock.call(mra.authc_clears_cache, 'AUTHENTICATION.SUCCEEDED')]

    mock_bus.subscribe.assert_has_calls(calls)
    mock_bus.isSubscribed.assert_has_calls(calls)


def test_mra_notify_event(modular_realm_authorizer_patched, monkeypatch):
    """
    test case:
    creates an Event and publishes it to the event_bus
    """
    mra = modular_realm_authorizer_patched
    items = [('permission1', True)]
    mock_bus = mock.create_autospec(event_bus)
    monkeypatch.setattr(mra, 'event_bus', mock_bus)

    mra.notify_event('identifiers', items, topic='AUTHORIZATION.RESULTS')

    mock_bus.sendMessage.assert_called_once_with('AUTHORIZATION.RESULTS',
                                                 identifiers='identifiers',
                                                 items=items,
                                                 logical_operator=None)


def test_mra_notify_event_raises(
        modular_realm_authorizer_patched, monkeypatch):
    """
    unit tested:  notify_results

    test case:
    creates an Event, tries publishes it to the event_bus,
    but fails and so raises an exception
    """
    mra = modular_realm_authorizer_patched
    monkeypatch.setattr(mra, 'event_bus', None)

    with pytest.raises(AttributeError):
        mra.notify_results('identifiers', 'result')


# -----------------------------------------------------------------------------
# IndexedAuthorizationInfo Tests
# -----------------------------------------------------------------------------

def test_iai_permissions_isset(
        indexed_authz_info, monkeypatch, permission_collection):
    """
    unit tested:  permissions (property)

    test case:
    permissions returns a complete set of every indexed Permission
    """
    info = indexed_authz_info
    monkeypatch.setattr(info, '_permissions', {'one': [1,2,3], 'two': [4,5]})
    assert info.permissions == {1,2,3,4,5}


def test_iai_permissions_setter(indexed_authz_info, monkeypatch):
    """
    unit tested:  permissions.setter

    test case:
    clears the existing permissions index and then indexes the new set of perms
    """
    info = indexed_authz_info
    mock_permissions = mock.MagicMock()
    monkeypatch.setattr(info, '_permissions', mock_permissions)

    with mock.patch.object(IndexedAuthorizationInfo, 'index_permission') as ip:
        ip.return_value = None

        testperm = 'domain1:action1'
        info.permissions = {testperm}
        ip.assert_called_once_with({testperm})

    mock_permissions.clear.assert_called_once_with()


def test_iai_add_role(indexed_authz_info):
    """
    unit tested:  add_role

    test case:
    updates the set, roles, with the new role(s)
    """
    info = indexed_authz_info
    roles = {'roleA', 'roleB'}
    info.add_role(roles)
    assert roles <= info.roles


def test_iai_add_permission(indexed_authz_info, test_permission_collection):
    """
    unit tested:  add_permission

    test case:
    adds new permission(s) to the index
    """
    info = indexed_authz_info
    tpc = test_permission_collection

    with mock.patch.object(IndexedAuthorizationInfo, 'index_permission') as ip:
        ip.return_value = None

        info.add_permission(tpc)

        ip.assert_called_once_with(tpc)


def test_iai_index_permission(indexed_authz_info, monkeypatch):
    """
    unit tested:  index_permission

    test case:
    permissions are indexed by domain and then the indexing is validated
    """
    info = indexed_authz_info
    perms = collections.defaultdict(set)
    monkeypatch.setattr(info, '_permissions', perms)
    test_results = {('domain1', 'domain1:action1:target1'),
                    ('domain2', '*:action2:*'),
                    ('domain1', 'domain1:action2:*')}
    info.index_permission(test_results)
    assert len(list(itertools.chain.from_iterable(info._permissions.values()))) == 3


@pytest.mark.parametrize('domain, expected',
                         [('domain1', {DefaultPermission('domain1:action1')}),
                          ('domainQ', set())])
def test_iai_get_permissions(indexed_authz_info, domain, expected, monkeypatch):
    """
    test case:
    returns the permissions for a specified domain or an empty set if there arent
    any
    """
    info = indexed_authz_info
    perms = collections.defaultdict(set)
    perms['domain1'].add('domain1:action1')
    monkeypatch.setattr(info, '_permissions', perms)
    result = info.get_permissions(domain)
    assert result == expected


def test_ipv_get_authzd_permissions(
        indexed_permission_verifier, monkeypatch, indexed_authz_info):
    """
    unit tested:  get_authzd_permissions

    test case:
    returns the permissions from the authzinfo that are relevant to the
    permission argument
    """
    ipv = indexed_permission_verifier
    perm = DefaultPermission('domain4:action4')

    domainperms = frozenset([DefaultPermission(domain={'domain4'},
                                               action={'action1', 'action2'}),
                             DefaultPermission(domain={'domain4'},
                                               action={'action3'},
                                               target={'target1'})])

    monkeypatch.setattr(indexed_authz_info, 'get_permissions',
                        lambda x: domainperms)

    result = ipv.get_authzd_permissions(indexed_authz_info, perm)

    assert domainperms == result


def test_ipv_is_permitted(
        indexed_permission_verifier, monkeypatch, indexed_authz_info):
    """
    unit tested:  get_authzd_permissions

    test case:
    - gets authorized permissions based on the requested permission
    - for each permission requested, confirm whether the related authorized
      permissions implies permission
    - yield the results as a tuple
    """
    ipv = indexed_permission_verifier

    dp1 = DefaultPermission('domain6:action1')
    monkeypatch.setattr(dp1, 'implies', lambda x: False)
    dp2 = DefaultPermission('domain7:action1')
    monkeypatch.setattr(dp2, 'implies', lambda x: True)
    authz_perms = frozenset([dp1, dp2])
    monkeypatch.setattr(ipv, 'get_authzd_permissions', lambda x,y: authz_perms)

    perm1 = 'domain1:action1'
    perm2 = 'domain2:action1'

    result = list(ipv.is_permitted('authz_info', [perm1, perm2]))

    assert result == [(perm1, True), (perm2, True)]

# -----------------------------------------------------------------------------
# SimpleRoleVerifier Tests
# -----------------------------------------------------------------------------

def test_srv_has_role(simple_role_verifier, indexed_authz_info):
    """
    unit tested:  has_role

    test case:
    for each role requested, yield whether has role
    """
    srv = simple_role_verifier
    test_roleids = {'role1', 'role10'}

    result = list(srv.has_role(indexed_authz_info, test_roleids))
    assert set(result) == set([('role1', True), ('role10', False)])
