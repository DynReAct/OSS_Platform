class BasicAlert extends HTMLElement {

    #alertContainer;
    #textContainer;
    #hidingTimer;

    constructor() {
        super();
        const shadow = this.attachShadow({mode: "open"});
        const style = document.createElement("style");
        style.textContent = ".alert-container { position: relative; padding: 1em; margin: 0.5em 0; width: 95%; color: white; background-color: grey; }\n" +
                            ".alert-container[hidden] { display: none; }\n" +
                            ".error { background-color: red; }\n" +
                            ".warn { background-color: orange; }\n" +
                            ".success { background-color: green; }\n" +
                            ".info { background-color: blue;}";
        shadow.append(style);
        const alertContainer = document.createElement("div");
        alertContainer.classList.add("alert-container");
        alertContainer.hidden = true;
        shadow.appendChild(alertContainer);
        const textContainer = document.createElement("div");
        alertContainer.appendChild(textContainer);

        this.#alertContainer = alertContainer;
        this.#textContainer = textContainer;
    }

    #closeInternal() {
        this.#textContainer.innerText = "";
        this.#alertContainer.hidden = true;
        this.#clearTimeout();
    }

    #clearTimeout() {
        if (this.#hidingTimer !== undefined) {
            window.clearTimeout(this.#hidingTimer);
            this.#hidingTimer = undefined;
        }
    }

    showMessage(msg, type, options) {
        if (!msg) {
            this.#closeInternal();
            return;
        }
        this.#clearTimeout();
        this.#textContainer.innerText = msg;
        type = type?.toLowerCase();
        const existingClasses = Array.from(this.#alertContainer.classList);
        const classesForRemoval = existingClasses.filter(cl => cl !== type && cl !== "alert-container");
        classesForRemoval.forEach(cl => this.#alertContainer.classList.remove(cl));
        if (type && existingClasses.indexOf(type) < 0)
            this.#alertContainer.classList.add(type);
        if (options?.timeout > 0)
            this.close(options?.timeout);
        this.#alertContainer.hidden = false;
    }

    close(timeoutMillis) {
        if (!(timeoutMillis > 0)) {
            this.#closeInternal();
            return;
        }
        this.#clearTimeout();
        this.#hidingTimer = window.setTimeout(() => this.#closeInternal(), timeoutMillis);
    }


}

globalThis.customElements.define("basic-alert", BasicAlert);
