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

# This file is used to create the super secret file mentioned below.
# Note that the super secret file must be created in the WORK_DIR.
# This file assumes that the WORK_DIR is c:\rvbd_handoff_scripts
# On running this script, you will be prompted for the storage array
# password, please enter the exact storage array password.
$secure = read-host -assecurestring
$encrypted = convertfrom-securestring -secureString $secure -key (1..16)
$encrypted | set-content c:\rvbd_handoff_scripts\supersecretfile.txt
$secure2 = get-content c:\rvbd_handoff_scripts\supersecretfile.txt | convertto-securestring -key (1..16)
