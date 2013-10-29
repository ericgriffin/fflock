#!/usr/bin/python

import globals
from datetime import datetime
import utility
from subprocess import PIPE, Popen
import signal
import sys
import getopt


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
    #utility.submit_job("", "Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test.mpg", "test1_OUT.mov", "", "", "")
    #utility.submit_job("", "Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test2.mpg", "test2_OUT.mov", "", "", "")
    utility.submit_job("", "Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test3.mxf", "test3_OUT.mov", "", "", "")
    #submit_job("Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test4.wmv", "test4_OUT.mov", "", "", "")
    #submit_job("Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test5.mpg", "test5_OUT.mov", "", "", "")
    #submit_job("Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test6.mov", "test6_OUT.mov", "", "", "")
    #submit_job("Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test7.avi", "test7_OUT.mov", "", "", "")
    #submit_job("Slave", "frames", "ffmpeg -y -i %s %s %s", " -c:v prores -profile:v 3 -quant_mat hq -vendor ap10 -flags ildct+ilme -c:a pcm_s24le -ac 2 ", "test8.mxf", "test8_OUT.mov", "", "", "")


if __name__ == "__main__":
    _uuid = utility.get_uuid()
    _timestamp = datetime.now()
    main(sys.argv[1:])
