#!/usr/bin/python

import sys
import os
import time
import glob
import signal
import getopt
import threading
from multiprocessing import Process
from modules import fflock_threadpool
from datetime import datetime
from xml.dom import minidom
from subprocess import PIPE, Popen
from modules import fflock_globals
from modules import fflock_utility


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
            #print "Registering Storage Server %s heartbeat at %s" % (_uuid, timestamp)
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
        volumeuuid = fflock_utility.get_uuid()
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


def fetch_db_jobs():
    """


    @return:
    """
    cursor = _db.cursor()
    cursor.execute(
        "SELECT UUID, JobType, JobSubType, Command, CommandPreOptions, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID FROM Jobs WHERE AssignedServerUUID = '%s' AND Assigned = '%s' AND State = '%s'" % (
            _uuid, 1, 0))
    results = cursor.fetchall()
    for row in results:
        jobuuid = row[0]
        jobtype = row[1]
        jobsubtype = row[2]
        command = row[3]
        commandpreoptions = row[4]
        commandoptions = row[5]
        jobinput = row[6]
        joboutput = row[7]
        storageuuid = row[8]

        if not fflock_utility.check_dependencies(jobuuid):
            continue
        fflock_utility.remove_dependency_jobs(jobuuid)

        # check to see if this storage server is busy
        serverstatecursor = _db.cursor()
        serverstatecursor.execute("SELECT UUID, State FROM Servers WHERE UUID = '%s'" % _uuid)
        serverstateresults = serverstatecursor.fetchone()
        # if this server is not busy then fetch next job
        if serverstateresults[1] < 10:
            cursor2 = _db.cursor()
            cursor2.execute("SELECT LocalPathNFS, PublicPathNFS FROM Storage WHERE UUID = '%s'" % storageuuid)
            result2 = cursor2.fetchone()

            nfsmountpath = result2[0].split(':', 1)[-1]

            # prepend nfs mount path to input and output file

            # if mux job, split inputs and add path before each
            if jobsubtype == "a/v mux":
                jobinput_list = jobinput.split(',')
                jobinput = ""
                for input in jobinput_list:
                    jobinput = jobinput + " -i " + nfsmountpath + input
                joboutput = nfsmountpath + joboutput
            elif jobsubtype == "http download" or jobsubtype == "ftp download" or jobsubtype == "s3 download":
                joboutput = nfsmountpath + joboutput
            elif jobsubtype == "ftp upload" or jobsubtype == "s3 upload":
                jobinput = nfsmountpath + jobinput
            elif jobsubtype == "cleanup":
                jobinput = jobinput
                joboutput = joboutput
            else:
                jobinput = nfsmountpath + jobinput
                joboutput = nfsmountpath + joboutput

            # run the job
            threadpool.add_task(run_job, jobuuid, jobtype, jobsubtype, command, commandpreoptions, commandoptions, jobinput, joboutput)
            #run_job(jobuuid, jobtype, jobsubtype, command, commandpreoptions, commandoptions, jobinput, joboutput)

    return True


def run_job(jobuuid, jobtype, jobsubtype, command, commandpreoptions, commandoptions, jobinput, joboutput):
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

    cursor = _db.cursor()
    # set server as busy and job as active
    cursor.execute("UPDATE Jobs SET State='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (1, jobuuid, _uuid))
    cursor.execute("UPDATE Servers SET State='%s' WHERE UUID='%s'" % (1, _uuid))

    if jobsubtype == "cleanup":
        fflock_utility.job_cleanup(jobuuid, commandpreoptions, commandoptions, jobinput, joboutput)
        # delete the cleanup job
        cursor.execute("DELETE FROM Jobs WHERE UUID='%s'" % jobuuid)

    elif jobsubtype == "http download":
        fflock_utility.download_file_http(jobinput, joboutput)
        #t1 = Process(target=fflock_utility.download_file_http, args=[jobinput, joboutput])
        #t1 = threading.Thread(target=fflock_utility.download_file_http, args=[jobinput, joboutput])
        #t1.start()
        ##while t1.isAlive():
        ##    time.sleep(3)
        ##    register_storage_server()

    elif jobsubtype == "ftp download":
        fflock_utility.download_file_ftp(jobinput, joboutput)
        #t2 = Process(target=fflock_utility.download_file_ftp, args=[jobinput, joboutput])
        #t2.start()
        #while t2.isAlive():
        #    time.sleep(3)
        #    register_storage_server()

    elif jobsubtype == "s3 download":
        fflock_utility.download_file_s3(jobinput, joboutput)
        #t3 = Process(target=fflock_utility.download_file_s3, args=[jobinput, joboutput])
        #t3.start()
        #while t3.isAlive():
        #    time.sleep(3)
        #    register_storage_server()

    elif jobsubtype == "ftp upload":
        fflock_utility.upload_file_ftp(jobinput, joboutput)
        #t4 = Process(target=fflock_utility.upload_file_ftp, args=[jobinput, joboutput])
        #t4.start()
        #while t4.isAlive():
        #    time.sleep(3)
        #    register_storage_server()

    elif jobsubtype == "s3 upload":
        fflock_utility.upload_file_s3(jobinput, joboutput)
        #t5 = Process(target=fflock_utility.upload_file_s3, args=[jobinput, joboutput])
        #t5.start()
        #while t5.isAlive():
        #    time.sleep(3)
        #    register_storage_server()

    else:
        jobcommand = command % (commandpreoptions, jobinput, commandoptions, joboutput)
        print "Executing storage job:", jobcommand
        print commandpreoptions
        print jobinput
        print commandoptions
        print joboutput
        proc = Popen(jobcommand, shell=True, stdout=PIPE)

        while proc.poll() is None:
            time.sleep(3)
            #register_storage_server()
        print proc.returncode

    # set server as free and job as finished
    if jobsubtype != "cleanup":
        cursor.execute("UPDATE Jobs SET State='%s', Progress='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (2, 100, jobuuid, _uuid))

    cursor.execute("UPDATE Servers SET State='%s' WHERE UUID='%s'" % (0, _uuid))

    return True


def check_xml_submits():
    """


    @rtype : Boolean
    @return:
    """
    submitfiles = fflock_globals.NFS_PATH

    if submitfiles[-1:] != "/":
        submitfiles += "/"
    submitfiles += "*.xml"
    for file in glob.glob(submitfiles):
        submitted = 0
        print "Submitting jobs from: ", file
        # parse job file
        xmldoc = minidom.parse(file)
        joblist = xmldoc.getElementsByTagName('job')
        for s in joblist:
            submitted = 1
            type = s.attributes['type'].value
            input = s.attributes['input'].value
            output = s.attributes['output'].value
            preoptions = s.attributes['preoptions'].value
            options = s.attributes['options'].value
            joboptions = s.attributes['joboptions'].value

            encodercmd = fflock_globals.ENCODER
            job_options = joboptions.split(",")
            for option in job_options:
                if option == "encoder=ffmbc": encodercmd = "ffmbc"
                if option == "encoder=avconv": encodercmd = "avconv"

            commandstring = "%s -y -i %s %s %s" % (encodercmd, "%s", "%s", "%s")

            if type == "transcode":
                storageuuid = fflock_utility.find_server_storage_UUIDs(_uuid)
                fflock_utility.ensure_dir(output, storageuuid)
                fflock_utility.submit_job("", "Master", "transcode", commandstring, preoptions, options, input,
                                   output, "", "", joboptions)

        # delete the submitted xml file
        if submitted == 1:
            #os.rename(file, file + ".submitted")
            os.remove(file)
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
        opts, args = getopt.getopt(argv, "hd:n:s:c:", ["help", "database=", "nfs=", "s3=", "config="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        if opt in ("-d", "--database"):
            fflock_globals.DATABASE_HOST = arg.split(':', 1)[0]
            fflock_globals.DATABASE_PORT = arg.split(':', 1)[-1]
            if fflock_globals.DATABASE_PORT == fflock_globals.DATABASE_HOST:
                fflock_globals.DATABASE_PORT = 3306
        if opt in ("-n", "--nfs"):
            storage = arg
            if storage[-1:] != "/":
                storage += "/"
            #if opt in ("-s", "--s3"):
        #    fflock_globals.S3BUCKET = arg
        if opt in ("-c", "--config"):
            fflock_globals.CONFIG_FILE = arg
    return storage


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = fflock_utility.get_uuid()
    _localip = fflock_utility.local_ip_address()
    _publicip = fflock_utility.public_ip_address()
    fflock_globals.NFS_PATH = parse_cmd(sys.argv[1:])
    if fflock_globals.CONFIG_FILE != "":
        fflock_utility.parse_config_file(fflock_globals.CONFIG_FILE, "storage")
    _db = fflock_utility.dbconnect()
    threadpool = fflock_threadpool.ThreadPool(20)

    while True:
        if register_storage_server():
            register_storage_volume(fflock_globals.NFS_PATH)
        check_slave_connectivity()
        check_xml_submits()
        fetch_db_jobs()
        #job_cleanup()
        time.sleep(2)