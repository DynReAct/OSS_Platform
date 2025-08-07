(function() {
    const aggrid_functions = globalThis.dashAgGridFunctions || {};
    if (!globalThis.dashAgGridFunctions)
        globalThis.dashAgGridFunctions = aggrid_functions

    aggrid_functions.formatCell = function(obj, numDigits) {
        return JsUtils.format(obj, numDigits);
    }

    globalThis.dynreact = Object.assign({}, globalThis.dynreact, {_site: undefined, _snapshot: undefined});
    const dynreact = globalThis.dynreact;
    dynreact.getSite = () => dynreact._site;
    dynreact.getSnapshot = () => dynreact._snapshot;

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        dynreact: {
            setSnapshot: (_, snap, site) => {
                dynreact._site = site;
                dynreact._snapshot = snap;
                if (snap) {
                    const coilsByOrder = Object.fromEntries(snap.orders.map(o => [o.id, []]));
                    snap.material.forEach(coil => {
                        if (!coil.order || !(coil.order in coilsByOrder))
                            return;
                        coilsByOrder[coil.order].push(coil);
                    });
                    snap.getCoilsByOrder = () => coilsByOrder;  // TODO sorted!
                }
                return "";
            },
            getTimezoneOffset: () => {
                return Intl.DateTimeFormat().resolvedOptions().timeZone; // new Date().getTimezoneOffset();
            }
        }
    });

})();



