import sys

from setuptools import setup, find_packages

with open('README.rst') as readme:
    long_description = readme.read()

extra_packages = []
if sys.version_info[0] == 2 and sys.version_info[1] == 6:
    extra_packages = ['argparse']

setup(
    name='cmdchk',
    version='1.0.0',
    description='A monitoring program that responds over HTTP.',
    long_description=long_description,
    url='http://git.launchbrigade.com/emarks/cmdchk',
    author='Ellison Marks',
    author_email='emarks@scratchspace.com',
    license='NCSA',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: University of Illinois/NCSA Open Source License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: System :: Monitoring',
    ],
    keywords='cluster monitor http',
    packages=find_packages(),
    install_requires=['setproctitle'].extend(extra_packages),
    platforms=['GNU/Linux'],
    entry_points={
        'console_scripts': [
            'cmdchk_wrapper = cmdchk.cmdchk_server:wrapper',
            'cmdchk_server = cmdchk.cmdchk_server:run_server',
        ]
    },
)
