#!/usr/bin/python

import globals
import time
import sys
from datetime import datetime, timedelta
import utility
import signal
import getopt


def signal_handler(signal, frame):
        """


        @rtype : object
        @param signal:
        @param frame:
        """
        unload()
        sys.exit(0)


def unload():
    """



    @rtype : object
    """
    print "\nunloading"
    db = utility.dbconnect()
    cursor = db.cursor()
    cursor.execute("DELETE FROM Servers WHERE Type = 'Master' AND UUID = %s", (str(_uuid)))
    db.close()


def register_master_server(uuid):
    db = utility.dbconnect()
    timestamp = datetime.now()

    cursor = db.cursor()
    cursor.execute("SELECT LocalIP, PublicIP, LastSeen, UUID FROM Servers WHERE Type = 'Master'")
    results = cursor.fetchone()

    if results is None:
        cursor.execute('INSERT INTO Servers(LocalIP,PublicIP, Type, LastSeen, UUID, State) VALUES(%s,%s,%s,%s,%s,%s)', (_localip, _publicip, 'Master', timestamp, uuid, 0))
        print "Server successfully registered as the Master Server running on [L}%s / [P}%s on %s" % (_localip, _publicip, timestamp)
    else:
        if results[0] == _localip and results[1] == _publicip and str(results[3]) == str(uuid):
            print "Registering Master Server %s heartbeat at %s" % (_uuid, timestamp)
            cursor.execute("UPDATE Servers SET LastSeen = %s WHERE LocalIP = %s AND PublicIP = %s AND Type = 'Master' AND UUID = %s", (timestamp, _localip, _publicip, uuid))
        elif (timestamp - results[2]) > timedelta(seconds=30):
            print "The Master Server running on [L]%s / [P]%s but heartbeat has not been detected for more than 30 seconds." % (results[0], results[1])
            print "Registering this server as the Master Server"
            cursor.execute("DELETE FROM Servers WHERE Type = 'Master'")
            register_master_server(uuid)
        else:
            print "A Master Server is actively running on [L]%s / [P]%s. Last heartbeat was seen on %s" % (results[0], results[1], results[2])
            sys.exit(1)

    db.commit()
    db.close()
    return True


def remove_stale_slave_servers():
    """



    @rtype : object
    @return:
    """
    #TODO remove undeleted storage confirmation files
    db = utility.dbconnect()
    timestamp = datetime.now()
    cursor = db.cursor()
    cursor.execute("SELECT LastSeen, UUID FROM Servers WHERE Type = 'Slave'")
    results = cursor.fetchall()
    for row in results:
        if (timestamp - row[0]) > timedelta(seconds=30):
            print "Removing stale slave server %s" % row[1]
            cursor.execute("DELETE FROM Servers WHERE Type = 'Slave' AND UUID = %s", (str(row[1])))
            cursor.execute("DELETE FROM Connectivity WHERE SlaveServerUUID = %s", (str(row[1])))
    db.close()
    return True


def remove_stale_storage_servers():
    """



    @rtype : object
    @return:
    """
    db = utility.dbconnect()
    timestamp = datetime.now()
    cursor = db.cursor()
    cursor.execute("SELECT LastSeen, UUID FROM Servers WHERE Type = 'Storage'")
    results = cursor.fetchall()
    for row in results:
        if (timestamp - row[0]) > timedelta(seconds=30):
            print "Removing stale storage server %s" % row[1]
            cursor2 = db.cursor()
            cursor2.execute("SELECT UUID FROM Storage WHERE ServerUUID = %s", str(row[1]))
            results2 = cursor2.fetchall()
            for row2 in results2:
                cursor.execute("DELETE FROM Connectivity WHERE StorageUUID = %s", (str(row2[0])))
            cursor.execute("DELETE FROM Storage WHERE ServerUUID = %s", (str(row[1])))
            cursor.execute("DELETE FROM Servers WHERE Type = 'Storage' AND UUID = %s", (str(row[1])))
    db.close()
    return True


def usage():
    #TODO usage
    """



    @rtype : none
    """
    print "\nUsage: master_server.py: [options]"
    print "-h / --help : help"
    print "-d [address:{port}] / --database [ip address:{port}] : specify the fflock database\n"



def main(argv):
    """


    @rtype : none
    @param argv:
    """

    try:
        opts, args = getopt.getopt(argv, "hd:", ["help", "database="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        if opt in ("-d", "--database"):
            globals.DATABASE_HOST = arg.split(':', 1)[0]
            globals.DATABASE_PORT = arg.split(':', 1)[-1]
            if globals.DATABASE_PORT == globals.DATABASE_HOST:
                globals.DATABASE_PORT = 3306

    while True:
        register_master_server(_uuid)
        remove_stale_slave_servers()
        remove_stale_storage_servers()
        time.sleep(5)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = utility.get_uuid()
    _localip = utility.local_ip_address()
    _publicip = utility.public_ip_address()
    main(sys.argv[1:])
