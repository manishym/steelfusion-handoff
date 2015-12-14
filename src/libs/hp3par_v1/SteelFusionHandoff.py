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

# IMPORTANT: This script works only with Python 2.x and WILL NOT WORK with Python 3.x. 
# HP3Parclient only worked for 2.x at the time of this script. 

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

import hp3parclient
from hp3parclient import client, exceptions


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
	Sets the paths accroding to the prefix.
	
	prefix : full path of directory in which the VADP scripts reside
    '''
    global WORK_DIR, VADP_CLEANUP, VADP_SETUP
    WORK_DIR = prefix
    VADP_CLEANUP = WORK_DIR + r'\vadp_cleanup.pl'
    VADP_SETUP = WORK_DIR + r'\vadp_setup.pl'

def check_lun(conn, serial):
    '''
    Checks for the presence of lun

    server : hostname/ip address 
    serial : lun serial

    Just checks to see if a volume exists for this LUN serial 
    Will fail if does not exist. 

    Example output:
    >>> volumes["members"][5]
    {u'adminSpace': {u'rawReservedMiB': 384, u'freeMiB': 126, u'usedMiB': 2, u'reservedMiB': 128}, u'additionalStates': [],
    u'ssSpcAllocWarningPct': 0, u'creationTimeSec': 1382039701, u'wwn': u'60002AC000000000000000090000299F', u'id': 9, u'uui
    d': u'b8edd5be-99d8-4d69-9d78-24690d24f5d8', u'degradedStates': [], u'failedStates': [], u'rwChildId': 30399, u'copyType
    ': 1, u'state': 1, u'provisioningType': 2, u'userCPG': u'FC_r1', u'baseId': 9, u'usrSpcAllocWarningPct': 0, u'readOnly':
     False, u'snapshotSpace': {u'rawReservedMiB': 768, u'freeMiB': 512, u'usedMiB': 0, u'reservedMiB': 512}, u'userSpace': {
    u'rawReservedMiB': 768, u'freeMiB': 512, u'usedMiB': 0, u'reservedMiB': 512}, u'snapCPG': u'NL_r6', u'usrSpcAllocLimitPc
    t': 0, u'name': u'Bob_Test', u'sizeMiB': 10240, u'policies': {u'system': False, u'caching': True, u'oneHost': False, u's
    taleSS': True, u'zeroDetect': True}, u'ssSpcAllocLimitPct': 0, u'creationTime8601': u'2013-10-17T15:55:01-04:00'}

    >>> volumes["members"][5]['wwn']
    u'60002AC000000000000000090000299F'

        '''
    try:
        volumes = cl.getVolumes()
    except exceptions.HTTPUnauthorized as ex:
        print "You must login first"
    except Exception as ex:
        print "Unable to get volumes."
        print ex
        sys.exit(1)
    for volume in volumes['members']:
        if serial in volume['wwn'] :
            volname = volume['name']

#If the name doesn't exist, will need to error with LUN serial not found.    
    try:
        script_log('Volume for LUN ' + serial + " is " + volname + '.\n')
    except NameError:
        print("Unable to find LUN.")
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
            delete_cloned_lun(cdb, sdb, server, snap_name)
            # Create a cloned snapshot lun form the snapshot
            cloned_lun_serial = create_snap_clone(cdb, sdb, rdb, server, serial, snap_name, access_group)
            # Mount the snapshot on the proxy host
            mount_proxy_backup(cdb, sdb, cloned_lun_serial, snap_name,
                               access_group, proxy_host, datacenter,
                               include_hosts, exclude_hosts) 
            print (snap_name)
            return
            
    # Creating a snapshot and no backup
    try:
        volumes = cl.getVolumes()
    except exceptions.HTTPUnauthorized as ex:
        print "You must login first"
    except Exception as ex:
        print "Unable to get volumes."
        print ex
        sys.exit(1)
    for volume in volumes['members']:
        if serial in volume['wwn'] :
            volname = volume['name']
    #   script_log('Volume for LUN ' + serial + " is " + name + '.\n')
    #If the name doesn't exist, will need to error with LUN serial not found.    
    try:
        script_log("Creating snapshot with volume: " + volname + '.\n')
    except NameError:
        script_log("Unable to find LUN.")
        sys.exit(1)
    #Create snapshot
    # The array snapshot name will be rvbd_xxxxxxxx.
    # will take the first 8 characters of the snap_name for the random characters.

    try:
        array_volname = "rvbd_" + snap_name[0:15]
        cl.createSnapshot(array_volname,volname)
    except Exception as ex:
        print "Unable to create snapshot."
        print ex
        sys.exit(1)
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
        array_volname = clone_serial.split(":")[0]
        # Deleting a protected snap. Un-mount the clone from the proxy host
        if not unmount_proxy_backup(cdb, sdb, serial, proxy_host,
                                    datacenter, include_hosts, exclude_hosts):
            sys.exit(1)
        # Delete the snapshot cloned lun
        delete_cloned_lun(cdb, sdb, server, snap_name)

    if not array_volname :
        s1, array_volname = rdb.get_snap_info(snap_name)
        script_log("The Array Volume name is " + array_volname + "\n.")

    try:
        cl.deleteVolume(array_volname)
    except Exception as ex:
        print "Unable to delete snapshot."
        print ex
        sys.exit(1)
    script_log ("SnapshotSet removed\n")
    rdb.delete_clone_info(snap_name)
    sys.exit(0)


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

    try:
        volumes = cl.getVolumes()
    except exceptions.HTTPUnauthorized as ex:
        print "You must login first"
    except Exception as ex:
        print "Unable to get volumes."
        print ex
        sys.exit(1)
    for volume in volumes['members']:
        if serial in volume['wwn'] :
            volname = volume['name']
    #   script_log('Volume for LUN ' + serial + " is " + name + '.\n')
    #If the name doesn't exist, will need to error with LUN serial not found.    
    try:
        script_log("Creating snapshot with volume: " + volname + '.\n')
    except NameError:
        script_log("Unable to find LUN.")
        sys.exit(1)
    #Create snapshot
    # The array snapshot name will be rvbd_xxxxxxxx.
    # will take the first 8 characters of the snap_name for the random characters.
    try:
        array_volname = "rvbd_" + snap_name[0:15]
        cl.createSnapshot(array_volname,volname)
    except Exception as ex:
        print "Unable to create snapshot."
        print ex
        sys.exit(1)

    #putting the info into the database so we know what to remove when we want to.
    rdb.insert_snap_info(snap_name, volname)
    
    #Create VLUN from the snapshot.
    try:
        cl.createVLUN(array_volname,hostname=accessgroup, auto="True")
    except Exception as ex:
        print "Unable to create VLUN from snapshot."
        print ex
        sys.exit(1)

	#Getting the LUN serial number from the cloned LUN:
    '''
    Sample output
    a=cl.getVLUN("rvbd_test2")
    {u'failedPathPol': 1, u'volumeName': u'rvbd_test2', u'hostname': u'nydemdl380g8vCAC01', u'portPos': {u'node': 1, u'slot
    : 1, u'cardPort': 1}, u'multipathing': 1, u'failedPathInterval': 0, u'active': True, u'type': 3, u'remoteName': u'10000
    051E56601F', u'lun': 4, u'volumeWWN': u'60002AC000000000020077010000299F'}
    '''
    
    try:
        cloned_lun_info=cl.getVLUN(array_volname)
    except Exception as ex:
        print "Unable to get LUN info."
        print ex
        sys.exit(1)
    cloned_lun_serial = cloned_lun_info['volumeWWN']

    # Store this information in a local database. 
    # This is needed because when you are running cleanup,
    # the script must find out which cloned lun needs to me un-mapped.
    script_log('Inserting serial: %s, cloned_lun_serial: %s, snap_name: %s, group: %s' %\
               (serial, cloned_lun_serial, snap_name, accessgroup))
    sdb.insert_clone_info(serial, cloned_lun_serial, snap_name, accessgroup)
    rdb.insert_snap_info(snap_name, volname)
    #script_log("Index is:" + str(index))
    return cloned_lun_serial        

 
def delete_cloned_lun(cdb, sdb, server, lun_serial):
    '''
    For the given serial, finds the last cloned lun
    and delete it.

    Note that it does not delete the snapshot, the snapshot is left behind.

    cdb : credentials db
    sdb : script db
    lun_serial : the lun serial for which we find the last cloned lun
    '''
    script_log('Starting delete_cloned_lun')
    clone_lun, snap_name, group = sdb.get_clone_info(lun_serial)
    clone_serial = clone_lun.split(':')[-1]
    script_log('Clone serial: %s , snap_name: %s, group: %s' % \
               (str(clone_serial), str(snap_name), str(group)))
	
    if not clone_serial:
        script_log ("No clone lun to be deleted")
        return

    script_log("Unmapping cloned lun on " + snap_name + "\n")

    '''
    # Need to first find the LUN number, then delete the VLUN.

    >>> a=cl.getVLUN("rvbd_test2")
    >>> a
    {u'failedPathPol': 1, u'volumeName': u'rvbd_test2', u'hostname': u'nydemdl380g8vCAC01', u'portPos': {u'node': 1, u'slot
    : 1, u'cardPort': 1}, u'multipathing': 1, u'failedPathInterval': 0, u'active': True, u'type': 3, u'remoteName': u'10000
    051E56601F', u'lun': 4, u'volumeWWN': u'60002AC000000000020077010000299F'}
    >>> a['lun']
    4
    >>> a=cl.deleteVLUN("rvbd_test2",a['lun'],hostname="nydemdl380g8vCAC01")
    '''

    try:
        vluninfo = cl.getVLUN(snap_name)
    except Exception as ex:
        print "Unable to get VLUN information."
        print ex
        sys.exit(1)

# Remove VLUN
    try:
        cl.deleteVLUN(snap_name,vluninfo['lun'],hostname=vluninfo['hostname'])
    except Exception as ex:
        print "Unable to delete VLUN."
        print ex
        sys.exit(1)    

    sdb.delete_clone_info(lun_serial)

    script_log("Cloned lun %s deleted successfully" % clone_serial)
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
                      default="chief-netapp1",
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
    serial = options.serial.upper()


    # Connect to 3Par array.

    # Get credentials for the proxy host
    username, password = cdb.get_enc_info(array)

    #this creates the client object and sets the url to the array.
    cl = client.HP3ParClient("http://"+array+":8008/api/v1")
    # Set the SSH authentication options for the SSH based calls.
    #cl.setSSHOptions(array, username, password)

    try:
        cl.login(username, password)
        script_log("Logged into the array.")
    except exceptions.HTTPUnauthorized as ex:
        script_log("Login failed.")

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
