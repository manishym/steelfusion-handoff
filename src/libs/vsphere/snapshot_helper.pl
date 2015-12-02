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

sub create_vm_snapshot {
    my ($vm, $quiesce, $retry_wo_quiesce) = @_;
    my $vm_name = $vm->name;
    my $snapshot_name = "granite_snapshot";
    my $log = LogHandle->new("create_vm_snapshot");
    my $num_attempts = 1;

    #Check if the user has requested to retry wo quiesce if the snapshot
    #failures occur because of quiescing related failuresj
    if ($retry_wo_quiesce and $quiesce == 1) {
        $num_attempts = 2;
    }

    #Remove previous snapshot
    cleanup_vm_snapshot($vm, $snapshot_name, 1);
    my $quiesce_vms = $quiesce;
    for (my $i = 0; $i < $num_attempts; ++$i) {
        my $description = "SteelFusion initiated non-quiesced snapshot";
        if ($quiesce_vms) {
            $description = "SteelFusion initiated quiesced snapshot";
        }
        eval {
            $log->info("Triggering snapshot for $vm_name with quiescing set to : $quiesce_vms");
            $vm->CreateSnapshot(
                             name => $snapshot_name,
                             description => $description,
                             memory => 0,
                             quiesce => $quiesce_vms);
            $log->diag("Snapshot successful for $vm_name with quiescing set to : $quiesce_vms");
        };
        if ($@) {
            if (ref($@) eq 'SoapFault') {
                if(ref($@->detail) eq 'InvalidName') {
                    $log->error("Snapshot name is invalid");
                } elsif(ref($@->detail) eq 'InvalidState') {
                    $log->error("Operation cannot be performed in the current state
                                 of the VM");
                } elsif(ref($@->detail) eq 'NotSupported') {
                    $log->error("Host product does not support snapshots.");
                    if ($quiesce_vms) {
                        $log->note("VM Snapshot failed for: $vm_name. Check if VMWare tools is installed");
                        $quiesce_vms = 0;
                        #Retry if requested
                        next;
                    }
                } elsif(ref($@->detail) eq 'InvalidPowerState') {
                    $log->error("Operation cannot be performed in the current power state
                                 of the VM.");
                } elsif(ref($@->detail) eq 'InsufficientResourcesFault') {
                    $log->error("Operation would violate a resource usage policy.");
                } elsif(ref($@->detail) eq 'HostNotConnected') {
                    $log->error("Host not connected.");
                } elsif(ref($@->detail) eq 'NotFound') {
                    $log->error("VM does not have a current snapshot");
                }  elsif(ref($@->detail) eq 'ApplicationQuiesceFault') {
                    my $quiesce_err = "Snapshot failure to AppQuiesce error";
                    $log->error($quiesce_err);
                    print STDERR $quiesce_err;
                    if ($quiesce_vms) {
                        $quiesce_vms = 0;
                        #Retry if requested
                        next;
                    }
                } else {
                    $log->error("SoapFault: " . $@ );
                }
            } else {
                $log->error("Fault: " . $@);
            }
        } else {
            return;
        }
    }
    die;
}


sub cleanup_vm_snapshot {
    my ($vm, $snapshot_name, $ignore_if_not_found) = @_;
    my $vm_name = $vm->name;
    my $nRefs = 0;
    my $log = LogHandle->new("cleanup_vm_snapshot");
    my $refs;
    if (defined $vm->snapshot) {
        ($refs, $nRefs) = find_snapshots($vm->snapshot->rootSnapshotList, $snapshot_name);
    }
    if($nRefs == 0 ) {
        if ($ignore_if_not_found == 0) {
            $log->error("Snapshot not found with name"
                        ." $snapshot_name in VM $vm_name");
            die;
        } else {
            $log->diag("Snapshot not found with name"
                        ." $snapshot_name in VM $vm_name");
            return;
        }
    }
    if ($nRefs > 1) {
        $log->warn("More than one snapshots with $snapshot_name found for $vm_name : $nRefs");
    }
    foreach (@$refs) {
        my $ref = $_;
        my $snapshot = Vim::get_view (mo_ref =>$ref->snapshot);
        eval {
            $log->diag("Removing snapshot " . $snapshot_name);
            $snapshot->RemoveSnapshot(removeChildren => 0);
            $log->diag("Operation :: Remove Snapshot ". $snapshot_name .
                            " For VM ". $vm->name 
                            ." completed successfully");
        };
        if ($@) {
            if (ref($@) eq 'SoapFault') {
               if(ref($@->detail) eq 'InvalidState') {
                  $log->error("Operation cannot be performed in the current state
                                of the VM");
               } elsif(ref($@->detail) eq 'HostNotConnected') {
                  $log->error("Host not connected.");
               } else {
                  $log->error("Fault: " . $@);
               }
            } else {
               $log->error("Fault: " . $@);
            }
            die;
        }
    }
}

#Check if CBT is enabled, if not enable for all the disks
sub cbt_check {
    my ($vm, $enable_cbt) = @_;
    my $vm_name = $vm->name;
    my $log = LogHandle->new("cbt_check");
    if (! defined($vm->capability->changeTrackingSupported) ||
            $vm->capability->changeTrackingSupported == 0)  {
        $log->warn("Change tracking not supported on VM $vm_name");
        die "Change tracking not supported for $vm_name";
    }
    #Determine the disks in the VM
    my $num_disks = scalar(@{$vm->layout->disk});

    #Check the config to see if ctk is enabled.
    my $config = $vm->config;
    my $extra_config = $config->extraConfig;
    my $ctk_enabled = 0;

    my $disk_ctk_regex = "scsi.*ctkEnabled";
    my $disks_w_ctk = 0;
    foreach (@$extra_config) {
        my $config_elem = $_;
        my $key = $config_elem->key;
        my $value = $config_elem->value;
        if ($key eq "ctkEnabled") {
            if ($value eq "true") {
                $ctk_enabled = 1;
            }
        } elsif ($key  =~ m/^$disk_ctk_regex$/) {
            $disks_w_ctk += 1;
        }
    }
    my $err_msg;
    if ($ctk_enabled == 0) {
        $log->warn("Change tracking not enabled for the VM $vm_name");
        $err_msg = "Change tracking not enabled for the VM";
    } elsif ($disks_w_ctk != $num_disks) {
        $log->warn("Change tracking not active for " . ($num_disks -
                    $disks_w_ctk) . " disks in VM $vm_name. Please check the configuration");
        $err_msg = "Change tracking not active for all the disks";
    } else {
        return;
    }
    if ($enable_cbt) {
        $log->info("Enabling CBT for $vm_name");
        my $config_spec = VirtualMachineConfigSpec->new(changeTrackingEnabled =>"true");
        eval {
            $vm->ReconfigVM(spec => $config_spec);
        };
        if ($@) {
            $log->error("Error while enabling CBT for $vm_name: $@");
            die $@;
        }
    } else {
        die $err_msg;
    }
}
