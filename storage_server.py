#!/usr/bin/python

import globals
import time
import sys
import os
import utility
import signal
import getopt
from datetime import datetime, timedelta


def signal_handler(signal, frame):
    """


    @rtype : none
    @param signal:
    @param frame:
    """
    unload()
    sys.exit(0)


def unload():
    """



    @rtype : object
    """
    #TODO signal slave to unmount shares when storage server goes down (create job)
    print "\nunloading"
    db = utility.dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT UUID FROM Storage WHERE ServerUUID = %s", str(_uuid))
    results = cursor.fetchall()
    for row in results:
        cursor.execute("DELETE FROM Connectivity WHERE StorageUUID = %s", (str(row[0])))
    cursor.execute("DELETE FROM Storage WHERE ServerUUID = %s", (str(_uuid)))
    cursor.execute("DELETE FROM Servers WHERE ServerType = 'Storage' AND UUID = %s", (str(_uuid)))
    db.close()


def register_storage_server():
    """



    @rtype : object
    @return:
    """
    db = utility.dbconnect()
    timestamp = datetime.now()

    cursor = db.cursor()
    cursor.execute("SELECT LocalIP, PublicIP, LastSeen, UUID FROM Servers WHERE ServerType = 'Storage'")
    results = cursor.fetchall()

    server_already_registered = 0

    for row in results:
        if row[0] == _localip and row[1] == _publicip and str(row[3]) == str(_uuid):
            print "Registering Storage Server %s heartbeat at %s" % (_uuid, timestamp)
            cursor.execute("UPDATE Servers SET LastSeen = %s WHERE LocalIP = %s AND PublicIP = %s AND ServerType = 'Storage' AND UUID = %s", (timestamp, _localip, _publicip, _uuid))
            server_already_registered = 1
    if server_already_registered == 0:
        cursor.execute('INSERT INTO Servers(LocalIP,PublicIP, ServerType, LastSeen, UUID, State) VALUES(%s,%s,%s,%s,%s,%s)', (_localip, _publicip, 'Storage', timestamp, _uuid, 0))
        print "Server successfully registered as a Storage Server running on [L}%s / [P}%s on %s" % (_localip, _publicip, timestamp)

    db.commit()
    db.close()
    return True


def register_storage_volume(path):
    """


    @rtype : object
    @param path:
    @return:
    """
    db = utility.dbconnect()
    timestamp = datetime.now()

    storagetype = "NFS"
    localpathnfs = _localip + ":" + path
    publicpathnfs = _publicip + ":" + path

    cursor = db.cursor()
    cursor.execute("SELECT ServerUUID, LocalPathNFS, PublicPathNFS FROM Storage WHERE ServerUUID = %s", _uuid)
    results = cursor.fetchall()

    volume_already_registered = 0

    for row in results:
        if str(row[0]) == str(_uuid) and row[1] == localpathnfs and row[2] == publicpathnfs:
            volume_already_registered = 1
    if volume_already_registered == 0:
        volumeuuid = utility.get_uuid()
        cursor.execute('INSERT INTO Storage(UUID, ServerUUID, StorageType, LocalPathNFS, PublicPathNFS) VALUES(%s,%s,%s,%s,%s)', (volumeuuid, _uuid, storagetype, localpathnfs, publicpathnfs))
        print "Volume %s on server %s has been registered" % (volumeuuid, _uuid)
    db.close()
    return True


def check_slave_connectivity():
    """



    @rtype : object
    """
    db = utility.dbconnect()
    cursor0 = db.cursor()
    cursor0.execute("SELECT UUID, ServerUUID, LocalPathNFS FROM Storage WHERE ServerUUID = %s", _uuid)
    results0 = cursor0.fetchall()
    for row0 in results0:
        storageuuid = row0[0]
        localpathnfs = row0[2]
        cursor = db.cursor()
        cursor.execute("SELECT SlaveServerUUID, StorageUUID, Connected FROM Connectivity WHERE StorageUUID = %s AND Connected = 0", storageuuid)
        results = cursor.fetchall()
        for row in results:
            slaveserveruuid = row[0]
            nfsmountpath = localpathnfs.split(':', 1)[-1]
            connectivity_test_file = nfsmountpath + slaveserveruuid
            connectivity_test_file_confirm = nfsmountpath + storageuuid
            if os.path.isfile(connectivity_test_file):
                print "Confirming storage connection from slave %s" % slaveserveruuid
                file = open(connectivity_test_file, "r")
                line = file.readline()
                if line == str(storageuuid):
                    file.close()
                    file2 = open(connectivity_test_file_confirm, "w")
                    file2.write(slaveserveruuid)
                    file2.close()
                else:
                    print "Storage connection from slave %s failed" % slaveserveruuid
                    file.close()
    db.close()


def usage():
    """


    @rtype : none
    """
    print "\nUsage: storage_server.py: [options]"
    print "-h / --help : help"
    print "-d [address:{port}] / --database [ip address:{port}] : specify the fflock database"
    print "-n [path] / --nfs [path] : specify NFS storage path"
    print "-s [path] / --s3 [path] : specify AWS S3 storage path\n"


def main(argv):
    """


    @rtype : none
    @param argv:
    """
    storage = ""

    try:
        opts, args = getopt.getopt(argv, "hd:n:s:", ["help", "database=", "nfs=", "s3="])
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
        if opt in ("-n", "--nfs"):
            storage = arg
            if storage[-1:] != "/":
                storage = storage + "/"
        if opt in ("-s", "--s3"):
            storage = arg

    while True:
        if register_storage_server():
            register_storage_volume(storage)
        check_slave_connectivity()
        time.sleep(5)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = utility.get_uuid()
    _localip = utility.local_ip_address()
    _publicip = utility.public_ip_address()

    main(sys.argv[1:])
