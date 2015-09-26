- Update Readme
- Update License
- Create Unit Tests
- Create foreign code folder structure
- Specify requirements for various storage appliance configurations in requirements file
- Follow structured python: http://www.pydanny.com/cookie-project-templates-made-easy.html
https://www.jeffknupp.com/blog/2013/08/16/open-sourcing-a-python-project-the-right-way/
http://www.connorgarvey.com/blog/?p=184
- Follow VMware python SDK structure: https://github.com/vmware/pyvmomi
- Setup configuration script to validate the environemt, python, perl, sdk and etc.
- Setup script should have prerequisite check
- Outline requirements - this code is written for python 3
- SteelFusionHandoff.py --work-dir c:\rvbd_handoff_scripts\src --serial 600143801259b9e40000500000490000 --array 172.16.1.216 --system STOMO-PRIMARY --operation HELLO
-  # TODO: Don't we need to remove sanpshot from the DB??? in remove_snapshot instead of calling the function in delete_cloned_lun
- Let alton know about compellent snapshot, line 238 ++ sdb.delete_clone_info(lun_serial) in compellent_handoff_script.pl

Q:
- Do we need to preserve wwn for the snapshot? no
- Do we need to preserve wwn for the cloned snapshot? no
- Mounting lun, can an array mount a lun (in reality its maping a lun), is that same as presenting the lun
- Testing backup: create snapshot, create snap, remove first snap, create snap-mount, create snap-mount, and remove snap-mount
- Access group is the group on the SAN where ESXi proxy host is added (wwwn)