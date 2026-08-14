#!/usr/bin/env python3

from bcoding import bencode, bdecode
import hashlib

book_xpaths = {
                "id_finder": "/html/body/main/div/div[1]/div[{0}]/div[1]/a[{1}]/span[1]/text()",
                "filename_within_torrent": "/html/body/main/div/div[1]/div[{0}]/div[2]/div[{1}]/div[1]/span/span/text()",
                "torrent_url": "/html/body/main/div/div[1]/div[{0}]/div[2]/div[{1}]/div[3]/a/@href",
                "extension": "/html/body/main/div/div[1]/div[{0}]/text()"
               }

replace_chars = str.maketrans(dict.fromkeys(''.join([" /"]), '.') | dict.fromkeys(''.join([":;"]), None))

state_str = ['queued', 'checking', 'downloading metadata', \
    'downloading', 'finished', 'seeding', 'allocating', 'checking fastresume']

def file_search(torrent_info, desired_file):
    priorities = []
    fidx = -1
    size = -1
    path = ""
    for idx, des in enumerate(torrent_info.files()):
        if des.path.endswith(desired_file):
            priorities.append(255)
            fidx = idx
            size = des.size
            path = des.path # todo: tidy this up a bit
        else:
            priorities.append(0)
    if idx == -1:
        raise Exception("Destination file not found in torrent")
    return (fidx, size, path, priorities)

def check_torrent_completion(ses, idx):
    alerts = ses.pop_alerts()
    for a in alerts:
        alert_type = type(a).__name__
        if (alert_type == "torrent_finished_alert" or
            alert_type == "file_completed_alert"):
            if a.index == idx:
                return True

    return False

def get_changing_indices(tree):
    div = None
    server_path_found = None
    torrent_found = None
    for div in range(3, 11):
        for id in range(2, 200):
            try:
                id_finder = tree.xpath(book_xpaths["id_finder"].format(div, id))
            except:
                continue
            if len(id_finder) == 0:
                continue
            if id_finder[0] == "Server Path":
                server_path_found = id
            if id_finder[0] == "Torrent":
                torrent_found = id
            if ((server_path_found is not None) and
                (torrent_found is not None) and
                (div is not None)):
                return div, server_path_found, torrent_found

    raise Exception("Could not find file path info or torrent in listing.")

def qbitt_file_search(torrent_files, desired_file):
    for idx, des in enumerate(torrent_files):
        if des["name"].endswith(desired_file):
            return idx

    raise Exception("Destination file not found in torrent")
    
def get_torrent_hash_and_num_files(t_path):
    with open(t_path, "rb") as f:
        torrent_data = f.read()
    config = bdecode(torrent_data)
    info = config["info"]
    hash_bit = hashlib.sha1(bencode(info)).digest()
    hash = hash_bit.hex()
    num_files = len(info['files']) if 'files' in info else 1
    return hash, num_files
