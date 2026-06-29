(function() {
    const aggrid_functions = globalThis.dashAgGridFunctions || {};
    if (!globalThis.dashAgGridFunctions)
        globalThis.dashAgGridFunctions = aggrid_functions
    const aggrid_cmp_functions = (globalThis.dashAgGridComponentFunctions = globalThis.dashAgGridComponentFunctions || {});

    aggrid_functions.formatCell = function(obj, numDigits, expThreshold) {
        return JsUtils.format(obj, numDigits, expThreshold);
    };

    aggrid_functions.renderMaterialShare = function(params) {
        console.log("   RENDER MATERIAL SHARE 1", params);
    };

    const drawWedge = (startFraction, endFraction, color, options) => {
        const radius = options?.radius || 50;
        const attributes = options?.attributes || {};
        if (endFraction >= 1 && startFraction <= 0) {
            // https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/circle
            const circle = React.createElement("circle", {fill: color, cx: radius, cy: radius, r: radius, ...attributes});
            return circle;
        }
        const largeArcFlag = endFraction - startFraction > 0.5 ? 1 : 0;
        const angleStart = startFraction * 2 * Math.PI;
        const angleEnd = endFraction * 2 * Math.PI;
        const xStart = (1 + Math.sin(angleStart)) * radius;
        const yStart = (1 - Math.cos(angleStart)) * radius;
        const xEnd   = (1 + Math.sin(angleEnd)) * radius;
        const yEnd   = (1 - Math.cos(angleEnd)) * radius;
        // https://developer.mozilla.org/en-US/docs/Web/SVG/Tutorials/SVG_from_scratch/Paths#arcs
        // Arc format: A rx ry x-axis-rotation large-arc-flag sweep-flag x y
        const d = `M ${radius} ${radius} L ${xStart} ${yStart} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${xEnd} ${yEnd} Z`;
        const path = React.createElement("path", {fill: color, d: d, ...attributes});
        return path;
    };

    aggrid_cmp_functions.RenderMaterialClasses = function(params) {
        const value = params?.value;
        const material = value?.material;
        const labels = value?.labels;
        const colors = value?.colors;
        const sum = material ? Object.values(material).reduce((a,b) => a+b, 0) : undefined;
        if (!(sum > 0) || !colors)
            return;
        let currentFraction = 0;
        const radius = 45;
        const children = Object.entries(material).map(([material, value], idx) => {
            if (value <= 0)
                return undefined;
            const endFraction = currentFraction + value / sum;
            const color = colors[material] || "grey";   // colors[idx % 4];
            const label = labels && material in labels ? labels[material] : material;
            const arc = drawWedge(currentFraction, endFraction, color, {radius: radius,
                    attributes: {"data-material": material, "data-mat-label": label, "data-weight": value, "data-fraction": value/sum}});
            currentFraction = endFraction;
            return arc;
        }).filter(arc => arc);
        const size = 50;
        const svg = React.createElement("svg", { viewBox: "0 0 100 100", width: size, height: size, style: {"padding": "5px 0"} }, children);
        // TODO like this we cannot attach event listeners to svg (React problem) => need to go via the parent id
        return svg;
    };

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
            } /*,
            getTimezoneOffset: () => {
                return Intl.DateTimeFormat().resolvedOptions().timeZone; // new Date().getTimezoneOffset();
            } */
        }
    });

})();



