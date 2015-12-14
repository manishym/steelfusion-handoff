#!/usr/bin/python
import os
import sys
import time 
import subprocess 
import re
import getopt
import socket
import syslog
import shlex

#Set the Core IP or host name
core_host = "10.33.195.149"

_path_prefix = "/"

_windows_mount_dir = "C:\\granite_backup"
_windows_exe_dir = "C:\\granite_scripts"
_local_winexe_path = "c:\\pstools\\psexec.exe"
_local_web_prefix = "/opt/tms/web2/html/"

_local_winutil_file = "rvbd_lun_info_util_x86.exe"
_local_setup_file = "rvbd_dp_setup.ps1"
_local_cleanup_file = "rvbd_dp_cleanup.ps1"

_command_pref = ""
_logger = None

class WinDpLogger:
    def __init__(self, name):
        self.name_ = name
        self.prefix_ = name
        self.pid_ = os.getpid()
        self.extra_logging_ = 0
        self.ctx_ = ''
        self.level_dict_ = { syslog.LOG_CRIT : 'CRIT',
                             syslog.LOG_ERR : 'ERR',
                             syslog.LOG_WARNING : 'WARNING',
                             syslog.LOG_NOTICE : 'NOTICE',
                             syslog.LOG_INFO : 'INFO',
                             syslog.LOG_DEBUG : 'DEBUG' }

    def set_params(self, pref = None, extra_logging = None, context = None):
        if (pref is not None):
            if (pref == ''):
                self.prefix_ = self.name_
            else:
                self.prefix_ = self.name_ + '/' + pref
        if (extra_logging is not None):
            self.extra_logging_ = extra_logging
        if (context is not None):
            self.ctx_ = context

    def formatted_message(self, level, message):
        ctx_string = ''
        if (self.ctx_):
            ctx_string = '{%s} ' % str(self.ctx_)
        return '%s[%d]: [%s.%s] - %s%s' % \
                    (self.name_, self.pid_,
                     self.prefix_, self.level_dict_[level],
                     ctx_string, str(message))

    def log_message(self, level, message):
        for line in message.splitlines():
            fmt_msg = self.formatted_message(level, line)
            syslog.syslog(level, fmt_msg)

    def debug(self, message):
        self.log_message(syslog.LOG_DEBUG, message)

    def diag(self, message):
        if (self.extra_logging_):
            self.info(message)
        else:
            self.debug(message)

    def info(self, message):
        self.log_message(syslog.LOG_INFO, message)

    def notice(self, message):
        self.log_message(syslog.LOG_NOTICE, message)

    def warn(self, message):
        self.log_message(syslog.LOG_WARNING, message)

    def error(self, message):
        self.log_message(syslog.LOG_ERR, message)

    def crit(self, message):
        self.log_message(syslog.LOG_CRIT, message)

class WinDp:
    def __init__(self):
        self.serial_ = None
        self.cloned_serial_ = None
        self.host_ = None
        self.username_ = None
        self.password_ = None
        self.ip_addrs_ = [] 
        self.port_ = "80"

        self.windows_mount_dir_ = _windows_mount_dir
        self.windows_exe_dir_ = _windows_exe_dir
        self.windows_exe_dir_path_ = None
        self.local_winexe_path_ = _local_winexe_path
        self.mount_prefix_ = None
        self.target_iqn_ = ""
        self.extra_logging_ = 0

        self.local_web_subdir_ = "" 
        self.local_winutil_file_ = _local_winutil_file
        self.local_setup_file_ = _local_setup_file
        self.local_cleanup_file_ = _local_cleanup_file

        self.local_winutil_path_ = None
        self.local_setup_path_ = None
        self.local_cleanup_path_ = None

    def execute(self):
        # check arguments
        if (self.check_args() == False):
            _logger.error("Incorrect arguments\n")
            usage()
            sys.exit(2)

#        if (self.set_script_path() == False):
#            _logger.error("Cannot set dva version\n")
#            sys.exit(1)

#        if (self.get_local_ips() == False):
#            _logger.error("Could not get IP of core\n")
#            sys.exit(1)

        # check environment on windows proxy
        if (self.check_windows_env() == False):
            _logger.error("Pre-check failure on Windows proxy host\n")
            sys.exit(1)

        # check scripts dir
        if (self.check_windows_host(self.windows_exe_dir_) == False):
            _logger.error("Failed to create script dir\n")
            sys.exit(1)

        # check script dir with version info
        if (self.check_windows_host(self.windows_exe_dir_path_) == False):
            _logger.error("Failed to create dir with version info\n")
            sys.exit(1)

        if (self.copy_files() == False):
            _logger.error("Could not copy files to host\n")
            sys.exit(1)

        if (self.execute_scripts_on_host() == False):
            _logger.error("Error executing script on proxy host\n")
            sys.exit(1)
        # do not cleanup scripts_dir

    def check_args(self):
        global _command_pref
        global _logger

        # check required arguments
        if self.serial_ is None or \
           self.cloned_serial_ is None or \
           self.host_ is None:
            _logger.error("Missing required arguments\n")
            return False

        # set logging params
        _logger.set_params(extra_logging = self.extra_logging_,
                           context = self.serial_)

        if (os.path.exists(self.local_winexe_path_) == False):
            _logger.error("Local winexe path does not exist\n")
            return False

        if (os.path.exists(self.local_winutil_path_) == False):
            _logger.error("Local winutil path does not exist\n")
            return False

        if ((self.local_cleanup_path_ is None) and
            (self.local_setup_path_ is None)):
            _logger.error("Specify which script is to be invoked on windows\n")
            return False

        if ((self.local_cleanup_path_ is not None) and
            (os.path.exists(self.local_cleanup_path_) == False)):
            _logger.error("Cleanup script does not exist on core\n")
            return False

        if ((self.local_setup_path_ is not None) and
             (os.path.exists(self.local_setup_path_) == False)):
            _logger.error("Setup script does not exist on core\n")
            return False

        # mount prefix is serial if not specified 
        if (self.mount_prefix_ is None):
            self.mount_prefix_ = self.serial_

        # obtain via environment variables
        _command_pref = self.local_winexe_path_ + " -E " + " //" \
                       + self.host_ + " "

        # override if username/password is specified
        if ((self.username_ is not None) and (self.password_ is not None)): 
            # get "\" in the path and replace with \\.
            idx = self.username_.find("\\")
            if (idx != -1):
                username = self.username_[0:idx] + "\\\\" + self.username_[(idx + 1):]
                self.username_ = username

            _command_pref = self.local_winexe_path_ + " -U " + self.username_ \
                        + "%" + self.password_ + " //" + self.host_ + " "
        return True

#    def set_script_path(self):
#        version_command = "/opt/rbt/bin/dc -v | grep 'Revision'"
#        version, error = subprocess.Popen(version_command, stdout = subprocess.PIPE,
#                                          stderr = subprocess.PIPE, shell = True).communicate()
#        dc_version = None
#        if version:
#            match = re.search(r'\s[\d]+', version)
#            if match:
#                dc_version = match.group().strip() 
#                self.windows_exe_dir_path_ = self.windows_exe_dir_ + "\\" + dc_version
#
#        if dc_version is None:
#            return False
#
#        return True

#    def get_local_ips(self):
#        port_command = "/opt/tms/bin/mdreq -v query get - /web/httpd/http/port"
#        port, error = subprocess.Popen(port_command, stdout = subprocess.PIPE,
#                                     stderr = subprocess.PIPE, shell = True).communicate()
#        if (port):
#            self.port_ = port.strip()
#        else:
#            _logger.error("Cannot get http port of granite core\n")
#            return False###

        # get ip addresses by hostname
#        try:
#            addrinfo = socket.getaddrinfo(socket.getfqdn(), self.port_)
#            for elem in addrinfo:
#                if len(elem) == 5:
#                    addrs = elem[4]
#                    if ((len(addrs) >=2) and (addrs[0]) and (addrs[0] != "127.0.0.1") and (addrs[0] not in self.ip_addrs_)):
#                        self.ip_addrs_.append(addrs[0])
#        except socket.gaierror, err:
#            _logger.info("Cannot get ip address of granite core from hostname\n")##

        # also obtain all ips from ifconfig -a.
#        get_all_ips(self.ip_addrs_)##
#
#        if (not self.ip_addrs_):
#            return False
#        return True

    def check_windows_env(self):
        # check if winexe works
        test_command = '"cmd /c echo"'
        test_command = _command_pref + test_command
        output, error = subprocess.Popen(test_command, stdout = subprocess.PIPE,
                                         stderr = subprocess.PIPE, shell = True).communicate()
        match_op = re.search("Error", output, re.IGNORECASE)
        match_err = re.search("Error", error, re.IGNORECASE)
        if match_op or match_err:
            # winexesvc seems to be stopped, run again with --reinstall option.
            test_command = '"cmd /c echo"'
            command_pref_reinst = _command_pref + "--reinstall "

            test_command = command_pref_reinst + test_command
            output, error = subprocess.Popen(test_command, stdout = subprocess.PIPE,
                                             stderr = subprocess.PIPE, shell = True).communicate()
            match_op = re.search("(Error)(.*)", output, re.IGNORECASE)
            match_err = re.search("(Error)(.*)", error, re.IGNORECASE)
            err_found = match_op if match_op else match_err
            if err_found:
                _logger.error(err_found.group(2).strip(': '))
                return False

        return True

    def check_windows_host(self, path):
        # check if script dir exists
        # do not create new script dir if the dir is already present
        ps_command = '"cmd /c dir ' + path + '"'
        output, error = subprocess.Popen(_command_pref + ps_command, stdout = subprocess.PIPE,
                                         stderr = subprocess.PIPE, shell = True).communicate()
        match_op = re.search("File not found", output, re.IGNORECASE)
        match_err = re.search("File not found", error, re.IGNORECASE)
        if not (match_op or match_err):
            # do not cleanup if found
            return True

        # create
        if (create_remote_dir(path) == False):
            return False

        return True 
 
    def setup_reqd_files(self, reqd_files):
        reqd_files.append('rvbd_lun_info_util.exe')

        if (self.local_cleanup_path_ is not None):
            reqd_files.append('rvbd_dp_cleanup.ps1')
        if (self.local_setup_path_ is not None):
            reqd_files.append('rvbd_dp_setup.ps1')

    def check_reqd_files_on_host(self, reqd_files):
        # check if exe and scripts exist
        ps_command = '"cmd /c dir /B '  + self.windows_exe_dir_path_ + '"'
        op, error = subprocess.Popen(_command_pref + ps_command, stdout = subprocess.PIPE,
                                 stderr = subprocess.PIPE, shell = True).communicate()

        if not op:
            return

        rem_obj = []

        for f in reqd_files:
            if (op.find(f) != -1):
                rem_obj.append(f)

        for f in rem_obj:
            reqd_files.remove(f)

    def copy_scripts_and_utils(self, ip, files):
        ps_command_pref = '"cmd /c echo . | powershell (new-object System.Net.WebClient).DownloadFile('

#        ps_command_arg1_pref = "'http://" + ip + ":" + self.port_ + "/"
        ps_command_arg1_pref = "'http://" + core_host + "/"

        if (self.local_web_subdir_):
            ps_command_arg1_pref += self.local_web_subdir_ + _path_prefix

        for src in files:
            # copy files
            dest = src
            if (src == "rvbd_lun_info_util.exe"):
                src = self.local_winutil_file_

            ps_command_arg1 = ps_command_arg1_pref + src + "',"
            ps_command_arg2 = "'" + self.windows_exe_dir_path_ + "\\" + dest + "')" + '"'
            subprocess.call(_command_pref + ps_command_pref + ps_command_arg1 + ps_command_arg2, shell = True)

        return True
 
    def copy_files(self):
        # setup reqd files list
        reqd_files = []
        self.setup_reqd_files(reqd_files)

        # after this function, reqd_files contains a list of files to be copied
        self.check_reqd_files_on_host(reqd_files)
        idx = 0
        retry = 0
        max_retries = 3
        num_addrs = len(self.ip_addrs_)

        if not reqd_files:
            return True

        old_len = len(reqd_files)
        while True:
            if (idx >= num_addrs):
                break
            if (retry >= max_retries):
               break

            ip = self.ip_addrs_[idx]
            # copy reqd_files to windows proxy
            if (self.copy_scripts_and_utils(ip, reqd_files) == False):
                _logger.info("Moving to next ip\n")
                idx += 1
                continue

            # check if files exist on windows proxy
            self.check_reqd_files_on_host(reqd_files)
            # check if all files were copied
            if not reqd_files:
                # all files were copied, break
                break

            # no files were copied, move to next ip
            if (len(reqd_files) == old_len):
                _logger.error("Could not copy files, moving to next ip\n")
                idx += 1
                continue

            # some files were copied, copy using the same ip
            retry += 1

        if ((idx >= num_addrs) or (retry >= max_retries)):
            _logger.error("Could not copy files to windows host\n")
            return False
        return True

    def get_command_to_run(self, command):
        return shlex.split(command.encode('ascii'))

    def escape_serial(self, serial):
        return serial.replace('&', '^^^&').replace('<', '^^^<').replace('>', '^^^>')

    def execute_command_with_retry(self, command):
        _logger.diag("Running %s" % command)

        MAX_RETRIES = 3
        retries = 0
        out, err, ret_status = ('', '', True)

        while retries <= MAX_RETRIES:
            retries += 1
            proc = subprocess.Popen(command, 
                                    stdout = subprocess.PIPE,
                                    stderr = subprocess.PIPE, shell = False)
            out, err = proc.communicate()
            if out:
                _logger.info("%s" % out)
            if err:
                _logger.error("%s" % err)
            if proc.wait() != 0:
                ret_status = False
                if err.find('is being used by another process') != -1 and\
                   retries <= MAX_RETRIES:
                    # Sleep for 20 seconds to allow another process to finish
                    # We allow max 1 minute for such retrials
                    _logger.info("Failed the operation since another operation "\
                                 "is in progress on the proxy host, retry...")
                    time.sleep(20)
                else:
                    # No need to retry on other errors
                    break
            else:
                ret_status = True
                break

        return (out, err, ret_status)

    def execute_scripts_on_host(self):
        ps_command_pref = '"cmd /c echo . | '
        ps_command_pref += "powershell Set-ExecutionPolicy bypass -Force -Scope CurrentUser;"
        exe = self.windows_exe_dir_path_ + "\\rvbd_lun_info_util.exe"
        ret_status = True
        if (self.local_cleanup_path_ is not None):
            ps_command = self.windows_exe_dir_path_ + "\\rvbd_dp_cleanup.ps1 "
            ps_command += "-lun " + "'" + self.escape_serial(self.serial_)  + "' "
            ps_command += "-clone " + "'" + self.escape_serial(self.cloned_serial_) + "' "
            ps_command += "-mount " + "'" + self.windows_mount_dir_ + "' "
            ps_command += "-exe " + "'" + exe + "' "
            ps_command += "-prefix " + "'" + self.escape_serial(self.mount_prefix_) + "' "
            ps_command += "-extra_logging " + "'" + str(self.extra_logging_) + "' "
            if (self.target_iqn_):
                ps_command += "-tiqn " + "'" + str(self.target_iqn_) + "'"
            ps_command += '"'

            out, err, ret_status = self.execute_command_with_retry(
                                        self.get_command_to_run(
                                        _command_pref + ps_command_pref + ps_command)) 

        if (self.local_setup_path_ is not None):
            ps_command = self.windows_exe_dir_path_ + "\\rvbd_dp_setup.ps1 "
            ps_command += "-lun " + "'" + self.escape_serial(self.serial_)  + "' "
            ps_command += "-clone " + "'" + self.escape_serial(self.cloned_serial_) + "' "
            ps_command += "-mount " + "'" + self.windows_mount_dir_ + "' "
            ps_command += "-exe " + "'" + exe + "' "
            ps_command += "-prefix " + "'" + self.escape_serial(self.mount_prefix_) + "' "
            ps_command += "-extra_logging " + "'" + str(self.extra_logging_) + "' "
            if (self.target_iqn_):
                ps_command += "-tiqn " + "'" + str(self.target_iqn_) + "'"
            ps_command += '"'

            out, err, ret_status = self.execute_command_with_retry(
                                        self.get_command_to_run(
                                        _command_pref + ps_command_pref + ps_command)) 
    
        ps_command_pref = '"cmd /c echo . | '
        ps_command_pref += "powershell Set-ExecutionPolicy Restricted  -Force -Scope CurrentUser" + '"'
        subprocess.call(_command_pref + ps_command_pref, shell = True)

        return ret_status

    def cleanup_files_on_host(self, path, rmdir = False):
        if rmdir:
            return remove_remote_dir(path)

        if (path == self.windows_exe_dir_path_):
            ps_command_pref = '"cmd /c del ' + path 
            ps_command = ps_command_pref + "\\rvbd_lun_info_util.exe" + '"'
            subprocess.call(_command_pref + ps_command, shell = True)

        if (self.local_cleanup_path_ is not None):
            ps_command = ps_command_pref + "\\rvbd_dp_cleanup.ps1" + '"'
            subprocess.call(_command_pref + ps_command, shell = True)

        if (self.local_setup_path_ is not None):
            ps_command = ps_command_pref + "\\rvbd_dp_setup.ps1" + '"'
            subprocess.call(_command_pref + ps_command, shell = True)

        return remove_remote_dir(path)


# Helper methods
def get_all_ips(ip_addrs):
    ip_cmd = "/sbin/ifconfig -a | grep 'inet addr' | cut -d: -f2 | awk '{ print $1}'"

    ip, error = subprocess.Popen(ip_cmd, stdout = subprocess.PIPE,
                                stderr = subprocess.PIPE, shell = True).communicate()
    if (ip):
        for addr in ip.split("\n"):
            addr = addr.strip()
            if ((addr) and (addr != "127.0.0.1") and (addr not in ip_addrs)):
                ip_addrs.append(addr)
    else:
        _logger.info("Cannot query ip addr of granite core\n")

def create_remote_dir(path):
    ps_command = '"cmd /c mkdir ' + path + '"'
    subprocess.call(_command_pref + ps_command, shell = True)

    ps_command = '"cmd /c dir ' + path + '"'
    output, error = subprocess.Popen(_command_pref + ps_command, stdout = subprocess.PIPE,
                                     stderr = subprocess.PIPE, shell = True).communicate()
    match_op = re.search("File not found", output, re.IGNORECASE)
    match_err = re.search("File not found", error, re.IGNORECASE)
    if match_op or match_err:
        return False
    return True

def remove_remote_dir(path):
    ps_command = '"cmd /c rmdir /S /Q ' + path + '"'
    subprocess.call(_command_pref + ps_command, shell = True)

    ps_command = '"cmd /c dir ' + path + '"'
    output, error = subprocess.Popen(_command_pref + ps_command, stdout = subprocess.PIPE,
                                     stderr = subprocess.PIPE, shell = True).communicate()
    match_op = re.search("File not found", output, re.IGNORECASE)
    match_err = re.search("File not found", error, re.IGNORECASE)
    if match_op or match_err:
        return True 

    return False

def get_file_from_path(path):
    # get last / in the path and return the string following that
    idx = path.rfind("/")
    if (idx != -1):
        return path[idx + 1:]

    return None

def usage():
    usage = """
    Optional:
    -h  help                 Help
    -m                       mount_dir on Windows host
    -e                       exe_dir on Windows host
    -b                       winexe binary path on granite core
    -P                       mount prefix
    -t                       iqn of target
    -D                       local web subdir on on granite core 
    -W                       local winutil file
    -S                       local setup file
    -C                       local cleanup file
    --extra_logging <0/1>    Extra logging

    Required:
    -s   <orig lun serial>   Original lun serial
    -c   <cloned lun serial> Cloned lun serial
    -w   <windows host>      Windows proxy hostname
    -u   <username>          Username for windows host
    -p   <password>          Password for Windows host
    --setup                  if setup script is to be invoked
    --cleanup                if cleanup script is to be invoked
    """

    sys.stderr.write("Usage: %s" % usage)

def parse_args(opts):
    windpparams = WinDp()

    # reqd: -s origserial -c clonedserial -w winhost -u username -p pass
    # optional: -m winmountdir -e winexedir -b corewinexepath -P mount_prefix -t target iqn
    # optional: -D corewebsubdir -W local winutil file -S local setup file -C local cleanup file -h
    # use w, d, u, p for winexe
    # pass s, c, m, e, P, t to windows host

    setup = False
    cleanup = False
    for o, arg in opts:
        if o == "-h":
            usage()
        #required
        elif o in ("-s", "--serial"):
            windpparams.serial_ = arg
        elif o in ("-c", "--clone"):
            windpparams.cloned_serial_ = arg
        elif o in ("-w", "--server"):
            windpparams.host_ = arg
        #optional
        elif o in ("-u", "--username"):
            windpparams.username_ = arg
        elif o in ("-p", "--password"):
            windpparams.password_ = arg
        elif o == "-m":
            windpparams.windows_mount_dir_ = arg
        elif o == "-e":
            windpparams.windows_exe_dir_ = arg 
        elif o == "-b":
            windpparams.local_winexe_path_ = arg
        elif o == "--mount_dir_name":
            windpparams.mount_prefix_ = arg
        elif o == "-t":
            windpparams.target_iqn_ = arg
        # local filenames - optional
        elif o == "-D":
            windpparams.local_web_subdir_ = arg
        elif o == "-W":
            windpparams.local_winutil_file_ = arg
        elif o == "-S":
            windpparams.local_setup_file_ = arg
        elif o == "-C":
            windpparams.local_cleanup_file_ = arg
        elif o == "--setup":
             setup = True 
        elif o == "--cleanup":
             cleanup = True 
        elif o in ("--extra_logging"):
            windpparams.extra_logging_ = int(arg)
        else:
            _logger.error("Incorrect arguments\n")
            usage()
            sys.exit(2)

    pref = _local_web_prefix + windpparams.local_web_subdir_
    if (windpparams.local_web_subdir_):
        pref += _path_prefix

    windpparams.local_winutil_path_ = pref + windpparams.local_winutil_file_

    if (setup == True):
        windpparams.local_setup_path_ = pref + windpparams.local_setup_file_ 

    if (cleanup == True):
        windpparams.local_cleanup_path_ = pref + windpparams.local_cleanup_file_ 

    windpparams.execute()

def main(argv):
    global _logger
    _logger = WinDpLogger("windows_dp")

    try:
        opts, args = getopt.getopt(argv, "s:c:w:u:p:m:e:b:t:D:W:S:C:h", 
            ["serial=", "clone=", "server=", "username=", "password=", "setup", "cleanup", "extra_logging=", "mount_dir_name="])
    except getopt.GetoptError, err:
        _logger.error("Incorrect arguments: %s" % err)
        usage()
        sys.exit(2)
    parse_args(opts) 
    
if __name__=="__main__":
    main(sys.argv[1:])
