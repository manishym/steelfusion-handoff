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


###############################################################################
# Sample Snapshot Handoff Script
# All operations are a no-op.
# Since we do not really create a clone, the mount operation
# and the unmount operation are going to fail on ESX.
###############################################################################
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

# Paths for VADP scripts
PERL_EXE = r'"C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\bin\perl.exe" '
WORK_DIR =  r'C:\rvbd_handoff_scripts\src\libs\compellent_v1'
VADP_CLEANUP = WORK_DIR + r'\vadp_cleanup.pl'
VADP_SETUP = WORK_DIR + r'\vadp_setup.pl'
COMPELLENT_SCRIPT = WORK_DIR + r'\compellent.ps1'
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

def execute_script(cmd):
    ps_command_pref = '"cmd /c echo . | '
    ps_command_pref += "powershell Set-ExecutionPolicy bypass -Force -Scope CurrentUser;"
    command = ps_command_pref + COMPELLENT_SCRIPT + " " + cmd + '"'
    script_log("Command is :[" + command + "]")
    proc = subprocess.Popen(command,
                            stdout = subprocess.PIPE,
                            stderr = subprocess.PIPE, shell = True)
    out, err = proc.communicate()
    status = proc.wait();
    script_log("OUT: " + str(out))
    script_log("ERR: " + str(err))
    script_log("STATUS: " + str(status))
    return (out, err, status)

def check_lun(server, serial):
    '''
    Checks for the presence of lun

    server : hostname/ip address 
    serial : lun serial

    Exits the process with code zero if it finds the lun,
    or non-zero code otherwise
    '''
    out, err, status = execute_script("-operation HELLO -serial %s -array %s" % (serial, server))
    if (status != 0):
        print ("Error occurred: " + str(err))
    else:
        print ("OK")
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
    rdb_snap_name, replay = rdb.get_snap_info(snap_name)
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
            delete_cloned_lun(cdb, sdb, server, serial)
            # Create a cloned snapshot lun form the snapshot
            cloned_lun_serial = create_snap_clone(cdb, sdb, rdb, server, serial, snap_name, access_group)
            # Mount the snapshot on the proxy host
            mount_proxy_backup(cdb, sdb, cloned_lun_serial, snap_name,
                               access_group, proxy_host, datacenter,
                               include_hosts, exclude_hosts) 
            print (snap_name)
            return

    # Else, either the snapshot is not protected
    # or the proxy unmount operation failed. In such a case
    # just create the snapshot and do not proxy mount it
    out, err, status = execute_script("-operation SNAP_CREATE -serial %s -array %s " % (serial, server))
    if status != 0:
        print ("Failed to create snapshot " + str(err))
        sys.exit(1)
	
  
    decoded = out.decode('utf-8')
    out_split = decoded.strip().split('\n')[0].split(":")[-1]
    script_log("The index is " + str(out_split))
    # Script finished successfully
    rdb.insert_snap_info(snap_name, out_split)
    print (snap_name)
    sys.exit(0)


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

    replay = ''
    # Check if we are removing a protected snapshot
    if protected_snap == snap_name:
        replay = clone_serial.split(":")[0]
        # Deleting a protected snap. Un-mount the clone from the proxy host
        if not unmount_proxy_backup(cdb, sdb, serial, proxy_host,
                                    datacenter, include_hosts, exclude_hosts):
            sys.exit(1)
        # Delete the snapshot cloned lun
        delete_cloned_lun(cdb, sdb, server, serial)

    # Expire the replay    
    
    if not replay :
        s1, replay = rdb.get_snap_info(snap_name)
        script_log("The replay index is  " + replay)

    if replay:
        out, err, status = execute_script("-operation SNAP_REMOVE -serial %s -array %s -replay %s" %\
                                          (serial, server, replay))
        if status != 0:
            print ("Failed to remove snapshot " + str(err))
            sys.exit(1)
	
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
    out, err, status = execute_script("-operation CREATE_SNAP_AND_MOUNT -serial %s -array %s -accessgroup %s " % (serial, server, accessgroup))
    if status != 0:
        msg = "Failed to create snapshot " + str(err)
        script_log(msg)
        print (msg)
        sys.exit(1)

    decoded = out.decode('utf-8')
    out_split = decoded.strip().split('\n')
    index = out_split[0].split(':')[-1].strip()
    cloned_lun = out_split[-1].split(':')[-1].strip()
    script_log("Cloned serial is " + cloned_lun)
    cloned_lun_serial = index + ":" + cloned_lun

    if cloned_lun_serial == ':':
        print ("Failed to create snapshot lun : " + str(decoded))
        sys.exit(1)
	
    # Store this information in a local database. 
    # This is needed because when you are running cleanup,
    # the script must find out which cloned lun needs to me un-mapped.
    script_log('Inserting serial: %s, cloned_lun_serial: %s, snap_name: %s, group: %s' %\
               (serial, cloned_lun_serial, snap_name, accessgroup))
    sdb.insert_clone_info(serial, cloned_lun_serial, snap_name, accessgroup)
    rdb.insert_snap_info(snap_name, index)
    script_log("Index is:" + str(index))
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

    script_log("Unmapping cloned lun with serial " + str(clone_serial))
    out, err, status = execute_script("-operation UNMOUNT -serial %s -array %s -mount %s" %\
                                      (serial, server, clone_serial))
    if status != 0:
        print ("Failed to delete cloned lun " + str(err))
        return
       
    script_log("Unmapping successful : " + str(out))   
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


def main():
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
    serial = options.serial

    if (serial[8:9] =='-'):
        # For iscsi, serial seen on GC is same as required by snap commands
        compellent_serial = serial
    else:
        # Convert the serial seen on the Granite Core
        # to the serial that Compellent understands.
        # Example:
        # Serial on Granite Core: 6000d310005267000000000000000017
        # Serial Compellent understands: 00005267-00000017
        # The first 8 digits are vendor id so we can ignore them.
        compellent_serial = '00' + serial[8:14] + '-' + serial[-8:]
    
    if options.operation == 'HELLO':
        check_lun(conn, compellent_serial)
    elif options.operation == 'CREATE_SNAP':   
        create_snap(cdb, sdb, rdb, conn, compellent_serial, options.snap_name, 
                    options.access_group, options.proxy_host,
                    options.datacenter, options.include_hosts,
                    options.exclude_hosts,
		    options.category, options.protect_category)
    elif options.operation == 'REMOVE_SNAP':
        remove_snap(cdb, sdb, rdb, conn, compellent_serial ,
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

if __name__ == '__main__':
    main()