#!/usr/bin/env python

from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='pycomfoair',
    version='0.0.3',
    author='Andreas Oberritter',
    author_email='obi@saftware.de',
    url='https://github.com/mtdcr/pycomfoair',
    description='Interface for Zehnder ComfoAir 350 ventilation units',
    download_url='https://github.com/mtdcr/pycomfoair',
    license='MIT',
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=['comfoair'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Home Automation',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires=[
        'async-timeout>=3.0.1',
        'bitstring>=3.1.5',
        'pyserial-asyncio>=0.4',
    ],
)
