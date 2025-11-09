window.addEventListener("load", () => {

formLoadUrl.addEventListener("submit", (event => {
    event.preventDefault();
    formLoadUrl.classList.add("disabled");
    fetch(formLoadUrl.action, {method: "POST", body: new FormData(formLoadUrl)});
}));

document.querySelectorAll("button.button-action").forEach(button => {
    button.addEventListener("click", () => {
        websocket.send(`WEB ${button.getAttribute("action")}`);
    });
});

var websocket;
var websocketRetryCount = 0;


function capitalizeFirstLetter(val) {
    return String(val).charAt(0).toUpperCase() + String(val).slice(1);
}


function connectWebsocket() {
    websocket = new WebSocket(WSS_URL);
    websocket.onopen = () => {
        websocketRetryCount = 0;
        console.log("Websocket is connected");
    }
    websocket.onmessage = (message) => {
        console.log("Incoming message:", message);
        const key = message.data.slice(0, 7);
        const value = message.data.slice(8);
        switch(key) {
            case "WEBLOAD":
                const body = JSON.parse(value);
                formLoadUrl.classList.remove("disabled");
                webpanel.classList.add("active");
                playerTitle.textContent = body.title;
                playerState.textContent = capitalizeFirstLetter(body.state);
                playerState.setAttribute("href", body.url);
                webpanel.setAttribute("state", body.state);
                break;
            case "WEBCLOS":
                webpanel.classList.remove("active");
                break;
        }
        websocket.send("PONG");
    };
    websocket.onclose = (event) => {
        websocketRetryCount++;
        let delay = 1;
        if (websocketRetryCount >= 10) {
            delay = 30;
        } else if (websocketRetryCount >= 3) {
            delay = 5;
        }
        console.log(`Socket is closed. Reconnect will be attempted in ${delay} second.`, event.reason);
        setTimeout(() => { connectWebsocket(); }, delay * 1000);
    };
    websocket.onerror = (err) => {
        console.error("Socket encountered error: ", err.message, "Closing socket");
        websocket.close();
    };
}

connectWebsocket();

});