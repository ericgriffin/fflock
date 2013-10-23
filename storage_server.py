#!/usr/bin/python

import globals
import time
import sys
import os
import utility
import signal
import getopt
import glob
from subprocess import PIPE, Popen
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
    cursor = _db.cursor()
    cursor.execute("SELECT UUID, ServerUUID FROM Storage WHERE ServerUUID = '%s'" % str(_uuid))
    results = cursor.fetchall()
    cursor.execute("DELETE FROM Storage WHERE ServerUUID = '%s'", (str(_uuid)))
    cursor.execute("DELETE FROM Servers WHERE ServerType = 'Storage' AND UUID = '%s'" % (str(_uuid)))
    for row in results:
        cursor.execute("DELETE FROM Connectivity WHERE StorageUUID = '%s'" % (str(row[0])))
    _db.close()
    return True


def register_storage_server():
    """



    @rtype : object
    @return:
    """
    timestamp = datetime.now()

    cursor = _db.cursor()
    cursor.execute("SELECT LocalIP, PublicIP, LastSeen, UUID FROM Servers WHERE ServerType = 'Storage'")
    results = cursor.fetchall()

    server_already_registered = 0

    for row in results:
        if row[0] == _localip and row[1] == _publicip and str(row[3]) == str(_uuid):
            print "Registering Storage Server %s heartbeat at %s" % (_uuid, timestamp)
            cursor.execute(
                "UPDATE Servers SET LastSeen = '%s' WHERE LocalIP = '%s' AND PublicIP = '%s' AND ServerType = 'Storage' AND UUID = '%s'" % (
                    timestamp, _localip, _publicip, _uuid))
            server_already_registered = 1
    if server_already_registered == 0:
        cursor.execute(
            "INSERT INTO Servers(LocalIP,PublicIP, ServerType, LastSeen, UUID, State) VALUES('%s','%s','%s','%s','%s','%s')" % (
                _localip, _publicip, 'Storage', timestamp, _uuid, 0))
        print "Server successfully registered as a Storage Server running on [L}%s / [P}%s on %s" % (
            _localip, _publicip, timestamp)

    _db.commit()
    return True


def register_storage_volume(path):
    """


    @rtype : object
    @param path:
    @return:
    """
    storagetype = "NFS"
    localpathnfs = _localip + ":" + path
    publicpathnfs = _publicip + ":" + path
    if publicpathnfs[-1:] != "/":
        publicpathnfs += "/"
    if localpathnfs[-1:] != "/":
        localpathnfs += "/"

    cursor = _db.cursor()
    cursor.execute("SELECT ServerUUID, LocalPathNFS, PublicPathNFS FROM Storage WHERE ServerUUID = '%s'" % _uuid)
    results = cursor.fetchall()

    volume_already_registered = 0

    for row in results:
        if str(row[0]) == str(_uuid) and row[1] == localpathnfs and row[2] == publicpathnfs:
            volume_already_registered = 1
    if volume_already_registered == 0:
        volumeuuid = utility.get_uuid()
        cursor.execute(
            "INSERT INTO Storage(UUID, ServerUUID, StorageType, LocalPathNFS, PublicPathNFS) VALUES('%s','%s','%s','%s','%s')" % (
                volumeuuid, _uuid, storagetype, localpathnfs, publicpathnfs))
        print "Volume %s on server %s has been registered" % (volumeuuid, _uuid)
    return True


def check_slave_connectivity():
    """



    @rtype : object
    """
    cursor0 = _db.cursor()
    cursor0.execute("SELECT UUID, ServerUUID, LocalPathNFS FROM Storage WHERE ServerUUID = '%s'" % _uuid)
    results0 = cursor0.fetchall()
    for row0 in results0:
        storageuuid = row0[0]
        localpathnfs = row0[2]
        cursor = _db.cursor()
        cursor.execute(
            "SELECT SlaveServerUUID, StorageUUID, Connected FROM Connectivity WHERE StorageUUID = '%s' AND Connected = 0" % storageuuid)
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
    return True


def fetch_jobs():
    """


    @return:
    """
    cursor = _db.cursor()
    cursor.execute(
        "SELECT UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID FROM Jobs WHERE AssignedServerUUID = '%s' AND Assigned = '%s' AND State = '%s'" % (
            _uuid, 1, 0))
    results = cursor.fetchall()
    for row in results:
        jobuuid = row[0]
        jobtype = row[1]
        jobsubtype = row[2]
        command = row[3]
        commandoptions = row[4]
        jobinput = row[5]
        joboutput = row[6]
        storageuuid = row[7]

        if not utility.check_dependencies(jobuuid):
            break
        utility.remove_dependency_jobs(jobuuid)

        # check to see if this storage server is busy
        serverstatecursor = _db.cursor()
        serverstatecursor.execute("SELECT UUID, State FROM Servers WHERE UUID = '%s'" % _uuid)
        serverstateresults = serverstatecursor.fetchone()
        # if this server is not busy then fetch next job
        if serverstateresults[1] == 0:
            cursor2 = _db.cursor()
            cursor2.execute("SELECT LocalPathNFS, PublicPathNFS FROM Storage WHERE UUID = '%s'" % storageuuid)
            result2 = cursor2.fetchone()

            nfsmountpath = result2[0].split(':', 1)[-1]

            # prepend nfs mount path to input and output file
            jobinput = nfsmountpath + jobinput
            joboutput = nfsmountpath + joboutput

            print jobinput, " ", joboutput

            # set server as busy and job as active
            cursor2.execute(
                "UPDATE Jobs SET State='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (1, jobuuid, _uuid))
            cursor2.execute("UPDATE Servers SET State='%s' WHERE UUID='%s'" % (1, _uuid))
            # run the job
            run_job(jobuuid, jobtype, jobsubtype, command, commandoptions, jobinput, joboutput)
            # set server as free and job as finished
            cursor2.execute(
                "UPDATE Jobs SET State='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (2, jobuuid, _uuid))
            cursor2.execute("UPDATE Servers SET State='%s' WHERE UUID='%s'" % (0, _uuid))
    return True


def run_job(jobuuid, jobtype, jobsubtype, command, commandoptions, jobinput, joboutput):
    """



    @param jobinput:
    @param joboutput:
    @rtype : boolean
    @param jobtype:
    @param command:
    @param commandoptions:
    @param jobinput:
    @param joboutput:
    @return:
    """
    jobcommand = command % (commandoptions, jobinput, joboutput)
    proc = Popen(jobcommand, shell=True, stdout=PIPE)

    while proc.poll() is None:
        time.sleep(3)
        register_storage_server()
    print proc.returncode
    return True


def job_cleanup():
    """


    @rtype : Boolean
    @return:
    """
    jobcursor = _db.cursor()
    deletecursor = _db.cursor()
    jobcursor.execute(
        "SELECT UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID FROM Jobs WHERE AssignedServerUUID = '%s' AND Assigned = '%s' AND State = '%s'" % (
            _uuid, 1, 2))
    jobresults = jobcursor.fetchall()
    for jobrow in jobresults:
        jobuuid = jobrow[0]
        jobtype = jobrow[1]
        jobsubtype = jobrow[2]
        joboutput = jobrow[6]
        storageuuid = jobrow[7]
        if jobtype == "Storage" and jobsubtype == "merge":
            todelete = utility.get_storage_nfs_folder_path(storageuuid) + joboutput + "_*"
            for file in glob.glob(todelete):
                print "delete ", file
                os.remove(file)
            deletecursor.execute("DELETE FROM Jobs WHERE UUID='%s'" % jobuuid)
    return True


def usage():
    """


    @rtype : none
    """
    print "\nUsage: storage_server.py: [options]"
    print "-h / --help : help"
    print "-d [address:{port}] / --database [ip address:{port}] : specify the fflock database"
    print "-n [path] / --nfs [path] : specify NFS storage path"
    print "-s [path] / --s3 [path] : specify AWS S3 storage path\n"


def parse_cmd(argv):
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
                storage += "/"
        if opt in ("-s", "--s3"):
            storage = arg
    return storage


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = utility.get_uuid()
    _localip = utility.local_ip_address()
    _publicip = utility.public_ip_address()
    storage = parse_cmd(sys.argv[1:])
    _db = utility.dbconnect()

    while True:
        if register_storage_server():
            register_storage_volume(storage)
        check_slave_connectivity()
        fetch_jobs()
        job_cleanup()
        time.sleep(5)