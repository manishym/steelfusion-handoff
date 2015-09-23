
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
# Need the HP P6000 sssu manageability sdk for this script
###############################################################################

from os import getenv, environ
import subprocess

# Defaults
#hostname = "localhost"
hostname = "172.16.1.216"
system = "STOMO-PRIMARY"
username = "administrator"
password = "P@ssw0rd"
path = '' #os.path.normpath('C:/Program Files (x86)/Hewlett-Packard/Sanworks/Element Manager for StorageWorks HSV/')
escape_newlines = False
check_system = None  # By default check all systems
timeout = None  # 0 means no timeout
longserviceoutput = "\n"


# set to true, if you do not have sssu binary handy
server_side_troubleshooting = False

# No real need to change anything below here
version = "0.1.0"
ok = 0
warning = 1
critical = 2
unknown = 3
not_present = -1
debugging = True

subitems = {'fan': 'fans', 'source': 'powersources', 'hostport': 'hostports', 'module': 'modules', 'sensor': 'sensors',
            'powersupply': 'powersupplies', 'bus': 'communicationbuses', 'port': 'fibrechannelports'}


def debug(debugtext):
    global debugging
    if debugging:
        print (debugtext)

def runCommand(command):
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
    if proc.returncode > 0:
        print ("Error %s: %s\n command was: '%s'" % (proc.returncode, stderr.strip(), command))
        # File not found, lets print path
        if proc.returncode == 127 or proc.returncode == 1:
            path = getenv("PATH")
            print ("Current Path: %s" % path)
            exit(unknown)
    else:
        return stdout.decode('UTF-8')

def run_sssu(system=None, command="ls system full"):
    """Runs the sssu command. This one is responsible for error checking from sssu"""
    commands = []

    continue_on_error = "set option on_error=continue"
    login = "select manager %s USERNAME=""%s"" PASSWORD=""%s""" % (
        hostname, username, password)

    commands.append(continue_on_error)
    commands.append(login)
    if system is not None:
        commands.append('select SYSTEM "%s"' % system)
    commands.append(command)

    commandstring = "sssu "
    for i in commands:
        commandstring += '"%s" ' % i
    global server_side_troubleshooting
    if server_side_troubleshooting == True:
        commandstring = 'cat "debug/%s"' % command

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
    output = runCommand(commandstring)
    debug(commandstring)

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
            print ("This is the command i was trying to execute: %s" % i)
            error = 1
        if i.find('information:') > 0:
            break
    if error > 0:
        print ("Error running the sssu command: " + str(error))
        print (commandstring)
        print (str_buffer)
        exit(unknown)
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
    return objects

def check_system(system_name):
    summary = ""
    perfdata = ""
    # longserviceoutput="\n"
    command = "ls system %s" % system_name
    objects = run_sssu(system_name, command)
    for i in objects:
        name = i['objectname']
        operationalstate = i['operationalstate']
        # Lets add to the summary
        summary += " %s=%s " % (name, operationalstate)
        # Collect the performance data
        interesting_perfdata = 'totalstoragespace|usedstoragespace|availablestoragespace'
        perfdata += get_perfdata(
            i, interesting_perfdata.split('|'), identifier="%s_" % name)
        # Collect extra info for longserviceoutput
        longoutput("%s = %s (%s)\n" %
                   (i['objectname'], i['operationalstate'], i['operationalstatedetail']))
        interesting_fields = 'licensestate|systemtype|firmwareversion|nscfwversion|totalstoragespace|usedstoragespace|availablestoragespace'
        for x in interesting_fields.split('|'):
            longoutput("- %s = %s \n" % (x, i[x]))
        longoutput("\n")


def get_perfdata(my_object, interesting_fields, identifier=""):
    perfdata = ""
    for i in interesting_fields:
        if i == '':
            continue
        perfdata += "'%s%s'=%s " % (identifier, i, my_object[i])
    return perfdata

def longoutput(text):
    global longserviceoutput
    longserviceoutput = longserviceoutput + text


def get_longserviceoutput(my_object, interesting_fields):
    longserviceoutput = ""
    for i in interesting_fields:
        longserviceoutput += "%s = %s \n" % (i, my_object[i])
    return longserviceoutput

def set_path():
    global path
    current_path = getenv('PATH')
    if path == '':
        if current_path.find('C:\\') > -1:  # We are on this platform
            path = ";C:\\Program Files (x86)\\Hewlett-Packard\\Sanworks\\Element Manager for StorageWorks HSV"
        else:
            path = ":/usr/local/bin"
    current_path = "%s%s" % (current_path, path)
    environ['PATH'] = current_path
set_path()

def check_lun(server, serial):
    '''
    Checks for the presence of lun on given HP array

    server : HP EVA hostname/ip address
    serial : lun serial (unformatted)

    Exits the process with code zero if it finds the lun,
    or non-zero code otherwise
    '''
    lun_path = get_volume_path(server, convert_serial(serial))
    if len(lun_path) == 0:
        print ("Lun %s not found" % (serial))
        sys.exit(1)

    print ("OK")
    sys.exit(0)

def get_volume_path(server, system, wwnid):
    '''
    Gets the volume for the given lun

    server : HP EVA Management appliance hostname/ip address
    system : HP EVA Storage System Name
    wwnid : lun wwn id

    returns vdisk path
    '''
    #out, err = self.sssu(["find vdisk lunwwid="+wwid+" xml"])
    objects = run_sssu(system, ["find vdisk lunwwid="+wwnid])
    for i in objects:
        vdisk_name = i['objectname']
    return vdisk_name

    api = NaElement("lun-list-info")

    xo = server.invoke_elem(api)
    if (xo.results_status() == "failed") :
        print ("Error:\n")
        print (xo.sprintf())
        return ""

    luns = xo.child_get("luns")
    for luns in luns.children_get():
        if luns.child_get_string("serial-number") == serial:
            return luns.child_get_string("path")
    return ""

def convert_serial(serial):
    # Convert the serial seen on the Granite Core
    # to the serial that HP EVA understands.
    # Example:
    # Serial on Granite Core: 600143801259b9e40000500000490000
    # Serial EVA understands: 6001-4380-1259-b9e4-0000-5000-0049-0000
    s = ""
    for i, c in enumerate(serial):
        s += c
        if (i+1) % 4 == 0: s += '-'
    return s.strip('-')
    #return '-'.join([serial[:4], serial[4:8], serial[8:12], serial[12:16],serial[16:20],serial[20:24],serial[24:28],serial[28:32],serial[32:]])

if __name__ == '__main__':
    set_path()
    check_system(system)
    print ("%s" % longserviceoutput)
