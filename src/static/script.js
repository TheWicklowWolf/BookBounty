var get_wanted_readarr = document.getElementById('get-readarr-wanted-btn');
var stop_readarr = document.getElementById('stop-readarr-btn');
var reset_readarr = document.getElementById('reset-readarr-btn');
var readarr_spinner = document.getElementById('readarr-spinner');
var readarr_progress_bar = document.getElementById('readarr-progress-status-bar');
var readarr_table = document.getElementById('readarr-table').getElementsByTagName('tbody')[0];
var select_all_checkbox = document.getElementById("select-all-checkbox");

var start_libgen = document.getElementById('start-libgen-btn');
var stop_libgen = document.getElementById('stop-libgen-btn');
var reset_libgen = document.getElementById('reset-libgen-btn');
var libgen_progress_bar = document.getElementById('libgen-progress-status-bar');
var libgen_table = document.getElementById('libgen-table').getElementsByTagName('tbody')[0];

var config_modal = document.getElementById('config-modal');
var save_message = document.getElementById("save-message");
var save_changes_button = document.getElementById("save-changes-btn");
const readarr_address = document.getElementById("readarr-address");
const readarr_api_key = document.getElementById("readarr-api-key");
const search_type = document.getElementById("search-type");
const sleep_interval = document.getElementById("sleep-interval");
const sync_schedule = document.getElementById("sync-schedule");
const minimum_match_ratio = document.getElementById("minimum-match-ratio");
var socket = io();

readarr_progress_bar.style.width = "0%";
readarr_progress_bar.setAttribute("aria-valuenow", 0);

function check_if_all_true() {
    var all_checked = true;
    var checkboxes = document.querySelectorAll('input[name="readarr_item"]');
    checkboxes.forEach(function (checkbox) {
        if (!checkbox.checked) {
            all_checked = false;
        }
    });
    select_all_checkbox.checked = all_checked;
}

function update_progress_bar(percentage, status) {
    libgen_progress_bar.style.width = percentage + "%";
    libgen_progress_bar.setAttribute("aria-valuenow", percentage);
    libgen_progress_bar.classList.remove("progress-bar-striped");
    libgen_progress_bar.classList.remove("progress-bar-animated");

    if (status === "running") {
        libgen_progress_bar.classList.remove("bg-primary", "bg-danger", "bg-dark", "bg-warning");
        libgen_progress_bar.classList.add("bg-success");
        libgen_progress_bar.classList.add("progress-bar-animated");

    } else if (status === "stopped") {
        libgen_progress_bar.classList.remove("bg-primary", "bg-danger", "bg-success", "bg-dark");
        libgen_progress_bar.classList.add("bg-warning");

    } else if (status === "idle") {
        libgen_progress_bar.classList.remove("bg-danger", "bg-success", "bg-primary", "bg-dark");
        libgen_progress_bar.classList.add("bg-primary");

    } else if (status === "complete") {
        libgen_progress_bar.classList.remove("bg-primary", "bg-warning", "bg-success", "bg-danger");
        libgen_progress_bar.classList.add("bg-dark");

    } else if (status === "failed") {
        libgen_progress_bar.classList.remove("bg-primary", "bg-success", "bg-warning", "bg-dark");
        libgen_progress_bar.classList.add("bg-danger");
    }
    libgen_progress_bar.classList.add("progress-bar-striped");
}

select_all_checkbox.addEventListener("change", function () {
    var is_checked = this.checked;
    var checkboxes = document.querySelectorAll('input[name="readarr_item"]');
    checkboxes.forEach(function (checkbox) {
        checkbox.checked = is_checked;
    });
});

get_wanted_readarr.addEventListener('click', function () {
    get_wanted_readarr.disabled = true;
    readarr_spinner.classList.remove('d-none');
    readarr_table.innerHTML = '';
    socket.emit("readarr_get_wanted");
});

stop_readarr.addEventListener('click', function () {
    socket.emit("stop_readarr");
    readarr_spinner.classList.add('d-none');
    get_wanted_readarr.disabled = false;
});

reset_readarr.addEventListener('click', function () {
    socket.emit("reset_readarr");
    readarr_table.innerHTML = '';
    readarr_spinner.classList.add('d-none');
    get_wanted_readarr.disabled = false;
});

config_modal.addEventListener('show.bs.modal', function (event) {
    socket.emit("load_settings");
    function handle_settings_loaded(settings) {
        readarr_address.value = settings.readarr_address;
        readarr_api_key.value = settings.readarr_api_key;
        search_type.value = settings.search_type;
        sleep_interval.value = settings.sleep_interval;
        sync_schedule.value = settings.sync_schedule.join(', ');
        minimum_match_ratio.value = settings.minimum_match_ratio;
        socket.off("settings_loaded", handle_settings_loaded);
    }
    socket.on("settings_loaded", handle_settings_loaded);
});

save_changes_button.addEventListener("click", () => {
    socket.emit("update_settings", {
        "readarr_address": readarr_address.value,
        "readarr_api_key": readarr_api_key.value,
        "search_type": search_type.value,
        "sleep_interval": sleep_interval.value,
        "sync_schedule": sync_schedule.value,
        "minimum_match_ratio": minimum_match_ratio.value
    });
    save_message.style.display = "block";
    setTimeout(function () {
        save_message.style.display = "none";
    }, 1000);
});

start_libgen.addEventListener('click', function () {
    start_libgen.disabled = true;
    var checked_indices = [];
    var checkboxes = document.getElementsByName("readarr_item");

    checkboxes.forEach(function (checkbox, index) {
        if (checkbox.checked) {
            checked_indices.push(index);
        }
    });
    socket.emit("add_to_download_list", checked_indices);
    start_libgen.disabled = false;
});

stop_libgen.addEventListener('click', function () {
    socket.emit("stop_libgen");
});

reset_libgen.addEventListener('click', function () {
    socket.emit("reset_libgen");
    libgen_table.innerHTML = '';
});

socket.on("readarr_update", (response) => {
    readarr_table.innerHTML = '';
    var all_checked = true;
    if (response.status == "busy") {
        get_wanted_readarr.disabled = true;
        readarr_spinner.classList.remove('d-none');
    }
    else {
        get_wanted_readarr.disabled = false;
        readarr_spinner.classList.add('d-none');
    }

    select_all_checkbox.style.display = "block";
    select_all_checkbox.checked = false;

    response.data.forEach((item, i) => {
        if (!item.checked) {
            all_checked = false;
        }
        var row = readarr_table.insertRow();

        var cell1 = row.insertCell(0);
        var cell2 = row.insertCell(1);

        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "form-check-input";
        checkbox.id = "readarr_" + i;
        checkbox.name = "readarr_item";
        checkbox.checked = item.checked;
        checkbox.addEventListener("change", function () {
            check_if_all_true();
        });

        var label = document.createElement("label");
        label.className = "form-check-label";
        label.htmlFor = "readarr_" + i;
        label.textContent = `${item.author} - ${item.book_name}`;

        cell1.appendChild(checkbox);
        cell2.appendChild(label);
    });
    select_all_checkbox.checked = all_checked;
});

socket.on("libgen_update", (response) => {
    libgen_table.innerHTML = '';
    response.data.forEach(function (entry) {
        var row = libgen_table.insertRow();
        var cell_item = row.insertCell(0);
        var cell_item_status = row.insertCell(1);

        cell_item.innerHTML = `${entry.author} - ${entry.book_name}`;
        cell_item_status.innerHTML = entry.status;
        cell_item_status.classList.add("text-center");
    });
    var percent_completion = response.percent_completion;
    var actual_status = response.status;
    update_progress_bar(percent_completion, actual_status);
});

socket.on("new_toast_msg", function (data) {
    show_toast(data.title, data.message);
});

function show_toast(header, message) {
    var toast_container = document.querySelector('.toast-container');
    var toast_template = document.getElementById('toast-template').cloneNode(true);
    toast_template.classList.remove('d-none');

    toast_template.querySelector('.toast-header strong').textContent = header;
    toast_template.querySelector('.toast-body').textContent = message;
    toast_template.querySelector('.text-muted').textContent = new Date().toLocaleString();

    toast_container.appendChild(toast_template);

    var toast = new bootstrap.Toast(toast_template);
    toast.show();

    toast_template.addEventListener('hidden.bs.toast', function () {
        toast_template.remove();
    });
}

const theme_switch = document.getElementById('theme-switch');
const saved_theme = localStorage.getItem('theme');
const saved_switch_position = localStorage.getItem('switchPosition');

if (saved_switch_position) {
    theme_switch.checked = saved_switch_position === 'true';
}

if (saved_theme) {
    document.documentElement.setAttribute('data-bs-theme', saved_theme);
}

theme_switch.addEventListener('click', () => {
    if (document.documentElement.getAttribute('data-bs-theme') === 'dark') {
        document.documentElement.setAttribute('data-bs-theme', 'light');
    } else {
        document.documentElement.setAttribute('data-bs-theme', 'dark');
    }
    localStorage.setItem('theme', document.documentElement.getAttribute('data-bs-theme'));
    localStorage.setItem('switchPosition', theme_switch.checked);
});
