--------------------------------------------------
# Important information
--------------------------------------------------
Current snapshot Handoff Scripts support ESXi Proxy servers up to version 5.5 Update2

--------------------------------------------------
# Snapshot Handoff Script
--------------------------------------------------
This document describes how to setup handoff host with SteelFusion handoff scripts.  
This document and all the scripts mentioned here are a property of  
Riverbed Technology and must not be distributed without proper licenses.  
(C) Copyright 2016 Riverbed Technology, Inc  
All rights reserved.  

---------------------------------------------------
# Script Version
---------------------------------------------------
v1.4.1-06012016

---------------------------------------------------
# Hardware Tested
---------------------------------------------------

|array name     | Storage Vendor        |Model/SW version                   |Fabric |Mount Point| API                                       |Edge & Core version        | Backup SW | Last Updated  | Notes                                                  |
|:-------------:|:---------------------:|:---------------------------------:|:-----:|:---------:|:-----------------------------------------:|:-------------------------:|:---------:|:-------------:|:-------------------------------------------------------|
|netapp_v1      |Netapp                 |FAS2050/7.3.7                      |iSCSI  |VMware     |NetApp Manageability SDK v5.2              | 2.5.0-3.6.0               | N/A       |01/14/2014     |Scripts written as a sample, not tested against live NetApp.|
|nimble_v1      |Nimble                 |CS220G/v2.0.7                      |iSCSI  |VMware     |Unofficial PowerShell                      |3.6.0/3.6.0                | Unknown   |02/06/2015     |API https://github.com/jrich523/NimblePowerShell |
|pure_v1        |Pure Storage           |FA-400/4.014                       |FC     |VMware     |Powershell API v4                          |3.6.0/3.6.0                |NetBackup  |02/15/2015     |There is a REST API, next iteration should be refactored to use REST. PowerShell API: http://blog.purestorage.com/faq-about-the-new-pure-storage-powershell-sdk/ |
|hp3par_v1      |3PAR                   |7200 / v3.1.3 MU1                  |FC     |VMware     |Mgmt Console CLI 4.6.1 and 3PAR Client v3.3|3.6.0/3.6.0                |n/a        |07/13/2015     |    	No Proxy mount functionality|
|compellent     |Compellent	            |4020 and 8000/6.5.20               |iSCSI	|VMware	    |Storage Center Command Set 7.01.01.002	    |4.1/4.0 and 4.2.0a         |VEEAM	    |04/22/2016     |1. SKIP_VM_REGISTRATION=1; Works with VMware ESXi5.5update3|
|hpeva          |HP                     |EVA 8400, HSV340, 10001000 Firmware|FC	    |VMware	    |HP P6000 SSSU CLI v10.3.4	                |3.6.0/3.6.0	            |VEEAM	    |12/01/2015 	|1. Requires -system argument; 2. SKIP_VM_REGISTRATION=1; 3. Bugfix: LUN mount on ESXi; 4. Bugfix: snapshot cleanup; 5.Doc: http://h20566.www2.hpe.com/hpsc/doc/public/display?docId=emr_na-c03375122&lang=en-us&cc=us; 6. HP SSSU:https://h20392.www2.hpe.com/portal/swdepot/displayProductInfo.do?productNumber=P6000_CV10.3|
|hpmsa_v1       |HP                     |MSA	P2000 G3/Bundle v. TS201R015|FC	    |VMware	    |SOAP Web API	                            |3.6.0/3.6.0 and 4.1.0/4.1.0|CA Arcserve|03/01/2016     |1. Upgraded VADP to version 4.1.0|
|hpmsa_v1       |HP                     |MSA	P2040 G3/Firmware  GL210R004|FC	    |VMware	    |SOAP Web API	                            |4.0.0/4.1.0 and 4.1.0/4.1.0|CA Arcserve|04/22/2016     |1. Upgraded VADP to version 4.1.0|
|hprmc          |HP                     |RMC	with 3PAP SAN               |FC	    |Integrated |SOAP Web API	                            |4.0.0/4.0.0 and 4.3.0/4.3.0|N/A        |05/19/2016     |   |
|freenas        |FreeNAS                |9.3                                |iSCSI	|n/a        |REST API	                                |4.3.0/4.3.0                |N/A        |05/19/2016     |1. Only snapshots implemented, no mounting. 2. Experimental, tested for development environments only.  |

---------------------------------------------------
# Preparing the Handoff Host
---------------------------------------------------
The scripts have been tested on Windows 2K8 R2, Windows 2012:   

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
   
NOTE: v1 scrips may have other library dependencies. Please check _v1 scripts for what they really need.

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
MUST be installed in the WORK_DIR. IDE used is JetBrains PyCharm v4.5.

1. configure.py  
This is a python script that allows the customers to store credentials
for the storage array in a local database (created using the script_db module
mentioned above). The script allows user to:  
    1. Setup a database : This will also clear any information if exists in the database.
	2. Add/Modify Host Information : You can add or modify the credentials associated with a host.
	3. Delete Host Information : This helps delete information associated with a host.
	4. Show information stored in the database for all hosts.  
NOTE: Before using proxy handoff scripts, users MUST setup the credentials database
by running this script in the WORK_DIR. User must add storage appliance and ESXi proxy host
IP/hostname and  associated credentials

2. run.py  
This is a full-working script that also supports
proxy backup operation for VMware luns.  
The script arguments are:  
array-model : the type of the array we are running scripts against. Reference supported array table for the correct array name.  
work-dir : WORK_DIR for handoff  
array-model : array name, see 'Hadware Tested' table for the correct name
array : storage array ip/hotname  
system: storage array system, this key is only for EVA managed arrays  
proxy-host : ESX Proxy Server ip/hotname  
access-group : SAN Initiator group to which proxy host is mapped  
protect-category : Snapshot category for which proxy backup must be run.

3. Proxy Mounting Scripts.  
The following are the perl scripts implement LUN mounting.  
Logger.pm LogHandler.pm  
vadp_setup.pl vadp_cleanup.pl vadp_helper.pl vm_common.pl vm_fix.pl

4. Script logging.  
Script log file is located in WORK_DIR\log\ folder.  
Script also tracks activity under Microsoft's System Event Log.

5. Work files.  
All work files are located in WORK_DIR\log\ folder.
Work files get created by executing scripts. These work files store
credentials, track snapshot names, track mounted LUNs
and store resignatured virtual machine vmx files.

6. SAN libraries and scripts.  
All SAN specific scripts are stored in WORK_DIR\lib\<storage type>  
Any SAN library that has _v1 in the folder name, has all working scripts and duplicates in the same folder.

------------------------------------------------------
# Example Installation Steps
------------------------------------------------------
1. Setup a VM with Windows 2012 Server.  
2. Install Python3.4 under C:\Python34.  
   This is the default directory under which this version of python will be installed.
3. Install VMware vSphere SDK for Perl 5.5.  
   To get the Windows Installer, you will need to sign-up with VMware.  
   Install the SDK in its default path (C:\Program Files (x86)\VMware).  
   Under 'Advanced Settings' -> 'Environment Variables' for 'Computer' 'Properties'  
   Edit the 'Path' Environment Variable for System (and not PATH for User).  
   Append this at the end:  
   'C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\bin;C:\Program Files (x86)\VMware\VMware vSphere CLI\Perl\lib;'  
   Press OK until you exit the dailogue boxes.
4. Install the appropriate SAN management SDK, if required. See 'Hadware Tested' table.
5. Create a directory 'C:\rvbd_handoff_scripts'.  
   Copy all the files in the Handoff Scripts package to this directory.  
   To ensure consistency, make sure the scripts are marked read-only.
6. Run the following command from command shell:  
   ```
   cd C:\rvbd_handoff_scripts
   C:\Python34\python.exe configure.py
   ```
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
   'C:\Python34\python.exe C:\rvbd_handoff_scripts\src\run.py '  
   Use the following for script args:  
   '--array-model ARRAYMODEL --work-dir c:\rvbd_handoff_scripts --array STORAGE_ARRAY --system EVA_STORAGE_SYSTEM --proxy-host PROXY_HOST --access-group proxy_esxi --protect-category daily'  
   Note that STORAGE_ARRAY and PROXY_HOST are IP addresses/DNS names for storage array and proxy ESX server.  
   They must match (6) so that the script will pick up the information for these from the credentials database.  
   Ex.  
   '--array-model hpeva --work-dir c:\rvbd_handoff_scripts --array 192.168.1.216 --system EVA-PROD --proxy-host gen-at34 --access-group proxy_esxi --protect-category daily'  
   Note: access-group is the permission on the lun, just make sure the wwn has permission to access the newly created volume  
   Press 'Add Handoff Host'.  
9. Now assign this handoff host to a LUN (LUN -> Snapshots -> Configuration -> Handoff Host).  
   Use 'Test Handoff Host' to validate configuration