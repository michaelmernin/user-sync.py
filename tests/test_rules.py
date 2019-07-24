import os
import pytest
from user_sync.rules import UmapiTargetInfo, AdobeGroup, UmapiConnectors
import mock

from user_sync.rules import RuleProcessor


@pytest.fixture
def rule_processor(caller_options):
    return RuleProcessor(caller_options)


@pytest.fixture
def caller_options():
    return {
        'adobe_group_filter': None,
        'after_mapping_hook': None,
        'default_country_code': 'US',
        'delete_strays': False,
        'directory_group_filter': None,
        'disentitle_strays': False,
        'exclude_groups': [],
        'exclude_identity_types': ['adobeID'],
        'exclude_strays': False,
        'exclude_users': [],
        'extended_attributes': None,
        'process_groups': True,
        'max_adobe_only_users': 200,
        'new_account_type': 'federatedID',
        'remove_strays': True,
        'strategy': 'sync',
        'stray_list_input_path': None,
        'stray_list_output_path': None,
        'test_mode': True,
        'update_user_info': False,
        'username_filter_regex': None,
        'adobe_only_user_action': ['remove'],
        'adobe_only_user_list': None,
        'adobe_users': ['all'],
        'config_filename': 'tests/fixture/user-sync-config.yml',
        'connector': 'ldap',
        'encoding_name': 'utf8',
        'user_filter': None,
        'users': None,
        'directory_connector_type': 'csv',
        'directory_connector_overridden_options': {
            'file_path': '../tests/fixture/remove-data.csv'},
        'adobe_group_mapped': False,
        'additional_groups': []}


def test_calculate_groups_to_remove(rule_processor):
    assert True


def test_calculate_groups_to_add(rule_processor):
    assert True


def test_get_username_from_user_key(rule_processor):
    with mock.patch('user_sync.rules.RuleProcessor.parse_user_key') as parse:
        parse.return_value = ['federatedID', 'test_user@email.com', '']
        username = rule_processor.get_username_from_user_key("federatedID,test_user@email.com,")
        assert username == 'test_user@email.com'

def test_parse_user_key(rule_processor):
    parsed_user_key = rule_processor.parse_user_key("federatedID,test_user@email.com,")
    assert parsed_user_key == ['federatedID', 'test_user@email.com', '']

    domain_parsed_key = rule_processor.parse_user_key("federatedID,test_user,email.com")
    assert domain_parsed_key == ['federatedID', 'test_user', 'email.com']


@pytest.fixture()
def umapi_target_info():
    return UmapiTargetInfo("")

# @pytest.fixture()
# def umapi_connectors():
#     return UmapiConnectors()

def test_add_mapped_group(umapi_target_info):
    umapi_target_info.add_mapped_group("All Students")
    assert "all students" in umapi_target_info.mapped_groups
    assert "All Students" in umapi_target_info.non_normalize_mapped_groups


def test_add_additional_group(umapi_target_info):

    umapi_target_info.add_additional_group('old_name', 'new_name')
    assert umapi_target_info.additional_group_map['old_name'][0] == 'new_name'


def test_add_desired_group_for(umapi_target_info):
    with mock.patch("user_sync.rules.UmapiTargetInfo.get_desired_groups") as mock_desired_groups:
        mock_desired_groups.return_value = None
        umapi_target_info.add_desired_group_for('user_key', 'group_name')
        assert umapi_target_info.desired_groups_by_user_key['user_key'] == {'group_name'}


def test_create():
    with mock.patch("user_sync.rules.AdobeGroup._parse") as parse:
        parse.return_value = ('group_name', None)
        AdobeGroup.create('this')
        assert ('group_name', None) in AdobeGroup.index_map


def test_parse():
    result = AdobeGroup._parse('qualified_name')
    assert result == ('qualified_name', None)
