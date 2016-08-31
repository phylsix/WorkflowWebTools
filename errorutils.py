"""Simple utils functions that do not rely on a session.

These are separated from globalerrors, since we do not need
to generate an ErrorInfo instance in other applications.

:author: Daniel Abercrombie <dabercro@mit.edu>
"""


import os
import json
import urllib2
import sqlite3


def add_to_database(curs, data_location):
    """Add data from a file to a central database

    :param sqlite3.Cursor curs: is the cursor to the database
    :param str data_location: is the location of the file or url
                              of data to add to the database.
                              This should be in JSON format,
                              and if a local file does not exist,
                              a url will be assumed.
    """

    if os.path.isfile(data_location):
        res = open(data_location, 'r')

    else:
        res = urllib2.urlopen(data_location)


    for stepname, errorcodes in json.load(res).items():
        for errorcode, sitenames in errorcodes.items():
            for sitename, numbererrors in sitenames.items():
                full_key = '_'.join([stepname, sitename, errorcode])
                try:
                    curs.execute('INSERT INTO workflows VALUES (?,?,?,?,?)',
                                 (full_key, stepname, errorcode,
                                  sitename, numbererrors))
                except sqlite3.IntegrityError:
                    print full_key + ' already exists in database.'
                    print 'That is probably a duplicate. Skipping...'

    res.close()


def create_table(curs):
    """Create the workflows error table with the proper format
    :param sqlite3.Cursor curs: is the cursor to the database
    """

    curs.execute(
        'CREATE TABLE workflows (fullkey varchar(1023) UNIQUE, '
        'stepname varchar(255), errorcode int, '
        'sitename varchar(255), numbererrors int)')