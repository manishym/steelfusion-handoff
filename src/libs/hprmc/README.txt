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

--------------------------------------------------
# Snapshot Handoff Sample Scripts
--------------------------------------------------

This document describes how to setup handoff host with sample scripts.
This document and all the scripts mentioned here are a property of
Riverbed Technology and must not be distributed without proper licenses.
(C) Copyright 2015 Riverbed Technology, Inc
All rights reserved.

---------------------------------------------------
# Preparing the Handoff Host
---------------------------------------------------
The scripts have been tested on Windows 2K8 R2. Python 3.3-3.6 have been tested as well.
1. Install Python3.4 for "all" users.
2. Install the requests library for python. Please reboot the Windows box after making these changes.
3. We tested by placing the directory under "C:\rvbd_handoff_scripts". This is referred to as "WORK_DIR" in the remained of this README.

---------------------------------------------------
# Managing Security of data
---------------------------------------------------
The handoff host must be configured with an Administrator account
that will be used for running the handoff scripts.
Note that the default script provided here accesses and reads the
credential database setup using the cred_mgmt.py script.
Since it stores credentials for storage array, we recommend:
1. Run the scripts using Administrator account
2. Set 'Administrator' only permissions on the WORK_DIR.
   This will ensure no one else has access to the credentials database.


---------------------------------------------------
# Handoff Scripts
---------------------------------------------------
Please note that all of these scripts MUST be installed in the WORK_DIR.

1. configure.py
This is a python script that allows the customers to store credentials
for the storage array in a local database (created using the script_db module
mentioned above). The script allows user to:
a. Setup a database : This will also clear any information if exists in the database.
b. Add/Modify Host Information : You can add or modify the credentials associated with a host.
c. Delete Host Information : This helps delete information associated with a host.
d. Show information stored in the database for all hosts.

Before using the sample scripts provided, users MUST setup the credentials database
by running this script in the WORK_DIR.

2. run.py
Main executable script that calls SAN specific SteelFusionHandoff.py snapshot management code.

3. ./src/script_db.py
This is a python module that defines two classes for managing information
on the Handoff host and act like a database. Note that this database is stored
in binary format, and it is NOT encrypted. Any information stored in this
database created by this module can be extracted by anyone who has
access to the database file.

5. ./src/libs/hprmcv1/SteelFusionHandoff.py
This is a full-working script that implements snapshot / backup operation handling for luns.

The script arguments are:
work-dir : WORK_DIR for handoff
array : HP RMC host
backuppolicy : Backup Policy from HPE RMC that will be assigned for Express Protect backup of SteelFusion LUNs.
protect-category : Snapshot category for which backup must be run. This must match the type of schedule being run by the snapshot scheduler on the Core. Options are hourly, daily, weekly, or manual.

------------------------------------------------------
# Example Installation Steps
------------------------------------------------------

These steps assume the steps in "Preparing the Handoff Host" have been completed.

1. Create a directory 'C:\rvbd_handoff_scripts'.
   Copy all the files in the Handoff Scripts package to this directory.
   To ensure consistency, make sure the scripts are marked read-only.

2. Run the following commands from command prompt:
   cd C:\rvbd_handoff_scripts
   C:\Python34\python.exe configure.py
   This will start the credentials mgmt script.
   Press appropriate option to first setup the DB.
   Then enter host information. Note that to later change any information, re-run the same
   command (do the Setup the DB - this will erase all other information in the db).

3. On the Core, create a Handoff Configuration (under Configure -> Backups -> Handoff Host.)
   Give the IP address/DNS name of the Windows VM, the user and password for Domain\Administrator.
   Handoff scripts can be installed in following script path:
   'C:\Python34\python.exe C:\rvbd_handoff_scripts\run.py '
   Use the following for script args:
   If you are not running Express Protect Backups:
   '--work-dir --array-model hprmcv1 --array <RMC_HOST>'
   If you are running Express Protect Backups:
   '--work-dir c:\rvbd_handoff_scripts --array-model hprmcv1 --array <RMC_HOST>  --protect-category daily --backuppolicy <POLICY_ID>'
   If you want to protect hourly, specify 'hourly' as protect-category. For manual testing use 'manual'.

   Note that <RMC_HOST> is the IP addresses/DNS name for the HPE RMC host. It must match (2) so that the script will pick up the information for these from the credentials database.
   Ex.
   '--work-dir c:\rvbd_handoff_scripts --array-model hprmcv1 --array rmchost --protect-category daily'

   Press 'Add Handoff Host'.

4. Now assign this handoff host to a LUN (LUN -> Snapshots -> Configuration -> Handoff Host).
   User 'Test Handoff Host' to debug.

Script behavior:
Test Handoff Host:
   Test Handoff Host will check for a Recovery Set on RMC. If there is none associated with the particular LUN, it will try to create one. Creating a Recovery Set on the RMC requires that there be a single storage pool. If there are no or multiple storage pools on RMC, you will need to create the Recovery Set manually.

Create Snapshot: 
   When a snapshot is taken from the Core, the protect-category will determine whether or not Express Backup will be used to perform a backup. If the category matches the schedule, it will attempt to perform a backup, but --backuppolicy must be provided. The backup policy id must be created manually on HPE RMC. Incremental backups are always attempted first. Incremental backups will only succeed if the previous snapshot succeeded and that snapshot must not have been deleted.

Remove Snapshot:
   In the script, there are the switches:
      REMOVE_BACKUP = '0'
      REMOVE_SNAPSHOT = '1'
   If you want the backup to be expired with the snapshot with SteelFusion's remove snapshot option, set REMOVE_BACKUP to 1. The default behavior is to leave the backup. If you want to remove the snapshot with SteelFusion's remove snapshot option, please set REMOVE_SNAPSHOT to 1. The default behavior is to REMOVE the backup.






