class PlantCalendar extends HTMLElement {

    #grid;
    #plant;
    #startDate;
    #endDate;
    #baselineHours;
    #availabilities;
    #tooltipContainer;

    get period() {
        return this.#startDate === undefined ? undefined : [new Date(this.#startDate), new Date(this.#endDate)];
    }

    get availabilitiesInput() {
        return this.#availabilities ? [...this.#availabilities] : undefined;
    }

    constructor() {
        super();
        const shadow = this.attachShadow({mode: "open"});
        const style = document.createElement("style");
        style.textContent = ":root {--ltp-portfolio-base: blue; --ltp-portfolio-light: lightblue; --ltp-portfolio-lighter: lightblue; --ltp-portfolio-dark: darkblue;}\n" +
                            "@supports (background-color: color-mix(in srgb, red 50%, blue 50%)) {\n" +
                                    ":root { --ltp-portfolio-base: #4169E1;  --ltp-portfolio-light: color-mix(in srgb, var(--ltp-portfolio-base), white); " +
                                            "--ltp-portfolio-lighter: color-mix(in srgb, var(--ltp-portfolio-base), white 75%);" +
                                            "--ltp-portfolio-dark: color-mix(in srgb, var(--ltp-portfolio-base), black); }}\n" +
                            ".ltp-calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); column-gap: 0.1em; row-gap: 0.1em; justify-items: stretch; " +
                                        "align-items: stretch; justify-content: start; text-align: center; word-wrap: wrap; }\n" +
                           ".ltp-calendar-grid>div { min-width: 8em; max-width: 10em; min-height: 2em; }\n" +
                           ".ltp-day-header { background: var(--ltp-portfolio-base); color: white; padding: 0 1em; padding-top: 0.5em; }\n" +
                           ".ltp-day { display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; }\n" +
                           ".ltp-day>div:first-child { background: var(--ltp-portfolio-light);color: var(--ltp-portfolio-dark); " +
                                                "flex-grow: 1; padding: 0.25em 1em; min-height: 1.5em; vertical-align: middle; font-size: 1.3em;}\n" +
                           ".ltp-day>div:nth-child(2) { background: var(--ltp-portfolio-light); flex-grow: 1; padding: 0.5em 0;}\n" +
                           ".ltp-day>div>input { max-width: 10em; background: var(--ltp-portfolio-lighter);}";


        shadow.append(style);
        const grid = document.createElement("div");
        shadow.append(grid);
        grid.classList.add("ltp-calendar-grid");
        this.#grid = grid;
        const tooltipContainer = document.createElement("div");
        tooltipContainer.classList.add("tooltip-container");
        tooltipContainer.setAttribute("hidden", "true");
        shadow.append(tooltipContainer);
        this.#tooltipContainer = tooltipContainer;
    }

    /**
    *
    * @param {string} startTime
    * @param {(string|number)} horizonWeeks
    * @param {Object[]} availabilities
    * @param {date "2023-12-01" => planned working hours} shifts
    */
    setAvailabilities(startTime, horizonWeeks, availabilities, shifts, plant) {
        if (!(horizonWeeks > 0))
            throw new Error("horizonWeeks must be a positive number");
        JsUtils.clear(this.#grid);
        this.#availabilities = availabilities;
        this.#plant = parseInt(plant);
        const startDate = new Date(startTime);   // or use JsUtils to parse string?
        const endDate = new Date(startDate);
        if (horizonWeeks % 4 === 0)
            endDate.setMonth(endDate.getMonth() + (horizonWeeks/4));
        else
            endDate.setDate(endDate.getDate() + (horizonWeeks * 7));
        this.#startDate = startDate;
        this.#endDate = endDate;
        const startDayOfWeek = startDate.getDay(); // 0: Sunday, 6: Saturday
        const endDayOfWeek = endDate.getDay(); // 0: Sunday, 6: Saturday
        const daysToDisplayFrac = (endDate.getTime() - startDate.getTime())/(24*3_600_000);
        let weeksToDisplay = Math.ceil(daysToDisplayFrac / 7);
        if ((endDayOfWeek > 0 && endDayOfWeek < startDayOfWeek) || daysToDisplayFrac % 7 === 0)  // is this accurate?
            weeksToDisplay += 1;
        // console.log("  WEEKS to display", weeksToDisplay, "days:", daysToDisplayFrac, "end day of week", endDayOfWeek)
        const baseline = availabilities?.find(a => a.daily_baseline)?.daily_baseline;
        const baselineHours = JsUtils.parseDurationHours(baseline);
        this.#baselineHours = baselineHours; // ideally they should not differ between files
        const rows = weeksToDisplay;
        const columns = 7;
        const frag = document.createDocumentFragment();
        ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"].forEach(day =>
                    JsUtils.createElement("div", {parent: frag, text: day, classes: "ltp-day-header"}));
        let cnt = 0;
        const date = new Date(startDate);
        shifts = shifts || {};
        let shift_iter = Object.keys(shifts)[Symbol.iterator]();
        let current_shift_res = shift_iter.next().value;
        for (let week=0; week<weeksToDisplay; week++) {
            for (let dayOfWeek=0; dayOfWeek<7; dayOfWeek++) {
                if (week === 0 && dayOfWeek < startDayOfWeek) {
                    JsUtils.createElement("div", {parent: frag});  // need to fill the grid
                    continue;
                }
                if (week === weeksToDisplay-1 && endDayOfWeek > 0 && dayOfWeek >= endDayOfWeek)
                    break;
                const dateFormatted = date.getDate() + "." + (date.getMonth() + 1) + ".";
                const formatted2 = JsUtils.formatDate(date, {skipTime: true});
                const applicableAvailability = availabilities?.find(av => av.period[0] <= formatted2 && av.period[1] > formatted2);
                let currentValue = 0;
                if (applicableAvailability) {
                    const baselineHours1 = JsUtils.parseDurationHours(applicableAvailability?.daily_baseline, baselineHours);
                    currentValue = baselineHours1;
                    if (applicableAvailability?.deltas && formatted2 in applicableAvailability.deltas) {
                         const delta = applicableAvailability.deltas[formatted2]
                         const deltaHours = JsUtils.parseDurationHours(delta, 0);
                         currentValue += deltaHours;
                    }
                } else if (current_shift_res !== undefined) {
                    // try to find an applicable shift
                    while (current_shift_res < formatted2) {
                         current_shift_res = shift_iter.next().value;
                         if (current_shift_res === undefined)
                            break;
                    }
                    if (current_shift_res === formatted2) {
                        currentValue = shifts[current_shift_res];
                    }
                }
                const dayContainer = JsUtils.createElement("div", {parent: frag, classes: "ltp-day", attributes: {"data-day": formatted2}});
                JsUtils.createElement("div", {parent: dayContainer, text: dateFormatted});
                const durationEdit = JsUtils.createElement("div", {parent: dayContainer, title: "Set available hours"});
                // TODO handle DST changes
                const durationInput = JsUtils.createElement("input", {parent: durationEdit, attributes: {type: "number", min: 0, max: 24, value: currentValue}});
                cnt++;
                date.setDate(date.getDate()+1);  // advance 1 day
            }
        }
        //this.#grid.style["grid-template-columns"] = "repeat(" + columns + ", 1fr)";
        this.#grid.appendChild(frag);
        // FIXME
        window.calendar = this;
    }

    /**
    * Returns availabilities in the same format it accepts as input, i.e. as a PlantAvailability object
    * (or undefined)
    */
    getAvailabilities() {
        if (!this.#startDate)
            return undefined;
        const baselineHours = this.#baselineHours;
        const baseline = baselineHours == 24 ? "P1D" : "PT" + baselineHours + "H";
        let deltas = Object.fromEntries(Array.from(this.#grid.querySelectorAll("div[data-day]")).map(dayContainer => {
                const value = parseFloat(dayContainer.querySelector("input")?.value);
                const day = dayContainer.dataset.day;
                if (!Number.isFinite(value) || value < 0 || value > 24 || !day || value === baselineHours)
                    return undefined;
                const newValue0 = value - baselineHours;
                const isMinus = newValue0 < 0;
                let newValue = isMinus ? "-" : "";
                newValue += "PT" + Math.abs(newValue0) + "H";
                return [day, newValue];
            }).filter(arr => arr));
        if (Object.keys(deltas).length === 0)
            deltas = undefined;
        return {
            equipment: this.#plant,
            period: [JsUtils.formatDate(this.#startDate, {skipTime: true}), JsUtils.formatDate(this.#endDate, {skipTime: true})],
            daily_baseline: baseline,
            deltas: deltas
        };
    }


}