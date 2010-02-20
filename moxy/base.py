#!/usr/bin/env python
'''
    MySQL database backend for Django using MySQLdb and Eventlet
'''

import eventlet.db_pool

from django.db.backends import BaseDatabaseWrapper, BaseDatabaseFeatures, BaseDatabaseOperations, util
try:
    import MySQLdb
except ImportError, e:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("Error loading MySQLdb module: %s" % e)

import re

from django.db.backends import *
from django.db.backends.mysql import base as mysqldb_base
from django.db.backends.mysql.client import DatabaseClient
from django.db.backends.mysql.creation import DatabaseCreation
from django.db.backends.mysql.introspection import DatabaseIntrospection
from django.db.backends.mysql.validation import DatabaseValidation
from django.db.backends.signals import connection_created
from django.utils.safestring import SafeString, SafeUnicode

# Raise exceptions for database warnings if DEBUG is on
from django.conf import settings

DatabaseError = MySQLdb.DatabaseError
IntegrityError = MySQLdb.IntegrityError


# This should match the numerical portion of the version numbers (we can treat
# versions like 5.0.24 and 5.0.24a as the same). Based on the list of version
# at http://dev.mysql.com/doc/refman/4.1/en/news.html and
# http://dev.mysql.com/doc/refman/5.0/en/news.html .
server_version_re = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{1,2})')

# MySQLdb-1.2.1 and newer automatically makes use of SHOW WARNINGS on
# MySQL-4.1 and newer, so the MysqlDebugWrapper is unnecessary. Since the
# point is to raise Warnings as exceptions, this can be done with the Python
# warning module, and this is setup when the connection is created, and the
# standard util.CursorDebugWrapper can be used. Also, using sql_mode
# TRADITIONAL will automatically cause most warnings to be treated as errors.

class DatabaseFeatures(mysqldb_base.DatabaseFeatures):
    pass


class DatabaseWrapper(BaseDatabaseWrapper):

    operators = {
        'exact': '= %s',
        'iexact': 'LIKE %s',
        'contains': 'LIKE BINARY %s',
        'icontains': 'LIKE %s',
        'regex': 'REGEXP BINARY %s',
        'iregex': 'REGEXP %s',
        'gt': '> %s',
        'gte': '>= %s',
        'lt': '< %s',
        'lte': '<= %s',
        'startswith': 'LIKE BINARY %s',
        'endswith': 'LIKE BINARY %s',
        'istartswith': 'LIKE %s',
        'iendswith': 'LIKE %s',
    }

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)
        self.server_version = None

        self.features = DatabaseFeatures()
        self.ops = mysqldb_base.DatabaseOperations()
        self.client = DatabaseClient(self)
        self.creation = DatabaseCreation(self)
        self.introspection = DatabaseIntrospection(self)
        self.validation = DatabaseValidation()

    def _valid_connection(self):
        if self.connection is not None:
            try:
                self.connection.ping()
                return True
            except DatabaseError:
                self.connection.close()
                self.connection = None
        return False

    def _cursor(self):
        if not self._valid_connection():
            kwargs = {
                #'conv': django_conversions,
                'charset': 'utf8',
                'use_unicode': True,
            }
            settings_dict = self.settings_dict
            if settings_dict['DATABASE_USER']:
                kwargs['user'] = settings_dict['DATABASE_USER']
            if settings_dict['DATABASE_NAME']:
                kwargs['db'] = settings_dict['DATABASE_NAME']
            if settings_dict['DATABASE_PASSWORD']:
                kwargs['passwd'] = settings_dict['DATABASE_PASSWORD']
            if settings_dict['DATABASE_HOST'].startswith('/'):
                kwargs['unix_socket'] = settings_dict['DATABASE_HOST']
            elif settings_dict['DATABASE_HOST']:
                kwargs['host'] = settings_dict['DATABASE_HOST']
            if settings_dict['DATABASE_PORT']:
                kwargs['port'] = int(settings_dict['DATABASE_PORT'])
            kwargs.update(settings_dict['DATABASE_OPTIONS'])
            self.connection = eventlet.db_pool.ConnectionPool.connect(MySQLdb, 15, **kwargs)
            connection_created.send(sender=self.__class__)
        cursor = mysqldb_base.CursorWrapper(self.connection.cursor())
        return cursor

    def _rollback(self):
        try:
            BaseDatabaseWrapper._rollback(self)
        except Database.NotSupportedError:
            pass

    def get_server_version(self):
        if not self.server_version:
            if not self._valid_connection():
                self.cursor()
            self.server_version = self.connection._obj.get_server_info()
            #m = server_version_re.match(self.connection.get_server_version())
            #if not m:
            #    raise Exception('Unable to determine MySQL version from version string %r' % self.connection.get_server_version())
            #self.server_version = tuple([int(x) for x in m.groups()])
        return self.server_version
