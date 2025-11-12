window.addEventListener("load", () => {

const wssClient = new WebsocketClient(API_URL, (message) => {
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
})

formLoadUrl.addEventListener("submit", (event => {
    event.preventDefault();
    formLoadUrl.classList.add("disabled");
    fetch(formLoadUrl.action, {method: "POST", body: new FormData(formLoadUrl)});
}));

document.querySelectorAll("button.button-action").forEach(button => {
    button.addEventListener("click", () => {
        wssClient.send(`WEB ${button.getAttribute("action")}`);
    });
});

function capitalizeFirstLetter(val) {
    return String(val).charAt(0).toUpperCase() + String(val).slice(1);
}

wssClient.connect();

});