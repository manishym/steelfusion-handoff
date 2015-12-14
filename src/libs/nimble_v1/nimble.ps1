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

# Before running the script, please run the compllent_cred.ps1
# for the first time to create the supersecret file in c:\rvbd_handoff_scripts

#Parameters for the script
param([string]$serial = "", [string]$operation = "", [string]$category = "", [string]$replay = "", [string]$mount="", [string]$user = "Admin", [string]$array="", [string]$accessgroup = "")
#$user = "Admin"            
$array="nimble.techmktg.lab"
$pw = "Im2demo4u"

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
$currentSnapins = Get-Module         
# Check if we need to load the snapin            
foreach ($snapin in $currentSnapins)            
{            
    if ($snapin.Name -eq "Name")            
    {$compSnapinLoaded = $TRUE}            
}            

if ($compSnapinLoaded -eq $FALSE)            
    {$null = Import-Module C:\rvbd_handoff_scripts\Nimble}


#$SCConnect = Get-SCConnection -Hostname $array -user $user -pass $pw
#$SCConnect = Connect-NSArray $array $pw
#if (! $SCConnect) 
##{
#    write-host ("Failed to connect to the storage array")
#    exit 1
#}

# Get handle to the lun for which we will run the required operation
Connect-NSArray $array $pw
$rdm_os_01 = Get-NSVolume | select name,serialnumber |  Where-Object { $_.serialnumber -like "$serial" }

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
	Connect-NSArray $array $pw
	$old_lun = Get-NSVolume | select name,serialnumber,aclList |  Where-Object { $_.serialnumber -like "$mount" }

	Remove-NSVolume $old_lun.name -force
    write-host ("LUN removed: "+ $old_lun.name)
	exit 0

}

if($operation.Contains("SNAP_REMOVE")) {
	#Clean up the replay
	
	if (! $replay) {
		# We need the mount serial argument for the script
		Write-Error "Please pass -replay parameter to the script"
		exit 1
	}

	Connect-NSArray $array $pw
	# Find the snapshot
	$snap = Get-NSSnapShot | Where-Object { $_.name -like "$replay" }
	$remove_vol = get-nsvolume | Where-Object { $_.name -like "$replay" }
    # Need to delete this current_snap
    if ($remove_vol) {
    $remove_vol.name | Remove-NSVolume -force -confirm:$FALSE
    write-host ("Volume removed: "+ $replay)
    }

    if ($snap) {
    Get-NSSnapShot | Where-Object { $_.name -like "$replay" } | Remove-NSSnapShot -Confirm:$false
    write-host ("Snapshot removed: "+ $replay)
    }
	exit 0
}

if ($operation.Contains("SNAP_CREATE")) {
Connect-NSArray $array $pw
	#Define Snapshot volume
	$rdm_os_01 = Get-NSVolume | select name,serialnumber |  Where-Object { $_.serialnumber -like "$serial" }
	#$rdm_os_01 = get-scvolume -serialnumber $serial -connection $SCConnect
	#$a = New-SCReplay $rdm_os_01 -MinutesToLive 1440 -Description RVBD_Granite_Snap -Connection $SCConnect
	$current = "{0:yyyy-MMM-dd-HH-mm}" -f (Get-Date)
    $snapname="rvbd"+$rdm_os_df01.serialnumber.Substring(0,6)+$current.Substring(9)
#	$snapname=$replay
    Write-Host ("Creating a snapshot of LUN "+$serial)
    $a = Get-NSVolume -name $rdm_os_01.name | New-NSSnapshot -name $snapname
#	$a = New-NSSnapshot -Volume $rdm_os_01.name -Name $rdm_os_01-$current
    Write-Host ("Snapshot Created:" + $snapname)
    exit 0
}

if ($operation.Contains("CREATE_SNAP_AND_MOUNT")) {
#Get-Variable | out-file c:\variables.txt
Connect-NSArray $array $pw
	$rdm_os_df01 = Get-NSVolume | select name,serialnumber |  Where-Object { $_.serialnumber -like "$serial" }
	Write-Host ("Creating a snapshot and will mount")
	$current = "{0:yyyy-MMM-dd-HH-mm}" -f (Get-Date)
    $snapname="rvbd"+$rdm_os_df01.serialnumber.Substring(0,6)+$current.Substring(9)
#    $snapname=$replay
	Get-NSVolume -name $rdm_os_01.name | New-NSSnapshot -name $snapname | new-nsclone -name $snapname
	Write-Host ("Snapshot Created:" + $snapname)
	Add-NSInitiatorGroupToVolume -InitiatorGroup $accessgroup -Volume $snapname -Access volume
	Write-Host ("Connecting Initiator $accessgroup to " + $snapname)
	$b=Get-NSVolume | select name,serialnumber |  Where-Object { $_.name -like "$snapname" }
	Write-Host ("New Volume Serial Number:" + $b.serialnumber)

	exit 0
}

Write-Host("Could not run the script at all!")









