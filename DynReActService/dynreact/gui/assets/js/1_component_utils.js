(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        dialog: {
            showModal: function(clicks, dialogId) {
                if (!clicks)  // prevent initial callback
                    return "";
                const dialog = document.querySelector("dialog#" + dialogId);
                if (!dialog) {
                    console.log("Dialog not found", dialogId);
                    return "";
                }
                const close = (event) => {
                    if (event.target.id === dialogId) { // only when user clicks outside the dialog
                        dialog.close();
                        dialog.removeEventListener("click", close);
                    }
                };
                dialog.showModal();
                dialog.addEventListener("click", close);
                return "Click to close menu";
            },
            closeModal: function(clicks, dialogId, dummyReturnValue) {
                 document.querySelector("dialog#" + dialogId)?.close();
                 return dummyReturnValue;
            }
        },

        alert: {
            showAlert: function(msg, type, siblingId, dummyReturnValue) {
                const sibling = document.querySelector("#" + siblingId);
                if (!sibling) {
                    console.log("Alert sibling not found", siblingId);
                    return "";
                }
                let alert = sibling.nextElementSibling;
                if (alert?.tagName !== "BASIC-ALERT")  {
                    alert = document.createElement("basic-alert");
                    sibling.parentNode.insertBefore(alert, sibling.nextSibling);
                }
                alert.showMessage(msg, type);
                return dummyReturnValue || "";
            },
            closeAlert: function(clicks, siblingId, dummyReturnValue) {
                const sibling = document.querySelector("#" + siblingId);
                const alert = sibling?.nextElementSibling;
                alert?.close();
                return dummyReturnValue || "";
            }


        }
    });


})()