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

####Below loads Compellent Storage Center Snapin
###Add-PSSnapin Compellent.StorageCenter.PSSnapin

# Before running the script, please run the compllent_cred.ps1
# for the first time to create the supersecret file in c:\rvbd_handoff_scripts

#Parameters for the script
param([string]$serial = "", [string]$operation = "", [string]$category = "", [string]$replay = "", [string]$mount="", [string]$user = "Admin", [string]$array="", [string]$accessgroup = "")
$user = "Admin"            
$pw = get-content c:\rvbd_handoff_scripts\supersecretfile.txt | convertto-securestring -key (1..16)

# Now this is passed as -array argument
if (! $array) {
	Write-Error ("Missing -array parameter");
	exit 1
}

if (! $operation) {
	Write-Error ("Missing -operation parameter");
	exit 1
}

# Make sure the necessary snapins are loaded            
$compSnapinLoaded = $FALSE            
$currentSnapins = Get-PSSnapin            
# Check if we need to load the snapin            
foreach ($snapin in $currentSnapins)            
{            
    if ($snapin.Name -eq "Compellent.StorageCenter.PSSnapIn")            
    {$compSnapinLoaded = $TRUE}            
}            

if ($compSnapinLoaded -eq $FALSE)            
    {$null = Add-PSSnapin Compellent.StorageCenter.PSSnapIn}


$SCConnect = Get-SCConnection -Hostname $array -user $user -pass $pw
if (! $SCConnect) 
{
    write-host ("Failed to connect to the storage array")
    exit 1
}

# Get handle to the lun for which we will run the required operation
$rdm_os_01 = get-scvolume -serialnumber $serial -connection $SCConnect

if ($operation.Contains("HELLO")) {
	# Just check that the lun is accessible
    if (!$rdm_os_01) {
        Write-Error ("Invalid serial test")
        # Failed to find the lun, exit with non-zero code
        exit 1
    }
    # We could find the lun, exit with code 0
    write-host ("OK")
    exit 0
}

if($operation.Contains("UNMOUNT")) {
	#Clean up the mounted lun
	
	if (! $mount) {
		# We need the mount serial argument for the script
		Write-Error "Please pass -mount parameter to the script"
		exit 1
	}
	
	#Define old Mounted Volume
	$old_lun = get-scvolume -serial $mount -connection $SCConnect

	#Define old Server Mapping
	$old_mapping = get-scserver -name $accessgroup -connection $SCConnect

	#Remove old Mapping
	remove-scvolumemap -SCVolume $old_lun -SCServer $old_mapping -connection $SCConnect -Confirm:$false

	#Remove old Volume
	Remove-SCVolume -SCVolume $old_lun -connection $SCConnect -Confirm:$false -SkipRecycleBin

	exit 0

}

if($operation.Contains("SNAP_REMOVE")) {
	#Clean up the replay
	
	if (! $replay) {
		# We need the mount serial argument for the script
		Write-Error "Please pass -replay parameter to the script"
		exit 1
	}
	
	# Find the snapshot
	$snap = Get-SCReplay -Index $replay -Connection $SCConnect
	# Need to delete this current_snap
    if ($snap) {
        Remove-SCReplay -SCReplay $snap -Connection $SCConnect -Confirm:$false
    }
    
	exit 0
}

if ($operation.Contains("SNAP_CREATE")) {

	#Define Snapshot volume
	$rdm_os_01 = get-scvolume -serialnumber $serial -connection $SCConnect
	$a = New-SCReplay $rdm_os_01 -MinutesToLive 1440 -Description RVBD_Granite_Snap -Connection $SCConnect
    Write-Host ("Index:" + $a.index)
    exit 0
}

if ($operation.Contains("CREATE_SNAP_AND_MOUNT")) {

	# Create a new snapshot (called replay)
	$b = New-SCReplay $rdm_os_01 -MinutesToLive 1440 -Description RVBD_Granite_Snap -Connection $SCConnect
	Write-Host ("Index:" + $b.index)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            # Code is missing to remove the old snapshot
	$current_snap = Get-SCReplay -Index $b.Index -Connection $SCConnect

	#Create Volume from replay (Snapshot)
    $mount_lun = new-scvolume -SourceSCReplay $b -connection $SCConnect

	#Define Proxy host to Mount to
	$Mount_Server = Get-SCServer -Name $accessgroup -connection $SCConnect

	#Map LUN to proxy host
	new-scvolumemap $mount_lun $Mount_Server -connection $SCConnect
	# Print the output
	Write-Host ("Clone:" + $mount_lun.SerialNumber)

	exit 0
}

Write-Host("Could not run the script at all!")









