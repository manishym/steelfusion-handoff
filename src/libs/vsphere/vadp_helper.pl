####
# (C) Copyright 2003-2013 Riverbed Technology, Inc.
# All rights reserved. Confidential.
#
####

use strict;
use warnings;
use File::Basename qw(dirname);
use Cwd qw(abs_path);
use lib dirname(abs_path(__FILE__));
require "vm_common.pl";
require "vm_fix.pl";

sub attach_and_mount_lun {
    my $log = LogHandle->new("attach_and_mount");
    my ($lun_serial, $datacenter, $host) = @_;

    $log->info("Starting setup operation on the host ". $host->name);
    my $storage = Vim::get_view(mo_ref => $host->configManager->storageSystem);
    my $datastore;

    my $scan_hbas = get_hbas_to_be_scanned($storage->storageDeviceInfo);
    
    my $MAX_RETRIES = 2;
    my $ds;
    my $count = 0;
    for ($count = 0; $count <= $MAX_RETRIES; $count++) {
        foreach (@$scan_hbas) {
            my $hba = $_;
            $log->debug("Scanning hba $hba");
            eval {
                $storage->RescanHba(hbaDevice => $hba);
            };
            if ($@) {
                $log->warn("Scan HBA failed for $hba: ". $@);
            }
            #XXX: More appropriate actions depending on the type of error
        }
        $storage = Vim::get_view(mo_ref => $host->configManager->storageSystem);
        #Walk through the scsi luns and the locate the lun that is of interest.
        my $scsi_device = serial_match_scsi_lun($storage, $lun_serial, $log);
        if (! defined($scsi_device)) {
            $log->info("Could not locate scsi device for $lun_serial");
            #Retry
            #Sleep before the next retry cycle
            sleep(2);
            next;
        }
        my $wwn_serial = $scsi_device->canonicalName;
        #Inorder to mount the VMFS volume we need to determine the VMFS UUID
        #Get a list of unresolved vmfs volumes and check if any of them matches the device.
        $datastore = mount_from_unresolved($host, $wwn_serial, $storage, $datacenter);
        if (defined($datastore) && $datastore->summary->accessible) {
            $log->info("Datastore for lun $wwn_serial is already mounted");
            return $datastore;
        }

        # Else try to attach the lun and rescan the VMFS volumes
        my $op_states = $scsi_device->operationalState;
        if ($$op_states[0] ne "ok") {
            eval {
                $storage->AttachScsiLun(lunUuid => $scsi_device->uuid);
                $log->info("Successfully attached LUN " . $lun_serial);
            };
            if($@) {
                if (ref($@) eq 'SoapFault') {
                    if(ref($@->detail) eq 'InvalidState') {
                        $log->diag("Device is already attached $lun_serial");
                    } else {
                        $log->error("Error attaching lun $lun_serial - " . $@);
                        die $@;
                }
                } else {
                    $log->error("Generic error attaching lun $lun_serial - " . $@);
                    die $@;
                }
            }
        } else {
            $log->info("Device is already attached");
        }

        #If ESXi had not seen the lun before then it will not show up in 
        #unresolved volumes.  It will show up when it is looked up and it may
        #need to be mounted
        $log->debug("Trying to mount the volume by looking up datastore");
        eval {
            $storage->RescanVmfs();
        };
        if ($@) {
            $log->warn("Rescan vmfs volumes failed: " . $@);
            #proceed
        }
        $ds = locate_unique_datastore_for_lun($wwn_serial,
                                              $datacenter,
                                              $host,
                                              $storage);
        if (defined ($ds)) {
            my $vmfs_name = $ds->info->vmfs->name;
            eval {
                $log->info("Mounting VMFS volume: $vmfs_name");
                $storage->MountVmfsVolume(vmfsUuid => $ds->info->vmfs->uuid);
                $log->diag("VMFS volume successfully mounted: $vmfs_name");
            };
            if($@) {
                if (ref($@) eq 'SoapFault') {
                    if(ref($@->detail) eq 'InvalidState') {
                        $log->diag("Device is already mounted $vmfs_name");
                    } else {
                        $log->error("Unable to mount $vmfs_name: $@");
                        die $@;
                    }
                } else {
                    die $@;
                }
            }
        }
        #Sleep before the next retry cycle
        sleep(2);
    }
    if (! defined($ds)) {
        my $err_msg = "Unable to mount the datastore. While this may be due ".
                      "to various reasons, rebooting the ESXi proxy host may ".
                      "help resolve it";
        die $err_msg;
    }
}

sub mount_from_unresolved {
    my ($host, $wwn_serial, $storage_sys, $datacenter) = @_;

    my $log = LogHandle->new("mount_unresolved");
    my $dstore_sys = Vim::get_view(mo_ref => $host->configManager->datastoreSystem);
    $log->diag("Query for unresolved vmfs volumes.");
    my $uvs = $dstore_sys->QueryUnresolvedVmfsVolumes();
    foreach (@$uvs) {
        my $vmfs = $_;
        my $vmfs_label = $vmfs->vmfsLabel;
        my $extents = $vmfs->extent;
        #Match against all extents
        my $match_found = 0;
        my @device_paths;
        foreach (@$extents) {
            my $device = $_->device;
            my $disk_name = $device->diskName;
            if ($disk_name eq $wwn_serial) {
                @device_paths = ($_->devicePath);
                $log->diag("Match found: $vmfs_label");
                $match_found = 1;
            }
        }
        if ($match_found == 0) {
            next;
        }
        #We may need to take additional actions depending on the resolve
        #state.
        my $unres_msg = "Volume $vmfs_label unresolvable: ";
        if (! $vmfs->resolveStatus->resolvable) {
            if ($vmfs->resolveStatus->incompleteExtents) {
                $log->error($unres_msg . " extents are missing.");
            } elsif ($vmfs->resolveStatus->multipleCopies) {
                $log->warn($unres_msg . " duplicate extents found");
                #In this case detach all the extents but the one that we are
                #trying to mount.
            } elsif (scalar(@$extents) > 1) {
                $log->warn($unres_msg . " extra extents found");
            } else {
                $log->error($unres_msg . " Unknown error");
            }
            #Detach all devices other than the one that is being mounted
            if (scalar(@$extents) > 1) {
                $log->note("Proceeding to detach cloned luns except $wwn_serial");
                foreach (@$extents) {
                    my $disk_name = $_->device->diskName;
                    if ($disk_name ne $wwn_serial) {
                        eval {
                            lookup_and_detach_device($disk_name, $storage_sys);
                        };
                        if ($@) {
                            $log->note("Detaching device $disk_name failed");
                        }
                    }
                }
            }
        } else {
            $log->diag("Volume $vmfs_label is resolvable");
        }
        $log->diag("Force mounting unresolved: $vmfs_label");
        my $res_spec = new HostUnresolvedVmfsResolutionSpec();
        $res_spec->{"extentDevicePath"} = \@device_paths;
        $res_spec->{"uuidResolution"} = "forceMount";
        my $i = 0;
        for ($i = 0; $i < 2; ++$i) {
            eval {
                $storage_sys->ResolveMultipleUnresolvedVmfsVolumes(resolutionSpec => ($res_spec));
                $log->info("Successfully mounted VMFS $vmfs_label!");
            };
            if ($@) {
                $log->info("Resolve unresolved volumes failed: $vmfs_label: $@");
            } else {
                my $datastore = locate_unique_datastore_for_lun($wwn_serial,
                                                                $datacenter,
                                                                $host,
                                                                $storage_sys);
                if (defined ($datastore)) {
                    $log->info("Successfully located the datastore");
                    return $datastore;
                } else {
                    $log->note("Unable to lookup datastore after resolving volume");
                }
            }
        }
        last;
    }
}

sub serial_match_scsi_lun {
    my ($storage, $lun_serial, $log) = @_;
    my @lun_serials = ($lun_serial);
    my $serial_scsi_lun = serial_match_scsi_luns($storage, \@lun_serials,
                                                 $log);
    return $serial_scsi_lun->{$lun_serial};
}

sub serial_match_scsi_luns {
    my ($storage, $lun_serials, $log) = @_;
    #Here the lun serial could be in ASCII (netapp) or naa id decmial string
    #form(EMC). We try and match for several variants
    my $lun_serial_variants;
    foreach (@$lun_serials) {
        my $lun_serial = $_;
        $lun_serial_variants->{$lun_serial} = $lun_serial;
        $lun_serial_variants->{ascii_to_dec_str($lun_serial)} = $lun_serial;
        $lun_serial_variants->{"naa." . lc($lun_serial)} = $lun_serial;
    }
    for (keys %$lun_serial_variants) {
        $log->debug("Looking for serial num: $_");
    }
    my $scsi_luns = $storage->storageDeviceInfo->scsiLun;
    my %serial_scsi_hash = ();
    foreach (@$scsi_luns) {
        my $scsi_device = $_;
        my $serial = get_scsi_serial($scsi_device);
        my $wwn_serial = lc($scsi_device->canonicalName);
        $log->debug("LUNS: $serial...$wwn_serial");
        my $matching_key;
        if ($lun_serial_variants->{$serial}) {
            $matching_key = $serial;
        } elsif ($lun_serial_variants->{$wwn_serial}) {
            $matching_key = $wwn_serial;
        }
        if (defined($matching_key)) {
            my $incoming_serial = $lun_serial_variants->{$matching_key};
            # Save the match against the incoming scsi device
            $serial_scsi_hash{$incoming_serial} = $scsi_device;
            $log->info("Using lun with name $wwn_serial on Proxy host " .
                       "for proxy backup operation");

            #Check if we can wrap
            if (keys(%serial_scsi_hash) == scalar(@$lun_serials)) {
                $log->diag("All luns lookedup");
                last;
            }
        }
    }
    return \%serial_scsi_hash;
}

sub should_exclude_vm {
    my ($vm_name, $acs_include_filter, $acs_exclude_filter,
        $include_filter, $exclude_filter) = @_;
    # Check if the VM has to be skipped. The order is like this:
    #  - First apply acs exclude filter
    #  - then apply acs include filter
    #  This will give you VMs which were snapshotted at the branch.
    #  Then apply 
    #  - exclude filter for proxy_backup
    #  - include filter for proxy_backup
    return (apply_filter($vm_name, $acs_exclude_filter) ||
            !(apply_filter($vm_name, $acs_include_filter)) ||
            apply_filter($vm_name, $exclude_filter) ||
            !(apply_filter($vm_name, $include_filter)));
}

sub handle_no_vmx_datastores {
    my ($ds, $datacenter, $host, $skip_vm_registration,
        $acs_include_filter, $acs_exclude_filter,
        $include_filter, $exclude_filter, $vm_name_prefix) = @_;
    my $log = LogHandle->new("handle_no_vmx_datastores");

    if ($skip_vm_registration == 0) {
        # Nothing to do
        return;
    }

    # Check if there are any VMs that have disks belonging to
    # this datastore. If there are, check if they should be
    # excluded. If not, then check if we are skipping
    # registration. If we are, then we must delete the
    # snapshot delta, vmdk and ctk files for the disks
    # that belong to this datastore and are attached to that VM.
    if (!defined($ds->vm)) {
	$log->info("No VMs found on this datastore yet");
	return;
    }

    foreach (@{$ds->vm}) {
        my $vm = Vim::get_view(mo_ref => $_);
        my $vm_name = $vm->name;
        if (should_exclude_vm($vm_name, $acs_include_filter,
                              $acs_exclude_filter,
                              $include_filter, $exclude_filter)) {
            $log->info("Skipping VM: $vm_name as specified by regex");
            next;
        }
        $log->diag("Processing VM: $vm_name as specified by regex");
        
        # Remove the snapshot files for the VM as it is
        # required for incremental backups to work
        eval {
            fix_vm($vm, $datacenter, 0, $skip_vm_registration);
        };
        if ($@) {
            die "Error while fixing the config file for VM $vm_name: $@";
        }
        if ($skip_vm_registration == 1) {
            eval {
                $vm->Reload();
            };
            if ($@) {
                $log->error("Error while reloading VM $vm_name: $@");
            }
        }
    }
}

sub prepare_vms_for_backup {
    my ($ds, $datacenter, $host, $skip_vm_registration,
        $acs_include_filter, $acs_exclude_filter,
        $include_filter, $exclude_filter, $vm_name_prefix) = @_;
    my $log = LogHandle->new("prepare_vms");
    #Browse the VMs and collect vmx paths.
    my $vmx_paths = get_vmx_paths($ds);
    my $error_preparing_vms = 0;
    my $no_of_vms_registered = 0;
    my @vms;

    # if we don't have any VMX files on this datastore, this may be serving
    # as a D drive for the VM.
    if (!defined($vmx_paths) || scalar(@$vmx_paths) == 0) {
        $log->info("No VMs to register for this datastore");
        handle_no_vmx_datastores($ds, $datacenter, $host, $skip_vm_registration,
        $acs_include_filter, $acs_exclude_filter,
        $include_filter, $exclude_filter, $vm_name_prefix);
        return;
    }

    foreach (@$vmx_paths) {
        my $vm;
        my $vm_name;
        $log->debug("Located VMX: $_" );
        my $skipped = 0;
        if ($skip_vm_registration == 0) {
            eval {
                $vm = register_vm($_, $datacenter, $host, $ds);
            };
            if ($@) {
                $log->error("Error while registering VM: $_: $@");
                $error_preparing_vms = 1;
                next;
            }
        } else {
            # For Veeam, we basically wait for ESXi to automatically
            # register the VM for us. We do not register the VM
            $log->info("Getting the VM ref without registering for: $_");
            $vm = get_vm_ref($_, $ds, 4);
            # This is possible the first time we run VADP with Veeam
            # for this lun. We need to register the VM if we cannot find one.
            if (! defined($vm)) {
                eval {
                    $vm = register_vm($_, $datacenter, $host, $ds);
                };
                if ($@) {
                    $log->error("Error while registering VM: $_: $@");
                    $error_preparing_vms = 1;
                    next;
                }
            }
        }
        if (! defined($vm)) {
            $log->error("Could not find VM with path $_");
            next;
        }
        $vm_name = $vm->name;
        # Check if the VM has to be skipped
        if (should_exclude_vm($vm_name, $acs_include_filter,
                              $acs_exclude_filter,
                              $include_filter, $exclude_filter)) {
            $log->info("Skipping VM: $vm_name as specified by regex");
            $skipped = 1;
            #Unregister
            eval {
                unregister_vm($vm);
            };
            if ($@) {
                #Log error and continue;
                $log->error("Error while unregistering VM $vm_name: $@");
                # Not logging an error because we may have registered
                # extra vms than necessary, but that is ok
            }
            next;
        }
        my $new_vm_name;
        eval {
            $new_vm_name = rename_vm_name($vm, $vm_name_prefix, $log);
        };
        if ($@) {
            die "Error while renaming the snapshot for VM $vm_name: $@";
        }
        eval {
            fix_vm($vm, $datacenter, 0, $skip_vm_registration);
        };
        if ($@) {
            die "Error while fixing the snapshot for VM $vm_name: $@";
        }
        if ($skip_vm_registration == 1) {
            eval {
                $vm->Reload();
            };
            if ($@) {
                $log->error("Error while reloading VM $vm_name: $@");
            }
        }
        $log->info("Successfully registered VM $new_vm_name");
        ++$no_of_vms_registered;
    }

    if ($error_preparing_vms != 0) {
        die "Failed to properly register all vms";
    }

    if ($no_of_vms_registered == 0) {
        die "Failed to register even a single VM properly, probably " . 
            "the include/exclude regex for ACS and Proxy Backup ends up excluding all VMs"
    }
}

sub get_vmx_paths {
    my ($ds) = shift;
    my $ds_browser = Vim::get_view(mo_ref => $ds->browser);
    my $log = LogHandle->new("get_vmx_paths");
            
    #For each of vmx paths collected register the VM.
    my $browse_task;
    eval {
        $browse_task = $ds_browser->SearchDatastoreSubFolders(datastorePath => '[' . $ds->summary->name . ']');
    };
    if ($@) {
        if (ref($@) eq 'SoapFault') {
            if (ref($@->detail) eq 'FileNotFound') {
                $log->error("The folder specified by "
                             . "datastorePath is not found");
            } elsif (ref($@->detail) eq 'InvalidDatastore') {
                $log->error("Operation cannot be performed on the target datastores");
            } else {
                $log->error("Error: $@");
            }
        } else {
            $log->error("Generic error: $@");
        }
        die $@;
    }
    my $vmx_files;
    foreach(@$browse_task) {
        if(defined $_->file) {
            foreach my $x (@{$_->file}) {
                my $ext = (fileparse($x->path, qr/\.[^.]*/))[2];
                if ($ext eq ".vmx") {
                    push (@$vmx_files, $_->folderPath . "/" . $x->path);
                }
            }
        }
    }
    return $vmx_files;
}

sub get_vm_ref {
    my ($vmxpath, $datastore, $no_of_tries) = @_;

    while($no_of_tries-- > 0) {
        # ESXi takes time before it registers the VM. So sleep a bit
        # before querying for VMs
        sleep(10);
        $datastore->update_view_data();
        my $vms_on_ds = $datastore->vm;
        my $log = LogHandle->new("get_vm_ref");

        if (!defined(@$vms_on_ds)) {
            $log->info("No VMs on this datastore!!!");
            next;
        }

        foreach (@$vms_on_ds) {
            my $vm_view = Vim::get_view(mo_ref => $_);
            my $vm_name = $vm_view->name;

            $log->info("Looking for VM with path : $vmxpath");
            my $get_vm_files_tries = 3;
            while($get_vm_files_tries-- > 0) { 
                if (defined($vm_view->config) && defined($vm_view->config->files)) {
                    last;
                }
                sleep(5);
                $vm_view->update_view_data();
                $log->info("Trying to get VM files info, refreshing VM view");
            }
            if (!(defined($vm_view->config) && defined($vm_view->config->files))) {
                # data not available for this VM, go to the next VM
                next;
            }
            my $vmx_new_path = $vm_view->config->files->vmPathName;
            $log->info("VM path : $vmx_new_path");
            if ($vm_view->config->files->vmPathName eq $vmxpath) {
                return $vm_view;
            } else {
                $log->diag("VMX paths do not match, trying another VM");
            }
        }
    }
    return;
}

sub register_vm {
    my ($vmxpath, $datacenter, $host, $ds) = @_;
    if (! defined($datacenter)) {
        $datacenter = Vim::find_entity_view(view_type => 'Datacenter');
    }

    # Find the resource pools which contain the host,
    # and select the first resource pool amongst it.
    my $resource_pools = Vim::find_entity_views(view_type => 'ResourcePool',
                                                begin_entity => $host->parent,
                                                filter => {'name' => "Resources"});
    my $resource_pool = $resource_pools->[0];

    my $folder_view = Vim::get_view(mo_ref => $datacenter->vmFolder);
    my $log = LogHandle->new("register_vm");
    $log->info("vmx path for the VM is $vmxpath");
    my $vm;
    eval {
        my $task_ref = $folder_view->RegisterVM(path => $vmxpath, asTemplate => 0, pool => $resource_pool);
        $vm = Vim::get_view(mo_ref => $task_ref);
        $log->diag("Registered VM '$vmxpath' ");
    };
    if ($@) {
        if (ref($@) eq 'SoapFault') {
            if (ref($@->detail) eq 'AlreadyExists') {
                $log->note("VM $vmxpath already registered.");
                return get_vm_ref($vmxpath, $ds, 2);
            } elsif (ref($@->detail) eq 'OutOfBounds') {
                $log->error("Maximum Number of Virtual Machines has been exceeded");
            } elsif (ref($@->detail) eq 'InvalidArgument') {
                $log->error("A specified parameter was not correct.");
            } elsif (ref($@->detail) eq 'DatacenterMismatch') {
                $log->error("Datacenter Mismatch: The input arguments had entities "
                         . "that did not belong to the same datacenter.");
            } elsif (ref($@->detail) eq "InvalidDatastore") {
                $log->error("Invalid datastore path: $vmxpath");
            } elsif (ref($@->detail) eq 'NotSupported') {
                $log->error(0,"Operation is not supported");
            } elsif (ref($@->detail) eq 'InvalidState') {
                $log->error("The operation is not allowed in the current state"); 
            } else {
                $log->error("Error: $@");
            }
        } else {
            $log->error("Generic error: $@");
        }
        die $@;
    }
    return $vm;
}

sub check_if_vm_in_use {
    my $vm = shift;
    my $vm_name = $vm->name;
    my $nRefs = 0;
    my $log = LogHandle->new("check_vm_in_use");
    my $refs;
    $log->info("Checking if vm in use");
    if (defined $vm->snapshot) {
        ($refs, $nRefs) = find_snapshots($vm->snapshot->rootSnapshotList,
                                         "granite_snapshot");
    }
    if($nRefs == 0) {
        $log->info("no snapshot found if vm in use");
        return 0;
    }
    #Find if the granite snapshot has a child
    foreach (@$refs) {
        my $child_snapshots = $_->childSnapshotList;
        if (defined($child_snapshots) && scalar(@$child_snapshots) > 0) {
            $log->note("VM $vm_name has other non-SteelFusion snapshots");
            return 1;
        }
    }
    return 0;
}

sub unregister_vms {
    my ($ds, $fail_if_in_use) = @_;
    my $log = LogHandle->new("unregister_vms");
    my ($vm_views, $total_vms_count) = get_vms_on_datastore($ds);
    if ($total_vms_count == 0) {
        $log->info("No VMs to unregister");
        return;
    } 
    my $ds_name = $ds->name;
    my $other_ds_vms;
    foreach (@$vm_views) {
        my $vm = $_;
        my $vm_name = $vm->name;
        #Make a note of the VM it is hosted on some other datastore.
        my $vmx_file_path = $vm->config->files->vmPathName;
        my ($vmx_ds_name, $vmx_dirname, $vmx_filename) = split_file_path($vmx_file_path);
        if ($vmx_ds_name ne $ds_name) {
            $log->diag("VMX for $vm_name in $vmx_ds_name");
            push(@$other_ds_vms, $vmx_file_path);
        }
        #Dump changeids before cleaning up the VM
        dump_changeid_info($vm);

        #If requested, check if the VM is in use.
        if ($fail_if_in_use) {
            if (check_if_vm_in_use($vm)) {
                die "VM $vm_name is in use.";
            }
        }
        eval {
            unregister_vm($vm);
        };
        if ($@) {
            #Log error and continue;
            $log->error("Error while unregistering VM $vm_name : $@");
        }
    }
    return $other_ds_vms;
}

sub is_safe_to_unmount {
    my ($ds, $skip_vm_registration) = @_;
    my ($vm_views, $total_vms_count) = get_vms_on_datastore($ds);
    my $ds_name = $ds->name;
    my $log = LogHandle->new("is_safe_to_unmount");
    foreach (@$vm_views) {
        my $vm = $_;
        my $vm_name = $vm->name;
        #Make a note of the VM it is hosted on some other datastore.
         my $vmx_file_path = "";
        eval {
            $vmx_file_path = $vm->config->files->vmPathName;
        };
        if ($@) {
            if ($skip_vm_registration != 0) {
                # Since we leave the VM orphaned, we are unable to get
                # the vmx file. Igore this error and return
                return;
            }
        }
        my ($vmx_ds_name, $vmx_dirname, $vmx_filename) = split_file_path($vmx_file_path);
        if ($vmx_ds_name ne $ds_name) {
            $log->diag("VMX for $vm_name in $vmx_ds_name");
        }
        #check if the VM is in use.
        if (check_if_vm_in_use($vm)) {
            die "VM $vm_name is in use.";
        }
    }
    return;
}

sub dump_changeid_info {
    my $vm = shift;
    my $log = LogHandle->new("changeid_info");
    my $snapshot_chain = $vm->snapshot;
    my $snapshot;
    if (defined($snapshot_chain) && defined($snapshot_chain->currentSnapshot)) {
        $snapshot = Vim::get_view(mo_ref => $snapshot_chain->currentSnapshot);
    } else {
        $log->info("No snapshots");
        return;
    }
    if (! defined($snapshot)) {
        $log->warn("Could not lookup current snapshot");
        return;
    }
    my $devices = $snapshot->config->hardware->device;
    $log->info("VM: ". $vm->name);
    foreach (@$devices) {
        my $device = $_;
        my $device_id = $device->key;
        if (ref($device) eq "VirtualDisk") {
            $log->info("Disk: " . $device_id . ", ChangeId: ".
                       $device->backing->changeId);
        }
    }
}

sub lookup_and_detach_device {
    my ($lun_serial, $storage_sys) = @_;
    $lun_serial = lc($lun_serial);
    if (index($lun_serial, "naa.") == -1) {
        $lun_serial = "naa." . $lun_serial;
    }
    my $log = LogHandle->new("detach");
    $log->diag("Looking to detach $lun_serial");
    my $devices = eval{$storage_sys->storageDeviceInfo->scsiLun || []};
    if (scalar(@$devices) == 0) {
        $log->warn("No devices found");
    }
    foreach my $device (@$devices) {
        if($device->canonicalName eq $lun_serial) {
            detach_device($storage_sys, $device, $log);
            last;
        }
    }
}

sub detach_device {
    my ($storage_sys, $device, $log) = @_;
    my $lunUuid = $device->uuid;
    my $lun_serial = $device->canonicalName;
    $log->diag("Detaching LUN \"$lun_serial\"");
    eval {
        $storage_sys->DetachScsiLun(lunUuid => $lunUuid);
    };
    if($@) {
        my $detach_err = 1;
        if (ref($@) eq 'SoapFault') {
            if(ref($@->detail) eq 'InvalidState') {
                $log->note("Device is already detached $lun_serial");
                $detach_err = 0;
            } elsif(ref($@->detail) eq 'NotFound') {
                $log->note("Could not find the device : $lun_serial");
                $detach_err = 0;
            }
        } 
        if ($detach_err) {
            $log->error("Unable to detach LUN $@");
            die $@;
        }
    } else {
        $log->info("Successfully detached LUN $lun_serial");
    }
    #Now remove the device from ESXi
    eval {
        $storage_sys->DeleteScsiLunState(lunCanonicalName => $lun_serial);
    };
    if($@) {
        $log->error("Unable to delete lunstate " . $@);
    } else {
        $log->diag("Successfully deleted lunstate for $lun_serial");
    }
}

sub umount_and_detach {
    my ($ds, $skip_vm_registration) = @_;
    my $ds_name = $ds->name;
    my $disk_name = $ds->info->vmfs->extent->[0]->diskName;
    my $log = LogHandle->new("umount_and_detach");
    if(! $ds->host) {
        $log->error("Host entry not present");
        return;
    }
    my $attached_hosts = $ds->host;
    my $num_hosts = scalar(@$attached_hosts);
    if ($num_hosts == 0) {
        $log->note("No hosts are attached to the datastore: $ds_name");
        return;
    } elsif($num_hosts > 1) {
        $log->error("More than one hosts are attached to the datastore
                     $ds_name: $num_hosts");
        die;
    }
    my $host = $attached_hosts->[0];
    my $hostView = Vim::get_view(mo_ref => $host->key, properties => ['name','configManager.storageSystem']);
    my $storageSys = Vim::get_view(mo_ref => $hostView->{'configManager.storageSystem'});
    $log->debug("Unmounting VMFS Datastore $ds_name from Host ".  $hostView->{'name'});
    if ($skip_vm_registration) {
        eval {
            $storageSys->UnmountForceMountedVmfsVolume(vmfsUuid => $ds->info->vmfs->uuid);
        };
    } else {
        eval {
            $storageSys->UnmountVmfsVolume(vmfsUuid => $ds->info->vmfs->uuid);
        };
    }
    if($@) {
        if (ref($@) eq 'SoapFault') {
            if(ref($@->detail) eq 'InvalidState') {
                $log->note("Device is already unmounted");
            } elsif(ref($@->detail) eq 'NotFoundFault') {
                $log->note("Could not find datastore, probably it is already unmounted");
            } else {
	        die $@;
            }
        } else {
            $log->error("Unable to unmount VMFS datastore $ds_name: " . $@);
            die $@;
        }
    } else {
        $log->info("Successfully unmounted VMFS datastore $ds_name");
    }
    detach_lun($disk_name, $storageSys);
}

sub detach_lun {
    my ($lun_serial, $storageSys) = @_;
    my $log = LogHandle->new("detach_lun");
    lookup_and_detach_device($lun_serial, $storageSys);

    #Scan the hbas to clear the vmfs volume from vcenter/esxi's view
    my $scan_hbas = get_hbas_to_be_scanned($storageSys->storageDeviceInfo);
    foreach (@$scan_hbas) {
        my $hba = $_;
        $log->debug("Scanning hba $hba");
        eval {
            $storageSys->RescanHba(hbaDevice => $hba);
        };
        if ($@) {
            $log->warn("Scan HBA failed for $hba: ". $@);
        }
    }
}

sub get_wwn_names {
    my ($luns, $host_list) = @_;
    my $log = LogHandle->new("get_wwn_names");
    my %serial_wwn_hash = ();
    my $lun_cnt = scalar(@$luns);
    if ($lun_cnt == 0) {
        return \%serial_wwn_hash;
    }
    #Build the list walking through all the hosts under the datacenter
    foreach (@$host_list) {
        my $host = $_;
        my $storage = Vim::get_view(mo_ref => $host->configManager->storageSystem);
        my $dstore_sys = Vim::get_view(mo_ref => $host->configManager->datastoreSystem);
        
        my $serial_scsi_hash = serial_match_scsi_luns($storage, $luns, $log);
        foreach (keys(%$serial_scsi_hash)) {
            my $scsi_device = $serial_scsi_hash->{$_};
            $log->debug("MATCH: $_ -> ". $scsi_device->canonicalName);
            my @wwn_hash_val = ($scsi_device->canonicalName, $host);
            $serial_wwn_hash{$_} = \@wwn_hash_val;
        }
    }
    return \%serial_wwn_hash;
}

sub get_hbas_to_be_scanned {
    my $storage_device = shift;
    my $all_hbas = $storage_device->hostBusAdapter;
    my $selected_hbas;
    my $log = LogHandle->new("select_hbas");
    foreach (@$all_hbas) {
        my $hba = $_;
        my $hba_type = ref($hba);
        if ($hba_type eq "HostInternetScsiHba" || $hba_type eq "HostFibreChannelHba") {
            my $hba_name = $hba->device;
            $log->diag("Selecting $hba_name of type $hba_type");
            push(@$selected_hbas, $hba_name);
        }
    }
    return $selected_hbas;
}

sub get_host_list {
    my ($datacenter, $include_filter, $exclude_filter) = @_;
    my $host_list;
    my $log = LogHandle->new("get_host_list");
    if (defined($datacenter)) {
        $host_list = Vim::find_entity_views(view_type => 'HostSystem',
                                            begin_entity => $datacenter);
    } else {
        $host_list = Vim::find_entity_views(view_type => 'HostSystem');
    }
    if (! defined ($include_filter)) {
        $include_filter = ".*";
    }
    if (! defined ($exclude_filter)) {
        $exclude_filter = "";
    }
    #Now apply the filter
    my @filtered_hosts;
    foreach (@$host_list) {
        my $host = $_;
        my $host_name = $host->name;
        if (! apply_filter($host_name, $exclude_filter)) {
            if (apply_filter($host_name, $include_filter)) {
                push (@filtered_hosts, $host);
            } else {
                $log->diag("Skipping host (include_filter): $host_name");
            }
        } else {
            $log->diag("Skipping host (exclude_filter): $host_name");
        }
    }
    return \@filtered_hosts;
}

sub get_host {
    my ($datacenter, $include_hosts, $exclude_hosts) = @_;
    my $log = LogHandle->new("get_host");
    my $host_list = get_host_list($datacenter, $include_hosts, $exclude_hosts);
    if (scalar(@$host_list) == 0) {
        $log->warn("Unable to locate ESXi Hosts");
        die "Unable to locate ESXi hosts";
    }
    #Just pick the first host
    return $host_list->[0];
}

sub rename_vm_name {
    my ($vm, $vm_name_prefix, $log) = @_;
    if ($vm_name_prefix eq "") {
        return;
    }
    my $vm_name = $vm->name;
    my $new_name = $vm_name_prefix . $vm_name;
    my $config_spec = VirtualMachineConfigSpec->
                              new(name => $new_name );

    eval {
        $vm->ReconfigVM(spec => $config_spec);
    };
    if ($@) {
        $log->error("Error while renaming display name name for $vm_name: $@");
        die $@;
    }
    return $new_name;
}

sub locate_unique_datastore_for_lun {
    my ($lun, $datacenter, $host, $storage) = @_;
    my $log = LogHandle->new("locate_unique_datastore_for_lun");

    $log->diag("Trying to get data store for $lun");
    my $retry_count = 0;
    my $ds_name = '';
    my @luns_with_dup_datastores = ();
    my $data_store;
    my $rescanned_vmfs = 0;
    while ($retry_count++ < 5) {
        my $datastores;
        
        if (defined ($datacenter)) {
            $datastores = Vim::find_entity_views(view_type => 'Datastore', 
                                                 begin_entity => $datacenter);
        } else {
            $datastores = Vim::find_entity_views(view_type => 'Datastore');
        }

        # Clear out the dups from last iteration
        @luns_with_dup_datastores = ();
        $ds_name = "";
        undef($data_store);
        foreach (@$datastores) {
            my $ds = $_;
            my $lun_serial = datastore_lun_serial($ds);
            #Some datastores need not be on iscsi luns and such will be ignored.
            if (defined($lun_serial) and ($lun_serial eq $lun)) {
                $ds_name = $ds->name;
                $log->info("Datastore $ds_name for $lun is the one that matches");
                $data_store = $ds;
            }
        }

        if (defined($data_store)) {
            foreach (@$datastores) {
                my $ds = $_;
                if ($ds->name eq $data_store->name and ($ds != $data_store)) {
                    $log->info("Datastore $ds_name exists on another lun");
                    push(@luns_with_dup_datastores, $ds);
                }
            }
        } else {
            $log->info("Could not find the datastore for $lun, ".
                       "rescanning again...");
            if ($rescanned_vmfs) {
                # We rescanned the vmfs previously and even
                # then could not find the datastore. No need
                # to try anymore since the datastore may be
                # in list of unresolved volumes.
                $log->info("Could not find the datastore for $lun, ".
                          "probably it is an unresolved volume");
                return;
            }
            #Rescan for VMFS volumes to pickup the datastore
            eval {
                $storage->RescanVmfs();
                $rescanned_vmfs = 1;
            };
            if ($@) {
                $log->warn("Rescan VMFS volumes failed " . $@);
                #proceed forward.
            }
            next;
        }

        my $dup_ds_size = @luns_with_dup_datastores;
        $log->info("Size of dup list : $dup_ds_size");
        # Check for duplicates
        if($dup_ds_size >= 1) {
            if (! defined ($datacenter)) {
                $log->info("Duplicate datastores found");
                # Try to un-mount the duplicate data stores.
                # We try to un-mount duplicate data stores only
                # for standalone ESXi hosts. This is because if it
                # is managed through a vCenter, vCenter seems to
                # automatically rename duplicate datastores.
                cleanup_duplicate_datastores(\@luns_with_dup_datastores,
                                             $ds_name,
                                             $datacenter, $host);
            } else {
                # vCenter renames the duplicate datastore names
                # appropriately
                $log->info("Found datastore on more than one lun, ".
                           "rescanning and waiting for renaming the datastore");
            }
            sleep(20);
            next;
        } else {
            $log->info("Found datastore $ds_name successfully for $lun");
            return $data_store
        }
    }

    my $dup_ds_size = @luns_with_dup_datastores;
    if ($dup_ds_size > 1) {
        $log->error("Another datastore exits with the same name $ds_name ".
                    "as that on the cloned lun $lun");
    }
    return;
}

sub cleanup_datastore {
    my ($datastore, $fail_if_backup_in_progress, $force_unmount,
        $datacenter, $host, $skip_vm_registration) = @_;
    my $unmount_fail = 0;
    my $unregister_failed = 0;
    my $other_ds_vms;

    my $log = LogHandle->new("cleanup_datastore");

    if ($skip_vm_registration == 0) {
        eval {
            $other_ds_vms = unregister_vms($datastore,
                                           $fail_if_backup_in_progress);
        };
        if ($@) {
            $log->error("Failed to unregister the VMs, " .
                        "backup possibly in progress?");
            $unregister_failed = 1;
        }
    } else {
        eval {
            is_safe_to_unmount($datastore, $skip_vm_registration);
        };
        if ($@) {
            $log->error("Unsafe to unmount the datastore: $@");
            if ($fail_if_backup_in_progress) {
                die "Failed to cleanup the datastore";
            }
        }
    }

    if (! $unregister_failed or $force_unmount) {
        # Unmount the lun after removing the datastore
        eval {
            umount_and_detach($datastore, $skip_vm_registration);
        };
        if ($@) {
            $log->error("Unmount failure for $_: " . $datastore->name);
            $unmount_fail = 1;
        }
    }

    if ($unregister_failed == 0) {
        #Re-register VMs from other datastores after the unmount is complete.
        foreach (@$other_ds_vms) {
            my $vmx_path = $_;
            $log->info("Re-registering VM $vmx_path");
            register_vm($vmx_path, $datacenter, $host, $datastore);
        }
    }

    if ($unmount_fail or $unregister_failed) {
        $log->error("Failed to cleanup the datastore");
        die $@;
    }
}

sub cleanup_duplicate_datastores {

    my ($datastores, $ds_name, $datacenter, $host) = @_;
    my $cleanup_fail = 0;
    my $log = LogHandle->new("cleanup_duplicate_datastores");

    $log->info("Cleaning up datastore with name $ds_name");

    foreach (@$datastores) {
        my $ds =  $_;
        eval {
            cleanup_datastore($ds, 0, 1, $datacenter, $host, 0);
        };
        if ($@) {
            $cleanup_fail = 1;
        }
    }

    if ($cleanup_fail) {
        die "Failed to unregister the VM and remove the datastore $ds_name";
    }
}

