#!/usr/bin/python

import os
import time
from datetime import datetime
import utility
from subprocess import PIPE, Popen
import signal
import sys
import getopt


def signal_handler(signal, frame):
    """


    @rtype : none
    @param signal:
    @param frame:
    """
    #unload()
    sys.exit(0)


def unload():
    """


    """
    print "\nunloading"
    db = utility.dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT SlaveServerUUID, StorageUUID, IPType, Connected FROM Connectivity WHERE SlaveServerUUID=%s", _uuid)
    results = cursor.fetchall()
    nfsmount = "-1"
    for row in results:
        cursor2 = db.cursor()
        if row[2] == "Local" and row[3] == 1:
            cursor2.execute("SELECT LocalPathNFS FROM Storage WHERE UUID=%s", row[1])
            results2 = cursor2.fetchone()
            nfsmount = results2[0]
        elif row[2] == "Public" and row[3] == 1:
            cursor2.execute("SELECT PublicPathNFS FROM Storage WHERE UUID=%s", row[1])
            results2 = cursor2.fetchone()
            nfsmount = results2[0]
        nfsmountpath = nfsmount.split(':', 1)[-1]
        unmountnfsshare = "umount -l %s" % nfsmountpath
        if os.path.ismount(nfsmountpath):
            print "Un-mounting NFS share ", nfsmountpath
            Popen(unmountnfsshare, shell=True)
    cursor.execute("DELETE FROM Servers WHERE Type = 'Slave' AND UUID = %s", (str(_uuid)))
    cursor.execute("DELETE FROM Connectivity WHERE SlaveServerUUID = %s", (str(_uuid)))
    db.close()


def register_slave_server():
    """



    @rtype : boolean
    @return:
    """
    db = utility.dbconnect()
    timestamp = datetime.now()

    cursor = db.cursor()
    cursor.execute("SELECT LocalIP, PublicIP, LastSeen, UUID FROM Servers WHERE Type = 'Slave'")
    results = cursor.fetchall()

    server_already_registered = 0

    for row in results:
        if row[0] == _localip and row[1] == _publicip and str(row[3]) == str(_uuid):
            print "Registering Slave Server %s heartbeat at %s" % (_uuid, timestamp)
            cursor.execute("UPDATE Servers SET LastSeen = %s WHERE LocalIP = %s AND PublicIP = %s AND Type = 'Slave' AND UUID = %s", (timestamp, _localip, _publicip, _uuid))
            server_already_registered = 1
    if server_already_registered == 0:
        cursor.execute('INSERT INTO Servers(LocalIP, PublicIP, Type, LastSeen, UUID, State) VALUES(%s,%s,%s,%s,%s,%s)', (_localip, _publicip, 'Slave', timestamp, _uuid, 0))
        print "Server successfully registered as a Slave Server running on [L}%s / [P}%s on %s" % (_localip, _publicip, timestamp)

    db.commit()
    db.close()
    return True


def calculate_connectivity():
    """



    @rtype : boolean
    """
    db = utility.dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT UUID, LocalPathNFS, PublicPathNFS FROM Storage")
    results = cursor.fetchall()
    latency = -1

    for row in results:
        connection_already_exists = 0
        localfolderpath = row[1].split(':', 1)[-1]
        localserveraddress = row[1].split(':', 1)[0]
        publicfolderpath = row[2].split(':', 1)[-1]
        publicserveraddress = row[2].split(':', 1)[0]
        localserverlatency = utility.ping(localserveraddress)
        publicserverlatency = utility.ping(publicserveraddress)

        if localserverlatency != 9999 and localserverlatency < publicserverlatency:
            iptype = "Local"
            latency = localserverlatency
        if publicserverlatency != 9999 and publicserverlatency < localserverlatency:
            iptype = "Public"
            latency = publicserverlatency

        if latency != -1:
            cursor2 = db.cursor()
            cursor2.execute("SELECT SlaveServerUUID, StorageUUID FROM Connectivity")
            results2 = cursor2.fetchall()
            for row2 in results2:
                if(str(row2[0]) == str(_uuid) and str(row2[1]) == str(row[0])):
                    cursor.execute("UPDATE Connectivity SET Latency = %s, IPType = %s WHERE SlaveServerUUID = %s AND StorageUUID = %s", (latency, iptype, _uuid, row[0]))
                    connection_already_exists = 1
            if connection_already_exists == 0:
                cursor.execute('INSERT INTO Connectivity(SlaveServerUUID, StorageUUID, Latency, IPType, Connected) VALUES(%s,%s,%s,%s,%s)', (_uuid, row[0], localserverlatency, iptype, 0))
        else:
            print "No connectivity to Storage Server %s" % row[0]
    db.close()
    return True


def mount_storage():
    """



    @rtype : boolean
    """
    db = utility.dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT SlaveServerUUID, StorageUUID, IPType, Connected FROM Connectivity WHERE SlaveServerUUID=%s", _uuid)
    results = cursor.fetchall()

    for row in results:
        cursor2 = db.cursor()
        nfsmount = "-1"
        if row[2] == "Local":
            cursor2.execute("SELECT LocalPathNFS FROM Storage WHERE UUID=%s", row[1])
            results2 = cursor2.fetchone()
            nfsmount = results2[0]
        elif row[2] == "Public":
            cursor2.execute("SELECT PublicPathNFS FROM Storage WHERE UUID=%s", row[1])
            results2 = cursor2.fetchone()
            nfsmount = results2[0]
        if nfsmount != "-1":
            nfsmountpath = nfsmount.split(':', 1)[-1]
            mountnfsshare = "mount -o rw -t nfs %s %s" % (nfsmount, nfsmountpath)
            if not os.path.exists(nfsmountpath):
                print "Creating ", nfsmountpath
                os.makedirs(nfsmountpath)
            if not os.path.ismount(nfsmountpath):
                print "Mounting NFS share ", nfsmountpath
                joblist=[]
                joblist.append(Popen(mountnfsshare, shell=True))
                joblist[0].wait()
            # if storage is not connected
            if row[3] != 1:
                if check_nfs_connectivity(nfsmountpath, row[1]):
                    cursor3 = db.cursor()
                    cursor3.execute("UPDATE Connectivity SET Connected=%s WHERE SlaveServerUUID=%s AND StorageUUID=%s", (1, _uuid, row[1]))
                else:
                    unmountnfsshare = "umount -l %s" % nfsmountpath
                    joblist=[]
                    joblist.append(Popen(unmountnfsshare, shell=True))
                    joblist[0].wait()
    db.close()
    return True


def check_nfs_connectivity(nfsmountpath, storageuuid):
    """


    @rtype : boolean
    @param nfsmountpath:
    @param storageserveruuid:
    @return:
    """
    retval = False
    print "Checking storage %s" % storageuuid
    filename = "%s%s" % (nfsmountpath, _uuid)
    filename_confirm = "%s%s" % (nfsmountpath, storageuuid)
    testfile = open(filename, "w")
    testfile.write(storageuuid)
    testfile.close()
    time.sleep(10)
    # check for confirmation file
    if os.path.exists(filename_confirm):
        testfileconfirm = open(filename_confirm, "r")
        line = testfileconfirm.readline()
        if line == str(_uuid):
            testfileconfirm.close()
            os.remove(filename)
            os.remove(filename_confirm)
            retval = True

    if retval == False:
        print "Storage not ready"
    if retval == True:
        print "Storage access confirmed"
    return retval


def check_storage_connected(storageuuid):
    """


    @rtype : boolean
    @param storageuuid:
    @return:
    """
    db = utility.dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT Connected, IPType FROM Connectivity WHERE SlaveServerUUID = %s AND StorageUUID = %s", (_uuid, storageuuid))
    results = cursor.fetchall()
    isconnected = "No"
    for row in results:
        if row[0] == 1:
            if row[1] == "Local":
                isconnected = "Local"
            if row[1] == "Public":
                isconnected = "Public"
    db.close()
    return isconnected


def fetch_jobs():
    """


    @return:
    """
    db = utility.dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT UUID, Type, Command, CommandOptions, Input, Output, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, Active, AssignedServerUUID FROM Jobs WHERE AssignedServerUUID = %s AND Assigned = %s AND Active = %s", (_uuid, 1, 0))
    results = cursor.fetchall()
    for row in results:
        jobuuid = row[0]
        type = row[1]
        command = row[2]
        commandoptions = row[3]
        input = row[4]
        output = row[5]
        storageuuid = row[6]

        connected_type = check_storage_connected(storageuuid)

        nfsmountpath = ""
        cursor2 = db.cursor()
        cursor2.execute("SELECT LocalPathNFS, PublicPathNFS FROM Storage WHERE ServerUUID = %s", storageuuid)
        result2 = cursor2.fetchone()

        if connected_type == "Local":
            nfsmountpath = result2[0].split(':', 1)[-1]
        if connected_type == "Public":
            nfsmountpath = result2[1].split(':', 1)[-1]

        #prepend nfs mount path to input and output file
        input = nfsmountpath + input
        output = nfsmountpath + output

        print input, " ", output

        if connected_type != "No":
            cursor2.execute("UPDATE Jobs SET Active=%s WHERE UUID=%s AND AssignedServerUUID=%s", (1, jobuuid, _uuid))
            run_job(type, command, commandoptions, input, output)
        else:
            print "Slave server has no connectivity to storage server %s" % row[4]
    db.close()
    return True


def run_job(type, command, commandoptions, input, output):
    """


    @rtype : boolean
    @param type:
    @param command:
    @param commandoptions:
    @param input:
    @param output:
    @return:
    """
    jobcommand = command % (commandoptions, input, output)
    print jobcommand
    Popen(jobcommand, shell=True)
    return True


def usage():
    #TODO usage
    """


    @rtype : none
    """
    print "\nUsage: slave_server.py: [options]"
    print "-h / --help : help"
    print "-p [path] / --path [path] : specify temporary storage mount path\n"



def main(argv):
    """


    @rtype : none
    @param argv:
    """

    try:
        opts, args = getopt.getopt(argv, "hp:", ["help", "path="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-p", "--path"):
            path = arg

    while True:
        register_slave_server()
        calculate_connectivity()
        mount_storage()
        fetch_jobs()
        time.sleep(5)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = utility.get_uuid()
    _localip = utility.local_ip_address()
    _publicip = utility.public_ip_address()
    main(sys.argv[1:])


