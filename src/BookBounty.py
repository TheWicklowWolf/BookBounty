import logging
import os
import re
import sys
import threading
import requests
from flask import Flask, render_template
from flask_socketio import SocketIO
from bs4 import BeautifulSoup
from libgen_api import LibgenSearch


class Data_Handler:
    def __init__(self, readarrAddress, readarrAPIKey, libgenAddress):
        self.readarrAddress = readarrAddress
        self.readarrApiKey = readarrAPIKey
        self.libgenSearchType = "/fiction/?q="
        self.libgenSearchBase = libgenAddress
        self.directory_name = "downloads"
        os.makedirs(self.directory_name, exist_ok=True)
        self.readarrMaxTags = 250
        self.readarrApiTimeout = 120
        self.http_timeout = 120
        self.libgenSleepInterval = 0
        self.reset()

    def reset(self):
        self.readarr_items = []
        self.download_list = []
        self.stop_readarr_event = threading.Event()
        self.stop_downloading_event = threading.Event()
        self.stop_monitoring_event = threading.Event()
        self.monitor_active_flag = False
        self.running_flag = False
        self.status = "Idle"
        self.index = 0
        self.percent_completion = 0

    def get_missing_from_readarr(self):
        try:
            self.stop_readarr_event.clear()
            self.readarr_items = []
            endpoint = f"{self.readarrAddress}/api/v1/wanted/missing"
            params = {"apikey": self.readarrApiKey, "pageSize": self.readarrMaxTags, "sortKey": "title", "sortDirection": "ascending"}
            response = requests.get(endpoint, params=params, timeout=self.readarrApiTimeout)
            if response.status_code == 200:
                wanted_missing = response.json()
                for album in wanted_missing["records"]:
                    title = album["title"]
                    author_and_title = album["authorTitle"]
                    author_reversed = author_and_title.replace(title, "")
                    author_with_sep = author_reversed.split(", ")
                    author = "".join(reversed(author_with_sep))
                    self.readarr_items.append(author + " -- " + title)
                self.readarr_items.sort()
                ret = {"Status": "Success", "Data": self.readarr_items}
            else:
                ret = {"Status": "Error", "Code": response.status_code, "Data": response.text}

        except Exception as e:
            logger.error(str(e))
            ret = {"Status": "Error", "Code": 500, "Data": str(e)}

        finally:
            if not self.stop_readarr_event.is_set():
                socketio.emit("readarr_status", ret)
            else:
                ret = {"Status": "Error", "Code": "", "Data": ""}
                socketio.emit("readarr_status", ret)

    def add_items(self):
        try:
            while not self.stop_downloading_event.is_set() and self.index < len(self.download_list):
                self.status = "Running"
                req_book = self.download_list[self.index]
                search_results = self.search_libgen(req_book)
                if search_results:
                    req_book["Status"] = "Link Found"

                    for link in search_results:
                        ret = self.download_from_libgen(req_book, link)
                        if ret == "Success":
                            req_book["Status"] = "Download Complete"
                            break
                        elif ret == "Already Exists":
                            req_book["Status"] = "File Already Exists"
                            break
                    else:
                        req_book["Status"] = ret
                        self.index += 1
                        continue
                else:
                    self.index += 1
                    continue

                logger.warning("Sleeping between requests")
                if self.stop_downloading_event.wait(timeout=self.libgenSleepInterval):
                    break
                logger.warning("Finished sleeping")
                self.index += 1

            if not self.stop_downloading_event.is_set():
                self.status = "Complete"
                logger.warning("Finished")
                self.running_flag = False
            else:
                self.status = "Stopped"
                logger.warning("Stopped")
                self.running_flag = False
                ret = {"Status": "Error", "Data": "Stopped"}
                socketio.emit("libgen_status", ret)

        except Exception as e:
            logger.error(str(e))
            self.status = "Stopped"
            logger.warning("Stopped")
            ret = {"Status": "Error", "Data": str(e)}
            socketio.emit("libgen_status", ret)

    def search_libgen(self, book):
        try:
            item = book["Item"]
            author_name, book_title = item.split(" -- ", 1)
            found_links = []
            non_standard_chars_pattern = r"[^a-zA-Z0-9\s.]"
            item = item.replace("ø", "o")
            cleaned_string = re.sub(non_standard_chars_pattern, "", item)
            cleaned_string = re.sub(r"\s+", " ", cleaned_string)

            if "non-fiction" in self.libgenSearchType:
                s = LibgenSearch()
                title_filters = {"Author": author_name, "Language": "English"}
                results = s.search_title_filtered(book_title, title_filters, exact_match=False)
                if results:
                    item_to_download = results[0]
                    download_links = s.resolve_download_links(item_to_download)
                    found_links = [value for value in download_links.values()]
                else:
                    book["Status"] = "No Link Found"

            else:
                search_item = cleaned_string.replace(" ", "+")
                url = self.libgenSearchBase + self.libgenSearchType + search_item
                response = requests.get(url, timeout=self.http_timeout)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    elements = soup.find_all(class_="record_mirrors_compact")

                    for element in elements:
                        links = element.find_all("a", href=True)
                        for link in links:
                            href = link["href"]
                            if href.startswith("http://") or href.startswith("https://"):
                                found_links.append(href)

                    if not found_links:
                        book["Status"] = "No Link Found"
                    else:
                        ret = {"Status": "Success", "Data": "Found Links"}
                        socketio.emit("libgen_status", ret)
                else:
                    ret = {"Status": "Error", "Data": "Libgen Connection Error"}
                    logger.error("Libgen Connection Error: " + str(response.status_code) + " Data: " + response.text)
                    socketio.emit("libgen_status", ret)
                    book["Status"] = "Libgen DB Error"

        except Exception as e:
            logger.error(str(e))
            raise Exception("Error Searching libgen: " + str(e))

        finally:
            return found_links

    def download_from_libgen(self, req_book, link):
        if "non-fiction" in self.libgenSearchType:
            link_url = link
        else:
            response = requests.get(link, timeout=self.http_timeout)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                download_div = soup.find("div", id="download")

                if download_div:
                    download_link = download_div.find("a")
                    if download_link:
                        link_url = download_link.get("href")
                    else:
                        return "Dead Link"
                else:
                    elements_with_get = soup.find_all(string=lambda text: "GET" in text)

                    for element_text in elements_with_get:
                        parent_element = element_text.parent
                        download_link = parent_element.find("a") if parent_element else None
                        if download_link:
                            link_url = download_link.get("href")
                            break
                    else:
                        return "Dead Link"
            else:
                return str(response.status_code) + " : " + response.text

        req_book["Status"] = "Checking Link"
        file_type = os.path.splitext(link_url)[1]
        valid_book_extensions = [".pdf", ".epub", ".mobi", ".azw", ".djvu"]
        if file_type not in valid_book_extensions:
            return "Wrong File Type"

        final_file_name = re.sub(r'[\\/*?:"<>|]', " ", req_book["Item"])
        author_name, book_title = final_file_name.split(" -- ", 1)
        author_name = author_name.title()
        final_file_name = final_file_name.replace(" -- ", " - ")
        file_path = os.path.join(self.directory_name, author_name, book_title, author_name + " - " + book_title + file_type)

        if os.path.exists(file_path):
            logger.info("File already exists: " + file_path)
            req_book["Status"] = "File Already Exists"
            return "Already Exists"
        else:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

        dl_resp = requests.get(link_url, stream=True)

        if self.stop_downloading_event.is_set():
            raise Exception("Cancelled")

        if dl_resp.status_code == 200:
            # Download file
            req_book["Status"] = "Downloading"
            with open(file_path, "wb") as f:
                for chunk in dl_resp.iter_content(chunk_size=1024):
                    if self.stop_downloading_event.is_set():
                        raise Exception("Cancelled")
                    f.write(chunk)
            logger.info("Downloaded: " + link_url + " to " + final_file_name)
            return "Success"
        else:
            req_book["Status"] = "Download Error"
            return str(dl_resp.status_code) + " : " + dl_resp.text

    def monitor(self):
        while not self.stop_monitoring_event.is_set():
            self.percent_completion = 100 * (self.index / len(self.download_list)) if self.download_list else 0
            custom_data = {"Data": self.download_list, "Status": self.status, "Percent_Completion": self.percent_completion}
            socketio.emit("progress_status", custom_data)
            self.stop_monitoring_event.wait(1)

    def cancel_downloads(self):
        self.stop_readarr_event.set()
        self.stop_downloading_event.set()
        for item in self.download_list[self.index :]:
            item["Status"] = "Download Cancelled"


app = Flask(__name__)
app.secret_key = "secret_key"
socketio = SocketIO(app)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s", datefmt="%d/%m/%Y %H:%M:%S", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger()

readarrAddress = os.environ.get("readarr_address", "http://192.168.1.2:8787")
readarrAPIKey = os.environ.get("readarr_api_key", "XYZ0123456789")
libgenAddress = os.environ.get("libgen_address", "http://libgen.is")

data_handler = Data_Handler(readarrAddress, readarrAPIKey, libgenAddress)


@app.route("/")
def home():
    return render_template("base.html")


@socketio.on("readarr")
def readarr():
    thread = threading.Thread(target=data_handler.get_missing_from_readarr)
    thread.start()


@socketio.on("libgen")
def libgen(data):
    try:
        data_handler.stop_downloading_event.clear()
        if data_handler.status == "Complete":
            data_handler.download_list = []
        for item in data["Data"]:
            full_item = {"Item": item, "Status": "Queued"}
            data_handler.download_list.append(full_item)

        if data_handler.running_flag == False:
            data_handler.index = 0
            data_handler.running_flag = True
            thread = threading.Thread(target=data_handler.add_items)
            thread.daemon = True
            thread.start()

        ret = {"Status": "Success"}

    except Exception as e:
        logger.error(str(e))
        ret = {"Status": "Error", "Data": str(e)}

    finally:
        socketio.emit("libgen_status", ret)


@socketio.on("connect")
def connection():
    if data_handler.monitor_active_flag == False:
        data_handler.stop_monitoring_event.clear()
        thread = threading.Thread(target=data_handler.monitor)
        thread.daemon = True
        thread.start()
        data_handler.monitor_active_flag = True


@socketio.on("loadSettings")
def loadSettings():
    data = {
        "readarrApiKey": data_handler.readarrApiKey,
        "readarrMaxTags": data_handler.readarrMaxTags,
        "readarrApiTimeout": data_handler.readarrApiTimeout,
        "libgenSearchBase": data_handler.libgenSearchBase,
        "libgenSearchType": data_handler.libgenSearchType,
        "libgenSleepInterval": data_handler.libgenSleepInterval,
    }
    socketio.emit("settingsLoaded", data)


@socketio.on("updateSettings")
def updateSettings(data):
    data_handler.readarrApiKey = data["readarrApiKey"]
    data_handler.readarrMaxTags = int(data["readarrMaxTags"])
    data_handler.readarrApiTimeout = int(data["readarrApiTimeout"])
    data_handler.libgenSearchBase = data["libgenSearchBase"]
    data_handler.libgenSearchType = data["libgenSearchType"]
    data_handler.libgenSleepInterval = int(data["libgenSleepInterval"])


@socketio.on("disconnect")
def disconnect():
    data_handler.stop_monitoring_event.set()
    data_handler.monitor_active_flag = False


@socketio.on("stopper")
def stopper():
    if data_handler.download_list:
        ret = {"Status": "Error", "Data": "Stopping"}
        socketio.emit("libgen_status", ret)
    data_handler.cancel_downloads()


@socketio.on("reset")
def reset():
    data_handler.cancel_downloads()
    data_handler.reset()
    custom_data = {"Data": data_handler.download_list, "Status": data_handler.status, "Percent_Completion": data_handler.percent_completion}
    socketio.emit("progress_status", custom_data)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
