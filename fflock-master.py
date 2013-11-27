#!/usr/bin/python

import sys
import os
import time
import signal
import getopt
import glob
from datetime import datetime, timedelta
from modules import fflock_globals
from modules import fflock_utility


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
    cursor = _db.cursor()
    cursor.execute("DELETE FROM Servers WHERE ServerType = 'Master' AND UUID = '%s'" % (str(_uuid)))
    _db.close()


def register_master_server(uuid):
    """


    @rtype : boolean
    @param uuid:
    @return:
    """
    timestamp = datetime.now()

    cursor = _db.cursor()
    cursor.execute("SELECT LocalIP, PublicIP, LastSeen, UUID, ServerType FROM Servers WHERE ServerType = 'Master'")
    results = cursor.fetchone()

    if results is None:
        cursor.execute(
            "INSERT INTO Servers(LocalIP, PublicIP, ServerType, LastSeen, UUID, State) VALUES('%s','%s','%s','%s','%s','%s')" % (
                _localip, _publicip, 'Master', timestamp, uuid, 0))
        print "Server successfully registered as the Master Server running on [L}%s / [P}%s on %s" % (
            _localip, _publicip, timestamp)
    else:
        if results[0] == _localip and results[1] == _publicip and str(results[3]) == str(uuid):
            #print "Registering Master Server %s heartbeat at %s" % (_uuid, timestamp)
            cursor.execute(
                "UPDATE Servers SET LastSeen = '%s' WHERE LocalIP = '%s' AND PublicIP = '%s' AND ServerType = 'Master' AND UUID = '%s'" % (
                    timestamp, _localip, _publicip, uuid))
        elif (timestamp - results[2]) > timedelta(seconds=30):
            print "The Master Server running on [L]%s / [P]%s but heartbeat has not been detected for more than 30 seconds." % (
                results[0], results[1])
            print "Registering this server as the Master Server"
            cursor.execute("DELETE FROM Servers WHERE ServerType = 'Master'")
            register_master_server(uuid)
        else:
            print "A Master Server is actively running on [L]%s / [P]%s. Last heartbeat was seen on %s" % (
                results[0], results[1], results[2])
            sys.exit(1)

    _db.commit()
    return True


def remove_stale_slave_servers():
    """



    @rtype : object
    @return:
    """
    timestamp = datetime.now()
    cursor = _db.cursor()
    cursor.execute("SELECT LastSeen, UUID, ServerType FROM Servers WHERE ServerType = 'Slave'")
    results = cursor.fetchall()
    for row in results:
        if (timestamp - row[0]) > timedelta(seconds=60):
            print "Removing stale slave server %s" % row[1]
            cursor.execute("DELETE FROM Servers WHERE ServerType = 'Slave' AND UUID = '%s'" % (str(row[1])))
            cursor.execute("DELETE FROM Connectivity WHERE SlaveServerUUID = '%s'" % (str(row[1])))
    return True


def remove_stale_connectivity_entries():
    """



    @rtype : boolean
    """
    deletecursor = _db.cursor()
    connectivitycursor = _db.cursor()
    connectivitycursor.execute("SELECT StorageUUID FROM Connectivity")
    connectivityresults = connectivitycursor.fetchall()
    for connectivityrow in connectivityresults:
        storagecursor = _db.cursor()
        storagecursor.execute("SELECT UUID FROM Storage")
        storageresults = storagecursor.fetchall()
        keep = 0
        for storagerow in storageresults:
            if connectivityrow[0] == storagerow[0]:
                keep = 1
        if keep == 0:
            print "Removing stale connectivity entry with StorageUUID", connectivityrow[0]
            deletecursor.execute("DELETE FROM Connectivity WHERE StorageUUID = '%s'" % connectivityrow[0])
    return True


def remove_stale_storage_servers():
    """



    @rtype : object
    @return:
    """
    timestamp = datetime.now()
    cursor = _db.cursor()
    cursor.execute("SELECT LastSeen, UUID, ServerType FROM Servers WHERE ServerType = 'Storage'")
    results = cursor.fetchall()
    for row in results:
        if (timestamp - row[0]) > timedelta(seconds=30):
            print "Removing stale storage server %s" % row[1]
            cursor2 = _db.cursor()
            cursor2.execute("SELECT UUID, ServerUUID FROM Storage WHERE ServerUUID = '%s'" % str(row[1]))
            results2 = cursor2.fetchall()
            for row2 in results2:
                cursor.execute("DELETE FROM Connectivity WHERE StorageUUID = '%s'" % (str(row2[0])))
            cursor.execute("DELETE FROM Storage WHERE ServerUUID = '%s'" % (str(row[1])))
            cursor.execute("DELETE FROM Servers WHERE ServerType = 'Storage' AND UUID = '%s'" % (str(row[1])))
    return True


def remove_orphaned_storage_confirmation_files():
    """


    @rtype : boolean
    @return:
    """
    storagecursor = _db.cursor()
    servercursor = _db.cursor()
    storagecursor.execute("SELECT UUID FROM Storage")
    storageresults = storagecursor.fetchall()
    for storagerow in storageresults:
        storagepath = fflock_utility.get_storage_nfs_folder_path(storagerow[0])
        todelete = storagepath + "*-*-*-*-*"
        for file in glob.glob(todelete):
            servercursor.execute("SELECT UUID FROM Servers")
            serverresults = servercursor.fetchall()
            delete = 1
            for serverrow in serverresults:
                serveruuidfile = storagepath + serverrow[0]
                if serveruuidfile == file:
                    delete = 0
            storageuuidfile = storagepath + storagerow[0]
            if storageuuidfile == file:
                delete = 0
            if delete == 1:
                print "Removing orphaned storage confirmation file", file
                os.remove(file)
    return True


def reassign_orphaned_jobs():
    reassigncursor = _db.cursor()
    servercursor = _db.cursor()
    servercursor.execute("SELECT UUID FROM Servers")
    serverresults = servercursor.fetchall()
    jobcursor = _db.cursor()
    jobcursor.execute("SELECT UUID, JobType, AssignedServerUUID FROM Jobs")
    jobresults = jobcursor.fetchall()
    for jobrow in jobresults:
        assigned = 0
        if jobrow[1] == "Slave":
            for serverrow in serverresults:
                if jobrow[2] == serverrow[0]:
                    assigned = 1
                else:
                    continue
            if assigned == 0:
                assigned_server = fflock_utility.find_server_for_slave_job()
                print "Reassigning orphaned job", jobrow[0], "to slave server", assigned_server
                reassigncursor.execute("UPDATE Jobs SET AssignedServerUUID='%s', State=0 WHERE UUID='%s'" % (assigned_server, jobrow[0]))

    return True


def download_external_source(jobuuid, storageuuid, jobinput, masteruuid):
    """



    @rtype : boolean
    """
    download_uuid = " "
    jobfileinput = jobinput
    if jobinput.startswith("http://") or jobinput.startswith("https://"):
        download_uuid = fflock_utility.get_uuid()
        jobfileinput = jobinput.split('/')[-1]
        fflock_utility.submit_job(download_uuid, "Storage", "http download", " ", " ", " ", jobinput, jobfileinput, " ",
                           masteruuid, "")
    if jobinput.startswith("ftp://"):
        download_uuid = fflock_utility.get_uuid()
        jobfileinput = jobinput.split('/')[-1]
        fflock_utility.submit_job(download_uuid, "Storage", "ftp download", " ", " ", " ", jobinput, jobfileinput, " ",
                           masteruuid, "")
    if jobinput.startswith("s3://"):
        download_uuid = fflock_utility.get_uuid()
        jobfileinput = jobinput.split('/')[-1]
        fflock_utility.submit_job(download_uuid, "Storage", "s3 download", " ", " ", " ", jobinput, jobfileinput, " ",
                           masteruuid, "")

    return download_uuid, jobfileinput


def upload_external_destination(jobuuid, storageuuid, source, joboutput, dependencies, masteruuid):
    """



    @rtype : boolean
    """
    upload_uuid = " "
    if joboutput.startswith("ftp://"):
        upload_uuid = fflock_utility.get_uuid()
        fflock_utility.submit_job(upload_uuid, "Storage", "ftp upload", " ", " ", " ", source, joboutput, dependencies,
                           masteruuid, "")
    if joboutput.startswith("s3://"):
        upload_uuid = fflock_utility.get_uuid()
        fflock_utility.submit_job(upload_uuid, "Storage", "s3 upload", " ", " ", " ", source, joboutput, dependencies,
                           masteruuid, "")

    return upload_uuid


def remap_output(jobuuid, storageuuid, joboutput, masteruuid):
    """



    @rtype : boolean
    """
    download_uuid = " "
    jobfileoutput = joboutput
    if joboutput.startswith("ftp://"):
        jobfileoutput = joboutput.split('/')[-1]
    if joboutput.startswith("s3://"):
        jobfileoutput = joboutput.split('/')[-1]
    return jobfileoutput


def fetch_jobs():
    """



    @rtype : boolean
    """
    jobcursor = _db.cursor()
    jobcursor.execute(
        "SELECT UUID, JobType, JobSubType, Command, CommandPreOptions, CommandOptions, JobInput, JobOutput, Assigned, State, AssignedServerUUID, StorageUUID, Priority, Dependencies, MasterUUID, Progress, ResultValue1, ResultValue2, JobOptions FROM Jobs")
    jobresults = jobcursor.fetchall()

    for jobrow in jobresults:
        jobuuid = jobrow[0]
        jobtype = jobrow[1]
        jobsubtype = jobrow[2]
        command = jobrow[3]
        commandpreoptions = jobrow[4]
        commandoptions = jobrow[5]
        jobinput = jobrow[6]
        joboutput = jobrow[7]
        jobassigned = jobrow[8]
        jobstate = jobrow[9]
        jobassignedserveruuid = jobrow[10]
        storageuuid = jobrow[11]
        jobpriority = jobrow[12]
        jobdependencies = jobrow[13]
        masteruuid = jobrow[14]
        jobprogress = jobrow[15]
        resultsvalue1 = jobrow[16]
        resultsvalue2 = jobrow[17]
        joboptions = jobrow[18]

        source_dependencies = ""

        # deal with master jobs
        if jobtype == "Master":
            if jobsubtype == "transcode":

                if jobstate == 0:
                    source_dependencies, jobinput = download_external_source("", storageuuid, jobinput, jobuuid)

                    updatecursor = _db.cursor()
                    updatecursor.execute("UPDATE Jobs SET State='%s' WHERE UUID='%s'" % (1, jobuuid))
                    detect_frames_job_uuid = fflock_utility.get_uuid()
                    fflock_utility.submit_job(detect_frames_job_uuid, "Slave", "detect frames", " ", commandpreoptions,
                                       commandoptions, jobinput, joboutput, source_dependencies, jobuuid, joboptions)

                # if master job is in progress, check state of child jobs and delete them if they are done
                if jobstate == 1:
                    child_jobs = 0
                    childcursor = _db.cursor()
                    childcursor.execute(
                        "SELECT JobSubType, MasterUUID, State FROM Jobs WHERE MasterUUID='%s'" % (jobuuid))
                    childresults = childcursor.fetchall()
                    for row in childresults:
                        if row[0] == "detect frames":
                            child_jobs += 1
                        elif row[2] < 2:
                            child_jobs += 1

                    if child_jobs == 0:
                        childcursor.execute("DELETE FROM Jobs WHERE MasterUUID='%s' AND State='%s'" % (jobuuid, 2))
                        childcursor.execute("UPDATE Jobs SET State='%s' WHERE UUID='%s'" % (2, jobuuid))

                # master job's children are all finished
                if jobstate == 2:

                    print "\n------ Job", jobuuid, "finished successfully ---------"
                    print "------ Source:", jobinput
                    print "------ Output:", joboutput

                    job_options = joboptions.split(",")
                    for option in job_options:
                        if option == "confirm_framecount":
                            if resultsvalue1 < resultsvalue2:
                                print "------ Transcoded file has", int(resultsvalue2) - int(
                                    resultsvalue1), "more frames than the source."
                            if resultsvalue1 > resultsvalue2:
                                print "------ Transcoded file has", int(resultsvalue1) - int(
                                    resultsvalue2), "less frames than the source."
                            if resultsvalue1 == resultsvalue2:
                                print "------ Source and Transcoded file have the same number of frames:", resultsvalue1

                    cleanup_uuid = fflock_utility.get_uuid()
                    fflock_utility.submit_job(cleanup_uuid, "Storage", "cleanup", " ", storageuuid, jobuuid, jobinput, joboutput, " ", jobuuid, "")


        # if detect frames job is done, initiate split-stitch transcode process
        if jobtype == "Slave" and jobsubtype == "detect frames" and jobstate == 2:
            deletecursor = _db.cursor()
            deletecursor.execute("DELETE FROM Jobs WHERE UUID = '%s'" % jobuuid)

            mux_dependencies = ""
            upload_dependencies = ""

            joboutput_original = joboutput
            joboutput = remap_output(jobuuid, storageuuid, joboutput, masteruuid)

            # create audio demux job
            demuxjob_uuid = fflock_utility.get_uuid()
            audio_demuxed_filetype = ".mkv"
            audio_demuxed_file = joboutput + "_audio" + audio_demuxed_filetype

            encodercmd = fflock_globals.ENCODER
            job_options = joboptions.split(",")

            for option in job_options:
                if option == "encoder=ffmbc": encodercmd = "ffmbc"
                if option == "encoder=avconv": encodercmd = "avconv"

            commandstring = "%s %s -i %s %s %s" % (encodercmd, "%s", "%s", "%s", "%s")
            preoptions = commandpreoptions + "-y "
            options = commandoptions + "-vn -strict -2"
            fflock_utility.submit_job(demuxjob_uuid, "Slave", "audio demux", commandstring, preoptions, options, jobinput,
                               audio_demuxed_file,
                               mux_dependencies, masteruuid, "")
            mux_dependencies += str(demuxjob_uuid)

            merge_dependencies, merge_textfile = split_transcode_job(jobuuid, command, commandpreoptions,
                                                                     commandoptions, jobinput, joboutput, storageuuid,
                                                                     masteruuid, resultsvalue1, resultsvalue2,
                                                                     joboptions)

            # create merge job
            mergejob_uuid = fflock_utility.get_uuid()
            outfilename, outfileextension = os.path.splitext(joboutput)
            joboutput_video = joboutput + "_video" + outfileextension
            fflock_utility.submit_job(mergejob_uuid, "Storage", "video merge", "ffmpeg %s -i %s %s  %s", "-y -f concat",
                               "-c copy", merge_textfile, joboutput_video,
                               merge_dependencies, masteruuid, "")
            if mux_dependencies[-1:] != ",":
                mux_dependencies += ","
            mux_dependencies += str(mergejob_uuid)

            # create audio/video mux job
            muxinput = joboutput_video + "," + audio_demuxed_file
            muxjob_uuid = fflock_utility.get_uuid()
            upload_dependencies += str(muxjob_uuid)
            fflock_utility.submit_job(muxjob_uuid, "Storage", "a/v mux", "ffmpeg %s %s %s  %s", "-y",
                               "-vcodec copy -acodec copy -strict -2", muxinput, joboutput, mux_dependencies,
                               masteruuid, "")

            job_options = fflock_utility.find_job_options_for_job(masteruuid).split(",")
            for option in job_options:
                if option == "confirm_framecount":
                    framecount1_uuid = fflock_utility.get_uuid()
                    fflock_utility.submit_job(framecount1_uuid, "Slave", "count frames",
                                       "ffprobe -show_frames %s | grep -c media_type=video", " ", "input", jobinput,
                                       " ", muxjob_uuid, masteruuid, "")
                    if len(str(upload_dependencies)) > 1 and upload_dependencies[-1:] != ",":
                        upload_dependencies += ","
                    upload_dependencies += str(framecount1_uuid)
                    framecount2_uuid = fflock_utility.get_uuid()
                    fflock_utility.submit_job(framecount2_uuid, "Slave", "count frames",
                                       "ffprobe -show_frames %s | grep -c media_type=video", " ", "output", joboutput,
                                       " ", muxjob_uuid, masteruuid, "")
                    if upload_dependencies[-1:] != ",":
                        upload_dependencies += ","
                    upload_dependencies += str(framecount2_uuid)

            upload_uuid = upload_external_destination(jobuuid, storageuuid, joboutput, joboutput_original,
                                                      upload_dependencies, masteruuid)

    return True


def split_transcode_job(jobuuid, command, commandpreoptions, commandoptions, jobinput, joboutput, storageuuid,
                        masteruuid, resultsvalue1, resultsvalue2, joboptions):
    """



    @rtype : boolean
    """

    keyframes = resultsvalue1.split(",")
    keyframes_diff = resultsvalue2.split(",")

    # determine how many active slaves exist
    num_slaves = fflock_utility.number_of_registered_slaves()
    # determine length of each sub-clip

    storage_nfs_path = fflock_utility.get_storage_nfs_folder_path(storageuuid)

    outfilename, outfileextension = os.path.splitext(joboutput)
    merge_textfile = joboutput + "_mergeinput.txt"
    mergefiletext = ""
    keyframe_index = 0
    end_of_keyframes = 0

    # create a uuid for the merge file creation job
    mergefile_uuid = fflock_utility.get_uuid()
    merge_dependencies = str(mergefile_uuid) + ","

    # create transcode jobs for each sub-clip
    for num in range(0, num_slaves):
        print "Splitting Job", jobuuid, "into part", num
        preoptions = commandpreoptions
        options = commandoptions

        # if last keyframe, dont specify time period
        if keyframes_diff[keyframe_index] == "-1":
            end_of_keyframes = 1
            ffmpeg_startstop = "-ss %f -y" % float(keyframes[keyframe_index])
        else:
            ffmpeg_startstop = "-ss %f -t %f" % (
            float(keyframes[keyframe_index]), float(keyframes_diff[keyframe_index]))

        #preoptions += ffmpeg_startstop
        options += "-an "
        options += ffmpeg_startstop

        encodercmd = fflock_globals.ENCODER
        job_options = joboptions.split(",")
        for option in job_options:
            if option == "encoder=ffmbc": encodercmd = "ffmbc"
            if option == "encoder=avconv": encodercmd = "avconv"

        commandstring = "%s -y -i %s %s %s" % (encodercmd, "%s", "%s", "%s")

        slavejobuuid = fflock_utility.submit_job("", "Slave", "transcode", commandstring, preoptions, options, jobinput,
                                          joboutput + "_part" + str(num) + outfileextension, "", masteruuid, joboptions)
        keyframe_index += 1
        merge_dependencies += str(slavejobuuid)
        merge_dependencies += ","

        # write the merge textfile for ffmpeg concat
        #mergefiletext += 'file ' + '"' + storage_nfs_path + joboutput + '_part' + str(num) + outfileextension + '"' + "\n"
        mergefiletext += "file " + storage_nfs_path + joboutput + "_part" + str(num) + outfileextension + "\n"
        # if number of keyframes is less than number of slave servers, break
        if end_of_keyframes == 1:
            break

    # trim off the last comma on the dependencies list
    if merge_dependencies[-1:] == ",":
        merge_dependencies = merge_dependencies[:-1]

    fflock_utility.submit_job(mergefile_uuid, "Slave", "write mergefile", " ", " ", " ", mergefiletext, merge_textfile, "", masteruuid, "")

    return merge_dependencies, merge_textfile


def cleanup_tasks():
    """



    @rtype : none
    """
    remove_stale_slave_servers()
    remove_stale_storage_servers()
    remove_stale_connectivity_entries()
    remove_orphaned_storage_confirmation_files()
    reassign_orphaned_jobs()
    return True


def load_balance():

    return True


def usage():
    """



    @rtype : none
    """
    print "\nUsage: master_server.py: [options]"
    print "-h / --help : help"
    print "-d [address:{port}] / --database [ip address:{port}] : specify the fflock database\n"


def parse_cmd(argv):
    """


    @rtype : none
    @param argv:
    """

    try:
        opts, args = getopt.getopt(argv, "hd:c:", ["help", "database=", "config="])
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
        if opt in ("-c", "--config"):
            fflock_globals.CONFIG_FILE = arg
    return True


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    _uuid = fflock_utility.get_uuid()
    _localip = fflock_utility.local_ip_address()
    _publicip = fflock_utility.public_ip_address()

    parse_cmd(sys.argv[1:])
    if fflock_globals.CONFIG_FILE != "":
        fflock_utility.parse_config_file(fflock_globals.CONFIG_FILE, "master")
    _db = fflock_utility.dbconnect()

    while True:
        register_master_server(_uuid)
        fetch_jobs()
        cleanup_tasks()
        load_balance()
        time.sleep(2)