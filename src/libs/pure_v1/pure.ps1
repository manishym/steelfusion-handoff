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

####Below loads Pure Module
###Import-Module PureStorage.PowerShell.Toolkit.psd1

#Parameters for the script
param([string]$serial = "", [string]$operation = "", [string]$category = "", [string]$replay = "", [string]$mount="", [string]$user = "", [string]$array="", [string]$accessgroup = "")
$user = "pureuser"            
$pw = "pureuser"

# Now this is passed as -array argument
if (! $array) {
	Write-Error ("Missing -array parameter");
	exit 1
}

if (! $operation) {
	Write-Error ("Missing -operation parameter");
	exit 1
}

# Make sure the necessary module is loaded            
$pureSnapinLoaded = $FALSE            
$currentSnapins = Get-Module           
# Check if we need to load the snapin            
foreach ($snapin in $currentSnapins)            
{            
    if ($snapin.Name -eq "PureStorage.PowerShell.Toolkit")            
    {$pureSnapinLoaded = $TRUE}            
}            

if ($pureSnapinLoaded -eq $FALSE)            
    {$null = Import-Module c:\rvbd_handoff_scripts\PureStorage.PowerShell.Toolkit.psm1}

#$SCConnect = Get-SCConnection -Hostname $array -user $user -pass $pw

$MyToken = Get-PfaAPIToken -FlashArray $array -Username $user -Password $pw
$SCConnect = Connect-PfaController -FlashArray $array -APIToken $MyToken.api_token 

if (! $SCConnect)
{
    write-host ("Failed to connect to the storage array")
    exit 1
}

$serial = $serial.Substring(8,24)


# Get handle to the lun for which we will run the required operation
#$rdm_os_01 = get-scvolume -serialnumber $serial -connection $SCConnect

$rdm_os_01 = Get-PfaVolume -FlashArray $array -Session $SCConnect | Where-Object { $_.serial -like "$serial" } 

#$rdm_os_01 = Get-PfaVolume -FlashArray $array -Session $SCConnect | Where-Object { $_.serial -like "624a9370753d69fe46db318d000262ba" } 

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
	#$old_lun = get-scvolume -serial $mount -connection $SCConnect
    $old_lun = Get-PfaVolume -FlashArray $array -Session $SCConnect | Where-Object { $_.serial -like "$mount" } 
    write-host ($old_lun)

	#Define old Server Mapping
	#$old_mapping = get-scserver -name $accessgroup -connection $SCConnect
    write-host ("The access group is: " + $accessgroup)

	#Remove old Mapping
	#remove-scvolumemap -SCVolume $old_lun -SCServer $old_mapping -connection $SCConnect -Confirm:$false       
    Disconnect-PfaVolume -FlashArray $array -Volume $old_lun.name -HostGroupName $accessgroup -Session $SCConnect
    write-host ("Removing permissions from the " + $accessgroup + "from the LUN") 

	#Remove old Volume
	#Remove-SCVolume -SCVolume $old_lun -connection $SCConnect -Confirm:$false -SkipRecycleBin
    Remove-PfaVolume -FlashArray $array -Volume $old_lun.name -Session $SCConnect  
    write-host ("The old LUN serial that should have been removed is: " + $old_lun.serial)
    Eradicate-PfaVolume -FlashArray $array -Volume $old_lun.name -Session $SCConnect
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
#	$snap = Get-SCReplay -Index $replay -Connection $SCConnect
    $snap = Get-PfaSnapshot -FlashArray $array -Session $SCConnect | Where-Object { $_.serial -like "$replay" } 


	# Need to delete this current_snap
    if ($snap) {
#        Remove-SCReplay -SCReplay $snap -Connection $SCConnect -Confirm:$false
    Write-Host ("Putting PfaVolume in the Recycle Bin:" + $snap.name)
    Remove-PfaVolume -FlashArray $array -Volume $snap.name -Session $SCConnect
    Write-Host ("Eradicating:" + $snap.serial)
    Eradicate-PfaVolume -FlashArray $array -Volume $snap.name -Session $SCConnect

    }
    
	exit 0
}

if ($operation.Contains("SNAP_CREATE")) {

	#Define Snapshot volume
#	$rdm_os_01 = get-scvolume -serialnumber $serial -connection $SCConnect

$rdm_os_01 = Get-PfaVolume -FlashArray $array -Session $SCConnect  | Where-Object { $_.serial -like "$serial" } 

#	$a = New-SCReplay $rdm_os_01 -MinutesToLive 1440 -Description RVBD_Granite_Snap -Connection $SCConnect
$current = "{0:yyyy-MMM-dd-HH-mm}" -f (Get-Date)
$a = New-PfaSnapshot -FlashArray $array -SnapshotVolume $rdm_os_01.name -SnapshotSuffix $current -Session $SCConnect
$a.serial
#$a = New-PfaVolume -FlashArray $array -name test1 -source $rdm_os_01.name+"_replay" -Session $SCConnect
#    Write-Host ("Index:" + $a.index)   
    Write-Host ("New LUN Serial is:" + $a.serial)
    exit 0
}

if ($operation.Contains("CREATE_SNAP_AND_MOUNT")) {
$rdm_os_01 = Get-PfaVolume -FlashArray $array -Session $SCConnect  | Where-Object { $_.serial -like "$serial" } 
	Write-Host ("Creating a snapshot and will mount")

#$rdm_os_01 | out-file c:\lun_trying_to_snapshot.txt

# Create a new snapshot (called replay)
$current = "{0:yyyy-MMM-dd-HH-mm}" -f (Get-Date)
#$b = New-PfaSnapshot -FlashArray $array -SnapshotVolume $rdm_os_01 -SnapshotSuffix ([Guid]::NewGuid()) ###  create snapshotsuffix - snapshot = volumename.suffix
$b = New-PfaSnapshot -FlashArray $array -SnapshotVolume $rdm_os_01.name -SnapshotSuffix $current -Session $SCConnect
	Write-Host ("Index:" + $b.serial)

#$b | out-file c:\serial.number.txt
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            # Code is missing to remove the old snapshot
#	$current_snap = Get-SCReplay -Index $b.Index -Connection $SCConnect
$current_snap = Get-PfaSnapshot -FlashArray $array -Session $SCConnect  | Where-Object { $_.name -like "$serial" } 

#	Write-Host ("I'm trying to mount and snapshot")

	#Create Volume from replay (Snapshot)
#    $mount_lun = new-scvolume -SourceSCReplay $b -connection $SCConnect
$sourcepre=$rdm_os_01.name
$source=$sourcepre+"."+$current
$snapname="rvbd"+$rdm_os_01.serial.Substring(19)+$current.Substring(9)

$mount_lun = New-PfaVolume -FlashArray $array -name $snapname -source $source -Session $SCConnect
$mount_lun2 = Get-PfaVolume -FlashArray $array -Session $SCConnect  | Where-Object { $_.name -like "$snapname" }  
Write-Host ("New LUN Serial is:" + $mount_lun.serial)

### Connect-PFAHost .... 
	#Define Proxy host to Mount to
#	$Mount_Server = Get-SCServer -Name $accessgroup -connection $SCConnect
	#Map LUN to proxy host
#	new-scvolumemap $mount_lun $Mount_Server -connection $SCConnect
Connect-PfaHostGroup -FlashArray $array -HostGroupName $accessgroup -Volume $mount_lun2.name -Session $SCConnect

# Print the output
#Write-Host ("Connected to Access group:" + $accessgroup)

	exit 0
}

Write-Host("Could not run the script at all!")









