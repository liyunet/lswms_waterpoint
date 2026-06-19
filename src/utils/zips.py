'''
Filename: zip.py
@author: cyoung, lwood
Description: Module zips a list of files into a tar.gz and puts it in a
                specified directory
Updated on:
    06/25/2013 - CYOUNG - print name instead file when is closed
    11/18/2013 - CYOUNG - added function to create zip files
    01/10/2017 - CYOUNG - added function createGZip() to create Gzip files
    12/04/2018 - CYOUNG - improved unzipGZip() for monthly SM process and some
                    code improvements.
'''
#!/usr/bin/python
import os
import gzip
import traceback
import tarfile
import zipfile
import shutil

def unzip(zip_file, unzip_loc):
    try:
        fileObj = gzip.GzipFile(zip_file, 'rb')
        fileContent = fileObj.read()
        unzip = open(unzip_loc, 'wb')
        unzip.write(fileContent)
        print (str(zip_file) + " has been unzipped ")
        fileObj.close()
        unzip.close()
    except:
        print (traceback.print_exc())

    return 0


def unzipTar(zip_file, unzip_loc):

    # Unzip rfe into temp folder
    try:
        if os.path.exists(zip_file)and os.path.exists(unzip_loc):
            os.chdir(unzip_loc)
            # print "exists"
            tar = tarfile.open(zip_file)
            tar.extractall()
            tar.close()

        else:
            print (traceback.print_exc())

    except:
        print (traceback.print_exc())

    return 0
