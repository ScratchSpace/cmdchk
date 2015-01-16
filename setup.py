import sys

from setuptools import setup, find_packages

with open('README.md') as readme:
    long_description = readme.read()

extra_packages = []
if sys.version_info[0] == 2 and sys.version_info[1] == 6:
    extra_packages = ['argparse']

setup(
    name='appsrvchk',
    version='1.0.0',
    description='A monitoring program that responds over HTTP.',
    long_description=long_description,
    url='http://git.launchbrigade.com/emarks/appsrvchk',
    author='Ellison Marks',
    author_email='emarks@scratchspace.com',
    license='NCSA',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: University of Illinois/NCSA Open Source License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2 :: Only',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: System :: Monitoring',
    ],
    keywords='cluster monitor appsrv http',
    packages=find_packages(),
    install_requires=['setproctitle'].extend(extra_packages),
    platforms=['GNU/Linux'],
    entry_points={
        'console_scripts': [
            'appsrvchk_wrapper = appsrvchk.appsrvchk_server:wrapper',
            'appsrvchk_server = appsrvchk.appsrvchk_server:run_server',
        ]
    },
)
