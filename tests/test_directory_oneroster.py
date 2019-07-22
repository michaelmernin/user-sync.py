import pytest
import mock
from user_sync.connector.directory_oneroster import *


@pytest.fixture
def oneroster_connector(caller_options):
    return OneRosterConnector(caller_options)


@pytest.fixture()
def caller_options():
    connection = {
        'platform': 'classlink',
        'client_id': 'client_id',
        'client_secret': 'client_secret',
        'host': 'https://example.oneroster.com/ims/oneroster/v1p1/',
        'page_size': 1000,
        'max_user_count': 0
    }

    schema = {
        'match_groups_by': 'name',
        'key_identifier': 'id',
        'all_users_filter': 'users',
        'default_group_filter': 'classes',
        'default_user_filter': 'students',
        'include_only': {}
    }

    options = {'user_identity_type': 'federatedID',
               'connection': connection,
               'schema': schema}

    return options


def test_parse_results_valid(oneroster_connector, stub_api_response, stub_parse_results):
    expected_result = stub_parse_results
    record_handler = RecordHandler(options=oneroster_connector.options, logger=oneroster_connector.logger)
    actual_result = record_handler.parse_results(stub_api_response, 'sourcedId', [])
    assert expected_result == actual_result

    # asserts extended attributes are added to source_attributes dict(),
    # sms and identifier attributes have been extended

    expected_result['18125']['source_attributes']['sms'] = '(666) 666-6666'
    expected_result['18125']['source_attributes']['identifier'] = '17580'
    expected_result['18317']['source_attributes']['sms'] = None
    expected_result['18317']['source_attributes']['identifier'] = '15125'
    actual_result = record_handler.parse_results(stub_api_response, 'sourcedId', ['sms', 'identifier'])
    assert expected_result == actual_result

    # Fetch nonexistent properties

    expected_result['18125']['source_attributes']['fake'] = None
    expected_result['18317']['source_attributes']['fake'] = None
    actual_result = record_handler.parse_results(stub_api_response, 'sourcedId', ['sms', 'identifier', 'fake'])
    assert expected_result == actual_result

    # Testing filter_out_users

    record_handler.inclusions = {'givenName': "Billy"}
    actual_result = record_handler.parse_results(stub_api_response, 'sourcedId', [])
    length_of_actual_result = len(actual_result)
    assert length_of_actual_result == 1


def test_filter_out_users(oneroster_connector, stub_api_response):
    oneroster_connector.options['schema']['include_only'] = {'givenName': "Billy"}
    record_handler = RecordHandler(options=oneroster_connector.options, logger=oneroster_connector.logger)

    actual_result = record_handler.exclude_user(stub_api_response[0])
    assert actual_result is False

    actual_result = record_handler.exclude_user(stub_api_response[1])
    assert actual_result is True


def test_filter_out_users_complex(oneroster_connector, stub_api_response, stub_parse_results):
    oneroster_connector.options['schema']['include_only'] = {'familyName': "Houston",
                                                                             'enabledUser': 'true',
                                                                             'role': 'student'}
    record_handler = RecordHandler(options=oneroster_connector.options, logger=oneroster_connector.logger)

    actual_result = record_handler.exclude_user(stub_api_response[0])
    assert actual_result is True

    actual_result = record_handler.exclude_user(stub_api_response[1])
    assert actual_result is False


def test_filter_out_users_failures(oneroster_connector, log_stream, stub_api_response):
    stream, logger = log_stream
    oneroster_connector.options['schema']['include_only'] = {'xxx': "Billy"}
    record_handler = RecordHandler(options=oneroster_connector.options, logger=logger)
    record_handler.exclude_user(stub_api_response[0])
    stream.flush()

    expected_logger_output = 'No key for filtering attribute xxx for user'
    actual_logger_output = stream.getvalue()
    assert expected_logger_output in actual_logger_output


def test_parse_yml_groups_valid(oneroster_connector):
    r = oneroster_connector.parse_yaml_groups({'classes::yyy::students'})
    assert r == {
        'classes': {
            'yyy': {
                'classes::yyy::students': 'students'}
        }
    }

    r = oneroster_connector.parse_yaml_groups({'courses::y    y    y::teachers'})
    assert r == {
        'courses': {
            'y    y    y': {
                'courses::y    y    y::teachers': 'teachers'
            }
        }
    }

    r = oneroster_connector.parse_yaml_groups({'xxx'})
    assert r == {
        'classes': {
            'xxx': {
                'xxx': 'students'}
        }
    }


def test_parse_yml_groups_complex_valid(oneroster_connector):
    group_list = {'courses::Alg-102::students',
                  'classes::Geography I - Spring::students',
                  'classes::Art I - Fall::students',
                  'classes::Art I - Fall::teachers',
                  'classes::Art        I - Fall::teachers',
                  'classes::Algebra I - Fall::students',
                  'schools::Spring Valley::students',
                  'xxx'}

    r = oneroster_connector.parse_yaml_groups(group_list)

    assert r == {
        "classes": {
            "algebra i - fall": {
                "classes::Algebra I - Fall::students": "students"
            },
            "geography i - spring": {
                "classes::Geography I - Spring::students": "students"
            },
            "art i - fall": {
                "classes::Art I - Fall::students": "students",
                "classes::Art I - Fall::teachers": "teachers"
            },
            "art        i - fall": {
                "classes::Art        I - Fall::teachers": "teachers"
            },
            'xxx': {
                'xxx': 'students'}
        },
        "courses": {
            "alg-102": {
                "courses::Alg-102::students": "students"
            }
        },
        "schools": {
            "spring valley": {
                "schools::Spring Valley::students": "students"
            }
        }
    }


def test_parse_yml_groups_failure(oneroster_connector):
    pytest.raises(ValueError, oneroster_connector.parse_yaml_groups, groups_list={'course::Alg-102::students'})
    pytest.raises(ValueError, oneroster_connector.parse_yaml_groups, groups_list={'courses::Alg-102::stud'})


def test_load_users_and_groups(oneroster_connector, stub_api_response, stub_parse_results):
    expected = list(stub_parse_results.values())
    expected[0]['source_attributes']['groups'] = {'xxx'}
    expected[1]['source_attributes']['groups'] = {'xxx'}

    with mock.patch("oneroster.ClasslinkConnector.get_users") as mock_endpoint:
        with mock.patch("user_sync.connector.directory_oneroster.RecordHandler.parse_results") as mock_parse_results:
            mock_endpoint.return_value = stub_api_response
            mock_parse_results.return_value = stub_parse_results

            actual_result = list(oneroster_connector.load_users_and_groups(['xxx'], [], False))
            assert actual_result == expected

            # testing max_user_count functionality
            oneroster_connector.options['connection']['max_user_count'] = 1
            actual_result = list(oneroster_connector.load_users_and_groups(['xxx'], [], False))
            actual_result_length = len(actual_result)
            assert actual_result_length == 1


def test_create_user_object(oneroster_connector, stub_api_response, stub_parse_results):
    record_handler = RecordHandler(options=oneroster_connector.options, logger=oneroster_connector.logger)
    record = stub_api_response[0]

    actual_result = record_handler.create_user_object(record, 'sourcedId', [])
    expected_result = stub_parse_results['18125']
    assert actual_result == expected_result

    expected_result['source_attributes']['enabledUser'] = 'true'
    expected_result['source_attributes']['sms'] = '(666) 666-6666'
    actual_result = record_handler.create_user_object(record, 'sourcedId', ['enabledUser', 'sms'])
    assert expected_result == actual_result

    expected_result = stub_parse_results['18317']
    expected_result['source_attributes']['bad'] = None
    actual_result = record_handler.create_user_object(stub_api_response[1], 'sourcedId', ['bad'])
    assert expected_result == actual_result

    expected_result['source_attributes']['orgs'] = {
        'href': 'https://adobe-ca-v2.oneroster.com/ims/oneroster/v1p1/orgs/2',
        'sourcedId': '2',
        'type': 'org'
    }
    actual_result = record_handler.create_user_object(stub_api_response[1], 'sourcedId', ['orgs', 'bad'])
    assert expected_result == actual_result

def test_generate_value(stub_api_response):

    formatter = OneRosterValueFormatter(None)
    formatter.attribute_names = ['givenName', 'familyName']
    formatter.string_format = '{givenName}.{familyName}@xxx.com'

    # Integration test

    actual_result, actual_value = formatter.generate_value(stub_api_response[0])
    assert actual_result == 'BILLY.FLORES@xxx.com'

    # Unit test

    with mock.patch("user_sync.connector.directory_oneroster.OneRosterValueFormatter.get_attribute_value") as first_mock_attribute_value:
        first_mock_attribute_value.side_effect = ['BILLY', 'FLORES']

        actual_result, actual_value = formatter.generate_value(stub_api_response[0])
        assert actual_result == 'BILLY.FLORES@xxx.com'


def test_get_attr_values():
    attributes = {
        'sourcedId': '18125',
        'status': 'active',
        'dateLastModified': '2019-03-01T18:14:45.000Z',
        'username': 'billy.flores',
        'userIds': [{
            'type': 'FED',
            'identifier': '18125'}],
        'enabledUser': 'true',
        'givenName': 'BILLY',
        'familyName': 'FLORES',
        'middleName': 'DASEAN',
        'role': 'student',
        'identifier': '17580',
        'email': 'billy.flores@classlink.k12.nj.us',
        'sms': None,
        'phone': {
            'home': '111-111-1111',
            'work': '222-222-2222'},
        'agents': ['1', '2'],
        'orgs': [{
            'href': 'https://adobe-ca-v2.oneroster.com/ims/oneroster/v1p1/orgs/2',
            'sourcedId': '2',
            'type': 'org'}],
        'grades': ['15', ['11', '12', '13'], '14'],
        'byte': b'byteencoded',
        'password': ''}

    formatter = OneRosterValueFormatter(None)

    # Get a simple string
    assert formatter.get_attribute_value(attributes, "username") == "billy.flores"
    assert formatter.get_attribute_value(attributes, "dateLastModified") == "2019-03-01T18:14:45.000Z"

    # Get a list
    assert formatter.get_attribute_value(attributes, "agents") == ['1', '2']

    # Get a dictionary
    assert formatter.get_attribute_value(attributes, "phone") == {
        'home': '111-111-1111',
        'work': '222-222-2222'}
    assert formatter.get_attribute_value(attributes, "orgs") == {
        'href': 'https://adobe-ca-v2.oneroster.com/ims/oneroster/v1p1/orgs/2',
        'sourcedId': '2',
        'type': 'org'
    }

    # Get None
    assert formatter.get_attribute_value(attributes, "sms") == None

    # Get a nested object
    assert formatter.get_attribute_value(attributes, "grades") == ['15', ['11', '12', '13'], '14']

    # Decode a string
    assert formatter.get_attribute_value(attributes, "byte") == "byteencoded"


@pytest.fixture()
def stub_api_response():
    return [{
        'sourcedId': '18125',
        'status': 'active',
        'dateLastModified': '2019-03-01T18:14:45.000Z',
        'username': 'billy.flores',
        'userIds': [{
            'type': 'FED',
            'identifier': '18125'}],
        'enabledUser': 'true',
        'givenName': 'BILLY',
        'familyName': 'FLORES',
        'middleName': 'DASEAN',
        'role': 'student',
        'identifier': '17580',
        'email': 'billy.flores@classlink.k12.nj.us',
        'sms': '(666) 666-6666',
        'phone': '',
        'agents': [],
        'orgs': [
            {
                'href': 'https://adobe-ca-v2.oneroster.com/ims/oneroster/v1p1/orgs/2',
                'sourcedId': '2',
                'type': 'org'}],
        'grades': ['11'],
        'password': ''},
        {
            'sourcedId': '18317',
            'status': 'active',
            'dateLastModified': '2019-03-01T18:14:45.000Z',
            'username': 'giselle.houston',
            'userIds': [{
                'type': 'FED',
                'identifier': '18317'}],
            'enabledUser': 'true',
            'givenName': 'GISELLE',
            'familyName': 'HOUSTON',
            'middleName': 'CAMILO',
            'role': 'student',
            'identifier': '15125',
            'email': 'giselle.houston@classlink.k12.nj.us',
            'sms': '',
            'phone': '',
            'agents': [],
            'orgs': [
                {
                    'href': 'https://adobe-ca-v2.oneroster.com/ims/oneroster/v1p1/orgs/2',
                    'sourcedId': '2',
                    'type': 'org'}],
            'grades': ['11'],
            'password': ''},

    ]


@pytest.fixture()
def stub_parse_results():
    return {
        '18125': {
            'identity_type': 'federatedID',
            'username': 'billy.flores@classlink.k12.nj.us',
            'domain': 'classlink.k12.nj.us',
            'firstname': 'BILLY',
            'lastname': 'FLORES',
            'email': 'billy.flores@classlink.k12.nj.us',
            'groups': set(),
            'country': None,
            'source_attributes': {
                'email': 'billy.flores@classlink.k12.nj.us',
                'identity_type': None,
                'username': None,
                'domain': None,
                'givenName': 'BILLY',
                'familyName': 'FLORES',
                'country': None}
        },
        '18317': {'identity_type': 'federatedID',
                  'username': 'giselle.houston@classlink.k12.nj.us',
                  'domain': 'classlink.k12.nj.us',
                  'firstname': 'GISELLE',
                  'lastname': 'HOUSTON',
                  'email': 'giselle.houston@classlink.k12.nj.us',
                  'groups': set(),
                  'country': None,
                  'source_attributes': {
                      'email': 'giselle.houston@classlink.k12.nj.us',
                      'identity_type': None,
                      'username': None,
                      'domain': None,
                      'givenName': 'GISELLE',
                      'familyName': 'HOUSTON',
                      'country': None}
                  }
    }
