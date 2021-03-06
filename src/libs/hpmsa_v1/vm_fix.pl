####
# (C) Copyright 2003-2013 Riverbed Technology, Inc.
# All rights reserved. Confidential.
#
####

use strict;
use warnings;
use Cwd qw(abs_path);
use File::Basename qw(dirname);
use lib dirname(abs_path(__FILE__)).'/';
use POSIX;

require "vm_common.pl";
require "snapshot_helper.pl";

use File::Temp qw/ tempfile tempdir /;
# VMX temp file location
use constant VMX_TMP => 'C:\\rvbd_handoff_scripts\\var';

sub fix_vm {
    my ($vm, $datacenter, $no_overwrite, $skip_vm_registration) = @_;
    my $vm_name = $vm->name;
    my $dc_name;
    if (defined($datacenter)) {
        $dc_name = $datacenter->name;
    }
    my $log = LogHandle->new("fix_vm");

    my $disk_snaps;
    eval {
    	$disk_snaps = get_latest_disk_snaps($vm);
    };
    if ($@) {
        if ($skip_vm_registration) {
            $log->info("VM information not yet available, skipping the VM");
            return;
        }
        # For regular VADP we must always have the snapshot
        # information available.
        die $@;
    }
    if (! defined($disk_snaps)) {
        $log->debug("No snapshots for VM: $vm_name, nothing more to be done");
        return;
    }
    for (keys %$disk_snaps) {
        $log->debug("disk_snaps: $_ : " . $disk_snaps->{$_});
    }

    my $disk_ids = get_current_disks($vm);
    for (keys %$disk_ids) {
        $log->debug("disk_ids: $_ : " . $disk_ids->{$_}[0]);
    }

    #Fetch the vmx file from the esxi
    my ($ds_name, $vm_dir, $vmx_filename) = get_vmx_file_info($vm);
    my $remote_vmx_path = "$vm_dir/$vmx_filename";
    my $tmpfile_dir = VMX_TMP;
    my $tmpfile_template = "$vmx_filename". "XXXXX";
    my ($discard, $vmx_file) = tempfile($tmpfile_template,
                                        DIR => $tmpfile_dir,
                                        SUFFIX => '.vmx' );
    my $fixed_vmx_file = $vmx_file . ".fixed";

    #Obtain the vmx file from the esxi
    eval {
        get_file($ds_name, $remote_vmx_path, $vmx_file, $dc_name);
    };
    if ($@) {
        $log->error("Unable to obtain the vmx file $vmx_file: $@");
        die $@;
    }
    $log->diag("Obtained the vmx file $remote_vmx_path at $vmx_file");
    # Start parsing the vmx file and substitute the disks
    open (in_fh, "<$vmx_file") or die "cannot open $vmx_file";
    open (out_fh, "+>$fixed_vmx_file") or die "cannot open $fixed_vmx_file";
    print out_fh "#Updated by Riverbed Granite at: ". strftime '%Y-%m-%d %H:%M:%S', localtime $^T;
    print out_fh "\n";

    my $do_not_delete_snap = 0;
    while (<in_fh>) {
        chomp;
        my $line = $_;
        #XXX REGEX
        my $scsi_idx = index($line, "scsi0:");
        if ($scsi_idx != -1) {
            my $locate_str = "\.fileName = \"";
            my $fpath_idx = index($line, $locate_str);
            if ($fpath_idx != -1) {
                #XXX Fix to use REGEX
                $fpath_idx += length($locate_str);
                my $file_path = substr($line, $fpath_idx,
                                       length($line) - ($fpath_idx + 1));
		my $dir_path = "";
                my $fname = $file_path;
                my $fname_idx = rindex($file_path, "/");
                if ($fname_idx != -1) {
                    $fname = substr($file_path, $fname_idx + 1);
                    $dir_path = substr($file_path, 0, $fname_idx) . "/";
                }
                my $fixed_fname = $dir_path . $fname;
                # Check if the disk is present in the disk id list,
                if (defined $disk_ids->{$fname}) {
                    my $disk_id = $disk_ids->{$fname}[0];
                    my $disk_ds_name = $disk_ids->{$fname}[1];
                    my $disk_dir_name = $disk_ids->{$fname}[2];
                    # Determine the new name
                    if ($disk_snaps->{$disk_id}) {
                	$log->debug("Fixed filename : " . $fname);
                        $fixed_fname = $dir_path . $disk_snaps->{$disk_id};
                        #Update the line to include the snapshot disk name
                        my $updated_line = substr($line, 0, $fpath_idx) .
                                                    $fixed_fname . "\"";
                        $log->diag("Updating disk name:$line -> $updated_line");
                        $line = $updated_line;
                        # Delete the delta and all the related files
    		        if ($skip_vm_registration &&
                           ($fname ne $disk_snaps->{$disk_id})) {
                                remove_snapshot_files($disk_ds_name,
                                                      $disk_dir_name, $fname,
                                                      $datacenter);
                        }
                    }
                } else {
                    $log->debug("Disk $fname is not present in the list");
                    $do_not_delete_snap = 1;
                }
            }
        }
        print out_fh "$line\n";
    }
    close(out_fh);
    $log->debug("Fixed vmx file at $fixed_vmx_file");
    #Now upload the file to ESXi. Do not overwrite the vmx file if explicitly
    #requested
    my $dest_file = $remote_vmx_path;
    if (defined($no_overwrite) && $no_overwrite == 1) {
        $dest_file = $remote_vmx_path . ".fixed";
    }
    $log->diag("Pushing the file $dest_file");
    #Send both the original and the fixed vmx files
    eval {
        put_file($ds_name, $vmx_file, $remote_vmx_path . ".orig", $dc_name);
        put_file($ds_name, $fixed_vmx_file, $dest_file, $dc_name);
    };
    if ($@) {
        $log->error("Unable to upload modified vmx file: $@");
        die $@;
    }
    #remove temp files
    unlink($fixed_vmx_file);
    unlink($vmx_file);

    # remove the snapshot
    if ($skip_vm_registration && ($do_not_delete_snap == 0)) {
    	cleanup_vm_snapshot($vm, "granite_snapshot", 1);
    }
}

sub remove_snapshot_files {
    my ($disk_ds_name, $disk_dir_name, $fname, $datacenter) = @_;
    my $log = LogHandle->new("remove_snapshot_files");
    my $path_prefix = "[" . $disk_ds_name . "] " . $disk_dir_name . "/";
    my $vmdk_to_remove = $path_prefix .  $fname;
    (my $delta_to_remove = $vmdk_to_remove) =~ s/.vmdk/-delta.vmdk/ ;
    (my $ctk_to_remove = $vmdk_to_remove) =~ s/.vmdk/-ctk.vmdk/ ;
    # Delete the delta and all the related files
    $log->info("Removing files: $vmdk_to_remove $ctk_to_remove and $delta_to_remove ");
    my $fm = Vim::get_view(mo_ref => Vim::get_service_content()->fileManager);
    eval {
        $fm->DeleteDatastoreFile(name => $vmdk_to_remove,
                                 datacenter => $datacenter);
        $fm->DeleteDatastoreFile(name => $ctk_to_remove,
                                 datacenter => $datacenter);
        $fm->DeleteDatastoreFile(name => $delta_to_remove,
                                 datacenter => $datacenter);
    };
    if($@) {
        die "Failed to delete file: ".($@->fault_string);
    }
}

sub get_current_disks {
    my $vm = shift;
    my $files = $vm->layoutEx->file;
    my $log = LogHandle->new("current_disks");
    my %disk_id_hash = ();
    foreach (@{$vm->layoutEx->disk}) {
        my $disk = $_;
        my $id = $disk->key;
        # Determine the latest name of the disk
        my $chain = $disk->chain;
        my $top_vmdk = $chain->[-1];
        eval {
            my $filekeys = $top_vmdk->fileKey;
            my $vmdk_desc_id = $filekeys->[0];
            $log->debug("VMDK descriptor_id: $vmdk_desc_id");
            my $filepath = $files->[$vmdk_desc_id]->name;
            $log->debug("VMDK descriptor for $id: $filepath");
            my ($ds_name, $dirname, $filename) = split_file_path($filepath);
            $log->diag("DS: $ds_name, Directory: $dirname, " .
                       "Filename: $filename");
            my @disk_info = ($id, $ds_name, $dirname, $filename);
            $disk_id_hash{$filename} = \@disk_info;
        };
        if ($@) {
            $log->note("Failed to find information for disk with $id : $@");
            $log->note("This may be because the disk may exist on a ".
                       "datastore on another lun. Please ensure that ".
                       "all luns who have datastores which host disks ".
                       "belonging to that same VM have same Proxy Backup ".
                       "setting for successful backup");
            next;
        }
    }

    if (keys(%disk_id_hash) == 0) {
        # Could not find any disk associated with this VM
        # Fail the snapshot since this is not normal
        my $vm_name = $vm->name;
        die "Failed to find any disk associated with the vm $vm_name";
    }

    return \%disk_id_hash;
}

#Returns a hash map of disk id to disk descriptor name of the latest snapshot
#that was taken.
sub get_latest_disk_snaps {
    my $vm = shift;
    my $files = $vm->layoutEx->file;
    my $log = LogHandle->new("latest_snap");
    my %disk_snapshot_hash = ();
    my $snapshots = $vm->layoutEx->snapshot;
    my $num_snapshots = 0;
    if (defined($snapshots)) {
        $num_snapshots = scalar(@$snapshots);
    }
    if ($num_snapshots == 0) {
        $log->info("No snapshots present for ". $vm->name);
        return;
    }
    my $latest_snapshot = $snapshots->[-1];
    foreach (@{$latest_snapshot->disk} ) {
        my $disk = $_;
        my $id = $disk->key;
        # Determine the latest name of the disk
        my $chain = $disk->chain;
        my $top_vmdk = $chain->[-1];
        my $filekeys = $top_vmdk->fileKey;
        my $vmdk_desc_id = $filekeys->[0];
        $log->diag("VMDK descriptor_id: $vmdk_desc_id");
        my $filepath = $files->[$vmdk_desc_id]->name;
        $log->diag("VMDK descriptor for $id: $filepath");
        my ($ds_name, $dirname, $filename) = split_file_path($filepath);
        $log->diag("DS: $ds_name, Directory: $dirname, Filename: $filename");
        $disk_snapshot_hash{$id} = $filename;
    }
    return \%disk_snapshot_hash;
}

# The file names within the vmx have datastore name as follows:
# [<ds_name>] <vm_dir>/<filepath>
# This function splits this and returns each of them
sub split_file_path {
    my ($filepath) = @_;
    #XXX use regex
    # my $fname_regex = ".* .*/.*";
    my $ds_idx = index($filepath, "] ");
    my $ds_name = substr($filepath, 1, $ds_idx - 1);

    my $fname_idx = rindex($filepath, "/");
    my $fname = substr($filepath, $fname_idx + 1);

    my $dirname = substr($filepath, $ds_idx + 2, $fname_idx - ($ds_idx + 2));
    return ($ds_name, $dirname, $fname);
}

#Return the vmx file path
sub get_vmx_file_info {
    my $vm = shift;
    my $files = $vm->layoutEx->file;
    foreach (@$files) {
        my $name = $_->name;
        if (index($name, ".vmx") != -1) {
            my ($ds_name, $dir, $fname) = split_file_path($name);
            return ($ds_name, $dir, $fname);
        }
    }
    die "Unable to locate the vmx file";
}
