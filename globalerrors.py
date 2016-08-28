"""
Generates the content for the errors pages

:author: Daniel Abercrombie <dabercro@mit.edu>
"""

import os
import urllib2
import json
import sqlite3
import time
import logging

from .reasonsmanip import reasons_list


ALL_ERRORS_LOCATION = 'https://cmst2.web.cern.ch/cmst2/unified/all_errors.json'
"""Location of the errors file loaded into globalerrors"""
EXPLAIN_ERRORS_LOCATION = 'https://cmst2.web.cern.ch/cmst2/unified/explanations.json'
"""Location of errors explanations"""


class ErrorInfo(object):
    """Holds the information for any errors for a session"""

    def __init__(self, data_location=ALL_ERRORS_LOCATION):
        """Initialization with a setup.
        :param str data_location: Set the location of the data to read in the info
        """

        self.data_location = data_location
        self.setup()

    def __del__(self):
        """Delete anything left over."""
        self.teardown()

    def setup(self):
        """Create an SQL database from the all_errors.json generated by production"""

        self.timestamp = time.time()

        self.conn = sqlite3.connect(':memory:', check_same_thread=False)
        curs = self.conn.cursor()
        curs.execute(
            'CREATE TABLE workflows (stepname varchar(255), errorcode int, '
            'sitename varchar(255), numbererrors int)')

        stepset = set()
        errorset = set()
        siteset = set()

        # Store everything into an SQL database for fast retrival

        if os.path.isfile(self.data_location):
            res = open(self.data_location, 'r')

        else:
            res = urllib2.urlopen(self.data_location)


        for stepname, errorcodes in json.load(res).items():
            stepset.add(stepname)
            for errorcode, sitenames in errorcodes.items():
                errorset.add(errorcode)
                for sitename, numbererrors in sitenames.items():
                    siteset.add(sitename)
                    curs.execute('INSERT INTO workflows VALUES (?,?,?,?)',
                                 (stepname, errorcode, sitename, numbererrors))
        res.close()

        allsteps = list(stepset)
        allsteps.sort()
        allerrors = list(errorset)
        allerrors.sort(key=int)
        allsites = list(siteset)
        allsites.sort()

        res = urllib2.urlopen(EXPLAIN_ERRORS_LOCATION)
        self.info = curs, allsteps, allerrors, allsites, json.load(res)
        res.close()

        self.curs = curs
        self.allsteps = allsteps

        self.connection_log('opened')

    def teardown(self):
        """Close the database when cache expires"""
        self.conn.close()
        self.connection_log('closed')

    def connection_log(self, action):
        """Logs actions on the sqlite3 connection

        :param str action: is the action on the connection
        """
        logging.info('Connection %s with timestamp %s', action, self.timestamp)

    def get_errors_explained(self):
        """
        :returns: Dictionary that maps each error code to a snippet of the error log
        :rtype: dict
        """
        return self.info[4]

    def get_allmap(self):
        """
        :returns: A dictionary that maps 'errorcode', 'stepname', and 'sitename'
                  to the lists of all the errors, steps, or sites
        :rtype: dict
        """

        return {  # lists of elements to call for each possible row and column
            'errorcode': self.info[2],
            'stepname':  self.info[1],
            'sitename':  self.info[3]
            }

    def return_workflows(self):
        """
        :returns: the set of all workflow names
        :rtype: set
        """
        wfs = set()

        for step in self.allsteps:
            wfs.add(step.split('/')[1])

        return wfs


GLOBAL_INFO = ErrorInfo()


def check_session(session, can_refresh=False):
    """If session is None, fills it.

    :param cherrypy.Session session: the current session
    :param bool can_refresh: tells the function if it is safe to refresh
                             and close the old database
    :returns: ErrorInfo of the session
    :rtype: ErrorInfo
    """

    if not session:
        theinfo = GLOBAL_INFO
    else:
        if session.get('info') is None:
            session['info'] = ErrorInfo()
        theinfo = session.get('info')

    # If session ErrorInfo is old, set up another connection
    if can_refresh and session.get('info').timestamp < time.time() - 60*30:
        theinfo.teardown()
        theinfo.setup()

    return theinfo


def get_step_list(workflow, session=None):
    """Gets the list of steps within a workflow

    :param str workflow: Name of the workflow to gather information for
    :param cherrypy.Session session: the current session
    :returns: list of steps withing the workflow
    :rtype: list
    """

    curs = check_session(session).curs

    steplist = list(     # Make a list of all the steps so we can sort them
        set(
            [stepgets[0] for stepgets in curs.execute(
                "SELECT stepname FROM workflows WHERE stepname LIKE '/{0}/%'".format(workflow)
                )
            ]
            )
        )
    steplist.sort()

    return steplist


def get_step_table(step, session=None):
    """Gathers the errors for a step into a 2-D table of ints

    :param str step: name of the step to get the table for
    :param cherrypy.Session session: Stores the information for a session
    :returns: A table of errors for the step
    :rtype: list of lists of ints
    """
    curs = check_session(session).curs
    allmap = check_session(session).get_allmap()

    steptable = []

    for error in allmap['errorcode']:
        steprow = []

        for site in allmap['sitename']:
            curs.execute('SELECT numbererrors FROM workflows '
                         'WHERE sitename=? AND errorcode=? AND stepname=?',
                         (site, error, step))
            numbererrors = curs.fetchall()

            if len(numbererrors) == 0:
                steprow.append(0)
            else:
                steprow.append(numbererrors[0][0])

        steptable.append(steprow)

    return steptable


def see_workflow(workflow, session=None):
    """Gathers the error information for a single workflow

    :param str workflow: Name of the workflow to gather information for
    :param cherrypy.Session session: Stores the information for a session
    :returns: Dictionary used to generate webpage for a requested workflow
    :rtype: dict
    """

    _, _, allerrors, allsites, _ = check_session(session).info
    steplist = get_step_list(workflow, session)

    tables = []

    for step in steplist:
        steptable = get_step_table(step, session)
        tables.append(zip(steptable, allerrors))

    return {
        'steplist':  zip(steplist, tables),
        'allerrors': allerrors,
        'allsites':  allsites,
        'reasonslist': reasons_list(),
        }


def get_row_col_names(pievar):
    """Get the column and row for the global table view, based on user input

    :param str pievar: The variable to divide the piecharts by.
    :returns: The names of the global table rows, and the table columns
    :rtype: (str, str)
    """

    pievarmap = { # for each pievar, set row and column
        'errorcode': ('stepname', 'sitename'),
        'sitename':  ('stepname', 'errorcode'),
        'stepname':  ('errorcode', 'sitename')
        }

    # Check for valid pievar and set default
    if pievar not in pievarmap.keys():
        pievar = 'errorcode'

    return pievarmap[pievar]


TITLEMAP = {
    'errorcode': 'code ',
    'stepname':  'step ',
    'sitename':  'site ',
    }
"""Dictionary that determines how a chosen pievar shows up in the pie chart titles"""


def get_errors_and_pietitles(pievar, session=None):
    """Gets the number of errors for the global table.

    .. todo::

        Figure out how to document the javascript and link to that from here.

    :param str pievar: The variable to divide the piecharts by.
                       This is the variable that does not make up the axes of the page table
    :param cherrypy.Session session: Stores the information for a session
    :returns: Errors for global table and titles for each pie chart.
              The errors are split into two variables.

               - The first variable is a dictionary with two keys: 'col' and 'row'.
                 Each item is a list of the total number of errors in each column or row.
               - The second variable is just a long list lists of ints.
                 One element of the first layer corresponds to
                 a pie chart on the globalerrors view.
                 Each element of the second layer tells different slices of the pie chart.
                 This is read in by the javascript.
               - The last variable is the list of titles to give each pie chart.
                 This will show up in a tooltip on the webpage.
    :rtype: dict, list of lists, list
    """


    curs = check_session(session, True).curs
    rowname, colname = get_row_col_names(pievar)

    allmap = check_session(session).get_allmap()

    pieinfo = []
    pietitles = []

    total_errors = {
        'row': [0] * len(allmap[rowname]),
        'col': [0] * len(allmap[colname])
        }

    for irow, row in enumerate(allmap[rowname]):

        pietitlerow = []

        for icol, col in enumerate(allmap[colname]):
            toappend = []
            pietitle = ''
            if rowname != 'stepname':
                pietitle += TITLEMAP[rowname] + ': ' + row + '\n'
            pietitle += TITLEMAP[colname] + ': ' + col
            for piekey, errnum in curs.execute(('SELECT {0}, numbererrors FROM workflows '
                                                'WHERE {1}=? AND {2}=?'.
                                                format(pievar, rowname, colname)),
                                               (row, col)):
                if errnum != 0:
                    toappend.append(errnum)
                    if pievar != 'stepname':
                        pietitle += '\n' + TITLEMAP[pievar] + str(piekey) + ': ' + str(errnum)
                    else:
                        pietitle += '\n' + TITLEMAP[pievar] + str(piekey).split('/')[1] + \
                            ': ' + str(errnum)
            pieinfo.append(toappend)
            sum_errors = sum(toappend)
            pietitlerow.append('Total Errors: ' + str(sum_errors) + '\n' + pietitle)

            total_errors['row'][irow] += sum_errors
            total_errors['col'][icol] += sum_errors

        pietitles.append(pietitlerow)

    return total_errors, pieinfo, pietitles


def get_header_titles(varname, errors, session=None):
    """Gets the titles that will end up being the <th> tooltips for the global view

    :param str varname: Name of the column or row variable
    :param list errors: A list of the total number of errors for the row or column
    :param cherrypy.Session session: Stores the information for a session
    :returns: A list of strings of the titles based on the column or row variable
              and the number of errors
    :rtype: list
    """

    output = []

    for name in check_session(session).get_allmap()[varname]:

        if varname == 'stepname':
            newnamelist = name.lstrip('/').split('/')
            newname = newnamelist[0] + '<br>' + '/'.join(newnamelist[1:])
            output.append({'title': name, 'name': newname})

        elif varname == 'errorcode':
            output.append({'title': str('\n --- \n'.join(
                check_session(session).get_errors_explained()[name]
                )
                                       ).rstrip('\n'),
                           'name': name})

        else:
            output.append({'title': name, 'name': name})

    for i, title in enumerate(output):
        title['title'] = ('Total errors: ' + str(errors[i]) + '\n' +
                          title['title'])

    return output


def return_page(pievar, session=None):
    """Get the information for the global views webpage

    :param str pievar: The variable to divide the piecharts by.
                       This is the variable that does not make up the axes of the page table
    :param cherrypy.Session session: Stores the information for a session
    :returns: Dictionary of information used by the global views page
              Of interest for other applications is the dictionary member 'steplist'.
              It is a tuple of the names of each step and the errors table for each of these steps.
              The table is an array of rows of the number of errors. Each row is an error code,
              and each column is a site.
    :rtype: dict
    """

    # Based on the dimesions from the user, create a list of pies to show
    rowname, colname = get_row_col_names(pievar)

    total_errors, pieinfo, pietitles = get_errors_and_pietitles(pievar, session)

    return {
        'collist': get_header_titles(colname, total_errors['col'], session),
        'pieinfo': pieinfo,
        'rowzip':  zip(get_header_titles(rowname, total_errors['row'], session), pietitles),
        'pievar':  pievar,
        }
