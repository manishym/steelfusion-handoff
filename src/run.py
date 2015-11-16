
__author__ = 'Laurynas Kavaliauskas'
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

###############################################################################
# Main process, kicks off appropriate storage script
###############################################################################
import sys
import optparse
import os
import subprocess

WORK_DIR =  r'C:\rvbd_handoff_scripts'

def get_option_parser():
    '''
    Returns argument parser
    '''
    parser = optparse.OptionParser()
    # These are script specific parameters that can be passed as
    # script arguments from the Granite Core.
    parser.add_option("--array-model",
                      type="string",
                      default=None,
                      help="storage array manager model identifier\n"
                           "Currently supported models:\n"
                           "\thpeva - HP EVA 8400"
                           "\tcompellent - Dell Compellent 2000/2040")
    parser.add_option("--work-dir",
                      type="string",
                      default=WORK_DIR,
                      help="Directory path to the VADP scripts")
    return parser

def main():
    options, argsleft = get_option_parser().parse_args()
    api_path = "%s/src/libs/%s/SteelFusionHandoff.py" % (options.work_dir, options.array_model)
    print (api_path)
    if not(os.path.isfile(api_path)):
        if options.array_model is not None:
            print("Array '%s' is unknown" % options.array_model, file=sys.stderr)
        else:
            print("--array-model parameter is missing.", file=sys.stderr)
        exit (2)
    try:
        #TODO:
        #0 Check whether script is configured
        retcode = subprocess.call("%s %s" % (api_path, str(sys.argv)), shell=True)
        if retcode < 0:
            print("Child was terminated by signal %i" % -retcode, file=sys.stderr)
        else:
            print("Child returned %i" % retcode, file=sys.stderr)
    except OSError as e:
        print("Execution failed %s" % e, file=sys.stderr)

if __name__ == '__main__':
    main()
