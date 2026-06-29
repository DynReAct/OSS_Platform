class BasicAlert extends HTMLElement {

    #alertContainer;
    #textContainer;
    #linkContainer;
    #hidingTimer;
    #linkActive = false;

    constructor() {
        super();
        const shadow = this.attachShadow({mode: "open"});
        const style = document.createElement("style");
        style.textContent = ".alert-container { position: relative; padding: 1em; margin: 0.5em 0; width: 95%; color: white; background-color: grey; }\n" +
                            ".alert-container[hidden] { display: none; }\n" +
                            ".error { background-color: red; }\n" +
                            ".warn { background-color: orange; }\n" +
                            ".success { background-color: green; }\n" +
                            ".info { background-color: blue;}\n" +
                            ".plain-link {text-decoration:none;}";
        shadow.append(style);
        const alertContainer = document.createElement("div");
        alertContainer.classList.add("alert-container");
        alertContainer.hidden = true;
        shadow.appendChild(alertContainer);
        const textContainer = document.createElement("div");
        alertContainer.appendChild(textContainer);
        const linkContainer = document.createElement("a");
        linkContainer.setAttribute("target", "_blank");
        linkContainer.classList.add("plain-link");
        linkContainer.hidden = true;
        shadow.appendChild(linkContainer);

        this.#alertContainer = alertContainer;
        this.#textContainer = textContainer;
        this.#linkContainer = linkContainer;
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
        this.#textContainer.textContent = msg;
        type = type?.toLowerCase();
        const existingClasses = Array.from(this.#alertContainer.classList);
        const classesForRemoval = existingClasses.filter(cl => cl !== type && cl !== "alert-container");
        classesForRemoval.forEach(cl => this.#alertContainer.classList.remove(cl));
        if (type && existingClasses.indexOf(type) < 0)
            this.#alertContainer.classList.add(type);
        if (options?.timeout > 0)
            this.close(options?.timeout);
        this.#alertContainer.title = options?.title || "";
        if (options?.href)
            this.#linkContainer.href = options.href;
        const linkWasActive = this.#linkActive;
        const linkActive = !!options?.href;
        if (linkActive && !linkWasActive) {
            this.#linkContainer.appendChild(this.#alertContainer);
            this.#linkContainer.hidden = false;
        } else if (!linkActive && linkWasActive) {
            this.shadowRoot.appendChild(this.#alertContainer);
            this.#linkContainer.removeAttribute("href");
            this.#linkContainer.hidden = true;
        }
        this.#linkActive = linkActive;
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
