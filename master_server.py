#!/usr/bin/python

import globals
import time
import sys
import os
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
    cursor.execute("DELETE FROM Servers WHERE ServerType = 'Master' AND UUID = %s", (str(_uuid)))
    db.close()


def register_master_server(uuid):
    """


    @rtype : boolean
    @param uuid:
    @return:
    """
    db = utility.dbconnect()
    timestamp = datetime.now()

    cursor = db.cursor()
    cursor.execute("SELECT LocalIP, PublicIP, LastSeen, UUID FROM Servers WHERE ServerType = 'Master'")
    results = cursor.fetchone()

    if results is None:
        cursor.execute('INSERT INTO Servers(LocalIP,PublicIP, ServerType, LastSeen, UUID, State) VALUES(%s,%s,%s,%s,%s,%s)', (_localip, _publicip, 'Master', timestamp, uuid, 0))
        print "Server successfully registered as the Master Server running on [L}%s / [P}%s on %s" % (_localip, _publicip, timestamp)
    else:
        if results[0] == _localip and results[1] == _publicip and str(results[3]) == str(uuid):
            print "Registering Master Server %s heartbeat at %s" % (_uuid, timestamp)
            cursor.execute("UPDATE Servers SET LastSeen = %s WHERE LocalIP = %s AND PublicIP = %s AND ServerType = 'Master' AND UUID = %s", (timestamp, _localip, _publicip, uuid))
        elif (timestamp - results[2]) > timedelta(seconds=30):
            print "The Master Server running on [L]%s / [P]%s but heartbeat has not been detected for more than 30 seconds." % (results[0], results[1])
            print "Registering this server as the Master Server"
            cursor.execute("DELETE FROM Servers WHERE ServerType = 'Master'")
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
    cursor.execute("SELECT LastSeen, UUID FROM Servers WHERE ServerType = 'Slave'")
    results = cursor.fetchall()
    for row in results:
        if (timestamp - row[0]) > timedelta(seconds=30):
            print "Removing stale slave server %s" % row[1]
            cursor.execute("DELETE FROM Servers WHERE ServerType = 'Slave' AND UUID = %s", (str(row[1])))
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
    cursor.execute("SELECT LastSeen, UUID FROM Servers WHERE ServerType = 'Storage'")
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
            cursor.execute("DELETE FROM Servers WHERE ServerType = 'Storage' AND UUID = %s", (str(row[1])))
    db.close()
    return True


def split_transcode_jobs():
    """



    @rtype : boolean
    """
    db = utility.dbconnect()
    timestamp = datetime.now()
    jobcursor = db.cursor()
    jobcursor.execute("SELECT UUID, JobType, JobSubType, Command, JobInput, JobOutput, Assigned, State, AssignedServerUUID, Priority, Dependencies, MasterUUID, Progress, ResultValue1, ResultValue2 FROM Jobs WHERE State = %s AND JobSubType = %s", (2, "frames"))
    jobresults = jobcursor.fetchall()

    for jobrow in jobresults:
        deletecursor = db.cursor()
        deletecursor.execute("DELETE FROM Jobs WHERE UUID = %s", jobrow[0])

        jobuuid = jobrow[0]
        jobinput = jobrow[4]
        joboutput = jobrow[5]
        masteruuid = jobrow[11]
        totalframes = jobrow[13]
        fps = jobrow[14]

        # determine how many active slaves exist
        num_slaves = number_of_registered_slaves()
        # determine length of each sub-clip
        duration_per_job = float(totalframes) / float(fps) / int(num_slaves)
        start = 0.0
        end = duration_per_job
        dependencies = ""
        # create transcode jobs for each sub-clip
        for num in range(0, num_slaves):
            print "Splitting Job ", jobuuid, " into part ", num
            outfilename, outfileextension = os.path.splitext(joboutput)
            ffmpeg_startstop = "-ss %f -t %f -y" % (start, end)
            jobuuid = submit_job("Slave", "transcode", "ffmpeg %s -i %s %s", ffmpeg_startstop, jobinput, joboutput + "_part" + str(num) + outfileextension, "", masteruuid)
            start += end + 1/float(fps)
            dependencies += str(jobuuid)
            dependencies += ","
        if dependencies[-1:] == ",":
            dependencies = dependencies[:-1]
        submit_job("Storage", "merge", "ffmpeg -f concat -i %s -c copy %s", " ", jobinput, joboutput + "_part" + str(num) + outfileextension, dependencies, masteruuid)


def find_storage_UUID_for_job():
    """



    @rtype : storage uuid
    @return:
    """
    storageuuid = ""
    db = utility.dbconnect()
    storagecursor = db.cursor()
    storagecursor.execute("SELECT UUID FROM Storage WHERE StorageType = %s", ("NFS"))
    storageresults = storagecursor.fetchall()
    for storagerow in storageresults:
        storageuuid = storagerow[0]
    return storageuuid


def find_server_for_storage_job():
    """



    @rtype : storage server uuid
    @return:
    """
    storageserveruuid = "NA"
    db = utility.dbconnect()
    storagecursor = db.cursor()
    storagecursor.execute("SELECT UUID, ServerType, State FROM Servers WHERE ServerType = %s", ("Storage"))
    storageresults = storagecursor.fetchall()

    #find best slave server to assign the job
    shortest_queue = 1000000
    server_with_shortest_queue = ""
    for storagerow in storageresults:
        current_queue = 0
        storageserveruuid = storagerow[0]
        jobcursor = db.cursor()
        jobcursor.execute("SELECT JobType, Assigned, State, AssignedServerUUID, Priority, Dependencies, Progress FROM Jobs WHERE AssignedServerUUID = %s", str(storageserveruuid))
        jobresults = jobcursor.fetchall()
        for jobrow in jobresults:
            current_queue += 1
        if current_queue < shortest_queue:
            server_with_shortest_queue = storageserveruuid
            shortest_queue = current_queue
    return server_with_shortest_queue


def find_server_for_slave_job():
    """



    @rtype : slave server uuid
    @return:
    """
    slaveserveruuid = "NA"
    db = utility.dbconnect()
    slavecursor = db.cursor()
    slavecursor.execute("SELECT UUID, ServerType, State FROM Servers WHERE ServerType = %s", ("Slave"))
    slaveresults = slavecursor.fetchall()

    #find best slave server to assign the job
    shortest_queue = 1000000
    server_with_shortest_queue = ""
    for slaverow in slaveresults:
        current_queue = 0
        slaveserveruuid = slaverow[0]
        jobcursor = db.cursor()
        jobcursor.execute("SELECT JobType, Assigned, State, AssignedServerUUID, Priority, Dependencies, Progress FROM Jobs WHERE AssignedServerUUID = %s", str(slaveserveruuid))
        jobresults = jobcursor.fetchall()
        for jobrow in jobresults:
            current_queue += 1
        if current_queue < shortest_queue:
            server_with_shortest_queue = slaveserveruuid
            shortest_queue = current_queue
    return server_with_shortest_queue


def number_of_registered_slaves():
    """


    @rtype : integer
    @return:
    """
    number_of_slaves = 0
    db = utility.dbconnect()
    slavecursor = db.cursor()
    slavecursor.execute("SELECT ServerType FROM Servers WHERE ServerType = %s", "Slave")
    slaveresults = slavecursor.fetchall()
    for slaverow in slaveresults:
        number_of_slaves = number_of_slaves + 1
    return number_of_slaves


def submit_job(jobtype, jobsubtype, command, commandoptions, input, output, dependencies):
    """


    @rtype : boolean
    @param jobtype:
    @param command:
    @param commandoptions:
    @param input:
    @param output:
    """
    db = utility.dbconnect()
    timestamp = datetime.now()


    storageuuid = find_storage_UUID_for_job()
    assignedserveruuid = ""
    if jobtype == "Slave":
        assignedserveruuid = find_server_for_slave_job()
    elif jobtype == "Storage":
        assignedserveruuid = find_server_for_storage_job()

    jobuuid = utility.get_uuid()
    jobinputcursor = db.cursor()
    jobinputcursor.execute(
        "INSERT INTO Jobs(UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, Assigned, State, AssignedServerUUID, StorageUUID, MasterUUID, Priority, Dependencies, Progress, AssignedTime, CreatedTime, ResultValue1, ResultValue2) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (jobuuid, jobtype, jobsubtype, command, commandoptions, input, output, 1, 0, assignedserveruuid, storageuuid, "0", 1, dependencies, 0, timestamp, timestamp, "", ""))
    db.close()
    return jobuuid


def usage():
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
        split_transcode_jobs()
        time.sleep(5)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = utility.get_uuid()
    _localip = utility.local_ip_address()
    _publicip = utility.public_ip_address()
    main(sys.argv[1:])
