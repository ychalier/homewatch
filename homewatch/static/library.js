window.addEventListener("load", () => {

const DEFAULT_LONG_PRESS_TIMEOUT = 500;
var pressTimer = null;

function registerUserLocation() {
    const userLocation = {
        pathname: window.location.pathname,
        scroll: document.querySelector(".library").scrollTop
    }
    localStorage.setItem(STORAGE_KEY_USER_LOCATION, JSON.stringify(userLocation));
}
registerUserLocation();
document.querySelector(".library").addEventListener("scroll", () => {
    registerUserLocation();
    clearTimeout(pressTimer);
});

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.has("scroll")) {
    const scrollY = parseFloat(urlParams.get("scroll"));
    document.querySelector(".library").scrollTo(0, scrollY);
}

function setViewedMedia(path, viewed, mediaProgress) {
    fetch(`${API_URL}/history?path=${path}&viewed=${viewed}`, {method: "post"})
        .then(() => {
            closeMediaDetails();
            mediaProgress.value = viewed == 1 ? parseFloat(mediaProgress.max) : 0;
        });
}

function setViewedFolder(path, viewed) {
    fetch(`${API_URL}/history?path=${path}&viewed=${viewed}`, {method: "post"})
        .then(() => {
            window.location.reload();
        });
}

function closeMediaDetails() {
    document.querySelectorAll(".modal-media-details").forEach(remove);
}

function showMediaDetails(mediaElement) {
    const template = document.getElementById("template-media-details");
    const detailsElement =  document.importNode(template.content, true);
    detailsElement.querySelector(".modal-background").src = mediaElement.querySelector(".media-poster").src;
    detailsElement.querySelector(".title").innerHTML = mediaElement.querySelector(".title").innerHTML;
    detailsElement.querySelector(".subtitle").innerHTML = mediaElement.querySelector(".subtitle").innerHTML;
    detailsElement.querySelector(".media-details-url").href = mediaElement.getAttribute("href");
    if (PLAYERMODE) {
        const path = mediaElement.getAttribute("path");
        detailsElement.querySelector(".media-details-play").addEventListener("click", () => {
            loadAndPlay(path).then(closeMediaDetails);
        });
        detailsElement.querySelector(".media-details-queue").addEventListener("click", () => {
            loadAndPlay(path, null, "next").then(closeMediaDetails);
        });
        const buttonResume = detailsElement.querySelector(".media-details-resume");
        const mediaProgress = mediaElement.querySelector("progress");
        const seek = parseInt(mediaProgress.value);
        const duration = parseInt(mediaProgress.max);
        if (mediaProgress == null) {
            remove(buttonResume);
        } else {
            if (seek > 0 && seek < .98 * duration) {
                buttonResume.textContent = `Reprendre (${formatDuration(seek / 1000)})`;
                buttonResume.addEventListener("click", () => {
                    loadAndPlay(path, seek).then(closeMediaDetails);
                });
            } else {
                remove(buttonResume);
            }
        }
        const buttonMarkAsViewed = detailsElement.querySelector(".media-details-viewed");
        if (seek < .98 * duration) {
            buttonMarkAsViewed.addEventListener("click", () => {
                setViewedMedia(path, 1, mediaProgress);
            });
        } else {
            remove(buttonMarkAsViewed);
        }
        const buttonMarkAsUnviewed = detailsElement.querySelector(".media-details-unviewed");
        if (seek > 0) {
            buttonMarkAsUnviewed.addEventListener("click", () => {
                setViewedMedia(path, 0, mediaProgress);
            });
        } else {
            remove(buttonMarkAsUnviewed);
        }
    }
    detailsElement.querySelector(".modal-button-close").addEventListener("click", closeMediaDetails);
    detailsElement.querySelector(".modal-overlay").addEventListener("click", closeMediaDetails);
    document.body.appendChild(detailsElement);
}

window.addEventListener("contextmenu", (event) => {
    event.preventDefault();
});

for (const mediaElement of document.querySelectorAll(".media")) {
    mediaElement.addEventListener("mouseup", () => {
        showMediaDetails(mediaElement);
    });
    mediaElement.addEventListener("touchstart", () => {
        pressTimer = window.setTimeout(() => {
            showMediaDetails(mediaElement);
        }, DEFAULT_LONG_PRESS_TIMEOUT);
        return false; 
    });
    mediaElement.addEventListener("touchend", () => {
        clearTimeout(pressTimer);
    });
}

if (PLAYERMODE) {
    document.getElementById("button-play-folder").addEventListener("click", () => {
        loadAndPlay(FOLDER, null, "folder");
    });
    document.getElementById("button-viewed-folder").addEventListener("click", () => {
        if (confirm(`Marquer tous les éléments et sous-dossiers de ${ FOLDER } comme vus ?`)) {
            setViewedFolder(FOLDER, 1);
        }
    });
    document.getElementById("button-unviewed-folder").addEventListener("click", () => {
        if (confirm(`Marquer tous les éléments et sous-dossiers de ${ FOLDER } comme non vus ?`)) {
            setViewedFolder(FOLDER, 0);
        }
    });
    for (const playlist of document.querySelectorAll(".playlist")) {
        playlist.addEventListener("click", () => {
            if (confirm(`Lire ${playlist.querySelector(".title").textContent} ?`)) {
                loadAndPlay(playlist.getAttribute("path"), null, "playlist");
            }
        });
    }
}

const FILTER_UNSEEN = 0;
const FILTER_LANGUAGE = 1;
const FILTER_SHORT = 2;
const FILTERS = [];

function toggleFilter(filter) {
    if (FILTERS.includes(filter)) {
        FILTERS.splice(FILTERS.indexOf(filter), 1);
    } else {
        FILTERS.push(filter);
    }
    updateFilters();
}

function updateFilters() {
    for (let filter = 0; filter <= 2; filter++) {
        const domFilterElement = document.querySelector(`.library-filter[filter="${filter}"]`);
        if (domFilterElement == null) continue;
        if (FILTERS.includes(filter)) {
            domFilterElement.classList.add("active");
        } else {
            domFilterElement.classList.remove("active");
        }
    }
    document.querySelectorAll(".media").forEach(media => {
        let shouldBeSeen = true;
        if (FILTERS.includes(FILTER_UNSEEN)) {
            const progress = media.querySelector("progress");
            shouldBeSeen = shouldBeSeen && (parseFloat(progress.value) < .9 * parseFloat(progress.max));
        }
        if (FILTERS.includes(FILTER_LANGUAGE)) {
            const hasLanguage = media.querySelector(".media-badge-language") != null;
            shouldBeSeen = shouldBeSeen && hasLanguage;
        }
        if (FILTERS.includes(FILTER_SHORT)) {
            const durationMs = parseFloat(media.getAttribute("duration"));
            shouldBeSeen = shouldBeSeen && (durationMs < 20 * 60 * 1000);
        }
        if (shouldBeSeen) {
            media.parentElement.classList.remove("hidden");
        } else {
            media.parentElement.classList.add("hidden");
        }
    });
}

document.querySelectorAll(".library-filter").forEach(filterElement => {
    filterElement.addEventListener("click", () => {
        toggleFilter(parseInt(filterElement.getAttribute("filter")));
    });
});

});