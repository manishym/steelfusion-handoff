
--------------------------------------------------
# Snapshot Handoff Script
--------------------------------------------------
This document describes how to setup handoff host with sample scripts.
This document and all the scripts mentioned here are a property of
Riverbed Technology and must not be distributed without proper licenses.
(C) Copyright 2015 Riverbed Technology, Inc
All rights reserved.

---------------------------------------------------
# Hardware Tested
---------------------------------------------------
SteelFusion Core 3.6.0
SteelFusion EX1160 v3.6.0a
ESXi 5.5.0
HP EVA 8400 (P6000), HSV340 Controller (10001000 Firmware)
HP P6000 SSSU 10.3.6
Windows 2012 Handoff host

---------------------------------------------------
# HP SDK Documentation
---------------------------------------------------
http://h20566.www2.hpe.com/hpsc/doc/public/display?docId=emr_na-c03375122&lang=en-us&cc=us

---------------------------------------------------
# Preparing the Handoff Host
---------------------------------------------------
The scripts have been tested on Windows 2K8 R2, Windows 2012
1. Install Python3.4.0+ (https://www.python.org/downloads/) under C:\Python34 for "all" users.
2. Install VMware's Perl SDK. The minimum required version is "VMware vSphere SDK for Perl 5.5".
   By default, the SDK is installed at 'C:\Program Files (x86)\VMware'.
   Please make sure to include the SDK Path 'C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\bin' and
   "C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\lib" in "System Environment Variable" called "Path".
   Please reboot the Windows box after making these changes.
3. If you are supporting proxy backup operations with handoff, please copy the scripts
   under "Handoff Scripts" mentioned below under appropriate directory.
   We tested by placing the directory under "C:\rvbd_handoff_scripts".
   This is referred to as "WORK_DIR" in the remainder of this README.
4. Setup the credentials to be used by your scripts using the setup.py script
   mentioned in the "Handoff Scripts".

---------------------------------------------------
# Managing Security of data
---------------------------------------------------
The handoff host must be configured with an Administrator account
that will be used for running the handoff scripts.
Note that the default script provided here accesses and reads the
credential database setup using the setup.py script.
Since it stores credentials for storage array, we recommend:
1. Run the scripts using Administrator account
2. Set 'Administrator' only permissions on the WORK_DIR.
   This will ensure no one else has access to the credentials database.


---------------------------------------------------
# Handoff Scripts
---------------------------------------------------
Granite Core dev team has provided the following package can help ease the
deployment of Snapshot Handoff. Please note that all of these scripts
MUST be installed in the WORK_DIR.

1. ./src/script_db.py
This is a python module that defines two classes for managing information
on the Handoff host and act like a database. Note that this database is stored
in binary format, and it is NOT encrypted. Any information stored in this
database created by this module can be easily extracted by anyone who has
access to the database file.

2. setup.py
This is a python script that allows the customers to store credentials
for the storage array in a local database (created using the script_db module
mentioned above). The script allows user to:
a. Setup a database : This will also clear any information if exists in the database.
b. Add/Modify Host Information : You can add or modify the credentials associated with a host.
c. Delete Host Information : This helps delete information associated with a host.
d. Show information stored in the database for all hosts.

Before using the sample scripts provided, users MUST setup the credentials database
by running this script in the WORK_DIR.

4. SteelFusionHandoff.py
This is a full-working script that also supports
proxy backup operation for VMware luns.
The script arguments are:
work-dir : WORK_DIR for handoff
storage-array : storage array
system: storage array system
proxy-host : ESX Proxy Server
access-group : SAN Initiator group to which proxy host is mapped
protect-category : Snapshot category for which proxy backup must be run.

5. Proxy Backup Scripts.
The following are the perl scripts implement proxy backup.
Logger.pm LogHandler.pm
vadp_setup.pl vadp_cleanup.pl vadp_helper.pl vm_common.pl vm_fix.pl

6. Log file is located in .\log\ folder.

------------------------------------------------------
# Example Installation Steps
------------------------------------------------------
1. Setup a VM with Windows 2012 Server.
2. Install Python3.4 under C:\Python34. This is the default directory
   under which this version of python will be installed.
3. Install VMware vSphere SDK for Perl 5.5.
   To get the Windows Installer, you will need to sign-up with VMware.
   Install the SDK in its default path (C:\Program Files (x86)\VMware).
   Under 'Advanced Settings' -> 'Environment Variables' for 'Computer' 'Properties'
   Edit the 'Path' Environment Variable for System (and not PATH for User).
   Append this at the end:
   'C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\bin;C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\lib;'.
   Press OK until you exit the dailogue boxes.
4. Install the HP SSSU SDK.
5. Create a directory 'C:\rvbd_handoff_scripts'.
   Copy all the files in the Handoff Scripts package to this directory.
   To ensure consistency, make sure the scripts are marked read-only.
6. Run the following command from command shell:
   cd C:\rvbd_handoff_scripts
   C:\Python34\python.exe setup.py
   This will start the credentials mgmt script.
   Press appropriate option to first setup the DB.
   Then enter host information. Note that to later change any information, re-run the same
   command (do the Setup the DB - this will erase all other information in the db).
   Add information for the proxy host (ex. PROXY_ESX) and the storage array (ex. STORAGE_ARRAY).

7. Reboot the Windows VM. This is just to ensure that the changes
   you made stick and are picked up properly by Windows OS.
8. On Granite Core, create a Handoff Configuration (under Snapshot -> Handoff Hosts).
   Give the IP address/DNS name of the Windows VM, the user and password for Administrator.
   Use the following for script path:
   'C:\Python34\python.exe C:\rvbd_handoff_scripts\src\SteelFusionHandoff.py '
   Use the following for script args:
   '--work-dir c:\rvbd_handoff_scripts --storage-array STORAGE_ARRAY --system EVA_STORAGE_SYSTEM --proxy-host PROXY_HOST --access-group proxy_esxi --protect-category daily'
   Note that STORAGE_ARRAY and PROXY_HOST are IP addresses/DNS names for storage array and proxy ESX server.
   They must match (6) so that the script will pick up the information for these from the credentials database.
   Ex.
   '--work-dir c:\rvbd_handoff_scripts --storage-array my-eva-manager --system EVA-PROD --proxy-host gen-at34 --access-group proxy_esxi --protect-category daily'

   Note: access-group is the permission on the lun, just make sure the wwn has permission to access the newly created volume
   Press 'Add Handoff Host'.
9. Now assign this handoff host to a LUN (LUN -> Snapshots -> Configuration -> Handoff Host).
   User 'Test Handoff Host' to validate configuration
