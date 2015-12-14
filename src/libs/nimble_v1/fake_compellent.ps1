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
#$user = "Admin"            
#$pw = get-content c:\rvbd_handoff_scripts\supersecretfile.txt | convertto-securestring -key (1..16)

# Now this is passed as -array argument
if (! $array) {
	Write-Error ("Missing -array parameter");
	exit 1
}

if (! $operation) {
	Write-Error ("Missing -operation parameter");
	exit 1
}

if ($operation.Contains("HELLO")) {
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
	


	exit 0

}

if($operation.Contains("SNAP_REMOVE")) {
	#Clean up the replay
	
	if (! $replay) {
		# We need the mount serial argument for the script
		Write-Error "Please pass -replay parameter to the script"
		exit 1
	}
	
	
	exit 0
}

if ($operation.Contains("SNAP_CREATE")) {

	#Define Snapshot volume
	
	$a = Get-Random -Minimum -100 -Maximum 100
    Write-Host ("Index:" + $a)
    exit 0
}

if ($operation.Contains("CREATE_SNAP_AND_MOUNT")) {

	# Create a new snapshot (called replay)
	$b = Get-Random -Minimum -100 -Maximum 100
	Write-Host ("Index:" + $b)
                                   

	$set    = "abcdefghijklmnopqrstuvwxyz0123456789".ToCharArray()
	$result = ""
	$Length = 20
	for ($x = 0; $x -lt $Length; $x++) {
		$result += $set | Get-Random
	}
	return $result								   
	# Print the output
	Write-Host ("Clone:" + $mount_lun.SerialNumber)

	exit 0
}

Write-Host("Could not run the script at all!")









