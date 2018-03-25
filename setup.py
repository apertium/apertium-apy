from os import path
from setuptools import setup

from apertium_apy import apy

setup(
    name='apertium-apy',
    version=apy.__version__,
    license=apy.__license__,
    description='Apertium Web Service',
    long_description=open(path.join(path.abspath(path.dirname(__file__)), 'README.md')).read(),
    long_description_content_type='text/markdown; charset=UTF-8',
    keywords='apertium parsing linguistics server',
    author='Apertium',
    author_email='sushain@skc.name',
    url='https://github.com/apertium/apertium-apy',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Topic :: Text Processing :: Linguistic',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Intended Audience :: Science/Research',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3 :: Only',
    ],
    python_requires='>=3.4',
    install_requires=['tornado>=4.3,<5'],
    extras_require={
        'spelling': ['apertium-streamparser'],
        'suggestions': ['requests'],
        'lang_detect': ['cld2'],
        'website_encoding_detect': ['chardet'],
    },
    entry_points={
        'console_scripts': ['apertium-apy=apertium_apy.apy:main'],
    },
    packages=['apertium_apy'],
)
