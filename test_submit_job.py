#!/usr/bin/python

import globals
from datetime import datetime
import utility
from subprocess import PIPE, Popen
import signal
import sys
import getopt


def find_server_for_storage_job():
    """



    @rtype : storage server uuid
    @return:
    """
    return ""


def find_server_for_slave_job():
    """



    @rtype : slave server uuid
    @return:
    """
    db = utility.dbconnect()
    slavecursor = db.cursor()
    slavecursor.execute("SELECT UUID, ServerType, State FROM Servers WHERE ServerType = '%s'" % "Slave")
    slaveresults = slavecursor.fetchall()

    #find best slave server to assign the job
    shortest_queue = 1000000
    server_with_shortest_queue = ""
    for slaverow in slaveresults:
        current_queue = 0
        slaveserveruuid = slaverow[0]
        jobcursor = db.cursor()
        jobcursor.execute(
            "SELECT JobType, Assigned, State, AssignedServerUUID, Priority, Dependencies, Progress FROM Jobs WHERE AssignedServerUUID = '%s'" % str(
                slaveserveruuid))
        jobresults = jobcursor.fetchall()
        for jobrow in jobresults:
            current_queue += 1
        if current_queue < shortest_queue:
            server_with_shortest_queue = slaveserveruuid
            shortest_queue = current_queue
    return server_with_shortest_queue


def find_storage_UUID_for_job():
    """



    @rtype : storage uuid
    @return:
    """
    storageuuid = ""
    db = utility.dbconnect()
    storagecursor = db.cursor()
    storagecursor.execute("SELECT UUID FROM Storage WHERE StorageType = '%s'" % "NFS")
    storageresults = storagecursor.fetchall()
    for storagerow in storageresults:
        storageuuid = storagerow[0]
    return storageuuid


def submit_job(jobtype, jobsubtype, command, commandoptions, input, output, dependencies, masteruuid):
    """


    @rtype : boolean
    @param jobtype:
    @param command:
    @param commandoptions:
    @param input:
    @param output:
    """
    db = utility.dbconnect()

    storageuuid = find_storage_UUID_for_job()
    assignedserveruuid = "NA"
    if jobtype == "Slave":
        assignedserveruuid = find_server_for_slave_job()
    elif jobtype == "Storage":
        assignedserveruuid = find_server_for_storage_job()

    if masteruuid == "":
        masteruuid = utility.get_uuid()
    jobuuid = utility.get_uuid()
    jobinputcursor = db.cursor()
    jobinputcursor.execute(
        "INSERT INTO Jobs(UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, Assigned, State, AssignedServerUUID, StorageUUID, MasterUUID, Priority, Dependencies, Progress, AssignedTime, CreatedTime, ResultValue1, ResultValue2) VALUES('%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s')" %
        (jobuuid, jobtype, jobsubtype, command, commandoptions, input, output, 1, 0, assignedserveruuid, storageuuid,
         masteruuid, 1, dependencies, 0, _timestamp, _timestamp, "", ""))
    db.close()
    return True


def main(argv):
    """


    @rtype : none
    @param argv:
    """

    try:
        opts, args = getopt.getopt(argv, "hd:", ["help", "database="])
    except getopt.GetoptError:
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            sys.exit()
        if opt in ("-d", "--database"):
            globals.DATABASE_HOST = arg.split(':', 1)[0]
            globals.DATABASE_PORT = arg.split(':', 1)[-1]
            if globals.DATABASE_PORT == globals.DATABASE_HOST:
                globals.DATABASE_PORT = 3306

    jobtype = "Slave"
    jobsubtype = "transcode"
    command = "ffmpeg %s -i %s %s"
    commandoptions = " "
    input = "test.mov"
    output = "Final.mp4"

    #submit_job(jobtype, jobsubtype, command, commandoptions, input, output, dependencies, masteruuid)
    #submit_job("Slave", "transcode", "ffmpeg %s -i %s %s", " ", "1.mp4", "Final1.avi", "", "")
    #submit_job("Slave", "transcode", "ffmpeg %s -i %s %s", " ", "test.mov", "Final.mp4", "", "")

    #submit_job("Slave", "frames", "ffmpeg %s -i %s %s", " ", "test.mov", "Final.mp4", "")
    submit_job("Slave", "frames", "ffmpeg -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test.mpg", "test_OUT.mov", "", "")


if __name__ == "__main__":
    _uuid = utility.get_uuid()
    _timestamp = datetime.now()
    main(sys.argv[1:])
