var readarrButton = document.getElementById('readarr_button');
var readarrSpinner = document.getElementById('readarr_spinner');
var readarrStatus = document.getElementById('readarr_status');
var libgenSpinner = document.getElementById('libgen_spinner');
var libgenStatus = document.getElementById('libgen_status');
var libgenButton = document.getElementById('libgen_button');
var stopButton = document.getElementById('libgen_button_stop');
var resetButton = document.getElementById('libgen_button_reset');
var readarrItemList = document.getElementById("readarrItemList");
var selectAllCheckbox = document.getElementById("select-all");
var selectAllContainer = document.getElementById("select-all-container");
var progress_bar = document.getElementById('progress-status-bar');
var libgenDataTable = document.getElementById('libgen-data-table').getElementsByTagName('tbody')[0];
var configModal = document.getElementById('configModal');
var saveMessage = document.getElementById("saveMessage");
var saveChangesButton = document.getElementById("saveChangesBtn");
const readarrApiKey = document.getElementById("readarrApiKey");
const readarrMaxTags = document.getElementById("readarrMaxTags");
const readarrApiTimeout = document.getElementById("readarrApiTimeout");
const libgenSearchBase = document.getElementById("libgenSearchBase");
const libgenSearchType = document.getElementById("libgenSearchType");
const libgenSleepInterval = document.getElementById("libgenSleepInterval");
var readarr_items = [];
var socket = io();

selectAllCheckbox.addEventListener("change", function () {
    var isChecked = this.checked;
    var checkboxes = document.querySelectorAll('input[name="readarr_item"]');
    checkboxes.forEach(function (checkbox) {
        checkbox.checked = isChecked;
    });
});

readarrButton.addEventListener('click', function () {
    readarrButton.disabled = true;
    readarrSpinner.style.display = "inline-flex";
    readarrStatus.textContent = "Accessing Readarr";
    readarrItemList.innerHTML = '';
    socket.emit("readarr");
});

libgenButton.addEventListener('click', function () {
    libgenButton.disabled = true;
    libgenSpinner.style.display = "inline-flex";
    var checkedItems = [];
    for (var i = 0; i < readarr_items.length; i++) {
        var checkbox = document.getElementById("readarr_" + i);
        if (checkbox.checked) {
            checkedItems.push(checkbox.value);
        }
    }
    socket.emit("libgen", { "Data": checkedItems });
});

stopButton.addEventListener('click', function () {
    socket.emit("stopper");
});

configModal.addEventListener('show.bs.modal', function (event) {
    socket.emit("loadSettings");

    function handleSettingsLoaded(settings) {
        readarrApiKey.value = settings.readarrApiKey;
        readarrMaxTags.value = settings.readarrMaxTags;
        readarrApiTimeout.value = settings.readarrApiTimeout;
        libgenSearchBase.value = settings.libgenSearchBase;
        libgenSearchType.value = settings.libgenSearchType;
        libgenSleepInterval.value = settings.libgenSleepInterval;
        socket.off("settingsLoaded", handleSettingsLoaded);
    }
    socket.on("settingsLoaded", handleSettingsLoaded);
});

saveChangesButton.addEventListener("click", () => {
    socket.emit("updateSettings", {
        "readarrApiKey": readarrApiKey.value,
        "readarrMaxTags": readarrMaxTags.value,
        "readarrApiTimeout": readarrApiTimeout.value,
        "libgenSearchBase": libgenSearchBase.value,
        "libgenSearchType": libgenSearchType.value,
        "libgenSleepInterval": libgenSleepInterval.value
    });
    saveMessage.style.display = "block";
    setTimeout(function () {
        saveMessage.style.display = "none";
    }, 1000);
});

resetButton.addEventListener('click', function () {
    socket.emit("reset");
    libgenDataTable.innerHTML = '';
    libgenSpinner.style.display = "none";
    libgenStatus.textContent = "";
});

socket.on("readarr_status", (response) => {
    if (response.Status == "Success") {
        readarrButton.disabled = false;
        readarrStatus.textContent = "List Retrieved";
        readarrSpinner.style.display = "none";
        readarr_items = response.Data;
        readarrItemList.innerHTML = '';
        selectAllContainer.style.display = "block";
        selectAllCheckbox.checked = false;
        for (var i = 0; i < readarr_items.length; i++) {
            var item = readarr_items[i];

            var div = document.createElement("div");
            div.className = "form-check";

            var input = document.createElement("input");
            input.type = "checkbox";
            input.className = "form-check-input";
            input.id = "readarr_" + i;
            input.name = "readarr_item";
            input.value = item;

            var label = document.createElement("label");
            label.className = "form-check-label";
            label.htmlFor = "readarr_" + i;
            label.textContent = item;

            input.addEventListener("change", function () {
                selectAllCheckbox.checked = false;
            });

            div.appendChild(input);
            div.appendChild(label);

            readarrItemList.appendChild(div);
        }
    }
    else {
        readarrStatus.textContent = "";
        var errorDiv = document.createElement("div");
        errorDiv.textContent = response.Code + " : " + response.Data;
        errorDiv.style.wordBreak = "break-all";
        readarrItemList.appendChild(errorDiv);
        readarrStatus.textContent = "Error Accessing Readarr";
    }
    readarrSpinner.style.display = "none";
    readarrButton.disabled = false;
});

socket.on("libgen_status", (response) => {
    if (response.Status == "Success") {
        libgenSpinner.style.display = "none";
        libgenStatus.textContent = "";
    } else {
        libgenStatus.textContent = response.Data;
    }
    libgenButton.disabled = false;
});

function updateProgressBar(percentage, status) {
    progress_bar.style.width = percentage + "%";
    progress_bar.ariaValueNow = percentage + "%";
    progress_bar.classList.remove("progress-bar-striped");
    progress_bar.classList.remove("progress-bar-animated");

    if (status === "Running") {
        progress_bar.classList.remove("bg-primary", "bg-danger", "bg-dark");
        progress_bar.classList.add("bg-success");
        progress_bar.classList.add("progress-bar-animated");

    } else if (status === "Stopped") {
        progress_bar.classList.remove("bg-primary", "bg-success", "bg-dark");
        progress_bar.classList.add("bg-danger");

    } else if (status === "Idle") {
        progress_bar.classList.remove("bg-success", "bg-danger", "bg-dark");
        progress_bar.classList.add("bg-primary");

    } else if (status === "Complete") {
        progress_bar.classList.remove("bg-primary", "bg-success", "bg-danger");
        progress_bar.classList.add("bg-dark");
    }
    progress_bar.classList.add("progress-bar-striped");
}

socket.on("progress_status", (response) => {
    libgenDataTable.innerHTML = '';
    response.Data.forEach(function (item) {
        var row = libgenDataTable.insertRow();
        var cellItem = row.insertCell(0);
        var cellLinkFound = row.insertCell(1);

        cellItem.innerHTML = item.Item;
        cellLinkFound.innerHTML = item.Status;
    });
    var percent_completion = response.Percent_Completion;
    var actual_status = response.Status;
    updateProgressBar(percent_completion, actual_status);
});

const themeSwitch = document.getElementById('themeSwitch');
const savedTheme = localStorage.getItem('theme');
const savedSwitchPosition = localStorage.getItem('switchPosition');

if (savedSwitchPosition) {
    themeSwitch.checked = savedSwitchPosition === 'true';
}

if (savedTheme) {
    document.documentElement.setAttribute('data-bs-theme', savedTheme);
}

themeSwitch.addEventListener('click', () => {
    if (document.documentElement.getAttribute('data-bs-theme') === 'dark') {
        document.documentElement.setAttribute('data-bs-theme', 'light');
    } else {
        document.documentElement.setAttribute('data-bs-theme', 'dark');
    }
    localStorage.setItem('theme', document.documentElement.getAttribute('data-bs-theme'));
    localStorage.setItem('switchPosition', themeSwitch.checked);
});
