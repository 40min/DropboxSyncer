#!/usr/bin/env python
from __future__ import print_function

import argparse
import contextlib
import datetime
import os
import six
import sys
import time
import unicodedata
import dropbox
import time

def read_access_token(token_file='access_token_file'):
    """ Extracts the access token from an external file 

    Returns the extracted access token
    """
    f = open(token_file)
    token = f.readlines()[0]
    return token

# OAuth2 access token.
TOKEN = read_access_token()

def compute_dir_index(path):
    """ Return a tuple containing:
    - list of files (relative to path)
    - lisf of subdirs (relative to path)
    - a dict: filepath => last 
    """
    files = []
    subdirs = []

    for root, dirs, filenames in os.walk(path):
        for subdir in dirs:
            subdirs.append(os.path.relpath(os.path.join(root, subdir), path))

        for f in filenames:
            files.append(os.path.relpath(os.path.join(root, f), path))
        
    index = {}
    for f in files:
        index[f] = os.path.getmtime(os.path.join(path, f))

    return dict(files=files, subdirs=subdirs, index=index)

def compute_diff(dir_base, dir_cmp):
    data = {}
    data['deleted'] = list(set(dir_cmp['files']) - set(dir_base['files']))
    data['created'] = list(set(dir_base['files']) - set(dir_cmp['files']))
    data['updated'] = []
    data['deleted_dirs'] = list(set(dir_cmp['subdirs']) - set(dir_base['subdirs']))

    for f in set(dir_cmp['files']).intersection(set(dir_base['files'])):
        if dir_base['index'][f] != dir_cmp['index'][f]:
            data['updated'].append(f)
    return data

def dropbox_changes(dbx, old_cursor):
    print("Dropbox changes called")
    changes = dbx.files_list_folder_continue(old_cursor)
    print("Changes: ", changes.entries)

    any_changes = False

    if len(changes.entries) > 0:
        any_changes = True
        for e in changes.entries:
            file_path = str(".") + str(e.path_display) #########
            print ("Filepath: ", file_path) 
            print("Processing file: ", e.path_display)
            if type(e) == dropbox.files.DeletedMetadata:
                os.remove(file_path)
            elif type(e) == dropbox.files.FileMetadata:
                if os.path.isfile(file_path):
                    # compare the time stamps
                    print ("mtime: ", os.stat(file_path).st_mtime)
                    t = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(os.path.getmtime(file_path))))
                    print("time time :", t)
                    t = datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
                    if t <= e.server_modified:
                        print(file_path, 'exists with different stats, downloading')
                        res = download_file(dbx, e.path_display)
                        with open(file_path) as f:
                            data = f.read()
                        if res == data:
                           print(name, 'is already synced [content match]')
                        else: # write this file
                            f=open(file_path,'w')
                            f.write(res)
                            f.close();
                    else:
                        with open(file_path, "rb") as f:
                            dbx.files_upload(f.read(), e.path_display, mute=True)
                else:
                    # download the file
                    res = download_file(dbx, e.path_display)
                    f=open(file_path,'w')
                    f.write(res)
                    f.close();
            else:
                print("Could upload or download (error with API ?")

    # return the latest cursor
    return get_current_cursor(dbx), any_changes

def get_current_cursor(dbx):
    a = dbx.files_list_folder_get_latest_cursor("/testfolder") ##########
    return a.cursor

def download_file(dbx, path):
    try:
        md, res = dbx.files_download(path)
    except dropbox.exceptions.HttpError as err:
        print('*** HTTP error', err)
        return None
    data = res.content
    print(len(data), 'bytes; md:', md)
    return data

def client_changes(dbx, diff1, diff2):
    print("client changes")
    # just the newly added files
    diffs = compute_diff(diff1, diff2)
    changes = False
    
    for f in diffs['created']:
        file_name = f
        file_path = "./testfolder/" + str(file_name)
        with open(file_path, 'rb') as file:
            dp_path = "/testfolder/" + str(file_name)
            print("path dbx: ", dp_path)
            dbx.files_upload(file.read(), dp_path , mute=True)
        changes = True
    for f in diffs['deleted']:
        print("deleted: ", f)
        dbx.files_delete("/testfolder/" + str(f))

        changes = True
    return changes



def main():
    # create a dropbox client instance
    dbx = dropbox.Dropbox(TOKEN)

    cursor = get_current_cursor(dbx)
    dir_id = compute_dir_index("./testfolder")
    time.sleep(5)
    while True:
        cursor, changes = dropbox_changes(dbx, cursor)
        if changes:
            # we made changes to the client, get new index
            dir_id = compute_dir_index("./testfolder")
        time.sleep(5)
        curr_dir_id = compute_dir_index("./testfolder")
        
        # scan for changes
        if client_changes(dbx, curr_dir_id, dir_id):
            # we have updates dropbox get new snapshot
            cursor = get_current_cursor(dbx)
        dir_id = curr_dir_id
        time.sleep(5)

### TODO: store the cursor and exit and use that initially as old cursor
if __name__=="__main__":
    main()