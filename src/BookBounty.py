import os
import re
import time
import json
import shutil
import logging
import tempfile
import threading
import concurrent.futures
import iso639
import requests
from flask import Flask, render_template
from flask_socketio import SocketIO
from bs4 import BeautifulSoup
from thefuzz import fuzz
from libgen_api import LibgenSearch


class DataHandler:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        self.general_logger = logging.getLogger()

        app_name_text = os.path.basename(__file__).replace(".py", "")
        release_version = os.environ.get("RELEASE_VERSION", "unknown")
        self.general_logger.info(f"{'*' * 50}\n")
        self.general_logger.info(f"{app_name_text} Version: {release_version}\n")
        self.general_logger.info(f"{'*' * 50}")

        self.readarr_items = []
        self.readarr_futures = []
        self.readarr_status = "idle"
        self.readarr_stop_event = threading.Event()

        self.libgen_items = []
        self.libgen_futures = []
        self.libgen_status = "idle"
        self.libgen_stop_event = threading.Event()
        self.libgen_thread_lock = threading.Lock()

        self.libgen_in_progress_flag = False        
        self.is_using_libgen_api = False
        self.index = 0
        self.percent_completion = 0

        self.clients_connected_counter = 0
        self.config_folder = "config"
        self.download_folder = "downloads"

        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)
        self.load_environ_or_config_settings()

    def load_environ_or_config_settings(self):
        # Defaults
        default_settings = {
            "readarr_address": "http://192.168.1.2:8787",
            "readarr_api_key": "",
            "request_timeout": 120.0,
            "thread_limit": 1,
            "sleep_interval": 0,
            "library_scan_on_completion": True,
            "sync_schedule": [],
            "minimum_match_ratio": 90,
            "selected_language": "English",
            "selected_path_type": "file",
            "preferred_extensions_fiction": [".epub", ".mobi", ".azw3", ".djvu"],
            "preferred_extensions_non_fiction": [".pdf", ".epub", ".mobi", ".azw3", ".djvu"],
            "search_last_name_only": False,
            "search_shortened_title": False,
        }

        # Load settings from environmental variables (which take precedence) over the configuration file.
        self.readarr_address = os.environ.get("readarr_address", "")
        self.readarr_api_key = os.environ.get("readarr_api_key", "")
        sync_schedule = os.environ.get("sync_schedule", "")
        self.sync_schedule = self.parse_sync_schedule(sync_schedule) if sync_schedule != "" else ""
        sleep_interval = os.environ.get("sleep_interval", "")
        self.sleep_interval = float(sleep_interval) if sleep_interval else ""
        minimum_match_ratio = os.environ.get("minimum_match_ratio", "")
        self.minimum_match_ratio = float(minimum_match_ratio) if minimum_match_ratio else ""
        self.selected_path_type = os.environ.get("selected_path_type", "")
        library_scan_on_completion = os.environ.get("library_scan_on_completion", "")
        self.library_scan_on_completion = library_scan_on_completion.lower() == "true" if library_scan_on_completion != "" else ""
        search_last_name_only = os.environ.get("search_last_name_only", "")
        self.search_last_name_only = search_last_name_only.lower() == "true" if search_last_name_only != "" else ""
        search_shortened_title = os.environ.get("search_shortened_title", "")
        self.search_shortened_title = search_shortened_title.lower() == "true" if search_shortened_title != "" else ""
        request_timeout = os.environ.get("request_timeout", "")
        self.request_timeout = float(request_timeout) if request_timeout else ""
        thread_limit = os.environ.get("thread_limit", "")
        self.thread_limit = int(thread_limit) if thread_limit else ""
        self.selected_language = os.environ.get("selected_language", "")
        preferred_extensions_fiction = os.environ.get("preferred_extensions_fiction", "")
        self.preferred_extensions_fiction = preferred_extensions_fiction.split(",") if preferred_extensions_fiction else ""
        preferred_extensions_non_fiction = os.environ.get("preferred_extensions_non_fiction", "")
        self.preferred_extensions_non_fiction = preferred_extensions_non_fiction.split(",") if preferred_extensions_non_fiction else ""

        # Load variables from the configuration file if not set by environmental variables.
        try:
            self.settings_config_file = os.path.join(self.config_folder, "settings_config.json")
            if os.path.exists(self.settings_config_file):
                self.general_logger.warning(f"Loading Settings via config file")
                with open(self.settings_config_file, "r") as json_file:
                    ret = json.load(json_file)
                    for key in ret:
                        if getattr(self, key) == "":
                            setattr(self, key, ret[key])

        except Exception as e:
            self.general_logger.error(f"Error Loading Config: {str(e)}")

        # Load defaults if not set by an environmental variable or configuration file.
        for key, value in default_settings.items():
            if getattr(self, key) == "":
                setattr(self, key, value)

        # Save config.
        self.save_config_to_file()

        # Start Scheduler
        thread = threading.Thread(target=self.schedule_checker, name="Schedule_Thread")
        thread.daemon = True
        thread.start()

    def save_config_to_file(self):
        try:
            with open(self.settings_config_file, "w") as json_file:
                json.dump(
                    {
                        "readarr_address": self.readarr_address,
                        "readarr_api_key": self.readarr_api_key,
                        "sleep_interval": self.sleep_interval,
                        "sync_schedule": self.sync_schedule,
                        "minimum_match_ratio": self.minimum_match_ratio,
                        "selected_path_type": self.selected_path_type,
                        "library_scan_on_completion": self.library_scan_on_completion,
                        "request_timeout": self.request_timeout,
                        "thread_limit": self.thread_limit,
                        "selected_language": self.selected_language,
                        "preferred_extensions_fiction": self.preferred_extensions_fiction,
                        "preferred_extensions_non_fiction": self.preferred_extensions_non_fiction,
                        "search_last_name_only": self.search_last_name_only,
                        "search_shortened_title": self.search_shortened_title,
                    },
                    json_file,
                    indent=4,
                )

        except Exception as e:
            self.general_logger.error(f"Error Saving Config: {str(e)}")

    def connect(self):
        socketio.emit("readarr_update", {"status": self.readarr_status, "data": self.readarr_items})
        socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
        self.clients_connected_counter += 1

    def disconnect(self):
        self.clients_connected_counter = max(0, self.clients_connected_counter - 1)

    def schedule_checker(self):
        try:
            while True:
                current_hour = time.localtime().tm_hour
                within_time_window = any(t == current_hour for t in self.sync_schedule)

                if within_time_window:
                    self.general_logger.warning(f"Time to Start - as in a time window: {self.sync_schedule}")
                    self.get_wanted_list_from_readarr()
                    if self.readarr_items:
                        x = list(range(len(self.readarr_items)))
                        self.add_items_to_download(x)
                    else:
                        self.general_logger.warning("No Missing Items")

                    self.general_logger.warning("Big sleep for 1 Hour")
                    time.sleep(3600)
                    self.general_logger.warning(f"Checking every 10 minutes as not in a sync time window: {self.sync_schedule}")
                else:
                    time.sleep(600)

        except Exception as e:
            self.general_logger.error(f"Error in Scheduler: {str(e)}")
            self.general_logger.error(f"Scheduler Stopped")

    def get_wanted_list_from_readarr(self):
        try:
            self.general_logger.warning(f"Accessing Readarr API")
            self.readarr_status = "busy"
            self.readarr_stop_event.clear()
            self.readarr_items = []
            page = 1
            while True:
                if self.readarr_stop_event.is_set():
                    return
                endpoint = f"{self.readarr_address}/api/v1/wanted/missing"
                params = {"apikey": self.readarr_api_key, "page": page, "includeAuthor": True}
                response = requests.get(endpoint, params=params, timeout=self.request_timeout)
                if response.status_code == 200:
                    wanted_missing_items = response.json()
                    if not wanted_missing_items["records"]:
                        break
                    for item in wanted_missing_items["records"]:
                        if self.readarr_stop_event.is_set():
                            break

                        title = item["title"]
                        author_and_title = item["authorTitle"]
                        series = item["seriesTitle"]
                        author_reversed = author_and_title.replace(title, "")
                        author_with_sep = author_reversed.split(", ")
                        author = "".join(reversed(author_with_sep)).title()
                        year = item["releaseDate"][:4]

                        meta_profile_id = item["author"]["metadataProfileId"]
                        endpoint = f"{self.readarr_address}/api/v1/metadataprofile/{meta_profile_id}"
                        params = {"apikey": self.readarr_api_key}
                        response = requests.get(endpoint, params=params, timeout=self.request_timeout)
                        allowed_languages = []
                        if response.status_code == 200:
                            author_meta_profile = response.json()
                            iso_langs = author_meta_profile.get("allowedLanguages", "")
                            allowed_languages = [iso639.Lang(iso).name.lower() for iso in iso_langs.split(",") if iso639.is_language(iso)]

                        if allowed_languages == []:
                            self.general_logger.error(f"Readarr MetadataProfile API Error Code: {response.status_code}")
                            self.general_logger.error(f"Unable to get language from metadata profile for author: {author}\nUsing default.")
                            allowed_languages = [l.lower().strip() for l in self.selected_language.split(",")]

                        new_item = {"author": author, "book_name": title, "series": series, "checked": True, "status": "", "year": year, "allowed_languages": allowed_languages}
                        self.readarr_items.append(new_item)
                    page += 1
                else:
                    self.general_logger.error(f"Readarr Wanted API Error Code: {response.status_code}")
                    self.general_logger.error(f"Readarr Wanted API Error Text: {response.text}")
                    socketio.emit("new_toast_msg", {"title": f"Readarr API Error: {response.status_code}", "message": response.text})
                    break

            self.readarr_items.sort(key=lambda x: (x["author"], x["book_name"]))
            self.readarr_status = "stopped" if self.readarr_stop_event.is_set() else "complete"

        except Exception as e:
            self.general_logger.error(f"Error Getting Missing Books: {str(e)}")
            self.readarr_status = "error"
            socketio.emit("new_toast_msg", {"title": "Error Getting Missing Books", "message": str(e)})

        finally:
            socketio.emit("readarr_update", {"status": self.readarr_status, "data": self.readarr_items})

    def trigger_readarr_scan(self):
        try:
            endpoint = "/api/v1/rootfolder"
            headers = {"X-Api-Key": self.readarr_api_key}
            root_folder_list = []
            response = requests.get(f"{self.readarr_address}{endpoint}", headers=headers)
            endpoint = "/api/v1/command"
            if response.status_code == 200:
                root_folders = response.json()
                for folder in root_folders:
                    root_folder_list.append(folder["path"])
            else:
                self.general_logger.warning(f"No Readarr root folders found")

            if root_folder_list:
                data = {"name": "RescanFolders", "folders": root_folder_list}
                headers = {"X-Api-Key": self.readarr_api_key, "Content-Type": "application/json"}
                response = requests.post(f"{self.readarr_address}{endpoint}", json=data, headers=headers)
                if response.status_code != 201:
                    self.general_logger.warning(f"Failed to start readarr library scan")

        except Exception as e:
            self.general_logger.error(f"Readarr library scan failed: {str(e)}")

        else:
            self.general_logger.warning(f"Readarr library scan started")

    def add_items_to_download(self, data):
        try:
            self.libgen_stop_event.clear()
            if self.libgen_status == "complete" or self.libgen_status == "stopped":
                self.libgen_items = []
                self.percent_completion = 0
            for i in range(len(self.readarr_items)):
                if i in data:
                    self.readarr_items[i]["status"] = "Queued"
                    self.readarr_items[i]["checked"] = True
                    self.libgen_items.append(self.readarr_items[i])
                else:
                    self.readarr_items[i]["checked"] = False

            if self.libgen_in_progress_flag == False:
                self.index = 0
                self.libgen_in_progress_flag = True
                thread = threading.Thread(target=self.master_queue, name="Queue_Thread")
                thread.daemon = True
                thread.start()

        except Exception as e:
            self.general_logger.error(f"Error Adding Items to Download: {str(e)}")
            socketio.emit("new_toast_msg", {"title": "Error adding new items", "message": str(e)})

        finally:
            socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
            socketio.emit("new_toast_msg", {"title": "Download Queue Updated", "message": "New Items added to Queue"})

    def master_queue(self):
        try:
            while not self.libgen_stop_event.is_set() and self.index < len(self.libgen_items):
                self.libgen_status = "running"
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_limit) as executor:
                    self.libgen_futures = []
                    start_position = self.index
                    for req_item in self.libgen_items[start_position:]:
                        if self.libgen_stop_event.is_set():
                            break
                        self.libgen_futures.append(executor.submit(self.find_link_and_download, req_item))
                    concurrent.futures.wait(self.libgen_futures)

            if self.libgen_stop_event.is_set():
                self.libgen_status = "stopped"
                self.general_logger.warning("Downloading Stopped")
                self.libgen_in_progress_flag = False
            else:
                self.libgen_status = "complete"
                self.general_logger.warning("Downloading Finished")
                self.libgen_in_progress_flag = False
                if self.library_scan_on_completion:
                    self.trigger_readarr_scan()

        except Exception as e:
            self.general_logger.error(f"Error in Master Queue: {str(e)}")
            self.libgen_status = "failed"
            socketio.emit("new_toast_msg", {"title": "Error in Master Queue", "message": str(e)})

        finally:
            socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
            socketio.emit("new_toast_msg", {"title": "End of Session", "message": f"Downloading {self.libgen_status.capitalize()}"})

    def find_link_and_download(self, req_item):
        finder_functions = [
            self._link_finder_libgen_api, 
            self._link_finder_libgen_is, 
            self._link_finder_libgen_li
            ]
        
        for func in finder_functions:
            try:                
                self.is_using_libgen_api = False
                req_item["status"] = "Searching..."
                socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
                search_results = func(req_item)
                if self.libgen_stop_event.is_set():
                    return

                if search_results:
                    req_item["status"] = "Link Found"
                    socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
                    for link in search_results:
                        ret = self.download_from_libgen(req_item, link)
                        if ret == "Success":
                            req_item["status"] = "Download Complete"
                            break
                        elif ret == "Already Exists":
                            req_item["status"] = "File Already Exists"
                            break
                    else:
                        req_item["status"] = ret
            
                if req_item["status"] == "Download Complete":
                    break

            except Exception as e:
                self.general_logger.error(f"Error Downloading: {str(e)}")
                req_item["status"] = "Download Error"

        self.index += 1
        self.percent_completion = 100 * (self.index / len(self.libgen_items)) if self.libgen_items else 0
        socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})

    def _link_finder_libgen_api(self, req_item):
        try:
            self.general_logger.warning(f'Searching API for Book: {req_item["author"]} - {req_item["book_name"]} - Allowed Languages: {",".join(req_item["allowed_languages"])}')
            author = req_item["author"]
            book_name = req_item["book_name"]
            book_search_text = book_name.split(":")[0] if self.search_shortened_title else book_name

            found_links = []

            try:
                with self.libgen_thread_lock:
                    s = LibgenSearch()
                    results = s.search_title(book_search_text)
                    self.general_logger.warning(f"Found {len(results)} potential matches")

            except Exception as e:
                self.general_logger.error(f"Error with libgen_api search library: {str(e)}")
                results = None

            for item in results:
                author_name_match_ratio = self.compare_author_names(item["Author"], author)
                book_name_match_ratio = fuzz.ratio(item["Title"], book_name)
                average_match_ratio = (author_name_match_ratio + book_name_match_ratio) / 2
                language_check = item["Language"].lower() in req_item["allowed_languages"] or self.selected_language.lower() == "all"
                if average_match_ratio > self.minimum_match_ratio and language_check:
                    download_links = s.resolve_download_links(item)
                    found_links = [value for value in download_links.values()]
                    break
            else:
                req_item["status"] = "No Link Found"

        except Exception as e:
            self.general_logger.error(f"Error Searching libgen API: {str(e)}")
            raise Exception(f"Error Searching libgen API: {str(e)}")

        finally:
            self.is_using_libgen_api = True
            return found_links

    def _link_finder_libgen_is(self, req_item):
        try:
            self.general_logger.warning(f'Searching libgen.is for Book: {req_item["author"]} - {req_item["book_name"]} - Allowed Languages: {",".join(req_item["allowed_languages"])}')
            author = req_item["author"]
            book_name = req_item["book_name"]

            author_search_text = f"{author.split(' ')[-1]}" if self.search_last_name_only else author
            book_search_text = book_name.split(":")[0] if self.search_shortened_title else book_name
            query_text = f"{author_search_text} - {book_search_text}"

            found_links = []
            search_item = query_text.replace(" ", "+")
            url = f"http://libgen.is/fiction/?q={search_item}"
            response = requests.get(url, timeout=self.request_timeout)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                table = soup.find("tbody")
                if table:
                    rows = table.find_all("tr")
                else:
                    rows = []

                for row in rows:
                    try:
                        cells = row.find_all("td")
                        try:
                            author_string = cells[0].get_text().strip()
                        except:
                            author_string = ""
                        try:
                            raw_title = cells[2].get_text().strip()
                            if "\nISBN" in raw_title:
                                title_string = raw_title.split("\nISBN")[0]
                            elif "\nASIN" in raw_title:
                                title_string = raw_title.split("\nASIN")[0]
                            else:
                                title_string = raw_title
                        except:
                            title_string = ""
                        try:
                            language = cells[3].get_text().strip()
                        except:
                            language = "english"
                        try:
                            file_type = cells[4].get_text().strip().lower()
                        except:
                            file_type = ".epub"
                        file_type_check = any(ft.replace(".", "").lower() in file_type for ft in self.preferred_extensions_fiction)
                        language_check = language.lower() in req_item["allowed_languages"] or self.selected_language.lower() == "all"

                        if file_type_check and language_check:
                            author_name_match_ratio = self.compare_author_names(author, author_string)
                            book_name_match_ratio = fuzz.ratio(title_string, book_search_text)
                            if author_name_match_ratio >= self.minimum_match_ratio and book_name_match_ratio >= self.minimum_match_ratio:
                                mirrors = row.find("ul", class_="record_mirrors_compact")
                                links = mirrors.find_all("a", href=True)
                                for link in links:
                                    href = link["href"]
                                    if href.startswith("http://") or href.startswith("https://"):
                                        found_links.append(href)
                    except:
                        pass

                if not found_links:
                    req_item["status"] = "No Link Found"
                socketio.emit("libgen_update", {"status": "Success", "data": self.libgen_items, "percent_completion": self.percent_completion})
            else:
                socketio.emit("libgen_update", {"status": "Error", "data": self.libgen_items, "percent_completion": self.percent_completion})
                self.general_logger.error("Libgen Connection Error: " + str(response.status_code) + " Data: " + response.text)
                req_item["status"] = "Libgen Error"
                socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})

        except Exception as e:
            self.general_logger.error(f"Error Searching libgen.is: {str(e)}")
            raise Exception(f"Error Searching libgen.is: {str(e)}")

        finally:
            return found_links

    def _link_finder_libgen_li(self, req_item):
        try:
            self.general_logger.warning(f'Searching libgen.li for Book: {req_item["author"]} - {req_item["book_name"]} - Allowed Languages: {",".join(req_item["allowed_languages"])}')
            author = req_item["author"]
            book_name = req_item["book_name"]

            author_search_text = f"{author.split(' ')[-1]}" if self.search_last_name_only else author
            book_search_text = book_name.split(":")[0] if self.search_shortened_title else book_name
            query_text = f"{author_search_text} - {book_search_text}"

            found_links = []
            search_item = query_text.replace(" ", "+")
            url = f"http://libgen.li/index.php?req={search_item}"
            response = requests.get(url, timeout=self.request_timeout)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                table = soup.find("tbody")
                if table:
                    rows = table.find_all("tr")
                else:
                    rows = []

                for row in rows:
                    try:
                        cells = row.find_all("td")
                        try:
                            author_string = cells[1].get_text().strip()
                        except:
                            author_string = ""
                        try:
                            raw_title = cells[0].find_all("a")[0].get_text().strip()
                            if "\nISBN" in raw_title:
                                title_string = raw_title.split("\nISBN")[0]
                            elif "\nASIN" in raw_title:
                                title_string = raw_title.split("\nASIN")[0]
                            else:
                                title_string = raw_title
                        except:
                            title_string = ""
                        try:
                            language = cells[4].get_text().strip()
                        except:
                            language = "english"
                        try:
                            file_type = cells[7].get_text().strip().lower()
                        except:
                            file_type = ".epub"
                        file_type_check = any(ft.replace(".", "").lower() in file_type for ft in self.preferred_extensions_fiction)
                        language_check = language.lower() in req_item["allowed_languages"] or self.selected_language.lower() == "all"

                        if file_type_check and language_check:
                            author_name_match_ratio = self.compare_author_names(author, author_string)
                            book_name_match_ratio = fuzz.ratio(title_string, book_search_text)
                            if author_name_match_ratio >= self.minimum_match_ratio and book_name_match_ratio >= self.minimum_match_ratio:
                                mirrors = cells[8]
                                links = mirrors.find_all("a", href=True)
                                for link in links:
                                    href = link["href"]
                                    if href.startswith("http://") or href.startswith("https://"):
                                        found_links.append(href)
                                    elif href.startswith("/"):
                                        found_links.append("http://libgen.li" + href)
                    except:
                        pass

                if not found_links:
                    req_item["status"] = "No Link Found"
                socketio.emit("libgen_update", {"status": "Success", "data": self.libgen_items, "percent_completion": self.percent_completion})
            else:
                socketio.emit("libgen_update", {"status": "Error", "data": self.libgen_items, "percent_completion": self.percent_completion})
                self.general_logger.error("Libgen Connection Error: " + str(response.status_code) + " Data: " + response.text)
                req_item["status"] = "Libgen Error"
                socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
        
        except Exception as e:
            self.general_logger.error(f"Error Searching libgen.li: {str(e)}")
            raise Exception(f"Error Searching libgen.li: {str(e)}")

        finally:
            return found_links

    def compare_author_names(self, author, author_string):
        try:
            processed_author = self.preprocess(author)
            processed_author_string = self.preprocess(author_string)
            match_ratio = fuzz.ratio(processed_author, processed_author_string)

        except Exception as e:
            self.general_logger.error(f"Error Comparing Names: {str(e)}")
            match_ratio = 0

        finally:
            return match_ratio

    def preprocess(self, name):
        name_string = name.replace(".", " ").replace(":", " ").replace(",", " ")
        new_string = "".join(e for e in name_string if e.isalnum() or e.isspace()).lower()
        words = new_string.split()
        words.sort()
        return " ".join(words)

    def download_from_libgen(self, req_item, link):

        req_item["status"] = "Checking Link"
        socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})

        if self.is_using_libgen_api:
            valid_book_extensions = self.preferred_extensions_non_fiction
            link_url = link
            try:
                file_type = os.path.splitext(link_url)[1]
            except:
                file_type = None
        else:
            try:
                valid_book_extensions = self.preferred_extensions_fiction
                response = requests.get(link, timeout=self.request_timeout)
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
                        table = soup.find("table")
                        if table:
                            rows = table.find_all("tr")
                            for row in rows:
                                if "GET" in row.get_text():
                                    download_link = row.find("a")
                                    if download_link:
                                        link_text = download_link.get("href")
                                        if "http" not in link_text:
                                            link_url = "https://libgen.li/" + link_text
                                        else:
                                            link_url = link_text
                                        break
                            else:
                                return "Dead Link"
                        else:
                            return "No Link Available"

                else:
                    return str(response.status_code) + " : " + response.text
            
            except:
                return "Dead Link"

            try:
                file_type = os.path.splitext(link_url)[1]

            except:
                file_type = None
                self.general_logger.info("File extension not in url or invalid, checking link content...")

        try:
            download_response = requests.get(link_url, stream=True)

        except Exception as e:
            req_item["status"] = "Link Failed"
            socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
            self.general_logger.error(f"Exception {str(e)} thrown by: {link_url}")
            return "Link Failed"

        if file_type == None or ".php" in file_type:
            link_file_name_text = download_response.headers.get("content-disposition")
            if not link_file_name_text:
                return "Unknown File Type"

            for ext in valid_book_extensions:
                if ext in link_file_name_text.lower():
                    file_type = ext
                    break

        if not file_type or file_type not in valid_book_extensions:
            return "Wrong File Type"

        cleaned_author_name = re.sub(r"\s{2,}", " ", re.sub(r'[\\*?:"<>|]', " - ", req_item["author"].replace("/", "+")))
        cleaned_book_name = re.sub(r"\s{2,}", " ", re.sub(r'[\\*?:"<>|]', " - ", req_item["book_name"].replace("/", "+")))

        if self.selected_path_type == "file":
            file_path = os.path.join(self.download_folder, f"{cleaned_author_name} - {cleaned_book_name} ({req_item['year']}){file_type}")

        elif self.selected_path_type == "folder":
            path_elements = [self.download_folder, req_item["author"]]

            if req_item["series"]:
                raw_series_string = req_item["series"].split(";")[0] if ";" in req_item["series"] else req_item["series"]

                if " #" in raw_series_string:
                    series_name, series_number = raw_series_string.split(" #", maxsplit=1)
                    cleaned_series_name = re.sub(r"\s{2,}", " ", re.sub(r'[\\/*?:"<>|]', " - ", series_name.replace("/", "+")))
                    path_elements.append(cleaned_series_name)
                    path_elements.append(f"{series_number} - {cleaned_book_name} ({req_item['year']})")
                    path_elements.append(f"{series_number} - {cleaned_series_name} - {cleaned_author_name} - {cleaned_book_name} ({req_item['year']}){file_type}")

                else:
                    series_name = raw_series_string.replace("/", "+")
                    cleaned_series_name = re.sub(r"\s{2,}", " ", re.sub(r'[\\/*?:"<>|]', " - ", series_name))
                    path_elements.append(cleaned_series_name)
                    path_elements.append(f"{cleaned_book_name} ({req_item['year']})")
                    path_elements.append(f"{series_name} - {cleaned_author_name} - {cleaned_book_name} ({req_item['year']}){file_type}")

            else:
                path_elements.append(f"{cleaned_book_name} ({req_item['year']})")
                path_elements.append(f"{cleaned_author_name} - {cleaned_book_name} ({req_item['year']}){file_type}")

            file_path = os.path.join(*path_elements)

        if os.path.exists(file_path):
            self.general_logger.info("File already exists: " + file_path)
            req_item["status"] = "File Already Exists"
            return "Already Exists"
        else:
            if self.selected_path_type == "folder":
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if self.libgen_stop_event.is_set():
            raise Exception("Cancelled")

        if download_response.status_code == 200:
            # Download file
            req_item["status"] = "Downloading"
            socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})

            total_size = int(download_response.headers.get("content-length", 0))
            downloaded_size = 0
            chunk_counter = 0

            self.general_logger.info(f"Downloading: {os.path.basename(file_path)} - Size: {total_size/1048576:.2f} MB")

            try:
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    for chunk in download_response.iter_content(chunk_size=1024):
                        if self.libgen_stop_event.is_set():
                            raise Exception("Cancelled")
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        chunk_counter += 1
                        if chunk_counter % 100 == 0:
                            percent_completion = (downloaded_size / total_size) * 100 if total_size > 0 else 0
                            self.general_logger.info(f"Downloading: {os.path.basename(file_path)} - Progress: {percent_completion:.2f}%")

                self.general_logger.info(f"Moving temp file: {f.name} to final location: {file_path}")
                shutil.move(f.name, file_path)

            except Exception as e:
                self.general_logger.error(f"Error downloading to temp file: {str(e)}")
                if os.path.exists(f.name):
                    os.remove(f.name)
                    self.general_logger.info(f"Removed temp file: {f.name}")

            if os.path.exists(file_path):
                self.general_logger.info(f"Downloaded: {link_url} to {file_path}")
                return "Success"
            else:
                self.general_logger.info("Downloaded file not found in Directory")
                return "Failed"
        else:
            req_item["status"] = "Download Error"
            socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})
            error_string = f"{download_response.status_code} : {download_response.text}"
            self.general_logger.error(f"Error downloading: {os.path.basename(file_path)} - {error_string}")
            return error_string

    def reset_readarr(self):
        self.readarr_stop_event.set()
        for future in self.readarr_futures:
            if not future.done():
                future.cancel()
        self.readarr_items = []

    def stop_libgen(self):
        try:
            self.libgen_stop_event.set()
            for future in self.libgen_futures:
                if not future.done():
                    future.cancel()
            for x in self.libgen_items[self.index :]:
                x["status"] = "Download Stopped"

        except Exception as e:
            self.general_logger.error(f"Error Stopping libgen: {str(e)}")

        finally:
            self.libgen_status = "stopped"
            socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})

    def reset_libgen(self):
        try:
            self.libgen_stop_event.set()
            for future in self.libgen_futures:
                if not future.done():
                    future.cancel()
            self.libgen_items = []
            self.percent_completion = 0

        except Exception as e:
            self.general_logger.error(f"Error Resetting libgen: {str(e)}")

        else:
            self.general_logger.warning("Reset Complete")

        finally:
            socketio.emit("libgen_update", {"status": self.libgen_status, "data": self.libgen_items, "percent_completion": self.percent_completion})

    def update_settings(self, data):
        try:
            self.readarr_address = data["readarr_address"]
            self.readarr_api_key = data["readarr_api_key"]
            self.sleep_interval = float(data["sleep_interval"])
            self.sync_schedule = self.parse_sync_schedule(data["sync_schedule"])
            self.minimum_match_ratio = float(data["minimum_match_ratio"])

        except Exception as e:
            self.general_logger.error(f"Failed to update settings: {str(e)}")

    def parse_sync_schedule(self, input_string):
        try:
            ret = []
            if input_string != "":
                raw_sync_schedule = [int(re.sub(r"\D", "", start_time.strip())) for start_time in input_string.split(",")]
                temp_sync_schedule = [0 if x < 0 or x > 23 else x for x in raw_sync_schedule]
                cleaned_sync_schedule = sorted(list(set(temp_sync_schedule)))
                ret = cleaned_sync_schedule

        except Exception as e:
            self.general_logger.error(f"Time not in correct format: {str(e)}")
            self.general_logger.error(f"Schedule Set to {ret}")

        finally:
            return ret

    def load_settings(self):
        data = {
            "readarr_address": self.readarr_address,
            "readarr_api_key": self.readarr_api_key,
            "sleep_interval": self.sleep_interval,
            "sync_schedule": self.sync_schedule,
            "minimum_match_ratio": self.minimum_match_ratio,
        }
        socketio.emit("settings_loaded", data)


app = Flask(__name__)
app.secret_key = "secret_key"
socketio = SocketIO(app)
data_handler = DataHandler()


@app.route("/")
def home():
    return render_template("base.html")


@socketio.on("readarr_get_wanted")
def readarr():
    thread = threading.Thread(target=data_handler.get_wanted_list_from_readarr, name="Readarr_Thread")
    thread.daemon = True
    thread.start()


@socketio.on("stop_readarr")
def stop_readarr():
    data_handler.readarr_stop_event.set()


@socketio.on("reset_readarr")
def reset_readarr():
    data_handler.reset_readarr()


@socketio.on("stop_libgen")
def stop_libgen():
    data_handler.stop_libgen()


@socketio.on("reset_libgen")
def reset_libgen():
    data_handler.reset_libgen()


@socketio.on("add_to_download_list")
def add_to_download_list(data):
    data_handler.add_items_to_download(data)


@socketio.on("connect")
def connection():
    data_handler.connect()


@socketio.on("disconnect")
def disconnect():
    data_handler.disconnect()


@socketio.on("load_settings")
def load_settings():
    data_handler.load_settings()


@socketio.on("update_settings")
def update_settings(data):
    data_handler.update_settings(data)
    data_handler.save_config_to_file()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
