(function() {
    const aggrid_functions = globalThis.dashAgGridFunctions || {};
    if (!globalThis.dashAgGridFunctions)
        globalThis.dashAgGridFunctions = aggrid_functions

    aggrid_functions.formatCell = function(obj, numDigits, expThreshold) {
        return JsUtils.format(obj, numDigits, expThreshold);
    }

    globalThis.dynreact = Object.assign({}, globalThis.dynreact, {_site: undefined, _snapshot: undefined, _ltp: undefined});
    // implements DashClientAccess from DynReActViz project
    const dynreact = globalThis.dynreact;
    dynreact.getSite = () => dynreact._site;
    dynreact.getSnapshot = () => dynreact._snapshot;
    dynreact.getLongTermPlanningSolution = () => dynreact._ltp;

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
            setLtp: (ltp) => {
                if (ltp) {
                    const sub_periods = ltp.targets.sub_periods.map(arr => arr.map(dt => new Date(dt)));
                    const sub_targets = Object.fromEntries(Object.entries(ltp.targets.production_sub_targets).map(([key, arr]) => {
                        return [key, arr.map(entry => { return {...entry, period: entry.period.map(p => new Date(p)) }; })];
                    }));
                    const targets = {
                        ...ltp.targets,
                        sub_periods: sub_periods,
                        period: ltp.targets.period.map(p => new Date(p)),
                        production_sub_target: sub_targets
                    };
                    const storage_levels = ltp.storage_levels.map(entry => { return {...entry, timestamp: new Date(entry.timestamp)}; });
                    ltp = {...ltp, targets: targets, storage_levels: storage_levels };
                }
                dynreact._ltp = ltp;
                return ltp?.id;
            },
            getTimezoneOffset: () => {
                return Intl.DateTimeFormat().resolvedOptions().timeZone; // new Date().getTimezoneOffset();
            }
        }
    });

})();



