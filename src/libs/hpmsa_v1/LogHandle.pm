###############################################################################
#
# (C) Copyright 2015 Riverbed Technology, Inc
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

package LogHandle;
use Logger;
use warnings;
use strict;
my $_global_prefix = "";
my $_extra_logging = 0;

sub set_global_params {
    my ($global_prefix, $extra_logging) = @_ ;
    if (defined($extra_logging) && $extra_logging > 0) {
        $_extra_logging = $extra_logging;
    }
    $_global_prefix = $global_prefix . "/";
}

sub global_prefix {
    return $_global_prefix;
}

sub new {
    my ($class) = shift;
    my ($log_prefix) = @_;
    my $self = {
        prefix_ => $_global_prefix . $log_prefix,
    };
    bless ($self, $class);
    return $self;
}

sub diag {
    my ($self) = shift;
    my ($msg) = @_;
    if ($_extra_logging) {
        Logger::instance()->info($self->{prefix_}, $msg);
    } else {
        Logger::instance()->debug($self->{prefix_}, $msg);
    }
}
sub info {
    my ($self) = shift;
    my ($msg) = @_;
    Logger::instance()->info($self->{prefix_}, $msg);
}
sub note {
    my ($self) = shift;
    my ($msg) = @_;
    Logger::instance()->note($self->{prefix_}, $msg);
}
sub debug {
    my ($self) = shift;
    my ($msg) = @_;
    Logger::instance()->debug($self->{prefix_}, $msg);
}
sub error {
    my ($self) = shift;
    my ($msg) = @_;
    Logger::instance()->error($self->{prefix_}, $msg);
}
sub warn {
    my ($self) = shift;
    my ($msg) = @_;
    Logger::instance()->warn($self->{prefix_}, $msg);
}

1;