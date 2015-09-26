###############################################################################
#
# (C) Copyright 2015 Riverbed Technology, Inc
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
###############################################################################


###############################################################################
# HP EVA API Library
# This assumes the backend is HP EVA 8400
# Requires HP P6000 SSSU Management SDK installed
###############################################################################

from os import getenv, environ
import subprocess

# Defaults
check_system = None  # By default check all systems
timeout = None  # None means no timeout
SSSU_WIN_PATH = ";C:\\Program Files (x86)\\Hewlett-Packard\\Sanworks\\Element Manager for StorageWorks HSV"
SSSU_NIX_PATH = ":/usr/local/bin"

# No real need to change anything below here
ok = 0
warning = 1
critical = 2
unknown = 3
not_present = -1

subitems = {'fan': 'fans', 'source': 'powersources', 'hostport': 'hostports', 'module': 'modules', 'sensor': 'sensors',
            'powersupply': 'powersupplies', 'bus': 'communicationbuses', 'port': 'fibrechannelports'}

# Implementation for HP SSSU cli calls
class hp_sssu(object):

    def __init__(self, server, system, username, password):
        self.server = server
        self.system = system
        self.username = username
        self.password = password
        self.path = ''
        self.set_path()

    def runCommand(self, command):
        """ runCommand: Runs command from the shell prompt. Exit if unsuccessful """
        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,)
        try:
            stdout, stderr = proc.communicate('through stdin to stdout', timeout)
        except: # catch *all* exceptions
            #e = sys.exc_info()[0]
            #print( "Error: %s" % e )
            #exit(unknown)
            pass
        #print ("Returned: %s" % stdout)
        if proc.returncode > 1:
            #print ("Error %s: %s\n command was: '%s'" % (proc.returncode, stderr.strip(), command))
            #print ("Returned: %s" % stdout)
            return "", stderr.decode('UTF-8'), proc.returncode
        else:
            return stdout.decode('UTF-8'), stderr.decode('UTF-8'), proc.returncode

    def run_sssu(self, command):
        """Runs the sssu command. This one is responsible for error checking from sssu"""
        commands = []

        continue_on_error = "set option on_error=continue"
        login = "select manager %s USERNAME=""%s"" PASSWORD=""%s""" % (
            self.server, self.username, self.password)

        commands.append(continue_on_error)
        commands.append(login)
        if self.system is not None:
            #commands.append('set SYSTEM "%s" manage' % self.system)
            commands.append('select SYSTEM "%s"' % self.system)
        #commands.append ('\r\n')
        commands.append(command)

        commandstring = "sssu "
        for i in commands:
            commandstring += '"%s" ' % i

        # print mystring
        # if command == "ls system full":
        #	output = runCommand("cat sssu.out")
        # elif command == "ls disk_groups full":
        #	output = runCommand("cat ls_disk*")
        # elif command == "ls controller full":
        #	output = runCommand("cat ls_controller")
        # else:
        #	print "What command is this?", command
        #	exit(unknown)
        output, err, status = self.runCommand(commandstring)
        # Should the command not give any output
        if output is '':
            return output, err, status
        output = output.split('\n')
        # Lets process the top few results from the sssu command. Make sure the
        # results make sense
        error = 0
        if output.pop(0).strip() != '':
            error = 1
        if output.pop(0).strip() != '':
            error = 2
        if output.pop(0).strip().find('SSSU for HP') != 0:
            error = 3
        if output.pop(0).strip().find('Version:') != 0:
            error = 4
        if output.pop(0).strip().find('Build:') != 0:
            error = 5
        if output.pop(0).strip().find('NoSystemSelected> ') != 0:
            error = 6
        str_buffer = ""
        for i in output:
            str_buffer = str_buffer + i + "\n"
            if i.find('Error') > -1:
                #print ("This is the command i was trying to execute: %s" % i)
                error = 1
            if i.find('information:') > 0:
                break
        if error > 0:
            #print ("Error running the sssu command: " + str(error))
            #print (commandstring)
            #print (str_buffer)
            return "", err, error
        objects = []
        current_object = None
        for line in output:
            if len(line) == 0:
                continue
            line = line.strip()
            tmp = line.split()
            if len(tmp) == 0:
                if current_object:
                    if not current_object['master'] in objects:
                        objects.append(current_object['master'])
                    current_object = None
                continue
            key = tmp[0].strip()
            if current_object and not current_object['master'] in objects:
                objects.append(current_object['master'])
            if key == 'object':
                current_object = {}
                current_object['master'] = current_object
            if key == 'controllertemperaturestatus':
                current_object = current_object['master']
            if key == 'iomodules':
                key = 'modules'
            # if key in subitems.values():
            #	object['master'][key] = []
            if key in subitems.keys():
                mastergroup = subitems[key]
                master = current_object['master']
                current_object = {}
                current_object['object_type'] = key
                current_object['master'] = master
                if not current_object['master'].has_key(mastergroup):
                    current_object['master'][mastergroup] = []
                current_object['master'][mastergroup].append(current_object)

            if line.find('.:') > 0:
                # We work on first come, first serve basis, so if
                # we accidentally see same key again, we will ignore
                if not key in current_object:
                    value = ' '.join(tmp[2:]).strip()
                    current_object[key] = value
        # Check if we were instructed to check only one eva system
        global check_system
        if command == "ls system full" and check_system is not None:
            tmp_objects = []
            for i in objects:
                if i['objectname'] == check_system:
                    tmp_objects.append(i)
            objects = tmp_objects
        return objects, err, 0

    def set_path(self):
            current_path = getenv('PATH')
            if self.path == '':
                if current_path.find('C:\\') > -1:  # We are on Win platform
                    self.path = SSSU_WIN_PATH
                else:
                    self.path = SSSU_NIX_PATH
            current_path = "%s%s" % (current_path, self.path)
            environ['PATH'] = current_path

if __name__ == '__main__':
    longserviceoutput="\n"
    system_name = "systemname"
    command = "ls system %s" % system_name
    objects = hp_sssu("localhost", system_name, "username", "password").run_sssu(command)
    for i in objects:
        # Collect info
        longserviceoutput +="%s = %s (%s)\n" % (i['objectname'], i['operationalstate'], i['operationalstatedetail'])
        interesting_fields = 'licensestate|systemtype|firmwareversion|nscfwversion|totalstoragespace|usedstoragespace|availablestoragespace'
        for x in interesting_fields.split('|'):
            longserviceoutput +="- %s = %s \n" % (x, i[x])
        longserviceoutput += "\n"
    print (longserviceoutput)

