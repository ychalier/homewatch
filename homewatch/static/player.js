window.addEventListener("load", () => {


const STATE_NOTHINGSPECIAL = 0;
const STATE_OPENING = 1;
const STATE_BUFFERING = 2;
const STATE_PLAYING = 3;
const STATE_PAUSED = 4;
const STATE_STOPPED = 5;
const STATE_ENDED = 6;
const STATE_ERROR = 7;


/**
 * Websocket logic
 */

var websocket;
var websocketRetryCount = 0;

async function connectWebsocket() {
    const wssUrl = await fetch(`${API_URL}/wss`).catch((error) => {
        retryConnection({reason: error});
    }).then(res => res.text());
    websocket = new WebSocket(wssUrl);
    websocket.onopen = () => {
        websocketRetryCount = 0;
        console.log("Websocket is connected");
        document.body.classList.remove("wss-disconnected");
        document.body.classList.add("wss-connected");
    }
    websocket.onmessage = (message) => {
        const key = message.data.slice(0, 4);
        const value = message.data.slice(5);
        switch(key) {
            case "TIME":
                player.setTime(parseInt(value), false);
                break;
            case "MPTH":
                player.setMediaPath(value);
                break;
            case "MSTT":
                player.setState(parseInt(value));
                break;
            case "QUEU":
                player.fetchQueue();
                break;
            case "SDEL":
                player.setSubtitlesDelay(parseInt(value));
                break;
        }
        websocket.send("PONG");
    };
    websocket.onclose = (event) => {
        retryConnection(event);
    };
    websocket.onerror = (err) => {
        console.error("Socket encountered error: ", err.message, "Closing socket");
        websocket.close();
    };
}

function retryConnection(event) {
    websocketRetryCount++;
    let delay = 1;
    if (websocketRetryCount >= 10) {
        delay = 30;
    } else if (websocketRetryCount >= 3) {
        delay = 5;
    }
    document.body.classList.add("wss-disconnected");
    document.body.classList.remove("wss-connected");
    console.log(`Socket is closed. Reconnect will be attempted in ${delay} second.`, event.reason);
    setTimeout(() => { connectWebsocket(); }, delay * 1000);
}

connectWebsocket();


function setSelectValue(selector, value) {
    document.querySelectorAll(selector).forEach(select => {
        select.querySelectorAll("option").forEach(option => {
            if (option.value == `${value}` || (option.value == "" && value == null)) {
                option.selected = true;
            } else {
                option.removeAttribute("selected");
            }
        });
    });
}


function setPlayerSources(selector, sourceList, callback, addNone=false) {
    document.querySelectorAll(selector).forEach(container => {
        container.innerHTML = "";
        if (addNone) {
            let sel = container.appendChild(document.createElement("option"));
            sel.value = "";
            sel.textContent = "Aucune";
        }
        sourceList.forEach((source, i) => {
            let sel = container.appendChild(document.createElement("option"));
            sel.value = i;
            if (source.title == null && source.lang == null) {
                sel.textContent = "Piste inconnue";
            } else if (source.title == null) {
                sel.textContent = source.lang;
            } else if (source.lang == null) {
                sel.textContent = source.title;
            } else {
                sel.textContent = `${source.title} [${source.lang}]`;
            }
        });
        container.addEventListener("change", () => {
            let selectedIndex = null;
            for (const option of container.querySelectorAll("option")) {
                if (option.selected) {
                    selectedIndex = option.value;
                    break;
                }
            }
            callback(selectedIndex);
        });
    });
}


function inflateMediaSubtitle(media, container) {
    container.innerHTML = "";
    if (media.counter != null) {
        create(container, "span", "subtitle-item").textContent = `#${ media.counter }`;
    }
    if (media.season != null) {
        create(container, "span", "subtitle-item").textContent = `Saison ${ media.season }`;
    }
    if (media.episode != null) {
        create(container, "span", "subtitle-item").textContent = `Épisode ${ media.episode }`;
    }
    if (media.director != null) {
        create(container, "span", "subtitle-item").textContent = `${ media.director }`;
    }
    if (media.year != null) {
        create(container, "span", "subtitle-item").textContent = `${ media.year }`;
    }
    create(container, "span", "subtitle-item").textContent = formatDuration(media.duration, true);
}


class Player {

    constructor() {
        this.mediaPath = null;
        this.media = null;
        this.time = null;
        this.state = null;
        this.audio = null;
        this.subs = null;
        this.volume = null;
        this.subtitlesDelay = null;
        this.aspectRatio = null;
        this.autoplay = null;
        this.shuffle = null;
        this.closeOnEnd = null;
        this.sleepAt = null;
        this.queue = null;
    }

    loadPlayerData(playerData) {
        this.setMediaPath(playerData.mediaPath);
        this.setState(playerData.state);
        this.setTime(playerData.time, false);
        this.setAudio(playerData.audio, false);
        this.setSubs(playerData.subs, false);
        this.setVolume(playerData.volume);
        this.setSubtitlesDelay(playerData.subtitlesDelay, false);
        this.setAutoplay(playerData.autoplay, false);
        this.setShuffle(playerData.shuffle, false);
        this.setCloseOnEnd(playerData.closeOnEnd, false);
        this.setSleepAt(playerData.sleepAt, false);
        this.setAspectRatio(playerData.aspectRatio, false);
    }

    fetchMedia() {
        fetch(`${API_URL}/media?path=${this.mediaPath.replaceAll("&", "%26")}`)
            .then(res => res.json())
            .then(data => {
                this.setMedia(data);
            });
    }

    fetchQueue() {
        fetch(`${API_URL}/queue`)
            .then(res => res.json())
            .then(data => {
                this.setQueue(data);
            });
    }

    setMediaPath(newMediaPath) {
        if (newMediaPath == "None") newMediaPath = null;
        if (newMediaPath != null && this.mediaPath == null) {
            document.querySelector(".player").classList.remove("hidden");
        }
        if (this.mediaPath == newMediaPath) return;
        this.mediaPath = newMediaPath;
        this.fetchMedia();
        this.fetchQueue();
    }

    setMedia(newMedia) {
        console.log("Setting media:", newMedia);
        var self = this;
        this.media = newMedia;
        const thumbnailUrl = MEDIA_URL + this.media.folder + "/" + this.media.thumbnail;
        document.querySelector(".player-left img").src = thumbnailUrl;
        document.querySelector(".player-left .title").textContent = this.media.title;
        inflateMediaSubtitle(this.media, document.querySelector(".player-left .subtitle"));
        document.querySelectorAll(".timebar-input").forEach(input => {
            input.max = this.media.duration * 1000;
        });
        setPlayerSources("#player-audio-sources", this.media.audio_sources, (index) => {
            self.setAudio(index, true);
        });
        setPlayerSources("#player-subtitle-sources", this.media.subtitle_sources, (index) => {
            self.setSubs(index == null ? -1 : index, true);
        }, true);
        setSelectValue("#player-audio-sources", this.audio);
        setSelectValue("#player-subtitle-sources", this.subs);
        displayTime(self.time);
        if (this.media.duration < 15 * 60 && this.closeOnEnd) {
            alert("Media is shorter than 15 minutes and close on end is enabled. Disabling close on end.");
            this.setCloseOnEnd(false, true);
        }
    }

    setQueue(newQueue) {
        this.queue = newQueue;
        const container = document.getElementById("queue");
        const template = document.getElementById("template-queue-media");
        container.innerHTML = "";
        for (let i = 0; i < this.queue.elements.length; i++) {
            const media = this.queue.elements[this.queue.ordering[i]];
            const element = document.importNode(template.content, true);
            const thumbnailUrl = MEDIA_URL + media.folder + "/" + media.thumbnail;
            element.querySelector(".inline-media-poster").src = thumbnailUrl;
            element.querySelector(".title").textContent = media.title;
            element.querySelector(".subtitle").textContent = media.subtitle;
            element.querySelector(".queue-media").addEventListener("click", () => {
                websocket.send(`JUMP ${i}`);
            });
            if (i < this.queue.current) {
                element.querySelector(".queue-media").classList.add("queue-previous");
            } else if (i == this.queue.current) {
                element.querySelector(".queue-media").classList.add("queue-current");
            } else {
                element.querySelector(".queue-media").classList.add("queue-next");
            }
            container.appendChild(element);
        }
        if (this.queue.current != null) {
            container.querySelector(".queue-current").scrollIntoView();
        }
    }

    setTime(newTime, notify=true) {
        this.time = newTime;
        if (!seeking) {
            displayTime(this.time);
        }
        if (notify) {
            websocket.send(`SEEK ${this.time}`);
        }
    }

    setState(newState) {
        this.state = newState;
        const icon = document.querySelector("#button-play .icon");
        if (this.state == STATE_PLAYING) {
            icon.className = "icon icon-pause";
        } else {
            icon.className = "icon icon-play";
        }
    }

    setAudio(newAudio, notify=true) {
        this.audio = parseInt(newAudio);
        if (this.media != null) {
            setSelectValue("#player-audio-sources", this.audio);
        }
        if (notify) {
            websocket.send(`ASRC ${this.audio}`);
        }
    }

    setSubs(newSubs, notify=true) {
        this.subs = (newSubs === "" || newSubs === null) ? null : parseInt(newSubs);
        if (this.media != null) {
            setSelectValue("#player-subtitle-sources", this.subs);
        }
        if (notify) {
            websocket.send(`SSRC ${this.subs == null ? "" : this.subs}`);
        }
    }

    setVolume(newVolume, notify=true) {
        this.volume = parseInt(newVolume);
        document.getElementById("player-volume").value = this.volume;
        displayVolume(this.volume);
        if (notify) {
            websocket.send(`VOLU ${this.volume}`);
        }
    }

    setSubtitlesDelay(newDelay) {
        this.subtitlesDelay = newDelay;
        document.getElementById("player-subtitles-delay").textContent = `${this.subtitlesDelay.toFixed(0)} ms`;
    }

    setAspectRatio(newAspectRatio, notify=true) {
        this.aspectRatio = newAspectRatio == null ? "" : newAspectRatio;
        setSelectValue("#player-select-aspect", this.aspectRatio);
        if (notify) {
            websocket.send(`ASPR ${this.aspectRatio}`);
        }
    }

    setAutoplay(newAutoplay, notify=true) {
        this.autoplay = newAutoplay;
        if (this.autoplay) {
            document.getElementById("button-autoplay").classList.remove("off");
        } else {
            document.getElementById("button-autoplay").classList.add("off");
        }
        if (notify) {
            websocket.send(`AUTO ${this.autoplay ? "1" : "0"}`);
        }
    }

    setShuffle(newShuffle, notify=true) {
        this.shuffle = newShuffle;
        if (this.shuffle) {
            document.getElementById("button-shuffle").classList.remove("off");
        } else {
            document.getElementById("button-shuffle").classList.add("off");
        }
        if (notify) {
            websocket.send(`SHUF ${this.shuffle ? "1" : "0"}`);
        }
        this.fetchQueue();
    }

    setCloseOnEnd(newCloseOnEnd, notify=true) {
        this.closeOnEnd = newCloseOnEnd;
        document.getElementById("button-closeonend").textContent = "Éteindre le serveur après la lecture : " + (this.closeOnEnd ? "ON" : "OFF");
        if (notify) {
            websocket.send(`CLOS ${this.closeOnEnd ? "1" : "0"}`);
        }
    }

    setSleepAt(newSleepAt, notify=true) {
        console.log("New sleep at:", newSleepAt);
        this.sleepAt = newSleepAt;
        displaySleepAt();
        if (notify) {
            websocket.send(`SLEE ${this.sleepAt == null ? "0" : this.sleepAt}`);
        }
    }

}

function displaySleepAt() {
    if (player.sleepAt == null) {
        document.getElementById("button-sleep").textContent = "Mise en veille automatique : OFF";
    } else {
        let sleepin = Math.max(0, (new Date(player.sleepAt * 1000) - new Date()) / 1000);
        document.getElementById("button-sleep").textContent = `Mise en veille automatique ${formatDuration(sleepin)}`;
    }
}

setInterval(displaySleepAt, 1000);

var player = new Player();

fetch(`${API_URL}/player`).then(res =>  res.json()).then(data => {
    player.loadPlayerData(data);
});

function closePreviousStatus() {
    document.querySelectorAll(".modal-previous-status").forEach(remove);
}

function askUserForLoadingPreviousStatus(status) {
    const template = document.getElementById("template-previous-status");
    const node =  document.importNode(template.content, true);
    node.querySelector(".poster").src = MEDIA_URL + status.player.media.folder + "/" + status.player.media.thumbnail;
    node.querySelector(".title").textContent = status.player.media.title;
    node.querySelector(".subtitle").textContent = status.player.media.subtitle;
    node.querySelector(".time").textContent = formatDuration(status.player.time / 1000);
    node.querySelector(".previous-status-load").addEventListener("click", () => {
        fetch(`${API_URL}/status/load`).then(res => res.text()).then();
        closePreviousStatus();
    });
    node.querySelector(".previous-status-cancel").addEventListener("click", closePreviousStatus);
    node.querySelector(".modal-button-close").addEventListener("click", closePreviousStatus);
    node.querySelector(".modal-overlay").addEventListener("click", closePreviousStatus);
    document.body.appendChild(node);
}

if (FIRST_LIBRARY_LOAD) {
    fetch(`${API_URL}/status/read`).then(res => res.json()).then(data => {
        if (data != null && data.player != null && (data.player.state == STATE_PLAYING || data.player.state == STATE_PAUSED)) {
            askUserForLoadingPreviousStatus(data);
        }
    });
}

/**
 * Event listeners
 */

window.addEventListener("focus", () => {
    websocket.send("MEDI");
    player.fetchQueue();
});

function bindButton(buttonId, callback) {
    document.getElementById(buttonId).addEventListener("click", () => {
        callback();
    });
}

function setPlayerCollapsed(collapsed=null) {
    const domPlayer = document.querySelector(".player-layout");
    if (collapsed == null) {
        collapsed = !domPlayer.classList.contains("collapsed");
    }
    const icon = document.querySelector("#button-collapse .icon");
    if (collapsed) {
        domPlayer.classList.add("collapsed");
        icon.className = "icon icon-expand";
    } else {
        domPlayer.classList.remove("collapsed");
        icon.className = "icon icon-collapse";
    }
}

bindButton("button-collapse", setPlayerCollapsed);

document.querySelector(".library").addEventListener("click", () => {
    setPlayerCollapsed(true);
});

bindButton("button-play", () => {
    if (player.state == STATE_PLAYING || player.state == STATE_PAUSED) {
        websocket.send("PAUS");
    } else if (player.state == STATE_STOPPED) {
        websocket.send("PLAY");
    } else if (player.state == STATE_ENDED) {
        websocket.send("RPLY");
    }
});

bindButton("button-rewind", () => {
    websocket.send("RWND");
});

bindButton("button-fastforward", () => {
    websocket.send("FFWD");
});

bindButton("button-subs-delay-later", () => {
    websocket.send("SLAT");
});

bindButton("button-subs-delay-earlier", () => {
    websocket.send("SEAR");
});

bindButton("button-subs-delay-reset", () => {
    websocket.send("SRST");
});

function displayVolume(volume) {
    document.getElementById("player-volume-value").textContent = `${volume} %`;
    const icon = document.querySelector("#volume-icon");
    icon.className = "panel-title-icon icon";
    if (volume >= 90) {
        icon.classList.add("icon-volume-max");
    } else if (volume >= 50) {
        icon.classList.add("icon-volume-mid");
    } else if (volume > 0) {
        icon.classList.add("icon-volume-min");
    } else {
        icon.classList.add("icon-volume-off");
    }
}

document.getElementById("player-volume").addEventListener("change", (event) => {
    player.setVolume(parseInt(event.target.value));
});

document.getElementById("player-volume").addEventListener("input", (event) => {
    displayVolume(parseInt(event.target.value));
});

document.getElementById("player-select-aspect").addEventListener("change", (event) => {
    let value = "";
    for (const option of event.target.querySelectorAll("option")) {
        if (option.selected) {
            value = option.value;
            break;
        }
    }
    player.setAspectRatio(value);
});

var seeking = false;

function displayTime(timeMs) {
    const timeSeconds = Math.max(0, timeMs / 1000);
    if (!seeking) {
        document.querySelectorAll(".timebar-input").forEach(input => {
            input.value = timeMs;
        });
    }
    document.querySelectorAll(".timebar-elapsed").forEach(span => {
        span.textContent = formatDuration(timeSeconds);
    });
    document.querySelectorAll(".timebar-remaining").forEach(span => {
        if (player.media != null) {
            span.textContent = "-" + formatDuration(Math.max(0, player.media.duration - timeSeconds));
        } else {
            span.textContent = "-:--";
        }
    });
}

document.querySelectorAll(".timebar-input").forEach(input => {
    input.addEventListener("pointerdown", (e) => {
        seeking = true;
    });
    input.addEventListener("pointermove", (e) => {
        if (seeking) {
            displayTime(parseInt(input.value));
        }
    });
    input.addEventListener("pointerup", (e) => {
        seeking = false;
        player.setTime(parseInt(input.value));
    });
});

bindButton("button-prev", () => { websocket.send("PREV"); });

bindButton("button-next", () => { websocket.send("NEXT"); });

bindButton("button-autoplay", () => { player.setAutoplay(!player.autoplay); });

bindButton("button-shuffle", () => { player.setShuffle(!player.shuffle); });

bindButton("button-closeonend", () => { player.setCloseOnEnd(!player.closeOnEnd); });

bindButton("button-sleep", () => {
    const answer = prompt("Mettre en veille dans (en minutes, laisser vide pour désactiver):", 30);
    if (answer != null) {
        if (answer.trim() == "" || answer.trim() == "0") {
            player.setSleepAt(null, true);
        } else {
            const newSleepAt = (new Date()) / 1000 + parseFloat(answer) * 60;
            player.setSleepAt(Math.round(newSleepAt), true);
        }
    }
});

/**
 * Player panels
 */

function bindPanel(buttonId, panelId) {
    const button = document.getElementById(buttonId);
    const panel = document.getElementById(panelId);
    button.addEventListener("click", () => {
        document.querySelector(".panel-overlay").classList.add("active");
        panel.classList.add("active");
    });
}

document.querySelector(".panel-overlay").addEventListener("click", () => {
    document.querySelector(".panel-overlay").classList.remove("active");
    document.querySelectorAll(".panel").forEach(panel => {
        panel.classList.remove("active");
    });
});

bindPanel("button-queue", "panel-queue");
bindPanel("button-settings", "panel-settings");

});