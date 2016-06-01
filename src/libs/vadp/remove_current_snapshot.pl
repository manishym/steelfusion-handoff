#!/usr/bin/perl

use FileHandle;
use Data::Dumper;
use strict;

=head NAME

remove_current_snapshot

=head1 SYNOPSIS

removes a current snapshot from a vmsd file

=head1 DESCRIPTION

Removes a current snapshot from a vmsd file, namely:

1. opens up that vmsd file
2. uses the global metadata to determine the current snapshot
3. identifies the current snapshot, indicated by metadata named snapshot[0-9]
4. deletes that metadata from the vmsd file
5. decrements the snapshots.numSnapshots field and snapshots.current field
6. writes out the new vmsd file.

= head1 METHODS

=over 2

=cut

=item remove_current_snapshot(vmsd_file, new_vmsd_file)

Removes the current snapshot from the given vmsd_file. Modifies it and writes
the changes to the fixed_vmsd_file.

Returns back a hash containing metadata for the snapshot that was deleted

=cut

sub remove_current_snapshot {

    my ($vmsd_file, $fixed_vmsd_file) = @_;

    my $snapshots = {};

    my $text = _gettext($vmsd_file);

    my $metadata = _metadata($text);
    $snapshots = _snapshots($text);

    my $return = _decrement_and_return_snapshot(
                         file      => $vmsd_file,
                         new_file  => $fixed_vmsd_file,
                         text      => $text,
                         metadata  => $metadata,
                         snapshots => $snapshots);

    return $return;
}

=item find_snap_uid_by_name(snapshots, snapshot name)

Finds the current snapshot ID associated with a given snapshot name

=cut
sub find_snap_uid_by_name
{
    my ($snapshots, $snap_name) = @_;

    my $snap_key;
    foreach $snap_key (keys(%$snapshots))
    {
        my $snap_entry;
        foreach $snap_entry ($snapshots->{$snap_key})
        {
            if ($snap_entry =~ /,*\.displayName = \"$snap_name\"/) {
                return $snap_key;
            }
        }
    }
}

=item remove_snapshot_by_name(vmsd_file, new_vmsd_file, snap_name)

Removes the snapshot pointed to by snap_name from the given vmsd_file. 
Modifies it and writes the changes to the fixed_vmsd_file.

Returns back a hash containing metadata for the snapshot that was deleted

=cut
sub remove_snapshot_by_name
{
    my ($vmsd_file, $fixed_vmsd_file, $snap_name) = @_;

    my $snapshots = {};

    my $text = _gettext($vmsd_file);

    my $metadata = _metadata($text);
    $snapshots = _snapshots($text);

    my $uid = find_snap_uid_by_name($snapshots, $snap_name);

    my $return = _decrement_remove_snap_by_uuid(
                         file      => $vmsd_file,
                         new_file  => $fixed_vmsd_file,
                         text      => $text,
                         metadata  => $metadata,
                         snapshots => $snapshots,
                         uuid      => "$uid");

    return $return;
}


=item _decrement_and_return_snapshot(file => <vmsd_filename>, new_file => <new_vmsd_filename>, text => <text_of_vmsd_file>, metadata => <metadata_portion>, snapshots => <parsed_snapshots)

Main subroutine that handles all special cases for the snapshot removal. Takes 
parsed metadata from the vmsd_file, decides how to edit the vmsd file, and
then performs the edit.

Returns back a hash with the metadata for the deleted snapshot.

=cut
sub _decrement_and_return_snapshot
{
    my (%p) = @_;

    my $file      = $p{'file'};
    my $new_file  = $p{'new_file'};
    my $text      = $p{'text'};
    my $metadata  = $p{'metadata'};
    my $snapshots = $p{'snapshots'};

    # case 0 - no snapshots, NOOP
    if (!_no_snapshots($snapshots))
    {
        return( { } );
    }

    my $cur_uid = _current_uid($metadata);

    return _decrement_remove_snap_by_uuid(
                         file      => $file,
                         new_file  => $new_file,
                         text      => $text,
                         metadata  => $metadata,
                         snapshots => $snapshots,
                         uuid      => $cur_uid);
}

=item _decrement_and_return_snapshot(file => <vmsd_filename>, new_file => <new_vmsd_filename>, text => <text_of_vmsd_file>, metadata => <metadata_portion>, snapshots => <parsed_snapshots, uuid => uuid of snap to remove)

Main subroutine that handles all special cases for the snapshot removal. Takes
parsed metadata from the vmsd_file, decides how to edit the vmsd file, and
then performs the edit based on the passed in snapshot uid.

Returns back a hash with the metadata for the deleted snapshot.

=cut
sub _decrement_remove_snap_by_uuid
{
    my (%p) = @_;

    my $file      = $p{'file'};
    my $new_file  = $p{'new_file'};
    my $text      = $p{'text'};
    my $metadata  = $p{'metadata'};
    my $snapshots = $p{'snapshots'};
    my $cur_uid   = $p{'uuid'};

    my $deleted_snapshot = _snapshot_hash($snapshots->{$cur_uid});

    # case 1 - 1 snapshot
    if (_no_snapshots($snapshots) == 1)
    {
        _zero_out(\$text);
        _write_file($text, $new_file);
    }
    elsif (_non_leaf($snapshots, $cur_uid))
    {
        die "ERROR: Non leaf node $cur_uid!\n";
    }
    else
    {
         _delete_snapshot(\$text, $snapshots->{$cur_uid});
         _modify_metadata
         (
                \$text,
                {
                     current      => _parent($snapshots->{$cur_uid}),
                     numSnapshots => (_numSnapshots($metadata) - 1)
                }
          );

          _write_file($text, $new_file);
    }
    return($deleted_snapshot);
}




# --- functions to modify ---

=item _modify_metadata(<vmsd_text>, <metadata_hash>)

Modifies vmsd_text to change the metadata in it to match keys given
in the metadata hash. For example,

_modify_metadata( $text, { current => 1 } );

would change the current snapshot to 1 (set snapshot.current = "1")

=cut

sub _modify_metadata {

    my ($text, $md) = @_;

    my $key;
    foreach $key (keys(%$md))
    {
        $$text =~ s#snapshot\.$key[^\n]*#snapshot.$key = "$md->{$key}"#s;
    }
}

=item _delete_snapshot(<text>, <text_of_snapshot_to_delete>)

Deletes the snapshot in the incoming text.

Works by simply matching that text via regular expression, and deleting it.

=cut

sub _delete_snapshot {

    my ($text, $snap) = @_;

    $snap = quotemeta($snap);
    $$text =~ s#$snap##s;
}

=item _zero_out(<text>)

Zeros out the given vmsd text, namely gets rid of all outstanding snapshots,
and the metadata snapshot.numSnapshots and snapshot.current.

=cut

sub _zero_out {

    my ($text) = @_;

    $$text =~ s#\nsnapshot\d[^\n]*##sg;

    $$text =~ s#\nsnapshot\.numSnapshots[^\n]*##sg;
    $$text =~ s#\nsnapshot\.current\b[^\n]*##s;
}

=item _write_file(<text>, <filename>)

Writes <text> out to the given file.

Saves old file to .bak, in case of issues, removes backup when done.

=cut

sub _write_file {

    my ($text, $file) = @_;

    system("rm -f $file.bak");
    system("mv -f $file $file.bak") if (-e $file);

    my    $fh = new FileHandle("> $file");
    print $fh $text;

    close($fh);

    system("rm -f $file.bak");
}

# --- getter functions ---

=item _snapshot_hash(<text>)

Takes the text for a snapshot and turns it into a hash

Returns a format that looks like:

    $VAR1 = 
    {
          'parent' => '16',
          'uid' => '21',
          'disk1.node' => 'scsi0:1',
          'description' => 'Before the DP scripts ran, the customer switched to customer_snap1. As a result both customer_snap2 and granite_snapshot are based off customer_snap1. They are siblings in a tree.',
          'createTimeLow' => '2143487478',
          'createTimeHigh' => '337495',
          'disk0.fileName' => 'foo-000003.vmdk',
          'filename' => 'foo-Snapshot21.vmsn',
          'numDisks' => '2',
          'disk1.fileName' => '/vmfs/volumes/563cf765-97ef4918-04a4-000eb6926de1/foo/foo_1-000003.vmdk',
          'disk0.node' => 'scsi0:0',
          'displayName' => 'granite_snapshot'
    };

=cut

sub _snapshot_hash {

    my ($text) = @_;

    my $return = {};

    while ($text =~ m#snapshot\d+\.(\S+)\s*=\s*"(.*?)"#sg) {
        $return->{$1} = $2; 
    }

    return($return);
}

=item _no_snapshots(<hash_of_snapshots>)

returns back the number of snapshots in the hash given.

=cut

sub _no_snapshots
{
    my ($snapshots) = @_;

    return(scalar(keys(%$snapshots)));
}

=item _non_leaf(<snapshot_hash>, <uid>)

checks to see whether or not the uid given has children or not.

returns back a list of the children that have uid as its parent.

=cut

sub _non_leaf
{
    my ($snapshots, $cur_uid) = @_;

    # leaves will contain the children which point to the given cur_id, 
    # either directly or indirectly.

    my @leaves     =  ();
    my @old_leaves =  ();

    # parents that we are looking for. Will be added to when we find 
    # snapshots which point to the cur_uid

    my $_parents   = { $cur_uid => 1 };

    my @uids = sort keys(%$snapshots);
    my @old_uids;

    do
    {
        @old_leaves = @leaves;
        @old_uids   = @uids;
        @uids       = ();
        
        my $uid;
        foreach $uid (@old_uids)
        {
            # avoid the current uid
            next if ($uid eq $cur_uid);

            # avoid snapshots that don't have parents.
            next if (!_parent($snapshots->{$uid}));

            # get the parent of the current uid, see if its in the hash
            # we are returning.
            if ($_parents->{_parent($snapshots->{$uid})})
            {
               push(@leaves, $uid);
               $_parents->{$uid}++;
            }
            else
            {
               # if not, the uid may be a grandchild of the uid
               push(@uids, $uid);
            }
        }
    }
    # we go until the # of leaves we have seen stabilized.
    while (@leaves && (@leaves == @old_leaves));

    return(1) if (@leaves);
    return(0);
}

=item _metadata(<text>)

Returns lines other than the ones that are related to snapshots,

Removes all lines that look like, snapshot\d+, what is left is metadata
associated with all snapshots.

=cut

sub _metadata
{
    my ($text) = @_;

    my @lines = split(m#\n#, $text);
    @lines = grep(!m#snapshot\d+#, @lines);

    return(join("\n", @lines));
}

=item _snapshots

Turns incoming hash into its composite snapshots, with the uid as key, and the 
text of the snapshot as as the value:

Uses regular expressions, to produce something like:

    $VAR = {
       ...
       '20' => 
         'snapshot1.uid = "20"
          snapshot1.filename = "foo-Snapshot20.vmsn"
          snapshot1.parent = "16"
          snapshot1.displayName = "customer_snap2"
          snapshot1.description = "Another snapshot taken by the customer before the DP script has initiated a snapshot. This is based off customer_snap1"
          snapshot1.createTimeHigh = "337495"
          snapshot1.createTimeLow = "2067008125"
          snapshot1.numDisks = "2"
          snapshot1.disk0.fileName = "foo-000002.vmdk"
          snapshot1.disk0.node = "scsi0:0"
          snapshot1.disk1.fileName = "/vmfs/volumes/563cf765-97ef4918-04a4-000eb6926de1/foo/foo_1-000002.vmdk"
          snapshot1.disk1.node = "scsi0:1"
          '
     }
=cut

sub _snapshots
{
    my ($line) = @_;
    my $snapshots = {};

    while ($line =~ m#(snapshot(\d+)\..*snapshot\2\.[^\n]*(?:\n|$))#sg)
    {
        my $snapshot = $1;
	$snapshots->{_uid($snapshot)} = $snapshot;
    }

    return($snapshots);
}

=item _uid(<text>)

Gets the uid from the current snapshot. Takes the text of the snapshot
as input.

=cut

sub _uid
{
    my ($text) = @_;

    my ($uid) = 
        ($text =~ m#snapshot\d+\.uid\s+=[^\n\d]*(\d+)#s);

    return($uid);
}

=item _current_uid(<text>)

Gets the current uid Takes the text of the full snapshot as 
input.

=cut

sub _current_uid
{
    my ($text) = @_; 

    my ($uid) = ($text =~ m#snapshot\.current\s*=[^\n\d]*(\d+)#s);
    return($uid);
}

=item _parent(<text>)

Gets the parent of the current snapshot. Takes the text of one snapshot
as input.

=cut

sub _parent
{
    my ($text) = @_;

    my ($parent) = ($text =~ m#\.parent\s*=[^\n\d]+(\d+)#s);
    return($parent);
}

=item _numSnapshots(<text>)

Gets the number of snapshots (numSnapshots) field from the current snapshot.
Takes the text of one snapshot as input.

=cut

sub _numSnapshots
{
    my ($text) = @_;
    my ($num_snapshots) = ($text =~ m#\.numSnapshots\s*=[^\n\d]+(\d+)#s);

    return($num_snapshots);
}

=item _gettext

generic, global functoin to get text for a given file.

=cut

sub _gettext
{
    my ($file) = @_;

    local($/) = undef; # go into slurp mode.

    my $fh = new FileHandle($file) || die "Couldn't open $file\n";
    my $line = <$fh>;
    return($line);
}

1;
