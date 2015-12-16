#!/usr/bin/python
# -*- coding: UTF-8 -*-
###############################################################################
#
# (C) Copyright 2014 Riverbed Technology, Inc
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

# Written and tested with Python 2.7, requests library 2.8.1 and lxml 3.5.
# Tested against HP MSA P2000 G3 FC, Bundle Version TS201R015, Storage Controller T201P02

import optparse
import sys
import errno
import shlex
import subprocess

# These are used for generating random clone serial
import string
import random
import logging

# Script DB is used to store/load the cloned lun
# information and the credentials
import script_db

# For setting up PATH
import os

import time
import re
import requests
requests.packages.urllib3.disable_warnings()
import hashlib
from lxml import etree

# Paths for VADP scripts
PERL_EXE = r'"C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\bin\perl.exe" '
WORK_DIR =  r'C:\rvbd_handoff_scripts'
VADP_CLEANUP = WORK_DIR + r'\vadp_cleanup.pl'
VADP_SETUP = WORK_DIR + r'\vadp_setup.pl'
HANDOFF_LOG_FILE = WORK_DIR + r'\handoff.txt'

def set_logger():
    logging.basicConfig(filename= HANDOFF_LOG_FILE, level=logging.DEBUG,
                        format='%(asctime)s : %(levelname)s: %(message)s',
                         datefmt='%m/%d/%Y %I:%M:%S %p')

def script_log(msg):
    '''
    Local logs are sent to std err

	msg : the log message
    '''
    sys.stderr.write(msg + "\n")
    logging.info(msg)

def set_script_path(prefix):
    '''
	Sets the paths according to the prefix.

	prefix : full path of directory in which the VADP scripts reside
    '''
    global WORK_DIR, VADP_CLEANUP, VADP_SETUP
    WORK_DIR = prefix
    VADP_CLEANUP = WORK_DIR + r'\vadp_cleanup.pl'
    VADP_SETUP = WORK_DIR + r'\vadp_setup.pl'

def assert_response_ok(obj):
    """Parses the XML returned by the device to check the return code.
    Raises an error if the return code is not 0.
    """
    for obj in obj.iter():
        if obj.get("basetype") != "status":
            continue
        ret_code = ret_str = None
        for prop in obj.iter("PROPERTY"):
            if prop.get("name") == "return-code":
                ret_code = prop.text
            elif prop.get("name") == "response":
                ret_str = prop.text
        if ret_code != "0":
            script_log('There was a problem with the previous operation.')
            script_log(ret_str)
            exit(1)
        else:
            script_log('operation succeeded.')
            return
    script_log("No status found")

def check_lun(conn, serial):
    '''
    Checks for the presence of lun

    server : hostname/ip address
    serial : lun serial

    Just checks to see if a volume exists for this LUN serial
    Will fail if does not exist.

    Example output:

    '''
    script_log('just getting a handle on the LUN.')

    requestvolumes = base_url + "/show/volume-names"
    volumes = requests.get(requestvolumes, verify=False, headers=headers, timeout=10)
    obj = etree.XML(volumes.text.encode('utf-8'))
    assert_response_ok(obj)
    #script_log(volumes.text.encode('utf-8'))
    breakloop = False
    for obj in obj.iter():
        if breakloop:
            break
        for prop in obj.iter("PROPERTY"):
            prop_name = prop.get("name")
            if prop_name == "volume-name":
                volume = prop.text
            if prop_name == "serial-number":
                lunserial = prop.text
                if lunserial == serial:
                    volname = volume
                    script_log('Volume for LUN ' + serial + " is " + volname + '.\n')
                    breakloop = True
                    break
                else:
                    volname = ''
    #If the name doesn't exist, will need to error with LUN serial not found.
    if volname == '':
        script_log("Unable to find LUN.")
        sys.exit(1)
    else:
        script_log ("OK\n")
    sys.exit(0)

def create_snap(cdb, sdb, rdb, server, serial, snap_name,
                access_group, proxy_host, datacenter,
                include_hosts, exclude_hosts,
                category, protect_category):
    '''
    Creates a snapshot

    cdb : credentials db
    sdb : script db
    rdb : snap name to replay name db
    rdb : snap name to replay name db
    server : hostname/ip address
    serial : lun serial
    snap_name : the snapshot name
    access_group : the initiator group to which cloned lun is mapped
    proxy_host : the host on which clone lun is mounted
    datacenter : VMware Data center
    include_hosts : Regex for including hosts in datacenter
    exclude_hosts : Regex for excluding hosts in datacenter
    category : snapshot category
    protect_category : the snapshot category for which proxy backup is run

    Prints the snapshot name on the output if successful
    and exits the process.
    If unsuccessful, exits the process with non-zero error code.

    If the snapshot category matches the protected category, we run
    data protection for this snapshot.
    '''
    # Check for duplicate requests, these are possible
    # if Granite Core Crashes or the Handoff host itself crashed
    script_log('Starting create_snap')

    rdb_snap_name, array_volname = rdb.get_snap_info(snap_name)
    if rdb_snap_name:
        script_log("Duplicate request")
        print (snap_name)
        return

    # Run proxy backup on this snapshot if its category matches
    # protected snapshot category

    if category == protect_category:
        # Un-mount the previously mounted cloned lun from proxy host
        if unmount_proxy_backup(cdb, sdb, serial, proxy_host, datacenter, include_hosts, exclude_hosts) :
            # Delete the cloned snapshot
            unmap_cloned_lun(cdb, sdb, server, serial)
            # Create a cloned snapshot lun form the snapshot
            cloned_lun_serial = create_snap_clone(cdb, sdb, rdb, server, serial, snap_name, access_group)
            # Mount the snapshot on the proxy host
            mount_proxy_backup(cdb, sdb, cloned_lun_serial, serial,
                               access_group, proxy_host, datacenter,
                               include_hosts, exclude_hosts)
            print (snap_name)
            return

    # Creating a snapshot and no backup
    requestvolumes = base_url + "/show/volume-names"
    volumes = requests.get(requestvolumes, verify=False, headers=headers, timeout=10)
    obj = etree.XML(volumes.text.encode('utf-8'))
    assert_response_ok(obj)

    breakloop = False
    for obj in obj.iter():
        if breakloop:
            break
        for prop in obj.iter("PROPERTY"):
            prop_name = prop.get("name")
            if prop_name == "volume-name":
                volume = prop.text
            if prop_name == "serial-number":
                lunserial = prop.text
                if lunserial == serial:
                    volname = volume
                    script_log("Creating snapshot with volume: " + volname + '.\n')
                    breakloop = True
                    break
                else:
                    volname = ''
    #If the name doesn't exist, will need to error with LUN serial not found.
    if volname == '':
        script_log("Unable to find LUN.")
        sys.exit(1)

    #Create snapshot
    # The array snapshot name will be rvbd_xxxxxxxx.
    # will take the first 8 characters of the snap_name for the random characters.

    array_volname = "rvbd_" + snap_name[0:15]
    createsnapshot = base_url + "/create/snapshots" + "/" + "volumes/" + volname + "/" + array_volname
    createsnap = requests.get(createsnapshot, verify=False, headers=headers, timeout=10)
    obj = etree.XML(createsnap.text.encode('utf-8')).find("OBJECT")
    assert_response_ok(obj)

    #putting the info into the database so we know what to remove when we want to.
    rdb.insert_snap_info(snap_name, array_volname)
    print (snap_name)
    return


def remove_snap(cdb, sdb, rdb, server, serial, snap_name, proxy_host,
                datacenter, include_hosts, exclude_hosts):
    '''
    Removes a snapshot

    cdb : credentials db
    sdb : script db
    rdb : snap name to replay name db
    server : Netapp hostname/ip address
    serial : lun serial
    snap_name : the snapshot name
    proxy_host : proxy host
    datacenter : vCenter datacenter
    include_hosts : Regex to include hosts in datacenter
    exclude_hosts : Regex to exclude hosts in datacenter

    If unsuccessful, exits the process with non-zero error code,
    else exits with zero error code.

    If we are removing a protected snapshot, we un-mount and cleanup
    the cloned snapshot lun and then remove the snapshot.

    '''

    clone_serial, protected_snap, group = sdb.get_clone_info(serial)

    array_volname = ''
    # Check if we are removing a protected snapshot
    if protected_snap == snap_name:
        if clone_serial:
            array_volname = clone_serial[1:7]+clone_serial[10:15]+'20000'+clone_serial[16:33]
        # Deleting a protected snap. Un-mount the clone from the proxy host
        if not unmount_proxy_backup(cdb, sdb, serial, proxy_host,
                                    datacenter, include_hosts, exclude_hosts):
            sys.exit(1)
        # Delete the snapshot cloned lun
        script_log("Running delete cloned_lun with parameters: "+serial)
        unmap_cloned_lun(cdb, sdb, server, serial)

    if not array_volname :
        s1, array_volname = rdb.get_snap_info(snap_name)

    if array_volname :
        script_log("The Array Volume name is " + array_volname + "\n.")
        deletesnapshot = base_url + "/delete/snapshot" + "/" + "cleanup" + "/" + array_volname
        deletesnap = requests.get(deletesnapshot, verify=False, headers=headers, timeout=10)
        script_log (array_volname + " snapshot removed\n")
        rdb.delete_clone_info(snap_name)
        sys.exit(0)
    else:
        script_log("No array volume to delete.")
        sys.exit(1)

def create_snap_clone(cdb, sdb, rdb, server, serial, snap_name, accessgroup):
    '''
    Creates a lun out of a snapshot

    cbd : credentials db
    sdb : script db
    server : the storage array
    serial : the original lun serial
    snap_name : the name of the snapshot from which lun must be created
    access_group : initiator group for Netapp, Storage Group for EMC

    Since this step is run as part of proxy backup, on errors,
    we exit with status zero so that Granite Core ACKs the Edge.
    '''
    script_log('Starting create_snap_clone')

    requestvolumes = base_url + "/show/volume-names"
    volumes = requests.get(requestvolumes, verify=False, headers=headers, timeout=10)
    obj = etree.XML(volumes.text.encode('utf-8'))

    breakloop = False
    for obj in obj.iter():
        if breakloop:
            break
        for prop in obj.iter("PROPERTY"):
            prop_name = prop.get("name")
            if prop_name == "volume-name":
                volume = prop.text
            if prop_name == "serial-number":
                lunserial = prop.text
                if lunserial == serial:
                    volname = volume
                    script_log("Creating snapshot with volume: " + volname + '.\n')
                    breakloop = True
                    break
                else:
                    volname = ''

    #If the name doesn't exist, will need to error with LUN serial not found.

    if volname == '':
        script_log("Unable to find LUN.")
        sys.exit(1)

    #Create snapshot
    # The array snapshot name will be rvbd_xxxxxxxx.
    # will take the first 16 characters of the snap_name for the random characters.

    array_volname = "rvbd_" + snap_name[0:15]

    # need to put in the , snap_name, volumes=volume_name)

    createsnapshot = base_url + "/create/snapshots" + "/" + "volumes/" + volname + "/" + array_volname
    createsnap = requests.get(createsnapshot, verify=False, headers=headers, timeout=10)
    obj = etree.XML(createsnap.text.encode('utf-8')).find("OBJECT")
    assert_response_ok(obj)
    script_log('created snapshot ' + array_volname)
    time.sleep(1)

    #putting the info into the database so we know what to remove when we want to.
    rdb.insert_snap_info(snap_name, array_volname)

    #Assign initiator to snapshot.

    #CLI would be: map volume access read-write host 50014380029baa82 lun 99 rvbd_test1

    # Get next available LUN number.
    luns = []
    getVLUN = base_url + "/show/host-maps"
    tree = requests.get(getVLUN, verify=False, headers=headers, timeout=10)
    obj = etree.XML(tree.text.encode('utf-8'))

    for obj in obj.iter():
        if obj.get("basetype") != "host-view-mappings":
            continue

        for prop in obj.iter("PROPERTY"):
            if prop.get("name") == "lun":
                luns.append(int(prop.text))

    lun = 1
    lun += max(luns)

    # Map volume with the new LUN number.
    # Requires volume_name, wwpns
    mapLUN = base_url + "/map/volume/access/read-write/host/" + accessgroup + "/lun/" + str(lun) + "/" + array_volname
    script_log('mapping LUN with url: '+ mapLUN)
    time.sleep(5)
    assignmapping = requests.get(mapLUN, verify=False, headers=headers, timeout=10)
    time.sleep(5)
    assignmapping = requests.get(mapLUN, verify=False, headers=headers, timeout=10)
    obj = etree.XML(assignmapping.text.encode('utf-8')).find("OBJECT")
    assert_response_ok(obj)
    script_log('Assigned mapping on MSA to ' + accessgroup + '.')
    #Getting the LUN serial number from the cloned LUN:
    requestvolumes = base_url + "/show/volume-names"
    volumes = requests.get(requestvolumes, verify=False, headers=headers, timeout=10)
    obj = etree.XML(volumes.text.encode('utf-8'))
    assert_response_ok(obj)

    breakloop = False
    for obj in obj.iter():
        if breakloop:
            break
        for prop in obj.iter("PROPERTY"):
            prop_name = prop.get("name")
            if prop_name == "volume-name":
                volume = prop.text
            if prop_name == "serial-number":
                lunserial = prop.text
                if volume == array_volname:
                    script_log("Serial Number for cloned LUN is: " + lunserial + '.\n')
                    breakloop = True
                    break
                else:
                    volname = ''
    #If the name doesn't exist, will need to error with LUN serial not found.
    if lunserial == '':
        script_log("Unable to find LUN.")
        sys.exit(1)
    script_log("Again, Serial Number for cloned LUN is: " + lunserial + '.\n')
    cloned_lun_serial = '6'+lunserial[0:6]+'000'+lunserial[6:12]+lunserial[16:33]
    script_log("Serial Number for cloned LUN in ESX format is: " + cloned_lun_serial)

    # Store this information in a local database.
    # This is needed because when you are running cleanup,
    # the script must find out which cloned lun needs to me un-mapped.
    # Here, the serial = the HP array serial number. The cloned_lun_serial is the serial used to mount the LUN's datastore in ESX.
    script_log('Inserting serial: %s, cloned_lun_serial: %s, snap_name: %s, group: %s' %\
               (serial, cloned_lun_serial, snap_name, accessgroup))
    sdb.insert_clone_info(serial, cloned_lun_serial, snap_name, accessgroup)
    rdb.insert_snap_info(snap_name, volname)
    #script_log("Index is:" + str(index))
    return cloned_lun_serial


def unmap_cloned_lun(cdb, sdb, server, lun_serial):
    '''
    For the given serial, finds the last cloned lun
    and unmaps it from ESXi.

    Note that it does not delete the snapshot, the snapshot is left behind.

    cdb : credentials db
    sdb : script db
    lun_serial : the lun serial for which we find the last cloned lun
    '''
    script_log('Unmapping previous lun from the ESXi proxy with serial: '+lun_serial)
    array_volname = lun_serial[1:7]+lun_serial[10:15]+'20000'+lun_serial[16:33]
    clone_lun, snap_name, group = sdb.get_clone_info(lun_serial)
    script_log('cloned_lun is: '+ clone_lun)
    clone_serial = clone_lun
    script_log('Clone serial: %s , snap_name: %s, group: %s' % \
               (str(clone_serial), str(snap_name), str(group)))

    if not clone_serial:
        script_log ("No snap clone to be unmapped.")
        return

    script_log("Unmapping cloned lun on " + snap_name + "\n")
    array_volname = 'rvbd_' + snap_name[0:15]
    unmap = base_url + "/unmap/volume" + "/" + "host" + "/" + group + "/" + array_volname
    try:
        unmap_lun = requests.get(unmap, verify=False, headers=headers, timeout=10)
        obj = etree.XML(deletesnap.text.encode('utf-8')).find("OBJECT")
    except Exception:
        pass
    script_log ("Snapshot " + array_volname + " unmapped from " + group + "\n")
    #rdb.delete_clone_info(snap_name)
    sdb.delete_clone_info(lun_serial)

    script_log("Cloned lun %s unmapped successfully" % clone_serial)
    return


def mount_proxy_backup(cdb, sdb, cloned_lun_info, snap_name,
                       access_group, proxy_host, datacenter,
                       include_hosts, exclude_hosts):
    '''
    Mounts the proxy backup on the proxy host

    cdb : credentials db
    sdb : script db
    cloned_lun_serial : the lun serial of the cloned snapshot lun
    snap_name : snapshot name
    access_group : initiator group
    proxy_host : the ESX proxy host/VMware VCenter
    datacenter : VMware datacenter
    include_hosts : Regex to include hosts for proxy backup
    exclude_hosts : Regex to exclude hosts for proxy backup
    '''
    # Get credentials for the proxy host
    username, password = cdb.get_enc_info(proxy_host)
    # The clone lun info is of the form
    # index:clone_lun_serial
    cloned_lun_serial = cloned_lun_info.split(":")[-1]

    # Create the command to be run
    cmd = ('%s "%s" --server %s --username %s --password %s --luns %s ' \
           '--datacenter "%s" --include_hosts "%s" --exclude_hosts "%s" ' \
           '--extra_logging 1' %\
           (PERL_EXE, VADP_SETUP, proxy_host,
            username, password, cloned_lun_serial,
            datacenter, include_hosts, exclude_hosts))

    script_log("Command is: " + cmd)
    proc = subprocess.Popen(cmd,
                            stdin = subprocess.PIPE,
                            stdout = subprocess.PIPE,
                            stderr = subprocess.PIPE)

    out, err = proc.communicate()
    status = proc.wait()
    script_log("Output: " +  str(out))
    script_log("ErrOut: " +  str(err))
    if status:
        script_log("Failed to mount the cloned lun: " + str(status))
    else:
        script_log("Mounted the cloned lun successfully")


def unmount_proxy_backup(cdb, sdb, lun_serial, proxy_host,
                         datacenter, include_hosts, exclude_hosts):
    '''
    Un-mounts the previously mounted clone lun from the proxy host

    cdb : credentials db
    sbd : script db
    lun_serial : the lun serial
    proxy_host : the ESX proxy host
    datacenter : VMware datacenter
    include_hosts : Hosts to include to perform proxy backup
    exclude_hosts : Hosts to exclude to perform proxy backup

    '''
    # Get the credentials for proxy host
    username, password = cdb.get_enc_info(proxy_host)

    # Find the cloned lun from the script db for given lun
    clone_serial, snap_name, group = sdb.get_clone_info(lun_serial)
    script_log('Clone serial: %s , snap_name: %s, group: %s' % \
               ( str(clone_serial), str(snap_name), str(group)))
    # The clone lun info is of the form
    # index:clone_lun_serial
    cloned_lun = clone_serial.split(':')[-1]

    if not cloned_lun:
         script_log("No clone serial found, returning")
         return	True

    cmd = ('%s "%s" --server %s --username %s --password %s --luns %s ' \
           '--datacenter "%s" --include_hosts "%s" --exclude_hosts "%s" '\
           '--extra_logging 1' %\
           (PERL_EXE, VADP_CLEANUP,
           proxy_host, username, password, cloned_lun,
           datacenter, include_hosts, exclude_hosts))

    script_log("Command is: " + cmd)
    proc = subprocess.Popen(cmd,
                            stdin = subprocess.PIPE,
                            stdout = subprocess.PIPE,
                            stderr = subprocess.PIPE)

    out, err = proc.communicate()
    status = proc.wait()
    script_log("Output: " +  str(out))
    script_log("ErrOut: " +  str(err))
    if status != 0:
        script_log("Failed to un-mount the cloned lun: " + str(status))
        return False
    else:
        script_log("Un-mounted the clone lun successfully")

    return True

def get_option_parser():
    '''
    Returns argument parser
    '''
    global WORK_DIR
    parser = optparse.OptionParser()

    # These are script specific parameters that can be passed as
    # script arguments from the Granite Core.
    parser.add_option("--array",
                      type="string",
                      help="storage array ip address or dns name")
    parser.add_option("--username",
                      type="string",
                      default="root",
                      help="log username")
    parser.add_option("--password",
                      type="string",
                      default="password",
                      help="login password")
    parser.add_option("--access-group",
                      type="string",
                      default="",
                      help="Access group to protect")
    parser.add_option("--proxy-host",
                      type="string",
                      default="",
                      help="Proxy Host Server")
    parser.add_option("--datacenter",
                      type="string",
                      default="",
                      help="Datacenter to look for proxy host")
    parser.add_option("--include-hosts",
                      type="string",
                      default=".*",
                      help="Include Host Regex")
    parser.add_option("--exclude-hosts",
                      type="string",
                      default="",
                      help="Exclude Host Regex")
    parser.add_option("--work-dir",
                      type="string",
                      default=WORK_DIR,
                      help="Directory path to the VADP scripts")
    parser.add_option("--protect-category",
                      type="string",
                      default="daily",
                      help="Directory path to the VADP scripts")

    # These arguments are always passed by Granite Core
    parser.add_option("--serial",
                      type="string",
                      help="serial of the lun")
    parser.add_option("--operation",
                      type="string",
                      help="Operation to perform (HELLO/SNAP/REMOVE)")
    parser.add_option("--snap-name",
                      type="string",
                      default="",
                      help="snapshot name")
    parser.add_option("--issue-time",
                      type="string",
                      default="",
                      help="Snapshot issue time")
    parser.add_option("--category",
                      type="string",
                      default="manual",
                      help="Snapshot Category")
    return parser


if __name__ == '__main__':
    set_logger()
    script_log("Running script with args: %s" % str(sys.argv))
    options, argsleft = get_option_parser().parse_args()

    # Set the working dir prefix
    set_script_path(options.work_dir)

    # Credentials db must be initialized using the cred_mgmt.py file
    cdb = script_db.CredDB(options.work_dir + r'\cred_db')

    # Initialize the script database
    sdb = script_db.ScriptDB(options.work_dir + r'\script_db')
    sdb.setup()

    # Create snap to replay mapping database
    rdb = script_db.SnapToReplayDB(options.work_dir + r'\replay_db')
    rdb.setup()

    # Setup server/lun info
    conn = options.array
    array = options.array

    serial = options.serial[1:7] + options.serial[10:16] + '0000' + options.serial[16:]

    # Connect to MSA array.

    # Get credentials for the proxy host
    username, password = cdb.get_enc_info(array)

    def create_login_hash(username, password):
        login_string = "{0}_{1}".format(username, password)
        return hashlib.md5(login_string).hexdigest()

    base_url = 'https://' + array + '/api'
    login_hash = create_login_hash(username, password)
    url_login = base_url + "/login/{0}".format(login_hash)
    req_login = requests.get(url_login, verify=False)
    sessionKey = None
    obj = etree.XML(req_login.text.encode('utf-8')).find("OBJECT")
    #assert_response_ok(obj)
    for prop in obj.iter("PROPERTY"):
        if prop.get("name") == "response":
            sessionKey = prop.text
            break
    headers = {'datatype': 'api', 'sessionKey': sessionKey}
    script_log('successfully logged into MSA array.')

    if options.operation == 'HELLO':
        check_lun(conn, serial)
    elif options.operation == 'CREATE_SNAP':
        create_snap(cdb, sdb, rdb, conn, serial, options.snap_name,
                    options.access_group, options.proxy_host,
                    options.datacenter, options.include_hosts,
                    options.exclude_hosts,
            options.category, options.protect_category)
    elif options.operation == 'REMOVE_SNAP':
        remove_snap(cdb, sdb, rdb, conn, serial,
            options.snap_name, options.proxy_host,
                    options.datacenter, options.include_hosts,
                    options.exclude_hosts)
    else:
        print ('Invalid operation: %s' % str(options.operation))
        cdb.close()
        sdb.close()
        rdb.close()
        sys.exit(errno.EINVAL)

    sdb.close()
    cdb.close()
    rdb.close()
 