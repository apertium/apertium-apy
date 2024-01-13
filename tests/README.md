Testing
=======

The tests require some test data.

To install the test data on Debian-based systems, first install core
tools as show at https://wiki.apertium.org/wiki/Debian and then do

    sudo apt-get install apertium-sme-nob apertium-es-en
    mkdir ~/apy-testdata
    cd ~/apy-testdata
    git clone --depth 1 https://github.com/apertium/apertium-nno
    cd apertium-nno
    ./autogen.sh
    make -j4

Now go back to the APy directory, and do

    NONPAIRS=~/apy-testdata python3 -m unittest tests/test*.py

to run the tests.
