
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
# Main API wrapper, kicks off appropriate storage array scripts
# Takes parameter --array-model
# Currently supported models:
# hpeva - HP EVA 8400
# compellent - Dell Compellent 2000/2040
###############################################################################
import sys
import argparse
import os
import subprocess

def get_option_parser():
    '''
    Returns argument parser
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument("--array-model",
                      required=True,
                      default=None,
                      help="storage array manager model identifier\n"
                           "Currently supported models:\n"
                           "\thpeva - HP EVA 8400"
                           "\tcompellent - Dell Compellent 2000/2040")
    return parser

def main():
    #TODO:
    # 1. Run setup.py to check whether all required components are in place
    # 2. In the future we should be calling main() for apropriate api library instead of suing subprocess.call()

    args, argsleft = get_option_parser().parse_known_args()
    api_path = "%s/src/libs/%s/SteelFusionHandoff.py" % (os.path.abspath(os.path.dirname(sys.argv[0])), args.array_model)
    if not(os.path.isfile(api_path)):
        if args.array_model is not None:
            print("Array type '%s' is unknown." % args.array_model, file=sys.stderr)
        else:
            print("--array-model parameter is missing.", file=sys.stderr)
        exit (1)
    try:
        # Cleaning up arguments used only by this module
        if args.array_model is not None:
            arg_ind = sys.argv.index("--array-model")
            nbin = sys.argv[arg_ind+1]
            sys.argv.remove(nbin)
        sys.argv.remove("--array-model")
        path_list = [api_path] + sys.argv[1:]
        retcode = subprocess.call(path_list, shell=False)
        sys.exit(retcode)
    except OSError as e:
        print("Execution failed %s" % e, file=sys.stderr)
        exit (1)

if __name__ == '__main__':
    main()
