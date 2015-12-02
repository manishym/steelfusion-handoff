from distutils.core import setup

setup(
    name='SteelFusionHandoff',
    version='1.1.0',
    author='Laurynas Kavaliauskas',
    author_email='lkavaliauskas@riverbed.com',
    packages=['src', 'src.test'],
    scripts=['bin/run.py','bin/configure.py'],
    url='http://github.com/Riverbed/steelfusionhandoff/',
    license='LICENSE',
    description='SteelFusion Handoff Scripts.',
    long_description=open('README.txt').read(),
    install_requires=[],
)