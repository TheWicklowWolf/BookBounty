#!/usr/bin/env python3

from bcoding import bencode, bdecode
import hashlib
import glob, os, time
from lxml import html, etree
import requests as re
import libtorrent as lt
import qbittorrentapi

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

def get_torrent_from_listing(url, save_as):
    page = re.get(url)
    tree = html.fromstring(page.content)

    div, server_path_found, torrent_found = get_changing_indices(tree)

    fname = tree.xpath(book_xpaths["filename_within_torrent"].format(div, server_path_found))[0].split("/")[-1]
    t_url = tree.xpath(book_xpaths["torrent_url"].format(div, torrent_found))[0]
    torrent = t_url.split('/')[-1]

    for d in range(2, 10):
        details = tree.xpath(book_xpaths["extension"].format(d))
        if len(details) > 0 and len(details[0].split(' · ')) > 2:
            break

    extension = details[0].split(' · ')[1]
    save_as += ("." + extension).lower()

    aa = url.split("/")
    return (f"{aa[0]}//{aa[2]}{str(t_url)}", torrent, fname, save_as)

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


class aaclient:
    def __init__(self, logger, qbitt_client = None):
        self.logger = logger
        self.qbitt_client = qbitt_client

    def hnr_download_torrent(self, t_path, desired_file, save_filename, save_path, allotted_time=600):
        info = lt.torrent_info(t_path)
        ses = lt.session({'listen_interfaces': '0.0.0.0:6881'})

        idx, size, path, priorities = file_search(info, desired_file)

        h = ses.add_torrent({'ti': info, 'save_path': save_path})
        h.prioritize_files(priorities)

        alert_mask = (lt.alert.category_t.error_notification |
                            lt.alert.category_t.performance_warning |
                            lt.alert.category_t.progress_notification)
        ses.set_alert_mask(alert_mask)

        self.logger.info(f"Torrenting: {save_filename} - Size: {size/1048576:.2f} MB")
        os.remove(t_path)

        # default time allotment without progress is 10 minutes (600 seconds)
        time_out = 0
        increments = 10 #seconds
        old_prog = 0
        while (allotted_time == 0 or time_out < allotted_time):
            s = h.status()
            prog = h.file_progress()[idx]
            msg = f"Torrent - {prog} - {state_str[s.state]} ({s.num_peers} {'peer' if s.num_peers == 1 else 'peers'})"
            if s.state == lt.torrent_status.finished:
                msg += f" - finished state for {s.finished_duration} seconds"
            self.logger.info(msg)
            time.sleep(increments)
            time_out += increments
            if prog != old_prog:
                old_prog = prog
                time_out = 0

            if (check_torrent_completion(ses, idx) or
                (prog >= size and
                 s.state == lt.torrent_status.finished and
                 s.finished_duration > 30)):
                new_path = save_path + "/" + save_filename
                os.renames(save_path + "/" + path, new_path)
                for f in glob.glob(save_path + "/.*.parts"):
                    os.remove(f)
                self.logger.info(f"Torrented: {t_path} to {new_path}")
                return "Success"

        msg = f"Gave up or timed out Torrent for {save_filename}."
        self.logger.warning(msg)
        return "Timed out HnR torrenting"

    def dl_torrent_from_listing(self, url, save_as):
        self.logger.info(f"Getting torrent listing from: {url}")
        t_url, torrent, fname, save_as = get_torrent_from_listing(url, save_as)
        t = re.get(t_url, allow_redirects=True, stream=True)
        path = f"./{torrent}"

        with open(path, "wb") as fout:
            desc=f"Torrent downloading {torrent}"
            self.logger.info(desc)
            for chunk in t.iter_content(chunk_size=4096):
                fout.write(chunk)
            self.logger.info(f"Torrent downloaded {torrent}")

        return (path, fname, save_as)

    def get_torrent_hash_and_num_files(self, t_path):
        with open(t_path, "rb") as f:
            torrent_data = f.read()
        config = bdecode(torrent_data)
        info = config["info"]
        hash_bit = hashlib.sha1(bencode(info)).digest()
        hash = hash_bit.hex()
        num_files = len(info['files']) if 'files' in info else 1
        return hash, num_files

    def qb_download_torrent(self, t_path, hash, desired_file, save_filename):
        conn_info = dict(
            host=self.qbitt_client["host"],
            port=self.qbitt_client["port"],
            username=self.qbitt_client["username"],
            password=self.qbitt_client["password"],
        )

        qb = qbittorrentapi.Client(**conn_info)

        try:
            qb.torrents_add(torrent_files=t_path, category=self.qbitt_client["musicCategory"], is_paused=True)
            time.sleep(1) # wait for qbittorrent to process the torrent

            files = qb.torrents_files(hash)
            qb.torrents_file_priority(hash, [i for i in range(len(files))], priority=0) # Do not download

            idx = qbitt_file_search(files.data, desired_file)
            qb.torrents_file_priority(hash, idx, 1) # Normal
            new_path = os.path.dirname(files[idx].name) + "/" +  save_filename
            qb.torrents_rename_file(hash, idx, new_path)
            qb.torrents_start(hash)
            self.logger.info(f"{save_filename} added to qBittorrent")
            return "Success"
        except:
            qb.torrents_delete(True, hash)
            self.logger.error(f"Error adding book. {t_path} removed from qBittorrent")
        finally:
            os.remove(t_path)

        return "Failed to add to qBittorrent"

    def torrent_from_bookbounty(self, link, save_as, save_path):
        path, fname, save_as = self.dl_torrent_from_listing(link, save_as)

        hash, num_files = self.get_torrent_hash_and_num_files(path)
        if num_files == 1:
            self.logger.error(f"This torrent is a single tar file torrent. {fname} not added to qBittorrent")
            os.remove(path)
            return "Unsuported Torrent Format"

        if self.qbitt_client != None:
            if num_files > 1500:
                self.logger.error(f"This torrent has too much stuff, trying HnR instead. {fname} not added to qBittorrent")
            else:
                return self.qb_download_torrent(path, hash, fname, save_as)

        return self.hnr_download_torrent(path, fname, save_as, save_path)
