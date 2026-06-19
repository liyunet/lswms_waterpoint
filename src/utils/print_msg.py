"""
@author: cyoung
Created on Jun 5, 2018
Description: Functions for printing message on command prompt and log file.
Updated on:
    08/01/2018 - CYOUNG - added print_Msg_orig() - function to print and
                    log_file.write() based on current lib processes.
    08/20/2018 - CYOUNG - added setLogger() for the print() and
                    log_file.write() using logging module.
    04/25/2019 - cholen - Added get_traceback_msg
    04/30/2019 - cholen - Adjusted traceback message to Claudia's version
    04/25/2019 - CYOUNG - added print_process_info() and log_process_info()
                    to add process information with command, ppg doc link, and
                    log path.
"""
# Import standard modules
import logging
import traceback

def printMsg_orig(msg, log_file):
    # function with original print and log_file.write()
    print(msg)
    log_file.write("\n" + msg)


def printMsg(msg, log_file):
    # function with print and log_file to open, write, and close
    print(msg)
    log_file = open(log_file, 'a+')
    log_file.write("\n" + msg)
    log_file.close()


def setLogger(log_path):
    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)

    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO) #logging.DEBUG)

    # Include filename and line number in the format
    # log_format = '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    log_format = '%(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    formatter = logging.Formatter(log_format)

    ch.setFormatter(formatter)
    fh.setFormatter(formatter)

    # add the handlers to logger
    logger.addHandler(ch)
    logger.addHandler(fh)

    return logger

