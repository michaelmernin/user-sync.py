# Copyright (c) 2016-2017 Adobe Systems Incorporated.  All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in allls

# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json
import six
import re
import string

import user_sync.config
import user_sync.connector.helper
import user_sync.helper
import user_sync.identity_type
from user_sync.error import AssertionException

from user_sync.connector.oneroster import OneRoster


def connector_metadata():
    metadata = {
        'name': OneRosterConnector.name
    }
    return metadata


def connector_initialize(options):
    """
    :type options: dict
    """
    state = OneRosterConnector(options)


    return state


def connector_load_users_and_groups(state, groups=None, extended_attributes=None, all_users=True):
    """
    :type state: LDAPDirectoryConnector
    :type groups: Optional(list(str))
    :type extended_attributes: Optional(list(str))
    :type all_users: bool
    :rtype (bool, iterable(dict))
    """
    return state.load_users_and_groups(groups or [], extended_attributes or [], all_users)


class OneRosterConnector(object):
    name = 'oneroster'
    __slots__ = ['options', 'user_identity_type', 'logger', 'results_parser', 'additional_group_filters']
    def __init__(self, caller_options):

        # Get the configuration information and apply data from YAML
        caller_config = user_sync.config.DictConfig('%s configuration' % self.name, caller_options)

        builder = user_sync.config.OptionsBuilder(caller_config)
        builder.set_string_value('limit', 1000)
        builder.set_string_value('key_identifier', 'sourcedId')
        builder.set_string_value('country_code', None)
        builder.require_string_value('client_id')
        builder.require_string_value('client_secret')
        builder.require_string_value('host')
        builder.set_string_value('logger_name', self.name)
        builder.set_string_value('string_encoding', 'utf8')
        builder.set_string_value('logger_name', self.name)
        builder.set_string_value('string_encoding', 'utf8')
        builder.set_string_value('user_email_format', six.text_type('{email}'))
        builder.set_string_value('user_given_name_format', six.text_type('{givenName}'))
        builder.set_string_value('user_surname_format', six.text_type('{familyName}'))
        builder.set_string_value('user_country_code_format', six.text_type('{countryCode}'))
        builder.set_string_value('user_username_format', None)
        builder.set_string_value('user_domain_format', None)
        builder.set_string_value('user_identity_type', None)
        builder.set_string_value('user_identity_type_format', None)

        self.options = builder.get_options()
        self.user_identity_type = user_sync.identity_type.parse_identity_type(self.options['user_identity_type'])
        self.logger = user_sync.connector.helper.create_logger(self.options)
        options = builder.get_options()
        self.options = options
        self.logger = logger = user_sync.connector.helper.create_logger(options)

        logger.debug('%s initialized with options: %s', self.name, options)
        caller_config.report_unused_values(self.logger)
        self.results_parser = RecordHandler(options, logger)

        self.additional_group_filters = None

    def load_users_and_groups(self, groups, extended_attributes, all_users):
        """
        description: Leverages class components to return and send a user list to UMAPI
        :type groups: list(str)
        :type extended_attributes: list(str)
        :type all_users: bool
        :rtype (bool, iterable(dict))
        """
        options = self.options

        ttt = get_actual_size(options)

        conn = Connection(self.logger, options['host'], options['limit'], options['client_id'], options['client_secret'])
        x = get_actual_size(conn)
        y = sys.getsizeof(conn)
        a = conn.__sizeof__()
        test = DataItem("mike", 29, "here")
        te = get_actual_size(test)
        ot = test.__sizeof__()
        groups_from_yml = self.parse_yml_groups(groups)
        users_result = {}

        for group_filter in groups_from_yml:
            inner_dict = groups_from_yml[group_filter]
            for group_name in inner_dict:
                for user_group in inner_dict[group_name]:
                    user_filter = inner_dict[group_name][user_group]

                    users_list = conn.get_user_list(group_filter, group_name, user_filter, options['key_identifier'], options['limit'])
                    #rh = RecordHandler(options, logger=None)
                    api_response = RecordHandler(options, logger=None).parse_results(users_list, options['key_identifier'], extended_attributes)
                    #api_response = RecordHandler.parse_results(options, users_list, options['key_identifier'], extended_attributes)

                    users_result = self.merge_users(users_result, api_response, user_group)

        return six.itervalues(users_result)

    def merge_users(self, user_list, new_users, group_name):

        for uid in new_users:
            if uid not in user_list:
                user_list[uid] = new_users[uid]

            (user_list[uid]['groups']).add(group_name)

        return user_list

    def parse_yml_groups(self, groups_list):
        """
        description: parses group options from user-sync.config file into a nested dict with Key: group_filter for the outter dict, Value: being the nested
        dict {Key: group_name, Value: user_filter}
        :type groups_list: set(str) from user-sync-config-ldap.yml
        :rtype: iterable(dict)
        """

        full_dict = dict()

        for text in groups_list:
            try:
                group_filter, group_name, user_filter = text.lower().split("::")
            except ValueError:
                raise ValueError("Incorrect MockRoster Group Syntax: " + text + " \nRequires values for group_filter, group_name, user_filter. With '::' separating each value")
            if group_filter not in ['classes', 'courses', 'schools']:
                raise ValueError("Incorrect group_filter: " + group_filter + " .... must be either: classes, courses, or schools")
            if user_filter not in ['students', 'teachers', 'users']:
                raise ValueError("Incorrect user_filter: " + user_filter + " .... must be either: students, teachers, or users")

            if group_filter not in full_dict:
                full_dict[group_filter] = {group_name: dict()}
            elif group_name not in full_dict[group_filter]:
                full_dict[group_filter][group_name] = dict()

            full_dict[group_filter][group_name].update({text: user_filter})

        return full_dict

class Connection:
    """ Starts connection and makes queries with One-Roster API"""

    __slots__ = ['logger', 'host_name', 'limit', 'client_id', 'client_secret', 'oneroster']
    def __init__(self, logger, host_name=None, limit='100', client_id=None, client_secret=None):
        self.host_name = host_name
        self.logger = logger
        self.limit = limit
        self.client_id = client_id
        self.client_secret = client_secret
        self.oneroster = OneRoster(client_id, client_secret)
        xr = get_actual_size(self.oneroster)
        c = 5

    def get_user_list(self, group_filter, group_name, user_filter, key_identifier, limit):
        """
        description:
        :type group_filter: str()
        :type group_name: str()
        :type user_filter: str()
        :type key_identifier: str()
        :type limit: str()
        :rtype parsed_json_list: list(str)
        """
        parsed_json_list = list()

        if group_filter == 'courses':
            class_list = self.get_classlist_for_course(group_name, key_identifier, limit)
            for each_class in class_list:
                key_id_classes = class_list[each_class]
                key = 'first'
                while key is not None:
                    response = self.oneroster.make_roster_request(
                        self.host_name + 'classes/' + key_id_classes + '/' + user_filter + '?limit=' + limit + '&offset=0') if key == 'first' \
                        else self.oneroster.make_roster_request(response.links[key]['url'])
                    if response.ok is False:
                        self.logger.warning(
                            'Error fetching ' + user_filter + ' Found for: ' + group_name + "\nError Response Message:" + " " +
                            response.text)
                        return {}

                    for ignore, users in json.loads(response.content).items():
                        parsed_json_list.extend(users)
                    if key == 'last':
                        break
                    key = 'next' if 'next' in response.links else 'last'

        else:
            try:

                key_id = self.get_key_identifier(group_filter, group_name, key_identifier, limit)
                key = 'first'
                while key is not None:
                    response = self.oneroster.make_roster_request(self.host_name + group_filter + '/' + key_id + '/' + user_filter + '?limit=' + limit + '&offset=0') if key == 'first' else self.oneroster.make_roster_request(response.links[key]['url'])
                    if response.ok is False:
                        self.logger.warning(
                            'Error fetching ' + user_filter + ' Found for: ' + group_name + "\nError Response Message:" + " " +
                            response.text)
                        return {}

                    for ignore, users in json.loads(response.content).items():
                        parsed_json_list.extend(users)
                    if key == 'last':
                        break
                    key = 'next' if 'next' in response.links else 'last'

            except ValueError as e:
                self.logger.warning(e)
                return {}

        return parsed_json_list

    def get_key_identifier(self, group_filter, group_name, key_identifier, limit):
        """
        description: Returns key_identifier (eg: sourcedID) for targeted group_name from One-Roster
        :type group_filter: str()
        :type group_name: str()
        :type key_identifier: str()
        :type limit: str()
        :rtype sourced_id: str()
        """
        keys = list()
        if group_filter == 'schools':
            name_identifier = 'name'
            revised_key = 'orgs'
        else:
            name_identifier = 'title'
            revised_key = group_filter
        key = 'first'
        while key is not None:
            response = self.oneroster.make_roster_request(self.host_name + group_filter + '?limit=' + limit + '&offset=0') if key == 'first' \
                else self.oneroster.make_roster_request(response.links[key]['url'])
            if response.status_code is not 200:
                raise ValueError('Non Successful Response'
                                 + '  ' + 'status:' + str(response.status_code) + "\n" + response.text)
            parsed_json = json.loads(response.content)

            for each_class in parsed_json.get(revised_key):
                if self.encode_str(each_class[name_identifier]) == self.encode_str(group_name):
                    try:
                        key_id = each_class[key_identifier]
                    except ValueError:
                        raise ValueError('Key identifier: ' + key_identifier + ' not a valid identifier')
                    keys.append(key_id)
                    return keys[0]

            if key == 'last':
                break
            key = 'next' if 'next' in response.links else 'last'

        if len(keys) == 0:
            raise ValueError('No key ids found for: ' + " " + group_filter + ":" + " " + group_name)
        elif len(keys) > 1:
            raise ValueError('Duplicate ID found: ' + " " + group_filter + ":" + " " + group_name)

        return keys[0]

    def get_classlist_for_course(self, group_name, key_identifier, limit):
        """
        description: returns list of sourceIds for classes of a course (group_name)
        :type group_name: str()
        :type key_identifier: str()
        :type limit: str()
        :rtype class_list: list(str)
        """

        class_list = dict()
        try:
            key_id = self.get_key_identifier('courses', group_name, key_identifier, limit)
            key = 'first'
            while key is not None:
                response = self.oneroster.make_roster_request(self.host_name + 'courses' + '/' + key_id + '/' + 'classes' + '?limit=' + limit + '&offset=0') if key == 'first' \
                    else self.oneroster.make_roster_request(response.links[key]['url'])

                if response.ok is not True:
                    status = response.status_code
                    message = response.reason
                    raise ValueError('Non Successful Response'
                                     + '  ' + 'status:' + str(status) + '  ' + 'message:' + str(message))

                for ignore, each_class in json.loads(response.content).items():
                    class_key_id = each_class[0][key_identifier]
                    class_name = each_class[0]['title']
                    class_list[class_name] = class_key_id

                if key == 'last':
                    break
                key = 'next' if 'next' in response.links else 'last'

        except ValueError as e:
            self.logger.warning(e)

        return class_list

    def encode_str(self, text):
        return re.sub(r'(\s)', '', text).lower()


class RecordHandler:
    __slots__ = ['logger', 'country_code', 'user_identity_type', 'user_identity_type_formatter', 'user_email_formatter',
                 'user_username_formatter', 'user_domain_formatter', 'user_given_name_formatter',
                 'user_surname_formatter', 'user_country_code_formatter']
    def __init__(self, options, logger):

        self.logger = logger
        self.country_code = options['country_code']

        self.user_identity_type = user_sync.identity_type.parse_identity_type(options['user_identity_type'])
        self.user_identity_type_formatter = OneRosterValueFormatter(options['user_identity_type_format'])
        self.user_email_formatter = OneRosterValueFormatter(options['user_email_format'])
        self.user_username_formatter = OneRosterValueFormatter(options['user_username_format'])
        self.user_domain_formatter = OneRosterValueFormatter(options['user_domain_format'])
        self.user_given_name_formatter = OneRosterValueFormatter(options['user_given_name_format'])
        self.user_surname_formatter = OneRosterValueFormatter(options['user_surname_format'])
        self.user_country_code_formatter = OneRosterValueFormatter(options['user_country_code_format'])

    def parse_results(self, result_set, key_identifier, extended_attributes):
        """
        description: parses through user_list from API calls, to create final user objects
        :type result_set: list(dict())
        :type extended_attributes: list(str)
        :type original_group: str()
        :type key_identifier: str()
        :rtype users_dict: dict(constructed user objects)
        """
        users_dict = dict()
        for user in result_set:
            if user['status'] == 'active':
                returned_user = self.create_user_object(user, key_identifier, extended_attributes)
                users_dict[user[key_identifier]] = returned_user
        return users_dict


    def create_user_object(self, record, key_identifier, extended_attributes):
        """
        description: Using user's API information to construct final user objects
        :type record: dict()
        :type extended_attributes: list(str)
        :type original_group: str()
        :type key_identifier: str()
        :rtype: formatted_user: dict(user object)
        """
        key = record.get(key_identifier)
        if key is None:
            return

        email, last_attribute_name = self.user_email_formatter.generate_value(record)
        email = email.strip() if email else None
        if not email:
            if last_attribute_name is not None:
                self.logger.warning('Skipping user with id %s: empty email attribute (%s)',  key, last_attribute_name)

        formatted_user = dict()
        source_attributes = dict()

        #       User information available from One-Roster
        source_attributes['sourcedId'] = record['sourcedId']
        source_attributes['status'] = record['status']
        source_attributes['dateLastModified'] = record['dateLastModified']
        source_attributes['username'] = record['username']
        source_attributes['userIds'] = record['userIds']
        source_attributes['enabledUser'] = record['enabledUser']
        source_attributes['givenName'] = formatted_user['firstname'] = record['givenName']
        source_attributes['familyName'] = formatted_user['lastname'] = record['familyName']
        source_attributes['middleName'] = record['middleName']
        source_attributes['role'] = record['role']
        source_attributes['identifier'] = record['identifier']
        source_attributes['email'] = formatted_user['email'] = formatted_user['username'] = record['email']
        source_attributes['sms'] = record['sms']
        source_attributes['phone'] = record['phone']
        source_attributes['agents'] = record['agents']
        source_attributes['orgs'] = record['orgs']
        source_attributes['grades'] = record['grades']
        source_attributes['domain'] = formatted_user['domain'] = str(record['email']).split('@')[1]
        source_attributes['password'] = record['password']
        source_attributes[key_identifier] = record[key_identifier]
        formatted_user['country'] = self.country_code
        formatted_user['identity_type'] = self.user_identity_type
        #Can be found in userIds if needed
        #source_attributes['userId'] = user['userId']
        #source_attributes['type'] = user['type']

        formatted_user['source_attributes'] = source_attributes
        formatted_user['groups'] = set()

        return formatted_user


class OneRosterValueFormatter(object):
    encoding = 'utf8'

    def __init__(self, string_format):
        """
        The format string must be a unicode or ascii string: see notes above about being careful in Py2!
        """
        if string_format is None:
            attribute_names = []
        else:
            string_format = six.text_type(string_format)    # force unicode so attribute values are unicode
            formatter = string.Formatter()
            attribute_names = [six.text_type(item[1]) for item in formatter.parse(string_format) if item[1]]
        self.string_format = string_format
        self.attribute_names = attribute_names

    def get_attribute_names(self):
        """
        :rtype list(str)
        """
        return self.attribute_names

    def generate_value(self, record):
        """
        :type record: dict
        :rtype (unicode, unicode)
        """
        result = None
        attribute_name = None
        if self.string_format is not None:
            values = {}
            for attribute_name in self.attribute_names:
                value = self.get_attribute_value(record, attribute_name, first_only=True)
                if value is None:
                    values = None
                    break
                values[attribute_name] = value
            if values is not None:
                result = self.string_format.format(**values)
        return result, attribute_name

    @classmethod
    def get_attribute_value(cls, attributes, attribute_name, first_only=False):
        """
        The attribute value type must be decodable (str in py2, bytes in py3)
        :type attributes: dict
        :type attribute_name: unicode
        :type first_only: bool
        """
        attribute_values = attributes.get(attribute_name)
        if attribute_values:
            try:
                if first_only or len(attribute_values) == 1:

                    attr = attribute_values if isinstance(attribute_values, six.string_types) else attribute_values[0]
                    return attr if isinstance(attr, six.string_types) else attr.decode(cls.encoding)

                else:
                    return [(val if isinstance(val, six.string_types)
                             else val.decode(cls.encoding)) for val in attribute_values]
            except UnicodeError as e:
                raise AssertionException("Encoding error in value of attribute '%s': %s" % (attribute_name, e))
        return None


import sys

def get_actual_size(obj, seen=None):
    """Recursively finds size of objects"""
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    # Important mark as seen *before* entering recursion to gracefully handle
    # self-referential objects
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_actual_size(v, seen) for v in obj.values()])
        size += sum([get_actual_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, '__dict__'):
        size += get_actual_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_actual_size(i, seen) for i in obj])
    return size


def dump(obj):
  for attr in dir(obj):
    return print("  obj.%s = %r" % (attr, getattr(obj, attr)))

class DataItem(object):
    __slots__ = ['name', 'age', 'address']
    def __init__(self, name, age, address):
        self.name = name
        self.age = age
        self.address = address

    def something(self, name):
        return name + 5