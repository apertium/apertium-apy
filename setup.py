from os import listdir, path
from setuptools import setup, find_packages
from setuptools.command.install import install
from subprocess import check_call, CalledProcessError

from apertium_apy import apy


class InstallHelper(install):
    def run(self):
        try:
            check_call(['make', 'langNames.db'])
        except CalledProcessError:
            pass

        super().run()

        try:
            check_call(['make', 'clean'])
        except CalledProcessError:
            pass


def files(root):
    for file_or_dir in listdir(root):
        full_path = path.join(root, file_or_dir)
        if path.isfile(full_path):
            yield full_path


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
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3 :: Only',
    ],
    python_requires='>=3.5',
    install_requires=['tornado>=4.2,<7'],
    extras_require={
        'spelling': ['apertium-streamparser'],
        'suggestions': ['requests'],
        'website_encoding_detect': ['chardet'],
        'lang_detect': ['chromium_compact_language_detector'],
        'full': ['apertium-streamparser', 'requests', 'chardet', 'chromium_compact_language_detector', 'commentjson'],
    },
    entry_points={
        'console_scripts': ['apertium-apy=apertium_apy.apy:main'],
    },
    packages=find_packages(exclude=['tests']),
    data_files=[
        ('share/apertium-apy', ['README.md', 'COPYING', 'langNames.db']),
        ('share/apertium-apy/tools', files('tools')),
        ('share/apertium-apy/tools/systemd', files('tools/systemd')),
        ('share/apertium-apy/tools/sysvinit', files('tools/sysvinit')),
        ('share/apertium-apy/tools/upstart', files('tools/upstart')),
    ],
    cmdclass={
        'install': InstallHelper,
    },
)
