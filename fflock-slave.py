#!/usr/bin/python

import sys
import os
import time
import signal
import getopt
import csv
import StringIO
from datetime import datetime
from subprocess import PIPE, Popen
from modules import fflock_globals
from modules import fflock_utility
from modules import fflock_encoder


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


    """
    print "\nunloading"
    connectivitycursor = _db.cursor()
    connectivitycursor.execute(
        "SELECT SlaveServerUUID, StorageUUID, IPType, Connected FROM Connectivity WHERE SlaveServerUUID='%s'" % _uuid)
    connectivityresults = connectivitycursor.fetchall()
    nfsmount = "-1"
    for connectivityrow in connectivityresults:
        storagecursor = _db.cursor()

        storagecursor.execute(
            "SELECT LocalPathNFS, PublicPathNFS, UUID FROM Storage WHERE UUID='%s'" % connectivityrow[1])
        storageresults = storagecursor.fetchone()
        if connectivityrow[2] == "Local" and connectivityrow[3] == 1:
            nfsmount = storageresults[0]
        elif connectivityrow[2] == "Public" and connectivityrow[3] == 1:
            nfsmount = storageresults[1]

        nfsmountpath = nfsmount.split(':', 1)[-1]
        nfsmountpath = fflock_globals.SLAVE_MOUNT_PREFIX_PATH + nfsmountpath
        unmountnfsshare = "umount -l %s" % nfsmountpath
        if os.path.ismount(nfsmountpath):
            print "Un-mounting NFS share ", nfsmountpath
            Popen(unmountnfsshare, shell=True)
    connectivitycursor.execute("DELETE FROM Servers WHERE ServerType = 'Slave' AND UUID='%s'" % (str(_uuid)))
    connectivitycursor.execute("DELETE FROM Connectivity WHERE SlaveServerUUID='%s'" % (str(_uuid)))
    _db.close()
    return True


def register_slave_server():
    """



    @rtype : boolean
    @return:
    """
    timestamp = datetime.now()

    cursor = _db.cursor()
    cursor.execute("SELECT LocalIP, PublicIP, LastSeen, UUID FROM Servers WHERE ServerType = 'Slave'")
    results = cursor.fetchall()

    server_already_registered = 0

    for row in results:
        if row[0] == _localip and row[1] == _publicip and str(row[3]) == str(_uuid):
            #print "Registering Slave Server %s heartbeat at %s" % (_uuid, timestamp)
            cursor.execute(
                "UPDATE Servers SET LastSeen = '%s' WHERE LocalIP = '%s' AND PublicIP = '%s' AND ServerType = 'Slave' AND UUID = '%s'" % (
                    timestamp, _localip, _publicip, _uuid))
            server_already_registered = 1
    if server_already_registered == 0:
        cursor.execute(
            "INSERT INTO Servers(LocalIP, PublicIP, ServerType, LastSeen, UUID, State) VALUES('%s','%s','%s','%s','%s','%s')" % (
                _localip, _publicip, 'Slave', timestamp, _uuid, 0))
        print "Server successfully registered as a Slave Server running on [L}%s / [P}%s on %s" % (
            _localip, _publicip, timestamp)

    _db.commit()
    return True


def calculate_connectivity():
    """



    @rtype : boolean
    """
    cursor = _db.cursor()
    cursor.execute("SELECT UUID, LocalPathNFS, PublicPathNFS FROM Storage")
    results = cursor.fetchall()
    latency = -1

    for row in results:
        connection_already_exists = 0
        localserveraddress = row[1].split(':', 1)[0]
        publicserveraddress = row[2].split(':', 1)[0]
        localserverlatency = fflock_utility.ping(localserveraddress)
        publicserverlatency = fflock_utility.ping(publicserveraddress)

        if publicserverlatency != 9999 and publicserverlatency < localserverlatency:
            iptype = "Public"
            latency = publicserverlatency
        if localserverlatency != 9999 and localserverlatency < publicserverlatency:
            iptype = "Local"
            latency = localserverlatency

        if latency != -1:
            cursor2 = _db.cursor()
            cursor2.execute(
                "SELECT SlaveServerUUID, StorageUUID FROM Connectivity WHERE SlaveServerUUID ='%s' AND StorageUUID = '%s'" % (
                    _uuid, row[0]))
            results2 = cursor2.fetchall()
            for row2 in results2:
                cursor.execute(
                    "UPDATE Connectivity SET Latency = '%s', IPType = '%s' WHERE SlaveServerUUID = '%s' AND StorageUUID = '%s'" % (
                        latency, iptype, _uuid, row[0]))
                connection_already_exists = 1
            if connection_already_exists == 0:
                print "Adding connectivity information between slave %s and storage %s" % (_uuid, row[0])
                cursor.execute(
                    "INSERT INTO Connectivity(SlaveServerUUID, StorageUUID, Latency, IPType, Connected) VALUES('%s','%s','%s','%s','%s')" % (
                        _uuid, row[0], localserverlatency, iptype, 0))
        else:
            print "No connectivity to Storage Server %s" % row[0]
    return True


def mount_storage():
    """



    @rtype : boolean
    """
    connectivitycursor = _db.cursor()
    connectivitycursor.execute(
        "SELECT SlaveServerUUID, StorageUUID, IPType, Connected FROM Connectivity WHERE SlaveServerUUID='%s'" % _uuid)
    connectivityresults = connectivitycursor.fetchall()

    for connectivityrow in connectivityresults:
        storageuuid = connectivityrow[1]
        iptype = connectivityrow[2]
        connected = connectivityrow[3]

        storagecursor = _db.cursor()
        nfsmount = "-1"

        storagecursor.execute("SELECT LocalPathNFS, PublicPathNFS FROM Storage WHERE UUID='%s'" % storageuuid)
        storageresults = storagecursor.fetchone()
        if storageresults is not None:
            if iptype == "Local":
                nfsmount = storageresults[0]
            elif iptype == "Public":
                nfsmount = storageresults[1]

        if nfsmount != "-1":
            nfsmountpath = nfsmount.split(':', 1)[-1]
            nfsmountpath = fflock_globals.SLAVE_MOUNT_PREFIX_PATH + nfsmountpath

            mountnfsshare = "mount -o rw -t nfs %s %s" % (nfsmount, nfsmountpath)
            if not os.path.exists(nfsmountpath):
                print "Creating ", nfsmountpath
                os.makedirs(nfsmountpath)
            if not os.path.ismount(nfsmountpath):
                print "Mounting NFS share %s" % nfsmountpath
                joblist = []
                joblist.append(Popen(mountnfsshare, shell=True))
                joblist[0].wait()
                # if storage is not connected
            if connected != 1:
                if check_nfs_connectivity(nfsmountpath, storageuuid):
                    cursor3 = _db.cursor()
                    cursor3.execute(
                        "UPDATE Connectivity SET Connected='%s' WHERE SlaveServerUUID='%s' AND StorageUUID='%s'" % (
                            1, _uuid, storageuuid))
                else:
                    print "Un-mounting NFS share %s" % nfsmountpath
                    unmountnfsshare = "umount -l %s" % nfsmountpath
                    joblist = []
                    joblist.append(Popen(unmountnfsshare, shell=True))
                    joblist[0].wait()
    return True


def check_nfs_connectivity(nfsmountpath, storageuuid):
    """


    @rtype : boolean
    @param nfsmountpath:
    @param storageuuid:
    @return:
    """
    retval = False
    print "Checking storage %s" % storageuuid
    filename = "%s%s" % (nfsmountpath, _uuid)
    filename_confirm = "%s%s" % (nfsmountpath, storageuuid)
    testfile = open(filename, "w")
    testfile.write(storageuuid)
    testfile.close()
    time.sleep(2)
    # check for confirmation file
    if os.path.exists(filename_confirm):
        testfileconfirm = open(filename_confirm, "r")
        line = testfileconfirm.readline()
        if line == str(_uuid):
            testfileconfirm.close()
            os.remove(filename)
            os.remove(filename_confirm)
            retval = True

    if not retval:
        print "Storage not ready"
    if retval:
        print "Storage access confirmed"
    return retval


def check_storage_connected(storageuuid):
    """


    @rtype : boolean
    @param storageuuid:
    @return:
    """
    cursor = _db.cursor()
    cursor.execute("SELECT Connected, IPType FROM Connectivity WHERE SlaveServerUUID = '%s' AND StorageUUID = '%s'" % (
        _uuid, storageuuid))
    results = cursor.fetchall()
    isconnected = "No"
    for row in results:
        if row[0] == 1:
            if row[1] == "Local":
                isconnected = "Local"
            if row[1] == "Public":
                isconnected = "Public"
    return isconnected


def find_keyframes(file, type, space):
    """


    @rtype : integer
    @param file:
    @return:
    """
    jobcommand = "ffprobe -show_frames -select_streams %s -print_format csv %s" % (type, file)
    proc = Popen(jobcommand, shell=True, stdout=PIPE, stderr=PIPE)

    #while proc.poll() is None:
    #    print "keyframe job not done - waiting"
    #    time.sleep(3)
    #    register_slave_server()

    out, err = proc.communicate()
    keyframedata = csv.reader(StringIO.StringIO(out))

    fps = fflock_utility.getFps(file)
    totalframes = fflock_utility.getTotalFrames(file, fps)
    num_slaves = fflock_utility.number_of_registered_slaves()
    duration_per_job = float(totalframes) / float(fps) / int(num_slaves)

    keyframes = ["0.000000"]
    keyframe_diff = ["0.00000"]
    current = 0
    previous = 0
    previousrow_time = 0
    keyframe_index = 0

    print "Approximate duration per job:", duration_per_job

    for row in keyframedata:
        # find I-frames
        if row[2] == "1":
            current = row[4]
            print "Current:", current, "Previous:", previous, "Duration/job:", duration_per_job
            if float(current) - float(previous) >= float(duration_per_job):
                keyframes.append(row[4])
                keyframe_index += 1
                keyframe_diff.append("-1")
                if space == 1:
                    keyframe_diff[keyframe_index - 1] = str(
                        round(round(float(previousrow_time), 6) - round(float(keyframes[keyframe_index - 1]), 6), 6))
                if space == 0:
                    keyframe_diff[keyframe_index - 1] = str(
                        round(round(float(row[4]), 6) - round(float(keyframes[keyframe_index - 1]), 6), 6))
                previous = current
                #print "Splitting job at I-frame ", row[6]
        previousrow_time = row[4]

    print "Keyframe Times:", keyframes
    print "Time between keyframes:", keyframe_diff
    return keyframes, keyframe_diff


def fetch_db_jobs():
    """


    @return:
    """
    cursor = _db.cursor()
    cursor.execute(
        "SELECT UUID, JobType, JobSubType, Command, CommandPreOptions, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID, JobOptions FROM Jobs WHERE AssignedServerUUID = '%s' AND Assigned = '%s' AND State = '%s'" % (
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
        masteruuid = row[11]
        joboptions = row[15]

        if not fflock_utility.check_dependencies(jobuuid):
            continue
        fflock_utility.remove_dependency_jobs(jobuuid)

        # check to see if this slave server is busy
        serverstatecursor = _db.cursor()
        serverstatecursor.execute("SELECT UUID, State FROM Servers WHERE UUID = '%s'" % _uuid)
        serverstateresults = serverstatecursor.fetchone()
        if serverstateresults is None:
            continue
            # if this server is not busy then fetch next job
        if serverstateresults[1] == 0:
            # see if this server is connected to the storage
            connected_type = check_storage_connected(storageuuid)

            # if slave server is connected to the storage
            if connected_type != "No":
                nfsmountpath = ""
                cursor2 = _db.cursor()
                cursor2.execute("SELECT LocalPathNFS, PublicPathNFS FROM Storage WHERE UUID = '%s'" % storageuuid)
                result2 = cursor2.fetchone()

                if connected_type == "Local":
                    print "Running job %s from storage %s over Local network" % (jobuuid, storageuuid)
                    print result2[0]
                    nfsmountpath = result2[0].split(':', 1)[-1]
                if connected_type == "Public":
                    print "Running job %s from storage %s over Public network" % (jobuuid, storageuuid)
                    nfsmountpath = result2[1].split(':', 1)[-1]

                nfsmountpath = fflock_globals.SLAVE_MOUNT_PREFIX_PATH + nfsmountpath

                # prepend nfs mount path to input and output file
                jobinput = nfsmountpath + jobinput
                joboutput = nfsmountpath + joboutput

                # set server as busy and job as active
                cursor2.execute(
                    "UPDATE Jobs SET State='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (1, jobuuid, _uuid))
                cursor2.execute("UPDATE Servers SET State='%s' WHERE UUID='%s'" % (1, _uuid))
                # run the job
                run_job(jobuuid, jobtype, jobsubtype, command, commandpreoptions, commandoptions, jobinput, joboutput,
                        masteruuid, joboptions)
                # set server as free and job as finished
                cursor2.execute(
                    "UPDATE Jobs SET State='%s', Progress='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (
                    2, 100, jobuuid, _uuid))
                cursor2.execute("UPDATE Servers SET State='%s' WHERE UUID='%s'" % (0, _uuid))

            else:
                print "Slave server has no connectivity to storage server %s" % storageuuid
    return True


def run_job(jobuuid, jobtype, jobsubtype, command, commandpreoptions, commandoptions, jobinput, joboutput, master_uuid,
            joboptions):
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

    encodercmd = fflock_globals.ENCODER
    frame_space = 0
    job_options = joboptions.split(",")
    for option in job_options:
        if option == "encoder=ffmpeg": encodercmd = "ffmpeg"
        if option == "encoder=ffmbc":
            encodercmd = "ffmbc"
            frame_space = 1
        if option == "encoder=avconv": encodercmd = "avconv"

    # if ffmpeg job
    if jobsubtype == "transcode":

        encoder = fflock_encoder.fflock_encoder(jobinput, joboutput, commandpreoptions, commandoptions, encodercmd, True)
        encoder.start()
        shouldupdate = False

        while encoder.getProgress() != 100 or shouldupdate:
            fflock_utility.clear()
            # keep the server alive so it doesn't get removed by master
            register_slave_server()
            print "Args: %s\nProgress: %s complete\nElapsed: %s seconds\nEta: %s seconds" % (
                encoder.getArgs(), encoder.getProgress(), encoder.getElapsedTime(), encoder.getEta())
            cursor.execute("UPDATE Jobs SET Progress='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (
                encoder.getProgress(), jobuuid, _uuid))
            time.sleep(3)

            #allows looping to 100%
            if shouldupdate == True:
                break
            shouldupdate = (encoder.getProgress() == 100)

        print "FFmpeg finished with return code: %s" % (encoder.getReturnCode())
        if encoder.getReturnCode() == 0:
            print "Encode took %s seconds" % (encoder.getElapsedTime())
            print "Encoded at %s x realtime" % (float(encoder.getInputDuration()) / float(encoder.getElapsedTime()))
        else:
            print "An error has occured: %s" % (encoder.getLastOutput())

    elif jobsubtype == "detect frames":
        keyframes, keyframes_diff = find_keyframes(jobinput, "v", frame_space)
        keyframes_str = ','.join(map(str, keyframes))
        keyframes_diff_str = ','.join(map(str, keyframes_diff))
        cursor.execute(
            "UPDATE Jobs SET Progress='%s', ResultValue1='%s', ResultValue2='%s' WHERE UUID='%s' AND AssignedServerUUID='%s'" % (
                100, keyframes_str, keyframes_diff_str, jobuuid, _uuid))

    elif jobsubtype == "count frames":
        num_frames = 0
        jobcommand = command % jobinput
        print "Executing frame-count slave job:", jobcommand
        proc = Popen(jobcommand, shell=True, stdout=PIPE)

        while proc.poll() is None:
            time.sleep(3)
            register_slave_server()
        num_frames = proc.communicate()[0].strip('\n')
        print "Number of frames:", num_frames
        print "Commandoptions:", commandoptions
        if commandoptions == "input":
            cursor.execute("UPDATE Jobs SET ResultValue1='%s' WHERE UUID='%s'" % (str(num_frames), str(master_uuid)))
        if commandoptions == "output":
            cursor.execute("UPDATE Jobs SET ResultValue2='%s' WHERE UUID='%s'" % (str(num_frames), str(master_uuid)))

    # generic slave job
    else:
        jobcommand = command % (commandpreoptions, jobinput, commandoptions, joboutput)
        print "Executing generic slave job:", jobcommand
        proc = Popen(jobcommand, shell=True, stdout=PIPE)

        while proc.poll() is None:
            time.sleep(3)
            register_slave_server()
        print proc.returncode
    return True


def usage():
    """


    @rtype : none
    """
    print "\nUsage: slave_server.py: [options]"
    print "-h / --help : help"
    print "-d [address:{port}] / --database [ip address:{port}] : specify the fflock database"
    print "-m [path] / --mount [path] : specify temporary storage mount path\n"


def parse_cmd(argv):
    """


    @rtype : none
    @param argv:
    """

    try:
        opts, args = getopt.getopt(argv, "hd:m:c:", ["help", "database=", "mount=", "config="])
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
        if opt in ("-m", "--mount"):
            fflock_globals.SLAVE_MOUNT_PREFIX_PATH = arg
            if fflock_globals.SLAVE_MOUNT_PREFIX_PATH[-1:] == "/":
                fflock_globals.SLAVE_MOUNT_PREFIX_PATH = fflock_globals.SLAVE_MOUNT_PREFIX_PATH[:-1]
        if opt in ("-c", "--config"):
            fflock_globals.CONFIG_FILE = arg


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = fflock_utility.get_uuid()
    _localip = fflock_utility.local_ip_address()
    _publicip = fflock_utility.public_ip_address()
    parse_cmd(sys.argv[1:])
    if fflock_globals.CONFIG_FILE != "":
        fflock_utility.parse_config_file(fflock_globals.CONFIG_FILE, "slave")
    _db = fflock_utility.dbconnect()

while True:
    register_slave_server()
    calculate_connectivity()
    mount_storage()
    fetch_db_jobs()
    time.sleep(2)
