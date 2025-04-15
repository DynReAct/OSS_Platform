class MaterialsGrid2 extends HTMLElement {

    #grid;          //from GUI grid
    #materials;     //from site.json
    #lot_creation;
    #tooltipContainer;
    #processName;
    #totalValue = 0;
    #buttongroup;
    #buttongroup_primary;
    #state_arr = [];

    static get observedAttributes() {
        return ["columns-selectable"];
    }

    constructor() {
        super();
        const shadow = this.attachShadow({mode: "open"});
        const style = document.createElement("style");
        style.textContent = ":root {--ltp-portfolio-base: blue; --ltp-portfolio-light: lightblue; --ltp-portfolio-lighter: lightblue; --ltp-portfolio-dark: darkblue; --ltp-portfolio-readonly: lightsteelblue; }\n" +
                            "@supports (background-color: color-mix(in srgb, red 50%, blue 50%)) {\n" +
                                    ":root { --ltp-portfolio-base: #4169E1;  --ltp-portfolio-light: color-mix(in srgb, var(--ltp-portfolio-base), white); " +
                                            "--ltp-portfolio-lighter: color-mix(in srgb, var(--ltp-portfolio-base), white 75%);" +
                                            "--ltp-portfolio-dark: color-mix(in srgb, var(--ltp-portfolio-base), black); }}\n" +
                            ".ltp-materials-grid { display: grid; column-gap: 0.1em; row-gap: 0.1em; justify-items: stretch; " +
                                        "align-items: stretch; justify-content: start; text-align: center; word-wrap: wrap; }\n" +
                           ".ltp-materials-grid>div {  min-height: 2em; }\n" +
                           ".ltp-material-category { width: 10em; background-color: var(--ltp-portfolio-base); color: white; padding: 0 1em; padding-top: 0.5em; display: flex; column-gap: 1em; }\n" +
                           ".ltp-material-class { display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; width: 12em; }\n" +
                           ".ltp-material-class>div:first-child { background-color: var(--ltp-portfolio-light); color: var(--ltp-portfolio-dark); " +
                                                "flex-grow: 1; padding: 0.25em 1em; min-height: 2em; vertical-align: middle;}\n" +
                           ".ltp-material-class>div:nth-child(2) { background-color: var(--ltp-portfolio-light); flex-grow: 1; padding: 0.5em 0;}\n" +
                           ".ltp-material-class>div>input { max-width: 8em; background-color: var(--ltp-portfolio-lighter);}\n" +
                           ".ltp-material-class>div>input:read-only { background-color: var(--ltp-portfolio-readonly); }\n" +
                           ".active-toggle {}\n " +
                           ".active-toggle:hover { cursor: pointer; }\n " +
                           ".ltp-material-disabled { background-color: darkgrey; }\n " +
                           ".grid-sub-buttons-area>div{ margin-top: 2.0em; }\n " +
                           ".grid-sub-buttons-row>div{  min-height: 1.5em; margin-top: 0.3em; }\n " +
                           ".grid-sub-button>div{ padding: 0.5em; }\n " +
                           ".ltp-material-master { font-weight: bold } \n" +
                           ".class-marked {} \n" +
                           ".title-flex {display: flex;}";


        shadow.append(style);
        const grid = document.createElement("div");
        shadow.append(grid);
        grid.classList.add("ltp-materials-grid");
        this.#grid = grid;
        const tooltipContainer = document.createElement("div");
        tooltipContainer.classList.add("tooltip-container");
        tooltipContainer.setAttribute("hidden", "true");
        shadow.append(tooltipContainer);
        this.#tooltipContainer = tooltipContainer;

        const buttongroup = document.createElement("div");
        this.#buttongroup = buttongroup;
        let is_primary = false;
    }

    goFirst(dd, daFirst) {
        var ordered = [];
        dd.forEach((elem) => {
            if (elem['id'] === daFirst)
                ordered.unshift(elem);
            else
                ordered.push(elem);
        })
        return ordered;
    }

    initState( masterId, masterVal){
        // init state_arr for one masterId with default-share
        const primary_category_id = this.getCategoryIdFromClassId(masterId);
        let sub_dict = Object.create(null);
        let col_array = [];
        let row_array = [];
        sub_dict.masterId = masterId;
        sub_dict.masterVal = masterVal;
        col_array =[];
        row_array = [];
        for (const category of this.#materials) {
            const cat_id = category.id;
            if (cat_id != primary_category_id){
                col_array.push({ category: cat_id, is_active: "true"});  // all cols set active
                for (const cell of category.classes) {
                    const cellVal = masterVal * cell.default_share;
                    row_array.push({'materialId': cell.id, 'value': cellVal});
                }
            }
        }
        sub_dict.colState = col_array;
        sub_dict.details = row_array;
        this.#state_arr.push(sub_dict);
    }

    saveState(){
        // save state for one masterclass into #state_arr from grid
        // save master_id, master_val
        // save for all cols active or not
        // save for all (active and inactive ) cells cellvalues
        const sub_dict = Object.create(null);
        const container1 = this.#grid.querySelector(".ltp-material-master");
        const masterId = container1.dataset.material;
        const inp1 = container1.querySelector("input[type=number]");
        const master_value = parseFloat(inp1.value);
        sub_dict.masterId = masterId;
        sub_dict.masterVal = master_value;
        // which cols are active ?
        const col_array = []; // empty array
        const row_array = [];
        const primary_category_id = this.getCategoryIdFromClassId(masterId);
        for (const materialHeader of this.#grid.querySelectorAll(".ltp-material-category") ){
            const cat_id = materialHeader.dataset.category;
            if (cat_id != primary_category_id){
                const my_toggle = materialHeader.querySelector(".active-toggle");  //search for class with .
                const my_active = my_toggle.dataset.active;
                const mycolState = Object.create(null);
                mycolState.category = cat_id;
                mycolState.is_active = my_active;
                //col_array.push({ category: cat_id, is_active: my_active});
                col_array.push(mycolState);
                sub_dict.colState = col_array;
                // get all values
                for ( const row of this.#grid.querySelectorAll("div[data-category=\"" + cat_id + "\"][data-material]")){
                    const mat_id = row.dataset.material;
                    const inp1 = row.querySelector("input[type=number]");
                    const sub_value = parseFloat(inp1.value)
                    row_array.push({'materialId': mat_id, 'value': sub_value});
                }
                sub_dict.details = row_array;
            }
        }
        // add or replace in state_arr
        if (this.#state_arr.find(o => o.masterId === masterId)){
            let obj = this.#state_arr.find((o,i) => {
                if (o.masterId === masterId) {
                    this.#state_arr[i] = sub_dict;
                }
            });
        }
        else {
            this.#state_arr.push(sub_dict);
        }
    }

    clearState( masterId){
        // remove entry masterId from state
        // find index of element in array, remove that index with splice
        const idx = this.#state_arr.findIndex(o => o.masterId === masterId);
        if (idx > -1) {                     // only splice array when item is found
            this.#state_arr.splice(idx, 1); // 2nd parameter means remove one item only
        }
    }

    clearAllStates(){
        // remove all entries from state
        this.#state_arr =[];
    }

    updateStateFromTotal(primary_category_id, factor){
        // called in case totalValue_changed, update all marked classes in #state_arr
        // update masterVal with factor, update all details with factor, colState no changes
        const arr_length = this.#state_arr.length;
        for (let ii = 0; ii < this.#state_arr.length; ii++) {
            const oneEntry = this.#state_arr[ii];
            oneEntry.masterVal = oneEntry.masterVal * factor;
            const details_length = oneEntry.details.length;
            for (let i2 = 0; i2 < oneEntry.details.length; i2++) {
                oneEntry.details[i2].value = oneEntry.details[i2].value *factor;
            }
            this.#state_arr[ii] = oneEntry;
        }
    }

    updateStateFromMaster(){
        // called in case distribution master classes change, update all marked classes in #state_arr
        // each class update in relation to grid master entry, factor=stateVal /gridVal
        // update masterVal, update all details, colState no changes
        for (let ii = 0; ii < this.#state_arr.length; ii++) {
            const oneEntry = this.#state_arr[ii];
            const masterId = oneEntry.masterId;
            const gridVal_masterId = this.getOneField(masterId);
            if (oneEntry.masterVal > 0) {
                const factor = gridVal_masterId / oneEntry.masterVal;
                oneEntry.masterVal = oneEntry.masterVal * factor;
                for (let i2 = 0; i2 < oneEntry.details.length; i2++) {
                    oneEntry.details[i2].value = oneEntry.details[i2].value *factor;
                }
                this.#state_arr[ii] = oneEntry;
            }
            else{ // keep state consistent, previous masterVal= 0 => init from default-share
                this.clearState( masterId);
                this.initState( masterId, gridVal_masterId);
            }
        }
    }

    updateStateFromGrid(masterIdGrid){
        // called by eventListener gridcell if primary and if sub_mode
        // called in case subfield change, update current class in #state_arr
        //  update details one col, colState etc no changes
        const new_entry = Object.create(null);
        const row_array = [];
        const primary_category_id = this.getCategoryIdFromClassId(masterIdGrid);
        for (let ii = 0; ii < this.#state_arr.length; ii++) {
            const oneEntry = this.#state_arr[ii];
            const masterIdState = oneEntry.masterId;
            if (masterIdState == masterIdGrid){
                new_entry.masterId = oneEntry.masterId;
                new_entry.masterVal= oneEntry.masterVal;
                new_entry.colState = oneEntry.colState;
                // get all values from grid
                for (const materialHeader of this.#grid.querySelectorAll(".ltp-material-category") ){
                    const cat_id = materialHeader.dataset.category;
                    if (cat_id != primary_category_id){
                        for ( const row of this.#grid.querySelectorAll("div[data-category=\"" + cat_id + "\"][data-material]")){
                            const mat_id = row.dataset.material;
                            const inp1 = row.querySelector("input[type=number]");
                            const sub_value = parseFloat(inp1.value)
                            row_array.push({'materialId': mat_id, 'value': sub_value});
                        }
                    }
                }
                new_entry.details = row_array;
                this.#state_arr[ii] = new_entry;
            }
        }
    }

    updateStateColState(masterId){
        // called by eventListener active-toggle if primary
        // called in case active-toggle change, update current class in #state_arr
        // update colState, details etc no changes
        const new_entry = Object.create(null);
        const col_array = []; // empty array
        const primary_category_id = this.getCategoryIdFromClassId(masterId);

        for (let ii = 0; ii < this.#state_arr.length; ii++) {
            const oneEntry = this.#state_arr[ii];
            const masterIdState = oneEntry.masterId;
            if (masterIdState == masterId){
                new_entry.masterId = oneEntry.masterId;
                new_entry.masterVal= oneEntry.masterVal;
                new_entry.details = oneEntry.details;
                for (const materialHeader of this.#grid.querySelectorAll(".ltp-material-category") ){
                    const cat_id = materialHeader.dataset.category;
                    if (cat_id != primary_category_id){
                        const my_toggle = materialHeader.querySelector(".active-toggle");  //search for class with .
                        const my_active = my_toggle.dataset.active;
                        const mycolState = Object.create(null);
                        mycolState.category = cat_id;
                        mycolState.is_active = my_active;
                        col_array.push(mycolState);
                    }
                }
                new_entry.colState = col_array;
                this.#state_arr[ii] = new_entry;
            }
        }
    }

    spreadStateVals(masterId){
        //spread from state values
        //case masterVal changed, spread from state with factor
        //also called case totalValue_changed and grid_mode main
        const masterValState = this.getMasterValFromState(masterId);
        const masterValGrid = this.getMasterValFromGrid();
        const primary_category_id = this.getCategoryIdFromClassId(masterId);
        if (masterValState == 0 && masterValGrid > 0){
            this.spreadDefaultVals(masterId);
            return;
        }
        const factor = (masterValState === masterValGrid) ? 1.0 : masterValGrid / masterValState;
        if (this.#state_arr.find(o => o.masterId === masterId)){
            for (const materialHeader of this.#grid.querySelectorAll(".ltp-material-category") ){
                const cat_id = materialHeader.dataset.category;
                if (cat_id != primary_category_id){
                    // get all values from state
                    for ( const elem of this.#grid.querySelectorAll("div[data-category=\"" + cat_id + "\"][data-material]")){
                        // set values cells from state
                        const mat_id = elem.dataset.material;
                        const val_from_state = this.getValueFromState(masterId, mat_id);
                        const inp = elem.querySelector("input[type=number]");
                        inp.value = val_from_state * factor;
                        inp.max = masterValState;
                    }
                }
            }
        }
        else{
            console.log ('error ', mat_id, ' not found in state');
        }
    }

    spreadStateVis(masterId){
        //spread from state visibility
        //called by GoSub, not called if totalValue_changed
        const primary_category_id = this.getCategoryIdFromClassId(masterId);
        if (this.#state_arr.find(o => o.masterId === masterId)){
            for (const materialHeader of this.#grid.querySelectorAll(".ltp-material-category") ){
                const cat_id = materialHeader.dataset.category;
                if (cat_id != primary_category_id){
                    const is_cat_active = this.getActiveFromState(masterId, cat_id);
                    // get all values from state
                    for ( const elem of this.#grid.querySelectorAll("div[data-category=\"" + cat_id + "\"][data-material]")){
                        // set cols active or not from state
                        if (is_cat_active){
                            if (elem.classList.contains ("ltp-material-disabled")){
                                elem.classList.remove("ltp-material-disabled");
                            }
                            elem.querySelector("input").disabled = false;
                        }
                        else{
                           if (!elem.classList.contains ("ltp-material-disabled")){
                                elem.classList.add("ltp-material-disabled");
                            }
                            elem.querySelector("input").disabled = true;
                        }
                    }
                    // set headers active or not from state
                    const materialHeader2 = this.#grid.querySelector("div[data-category=\"" + cat_id + "\"].ltp-material-category");
                    if (materialHeader2){
                        const my_toggle = materialHeader2.querySelector(".active-toggle");  //search for class with .
                        if (is_cat_active){
                            my_toggle.textContent = "✔";                             // .textContent is DOM element
                            my_toggle.title= "Disable structure category";           // .title is DOM element
                            my_toggle.dataset.active = "true";                       // howto set attribute, user defined .dataset, results in "data-active", here string
                            if (materialHeader2.classList.contains ("ltp-material-disabled"))
                                materialHeader2.classList.remove("ltp-material-disabled");
                        }
                        else{
                            my_toggle.textContent = "X";                            // .textContent is DOM element
                            my_toggle.title= "Activate structure category";         // .title is DOM element
                            if (materialHeader2.dataset.active)
                                delete my_toggle.dataset.active;                    // howto remove attribute, user defined .dataset
                            if (!materialHeader2.classList.contains ("ltp-material-disabled"))
                                materialHeader2.classList.add("ltp-material-disabled");
                        }
                    }
                }
            }
        }
        else{
            console.log ('error ', mat_id, ' not found in state');
        }
    }

    spreadDefaultVals(masterId){
        // spread grid elements from share-default, here no settings active or not
        const masterVal = this.getMasterValFromGrid();
        const primary_category_id = this.getCategoryIdFromClassId(masterId);
        for (const materialHeader of this.#grid.querySelectorAll(".ltp-material-category") ){
            const cat_id = materialHeader.dataset.category;
            if (cat_id != primary_category_id){
                // set all values from masterVal and defaultshare
                for ( const elem of this.#grid.querySelectorAll("div[data-category=\"" + cat_id + "\"][data-material]")){
                    const val_default = masterVal * elem.dataset.defaultshare;
                    const inp = elem.querySelector("input[type=number]");
                    inp.value = val_default;
                    inp.max = masterVal;
                }
            }
        }
    }

    spreadDefaultVis(masterId){
        // spread default visibility grid_mode sub
        const primary_category_id = this.getCategoryIdFromClassId(masterId);
        for (const materialHeader of this.#grid.querySelectorAll(".ltp-material-category") ){
            const cat_id = materialHeader.dataset.category;
            if (cat_id != primary_category_id){
                // set all values from masterVal and defaultshare
                for ( const elem of this.#grid.querySelectorAll("div[data-category=\"" + cat_id + "\"][data-material]")){
                    // set col elements all active
                    if (elem.classList.contains ("ltp-material-disabled")){
                        elem.classList.remove("ltp-material-disabled");
                    }
                    elem.querySelector("input").disabled = false;
                }
                // set all headers active
                const materialHeader2 = this.#grid.querySelector("div[data-category=\"" + cat_id + "\"].ltp-material-category");
                if (materialHeader2){
                    const my_toggle = materialHeader2.querySelector(".active-toggle");  //search for class with .
                    my_toggle.textContent = "✔";                             // .textContent is DOM element
                    my_toggle.title= "Disable structure category";           // .title is DOM element
                    my_toggle.dataset.active = "true";                       // howto set attribute, user defined .dataset, results in "data-active", here string
                    if (materialHeader2.classList.contains ("ltp-material-disabled"))
                        materialHeader2.classList.remove("ltp-material-disabled");
                }
            }
        }
    }

    spreadDefaultVisAll(){
        //for non-primary
        const allHeaders = this.#grid.querySelectorAll(".ltp-material-category");
        for (const materialHeader of allHeaders){
            const cat_id = materialHeader.dataset.category;
            // set col elements all active
            for ( const elem of this.#grid.querySelectorAll("div[data-category=\"" + cat_id + "\"][data-material]")){
                if (elem.classList.contains ("ltp-material-disabled")){
                    elem.classList.remove("ltp-material-disabled");
                }
                elem.querySelector("input").disabled = false;
            }
            // set all headers active
            const materialHeader2 = this.#grid.querySelector("div[data-category=\"" + cat_id + "\"].ltp-material-category");
            if (materialHeader2){
                const my_toggle = materialHeader2.querySelector(".active-toggle");  //search for class with .
                my_toggle.textContent = "✔";                             // .textContent is DOM element
                my_toggle.title= "Disable structure category";           // .title is DOM element
                my_toggle.dataset.active = "true";                       // howto set attribute, user defined .dataset, results in "data-active", here string
                if (materialHeader2.classList.contains ("ltp-material-disabled"))
                    materialHeader2.classList.remove("ltp-material-disabled");
            }
        }
    }

    setModeMain(primary_category_id){
        // 3 enable primary col grid elements
        // 4 disable all other cols grid elements
        for (const category of this.#materials) {
            for (const cell of category.classes) {
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cell.id + "\"]");
                if (materialParent){
                    if (category.id != primary_category_id){
                        if (!materialParent.classList.contains ("ltp-material-disabled")){
                            materialParent.classList.add("ltp-material-disabled");
                            materialParent.querySelector("input").disabled = true;
                        }
                    }
                    else{
                        if (materialParent.classList.contains ("ltp-material-disabled")){
                            materialParent.classList.remove("ltp-material-disabled");
                            materialParent.querySelector("input").disabled = false;
                        }
                    }
                }
            }
        }
        // 3a ensable primary col header toggle
        // 4a disable all other cols header toggle
        for (const category of this.#materials) {
            // look for "ltp-material-category"
            const materialHeader = this.#grid.querySelector("div[data-category=\"" + category.id + "\"].ltp-material-category");
            if (materialHeader){
                const my_toggle = materialHeader.querySelector(".active-toggle");  //search for class with .
                if (category.id != primary_category_id){
                    delete my_toggle.dataset.active;                         // howto remove attribute, user defined .dataset
                    my_toggle.textContent = "X";                             // .textContent is DOM element
                    my_toggle.style.visibility = "hidden";                   // toggle should only visible in submode
                    my_toggle.title= "Activate structure category";          // .title is DOM element
                    materialHeader.classList.add("ltp-material-disabled");
                }
                else{
                    my_toggle.dataset["active"] = "true";                    // howto set attribute, user defined .dataset, results in "data-active", here string
                    my_toggle.textContent = "✔";                             // .textContent is DOM element
                    my_toggle.title= "Disable structure category";           // .title is DOM element
                    materialHeader.classList.remove("ltp-material-disabled");
                }
            }
        }
    }

    setModeSub(primary_category_id){
        // 2a disable primary col grid elements
        for (const category of this.#materials) {
            for (const cell of category.classes) {
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cell.id + "\"]");
                if (materialParent){
                    if (category.id == primary_category_id){
                       if (!materialParent.classList.contains ("ltp-material-disabled")){
                            materialParent.classList.add("ltp-material-disabled");
                            materialParent.querySelector("input").disabled = true;
                        }
                    }
                }
            }
        }
        // 2b disable primary col header toggle
         for (const category of this.#materials) {
            // look for "ltp-material-category"
            const materialHeader = this.#grid.querySelector("div[data-category=\"" + category.id + "\"].ltp-material-category");
            if (materialHeader){
                const my_toggle = materialHeader.querySelector(".active-toggle");  //search for class with .
                if (category.id == primary_category_id){
                    delete my_toggle.dataset.active;                         // howto remove attribute, user defined .dataset
                    my_toggle.textContent = "X";                             // .textContent is DOM element
                    my_toggle.style.visibility = "hidden";
                    my_toggle.title= "Activate structure category";           // .title is DOM element
                    materialHeader.classList.add("ltp-material-disabled");
                }
                else{
                    my_toggle.style.visibility = "visible";
                    // all other props via spread from state
                }
            }
        }
    }

    setButtonsModeMain(){
        // switch buttongroup_primary
        const butt_rows_main = this.#buttongroup_primary.querySelectorAll(".grid-sub-buttons-main");
        for (const item of butt_rows_main){
            item.style.visibility = "visible";
        }
        const butt_rows_sub = this.#buttongroup_primary.querySelectorAll(".grid-sub-buttons-sub");
        for (const item of butt_rows_sub){
            item.style.visibility = "hidden";
        }
    }

    setButtonsModeSub(){
        // switch buttongroup_primary
        const butt_rows_main = this.#buttongroup_primary.querySelectorAll(".grid-sub-buttons-main");
        for (const item of butt_rows_main){
            item.style.visibility = "hidden";
        }
        const butt_rows_sub = this.#buttongroup_primary.querySelectorAll(".grid-sub-buttons-sub");
        for (const item of butt_rows_sub){
            item.style.visibility = "visible";
        }
    }

    getMasterId(primary_category_id, masterRow){
        let masterId;
        for (const category of this.#materials) {
            if (category.id == primary_category_id){
                for (const cell of category.classes) {
                    const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cell.id + "\"]");
                    if (materialParent.style["grid-row-start"] == masterRow){
                        masterId = cell.id;
                    }
                }
            }
        }
        return masterId;
    }

    getMasterValFromGrid(){
        const container1 = this.#grid.querySelector(".ltp-material-master");
        const inp1 = container1.querySelector("input[type=number]");
        const masterVal = parseFloat(inp1.value);
        return masterVal;
    }

    getMasterIdFromGrid(){
        const container1 = this.#grid.querySelector(".ltp-material-master");
        const masterId = container1.dataset.material;
        return masterId;
    }

    setMaterialMarked(materialId){
        // mark one master grid element
        const materialParent = this.#grid.querySelector("div[data-material=\"" + materialId + "\"]");
        const my_marker = materialParent.querySelector(".class-marked");
        my_marker.style.visibility = "visible";
        my_marker.dataset.marked = "true";
    }

    setMaterialUnmarked(materialId){
        // unmark one master grid element
        const materialParent = this.#grid.querySelector("div[data-material=\"" + materialId + "\"]");
        const my_marker = materialParent.querySelector(".class-marked");
        my_marker.style.visibility = "hidden";
        my_marker.dataset.marked = "false";
    }

    setMaterials(process, materials, lot_creation) {
        JsUtils.clear(this.#grid);
        this.#materials = materials;
        this.#processName = process;
        this.#lot_creation = lot_creation;
        this.#totalValue = 0;
        const columns = materials.length;
        const columnsSelectable = this.columnsSelectable;
        //const rows = Math.max(...materials.map(cat => cat.classes.length));
        const frag = document.createDocumentFragment();
        // -- ordered prim as first column
        let primary_category_id;
        let masterId;
        let grid_mode = "main";
        let row_max = 0;
        let sum2spread = 0;
        if (lot_creation){
            if (Object.keys(lot_creation.processes).includes(process) && lot_creation.processes[process].structure?.primary_category){
                this.is_primary = true;
                primary_category_id = lot_creation.processes[process].structure.primary_category;
                let ordered_materials = this.goFirst(materials, primary_category_id);
                materials = ordered_materials;
            }
            else{
                this.is_primary = false;
            }
        }
        let column = 0;
        for (const material_category of materials) {
            if (material_category.process_steps && material_category.process_steps.indexOf(process) < 0)
                continue;
            column++;
            const categoryHeader = JsUtils.createElement("div", {
                parent: frag,
                classes: "ltp-material-category",
                style: {"grid-column-start": column, "grid-row-start": 1},
                attributes: {"data-category": material_category.id}
            });
            const headerText = JsUtils.createElement("div", {text: material_category.name || material_category.id, parent: categoryHeader});
            let row = 1;
            const classes = [];
            for (const material_class of material_category.classes) {
                row = row + 1;
                const data_dict = {"data-category": material_category.id, "data-material": material_class.id};
                if (material_class.is_default)
                    data_dict["data-default"] = true;
                if (material_class.default_share !== undefined)
                    data_dict["data-defaultshare"] = material_class.default_share;
                const material_parent = JsUtils.createElement("div", {
                    parent: frag,
                    style: {"grid-column-start": column, "grid-row-start": row},
                    classes: "ltp-material-class",
                    attributes: data_dict
                });
                //JsUtils.createElement("div", {text: material_class.name||material_class.id, parent: material_parent});
                const grid_element_title = JsUtils.createElement("div", { parent: material_parent, classes: "title-flex"});
                JsUtils.createElement("div", {text: material_class.name||material_class.id, parent: grid_element_title});
                if (column == 1){
                    const marker = JsUtils.createElement("div", {parent: grid_element_title, text: "✱", attributes: {"data-marked": "false"},
                                            classes: "class-marked", title: "State is saved for this masterclass" , style: {"visibility": "hidden"} });
                }
                // TODO handle stepMismatch (should be ignored) https://developer.mozilla.org/en-US/docs/Web/API/ValidityState/stepMismatch
                const inp = JsUtils.createElement("input", {
                    parent: JsUtils.createElement("div", {parent: material_parent}),
                    attributes: {min: "0", step: "1000", type: "number"}
                });
                inp.value = 0;
                if (material_class.is_default){
                    inp.readOnly = true;
                } else {
                     inp.addEventListener("change", (event) => {
                        if (!this.is_primary){
                            sum2spread = this.#totalValue;
                            this.changeFilling(material_category, material_class.id, sum2spread);
                        }
                        else{//primary
                            masterId = this.getMasterIdFromGrid();
                            if (grid_mode=='main')
                                sum2spread = this.#totalValue;
                            else
                                sum2spread = this.getOneField(masterId);
                            this.changeFilling(material_category, material_class.id, sum2spread);

                            // keep state consistent independent from further user action
                            this.updateStateFromMaster();
                            // case masterfield spread all fields
                            if (material_category.id == primary_category_id){
                                if (this.#state_arr.find(o => o.masterId === masterId))
                                    this.spreadStateVals(masterId);
                                else
                                    this.spreadDefaultVals(masterId);
                            }
                            else{
                                this.updateStateFromGrid(masterId);
                            }
                        }
                    });
                }
                classes.push(material_parent);
                row_max = row;
            }
            if (columnsSelectable) {
                const toggle = JsUtils.createElement("div", {parent: categoryHeader, attributes: {"data-active": "true"}, text: "✔",
                                            classes: "active-toggle", title: "Disable structure category"});
                if (this.is_primary){
                    //case primary, first col open, all others disabled
                    if (column > 1){
                        delete toggle.dataset["active"];
                        toggle.textContent = "X";
                        toggle.style.visibility = "hidden";
                        toggle.title = "Activate structure category";
                        classes.forEach(cl => {
                            cl.classList.add("ltp-material-disabled");
                            cl.querySelector("input").disabled = true;
                        });
                        categoryHeader.classList.add("ltp-material-disabled");
                    }
                }

                toggle.addEventListener("click", () => {
                    const wasActive = toggle.dataset["active"] === "true";
                    if (wasActive) {
                        delete toggle.dataset["active"];
                        toggle.textContent = "X";
                        toggle.title = "Activate structure category";
                        classes.forEach(cl => {
                            cl.classList.add("ltp-material-disabled");
                            cl.querySelector("input").disabled = true;
                        });
                        categoryHeader.classList.add("ltp-material-disabled");
                    } else {
                        toggle.dataset["active"] = "true";
                        toggle.textContent = "✔";
                        toggle.title = "Disable structure category";
                        classes.forEach(cl => {
                            cl.classList.remove("ltp-material-disabled");
                            cl.querySelector("input").disabled = false;
                        });
                        categoryHeader.classList.remove("ltp-material-disabled");
                    }
                    // update state
                    if (this.is_primary){
                        const masterId = this.getMasterIdFromGrid();
                        this.updateStateColState(masterId);
                    }
                });
            }

        }
        this.#grid.style["grid-template-columns"] = "repeat(" + columns + ", 1fr)";
        this.#grid.appendChild(frag);

        if (this.is_primary){
            let masterRow;
            const masterRowMin = 2;     //fix
            const materialPrim = this.#grid.querySelectorAll("div[data-category=\"" + primary_category_id + "\"].ltp-material-class");
            const masterRowMax = masterRowMin + materialPrim.length - 1;
            const frag2 = document.createDocumentFragment();
            // define all buttons
            const buttongroup_primary = JsUtils.createElement("div", {
                parent: frag2,
                style: {"grid-column-start": 1, "grid-row-start": row_max+1} ,
                classes: "grid-sub-buttons-area",
                });
            this.#buttongroup_primary = buttongroup_primary;
            const button_parent_row = JsUtils.createElement("div", {
                parent: buttongroup_primary,
                classes: "grid-sub-buttons-row",
                });
            const buttons_row1 = JsUtils.createElement("div", { parent: button_parent_row});
            const buttGosub = JsUtils.createElement("button", { classes: ["grid-sub-button", "grid-sub-buttons-main"], parent: buttons_row1, text: "Sub Categories", title: "Go to sub categories"  });
            const buttPrev = JsUtils.createElement("button", { classes: ["grid-sub-button", "grid-sub-buttons-main"], text: "Prev", parent: buttons_row1, title: "Go to prev main class" });
            const buttNext = JsUtils.createElement("button", { classes: ["grid-sub-button", "grid-sub-buttons-main"], text: "Next", parent: buttons_row1, title: "Go to next main class" });
            const buttons_row2 = JsUtils.createElement("div", { parent: button_parent_row});
            const buttBack2Main = JsUtils.createElement("button", {classes: ["grid-sub-button", "grid-sub-buttons-sub"], text: "Back to Main", parent: buttons_row2, title: "Go back to main class and save state" });
            const buttons_row3 = JsUtils.createElement("div", { parent: button_parent_row});
            const buttCancel = JsUtils.createElement("button", {classes: ["grid-sub-button", "grid-sub-buttons-sub"], text: "Cancel", parent: buttons_row3, title: "Go back to main class without saving changes of state" });
            const buttClear = JsUtils.createElement("button", {classes: ["grid-sub-button", "grid-sub-buttons-sub"], text: "Clear", parent: buttons_row3, title: "Go back to main class and clear state for this class" });
            const buttReset = JsUtils.createElement("button", {classes: ["grid-sub-button", "grid-sub-buttons-sub"], text: "Reset", parent: buttons_row3, title: "Stay in submode, fill elements default" });

            // start default settings
            grid_mode = "main";     // ?? should use mode
            buttGosub.style.visibility = "visible";
            buttPrev.style.visibility = "visible";
            buttNext.style.visibility = "visible";
            buttBack2Main.style.visibility = "hidden";
            buttCancel.style.visibility = "hidden";
            buttClear.style.visibility = "hidden";
            buttReset.style.visibility = "hidden";

            // 0a get cellId mastercell
            masterRow = masterRowMin;  //start
            masterId = this.getMasterId(primary_category_id, masterRow);

            // 0b highlight element primaryCol masterRow start 1,2 == mastercell
            // masterId = "heat_continuous";
            const materialParent = this.#grid.querySelector("div[data-material=\"" + masterId + "\"]");
            materialParent.classList.add("ltp-material-master");

            // 0c toggle of mastercat not visible
            const materialHeader = this.#grid.querySelector("div[data-category=\"" + primary_category_id + "\"].ltp-material-category");
            const my_toggle = materialHeader.querySelector(".active-toggle");
            my_toggle.style.visibility = "hidden";

            buttGosub.addEventListener("click", () => {
                // 1 visible spec buttons
                // 2 set mode sub => disable first col
                // 3 get value from mastercell, this will be sum for next cats
                // 4 spread sum from state to all cols, enable, disable cols
                grid_mode = "sub";     // ?? should use mode

                // 1 visible, invisible buttons
                this.setButtonsModeSub();

                // 2a disable primary col grid elements
                // 2b disable primary col header toggle
                this.setModeSub(primary_category_id);

                // 3 get value from mastercell, this will be sum for next cats
                const masterProduction = this.getOneField(masterId);       //id

                // 4 spread sum to all fields from default or state_arr
                if (!this.#state_arr.find(o => o.masterId === masterId)){
                    this.spreadDefaultVals(masterId);
                    this.spreadDefaultVis(masterId);
                }
                else{
                    this.spreadStateVals(masterId);
                    this.spreadStateVis(masterId);
                }
            });

            buttPrev.addEventListener("click", () => {
                const materialParent = this.#grid.querySelector(".ltp-material-master");
                masterRow = parseInt(materialParent.style["grid-row-start"]);
                // 0 check if possible
                if (masterRow > masterRowMin)
                {
                    // 1 dishighlight current mastercell
                    materialParent.classList.remove("ltp-material-master");

                    // 2 highlight element prim col prev row == new mastercell
                    masterRow = masterRow -1;
                    masterId = this.getMasterId(primary_category_id, masterRow);
                    const materialParent2 = this.#grid.querySelector("div[data-material=\"" + masterId + "\"]");
                    materialParent2.classList.add("ltp-material-master");

                    //3 spread vals to all sub fields of masterId
                    if (this.#state_arr.find(o => o.masterId === masterId))
                        this.spreadStateVals(masterId);
                    else
                        this.spreadDefaultVals(masterId);
                }
            });

            buttNext.addEventListener("click", () => {
                // get masterRow from grid, maybe changed by SetDefault
                const materialParent = this.#grid.querySelector(".ltp-material-master");
                masterRow = parseInt(materialParent.style["grid-row-start"]);
                // 0 check if possible
                if (masterRow < masterRowMax){
                    // 1 dishighlight current mastercell
                    materialParent.classList.remove("ltp-material-master");

                    // 2 highlight element prim col next row ==mastercell
                    masterRow = masterRow + 1;
                    masterId = this.getMasterId(primary_category_id, masterRow);
                    const materialParent2 = this.#grid.querySelector("div[data-material=\"" + masterId + "\"]");
                    materialParent2.classList.add("ltp-material-master");

                    //3 spread vals to all sub fields of masterId
                    if (this.#state_arr.find(o => o.masterId === masterId))
                        this.spreadStateVals(masterId);
                    else
                        this.spreadDefaultVals(masterId);
                }
            });

            buttBack2Main.addEventListener("click", () => {
                // 1 save state of subs
                // 2 buttons visiblity
                // 3 set mode main => enable first col, disable other cols, headers same

                // 1a save state of subs for this master class
                this.saveState();
                // 1b mark saved class
                const masterId = this.#grid.querySelector(".ltp-material-master").dataset.material;
                this.setMaterialMarked(masterId);

                // 2 buttons visibility
                grid_mode = "main";     // ?? should use mode
                this.setButtonsModeMain();

                // 3 enable, disable elements and headers
                this.setModeMain(primary_category_id);
            });

            buttCancel.addEventListener("click", () => {
                // 1 NOT save state of subs
                // 2 buttons visiblity
                // 3 set mode main => enable first col, disable other cols, headers same

                // 2 buttons visibility
                grid_mode = "main";     // ?? should use mode
                this.setButtonsModeMain();

                // 3 enable, disable elements and headers
                this.setModeMain(primary_category_id);
             });

            buttClear.addEventListener("click", () => {
                // 1 remove masterId from state
                this.clearState( masterId);
                this.setMaterialUnmarked(masterId);

                // 2 buttons visibility
                grid_mode = "main";     // ?? should use mode
                this.setButtonsModeMain();

                // 3 enable, disable elements and headers
                this.setModeMain(primary_category_id);
            });

            buttReset.addEventListener("click", () => {
                // stay in submode, fill elemenst according default-share
                // 3 get value from mastercell, this will be sum for next cats
                const masterProduction = this.getOneField(masterId);       //id
                // 4 spread sum to all fields from default-share, default visibility
                this.spreadDefaultVals(masterId);
                this.spreadDefaultVis(masterId);
                // 5 state
                this.updateStateFromGrid(masterId);
                this.updateStateColState(masterId);
            });

            this.#grid.appendChild(frag2);
        }

        // FIXME
        window.materials = this;
    }

    materialsSet() {
        return !!this.#materials;
    }

    initTargets(totalValue) {
        // start or setDefaultButton or outer clearButton
        // called by clientside resetMaterialGrid and clearMaterialGrid
        if (totalValue === undefined || !this.#materials)
            return;
        this.#totalValue = totalValue;

        for (const category of this.#materials) {
            const sharesMissing = category.classes.filter(m => m.default_share === undefined);
            const sharesDefined = sharesMissing.length <= 1;
            const shares = Object.fromEntries(category.classes.filter(cl => cl.default_share !== undefined).map(cl => [cl.id, cl.default_share]));
            if (sharesMissing.length === 1) {
                const aggregated = Object.values(shares).reduce((a,b) => a+b, 0);
                const final = aggregated >= 1 ? 0 : 1 - aggregated;
                shares[sharesMissing[0].id] = final;
            }
            else {
                const defaultClass = category.classes.find(m => m.is_default);
                if (defaultClass) {
                    const aggregated = Object.entries(shares).filter(([k,v]) => k !== defaultClass.id).map(([k,v]) => v).reduce((a,b) => a+b, 0);
                    const final = aggregated >= 1 ? 0 : 1 - aggregated;
                    sharesMissing.forEach(sh => shares[sh.id] = 0);
                    shares[defaultClass.id] = final;
                }
            }
            for (const [clzz, share] of Object.entries(shares)) {
                const amount = totalValue * share;
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + clzz + "\"]");
                if (!materialParent) {
                    console.log("Material cell not found:", clzz, "category: ", category?.id);
                    continue;
                }
                const inp = materialParent.querySelector("input[type=number]");
                inp.value = amount;
                inp.max = totalValue;
            }
        }
        if (!this.is_primary){
            // all cols active
            this.spreadDefaultVisAll();
        }

        if (this.is_primary)
        {  // all reset actions
            // 1 delete all states + unmark
            const primary_category_id = this.#lot_creation.processes[this.#processName].structure.primary_category;
            //loop materials for cat=prim_cat
            for (const category of this.#materials) {
                if (category.id == primary_category_id){
                    for (const cell of category.classes) {
                        this.clearState(cell.id);
                        this.setMaterialUnmarked(cell.id);
                    }
                }
            }
            // 2 set mode main
            const masterRow = 2;      //first
            const masterId = this.getMasterId(primary_category_id, masterRow);
            this.setModeMain(primary_category_id);
            // 3a dishighlight current mastercell
            const materialParent = this.#grid.querySelector(".ltp-material-master");
            materialParent.classList.remove("ltp-material-master");
            // 3b highlight element prim col mastercell
            const materialParent2 = this.#grid.querySelector("div[data-material=\"" + masterId + "\"]");
            materialParent2.classList.add("ltp-material-master");
            // 4 fill with default
            this.spreadDefaultVals(masterId);
            // 5 buttons mode main
            //grid_mode = "main";     // ?? should use mode
            this.setButtonsModeMain();
        }
    }

    getSetpoints() {
        // get all values, for later usage in Store
        let my_is_active;
        if (!this.#materials)
            return undefined;
        const results = Object.create(null);
        if (!this.is_primary){
            // get all values from grid
            results['_sum'] = this.#totalValue;
            for (const container of this.#grid.querySelectorAll("div[data-category][data-material]:not(.ltp-material-disabled)")) {
                const inp = container.querySelector("input[type=number]");
                results[container.dataset.material] = parseFloat(inp.value) || 0;
            }
        }
        else{ // get setpoints from state
            results['_sum'] = this.#totalValue;
            for (let ii = 0; ii < this.#state_arr.length; ii++) {
                const oneEntry = this.#state_arr[ii];
                const subObj = Object.create(null);
                subObj['_sum'] = oneEntry.masterVal;
                for (let i2 = 0; i2 < oneEntry.details.length; i2++) {
                    const myMaterialId = oneEntry.details[i2].materialId;
                    const myCatId = this.getCategoryIdFromClassId(myMaterialId);
                    //check cat is_active
                    for (let i3 = 0; i3 < oneEntry.colState.length; i3++) {
                        if (oneEntry.colState[i3].category == myCatId)
                            my_is_active = oneEntry.colState[i3].is_active; // "true" or undefined
                    }
                    if (my_is_active) {
                        subObj[myMaterialId] = oneEntry.details[i2].value;
                    }
                }
                results[oneEntry.masterId] = subObj;
            }
            //additional get sum from non-stated masters
            const primary_category_id = this.#lot_creation.processes[this.#processName].structure.primary_category;
            for (const category of this.#materials) {
                if (category.id == primary_category_id){
                    for (const cell of category.classes) {
                        const cellid = cell.id;
                        if (!this.#state_arr.find(o => o.masterId === cellid)){
                            const subObj = Object.create(null);
                            subObj['_sum'] = this.getOneField(cellid);
                            results[cellid] = subObj;
                        }
                    }
                }
            }
        }
        return results;
    }

    getOneField(cellid){
        return parseFloat(this.#grid.querySelector("div[data-category][data-material=\"" + cellid + "\"]")?.querySelector("input[type=number]")?.value);
    }

    setOneField(cellid, newValue){
        //set value to spec grid cell
        const materialParent = this.#grid.querySelector("div[data-category][data-material=\"" + cellid + "\"]");
        if (materialParent)
            materialParent.querySelector("input[type=number]").value = newValue;
    }

    setSetpointsTest(totalProduction) {
        // just test method loop grid and to set specified value to specified field
        for (const category of this.#materials) {
            let idx = 0;
            for (const item in category.classes) {
                idx = idx + 1;
                const cellid = category.classes[item].id;
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cellid + "\"]");
                if (!materialParent) {
                    console.log("Material cell not found:", item, "category: ", category?.id);
                    continue;
                }
                materialParent.querySelector("input[type=number]").value = 4712;  //just test
            }
        }
    }

    /*
    reset(setpoints) {
        if (!setpoints)
            return;
        Object.entries(setpoints).forEach(([key, value]) => {
            const el = this.#grid.querySelector("div[data-material=\"" + key + "\"] input[type=\"number\"]");
            if (el)
                el.value = value;
        });
    }
    */

    changeFilling(material_category, changed_class, lots_weight_total) {
        const allContainers = Array.from(this.#grid.querySelectorAll("div[data-category=\"" + material_category.id + "\"][data-material]"));
        const defaultContainer = allContainers.find(c => c.dataset["default"] === "true") || allContainers[0];
        const totalSum = allContainers.map(c => parseFloat(c.querySelector("input[type=number]").value) || 0).reduce((a,b) => a+b, 0);
        const diff = totalSum - lots_weight_total;
        if (diff === 0)
            return false;
        const defaultValueField = defaultContainer.querySelector("input[type=number]");
        const defaultValue = parseFloat(defaultValueField.value) || 0;
        if (changed_class !== undefined && defaultValue - diff >= 0) {  // if possible, adapt the default field only
            defaultValueField.value = defaultValue - diff;
            return true;
        }
        // else, try to adapt all others
        const currentChanged = allContainers.find(c => c.dataset["material"] === changed_class);
        const currentValue = currentChanged !== undefined ? parseFloat(currentChanged.querySelector("input[type=number]").value ) || 0 : 0;
        if (currentValue <= lots_weight_total) {
            const totalRemaining = lots_weight_total - currentValue;
            const totalOther = totalSum - currentValue;
            for (const el of allContainers) {
                if (el === currentChanged)
                    continue;
                const inp = el.querySelector("input[type=number]");
                const fraction = parseFloat(inp.value) / totalOther;
                inp.value = fraction * totalRemaining;
            }
            return true;
        }
        // else: the newly set value is greater than the total available amount => TODO show warning to user and disable Accept button
        return false; // FIXME
    }

    totalValueChanged(totalProduction) {
        // called from initMaterialGrid when total production changes
        const oldValue = this.#totalValue;
        if (oldValue === totalProduction)
            return;
        const factor = totalProduction / oldValue;
        this.#totalValue = totalProduction;
        if (oldValue === 0) {
            this.initTargets(totalProduction);
            return true;
        }
        Array.from(this.#grid.querySelectorAll("[data-category][data-material] input[type=number]")).forEach(inp => inp.max = totalProduction);
        let changed = false;
        if (this.is_primary) {
            //1 changeFilling only master category
            const container1 = this.#grid.querySelector(".ltp-material-master");
            const primary_category_id = container1.dataset.category;
            const masterId = container1.dataset.material;
            const primary_category = this.getCategoryFromId(primary_category_id);
            this.changeFilling(primary_category, undefined, this.#totalValue);
            //2 spread from state or default
            if (!this.#state_arr.find(o => o.masterId === masterId)){
                this.spreadDefaultVals(masterId);
                //this.spreadDefaultVis(masterId);
            }
            else{
                this.spreadStateVals(masterId);
                //this.spreadStateVis(masterId);
            }
            //3 update state for ALL saved classes
            this.updateStateFromTotal(primary_category_id, factor);
            changed = true;
        }
        else{ //non-primary, for all categories
            for (const category of this.#materials) {
                if (this.changeFilling(category, undefined, this.#totalValue))
                    changed = true;
            }
        }
        return changed;
    }

    getValueFromState(masterId, materialId){
        // matching state to masterId
        const oneState = this.#state_arr.find(o => o.masterId === masterId);
        if (oneState){
            const check01 = oneState.details;   //array of objects
            // find matching entry in array
            const cell = oneState.details.find(el => el.materialId === materialId);
            return cell.value;
        }
        else
            return undefined;
    }

    getActiveFromState(masterId, catId){
        const oneState = this.#state_arr.find(o => o.masterId === masterId);
        if (oneState){
            const cell = oneState.colState.find(el => el.category === catId);
            if (cell.is_active == "true")
                return true;
        }
        else
            return false;
    }

    getMasterValFromState(masterId){
        // matching state to masterId
        const oneState = this.#state_arr.find(o => o.masterId === masterId);
        if (oneState){
            const masterVal = oneState.masterVal;   //masterVal = sum to spread
            return masterVal;
        }
        else
            return undefined;
    }

    getCategoryFromId(categoryId){
        for (const category of this.#materials) {
            if (category.id == categoryId){
                return (category);
            }
        }
    }

    getCategoryIdFromClassId(classId){
        for (const category of this.#materials) {
            for (const item in category.classes) {
                const cellid = category.classes[item].id;
                if (cellid == classId)
                    return (category.id);
            }
        }
    }

    getProcessName(){
        return this.#processName;
    }

    get columnsSelectable() {
        return this.getAttribute("columns-selectable") !== null;
    }

    set columnsSelectable(selectable) {
        if (selectable)
            this.setAttribute("columns-selectable", "");
        else
            this.removeAttribute("columns-selectable");
    }

}