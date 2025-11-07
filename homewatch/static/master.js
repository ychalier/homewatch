const STORAGE_KEY_USER_LOCATION = "homewatch_user_location";


function create(parent=null, tag="div", className=null) {
    const element = document.createElement(tag);
    if (parent != null) {
        parent.appendChild(element);
    }
    if (className != null) {
        element.className = className;
    }
    return element;
}


function remove(element) {
    element.parentNode.removeChild(element);
}


function formatDuration(totalSeconds, simplified=false) {
    let hours = Math.floor(totalSeconds / 3600);
    let minutes = Math.floor((totalSeconds - 3600 * hours) / 60);
    let seconds = Math.floor(totalSeconds - 3600 * hours - 60 * minutes);
    if (simplified) {
        if (hours == 0) {
            return `${minutes} min`;
        } else {
            return `${hours}h${minutes.toString().padStart(2, "0")}`;
        }
    } else {
        if (hours == 0) {
            return `${minutes}:${seconds.toString().padStart(2, "0")}`;
        } else {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
        }
    }
}


function loadAndPlay(path, seek=null, target="media", queueIndex=null) {
    console.log("Loading and playing", path);
    let queueArgument = "";
    if (queueIndex != null) {
        queueArgument = `&queue=` + queueIndex.join(",");
    }
    return fetch(`${API_URL}/load?path=${path.replaceAll("&", "%26")}&target=${target}${queueArgument}` + (seek==null ? "" : `&seek=${seek}`));
}


function getSelectedOption(select) {
    for (const option of select.querySelectorAll("option")) {
        if (option.selected) {
            return option.value;
        }
    }
    return null;
}


function setSelectedOption(select, value) {
    for (const option of select.querySelectorAll("option")) {
        if (option.value == value) {
            option.selected = true;
        } else {
            option.removeAttribute("selected");
        }
    }
}


window.addEventListener("load", () => {
    
window.addEventListener("click", () => {
    document.querySelectorAll(".menu").forEach(menu => {
        menu.classList.remove("active");
    });
});

document.querySelectorAll(".menu").forEach(menu => {
    const icon = menu.querySelector(".menu-icon");
    icon.addEventListener("click", (event) => {
        event.stopPropagation();
        menu.classList.add("active");
        return false;
    });
});

function showModalShutdown() {
    const template = document.getElementById("template-modal-shutdown");
    const mainElement =  document.importNode(template.content, true);
    mainElement.querySelector(".modal-button-close").addEventListener("click", closeModals);
    mainElement.querySelector(".modal-overlay").addEventListener("click", closeModals);
    mainElement.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", (event) => {
            if (confirm(`Confirmer ${button.textContent.toLowerCase()} ?`)) {
                fetch(button.getAttribute("href"));
                closeModals();
            } else {
                event.preventDefault();
            }
        });
    });
    document.body.appendChild(mainElement);
}

function closeModals() {
    document.querySelectorAll(".modal").forEach(remove);
}

const linkShutdown = document.getElementById("link-shutdown");
if (linkShutdown != null) {
    linkShutdown.addEventListener("click", showModalShutdown);
}

function showModalWaitingScreen() {
    const template = document.getElementById("template-modal-waiting-screen");
    const mainElement =  document.importNode(template.content, true);
    mainElement.querySelector(".modal-button-close").addEventListener("click", closeModals);
    mainElement.querySelector(".modal-overlay").addEventListener("click", closeModals);
    mainElement.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", (event) => {
            fetch(button.getAttribute("href"));
            closeModals();
        });
    });
    document.body.appendChild(mainElement);
}

const linkWaitingScreen = document.getElementById("link-waiting-screen");
if (linkWaitingScreen != null) {
    linkWaitingScreen.addEventListener("click", showModalWaitingScreen);
}

});