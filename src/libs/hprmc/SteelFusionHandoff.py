###############################################################################
#
# (C) Copyright 2016 Riverbed Technology, Inc
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

import optparse
import sys
import errno
import shlex
import subprocess
import time

import os

# Script DB is used to store/load the cloned lun
# information and the credentials
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/' + '../../..'))
from src import script_db

import logging

import re
import requests
requests.packages.urllib3.disable_warnings()
import json

# Configuration defaults
CRED_DB = r'\var\cred.db'
SCRIPT_DB = r'\var\script.db'
SNAP_DB = r'\var\replay.db'
WORK_DIR =  r'C:\rvbd_handoff_scripts'
HANDOFF_LOG_FILE = r'\log\handoff.log'

# Remove snapshot / backup behavior
# If you want the backup to be expired with the snapshot with SteelFusion's remove snapshot option, please set
# REMOVE_BACKUP to 1. The default behavior is to leave the backup.
REMOVE_BACKUP = '0'
# If you want to remove the snapshot with SteelFusion's remove snapshot option, please set REMOVE_SNAPSHOT to 1.
# The default behavior is to REMOVE the backup.
REMOVE_SNAPSHOT = '1'



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

    prefix : full path of directory in which the scripts reside
    '''
    global WORK_DIR
    WORK_DIR = prefix

# Defining a function to do posts against HP RMC
def hprmchost_call (hprmchost, info, headers, function):
    url_prefix = "https://" + hprmchost + '/rest/rm-central/v1/'
    url = (url_prefix + function + parameters)
    return requests.post(url,verify=False, data=json.dumps(info), headers=headers)

# Defining a function to do gets against HP RMC
def hprmchost_get (hprmchost, headers, function):
    url_prefix = "https://" + hprmchost + '/rest/rm-central/v1/'
    url = (url_prefix + function + parameters)
    return requests.get(url,verify=False, headers=headers)

# Defining a function to do gets against HP RMC
def hprmchost_gettask (hprmchost, headers, function):
    url_prefix = "https://" + hprmchost
    url = (url_prefix + function + parameters)
    return requests.get(url,verify=False, headers=headers)

# Defining a function to do gets against HP RMC
def hprmchost_del (hprmchost, headers, function, parameters):
    url_prefix = "https://" + hprmchost + '/rest/rm-central/v1/'
    url = (url_prefix + function + "/" + parameters)
    return requests.delete(url,verify=False, headers=headers)

def check_lun(conn, serial):
    '''
    Checks for the presence of lun

    server : hostname/ip address
    serial : lun serial

    Just checks to see if a recovery set exists for this LUN serial
    Will fail if does not exist. We may change this to creating a recovery set.
    Example hprmchost_call
    #b = requests.get('https://10.21.20.235/rest/rm-central/v1/recovery-sets',verify=False,headers=headers)
    Example output
    '{"recoverySets": [{"status": "available", "snapCount": 0, "backupCount": 0, "de
    scription": "my first rdm backup", "wwnlist": ["60002AC0000000000200330F0000299F
    "], "resourceUri": "/rest/rm-central/v1/recovery-sets/ddc3476c-acf7-4261-9115-d0
    dd64df2695", "associatedResourceUri": "/rest/rm-central/v1/storage-pools/1c6b568
    9-251b-45b4-a8d4-6f8979ebb36e", "removeOldestSnap": false, "volumelist": ["rdm4r
    vbdcore"], "backupPolicyId": "", "removeOldestBackup": false, "poolId": "1c6b568
    9-251b-45b4-a8d4-6f8979ebb36e", "id": "ddc3476c-acf7-4261-9115-d0dd64df2695", "c
    reatedAt": "2015-04-29T06:10:43.415731Z", "name": "jdoe1234"}]}'
    '''
    getrecoverysets = hprmchost_get (array, headers, "recovery-sets")
    getrecoverysets = getrecoverysets.json()
    # Using counter to show number of RecoverySets found.
    counter = 0
    for recoveryset in getrecoverysets['recoverySets']:
        wwn = str(recoveryset.get('wwnlist')).strip("'[]")
        recoverysetid = str(recoveryset.get('id'))
        if serial in wwn :
            script_log('Found recoverysetid for LUN serial ' + wwn + '\n')
        # Using counter to show number of RecoverySets found.
            counter = counter+1
    if counter > 1:
        print (str(counter) + " RecoverySets found. A snapshot or backup will be created for all RecoverySets.\n")
        sys.exit(0)
    # Will try to create a Recovery Set if there isn't one, but only if there is only 1 Storage Pool.
    elif counter == 0:
        getstoragepools = hprmchost_get (array, headers, "storage-pools")
        getstoragepools = getstoragepools.json()
        storagepoolcounter = 0
        for storagepool in getstoragepools['storagePools']:
            storagepoolid = str(storagepool.get('id')).strip("'[]")
        # Using counter to show number of RecoverySets found.
            storagepoolcounter = storagepoolcounter+1
        if storagepoolcounter > 1:
            print ("More than 1 Storage Pool found. Please add a Recovery Set for this LUN manually.\n")
            sys.exit(1)
        #create a recovery set if a there is only 1 storage pool.
        #recoveset = {"recoverySet": {"name": "Test-RS", "description": "RS Test","poolId": "1c6b5689-251b-45b4-a8d4-6f8979ebb36e", "wwnlist": ["60002AC0000000000200330F0000299F"]} }
        #b = requests.post('https://10.21.20.235/rest/rm-central/v1/recovery-sets',verify=False,headers=headers, data=json.dumps(recoveset))
        else:
            recoverysetattrib = {"recoverySet": {"name": "rvbd_" + serial, "description": "Riverbed Created Recovery Set","poolId": storagepoolid, "wwnlist": [serial]} }
            createrecoveryset = hprmchost_call (array, recoverysetattrib, headers, "recovery-sets")
        #script_log ("No RecoverySet available.\n")
            script_log ("Recovery Set Created for "+serial+".\n")
        script_log ("OK\n")
    sys.exit(0)


def create_snap(cdb, sdb, rdb, server, serial, snap_name,
                backuppolicy, category, protect_category):
    '''
    Creates a snapshot

    cdb : credentials db
    sdb : script db
    rdb : snap name to replay name db
    rdb : snap name to replay name db
    server : hostname/ip address
    serial : lun serial
    snap_name : the snapshot name
    backuppolicy: backup policy in HP RMC if doing a backup.
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

    # Creating a snapshot and no backup
    # snapnow = { "snapshotSet": { "name": "asdfasdfasdf", "description": "rmc-restore-desc", "recoverySetId": "ddc3476c-acf7-4261-9115-d0dd64df2695" } }
    # b = requests.post('https://10.21.20.235/rest/rm-central/v1/snapshot-sets',verify=False,headers=headers, data = json.dumps(snapnow))


    #  Need to first get the recoveryset. Then, will loop through them all and create a snapshot for each of them.
    #Just checks to see if a recovery set exists for this LUN serial
    #Will fail if does not exist. We may change this to creating a recovery set.
    #Example hprmchost_call
    ##b = requests.get('https://10.21.20.235/rest/rm-central/v1/recovery-sets',verify=False,headers=headers)
    #Example output
    #'{"recoverySets": [{"status": "available", "snapCount": 0, "backupCount": 0, "de
    #scription": "my first rdm backup", "wwnlist": ["60002AC0000000000200330F0000299F
    #"], "resourceUri": "/rest/rm-central/v1/recovery-sets/ddc3476c-acf7-4261-9115-d0
    #dd64df2695", "associatedResourceUri": "/rest/rm-central/v1/storage-pools/1c6b568
    #9-251b-45b4-a8d4-6f8979ebb36e", "removeOldestSnap": false, "volumelist": ["rdm4r
    #vbdcore"], "backupPolicyId": "", "removeOldestBackup": false, "poolId": "1c6b568
    #9-251b-45b4-a8d4-6f8979ebb36e", "id": "ddc3476c-acf7-4261-9115-d0dd64df2695", "c
    #reatedAt": "2015-04-29T06:10:43.415731Z", "name": "jdoe1234"}]}'

    #Sample output for following a snapshot task to get id.
    # >>> b.text
    #'{"taskUri": "/rest/rm-central/v1/tasks/25116584-07b7-4590-8574-c8392f3d8753"}'
    #>>> p = requests.get('https://10.21.20.235/rest/rm-central/v1/tasks/25116584-07b
    #7-4590-8574-c8392f3d8753',verify=False,headers=headers)
    #>>> p
    #<Response [200]>
    #>>> p.text
    #'{"task": {"totalSteps": 5, "taskErrors": null, "name": "Create_Recoveryset_Snap
    #shot", "taskOutput": [{"outputOfTask": "Initiating creation of Recovery Set snap
    #shot."}, {"outputOfTask": "Preparing Recovery Set snapshot data from the volumes
    # of the Recovery Set."}, {"outputOfTask": "Delegating the request to driver to f
    #etch volume details."}, {"outputOfTask": "SUCCESSFULLY_UPDATED_RECOVERYSET_SNAPS
    #HOT_DETAILS"}], "completedAt": "2015-05-17T06:01:49.055921Z", "taskState": "Comp
    #leted", "completedSteps": 5, "taskStatus": "CREATED_RECOVERYSET_SNAPSHOT_SUCCESS
    #FULLY", "completedPercentage": 100, "owner": "c9122ce31812455f8e5d60da74138abb",
    # "associatedData": {"storageSystemName": "STG3PAR7200", "recoverysetUri": "/rest
    #/rm-central/v1/recovery-sets/40a7ebca-4f43-4c8e-b714-a16ea9668035", "recoveryset
    #Name": "Riverbed LUN", "GBMoved": 0}, "associatedResource": {"resourceName": "as
    #dfasdfasdf", "associationType": "IS_A", "resourceCategory": "Recovery Set Snapsh
    #ot", "resourceUri": "/rest/rm-central/v1/snapshot-sets/8f700be8-c9ec-4fcc-8de1-3
    #1aa171dfb35"}, "taskProgress": [{"taskProgressUpdate": "SUCCESSFULLY_UPDATED_REC
    #OVERYSET_SNAPSHOT_DETAILS"}, {"taskProgressUpdate": "RECOVERYSET_SNAPSHOT_DATA_P
    #REPARED"}, {"taskProgressUpdate": "Successfully fetched the Recovery Set details
    #."}, {"taskProgressUpdate": "Recovery Set snapshot parameters are validated."}],
    # "taskType": "User", "taskUri": "/rest/rm-central/v1/tasks/25116584-07b7-4590-85
    #74-c8392f3d8753", "parentTaskId": null, "id": "25116584-07b7-4590-8574-c8392f3d8
    #753", "createdAt": "2015-05-17T06:01:46.244616Z"}}'

    # SnapshotSet is = ['task']['associatedResource']['resourceUri']

    getrecoverysets = hprmchost_get (array, headers, "recovery-sets")
    getrecoverysets = getrecoverysets.json()
    # Using counter to show successes.
    counter = 0
    for recoveryset in getrecoverysets['recoverySets']:
        wwn = str(recoveryset.get('wwnlist')).strip("'[]")
        recoverysetid = str(recoveryset.get('id'))

        if serial in wwn :
            counter = counter+1
            script_log('Found recoverysetid for LUN serial ' + wwn + '. Continuing ...\n')

    # Will try to create a Recovery Set if there isn't one, but only if there is only 1 Storage Pool.
    if counter == 0:
        getstoragepools = hprmchost_get (array, headers, "storage-pools")
        getstoragepools = getstoragepools.json()
        storagepoolcounter = 0
        for storagepool in getstoragepools['storagePools']:
            storagepoolid = str(storagepool.get('id')).strip("'[]")
        # Using counter to show number of RecoverySets found.
            storagepoolcounter = storagepoolcounter+1
        if storagepoolcounter > 1:
            print ("More than 1 Storage Pool found. Please create a Recovery Set for this LUN manually.\n")
            sys.exit(1)
        #create a recovery set if a there is only 1 storage pool.
        #recoveset = {"recoverySet": {"name": "Test-RS", "description": "RS Test","poolId": "1c6b5689-251b-45b4-a8d4-6f8979ebb36e", "wwnlist": ["60002AC0000000000200330F0000299F"]} }
        #b = requests.post('https://10.21.20.235/rest/rm-central/v1/recovery-sets',verify=False,headers=headers, data=json.dumps(recoveset))
        else:
            recoverysetattrib = {"recoverySet": {"name": "rvbd_" + serial, "description": "Riverbed Created Recovery Set","poolId": storagepoolid, "wwnlist": [serial]} }
            createrecoveryset = hprmchost_call (array, recoverysetattrib, headers, "recovery-sets")
        #script_log ("No RecoverySet available.\n")
            script_log ("Recovery Set Created for "+serial+". \n")
            time.sleep(10)

    counter = 0
    for recoveryset in getrecoverysets['recoverySets']:
        wwn = str(recoveryset.get('wwnlist')).strip("'[]")
        recoverysetid = str(recoveryset.get('id'))

        if serial in wwn :
            counter = counter+1
            if category == protect_category:
                script_log ("Checking backup file.")
                try:
                    backuptaskfile = open(WORK_DIR + '\\var\\' + recoverysetid+'_backup.txt','r')
                    task = backuptaskfile.read()
                    backuptaskfile.close()
                    previousbackup = "available"
                except:
                    script_log ("No previous backup recorded. Will do a full backup.")
                    previousbackup = ''
                if previousbackup != '':
                    lastbackuptaskstatus = ''
                    script_log("The previous backup task status is: " + task)
                    #task = ast.literal_eval(task)
                    #task = task['taskUri']
                    try:
                        backuptask = hprmchost_gettask (array, headers, task)
                        backuptask = backuptask.json()
                        lastbackuptaskstatus = backuptask['taskTree']['taskState']
                        script_log ("Last backup status " + lastbackuptaskstatus + "\n")
                    except:
                        script_log("Something was wrong with the previous backup. Performing full backup.")
                    if lastbackuptaskstatus == "Running":
                        script_log ("Backup Task is not yet complete. Will NOT take snapshot or backup.")
                        sys.exit(1)

            script_log('Found recoverysetid for LUN serial ' + wwn + '\n')
            snapnow = { "snapshotSet": { "name": snap_name, "description": "Riverbed Snapshot", "recoverySetId": recoverysetid } }
            #Example of the call to create a snapshot without the function
            #snapshot = requests.post('https://10.21.20.235/rest/rm-central/v1/snapshot-sets',verify=False,headers=headers, data = json.dumps(snapnow))
            snapshot = hprmchost_call (array, snapnow, headers, "snapshot-sets")
            script_log(snapshot.text)
            snapshot = snapshot.json()
            #print ("Printing snap name", snap_name, "\n\n\n\n\n\n")

            # Using counter to show number of RecoverySets found.
            # If we're doing a backup, get the snapshot set from the task id and with it, create a backup.
            # We'll also need the backup policy id. Customer will need to provide this with --backuppolicy.
            #Sample output of get for backupsets.
            #b = requests.get('https://10.21.20.235/rest/rm-central/v1/backup-sets',verify=False,headers=headers)

            #'{"backupSets": [{"status": "error", "resourceUri": "/rest/rm-central/v1/backup-sets/ac3f5af9-87ff-4cc6-b
            #523-f5528dbd516c", "verified": false, "description": "", "snapshotSetId": null,
            ##"associatedResourceUri": null, "backupPolicyId": "90a36816-e76e-433f-a60b-3a5620
            #889a65", "incremental": false, "recoverySetId": "ddc3476c-acf7-4261-9115-d0dd64d
            #f2695", "id": "ac3f5af9-87ff-4cc6-b523-f5528dbd516c", "createdAt": "2015-05-15T0
            #6:29:56.775155Z", "name": "jill1234"}]}'

            #backupdetails = {"backupSet": {"name": "ORACLE-bp-61","description": "rmc-proc","snapshotSetId": "913ce463-de0b-4006-89d1-e3cb0789304c",
            #"backupPolicyId":"4f1d641a-b195-4b67-aa12-7f812c2e9ac7", #Optional “Incremental”:”true”,}}
            #b = requests.post('https://10.21.20.235/rest/rm-central/v1/backup-sets',verify=False,headers=headers, data = json.dumps(backupdetails))
            #Find snapshot ID from the task uri.
            #>>> p = requests.get('https://10.21.20.235/rest/rm-central/v1/tasks/25116584-07b
            #7-4590-8574-c8392f3d8753',verify=False,headers=headers)

            #opening file to get previous snapshot from recovery set.
            try:
                snapshotinfofile = open(WORK_DIR + '\\var\\' + recoverysetid+'_snapshot.txt','r')
                previoussnapshot = snapshotinfofile.read()
                script_log("snapshot file contents " + previoussnapshot)
                snapshotinfofile.close()
            except:
                script_log ("No previous snapshot file found.")
                previoussnapshot = ""
            #sleeping to give the snapshot time to finish.
            time.sleep(2)
            task = snapshot['taskUri']
            script_log ("Attaching to snapshot task Uri "+task+" \n")
            snapshottask = hprmchost_gettask (array, headers, task)
            snapshottask = snapshottask.json()
            '''  Task status should look like this:
             {'task': {'taskErrors': None, 'totalSteps': 5, 'taskStatus': 'Recovery set snapshot created successfully.',
             'taskOutput': [{'outputOfTask': 'Initiating creation of Recovery Set snapshot.'}, {'outputOfTask': 'Preparing
             Recovery Set snapshot data from the volumes of the Recovery Set.'}, {'outputOfTask': 'Delegating the request to
             driver to fetch volume details.'}, {'outputOfTask': 'Recovery set snapshot details updated successfully.'}],
             'associatedResource': {'resourceName': 'b6206bb7-9090-499c-a446-a24828bd6da2', 'resourceCategory': 'Recovery Set
             Snapshot', 'associationType': 'IS_A',
             'resourceUri': '/rest/rm-central/v1/snapshot-sets/a57fd465-3523-4855-bb03-554c78d75485'}, 'taskState':
             'Completed', 'completedSteps': 5, 'id': 'd597ca29-566a-482e-b874-6cb624a25fae', 'name': 'Create_Recoveryset_Snapshot',
             'taskType': 'User', 'taskProgress': [{'taskProgressUpdate': 'Recovery set snapshot details updated successfully.'},
             {'taskProgressUpdate': 'Prepared Recovery Set snapshot data.'}, {'taskProgressUpdate': 'Successfully fetched the
             Recovery Set details.'}, {'taskProgressUpdate': 'Recovery Set snapshot parameters are validated.'}], 'createdAt':
             '2015-08-18T23:40:38.791258Z', 'completedPercentage': 100, 'taskUri':
             '/rest/rm-central/v1/tasks/d597ca29-566a-482e-b874-6cb624a25fae', 'completedAt': '2015-08-18T23:40:40.578039Z',
             'associatedData': {'recoverysetName': 'rvbd_60002AC000000000000004A8000062AD', 'GBMoved': 0, 'storageSystemName':
             '3PAR', 'recoverysetUri': '/rest/rm-central/v1/recovery-sets/dab518a8-7c38-406d-b3a5-6faed4bc9945'}, 'parentTaskId':
             None, 'owner': '66373cb2a66b4428b25e1ae285f9a473'}}
            '''
            script_log ("snapshot task state :" + snapshottask['task']['taskState'])
            if snapshottask['task']['taskState']!='Completed':
                script_log ("Snapshot not yet available. Waiting 10 seconds.")
                time.sleep(10)
                snapshottask = hprmchost_gettask (array, headers, task)
                snapshottask = snapshottask.json()
                script_log ("snapshot task state :" + snapshottask['task']['taskState'])
            if snapshottask['task']['taskState']!='Completed':
                script_log ("Snapshot not yet available. Waiting 15 more seconds.")
                time.sleep(15)
                snapshottask = hprmchost_gettask (array, headers, task)
                snapshottask = snapshottask.json()
            if snapshottask['task']['taskState']!='Completed':
                script_log ("Snapshot not yet available. Waiting 30 more seconds.")
                time.sleep(30)
                snapshottask = hprmchost_gettask (array, headers, task)
                snapshottask = snapshottask.json()
            if snapshottask['task']['taskState']!='Completed':
                script_log ("Snapshot not yet available. Waiting 60 more seconds.")
                time.sleep(60)
                snapshottask = hprmchost_gettask (array, headers, task)
                snapshottask = snapshottask.json()
            if snapshottask['task']['taskState']!='Completed':
                print ("It's taking a while to create the snapshots. Please adjust the sleep times or check for trouble on the array.\n")
                sys.exit(1)
            script_log ("Attaching to snapshot task "+str(snapshottask)+" \n")
            snapshoturl = snapshottask['task']['associatedResource']['resourceUri']
            script_log ("snapshoturl is "+snapshoturl+" \n")
            snapshotset = re.search('snapshot-sets/(.*)',snapshoturl)
            snapshotset = snapshotset.group(1)
            script_log ("snapshotset is "+snapshotset+" \n")

            #writing snapshotset to file so that we can read it back in next time for incremental backups.
            snapshotinfofile = open(WORK_DIR + '\\var\\' + recoverysetid+'_snapshot.txt','w')
            snapshotinfofile.write(snapshotset)
            snapshotinfofile.close()


            # If the backup is enabled, take a backup.
                # Run proxy backup on this snapshot if its category matches
                # protected snapshot category
            if category == protect_category:
                backuppolicyfound = False
                if backuppolicy == "":
                    script_log("Please provide RMC Backup Policy Id with --backuppolicy")
                    sys.exit(1)
                else:
                    script_log("Setting up Backup using policy: "+ backuppolicy + "\n")
                    getbackuppolicies = hprmchost_get(array, headers, "backup-policies")
                    getbackuppolicies = getbackuppolicies.json()
                    for backupPolicy in getbackuppolicies['backupPolicies']:
                        backuppolicyname = str(backupPolicy.get('name')).strip("'[]")
                        backupPolicyId = str(backupPolicy.get('id')).strip("'[]")
                        if backuppolicyname == backuppolicy :
                            script_log ("Attaching Backup to " + backuppolicy + ".\n")
                            if previoussnapshot == "":
                                backupattrib = {"backupSet": {"name": snap_name, "description": "Riverbed backup", "snapshotSetId": snapshotset, "backupPolicyId":backupPolicyId }}
                                script_log ("Creating Full backup.")
                            else:
                                backupattrib = {"backupSet": {"name": snap_name, "description": "Riverbed backup", "snapshotSetId": previoussnapshot, "backupPolicyId":backupPolicyId, "incremental":True }}
                                script_log ("Creating Incremental backup.")
                            script_log ("backupattrib is "+str(backupattrib)+" \n")
                            createbackup = hprmchost_call (array, backupattrib, headers, "backup-sets")
                            script_log ("createbackup response is "+str(createbackup.text)+" \n")
                            script_log ('Create Backup Status code: '+str(createbackup.status_code))
                            if createbackup.status_code != int(202):
                                backupattrib = {"backupSet": {"name": snap_name, "description": "Riverbed backup", "snapshotSetId": snapshotset, "backupPolicyId":backupPolicyId }}
                                script_log ("Incremental Backup Failed. Creating Full backup.")
                                createbackup = hprmchost_call (array, backupattrib, headers, "backup-sets")
                                createbackup2 = createbackup.json()
                                script_log ("createbackup is "+str(createbackup2)+" \n")
                                backuptaskfile = open(WORK_DIR + '\\var\\' + recoverysetid+'_backup.txt','w')
                                backuptaskfile.write(createbackup2['taskUri'])
                                backuptaskfile.close()
                                if createbackup.status_code != int(202):
                                    script_log ('Backup failed. Please check HP RMC log for details.')
                                    sys.exit(1)
                            backuppolicyfound = True
                            break
                    if not backuppolicyfound:
                        script_log("Backup Policy not found on the RMC. Please provide the correct RMC Backup Policy Id with --backuppolicy")
                        sys.exit(1)

    print (snap_name)
    if counter > 1:
        script_log (str(counter) + " RecoverySets found. A snapshot or backup was created for all RecoverySets.\n")
    if counter == 0:
        script_log ("Recovery Set not found. If the problem persists, please create a Recovery Set for this LUN manually.\n")
        sys.exit(1)
    else:
        # Script finished successfully - If removing snapshots, we will keep a database of them.
        rdb.insert_snap_info(snap_name, recoverysetid)
        sys.exit(0)


def remove_snap(cdb, sdb, rdb, server, serial, snap_name):
    '''
    Removes a snapshot and/or backup.

    cdb : credentials db
    sdb : script db
    rdb : snap name to replay name db
    server : HP RMC hostname/ip address
    serial : lun serial
    snap_name : the snapshot and/or backup name

    If unsuccessful, exits the process with non-zero error code,
    else exits with zero error code.

Snapshot sets look like this:
>>> b = requests.get('https://10.33.195.65//rest/rm-central/v1/snapshot-sets',verify=False,headers=headers)
>>> b.text
'{"snapshotSets": [{"status": "available", "resourceUri": "/rest/rm-central/v1/s
napshot-sets/1e5adc4f-fa92-42ef-9d75-ae11c698487a", "description": "", "associat
edResourceUri": "/rest/rm-central/v1/recovery-sets/ddc3476c-acf7-4261-9115-d0dd6
4df2695", "snapCreationTime": "2015-04-29T02:32:19.000000", "recoverySetId": "dd
c3476c-acf7-4261-9115-d0dd64df2695", "id": "1e5adc4f-fa92-42ef-9d75-ae11c698487a
", "createdAt": "2015-04-29T06:13:58.124990Z", "name": "123456df"}]}'

    '''

# Removing Snapshots if applicable
    if REMOVE_SNAPSHOT == '1' :
        script_log('Removing SnapshotSets' + snap_name + '\n')
        #Getting list of all snapshot sets
        getsnapshotsets = hprmchost_get (array, headers, "snapshot-sets")
        getsnapshotsets = getsnapshotsets.json()
        # Using counter to show number of SnapshotSets found.
        counter = 0
        for snapshotset in getsnapshotsets['snapshotSets']:
            rvbdsnapshotsetname = str(snapshotset.get('name')).strip("'[]")
            hprmcsnapshotsetid = str(snapshotset.get('id')).strip("'[]")
            #script_log (rvbdsnapshotsetname)
            if rvbdsnapshotsetname == snap_name :
                script_log('Found Riverbed snapshotset to remove: ' + snap_name + '\n')
                script_log('HP RMC snapshotSet to remove: ' + hprmcsnapshotsetid +" \n")
                # delete example without using the function
                #requests.delete('https://10.21.20.235/rest/rm-central/v1/snapshot-sets/64b2343d-8278-4f75-a17e-d45ab828c80a',verify=False,headers=headers)
                snapshot = hprmchost_del (array, headers, "snapshot-sets", hprmcsnapshotsetid)
                # Using counter to show number of SnapshotSets found.
                counter = counter+1
        if counter > 1:
            script_log (str(counter) + " SnapshotSets removed.\n")
        elif counter == 0:
            script_log ("No SnapshotSet available.\n")
        else:
            script_log ("SnapshotSet removed\n")

# Removing Backups if applicable
    if REMOVE_BACKUP == '1' :
        script_log('Removing BackupSets' + snap_name + '\n')
        # Using counter to show number of SnapshotSets found.
        counter = 0
        getbackupsets = hprmchost_get (array, headers, "backup-sets")
        getbackupsets = getbackupsets.json()
        for backupset in getbackupsets['backupSets']:
            rvbdbackupsetname = str(backupset.get('name')).strip("'[]")
            hprmcbackupsetid = str(backupset.get('id')).strip("'[]")
            #script_log (rvbdsnapshotsetname)
            if rvbdbackupsetname == snap_name :
                script_log('Found Riverbed backupSet to remove: ' + snap_name + '\n')
                script_log('HP RMC backupSet to remove: ' + hprmcbackupsetid +" \n")
                # delete example without using the function
                #requests.delete('https://10.21.20.235/rest/rm-central/v1/snapshot-sets/64b2343d-8278-4f75-a17e-d45ab828c80a',verify=False,headers=headers)
                snapshot = hprmchost_del (array, headers, "backup-sets", hprmcbackupsetid)
                # Using counter to show number of SnapshotSets found.
                counter = counter+1
        if counter > 1:
            script_log (str(counter) + " BackupSets removed.\n")
        elif counter == 0:
            script_log ("No BackupSets available.\n")
        else:
            script_log ("BackupSets removed\n")

    rdb.delete_snap_info(snap_name)
    sys.exit(0)

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
                      default="",
                      help="RMC ip address or dns name")
    parser.add_option("--backuppolicy",
                      type="string",
                      default="",
                      help="RMC backup PolicyId")
    parser.add_option("--work-dir",
                      type="string",
                      default=WORK_DIR,
                      help="Directory path to the handoff host scripts")
    parser.add_option("--protect-category",
                      type="string",
                      default="daily",
                      help="whether or not we perform an RMC backup")

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

    # Credentials db must be initialized by running the setup.py file in the root
    global cdb
    cdb = script_db.CredDB(options.work_dir + CRED_DB)

    # Initialize the script database
    sdb = script_db.ScriptDB(options.work_dir + SCRIPT_DB)
    sdb.setup()

    # Create snap to replay mapping database
    rdb = script_db.SnapToReplayDB(options.work_dir + SNAP_DB)
    rdb.setup()

    # Setup server/lun info
    conn = options.array
    array = options.array
    serial = options.serial.upper()

    # Connect to HP RMC and get token.
    #Connect to db to get creds.
    username, password = cdb.get_enc_info(array)

    creds = {'auth': {'passwordCredentials': {'username': username, 'password': password}}}
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    function = 'login-sessions'
    parameters = ''
    auth = hprmchost_call (array, creds, headers, "login-sessions")
    script_log (auth.text)
    token = auth.json()
    #print (token)
    token = token["loginSession"]["access"]["token"]["id"]
    script_log  ("Authenticated with RMC with token " + token + "\n")
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'X-Auth-Token': token}

    if options.operation == 'HELLO':
        check_lun(conn, serial)
    elif options.operation == 'CREATE_SNAP':
        create_snap(cdb, sdb, rdb, conn, serial, options.snap_name,
                    options.backuppolicy, options.category, options.protect_category)
    elif options.operation == 'REMOVE_SNAP':
        remove_snap(cdb, sdb, rdb, conn, serial, options.snap_name)
    else:
        print ('Invalid operation: %s' % str(options.operation))
        cdb.close()
        sdb.close()
        rdb.close()
        sys.exit(errno.EINVAL)

    sdb.close()
    cdb.close()
    rdb.close()