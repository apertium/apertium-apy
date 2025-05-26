#!/bin/bash
#
# bot initscript
#
# Last Updated: Oct 31, 2011
# Modified for Apertium on Jan 11, 2014
# If broken, yell at: firespeaker
#

### BEGIN INIT INFO
# Provides:		apy
# Required-Start:	$network
# Required-Stop:	$network
# Default-Start:	3 4 5
# Default-Stop:		0 1 6
# Short-Description:	Apertium APY, Apertium API in Python
### END INIT INFO

export PKG_CONFIG_PATH=/traductors/lib/pkgconfig
export PATH=/traductors/bin:/usr/bin:/bin:$PATH
export LD_LIBRARY_PATH=/traductors/lib:$LD_LIBRARY_PATH

SERVLET="apy.py"
EXEC="/traductors/apertium-apy/"
ARGS="-l tools/apertiumlangs.db ../pairs -d -P /var/log"
USER="www-data"

start_apy() {
    #echo "start-stop-daemon -S -c $USER -p /var/run/$SERVLET.pid -m -d $EXEC -b -x $SERVLET -- $ARGS"
    #echo "start-stop-daemon -S -c $USER -p /var/run/$SERVLET.pid -m -d `dirname $EXEC` -b -x $EXEC -- $ARGS"
    #start-stop-daemon -S -c $USER -p /var/run/$SERVLET.pid -m -d $EXEC -b -x $EXEC/$SERVLET -- $ARGS
    #start-stop-daemon -S -c $USER -p /var/run/$SERVLET.pid -m -d $EXEC -b -x /usr/bin/python3 -- "$EXEC/$SERVLET $ARGS > /var/log/apertium-apy.log 2>&1"
    #start-stop-daemon -S -c $USER -p /var/run/$SERVLET.pid -m -d $EXEC -b -x /usr/bin/python3 -- "$EXEC/$SERVLET $ARGS > /var/log/apertium-apy.log 2>&1"
    start-stop-daemon -S -c $USER -p /var/run/$SERVLET.pid -m -d $EXEC -b -x $EXEC/$SERVLET -- $ARGS
    SUCCESS=$?
    if [ $SUCCESS -gt 0 ]; then
        echo "ERROR: Couldn't start $SERVLET"
    fi
    return $SUCCESS
}

stop_apy() {
    start-stop-daemon -K -p /var/run/$SERVLET.pid
    SUCCESS=$?
    if [ $SUCCESS -gt 0 ]; then
        echo "ERROR: Couldn't stop $SERVLET"
    fi
    return $SUCCESS
}

case "$1" in
    start)
        echo "Starting $SERVLET"
        start_apy
        ;;
    stop)
        echo "Stopping $SERVLET"
        stop_apy
        ;;
    restart)
        echo "Restarting $SERVLET"
        stop_apy
        if [ $? -gt 0 ]; then
            exit -1
        fi
        start_apy
        ;;
    force-reload)
        echo "Restarting $SERVLET"
        stop_apy
        if [ $? -gt 0 ]; then
            exit -1
        fi
        start_apy
        ;;
    status)
        if [ -e /var/run/$SERVLET.pid ]; then
            exit 0
        fi
        exit 3
        ;;
    *)
        echo "Usage: /etc/init.d/$SERVLET {start, stop, restart, force-reload, status}"
        exit 1
        ;;
esac

exit 0
