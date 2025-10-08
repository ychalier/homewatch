window.addEventListener("load", () => {
    document.querySelectorAll("button.button-action").forEach(button => {
        button.addEventListener("click", () => {
            fetch(API_URL + `?action=${button.getAttribute("action")}`);
        });
    });
});