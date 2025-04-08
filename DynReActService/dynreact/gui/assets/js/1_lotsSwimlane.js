class LotsSwimlane extends HTMLElement {

  static get observedAttributes() {
    return ["row-size", "lot-height", "lot-color", "lot-sizing"];
  }

  #lanesContainer;
  #tooltipContainer;
  #svgParent;
  #rowSize = 50;
  #lotHeight = 20;
  #lotColor = "darkred";
  #lotSizing = "constant";  // constant, weight, orders, coils
  #site = undefined;
  #snapshot = undefined;
  #process = undefined;
  // Record<number, Array<Lot>>  // keys: plant id
  #lots = undefined;
  // Record<string, Record<string, Array<Coil>>>  // keys: lot id, order id
  #coils = undefined;
  // all: Record<string, number>
  #numOrdersByLot = undefined;
  #numCoilsByLot = undefined;
  #numOrdersByPlant = undefined;
  #numCoilsByPlant = undefined;
  #weightByLot = undefined;
  #weightByPlant = undefined;
  #plants = undefined;

  // information about created elements
  #lanes = undefined;

  set rowSize(size) {
    if (size > 0) {
      this.#rowSize = size;
      this._init();
    }
  }

  get rowSize() {
    return this.#rowSize;
  }

  set lotHeight(height) {
    if (height > 0) {
      this.#lotHeight = height;
      this.init();
    }
  }

  get lotHeight() {
    return this.#lotHeight;
  }

  set lotColor(color) {
    if (color) {
      this.#lotColor = color;
      this._init();
    }
  }

  get lotColor() {
    return this.#lotColor;
  }

  set lotSizing(value) {
    const previous = this.#lotSizing;
    const lower = value?.toLowerCase()
    switch (value) {
    case "constant":
    case "weight":
    case "orders":
    case "coils":
        this.#lotSizing = lower;
        if (lower !== previous)
            this._init();
    }
  }

  get lotSizing() {
    return this.#lotSizing;
  }

  get lots() {
    return this.#lots ? {...this.#lots} : undefined;
  }

  get site() {
    return this.#site ? {...this.#site} : undefined;
  }

  get snapshot() {
    return this.#snapshot ? {...this.#snapshot} : undefined;
  }

  get plants() {
    return this.#plants ? [...this.#plants] : undefined;
  }
  
  get coils() {
    return this.#coils ? {...this.#coils} : undefined;
  }
  
  get numOrdersByLot() {
    return this.#numOrdersByLot ? {...this.#numOrdersByLot} : undefined;
  }
  
  get numCoilsByLot() {
    return this.#numCoilsByLot ? {...this.#numCoilsByLot} : undefined;
  }
  
  get weightByLot() {
    return this.#weightByLot ? {...this.#weightByLot} : undefined;
  }
  
  get numOrdersByPlant() {
    return this.#numOrdersByPlant ? {...this.#numOrdersByPlant} : undefined;
  }
  
  get numCoilsByPlant() {
    return this.#numCoilsByPlant ? {...this.#numCoilsByPlant} : undefined;
  }
  
  get weightByPlant() {
    return this.#weightByPlant ? {...this.#weightByPlant} : undefined;
  }

  constructor() {
    super();
    const shadow = this.attachShadow({mode: "open"});
    const style = document.createElement("style");
    style.textContent = ".hidden { display: none; } " +
        ".plant-header { dominant-baseline: middle; color: darkgreen; } " +
        ".tooltip-container { position: absolute; pointer-events: none; background: white; padding: 0.5em; z-index: 5; border-radius: 2px; } " +
        ".tooltip-container[hidden] { display: none; } " +
        ".plant-header:hover { cursor: pointer;} " +
        ".lot-rect:hover { cursor: pointer;} ";
        /*
        ".lanes-container {display: grid; grid-template-columns: auto 1fr; } " +
        ".plant-title {padding: 1em; border: 2px solid darkgreen;} " +
        ".plant-lane {padding: 1em; border: 2px solid darkgreen;} "
        ;
        */
    shadow.append(style);
    const lanesContainer = document.createElement("div");
    shadow.append(lanesContainer);
    lanesContainer.classList.add("lanes-container");
    this.#lanesContainer = lanesContainer;
    const tooltipContainer = document.createElement("div");
    tooltipContainer.classList.add("tooltip-container");
    tooltipContainer.setAttribute("hidden", "true");
    shadow.append(tooltipContainer);
    this.#tooltipContainer = tooltipContainer;
    // FIXME
    window.lane = this;
  }

  #previousHoverTarget = undefined;

  _hover(evt) {
    const target = evt.target;
    const container = this.#tooltipContainer;
    if (target === this.#previousHoverTarget) {
        if (!container.getAttribute("hidden")) {
            container.style.setProperty("top", (evt.pageY - 5)  + "px");
            container.style.setProperty("left", (evt.pageX + 15) + "px");
        }
        return;  // potentially move tooltip?
    }
    this.#previousHoverTarget = target;
    const lot = target.dataset.lot;
    const plant = parseInt(target.dataset.plant);
    if (Number.isFinite(plant)) {
        const isLot = !!lot;
        if (isLot) {
            const numOrders = this.#numOrdersByLot[lot] || 0;
            const numCoils = this.#numCoilsByLot[lot] || 0;
            const weight = this.#weightByLot[lot] || 0;
            container.innerText = "Lot " + target.dataset.lot + " (orders: " + numOrders + ", coils: " + numCoils + ", weight: " + JsUtils.formatNumber(weight) + "t)";
        } else {
            const numOrders = this.#numOrdersByPlant[plant] || 0;
            const numCoils = this.#numCoilsByPlant[plant] || 0;
            const weight = this.#weightByPlant[plant] || 0;
            const plantName = this.#plants.find(p => p.id === plant)?.name_short || plant;
            container.innerText = "Plant " + plantName  + " (id: " + plant + ", orders: " + numOrders + ", coils: " + numCoils + ", weight: " + JsUtils.formatNumber(weight, 4) + "t)";;
        }
        container.style.setProperty("top", (evt.pageY - 5)  + "px");
        container.style.setProperty("left", (evt.pageX + 15) + "px");
        container.removeAttribute("hidden");
    } else { // if tooltip visible
        container.setAttribute("hidden", "true");
    }

  }

  setPlanning(site, snapshot, process, lots) {
    // console.log("New planning", lots);
    const lotsByPlant = {};
    lots?.forEach(lot => {
      if (!(lot.plant_id in lotsByPlant))
        lotsByPlant[lot.plant_id] = [];
      lotsByPlant[lot.plant_id].push(lot);
    });
    this.#lots = lots ? lotsByPlant : undefined;
    this.#site = site;
    this.#process = process;
    this.#snapshot = snapshot;
    const plantIds = [...Object.keys(lotsByPlant)].map(v => parseInt(v));
    this.#plants = site?.equipment?.filter(plant => plantIds.indexOf(plant.id) >= 0);
    if (snapshot && lots) {
        const coilsByOrder = snapshot.getCoilsByOrder();
        // Record<string, Record<string, Array<Coil>>>  // keys: lot id, order id
        const coils = Object.fromEntries(lots.map(lot => [lot.id, Object.fromEntries(lot.order_ids.map(order => [order, order in coilsByOrder ? coilsByOrder[order] : []]))]));
        this.#coils = coils;
        // Record<string, number>
        const numOrdersByLot = Object.fromEntries(lots.map(lot => [lot.id, lot.id in coils ? Object.keys(coils[lot.id]).length : 0]));
        // Record<string, number>
        const numCoilsByLot = Object.fromEntries(lots.map(lot => [lot.id, lot.id in coils ? Object.values(coils[lot.id]).flatMap(coils0 => coils0).length : 0]));
        const weightByLot = Object.fromEntries(lots.map(lot => [lot.id, lot.id in coils ?
                Object.values(coils[lot.id]).map(coils0 => coils0.map(c => c.weight).filter(weight => Number.isFinite(weight)).reduce((a,b) => a+b, 0)).reduce((a,b) => a+b, 0) : 0]));
        const numOrdersByPlant = Object.fromEntries(Object.entries(lotsByPlant).map(([plantId, lots]) =>
                            [plantId, lots.map(lot => numOrdersByLot[lot.id]).reduce((a,b) => a+b, 0)]));
        const numCoilsByPlant = Object.fromEntries(Object.entries(lotsByPlant).map(([plantId, lots]) =>
                            [plantId, lots.map(lot => numCoilsByLot[lot.id]).reduce((a,b) => a+b, 0)]));
        const weightByPlant = Object.fromEntries(Object.entries(lotsByPlant).map(([plantId, lots]) =>
                            [plantId, lots.map(lot => weightByLot[lot.id]).reduce((a,b) => a+b, 0)]));

        this.#numOrdersByLot = numOrdersByLot;
        this.#numCoilsByLot = numCoilsByLot;
        this.#weightByLot = weightByLot;
        this.#numOrdersByPlant = numOrdersByPlant;
        this.#numCoilsByPlant = numCoilsByPlant;
        this.#weightByPlant = weightByPlant;
    } else {
        this.#coils = undefined;
        this.#numOrdersByLot = undefined;
        this.#numCoilsByLot = undefined;
        this.#numOrdersByPlant = undefined;
        this.#numCoilsByPlant = undefined;
        this.#weightByLot = undefined;
        this.#weightByPlant = undefined;
    }
    this._init();
  }

  _init() {
    this.clear();
    if (!this.#plants)
      return;
    const rowSize = this.#rowSize;
    const lotHeight = this.#lotHeight;
    const lotColor = this.#lotColor;
    const width = Math.max(document.body.clientWidth - 100, 100);
    const svgParent = LotsSwimlane._create("svg", { attributes: {
        viewbox: "0 0 " + width + " " + (rowSize * this.#plants.length + 1),
        width: "90vw",
        height: (rowSize * this.#plants.length) + "px"
    }});
    this.#svgParent = svgParent;
    const sizing = this.#lotSizing;
    const sizeFactor = sizing === "constant" ? Math.max(...Array.from(Object.values(this.#lots)).map(lots => lots.length)) :
        sizing === "weight" ? Math.max(...Object.values(this.#weightByPlant)) :
        sizing === "orders" ? Math.max(...Object.values(this.#numOrdersByPlant)) :
        Math.max(...Object.values(this.#numCoilsByPlant));
    this.#lanes = this.#plants.map((plant, idx) => this._createPlantLane(idx, plant, svgParent, rowSize, width, lotHeight, lotColor, sizing, sizeFactor));
    this.#lanesContainer.appendChild(svgParent);
    const y = this.#plants.length * rowSize;
    LotsSwimlane._create("line", { parent: svgParent, attributes: { x1: 0, y1: y,  x2: width, y2: y, stroke: "darkgreen" }} );
    svgParent.addEventListener("mousemove", this._hover.bind(this));
  }

  // using event.target property instead
  /*
  _findField(x, y) {
    const lanes = this.#lanes;  // Array<{plant: number; title: DOMRect, lots: Array<{lot: string; field: DOMRect}>}>
    if (!lanes)
        return undefined;
    // check for vertical match first
    const match = lanes.find(lane => lane.title.y < y && (lane.title.y + lane.title.height) > y);
    if (!match)
        return undefined;
    const isTitle = match.title.x < x && (match.title.x + match.title.width) > x;
    const lot = isTitle ? undefined :
        match.lots.find(lot => lot.field.x < x && (lot.field.x + lot.field.width) > x && lot.field.y < y && (lot.field.y + lot.field.height) > y);
    return {
        plant: match.plant,
        isTitle: isTitle,
        lot: lot?.lot
    };
  }
  */

  /**
  TODO before calling this function, we need to determine the available space and the algorithm used to calculate the item length
  */
  _createPlantLane(idx, plant, svg, rowSize, rowWidth, lotHeight, lotColor, sizing, sizeFactor) {
    const title = LotsSwimlane._create("text", { attributes: { x: 15, y: (idx + 0.5) * rowSize }, dataset: {plant: plant.id}, classes: "plant-header", parent: svg } );
    title.textContent = LotsSwimlane.plantName(plant);
    const start0 = 100;
    const yFieldStart = idx * rowSize;
    const titleField = new DOMRect(0, yFieldStart, start0, rowSize);
    const lotFields = [];
    const lots = this.#lots[plant.id];
    let xStart = start0;
    for (const lot of lots) {
        //x="120" width="100" height="100" rx="15"
        const size = sizing === "constant" ? 1 :
            sizing === "weight" ? this.#weightByLot[lot.id] :
            sizing === "orders" ? this.#numOrdersByLot[lot.id] :
            this.#numCoilsByLot[lot.id];

        const width = /* 20*/ Math.max((rowWidth-start0-50) / sizeFactor * size - 10, 3) ;
        const lotYStart = (idx + 0.5) * rowSize - (lotHeight/2);
        const rect = LotsSwimlane._create("rect", { attributes: { x: xStart, width: width,
            y: (idx + 0.5) * rowSize - (lotHeight/2), height: lotHeight, rx: 3, fill: lotColor }, dataset: {lot: lot.id, plant: plant.id},
            classes: "lot-rect", parent: svg } );
        xStart += width + 10;
        const field = new DOMRect(xStart, lotYStart, width, lotHeight);
        lotFields.push({
            lot: lot.id,
            field: field
        });

    }

    const y = idx * rowSize;
    LotsSwimlane._create("line", { parent: svg, attributes: {
      x1: 0, y1: y,
      x2: rowWidth, y2: y,
      stroke: "darkgreen"
    }} );
    return {
        plant: plant.id,
        title: titleField,
        lots: lotFields
    };

  }

  clear() {
    while (this.#lanesContainer.firstChild)
        this.#lanesContainer.firstChild.remove();
    this.#svgParent = undefined;
    this.#lanes = undefined;
  }

  attributeChangedCallback(name, oldValue, newValue) {
    const attr = name.toLowerCase();
    switch (attr) {
      case "row-size":
        this.rowSize = parseFloat(newValue);
        break;
      case "lot-height":
        this.lotHeight = parseFloat(newValue);
        break;
      case "lot-color":
        this.lotColor = newValue;
        break;
      case "lot-sizing":
        this.lotSizing = newValue;
        break;
    }
  }

  static plantName(plant) {
    return plant.name_short || plant.name || plant.id;
  }

  static plantTooltip(plant) {
    if (plant.name)
      return plant.name + "(id: " + plant.id + ")";
    return "Id: " + plant.id;
  }

  static _create(svgTag, options) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", svgTag);
    if (options?.attributes)
      Object.entries(options.attributes).forEach(([key, value]) => el.setAttribute(key, value));
    if (options?.dataset)
        Object.entries(options.dataset).forEach(([key, value]) => el.dataset[key] = value);
    if (options?.classes) {
      const classes = !Array.isArray(options.classes) ? [options.classes] : options.classes;
      classes.forEach(cl => el.classList.add(cl));
    }
    if (options?.parent)
      options?.parent.appendChild(el);
    return el;
  }


}

globalThis.customElements.define("lots-swimlane", LotsSwimlane);

/* row data (TODO: need snapshot in addition, also site maybe)

{
    "id": lot.id,
    "plant": plants[lot.plant].name_short if lot.plant in plants and plants[lot.plant].name_short is not None else str(lot.plant),
    "num_orders": len(lot.orders),
    "num_coils": num_coils[lot.id],
    "order_ids": ", ".join(lot.orders),
    "first_due_date": first_due_dates[lot.id],
    "all_due_dates": all_due_dates[lot.id],
    "total_weight": total_weights[lot.id]
}

*/



