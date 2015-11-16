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
- Distinguish scripts as V1 or V2. V1 is the all-in one style, where V2 is separate libraries.
- Any new lib should invoke main() in "if __main__ "
- Update documentation to include --arraymodel parameter