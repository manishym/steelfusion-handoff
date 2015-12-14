Function Connect-PfaHost() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $HostName,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Volume,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $HostConnect = $null
    $HostConnect = [ordered]@{
        name = $HostName
        vol = $Volume
    } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "https://$FlashArray/api/1.2/host/$HostName/volume/$Volume" -Body $HostConnect -WebSession $Session -ContentType "application/json"
}

Function New-PfaSnapshot() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $SnapshotVolume,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $SnapshotSuffix,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Snapshot = $null
    $Snapshot = [ordered]@{
        snap = "true"
        source = [Object[]]"$SnapshotVolume"
        suffix = $SnapshotSuffix
    } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "https://$FlashArray/api/1.2/volume" -Body $Snapshot -WebSession $Session -ContentType "application/json"
}

Function New-PfaVolume() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Name,
        [Parameter()][ValidateNotNullOrEmpty()][string] $Size = $null,
        [Parameter()][ValidateNotNullOrEmpty()][string] $Source = $null,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
        #TODO: Add Overwrite support.
    )

    $Volume = $null
    If($Source) {
        $Volume = @{
            source = $Source
        } | ConvertTo-Json
    } Else {
        $Volume = @{
            size = $Size
        } | ConvertTo-Json
    }
    Invoke-RestMethod -Method Post -Uri "https://$FlashArray/api/1.2/volume/$Name" -Body $Volume -WebSession $Session -ContentType "application/json"
}

function Get-PfaAPIToken {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
	    [Parameter()][ValidateNotNullOrEmpty()][string] $Username,
	    [Parameter()][ValidateNotNullOrEmpty()][string] $Password
    )
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    $AuthAction = @{
        password = $Username
        username = $Password
    }
    return(Invoke-RestMethod -Method Post -Uri "https://$FlashArray/api/1.2/auth/apitoken" -Body $AuthAction)
}

Function Connect-PfaController() {
    [CmdletBinding()]
	Param (
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][string] $APIToken
	)
	
	[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
	$SessionAction = @{
		api_token = $APIToken
	}
	$Response = Invoke-RestMethod -Method Post -Uri "https://$FlashArray/api/1.1/auth/session" -Body $SessionAction -SessionVariable Session
	$Session
}

Function Disconnect-PfaController() {
	[CmdletBinding()]
	Param (
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
	)
	$Respone = Invoke-RestMethod -Method Delete -Uri "https://$FlashArray/api/1.1/auth/session" -WebSession $Session
}

Function Get-PfaHosts() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    return(Invoke-RestMethod -Method Get -Uri "https://$FlashArray/api/1.2/host" -WebSession $Session -ContentType "application/json")
}

Function Get-PfaAlerts() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/message?audit=true"
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Get-PfaArray() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    return(Invoke-RestMethod -Method Get -Uri "https://$FlashArray/api/1.2/array" -WebSession $Session)
}

Function Get-PfaVolume() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/volume"
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Get-PfaVolumeStatistics() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Volume,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/volume/$Volume"+"?action=monitor"
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Disconnect-PfaVolume() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Volume,
        [Parameter()][ValidateNotNullOrEmpty()][string] $HostName = $null,
        [Parameter()][ValidateNotNullOrEmpty()][string] $HostGroupName = $null,
   		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    If($HostName) {
        $Uri = "https://$FlashArray/api/1.2/host/$HostName/volume/$Volume"
    } Else {
        If($HostGroupName) {
            $Uri = "https://$FlashArray/api/1.2/hgroup/$HostGroupName/volume/$Volume"
        }
    }
    return(Invoke-RestMethod -Method Delete -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Remove-PfaVolume() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Volume,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
        #[Parameter()][ValidateNotNullOrEmpty()][string] $Eradicate
    )
    try {
        return(Invoke-RestMethod -Method Delete -Uri "https://$FlashArray/api/1.2/volume/$Volume" -WebSession $Session)
    } catch {
        # TODO        
    }
}

Function Get-PfaSnapshot() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/volume?snap=true"
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Eradicate-PfaVolume() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Volume,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    try {
        $Uri = "https://$FlashArray/api/1.2/volume/$Volume"+"?eradicate=true"
        $Response = Invoke-RestMethod -Method Delete -Uri $Uri -WebSession $Session
    } catch {
        # TODO
    }
}

Function Get-PfaPorts() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/port"
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Get-PfaInitiators() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/port?initiators=true"
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Get-PfaHostGroup() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter()][ValidateNotNullOrEmpty()][string] $GroupName = $null,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    If($GroupName) {
        $Uri = "https://$FlashArray/api/1.2/hgroup/$GroupName"
    } Else {
        $Uri = "https://$FlashArray/api/1.2/hgroup"
    }
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Get-PfaHostGroupSpace() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter()][ValidateNotNullOrEmpty()][string] $GroupName = $null,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    If($GroupName) {
        $Uri = "https://$FlashArray/api/1.2/hgroup/$GroupName"+"?space=true"
    } Else {
        $Uri = "https://$FlashArray/api/1.2/hgroup?space=true"
    }
    return(Invoke-RestMethod -Method Get -Uri $Uri -WebSession $Session -ContentType "application/json")
}

Function Open-PureStorageGitHub() {
    $link = "https://github.com/purestorage/PowerShell-Toolkit"
    $browserProcess = [System.Diagnostics.Process]::Start($link)
}

Function Connect-PfaHostGroup() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $HostGroupName,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Volume,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/hgroup/$HostGroupName/volume/$Volume"
    Invoke-RestMethod -Method Post -Uri $Uri -Body $HostConnect -WebSession $Session -ContentType "application/json"
}

Function Get-PfaProtectionGroups() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )
    $Uri = "https://$FlashArray/api/1.2/pgroup"
    Invoke-RestMethod -Method Get -Uri $Uri -Body $HostConnect -WebSession $Session -ContentType "application/json"
}

Function Refresh-PfaVolume() {
    [CmdletBinding()]
    Param(
	    [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $FlashArray,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Name,
        [Parameter(Mandatory=$True)][ValidateNotNullOrEmpty()][string] $Source,
		[Parameter(Mandatory = $True)][ValidateNotNullOrEmpty()][Microsoft.PowerShell.Commands.WebRequestSession]$Session
        #TODO: Add Overwrite support.
    )

    $Json = [ordered]@{
        overwrite = "true"
        source = $Source
    } | ConvertTo-Json

    Invoke-RestMethod -Method Post -Uri "https://$FlashArray/api/1.2/volume/$Name" -Body $Json -WebSession $Session -ContentType "application/json"
}

Export-ModuleMember -Function Connect-PfaController
Export-ModuleMember -Function Disconnect-PfaController
Export-ModuleMember -Function New-PfaSnapshot
Export-ModuleMember -Function New-PfaVolume
Export-ModuleMember -Function Connect-PfaHost
Export-ModuleMember -Function Get-PfaVolume
Export-ModuleMember -Function Get-PfaVolumeStatistics
Export-ModuleMember -Function Get-PfaHosts
Export-ModuleMember -Function Get-PfaArray
Export-ModuleMember -Function Get-PfaSnapshot
Export-ModuleMember -Function Get-PfaAlerts
Export-ModuleMember -Function Remove-PfaVolume
Export-ModuleMember -Function Disconnect-PfaVolume
Export-ModuleMember -Function Get-PfaAPIToken
Export-ModuleMember -Function Eradicate-PfaVolume
Export-ModuleMember -Function Get-PfaPorts
Export-ModuleMember -Function Get-PfaInitiators
Export-ModuleMember -Function Get-PfaHostGroupSpace
Export-ModuleMember -Function Get-PfaHostGroup
Export-ModuleMember -Function Open-PureStorageGitHub
Export-ModuleMember -Function Connect-PfaHostGroup
Export-ModuleMember -Function Connect-PfaProtectionGroups
Export-ModuleMember -Function Refresh-PfaVolume