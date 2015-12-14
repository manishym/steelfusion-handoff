#!/usr/bin/perl
####
# (C) Copyright 2003-2015 Riverbed Technology, Inc.
# All rights reserved. Confidential.
#
####

use strict;
use warnings;
use File::Basename qw(dirname);
use Cwd qw(abs_path);
use lib dirname(abs_path(__FILE__));

require "vadp_helper.pl";

#Initialize logging
Logger::initialize();


my %opts = (
    'luns' => {
    type => "=s",
    help => "Serial num of luns (comma seperated) that are being cleaned up",
    required => 1,
    },
    'datacenter' => {
    type => "=s",
    help => "Datacenter under which to look for cleaning up the snapshot lun",
    default => "",
    required => 0,
    },
    'include_hosts' => {
    type => "=s",
    help => "Comma separated host names (or regex) that are to be included for proxy setup",
    default => '.*',
    required => 0,
    },
    'exclude_hosts' => {
    type => "=s",
    help => "Comma separated host names (or regex) that are to be excluded for proxy setup NOTE: This overrides include_hosts",
,
    default => '',
    required => 0,
    },
    'fail_if_backup_in_progress' => {
    type => "=i",
    help => "Cleanup is aborted if backup is in progress.",
    default => 0,
    required => 0,
    },
    'extra_logging' => {
    type => "=i",
    help => "Set to > 0 for extra logging information",
    default => 0,
    required => 0,
    },
    'skip_vm_registration' => {
    type => "=i",
    help => "Set to > 0 for extra logging information",
    default => 0,
    required => 0,
    },
    #XXX This is required as this is an extra arg and has to be common to both
    #setup and cleanup. This will go away when setup and cleanup scripts get
    #seperate extra_args
    'vm_name_prefix' => {
        type => "=s",
        help => "This will be prefixed to the VM name when it is registered on the proxy",
    ,
        default => '',
        required => 0,
    }
);


Opts::add_options(%opts);

Opts::parse();
Opts::validate();

#Remaining args
my $lunlist = trim_wspace(Opts::get_option('luns'));
my $datacenter = trim_wspace(Opts::get_option('datacenter'));
my $fail_if_backup_in_progress = Opts::get_option('fail_if_backup_in_progress');
my $include_hosts = trim_wspace(Opts::get_option('include_hosts'));
my $exclude_hosts = trim_wspace(Opts::get_option('exclude_hosts'));
my $extra_logging = int(trim_wspace(Opts::get_option('extra_logging')));
my $skip_vm_registration = int(trim_wspace(Opts::get_option('skip_vm_registration')));

my @luns = split('\s*,\s*', $lunlist);

LogHandle::set_global_params($luns[0], $extra_logging);

my $log = LogHandle->new("vadp_cleanup");

#Connect to the ESX server.
esxi_connect($log);

#Lookup datacenter
my $dc_view;
if ($datacenter ne "") {
    eval {
        $dc_view = lookup_datacenter($datacenter);
    };
    if ($@) {
        FAILURE("Error while looking up datacenter $datacenter");
    }
}

my $host_list = get_host_list($dc_view, $include_hosts, $exclude_hosts);
if (scalar(@$host_list) == 0) {
    $log->warn("Unable to locate ESXi Hosts");
    die "Unable to locate ESXi hosts";
}

#Determine the serial
my $serial_wwn_hash;
eval {
    $serial_wwn_hash = get_wwn_names(\@luns, $host_list);
};
if ($@) {
    FAILURE($@);
}
my @wwn_luns = {};
if (scalar(keys %$serial_wwn_hash) == 0) {
    $log->warn("Unable to locate the lun");
    SUCCESS();
}

for (keys %$serial_wwn_hash) {
    push(@wwn_luns, $serial_wwn_hash->{$_}[0]);
}

#Determine the datastore corresponding to the specified lun
my $lun_ds_hash = locate_datastores_for_luns(\@wwn_luns, $dc_view);
if (scalar(keys %$lun_ds_hash) == 0) {
    $log->warn("Unable to locate any datastores, proceeding to detach lun");
    # Did not find any datastore associated with the lun,
    # go ahead and detach the luns
    for (keys %$serial_wwn_hash) {
        my $host = $serial_wwn_hash->{$_}[1];
        my $hostView = Vim::get_view(mo_ref => $host->summary->host,
                        properties => ['name','configManager.storageSystem']);
        my $storageSys = Vim::get_view(mo_ref => $hostView->{'configManager.storageSystem'});
        lookup_and_detach_device($serial_wwn_hash->{$_}[0],
                                 $storageSys);
    }
    SUCCESS();
}

for (keys %$lun_ds_hash) {
    my $ds = $lun_ds_hash->{$_};
    my $ds_name = $ds->name;
    $log->debug("Located datastore $ds_name for lun $_");
}

my $umount_fail = 0;
foreach (keys %$lun_ds_hash) {
    my $datastore = $lun_ds_hash->{$_};
    eval {
        # Since we mounted the datastore only on one host,
        # we chose the first host associated with the datastore
        # to cleanup the datastore from
        cleanup_datastore($datastore, $fail_if_backup_in_progress,
                          0, $dc_view,
                          $datastore->host->[0], $skip_vm_registration);
    };
    if ($@) {
        $umount_fail = 1;
    }
}

if ($umount_fail) {
    FAILURE("Unmount of datastore failed");
}

SUCCESS();
