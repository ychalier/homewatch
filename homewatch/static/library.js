window.addEventListener("load", () => {

const DEFAULT_LONG_PRESS_TIMEOUT = 500;

const SORT_DEFAULT = 0;
const SORT_TITLE = 1;
const SORT_DIRECTOR = 2;
const SORT_YEAR = 3;
const SORT_DURATION = 4;
const FILTER_UNSEEN = 0;
const FILTER_LANGUAGE = 1;
const FILTER_SHORT = 2;
const FILTER_CHROMECAST = 3;
const FILTER_HTML5 = 4;

const sortSelect = document.querySelector("select.library-sort");
var pressTimer = null;
var currentSortKey = null;
var currentFilters = [];


function registerUserLocation() {
    const userLocation = {
        pathname: window.location.pathname,
        scroll: document.querySelector(".library").scrollTop,
        sort: currentSortKey,
        filters: currentFilters,
    }
    localStorage.setItem(STORAGE_KEY_USER_LOCATION, JSON.stringify(userLocation));
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
    if (ENABLE_CHROMECAST) {
        detailsElement.querySelector(".media-details-cast").href = CAST_URL + "?" + new URLSearchParams({
            url: "http://" + window.location.host + mediaElement.getAttribute("href"),
            type: mediaElement.getAttribute("type"),
        }).toString();
    }
    if (PLAYERMODE) {
        const path = mediaElement.getAttribute("path");
        detailsElement.querySelector(".media-details-play").addEventListener("click", () => {
            loadAndPlay(path, null, "media", getQueueIndex()).then(closeMediaDetails);
        });
        detailsElement.querySelector(".media-details-queue").addEventListener("click", () => {
            loadAndPlay(path, null, "next", null).then(closeMediaDetails);
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
                    loadAndPlay(path, seek, "media", getQueueIndex()).then(closeMediaDetails);
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


function getQueueIndex() {
    const mediaContainer = document.querySelector(".library-section.library-medias");
    const queueIndex = [];
    mediaContainer.querySelectorAll(".media-wrapper:not(.hidden) .media").forEach(media => {
        queueIndex.push(parseInt(media.getAttribute("index")) - 1);
    });
    return queueIndex;
}


const preventEventDefault = event => event.preventDefault();


function readSortKey() {
    let sortingKeyString = getSelectedOption(sortSelect);
    switch (sortingKeyString) {
        case "title":
            currentSortKey = SORT_TITLE;
            break;
        case "director":
            currentSortKey = SORT_DIRECTOR;
            break;
        case "year":
            currentSortKey = SORT_YEAR;
            break;
        case "duration":
            currentSortKey = SORT_DURATION;
            break;
        case "default":
        default:
            currentSortKey = SORT_DEFAULT;
            break;
    }
}

/**
 * Remove diacritics and lower a string, for generalized comparison.
 * @param {String} string The string to normalize 
 * @returns The normalized string
 */
function normalizeString(string) {
    if (string == null) {
        return null;
    }
    return string.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}


function extractSortKeyValue(mediaElement, sortKey) {
    let value;
    switch(sortKey) {
        case SORT_DEFAULT:
            value = [null, null, null, null];
            if (mediaElement.hasAttribute("counter")) {
                value[0] = parseInt(mediaElement.getAttribute("counter"));
            }
            if (mediaElement.hasAttribute("season")) {
                value[1] = parseInt(mediaElement.getAttribute("season"));
            }
            if (mediaElement.hasAttribute("episode")) {
                value[2] = parseInt(mediaElement.getAttribute("episode"));
            }
            if (mediaElement.hasAttribute("title")) {
                value[3] = mediaElement.getAttribute("title");
            }
            break;
        case SORT_TITLE:
            value = normalizeString(mediaElement.querySelector(".title").textContent);
            if (value == null) value = "ÿ";
            break;
        case SORT_DIRECTOR:
            value = normalizeString(mediaElement.getAttribute("director"));
            if (value == null) value = "ÿ";
            break;
        case SORT_YEAR:
            value = mediaElement.getAttribute("year");
            if (value == null) value = "9999";
            break;
        case SORT_DURATION:
            value = parseInt(mediaElement.getAttribute("duration"));
            break;
    }
    
    return value;
}


function compareSortKeys(a, b) {
    const aKey = a.key;
    const bKey = b.key;
    if (Array.isArray(aKey)) {
        for (let i = 0; i < aKey.length; i++) {
            if (aKey[i] == null && bKey[i] == null) {
                continue;
            } else if (bKey[i] == null) {
                return -1;
            } else if (aKey[i] == null) {
                return 1;
            } else {
                if (aKey[i] == bKey[i]) {
                    continue;
                }
                return aKey[i] < bKey[i] ? -1 : 1;
            }
        }
    } else {
        return aKey < bKey ? -1 : 1;
    }
}


function updateSort() {
    const mediaContainer = document.querySelector(".library-section.library-medias");
    const mediaElements = [];
    document.querySelectorAll(".media").forEach((mediaElement) => {
        mediaElements.push({
            element: mediaElement.parentElement, // .media-wrapper
            key: extractSortKeyValue(mediaElement, currentSortKey)
        })
    });
    mediaElements.sort(compareSortKeys);
    for (let i = 0; i < mediaElements.length; i++) {
        mediaContainer.appendChild(mediaElements[i].element);
    }
}


function toggleFilter(filter) {
    if (currentFilters.includes(filter)) {
        currentFilters.splice(currentFilters.indexOf(filter), 1);
    } else {
        currentFilters.push(filter);
    }
    updateFilters();
}


function updateFilters() {
    for (let filter = 0; filter <= 4; filter++) {
        const domFilterElement = document.querySelector(`.library-filter[filter="${filter}"]`);
        if (domFilterElement == null) continue;
        if (currentFilters.includes(filter)) {
            domFilterElement.classList.add("active");
        } else {
            domFilterElement.classList.remove("active");
        }
    }
    document.querySelectorAll(".media").forEach(media => {
        let shouldBeSeen = true;
        if (currentFilters.includes(FILTER_UNSEEN)) {
            const progress = media.querySelector("progress");
            shouldBeSeen = shouldBeSeen && (parseFloat(progress.value) < .9 * parseFloat(progress.max));
        }
        if (currentFilters.includes(FILTER_LANGUAGE)) {
            const hasLanguage = media.querySelector(".media-badge-language") != null;
            shouldBeSeen = shouldBeSeen && hasLanguage;
        }
        if (currentFilters.includes(FILTER_SHORT)) {
            const durationMs = parseFloat(media.getAttribute("duration"));
            shouldBeSeen = shouldBeSeen && (durationMs < 20 * 60 * 1000);
        }
        if (currentFilters.includes(FILTER_CHROMECAST)) {
            const isCastabale = media.querySelector(".media-badge-chromecast") != null;
            shouldBeSeen = shouldBeSeen && isCastabale;
        }
        if (currentFilters.includes(FILTER_HTML5)) {
            const isHtml5 = media.querySelector(".media-badge-html5") != null;
            shouldBeSeen = shouldBeSeen && isHtml5;
        }
        if (shouldBeSeen) {
            media.parentElement.classList.remove("hidden");
        } else {
            media.parentElement.classList.add("hidden");
        }
    });
}


for (const mediaElement of document.querySelectorAll(".media")) {
    mediaElement.addEventListener("mouseup", (event) => {
        if (event.button == 0) showMediaDetails(mediaElement);
    });
    mediaElement.addEventListener("touchstart", () => {
        mediaElement.addEventListener("contextmenu", preventEventDefault);
        pressTimer = window.setTimeout(() => {
            showMediaDetails(mediaElement);
        }, DEFAULT_LONG_PRESS_TIMEOUT);
        return false; 
    });
    mediaElement.addEventListener("touchend", () => {
        mediaElement.removeEventListener("contextmenu", preventEventDefault);
        clearTimeout(pressTimer);
    });
}

if (PLAYERMODE) {
    document.getElementById("button-play-folder").addEventListener("click", () => {
        loadAndPlay(FOLDER, null, "folder", null);
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
                loadAndPlay(playlist.getAttribute("path"), null, "playlist", null);
            }
        });
    }
}

sortSelect.addEventListener("input", () => {
    readSortKey();
    updateSort();
    registerUserLocation();
});

document.querySelectorAll(".library-filter").forEach(filterElement => {
    filterElement.addEventListener("click", () => {
        toggleFilter(parseInt(filterElement.getAttribute("filter")));
        registerUserLocation();
    });
});

document.querySelector(".library").addEventListener("scroll", () => {
    registerUserLocation();
    clearTimeout(pressTimer);
});

const userLocationString = localStorage.getItem(STORAGE_KEY_USER_LOCATION);
if (userLocationString != "" && userLocationString != null) {
    const userLocation = JSON.parse(userLocationString);
    if (window.location.pathname == userLocation.pathname) {
        if (userLocation.sort != undefined && userLocation.sort != null) {
            currentSortKey = userLocation.sort;
            switch(currentSortKey) {
                case SORT_DEFAULT:
                    setSelectedOption(sortSelect, "default");
                    break;
                case SORT_TITLE:
                    setSelectedOption(sortSelect, "title");
                    break;
                case SORT_DIRECTOR:
                    setSelectedOption(sortSelect, "director");
                    break;
                case SORT_YEAR:
                    setSelectedOption(sortSelect, "year");
                    break;
                case SORT_DURATION:
                    setSelectedOption(sortSelect, "duration");
                    break;
            }
        }
        if (userLocation.filters != undefined && userLocation.filters != null) {
            currentFilters = userLocation.filters;
        }
    }
}

registerUserLocation();

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.has("scroll")) {
    const scrollY = parseFloat(urlParams.get("scroll"));
    document.querySelector(".library").scrollTo(0, scrollY);
}

readSortKey();
updateSort();
updateFilters();

});