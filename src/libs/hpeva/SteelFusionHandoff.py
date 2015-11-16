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
# HP EVA Snapshot Handoff Main Script
###############################################################################

import optparse
import sys
import errno
import subprocess
import logging
from src.libs.hpeva import hpeva_api

# Script DB is used to store/load the cloned lun
# information and the credentials
import src.script_db

# Configuration defaults
CRED_DB = r'\var\cred.db'
SCRIPT_DB = r'\var\script.db'
SNAP_DB = r'\var\replay.db'
WORK_DIR =  r'C:\rvbd_handoff_scripts'
HANDOFF_LOG_FILE = r'\log\handoff.log'

# Path for VADP scripts
PERL_EXE = r'"C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\bin\perl.exe" '
VADP_CLEANUP = r'\src\libs\vsphere\vadp_cleanup.pl'
VADP_SETUP = r'\src\libs\vsphere\vadp_setup.pl'

# Configuration for Veeam or Commvault backup software
# Enables incremental backup support
# Set it to '0' to disable
SKIP_VM_REGISTRATION = '1'


def set_logger():
    logging.basicConfig(filename=(WORK_DIR + HANDOFF_LOG_FILE), level=logging.DEBUG,
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

	prefix : full path to work directory
    '''
    global WORK_DIR
    WORK_DIR = prefix
    set_logger()

def create_snap(cdb, sdb, rdb, server, serial, system, snap_name,
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
    system : HP EVA systen name
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
    rdb_snap_name, replay = rdb.get_snap_info(snap_name)
    if rdb_snap_name:
        script_log("Duplicate request")
        print (snap_name)
        return
    wwnid = convert_serial(serial)
    # Run proxy backup on this snapshot if its category matches
    # protected snapshot category
    if category == protect_category:
        # Un-mount the previously mounted cloned lun from proxy host
        if unmount_proxy_backup(cdb, sdb, serial, proxy_host, datacenter, include_hosts, exclude_hosts) :
            # Delete the cloned snapshot
            delete_lun(cdb, sdb, server, serial)
            # Create a cloned snapshot lun form the snapshot
            lun_serial = create_lun(cdb, sdb, rdb, server, serial, snap_name, access_group)
            # Mount the snapshot on the proxy host
            mount_proxy_backup(cdb, sdb, lun_serial, snap_name,
                               access_group, proxy_host, datacenter,
                               include_hosts, exclude_hosts)
            print (snap_name)
            return

    # Else, either the snapshot is not protected
    # or the proxy unmount operation failed. In such a case
    # just create the snapshot and do not proxy mount it
    vdisk_path = get_vdisk_name(server, system, wwnid)
    if len(vdisk_path) == 0:
        print ("Lun %s not found" % (wwnid))
        sys.exit(1)

    vdisk_snapname = "rvbd_" + snap_name[0:15]
    #command = 'ADD SNAPSHOT %s VDISK="%s" ALLOCATION_POLICY=DEMAND WORLD_WIDE_LUN_NAME = %s' %\
    command = 'ADD SNAPSHOT %s VDISK="%s" ALLOCATION_POLICY=DEMAND' %\
                            (vdisk_snapname, vdisk_path)
    user, pwd = cdb.get_enc_info(server)
    out, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status != 0:
        print ("Failed to create snapshot " + str(err))
        sys.exit(1)
    rdb.insert_snap_info(snap_name, vdisk_snapname)
    print (snap_name)
    sys.exit(0)


def remove_snap(cdb, sdb, rdb, server, serial, system, snap_name, proxy_host,
                datacenter, include_hosts, exclude_hosts):
    '''
    Removes a snapshot

    cdb : credentials db
    sdb : script db
    rdb : snap name to replay name db
    server : Netapp hostname/ip address
    serial : lun serial
    system : HP EVA systen name
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

    # Check if we are removing a protected snapshot
    if protected_snap == snap_name:
        # Deleting a protected snap. Un-mount the clone from the proxy host
        if not unmount_proxy_backup(cdb, sdb, serial, proxy_host,
                                    datacenter, include_hosts, exclude_hosts):
            sys.exit(1)
        # Delete the snapshot cloned lun
        delete_lun(cdb, sdb, server, serial)

    # Remove snapshot
    vdisk_snapname = rdb.get_snap_info(snap_name)[1]
    if vdisk_snapname == '':
        script_log("The snapshot does not exist in handoff server's DB. Nothing to remove\n.")
        sys.exit(1)
    else:
        script_log("Snapshot name is " + vdisk_snapname + "\n.")
    command = 'DELETE VDISK "%s" ' % vdisk_snapname
    user, pwd = cdb.get_enc_info(server)
    out, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status != 0:
        print ("Snapshot delete operation failed " + str(err))
        sys.exit(1)
    # Wait for disk to be deleted
    # script_log("Waiting for " + vdisk_snapname + " snapshot to be removed\n.")
    # command = 'WAIT_UNTIL VDISK "%s" DELETED  ' % vdisk_snapname
    # out, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    # if status != 0:
    #     print ("Failed to remove snapshot " + str(err))
    #     sys.exit(1)
    rdb.delete_snap_info(snap_name)
    script_log ("Snapshot removed\n")
    sys.exit(0)

def create_lun(cdb, sdb, rdb, server, serial, snap_name, accessgroup):
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
    script_log('Starting snapshot LUN mapping')
    wwnid = convert_serial(serial)

    # Get VDISK path
    vdisk_path = get_vdisk_name(server, system, wwnid)
    if len(vdisk_path) == 0:
        print ("Lun %s not found" % (wwnid))
        sys.exit(1)

    # Take a snapshot
    vdisk_snapname = "rvbd_" + snap_name[0:15]
    #command = 'ADD SNAPSHOT %s VDISK="%s" ALLOCATION_POLICY=DEMAND WORLD_WIDE_LUN_NAME = %s' % (vdisk_snapname, vdisk_path, wwnid)
    command = 'ADD SNAPSHOT %s VDISK="%s" ALLOCATION_POLICY=DEMAND' % (vdisk_snapname, vdisk_path)
    user, pwd = cdb.get_enc_info(server)
    out, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status != 0:
        print ("Failed to create snapshot " + str(err))
        sys.exit(1)

    # Wait until Snap is created
    command = "WAIT_UNTIL VDISK %s GOOD" % vdisk_snapname
    hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    rdb.insert_snap_info(snap_name, vdisk_snapname)

    # Map LUN to the Host
    command = 'ADD LUN 0 VDISK=%s HOST=%s' %\
                            (vdisk_snapname, accessgroup)
    user, pwd = cdb.get_enc_info(server)
    out, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status != 0:
        print ("Failed to map snapshot LUN" + str(err))
        sys.exit(1)

    # Retrieve LUN wwn information
    command = "ls vdisk %s" % vdisk_snapname
    objects, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status > 0:
        print ("Failed to query snapshot LUN" + str(err))
        sys.exit(1)
    for i in objects:
        #snap_host = i['hostname']
        #snap_lunnumber = i['lunnumber']
        snap_lunid = i['wwlunid']
    lun_serial = snap_lunid.strip().replace('-', '')

    # Store this information in a local database.
    # This is needed because when you are running cleanup,
    # the script must find out which cloned lun needs to me un-mapped.
    script_log('Inserting serial: %s, cloned_lun_serial: %s, snap_name: %s, group: %s' %\
               (serial, lun_serial, snap_name, accessgroup))
    sdb.insert_clone_info(serial, lun_serial, snap_name, accessgroup)
    rdb.insert_snap_info(snap_name, vdisk_snapname)
    return lun_serial


def delete_lun(cdb, sdb, server, serial):
    '''
    For the given serial, finds the last cloned lun
    and delete it.

    Note that it does not delete the snapshot, the snapshot is left behind.

    cdb : credentials db
    sdb : script db
    lun_serial : the lun serial for which we find the last cloned lun
    '''
    script_log('Starting LUN removal...')
    lun_serial, snap_name, accessgroup = sdb.get_clone_info(serial)
    script_log('LUN serial: %s , snap_name: %s, accessgroup: %s' % \
               (str(lun_serial.split(':')[-1]), str(snap_name), str(accessgroup)))

    vdisk_snapname = rdb.get_snap_info(snap_name)[1]
    if not vdisk_snapname:
        script_log ("No LUN to be removed")
        return

    user, pwd = cdb.get_enc_info(server)

    # Retrieve LUN  information
    command = "ls vdisk %s" % vdisk_snapname
    objects, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status > 0:
        print ("Failed to query snapshot LUN" + str(err))
        return
    for i in objects:
        snap_host = i['hostname']
        snap_lunnumber = i['lunnumber']
    lun_name = snap_host + "\\" + snap_lunnumber

    # Unmap LUN on the Host
    command = 'DELETE LUN %s' % lun_name
    out, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status != 0:
        print ("Failed to unmap snapshot LUN " + str(err))
        return

    script_log("LUN unmap operation succeeded")
    sdb.delete_clone_info(serial)
    script_log("LUN %s deleted successfully" % lun_name)
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
           '--extra_logging 1 --skip_vm_registration %s' %\
           (PERL_EXE, WORK_DIR + VADP_SETUP, proxy_host,
            username, password, cloned_lun_serial,
            datacenter, include_hosts, exclude_hosts, SKIP_VM_REGISTRATION))

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
        script_log("Failed to mount snapshot LUN: " + str(status))
    else:
        script_log("Mounted snapshot LUN successfully")


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
           '--extra_logging 1 --skip_vm_registration %s' %\
           (PERL_EXE, WORK_DIR + VADP_CLEANUP,
           proxy_host, username, password, cloned_lun,
           datacenter, include_hosts, exclude_hosts, SKIP_VM_REGISTRATION))

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
                      default="localhost",
                      help="storage array manager ip address or dns name")
    parser.add_option("--system",
                    type="string",
                    default="",
                    help="storage array system name")
    parser.add_option("--username",
                      type="string",
                      default="root",
                      help="log username")
    parser.add_option("--password",
                      type="string",
                      default="",
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

def convert_serial(serial):
    # Convert the serial seen on the Granite Core
    # to the serial that HP EVA understands.
    # Example:
    # Serial on Granite Core: 600112341234ffff0000500000490000
    # Serial EVA understands: 6001-1234-1234-ffff-0000-5000-0049-0000
    s = ""
    for i, c in enumerate(serial):
        s += c
        if (i+1) % 4 == 0: s += '-'
    return s.strip('-')

def check_lun(server, system, serial):
    '''
    Checks for the presence of lun on given HP array

    server : HP EVA hostname/ip address
    system : HP EVA Storage System Name
    serial : lun serial

    Exits the process with code zero if it finds the lun,
    or non-zero code otherwise
    '''
    wwnid = convert_serial(serial)
    lun_path = get_vdisk_name(server, system, wwnid)
    if len(lun_path) == 0:
        print ("Lun %s not found" % (wwnid))
        sys.exit(1)
    print ("OK")
    sys.exit(0)

def get_vdisk_name(server, system, wwnid):
    '''
    Gets the volume for the given lun

    server : HP EVA Management appliance hostname/ip address
    system : HP EVA Storage System Name
    wwnid : lun wwn id

    returns vdisk path
    '''
    command = "find vdisk lunwwid=%s" % wwnid
    user, pwd = cdb.get_enc_info(server)
    objects, err, status = hpeva_api.hp_sssu(server, system, user, pwd).run_sssu(command)
    if status > 0:
        return ""
    vdisk_name = ""
    for i in objects:
        vdisk_name = i['familyname']
    return vdisk_name


if __name__ == '__main__':

    set_logger()
    script_log("Running script with args: %s" % str(sys.argv))
    options, argsleft = get_option_parser().parse_args()

    # Set the working dir prefix
    set_script_path(options.work_dir)

    # Credentials db must be initialized by running the setup.py file in the root
    global cdb
    cdb = src.script_db.CredDB(options.work_dir + CRED_DB)

    # Initialize the script database
    sdb = src.script_db.ScriptDB(options.work_dir + SCRIPT_DB)
    sdb.setup()

    # Create snap to replay mapping database
    rdb = src.script_db.SnapToReplayDB(options.work_dir + SNAP_DB)
    rdb.setup()

    # Setup server/lun info
    conn = options.array
    system = options.system
    if options.operation == 'HELLO':
        check_lun(conn, system, options.serial)
    elif options.operation == 'CREATE_SNAP':
        create_snap(cdb, sdb, rdb, conn, options.serial, options.system, options.snap_name,
                    options.access_group, options.proxy_host,
                    options.datacenter, options.include_hosts,
                    options.exclude_hosts,
		            options.category, options.protect_category)
    elif options.operation == 'REMOVE_SNAP':
        remove_snap(cdb, sdb, rdb, conn, options.serial , options.system,
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
