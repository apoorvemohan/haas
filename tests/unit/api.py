# Copyright 2013-2014 Massachusetts Open Cloud Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the
# License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS
# IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied.  See the License for the specific language
# governing permissions and limitations under the License.

"""Unit tests for api.py"""

from haas import model, api, deferred
from haas.test_common import *
import pytest
import json


class TestUser:
    """Tests for the haas.api.user_* functions."""

    @database_only
    def test_new_user(self, db):
        api._assert_absent(db, model.User, 'bob')
        api.user_create('bob', 'foo')

    @database_only
    def test_duplicate_user(self, db):
        api.user_create('alice', 'secret')
        with pytest.raises(api.DuplicateError):
                api.user_create('alice', 'password')

    @database_only
    def test_delete_user(self, db):
        api.user_create('bob', 'foo')
        api.user_delete('bob')

    @database_only
    def test_delete_missing_user(self, db):
        with pytest.raises(api.NotFoundError):
            api.user_delete('bob')

    @database_only
    def test_delete_user_twice(self, db):
        api.user_create('bob', 'foo')
        api.user_delete('bob')
        with pytest.raises(api.NotFoundError):
            api.user_delete('bob')


class TestProjectCreateDelete:
    """Tests for the haas.api.project_* functions."""

    @database_only
    def test_project_create_success(self, db):
        api.project_create('anvil-nextgen')
        api._must_find(db, model.Project, 'anvil-nextgen')

    @database_only
    def test_project_create_duplicate(self, db):
        api.project_create('anvil-nextgen')
        with pytest.raises(api.DuplicateError):
            api.project_create('anvil-nextgen')

    @database_only
    def test_project_delete(self, db):
        api.project_create('anvil-nextgen')
        api.project_delete('anvil-nextgen')
        with pytest.raises(api.NotFoundError):
            api._must_find(db, model.Project, 'anvil-nextgen')

    @database_only
    def test_project_delete_nexist(self, db):
        with pytest.raises(api.NotFoundError):
            api.project_delete('anvil-nextgen')

    @database_only
    def test_project_delete_hasnode(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        with pytest.raises(api.BlockedError):
            api.project_delete('anvil-nextgen')

    @database_only
    def test_project_delete_success_nodesdeleted(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        api.project_detach_node('anvil-nextgen', 'node-99')
        api.project_delete('anvil-nextgen')

    @database_only
    def test_project_delete_hasnetwork(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('hammernet', 'anvil-nextgen')
        with pytest.raises(api.BlockedError):
            api.project_delete('anvil-nextgen')

    @database_only
    def test_project_delete_success_networksdeleted(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.network_delete('hammernet')
        api.project_delete('anvil-nextgen')

    @database_only
    def test_project_delete_hasheadnode(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-01', 'anvil-nextgen', 'base-headnode')
        with pytest.raises(api.BlockedError):
            api.project_delete('anvil-nextgen')

class TestProjectAddDeleteUser:
    """Tests for adding and deleting a user from a project"""

    @database_only
    def test_project_add_user(self, db):
        api.user_create('alice', 'secret')
        api.project_create('acme-corp')
        api.project_add_user('acme-corp', 'alice')
        user = api._must_find(db, model.User, 'alice')
        project = api._must_find(db, model.Project, 'acme-corp')
        assert project in user.projects
        assert user in project.users

    @database_only
    def test_project_remove_user(self, db):
        api.user_create('alice', 'secret')
        api.project_create('acme-corp')
        api.project_add_user('acme-corp', 'alice')
        api.project_remove_user('acme-corp', 'alice')
        user = api._must_find(db, model.User, 'alice')
        project = api._must_find(db, model.Project, 'acme-corp')
        assert project not in user.projects
        assert user not in project.users

    @database_only
    def test_project_delete(self, db):
        api.project_create('acme-corp')
        api.project_delete('acme-corp')
        with pytest.raises(api.NotFoundError):
            api._must_find(db, model.Project, 'acme-corp')

    @database_only
    def test_duplicate_project_create(self, db):
        api.project_create('acme-corp')
        with pytest.raises(api.DuplicateError):
            api.project_create('acme-corp')

    @database_only
    def test_duplicate_project_add_user(self, db):
        api.user_create('alice', 'secret')
        api.project_create('acme-corp')
        api.project_add_user('acme-corp', 'alice')
        with pytest.raises(api.DuplicateError):
            api.project_add_user('acme-corp', 'alice')

    @database_only
    def test_bad_project_remove_user(self, db):
        """Tests that removing a user from a project they're not in fails."""
        api.user_create('alice', 'secret')
        api.project_create('acme-corp')
        with pytest.raises(api.NotFoundError):
            api.project_remove_user('acme-corp', 'alice')


class TestNetworking:

    @database_only
    def test_networking_involved(self, db):
        api.port_register('1')
        api.port_register('2')
        api.port_register('3')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register('node-98', 'ipmihost', 'root', 'tapeworm')
        api.node_register('node-97', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', 'eth0', 'DE:AD:BE:EF:20:14')
        api.node_register_nic('node-98', 'eth0', 'DE:AD:BE:EF:20:15')
        api.node_register_nic('node-97', 'eth0', 'DE:AD:BE:EF:20:16')
        api.port_connect_nic('1', 'node-99', 'eth0')
        api.port_connect_nic('2', 'node-98', 'eth0')
        api.port_connect_nic('3', 'node-97', 'eth0')

        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        api.project_connect_node('anvil-nextgen', 'node-98')
        network_create_simple('hammernet', 'anvil-nextgen')
        network_create_simple('spiderwebs', 'anvil-nextgen')
        api.node_connect_network('node-98', 'eth0', 'hammernet')

    @database_only
    def test_networking_nic_no_port(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', 'eth0', 'DE:AD:BE:EF:20:14')

        api.project_create('anvil-nextgen')

        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', 'eth0', 'hammernet')


class TestProjectConnectDetachNode:

    @database_only
    def test_project_connect_node(self, db):
        api.project_create('anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.project_connect_node('anvil-nextgen', 'node-99')
        project = api._must_find(db, model.Project, 'anvil-nextgen')
        node = api._must_find(db, model.Node, 'node-99')
        assert node in project.nodes
        assert node.project is project

    @database_only
    def test_project_connect_node_project_nexist(self, db):
        """Tests that connecting a node to a nonexistent project fails"""
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        with pytest.raises(api.NotFoundError):
            api.project_connect_node('anvil-nextgen', 'node-99')

    @database_only
    def test_project_connect_node_node_nexist(self, db):
        """Tests that connecting a nonexistent node to a projcet fails"""
        api.project_create('anvil-nextgen')
        with pytest.raises(api.NotFoundError):
            api.project_connect_node('anvil-nextgen', 'node-99')

    @database_only
    def test_project_detach_node(self, db):
        api.project_create('anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.project_connect_node('anvil-nextgen', 'node-99')
        api.project_detach_node('anvil-nextgen', 'node-99')
        project = api._must_find(db, model.Project, 'anvil-nextgen')
        node = api._must_find(db, model.Node, 'node-99')
        assert node not in project.nodes
        assert node.project is not project

    @database_only
    def test_project_detach_node_notattached(self, db):
        """Tests that removing a node from a project it's not in fails."""
        api.project_create('anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        with pytest.raises(api.NotFoundError):
            api.project_detach_node('anvil-nextgen', 'node-99')

    @database_only
    def test_project_detach_node_project_nexist(self, db):
        """Tests that removing a node from a nonexistent project fails."""
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        with pytest.raises(api.NotFoundError):
            api.project_detach_node('anvil-nextgen', 'node-99')

    @database_only
    def test_project_detach_node_node_nexist(self, db):
        """Tests that removing a nonexistent node from a project fails."""
        api.project_create('anvil-nextgen')
        with pytest.raises(api.NotFoundError):
            api.project_detach_node('anvil-nextgen', 'node-99')

    @database_only
    def test_project_detach_node_on_network(self, db):
        api.project_create('anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', 'eth0', 'DE:AD:BE:EF:20:13')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', 'eth0', 'hammernet')
        with pytest.raises(api.BlockedError):
            api.project_detach_node('anvil-nextgen', 'node-99')

    @database_only
    def test_project_detach_node_success_nic_not_on_network(self, db):
        api.project_create('anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', 'eth0', 'DE:AD:BE:EF:20:13')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.project_detach_node('anvil-nextgen', 'node-99')

    @database_only
    def test_project_detach_node_removed_from_network(self, db):
        api.project_create('anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', 'eth0', 'DE:AD:BE:EF:20:13')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', 'eth0', 'hammernet')
        deferred.apply_networking()
        api.node_detach_network('node-99', 'eth0')
        deferred.apply_networking()

        api.project_detach_node('anvil-nextgen', 'node-99')


class TestNodeRegisterDelete:
    """Tests for the haas.api.node_* functions."""

    @database_only
    def test_node_register(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api._must_find(db, model.Node, 'node-99')

    @database_only
    def test_duplicate_node_register(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        with pytest.raises(api.DuplicateError):
            api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')

    @database_only
    def test_node_delete(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_delete('node-99')
        with pytest.raises(api.NotFoundError):
            api._must_find(db, model.Node, 'node-99')

    @database_only
    def test_node_delete_nexist(self, db):
        with pytest.raises(api.NotFoundError):
            api.node_delete('node-99')


class TestNodeRegisterDeleteNic:

    @database_only
    def test_node_register_nic(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', '01-eth0', 'DE:AD:BE:EF:20:14')
        nic = api._must_find(db, model.Nic, '01-eth0')
        assert nic.owner.label == 'compute-01'

    @database_only
    def test_node_register_nic_no_node(self, db):
        with pytest.raises(api.NotFoundError):
            api.node_register_nic('compute-01', '01-eth0', 'DE:AD:BE:EF:20:14')

    @database_only
    def test_node_register_nic_duplicate_nic(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', '01-eth0', 'DE:AD:BE:EF:20:14')
        nic = api._must_find(db, model.Nic, '01-eth0')
        with pytest.raises(api.DuplicateError):
            api.node_register_nic('compute-01', '01-eth0', 'DE:AD:BE:EF:20:15')

    @database_only
    def test_node_delete_nic_success(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', '01-eth0', 'DE:AD:BE:EF:20:14')
        api.node_delete_nic('compute-01', '01-eth0')
        api._assert_absent(db, model.Nic, '01-eth0')
        api._must_find(db, model.Node, 'compute-01')

    @database_only
    def test_node_delete_nic_nic_nexist(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        with pytest.raises(api.NotFoundError):
            api.node_delete_nic('compute-01', '01-eth0')

    @database_only
    def test_node_delete_nic_node_nexist(self, db):
        with pytest.raises(api.NotFoundError):
            api.node_delete_nic('compute-01', '01-eth0')

    @database_only
    def test_node_delete_nic_wrong_node(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register('compute-02', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', '01-eth0', 'DE:AD:BE:EF:20:14')
        with pytest.raises(api.NotFoundError):
            api.node_delete_nic('compute-02', '01-eth0')

    @database_only
    def test_node_delete_nic_wrong_nexist_node(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', '01-eth0', 'DE:AD:BE:EF:20:14')
        with pytest.raises(api.NotFoundError):
            api.node_delete_nic('compute-02', '01-eth0')

    @database_only
    def test_node_register_nic_diff_nodes(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register('compute-02', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'ipmi', 'DE:AD:BE:EF:20:14')
        api.node_register_nic('compute-02', 'ipmi', 'DE:AD:BE:EF:20:14')


class TestNodeConnectDetachNetwork:

    @database_only
    def test_node_connect_network_success(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')

        api.node_connect_network('node-99', '99-eth0', 'hammernet')
        deferred.apply_networking()
        network = api._must_find(db, model.Network, 'hammernet')
        nic = api._must_find(db, model.Nic, '99-eth0')
        assert nic.network is network
        assert nic in network.nics

    @database_only
    def test_node_connect_network_wrong_node_in_project(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', '99-eth0', 'hammernet')
        api.node_register('node-98', 'ipmihost', 'root', 'tapeworm') #added
        api.project_connect_node('anvil-nextgen', 'node-98') #added

        with pytest.raises(api.NotFoundError):
            api.node_connect_network('node-98', '99-eth0', 'hammernet')

    @database_only
    def test_node_connect_network_wrong_node_not_in_project(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_register('node-98', 'ipmihost', 'root', 'tapeworm') # added

        with pytest.raises(api.NotFoundError):
            api.node_connect_network('node-98', '99-eth0', 'hammernet')

    @database_only
    def test_node_connect_network_no_such_node(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')

        with pytest.raises(api.NotFoundError):
            api.node_connect_network('node-98', '99-eth0', 'hammernet') # changed

    @database_only
    def test_node_connect_network_no_such_nic(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
#        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')

        with pytest.raises(api.NotFoundError):
            api.node_connect_network('node-99', '99-eth0', 'hammernet')

    @database_only
    def test_node_connect_network_no_such_network(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
#        network_create_simple('hammernet', 'anvil-nextgen')
        with pytest.raises(api.NotFoundError):
            api.node_connect_network('node-99', '99-eth0', 'hammernet')

    @database_only
    def test_node_connect_network_node_not_in_project(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
#        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')

        with pytest.raises(api.ProjectMismatchError):
            api.node_connect_network('node-99', '99-eth0', 'hammernet')

    @database_only
    def test_node_connect_network_different_projects(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_create('anvil-oldtimer') # added
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-oldtimer') # changed

        with pytest.raises(api.ProjectMismatchError):
            api.node_connect_network('node-99', '99-eth0', 'hammernet')

    @database_only
    def test_node_connect_network_already_attached_to_same(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', '99-eth0', 'hammernet') # added
        deferred.apply_networking() # added

        api.node_connect_network('node-99', '99-eth0', 'hammernet')

    @database_only
    def test_node_connect_network_already_attached_differently(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        network_create_simple('hammernet2', 'anvil-nextgen') #added
        api.node_connect_network('node-99', '99-eth0', 'hammernet') # added
        deferred.apply_networking() # added

        api.node_connect_network('node-99', '99-eth0', 'hammernet2')


    @database_only
    def test_node_detach_network_success(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', '99-eth0', 'hammernet')
        deferred.apply_networking() # added

        api.node_detach_network('node-99', '99-eth0')
        deferred.apply_networking()
        network = api._must_find(db, model.Network, 'hammernet')
        nic = api._must_find(db, model.Nic, '99-eth0')
        assert nic.network is not network
        assert nic not in network.nics

    @database_only
    def test_node_detach_network_not_attached(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
#        api.node_connect_network('node-99', '99-eth0', 'hammernet')

        api.node_detach_network('node-99', '99-eth0')

    @database_only
    def test_node_detach_network_wrong_node_in_project(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register('node-98', 'ipmihost', 'root', 'tapeworm') # added
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        api.project_connect_node('anvil-nextgen', 'node-98') # added
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', '99-eth0', 'hammernet')

        with pytest.raises(api.NotFoundError):
            api.node_detach_network('node-98', '99-eth0') # changed

    @database_only
    def test_node_detach_network_wrong_node_not_in_project(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register('node-98', 'ipmihost', 'root', 'tapeworm') # added
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', '99-eth0', 'hammernet')

        with pytest.raises(api.NotFoundError):
            api.node_detach_network('node-98', '99-eth0') # changed

    @database_only
    def test_node_detach_network_no_such_node(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', '99-eth0', 'hammernet')

        with pytest.raises(api.NotFoundError):
            api.node_detach_network('node-98', '99-eth0') # changed

    @database_only
    def test_node_detach_network_no_such_nic(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'node-99')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_connect_network('node-99', '99-eth0', 'hammernet')

        with pytest.raises(api.NotFoundError):
            api.node_detach_network('node-99', '99-eth1') # changed

    @database_only
    def test_node_detach_network_node_not_in_project(self, db):
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', '99-eth0', 'DE:AD:BE:EF:20:14')
        api.project_create('anvil-nextgen')
#        api.project_connect_node('anvil-nextgen', 'node-99')
#        network_create_simple('hammernet', 'anvil-nextgen')
#        api.node_connect_network('node-99', '99-eth0', 'hammernet')

        with pytest.raises(api.ProjectMismatchError):
            api.node_detach_network('node-99', '99-eth0')


class TestHeadnodeCreateDelete:

    @database_only
    def test_headnode_create_success(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        hn = api._must_find(db, model.Headnode, 'hn-0')
        assert hn.project.label == 'anvil-nextgen'

    @database_only
    def test_headnode_create_badproject(self, db):
        """Tests that creating a headnode with a nonexistent project fails"""
        with pytest.raises(api.NotFoundError):
            api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')

    @database_only
    def test_headnode_create_duplicate(self, db):
        """Tests that creating a headnode with a duplicate name fails"""
        api.project_create('anvil-nextgen')
        api.project_create('anvil-oldtimer')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        with pytest.raises(api.DuplicateError):
            api.headnode_create('hn-0', 'anvil-oldtimer', 'base-headnode')

    @database_only
    def test_headnode_create_second(self, db):
        """Tests that creating a second headnode one one project fails"""
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create('hn-1', 'anvil-nextgen', 'base-headnode')


    @database_only
    def test_headnode_delete_success(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_delete('hn-0')
        api._assert_absent(db, model.Headnode, 'hn-0')

    @database_only
    def test_headnode_delete_nonexistent(self, db):
        """Tests that deleting a nonexistent headnode fails"""
        with pytest.raises(api.NotFoundError):
            api.headnode_delete('hn-0')


class TestHeadnodeCreateDeleteHnic:

    @database_only
    def test_headnode_create_hnic_success(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        nic = api._must_find(db, model.Hnic, 'hn-0-eth0')
        assert nic.owner.label == 'hn-0'

    @database_only
    def test_headnode_create_hnic_no_headnode(self, db):
        with pytest.raises(api.NotFoundError):
            api.headnode_create_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_headnode_create_hnic_duplicate_hnic(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        with pytest.raises(api.DuplicateError):
            api.headnode_create_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_headnode_delete_hnic_success(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        api.headnode_delete_hnic('hn-0', 'hn-0-eth0')
        api._assert_absent(db, model.Hnic, 'hn-0-eth0')
        hn = api._must_find(db, model.Headnode, 'hn-0')

    @database_only
    def test_headnode_delete_hnic_hnic_nexist(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        with pytest.raises(api.NotFoundError):
            api.headnode_delete_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_headnode_delete_hnic_headnode_nexist(self, db):
        with pytest.raises(api.NotFoundError):
            api.headnode_delete_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_headnode_delete_hnic_wrong_headnode(self, db):
        api.project_create('anvil-nextgen')
        api.project_create('anvil-oldtimer')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create('hn-1', 'anvil-oldtimer', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        with pytest.raises(api.NotFoundError):
            api.headnode_delete_hnic('hn-1', 'hn-0-eth0')

    @database_only
    def test_headnode_delete_hnic_wrong_nexist_headnode(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        with pytest.raises(api.NotFoundError):
            api.headnode_delete_hnic('hn-1', 'hn-0-eth0')

    @database_only
    def test_headnode_create_hnic_diff_headnodes(self, db):
        api.project_create('anvil-legacy')
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-legacy', 'base-headnode')
        api.headnode_create('hn-1', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'eth0')
        api.headnode_create_hnic('hn-1', 'eth0')


class TestHeadnodeConnectDetachNetwork:

    @database_only
    def test_headnode_connect_network_success(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')

        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')
        network = api._must_find(db, model.Network, 'hammernet')
        hnic = api._must_find(db, model.Hnic, 'hn-0-eth0')
        assert hnic.network is network
        assert hnic in network.hnics

    @database_only
    def test_headnode_connect_network_no_such_headnode(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')

        with pytest.raises(api.NotFoundError):
            api.headnode_connect_network('hn-1', 'hn-0-eth0', 'hammernet') # changed

    @database_only
    def test_headnode_connect_network_no_such_hnic(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')

        with pytest.raises(api.NotFoundError):
            api.headnode_connect_network('hn-0', 'hn-0-eth1', 'hammernet') # changed

    @database_only
    def test_headnode_connect_network_no_such_network(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')

        with pytest.raises(api.NotFoundError):
            api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet2') # changed

    @database_only
    def test_headnode_connect_network_already_attached_to_same(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet') # added

        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

    @database_only
    def test_headnode_connect_network_already_attached_differently(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')
        network_create_simple('hammernet2', 'anvil-nextgen')
        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet') # added

        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet2') # changed

    @database_only
    def test_headnode_connect_network_different_projects(self, db):
        api.project_create('anvil-nextgen')
        api.project_create('anvil-oldtimer') # added
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-oldtimer') #changed

        with pytest.raises(api.ProjectMismatchError):
            api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

    @database_only
    def test_headnode_connect_network_non_allocated(self, db):
        """Connecting a headnode to a non-allocated network should fail.

        Right now the create_bridges script will only create bridges
        for vlans in the database, so any specified by the administrator
        will not exist. Since the haas does not create the bridges during
        execution, attempting to attach a headnode to a network whose vlan
        does not have an existing bridge will fail. An administrator could
        work around this by creating the bridges manually, but we wish to
        treat the naming of the bridges as an implementation detail as much
        as possible, and thus discourage this.

        For now connecting headnodes to non-allocated networks is simply
        not supported; this will change in the future. In the meantime,
        we should report a sensible error, and this test checks for that.

        See also issue #333
        """
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        api.network_create('hammernet', 'admin', 'anvil-nextgen', '7')
        with pytest.raises(api.BadArgumentError):
            api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')


    @database_only
    def test_headnode_detach_network_success(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

        api.headnode_detach_network('hn-0', 'hn-0-eth0')
        network = api._must_find(db, model.Network, 'hammernet')
        hnic = api._must_find(db, model.Hnic, 'hn-0-eth0')
        assert hnic.network is None
        assert hnic not in network.hnics

    @database_only
    def test_headnode_detach_network_not_attached(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')
#        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

        api.headnode_detach_network('hn-0', 'hn-0-eth0')

    @database_only
    def test_headnode_detach_network_no_such_headnode(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

        with pytest.raises(api.NotFoundError):
            api.headnode_detach_network('hn-1', 'hn-0-eth0')  # changed

    @database_only
    def test_headnode_detach_network_no_such_hnic(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

        with pytest.raises(api.NotFoundError):
            api.headnode_detach_network('hn-0', 'hn-0-eth1')  # changed


class TestHeadnodeFreeze:

    # We can't start the headnodes for real in the test suite, but we need
    # "starting" them to still clear the dirty bit.
    @pytest.fixture(autouse=True)
    def patch_start(self, monkeypatch):
        def start(self):
            self.dirty = False
        monkeypatch.setattr(model.Headnode, 'start', start)


    def _prep(self):
        """Helper to set up common state."""
        api.project_create('anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')

    def _prep_delete_hnic(self):
        self._prep()
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')

    def _prep_connect_network(self):
        """Helper to set up common state for headnode_connect_network tests."""
        self._prep()
        network_create_simple('hammernet', 'anvil-nextgen')
        api.headnode_create_hnic('hn-0', 'hn-0-eth0')

    def _prep_detach_network(self):
        self._prep_connect_network()
        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

    @database_only
    def test_freeze_fail_create_hnic(self, db):
        self._prep()

        api.headnode_start('hn-0')
        with pytest.raises(api.IllegalStateError):
            api.headnode_create_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_succeed_create_hnic(self, db):
        self._prep()

        api.headnode_create_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_freeze_fail_delete_hnic(self, db):
        self._prep_delete_hnic()

        api.headnode_start('hn-0')
        with pytest.raises(api.IllegalStateError):
            api.headnode_delete_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_succeed_delete_hnic(self, db):
        self._prep_delete_hnic()

        api.headnode_delete_hnic('hn-0', 'hn-0-eth0')

    @database_only
    def test_freeze_fail_connect_network(self, db):
        self._prep_connect_network()

        api.headnode_start('hn-0')
        with pytest.raises(api.IllegalStateError):
            api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

    @database_only
    def test_succeed_connect_network(self, db):
        self._prep_connect_network()

        api.headnode_connect_network('hn-0', 'hn-0-eth0', 'hammernet')

    @database_only
    def test_freeze_fail_detach_network(self, db):
        self._prep_detach_network()

        api.headnode_start('hn-0')
        with pytest.raises(api.IllegalStateError):
            api.headnode_detach_network('hn-0', 'hn-0-eth0')

    @database_only
    def test_succeed_detach_network(self, db):
        self._prep_detach_network()

        api.headnode_detach_network('hn-0', 'hn-0-eth0')

class TestNetworkCreateDelete:
    """Tests for the haas.api.network_* functions."""

    @database_only
    def test_network_create_success(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('hammernet', 'anvil-nextgen')
        net = api._must_find(db, model.Network, 'hammernet')
        assert net.creator.label == 'anvil-nextgen'

    @database_only
    def test_network_create_badproject(self, db):
        """Tests that creating a network with a nonexistent project fails"""
        with pytest.raises(api.NotFoundError):
            network_create_simple('hammernet', 'anvil-nextgen')

    @database_only
    def test_network_create_duplicate(self, db):
        """Tests that creating a network with a duplicate name fails"""
        api.project_create('anvil-nextgen')
        api.project_create('anvil-oldtimer')
        network_create_simple('hammernet', 'anvil-nextgen')
        with pytest.raises(api.DuplicateError):
            network_create_simple('hammernet', 'anvil-oldtimer')

    @database_only
    def test_network_delete_success(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.network_delete('hammernet')
        api._assert_absent(db, model.Network, 'hammernet')

    @database_only
    def test_network_delete_project_complex_success(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', 'eth0', 'DE:AD:BE:EF:20:14')
        api.project_connect_node('anvil-nextgen', 'node-99')
        api.node_connect_network('node-99', 'eth0', 'hammernet')
        deferred.apply_networking()
        api.node_detach_network('node-99', 'eth0')
        deferred.apply_networking()
        api.network_delete('hammernet')

    @database_only
    def test_network_delete_nonexistent(self, db):
        """Tests that deleting a nonexistent network fails"""
        with pytest.raises(api.NotFoundError):
            api.network_delete('hammernet')

    @database_only
    def test_network_delete_node_on_network(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('node-99', 'eth0', 'DE:AD:BE:EF:20:14')
        api.project_connect_node('anvil-nextgen', 'node-99')
        api.node_connect_network('node-99', 'eth0', 'hammernet')
        with pytest.raises(api.BlockedError):
            api.network_delete('hammernet')

    @database_only
    def test_network_delete_headnode_on_network(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('hammernet', 'anvil-nextgen')
        api.headnode_create('hn-0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('hn-0', 'eth0')
        api.headnode_connect_network('hn-0', 'eth0', 'hammernet')
        with pytest.raises(api.BlockedError):
            api.network_delete('hammernet')


class TestPortRegisterDelete:

    @database_only
    def test_port_register_success(self, db):
        api.port_register('3')

    @database_only
    def test_port_register_duplicate(self, db):
        api.port_register('3')
        with pytest.raises(api.DuplicateError):
            api.port_register('3')

    @database_only
    def test_port_delete_success(self, db):
        api.port_register('3')
        api.port_delete('3')

    @database_only
    def test_port_delete_no_such_port(self, db):
        with pytest.raises(api.NotFoundError):
            api.port_delete('3')


class TestPortConnectDetachNic:

    @database_only
    def test_port_connect_nic_success(self, db):
        api.port_register('3')
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        api.port_connect_nic('3', 'compute-01', 'eth0')

    @database_only
    def test_port_connect_nic_no_such_switch(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        with pytest.raises(api.NotFoundError):
            api.port_connect_nic('3', 'compute-01', 'eth0')

    @database_only
    def test_port_connect_nic_no_such_port(self, db):
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        with pytest.raises(api.NotFoundError):
            api.port_connect_nic('3', 'compute-01', 'eth0')

    @database_only
    def test_port_connect_nic_no_such_node(self, db):
        api.port_register('3')
        with pytest.raises(api.NotFoundError):
            api.port_connect_nic('3', 'compute-01', 'eth0')

    @database_only
    def test_port_connect_nic_no_such_nic(self, db):
        api.port_register('3')
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        with pytest.raises(api.NotFoundError):
            api.port_connect_nic('3', 'compute-01', 'eth0')

    @database_only
    def test_port_connect_nic_already_attached_to_same(self, db):
        api.port_register('3')
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        api.port_connect_nic('3', 'compute-01', 'eth0')
        with pytest.raises(api.DuplicateError):
            api.port_connect_nic('3', 'compute-01', 'eth0')

    @database_only
    def test_port_connect_nic_nic_already_attached_differently(self, db):
        api.port_register('3')
        api.port_register('4')
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        api.port_connect_nic('3', 'compute-01', 'eth0')
        with pytest.raises(api.DuplicateError):
            api.port_connect_nic('4', 'compute-01', 'eth0')

    @database_only
    def test_port_connect_nic_port_already_attached_differently(self, db):
        api.port_register('3')
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register('compute-02', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        api.node_register_nic('compute-02', 'eth1', 'DE:AD:BE:EF:20:15')
        api.port_connect_nic('3', 'compute-01', 'eth0')
        with pytest.raises(api.DuplicateError):
            api.port_connect_nic('3', 'compute-02', 'eth1')


    @database_only
    def test_port_detach_nic_success(self, db):
        api.port_register('3')
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        api.port_connect_nic('3', 'compute-01', 'eth0')
        api.port_detach_nic('3')

    @database_only
    def test_port_detach_nic_no_such_port(self, db):
        with pytest.raises(api.NotFoundError):
            api.port_detach_nic('3')

    @database_only
    def test_port_detach_nic_not_attached(self, db):
        api.port_register('3')
        api.node_register('compute-01', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('compute-01', 'eth0', 'DE:AD:BE:EF:20:14')
        with pytest.raises(api.NotFoundError):
            api.port_detach_nic('3')


class TestQuery:
    """test the query api"""

    def _compare_node_dumps(self, actual, expected):
        """This is a helper method which compares the parsed json output of
        two show_headnode calls for equality. There are a couple issue to work
        around to get an accurate result - in particular, we often don't care
        about the order of lists, which needs special handling (especially when
        the arguments aren't orderable).
        """
        # For two lists to be equal, their elements have to be in the same
        # order. However, there is no ordering defined on dictionaries, so we
        # can't just sort the lists. instead we check our desired notion of
        # equality manually, and then clear both hnic lists before comparing
        # the rest of the data:
        for nic in actual['nics']:
            assert nic in expected['nics']
            expected['nics'].remove(nic)
        assert len(expected['nics']) == 0
        actual['nics'] = []
        assert expected == actual


    @database_only
    def test_free_nodes(self, db):
        api.node_register('master-control-program', 'ipmihost', 'root', 'tapeworm')
        api.node_register('robocop', 'ipmihost', 'root', 'tapeworm')
        api.node_register('data', 'ipmihost', 'root', 'tapeworm')
        result = json.loads(api.list_free_nodes())
        # For the lists to be equal, the ordering must be the same:
        result.sort()
        assert result == [
            'data',
            'master-control-program',
            'robocop',
        ]

    @database_only
    def test_list_projects(self, db):
        assert json.loads(api.list_projects()) == []
        api.project_create('anvil-nextgen')
        assert json.loads(api.list_projects()) == ['anvil-nextgen']
        api.project_create('runway')
        api.project_create('manhattan')
        assert sorted(json.loads(api.list_projects())) == [
            'anvil-nextgen',
            'manhattan',
            'runway',
        ]

    @database_only
    def test_no_free_nodes(self, db):
        assert json.loads(api.list_free_nodes()) == []

    @database_only
    def test_some_non_free_nodes(self, db):
        """Make sure that allocated nodes don't show up in the free list."""
        api.node_register('master-control-program', 'ipmihost', 'root', 'tapeworm')
        api.node_register('robocop', 'ipmihost', 'root', 'tapeworm')
        api.node_register('data', 'ipmihost', 'root', 'tapeworm')

        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'robocop')
        api.project_connect_node('anvil-nextgen', 'data')

        assert json.loads(api.list_free_nodes()) == ['master-control-program']

    @database_only
    def test_show_node(self, db):
        api.node_register('robocop', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('robocop', 'eth0', 'DE:AD:BE:EF:20:14')
        api.node_register_nic('robocop', 'wlan0', 'DE:AD:BE:EF:20:15')

        actual = json.loads(api.show_node('robocop'))
        expected = {
            'name': 'robocop',
            'free': True,
            'nics': [
                {
                    'label':'eth0',
                    'macaddr': 'DE:AD:BE:EF:20:14',
                },
                {
                    'label':'wlan0',
                    'macaddr': 'DE:AD:BE:EF:20:15'
                }
            ],
        }
        self._compare_node_dumps(actual, expected)


    @database_only
    def test_show_node_unavailable(self, db):
        api.node_register('robocop', 'ipmihost', 'root', 'tapeworm')
        api.node_register_nic('robocop', 'eth0', 'DE:AD:BE:EF:20:14')
        api.node_register_nic('robocop', 'wlan0', 'DE:AD:BE:EF:20:15')

        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'robocop')

        actual = json.loads(api.show_node('robocop'))
        expected = {
            'name': 'robocop',
            'free': False,
            'nics': [
                {
                    'label': 'eth0',
                    'macaddr': 'DE:AD:BE:EF:20:14',
                },
                {
                    'label': 'wlan0',
                    'macaddr': 'DE:AD:BE:EF:20:15',
                },
            ],
        }
        self._compare_node_dumps(actual, expected)

    @database_only
    def test_show_nonexistant_node(self, db):
        with pytest.raises(api.NotFoundError):
            api.show_node('master-control-program')

    @database_only
    def test_project_nodes_exist(self, db):
        api.node_register('master-control-program', 'ipmihost', 'root', 'tapeworm')
        api.node_register('robocop', 'ipmihost', 'root', 'tapeworm')
        api.node_register('data', 'ipmihost', 'root', 'tapeworm')

        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'master-control-program')
        api.project_connect_node('anvil-nextgen', 'robocop')
        api.project_connect_node('anvil-nextgen', 'data')
        result = json.loads(api.list_project_nodes('anvil-nextgen'))
        # For the lists to be equal, the ordering must be the same:
        result.sort()
        assert result == [
            'data',
            'master-control-program',
            'robocop',
        ]

    @database_only
    def test_project_headnodes_exist(self, db):
        api.project_create('anvil-nextgen')
        api.headnode_create('hn0', 'anvil-nextgen', 'base-headnode')
        api.headnode_create('hn1', 'anvil-nextgen', 'base-headnode')
        api.headnode_create('hn2', 'anvil-nextgen', 'base-headnode')

        result = json.loads(api.list_project_headnodes('anvil-nextgen'))
        # For the lists to be equal, the ordering must be the same:
        result.sort()
        assert result == [
            'hn0',
            'hn1',
            'hn2',
        ]

    @database_only
    def test_no_project_nodes(self, db):
        api.project_create('anvil-nextgen')
        assert json.loads(api.list_project_nodes('anvil-nextgen')) == []

    @database_only
    def test_no_project_headnodes(self, db):
        api.project_create('anvil-nextgen')
        assert json.loads(api.list_project_headnodes('anvil-nextgen')) == []

    @database_only
    def test_some_nodes_in_project(self, db):
        """Test that only assigned nodes are in the project."""
        api.node_register('master-control-program', 'ipmihost', 'root', 'tapeworm')
        api.node_register('robocop', 'ipmihost', 'root', 'tapeworm')
        api.node_register('data', 'ipmihost', 'root', 'tapeworm')

        api.project_create('anvil-nextgen')
        api.project_connect_node('anvil-nextgen', 'robocop')
        api.project_connect_node('anvil-nextgen', 'data')

        result = json.loads(api.list_project_nodes('anvil-nextgen'))
        result.sort()
        assert result == ['data', 'robocop']

    @database_only
    def test_project_list_networks(self, db):
        api.project_create('anvil-nextgen')

        network_create_simple('pxe', 'anvil-nextgen')
        network_create_simple('public', 'anvil-nextgen')
        network_create_simple('private', 'anvil-nextgen')

        result = json.loads(api.list_project_networks('anvil-nextgen'))
        # For the lists to be equal, the ordering must be the same:
        result.sort()
        assert result == [
                'private',
                'public',
                'pxe'
        ]

    @database_only
    def test_no_project_networks(self, db):
        api.project_create('anvil-nextgen')
        assert json.loads(api.list_project_nodes('anvil-nextgen')) == []


    @database_only
    def test_show_headnode(self, db):
        api.project_create('anvil-nextgen')
        network_create_simple('spiderwebs', 'anvil-nextgen')
        api.headnode_create('BGH', 'anvil-nextgen', 'base-headnode')
        api.headnode_create_hnic('BGH', 'eth0')
        api.headnode_create_hnic('BGH', 'wlan0')
        api.headnode_connect_network('BGH', 'eth0', 'spiderwebs')


        result = json.loads(api.show_headnode('BGH'))
        # For the lists to be equal, the ordering must be the same:
        result['hnics'].sort()
        assert result == {
            'name': 'BGH',
            'project': 'anvil-nextgen',
            'hnics': [
                'eth0',
                'wlan0',
            ],
            'vncport': None
        }

    @database_only
    def test_show_nonexistant_headnode(self, db):
        with pytest.raises(api.NotFoundError):
            api.show_headnode('BGH')


    @database_only
    def test_list_headnode_images(self, db):
        result = json.loads(api.list_headnode_images())
        assert result == [ 'base-headnode', 'img1', 'img2', 'img3', 'img4' ]


class TestFancyNetworkCreate:
    """Test creating network with advanced parameters.

    These test the 10 possible combinations of creator project, access
    project, and underlying net-id.  It confirms that the legal ones are
    allowed, and that their parameters are passed into the database
    succesfully, and confirms the the prohibited ones are disallowed.

    The details of these combinations are shown in docs/networks.md
    """

    @database_only
    def test_project_network(self, db):
        """Succesfully create a project-owned network."""
        api.project_create('anvil-nextgen')
        api.network_create('hammernet', 'anvil-nextgen', 'anvil-nextgen', '')
        project = api._must_find(db, model.Project, 'anvil-nextgen')
        network = api._must_find(db, model.Network, 'hammernet')
        assert network.creator is project
        assert network.access is project
        assert network.allocated is True

    @database_only
    def test_project_network_imported_fails(self, db):
        """Fail to make a project-owned network with a supplied net-id."""
        api.project_create('anvil-nextgen')
        with pytest.raises(api.BadArgumentError):
            api.network_create('hammernet', 'anvil-nextgen', 'anvil-nextgen', '35')

    @database_only
    def test_project_network_bad_access_fails(self, db):
        """Fail to make a project-owned network that others can access."""
        api.project_create('anvil-nextgen')
        api.project_create('anvil-oldtimer')
        for access in ['', 'anvil-oldtimer']:
            for net_id in ['', '35']:
                with pytest.raises(api.BadArgumentError):
                    api.network_create('hammernet', 'anvil-nextgen', access, net_id)

    @database_only
    def test_admin_network(self, db):
        """Succesfully create all 4 varieties of administrator-owned networks."""
        api.project_create('anvil-nextgen')
        project = api._must_find(db, model.Project, 'anvil-nextgen')
        for project_api, project_db in [('', None), ('anvil-nextgen', project)]:
            for net_id, allocated in [('', True), ('35', False)]:
                network = 'hammernet' + project_api + net_id
                api.network_create(network, 'admin', project_api, net_id)
                network = api._must_find(db, model.Network, network)
                assert network.creator is None
                assert network.access is project_db
                assert network.allocated is allocated
            network = api._must_find(db, model.Network, 'hammernet' + project_api + '35')
            assert network.network_id == '35'


class TestDryRun:
    """Test that api calls using functions with @no_dry_run behave reasonably."""

    @database_only
    def test_node_power_cycle(self, db):
        """Check that power-cycle behaves reasonably under @no_dry_run."""
        api.project_create('anvil-nextgen')
        api.node_register('node-99', 'ipmihost', 'root', 'tapeworm')
        api.project_connect_node('anvil-nextgen', 'node-99')
        api.node_power_cycle('node-99')
