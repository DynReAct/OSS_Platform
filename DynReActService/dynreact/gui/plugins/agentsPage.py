"""
Module agentsPage

Page responsible to present the UI into the global solution

"""

from enum import Enum
import dash, json, time, string, random, hashlib, datetime
import dash_ag_grid as dash_ag
import pandas as pd
from confluent_kafka import Producer, Consumer
from confluent_kafka.admin import AdminClient
from dash import html, dcc, ctx, callback, Input, Output, State
from jsonpath_ng.ext import parse
from dynreact.auction.auction import Auction, JobStatus
from dynreact.app import state
from dynreact.shortterm.common import KeySearch, purge_topics, delete_topics
from dynreact.shortterm.short_term_planning import create_auction, start_auction, genauction, ask_results
from dynreact.gui.localization import Localization
from dynreact.gui.pages.session_state import language
from dash import ALL

DISPLAY_FLEX = {"display": "flex"}
DISPLAY_BLOCK = {"display": "block"}
NO_DISPLAY = {"display": "none"}

translations_key = "agp"

# Settings (From stp_context.json in DynReactService/data)
# params related to kafka config and timing delays
# We force the extaction of the configuration object before finding the values.
stp_params = state._plugins.get_stp_config_params() # O el método que recupere el ShortTermTargets
if stp_params:
    KeySearch.set_global(stp_params._stpConfigParams)
# state.set_stp_config()
EXTERNAL_PERF_URL = KeySearch.search_for_value("PERF_URL")

# Recovering the last snapshot selected as well as Site related plants
current  = state.get_snapshot_provider().current_snapshot_id()
res_lst  = [j.name_short for j in  state.get_site().get_process_all_equipment()]

snapshot = state.get_snapshot(current)

KAFKA_IP = KeySearch.search_for_value("KAFKA_IP")
TOPIC_GEN = KeySearch.search_for_value("TOPIC_GEN")
TOPIC_CALLBACK = KeySearch.search_for_value("TOPIC_CALLBACK")
VB = KeySearch.search_for_value("VB")
SMALL_WAIT = KeySearch.search_for_value("SMALL_WAIT")

class ParamDef(tuple, Enum):
    I = (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)
    L = (NO_DISPLAY, DISPLAY_FLEX, dash.no_update, dash.no_update, dash.no_update)
    G = (NO_DISPLAY, NO_DISPLAY, DISPLAY_FLEX, DISPLAY_FLEX, dash.no_update)
    R = (NO_DISPLAY, dash.no_update, DISPLAY_FLEX, DISPLAY_FLEX, dash.no_update)

def sendmsgtopic(producer: Producer, tsend: str, topic: str, source: str, dest: str,
                 action: str, payload: dict = None, vb: int = 0) -> None:
    """
    Send message to a Kafka topic.

    :param producer: The Kafka producer instance.
    :param tsend: The topic to send the message to.
    :param topic: The topic of the message.
    :param source: The source of the message.
    :param dest: The destination of the message.
    :param action: The action to be performed.
    :param payload: The payload of the message. Defaults to {"msg": "-"}
    :param vb: Verbosity level. Defaults to 0.
    """
    if payload is None:
        payload = {"msg": "-"}
    msg = dict(
        topic=topic,
        action=action,
        source=source,
        dest=dest,
        payload=payload
    )
    mtxt = json.dumps(msg)

    producer.produce(value=mtxt, topic=tsend, on_delivery=confirm)
    producer.flush()


def confirm(err: str, msg: str) -> None:
    """
    Confirms the message delivery and prints an error message if any.

    :param err: Error message, if any.
    :param msg: The message being confirmed.
    """
    if err:
        print("Error sending message: " + msg + " [" + err + "]")
    return None


def sleep(seconds: float, producer: Producer, verbose: int):
    """
    Sleep for the specified number of seconds and notify the general LOG about it.

    :param seconds: Number of seconds to be waited.
    :param producer: Kafka object producer.
    :param verbose: Level of verbosity.
    """
    if verbose > 0:
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=TOPIC_GEN, source="UX",
            dest="LOG:" + TOPIC_GEN, action="WRITE",
            payload=dict(msg=f"Waiting for {seconds}s..."), vb=verbose
        )
    time.sleep(seconds)

def flatten_jobs_and_transform(jobs, columns):
    """
    Generates a dict that matches the expected type of AgGrid

    :param jobs: Array of results(dict) with job information.
    :param columns: Desired column to include information about.

    :return: Processed job JSON.
    :rtype: dict
    """
    flatten_jobs = []
    for record in jobs:
        flattened = {}
        for col in columns:
            path = col.get("path")
            identifier = col.get("field")
            if path and identifier:
                expr = parse(f'$.{path}')
                match = expr.find(record)
                flattened[identifier] = match[0].value if match else None
        flatten_jobs.append(flattened)
    return flatten_jobs

def random_letters(length: int):
    """
    Generates a random letter identifier.

    :param length: Word size.

    :return: Random pattern.
    :rtype: str
    """
    return ''.join(random.choices(string.ascii_lowercase, k=length))

def make_ag_grid_for_equipment(equipment_id, jobs):
    """
    Generates a random letter identifier.

    :param equipment_id: Current equipment.
    :param jobs: Array of results(dict) with job information.

    :return: HTML layout operated by the UI.
    :rtype: dash.html.Div
    """
    c_defs = KeySearch.search_for_value("TableMappings")

    if c_defs:
        # Paths can't have '.'
        c_process = list(map(lambda d: {**d, "field": hashlib.sha256(d["headerName"].encode()).hexdigest()[0:5]}, c_defs))
        row_data = flatten_jobs_and_transform(jobs, c_process)

        return html.Div([
            html.Div([
                # Put the button here
                html.Button("Download Equipment CSV", id="download-btn", className="dynreact-button"),
            ], style={
                "display": "flex",
                "justifyContent": "flex-end",  # aligns button to the right
                "margin": "10px"
            }),
            dcc.Download(id="download-csv"),
            dash_ag.AgGrid(
                className="ag-theme-alpine",
                rowData=row_data,
                columnDefs=c_process,
                defaultColDef={"resizable": True, "sortable": True, "filter": True},
                style={"height": "300px", "width": "100%"},
                columnSize="sizeToFit"  # Ensures no horizontal scroll
            )
        ])

    else:
        return html.Div([
            html.Div([
                # Put the button here
                html.Button("Download Equipment CSV", id="download-btn", className="dynreact-button"),
            ], style={
                "display": "flex",
                "justifyContent": "flex-end",  # aligns button to the right
                "margin": "10px"
            }),
            dcc.Download(id="download-csv"),
            html.Div("No TABLE_MAPPINGS are defined, unable to render Table")
        ])

def initialize_defaults(extra=False):
    """
    Initializes default values for the layout function.

    :param bool extra: Whether to initialize extra variables.
    :return: Tuple of default values.
    :rtype: tuple
    """
    if extra:
        return [], [], [], 'No', '', pd.DataFrame(), [], []
    return 'None', 'Orders', [], [], [], []

def build_resources_list(res_lst):
    """
    Builds a list of resources for selection.

    :param list res_lst: List of resource names.
    :return: Tuple of resource options for a dropdown.
    :rtype: tuple
    """
    return res_lst, []

def generate_page_header(snpshot):
    """
    Generates the page header section.

    :param str snpshot: Timestamp for the current snapshot.
    :return: Page header HTML component.
    :rtype: dash.html.Div
    """
    return html.Div([
        dcc.Location(id="agents-url", refresh=False),
        html.H1("Short term planning", id="agp-title"),
        html.H2(f"Interesting Equipments and Materials for: {snpshot}", id="ag-page"),
        html.Br()
    ])

def generate_material_type_section(default_value='Orders'):
    """
    Generates the material type selection section (Orders vs Materials).

    :param default_value: Default material type selection.
    :return: HTML Div with material type selector.
    :rtype: dash.html.Div
    """
    return html.Div([
        html.Div("Schedule based on: ", id="ag-cont_item-matypes"),
        dcc.RadioItems(
            options=[
                {'label': 'Materials', 'value': 'Materials'},
                {'label': 'Orders', 'value': 'Orders'}
            ],
            value=default_value,
            inline=True,
            id="ag-matypes",
        )],
        className="agents-selector-matypes",
        id="ag-sect1"
    )

def generate_resource_section(res_all, res_def):
    """
    Generates the resource selection section using Dropdown.

    :param res_all: All available resources.
    :param res_def: Default selected resources.
    :return: HTML Div with resource selector.
    :rtype: dash.html.Div
    """
    return html.Div([
        generate_material_type_section(),
        html.Br(),
        html.Div([
            html.Div("Targeted Equipments: ", id="ag-cont_item-resources"),
            dcc.Dropdown(
                options=res_all,
                value=res_def,
                multi=True,
                id="ag-resources",
            )],
            className="agents-selector-resources",
            id="ag-sect2"
        ),
        html.Br(),
        html.Div(id="ag-equipment-configs", style={"margin-top": "20px"}),
        html.Br(),
    ])

def generate_materials_section(lmats, s_mats):
    """
    Generates the materials selection section using Dropdown.

    :param lmats: Available materials.
    :param s_mats: Selected materials.
    :return: HTML Div with materials selector.
    :rtype: dash.html.Div
    """
    return html.Div([
        html.Div(
            children="Targeted Orders (click to unselect): ",
            id="ag-cont_item-materials"
        ),
        dcc.Dropdown(
            options=lmats,
            value=s_mats,
            multi=True,
            id="ag-materials",
        )],
        className="agents-selector-materials",
        id="ag-sect3",
        style=NO_DISPLAY
    )

def generate_ass_material_type_section(default_value='No'):
    """
    Generates the assigned materials type section.

    :param default_value: Default value for including assigned materials.
    :return: HTML Div with assigned material type selector.
    :rtype: dash.html.Div
    """
    return html.Div([
        html.Div(
            children="Include materials/orders assigned to non-targeted resources?: ",
            id="ag-cont_ass-materials"
        ),
        dcc.RadioItems(
            options=[
                {'label': 'Yes', 'value': 'Yes'},
                {'label': 'No', 'value': 'No'}
            ],
            value=default_value,
            inline=True,
            id="ag-ass-matypes",
        )],
        className="agents-selector-ass-matypes",
        id="ag-sect4"
    )

def generate_ass_materials_section(amats, as_mats):
    """
    Generates the assigned materials selection section using Dropdown.

    :param list amats: List of associated materials.
    :param list as_mats: List of selected associated materials.
    :return: Associated materials selection HTML component.
    :rtype: dash.html.Div
    """
    return html.Div([
        html.Div(
            children="Targeted Assigned Orders (click to select): ",
            id="ag-cont_item-ass-materials"
        ),
        dcc.Dropdown(
            options=amats,
            value=as_mats,
            multi=True,
            id="ag-ass-materials",
        )],
        className="agents-selector-ass-materials",
        id="ag-sect5",
        style=NO_DISPLAY
    )

def generate_input_section(txt_def):
    """
    Generates the input section for entering reference names.

    :param str txt_def: Default text value for the input field.
    :return: Input field HTML component.
    :rtype: dash.html.Div
    """
    return html.Div([
        html.P('Enter the ReferenceName for this simulation:'),
        dcc.Input(id='ag-ref', type='text', debounce=True, value=txt_def),
        html.P(id='ag-err', style={'color': 'red'}),
        html.P(id='ag-out')
    ])


def generate_buttons():
    """
    Generates the buttons for creating and starting an auction.

    :return: HTML Div with action buttons.
    :rtype: dash.html.Div
    """
    return html.Div([
        html.Button(
            children='Create Auction',
            id='ag-submit',
            n_clicks=0,
            style=DISPLAY_BLOCK
        ),
        html.Button(
            children='Start Auction',
            id='ag-start',
            n_clicks=0,
            style=NO_DISPLAY
        ),
        html.Button(
            children=[
                html.Span(className="material-symbols-outlined", children="refresh"),
                " Refresh Results"
            ],
            id='ag-refresh',
            n_clicks=0,
            style=NO_DISPLAY
        ),
        html.Button(
            children='End Auction',
            id='ag-end',
            n_clicks=0,
            style=NO_DISPLAY
        ),
        html.Button(
            children='Restart',
            id='ag-restart',
            n_clicks=0,
            style=NO_DISPLAY
        )],
        style={'display': 'flex', 'justify-content': 'space-between', 'width': '100%'}
    )

def generate_status_section():
    """
    Generates the status display section.

    :return: HTML Div with status display.
    :rtype: dash.html.Div
    """
    return html.Div([
        html.Hr(),
        html.H2("Status", id="ag-h2section-status"),
        html.Div([
            html.Div(
                children="Status of the auction: Not started.",
                id="ag-status"
            )],
            className="agents-status-auction"
        ),
    ])

def layout(*args, **kwargs):
    """
    Function defining the Flask layout for the STP Agents.

    :param args: Variable-length arguments.
    :param kwargs: Variable-length keyword arguments.
    :return: HTML layout operated by the UI.
    :rtype: dash.html.Div
    """
    # Initialize default values
    snpshot, mat_def, res_all, res_def, lmats, s_mats = initialize_defaults()
    o_mats, amats, as_mats, mat_ass_def, txt_def, resul, res_no_all, res_no_def = initialize_defaults(extra=True)

    # Update values if there is a current state
    if current is not None:
        snpshot = current.strftime("%Y-%m-%dT%H:%M:%S%z")
        res_all, res_def = build_resources_list(res_lst)

    # Generate HTML layout
    htmscr = html.Div([
        html.Link(
            href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&icon_names=refresh",
            rel="stylesheet"
        ),
        language,
        dcc.Store(id='stored-data'),
        dcc.Store(id='has_initialized_session', data=False),
        dcc.Store(id='auction-store', storage_type="local"),
        generate_page_header(snpshot),
        generate_resource_section(res_all, res_def),
        generate_materials_section(lmats, s_mats),
        generate_ass_material_type_section(mat_ass_def),
        html.Br(),
        generate_ass_materials_section(amats, as_mats),
        generate_input_section(txt_def),
        dcc.Loading([
            generate_buttons(),
            generate_status_section(),
            dcc.Tabs(
                id="tabs",
                children=[],
                style={
                    "overflowX": "auto",
                    "whiteSpace": "nowrap",
                    "maxWidth": "100%"
                }
            ),
            html.Div(id="tab-content", style={"marginTop": 20})
        ],
        delay_show=50,
        overlay_style={
            "visibility": "visible",
            "filter": "blur(4px)",
            "opacity": .5,
            "backgroundColor": "white"
        },
        custom_spinner=html.Span("Loading", className="loader")
        )
    ])

    return htmscr


@callback(  Output('ag-cont_item-materials','children'),
            Output('ag-materials','options'),
            Output('ag-sect3','style'),
            Output('ag-materials','value'),
            Input( 'ag-matypes','value'),
            Input( 'ag-resources','value'))
def set_materials(matype, plants):
    """
    Function to prepare the list of materials to use in the auction

    :param str matype: Either Materials or Orders.
    :param list plants: List of resources to be part of the auction.

    :return: Tuple of string, list, dictionary and list of materials.
    :rtype: tuple
    """
    if len(matype) > 0 and len(plants) > 0:
        res  = []
        site = state.get_site()
        all_materials = []

        for ir in plants:
            stg_act = site.get_equipment_by_name(ir).storage_in

            if matype == 'Materials':
                lmts = snapshot.get_material_equipment(site, ir, stg_act)
            else:
                lmts = snapshot.get_orders_equipment(site, ir, stg_act)

            all_materials.extend(sorted(lmts))

        # Remove duplicates
        unique_materials = []
        seen = set()
        for mat in all_materials:
            if mat not in seen:
                unique_materials.append(mat)
                seen.add(mat)

        titx= f'Targeted {matype} (click to unselect from {len(unique_materials)} entries):'

        for ic in unique_materials:
            res.append({"label": str(ic), "value": str(ic)})

        return titx, res, DISPLAY_BLOCK, []
    else:
        if matype == 'Materials':
            titx = 'Targeted Materials (select resources first):'
        else:
            titx = 'Targeted Orders (select resources first):'

        return titx, [], NO_DISPLAY, []

#
@callback( Output('ag-cont_item-ass-materials','children'),
           Output('ag-ass-materials','options'),
           Output('ag-sect5','style'),
           Output('ag-ass-materials','value'),
           Input( 'ag-matypes','value'),
           Input( 'ag-resources','value'),
           Input( 'ag-ass-matypes','value'))
def set_ass_materials(matype, plants, ass_mats):
    """
    Function to prepare the list of materials to use in the aunction

    :param str matype: Either Materials or Orders.
    :param list plants: List of resources to be part of the auction.
    :param list ass_mats: List of materials already assigned

    :return: Tuple of string, list, dictionary and list of materials.
    :rtype: tuple
    """
    if len(matype) > 0 and len(plants) > 0 and ass_mats == 'Yes':
        res = []
        site = state.get_site()
        all_assigned_materials = []

        for ir in plants:
            cplnt = site.get_equipment_by_name(ir)
            stg_act = cplnt.storage_in

            if matype == 'Materials':
                amts = snapshot.get_material_equipment(site, ir, stg_act, cplnt.id)
            else:
                amts = snapshot.get_orders_equipment(site, ir, stg_act,cplnt.id)

            all_assigned_materials.extend(sorted(amts))

        # Remove duplicates
        unique_assigned_materials = []
        seen = set()
        for mat in all_assigned_materials:
            if mat not in seen:
                unique_assigned_materials.append(mat)
                seen.add(mat)

        titx= f'Targeted {matype} (click to select from {len(amts)} entries):'

        for ic in unique_assigned_materials:
            res.append({"label": str(ic), "value": str(ic)})

        return titx, res, DISPLAY_BLOCK, []

    return '', [], NO_DISPLAY, []

@callback(
    Output('ag-status', 'children'),
    Output('ag-submit', 'style'),
    Output('ag-start', 'style'),
    Output('ag-refresh', 'style'),
    Output('ag-end', 'style'),
    Output('ag-restart', 'style'),
    Output('tabs', 'children'),
    Output('auction-store', 'data'),
    Output('has_initialized_session', 'data'),
    Input('ag-submit', 'n_clicks'),
    Input('ag-start', 'n_clicks'),
    Input('ag-refresh', 'n_clicks'),
    Input('ag-end', 'n_clicks'),
    Input('ag-restart', 'n_clicks'),
    State('ag-ref', 'value'),
    State('ag-matypes', 'value'),
    State('ag-resources', 'value'),
    State('ag-materials', 'value'),
    State('ag-ass-matypes', 'value'),
    State('ag-ass-materials', 'value'),
    State('auction-store', 'data'),
    State('has_initialized_session', 'data'),
    State({'type': 'equip-date', 'index': ALL}, 'value'),
    prevent_initial_call=True
)
def handle_auction_actions(ag_create, ag_start, ag_refresh, ag_end, ag_restart,
                          reftxt, matype, resources, materials, ass_type, ass_materials,
                          auction_data, has_initialized, dates):
    """
    Handles all auction-related actions based on button clicks.
    Includes complete logic for both Orders and Materials material types.

    :param ag_create: Number of clicks on Create button.
    :param ag_start: Number of clicks on Start button.
    :param ag_refresh: Number of clicks on Refresh button.
    :param ag_end: Number of clicks on End button.
    :param ag_restart: Number of clicks on Restart button.
    :param reftxt: Reference text for the auction.
    :param matype: Material type (Materials or Orders).
    :param resources: Selected resources.
    :param materials: Selected materials.
    :param ass_type: Whether to include assigned materials.
    :param ass_materials: Selected assigned materials.
    :param auction_data: Stored auction data.
    :param has_initialized: Whether session has been initialized.
    :param dates: List of start dates for each equipment.
    :return: Tuple with updated UI states and data.
    :rtype: tuple
    """
    # Deserialize auction if it exists
    if auction_data:
        auction = Auction.model_validate_json(auction_data)
    else:
        auction = Auction(
            all_equip=res_lst,
            equip=[],
            snapshot=current.strftime("%Y-%m-%dT%H:%M:%S%z") if current else ""
        )

    # Determine which button was clicked
    triggered_id = ctx.triggered_id

    if triggered_id == 'ag-submit':
        return handle_create_click(ag_create, reftxt, matype, resources, materials,
                                  ass_type, ass_materials, auction, dates)
    elif triggered_id == 'ag-start':
        return handle_start_click(ag_start, reftxt, auction)
    elif triggered_id == 'ag-refresh':
        return handle_refresh_click(ag_refresh, reftxt, auction)
    elif triggered_id == 'ag-end':
        return handle_end_click(ag_end, reftxt, auction)
    elif triggered_id == 'ag-restart':
        return handle_restart_click(ag_restart, reftxt, auction)

    return dash.no_update

def handle_create_click(ag_create, reftxt, matype, plnts, lmats, ass_type, amats, auction, dates):
    """
    Handles the logic when the 'Create Auction' button is clicked.
    Supports both Materials and Orders material types with proper conversion logic.

    :param ag_create: Number of clicks on the Create button.
    :param reftxt: Topic under which the auction will take place.
    :param matype: Material type (Materials or Orders).
    :param plnts: List of selected plants/resources.
    :param lmats: List of selected materials.
    :param ass_type: Whether to include assigned materials ('Yes' or 'No').
    :param amats: List of assigned materials.
    :param auction: Current auction object.
    :param dates: List of start dates for each equipment.
    :return: Tuple containing the auction status message, styling options,
             tabs, and serialized auction.
    :rtype: tuple
    """

    equip_configs = {}
    for i, plant_name in enumerate(plnts):
        equip_configs[plant_name] = {
            "start_date": dates[i]
        }

    # Set up auction details
    auction.code = reftxt
    snpshot = current.strftime("%Y-%m-%dT%H:%M:%S%z")

    # Prepare materials list based on type and assigned materials
    if matype == 'Materials':
        final_mats = lmats if lmats else []
        if ass_type == 'Yes' and amats:
            # Combine with assigned materials
            final_mats = list(set(final_mats + amats))
        os_mats = final_mats

    else:  # Orders
        # For Orders, we need special handling
        o_mats = lmats if lmats else []
        if ass_type == 'Yes' and amats:
            # Combine with assigned materials
            o_mats = list(set(o_mats + amats))

        os_mats = snapshot.get_material_selected_orders(o_mats, plnts, state.get_site())

    # Create the auction
    purge_topics(topics=[TOPIC_CALLBACK, TOPIC_GEN])

    try:
        initialize_auction(
            topic=reftxt,
            snap_name=snpshot,
            resources=plnts,
            materials=os_mats,
            verbose=0,
            equip_configs=equip_configs
        )

        # Set auction lists based on material type
        # For Materials: lmats gets os_mats, omats is empty
        # For Orders: omats gets the original o_mats list, lmats is empty
        # smats gets os_mats (the converted list for Orders, or direct list for Materials)
        if matype == 'Materials':
            auction.set_lists(reftxt, os_mats, matype, os_mats)
        else:  # Orders
            auction.set_lists(reftxt, o_mats, matype, os_mats)

        auction.auction_status = JobStatus.L

        # Delay to allow auction agents to launch
        time.sleep(len(plnts) + 5)

        text = (f'The auction {reftxt} involving {len(plnts)} resource(s) and '
                f'{len(os_mats)} {matype} is being created now. '
                f'Button clicked {ag_create} times.')
        auction.helper_text = text

        return (text, NO_DISPLAY, DISPLAY_FLEX, dash.no_update, DISPLAY_FLEX,
                DISPLAY_FLEX, dash.no_update, auction.model_dump_json(), dash.no_update)
    except Exception as e:
        text = f'An error occurred: {e}'
        return (text, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update)


def handle_start_click(ag_start, reftxt, auction):
    """
    Handles the logic when the 'Start' button is clicked.

    :param ag_start: Number of clicks on the Start button.
    :param reftxt: Topic under which the auction will take place.
    :param auction: Current auction object.
    :return: Tuple containing the auction status message, styling options,
             and current results.
    :rtype: tuple
    """
    producer_config = {
        "bootstrap.servers": KAFKA_IP,
        "linger.ms": 100,
        "acks": "all",
        "message.timeout.ms": 10000
    }
    consumer_config = {
        "bootstrap.servers": KAFKA_IP,
        "group.id": "UX",
        "auto.offset.reset": "earliest",
        'enable.auto.commit': False
    }
    producer = Producer(producer_config)
    consumer = Consumer(consumer_config)
    consumer.subscribe([genauction(reftxt), TOPIC_CALLBACK])

    # Calculate number of agents based on material type
    if auction.matype == 'Materials':
        num_materials = len(auction.lmats)
    else:  # Orders
        # For Orders, use smats (the converted list) for agent count
        num_materials = len(auction.smats)

    numag = len(auction.equip) + num_materials + 1
    print(f"Calculated {numag} agents for {auction.matype}")

    try:
        start_auction(
            topic=genauction(reftxt),
            verbose=VB,
            producer=producer,
            consumer=consumer,
            num_agents=numag
        )

        consumer.close()
        auction.auction_status = JobStatus.G

    except Exception as e:
        print(e)
        auction.auction_status = JobStatus.E
        purge_topics(topics=[TOPIC_CALLBACK, TOPIC_GEN])
        delete_topics(topics=[genauction(reftxt)])
        text = (f'The auction {reftxt} failed to start, please create a new '
                f'auction with a different name')
        auction.helper_text = text
        return (text, DISPLAY_FLEX, NO_DISPLAY, NO_DISPLAY, NO_DISPLAY,
                dash.no_update, dash.no_update, auction.model_dump_json(), dash.no_update)

    text = 'Auction effectively started.'
    auction.helper_text = text
    return (text, dash.no_update, NO_DISPLAY, DISPLAY_FLEX, DISPLAY_FLEX,
            NO_DISPLAY, dash.no_update, auction.model_dump_json(), dash.no_update)

def handle_refresh_click(ag_refresh, reftxt, auction):
    """
    Handles the logic when the 'Refresh' button is clicked.

    :param ag_refresh: Number of clicks on the Refresh button.
    :param reftxt: Topic under which the auction will take place.
    :param auction: Current auction object.
    :return: Tuple containing the auction status message, styling options,
             and current results.
    :rtype: tuple
    """
    producer_config = {
        "bootstrap.servers": KAFKA_IP,
        "linger.ms": 100,
        "acks": "all",
        "message.timeout.ms": 10000
    }
    consumer_config = {
        "bootstrap.servers": KAFKA_IP,
        "group.id": "UX",
        "auto.offset.reset": "earliest",
        'enable.auto.commit': False
    }
    producer = Producer(producer_config)
    consumer = Consumer(consumer_config)
    consumer.subscribe([genauction(reftxt), TOPIC_CALLBACK])

    res = ask_results(
        topic=genauction(reftxt),
        producer=producer,
        consumer=consumer,
        verbose=VB
    )
    auction.auction_status = JobStatus.R
    auction.set_resul(res)

    consumer.close()
    print(auction.resul)

    # Generate tabs for each equipment
    tabs = []
    if auction.resul:
        for equipment_id in auction.resul.keys():
            tabs.append(dcc.Tab(label=equipment_id, value=equipment_id))

    text = (f'Updated results {ag_refresh} times, last results update '
            f'{datetime.datetime.now()}.')
    auction.helper_text = text

    return (text, dash.no_update, dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, tabs,
            auction.model_dump_json(), dash.no_update)


def handle_end_click(ag_end, reftxt, auction):
    """
    Handles the logic when the 'End' button is clicked.

    :param ag_end: Number of clicks on the End button.
    :param reftxt: Topic under which the auction will take place.
    :param auction: Current auction object.
    :return: Tuple containing the auction status message, styling options,
             and current results.
    :rtype: tuple
    """
    producer_config = {
        "bootstrap.servers": KAFKA_IP,
        "linger.ms": 100,
        "acks": "all",
        "message.timeout.ms": 10000
    }
    producer = Producer(producer_config)

    # End auction using Kafka messages
    topic = genauction(reftxt)

    # Instruct all RESOURCE children to exit
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="RESOURCE:" + topic + ":.*",
        action="EXIT",
        vb=VB
    )

    # Instruct all MATERIAL children to exit
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="MATERIAL:" + topic + ":.*",
        action="EXIT",
        vb=VB
    )

    # Instruct the LOG of the auction to exit
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="LOG:" + topic,
        action="EXIT",
        vb=VB
    )

    # Small wait for cleanup
    sleep(SMALL_WAIT, producer=producer, verbose=VB)

    text = f'Auction ended on {datetime.datetime.now()}, you may now refresh the page.'
    auction = Auction(
        all_equip=res_lst,
        equip=[],
        snapshot=current.strftime("%Y-%m-%dT%H:%M:%S%z")
    )
    auction.auction_status = JobStatus.E

    return (text, dash.no_update, dash.no_update, NO_DISPLAY, NO_DISPLAY,
            DISPLAY_FLEX, dash.no_update, auction.model_dump_json(), dash.no_update)


def handle_restart_click(ag_restart, reftxt, auction):
    """
    Handles the logic when the 'Restart' button is clicked.

    :param ag_restart: Number of clicks on the Restart button.
    :param reftxt: Topic under which the auction will take place.
    :param auction: Current auction object.
    :return: Tuple containing the auction status message, styling options,
             and current results.
    :rtype: tuple
    """
    if auction.auction_status != JobStatus.E:
        handle_end_click(ag_restart, reftxt, auction)

    auction = Auction(
        all_equip=res_lst,
        equip=[],
        snapshot=current.strftime("%Y-%m-%dT%H:%M:%S%z")
    )

    return ("Status of the auction: Not started.", DISPLAY_FLEX, NO_DISPLAY,
            NO_DISPLAY, NO_DISPLAY, NO_DISPLAY, [],
            auction.model_dump_json(), False)


def initialize_auction(topic: str, snap_name: str, resources: list,
                       materials: list, verbose: int, equip_configs: dict) -> tuple[str, int]:
    """
    Starting the auction creation.

    :param topic: Topic for the auction.
    :param snap_name: Name of the relevant snapshot.
    :param resources: List of interesting resources for the auction.
    :param materials: List of interesting materials for the auction.
    :param verbose: Verbosity level.
    :return: Topic name of the auction and number of agents.
    :rtype: tuple
    """
    admin_client = AdminClient({"bootstrap.servers": KAFKA_IP})
    producer_config = {
        "bootstrap.servers": KAFKA_IP,
        'linger.ms': 100,
        'acks': 'all'
    }
    producer = Producer(producer_config)

    # Get equipment IDs from site structure
    lres = []
    configs_by_id = {}

    for name in resources:
        equip_obj = state.get_site().get_equipment_by_name(name)
        equip_id = equip_obj.get_equipment_id()
        lres.append(equip_id)

        if name in equip_configs:
            configs_by_id[equip_id] = equip_configs[name]

    return create_auction(
        equipments=lres,
        producer=producer,
        admin_client=admin_client,
        snapshot=snap_name,
        act=topic,
        verbose=verbose,
        materials=materials,
        equip_configs=configs_by_id,
    )


@callback(
    Output('tab-content', 'children'),
    Input('tabs', 'value'),
    State('auction-store', 'data')
)
def render_tab_content(selected_tab, auction_data):
    """
    Renders content for the selected results tab.

    :param selected_tab: The selected tab value.
    :param auction_data: Stored auction data.
    :return: HTML content for the tab.
    :rtype: dash.html.Div
    """
    if not selected_tab or not auction_data:
        return html.Div("No results available yet.")

    auction = Auction.model_validate_json(auction_data)

    if selected_tab in auction.resul:
        jobs = auction.resul[selected_tab]
        return make_ag_grid_for_equipment(selected_tab, jobs)

    return html.Div("No results for this equipment.")

@callback(
    Output("download-csv", "data"),
    Input("download-btn", "n_clicks"),
    State('tabs', 'value'),
    State('auction-store', 'data'),
    prevent_initial_call=True
)
def download_equipment_csv(n_clicks, selected_tab, auction_data):
    """
    Handles CSV download for the selected equipment.

    :param n_clicks: Number of button clicks.
    :param selected_tab: The selected tab value.
    :param auction_data: Stored auction data.
    :return: CSV download data.
    """
    if not selected_tab or not auction_data:
        return dash.no_update

    auction = Auction.model_validate_json(auction_data)

    if selected_tab in auction.resul:
        jobs = auction.resul[selected_tab]
        c_defs = KeySearch.search_for_value("TableMappings")

        if c_defs:
            c_process = list(map(
                lambda d: {**d, "field": hashlib.sha256(d["headerName"].encode()).hexdigest()[0:5]},
                c_defs
            ))
            row_data = flatten_jobs_and_transform(jobs, c_process)
            df = pd.DataFrame(row_data)

            return dcc.send_data_frame(
                df.to_csv,
                f"{selected_tab}_results.csv",
                index=False
            )

    return dash.no_update


@callback(
    Output("ag-equipment-configs", "children"),
    Input("ag-resources", "value"),
    prevent_initial_call=True
)
def update_equipment_inputs(selected_equipments):
    if not selected_equipments:
        return []

    content = [html.H4("Equipment Specific Configuration:")]

    for equip in selected_equipments:
        row = html.Div([
            html.Label(f"Machine: {equip}", style={"fontWeight": "bold", "width": "150px", "display": "inline-block"}),

            dcc.Input(
                id={'type': 'equip-date', 'index': equip},
                type="datetime-local",
                value=datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"),
                style={"margin-right": "20px"}
            ),
            html.Hr()
        ], style={"margin-bottom": "15px", "display": "flex", "alignItems": "center"})

        content.append(row)

    return content

@callback(
    Output("agp-title", "children"),
    Output("ag-cont_item-matypes", "children"),
    Output("ag-cont_item-resources", "children"),
    Output("ag-cont_ass-materials", "children"),
    Output("ag-submit", "children"),
    Output("ag-start", "children"),
    Output("ag-refresh", "children"),
    Output("ag-end", "children"),
    Output("ag-restart", "children"),
    Input("lang", "data")
)
def update_page_localization(lang: str):
    translation = Localization.get_translation(lang, translations_key)
    return (
        Localization.get_value(translation, "title", "Short term planning"),
        Localization.get_value(translation, "schedule_based_on", "Schedule based on: "),
        Localization.get_value(translation, "targeted_equipments", "Targeted Equipments: "),
        Localization.get_value(translation, "include_assigned",
                               "Include materials/orders assigned to non-targeted resources?: "),
        Localization.get_value(translation, "btn_create", "Create Auction"),
        Localization.get_value(translation, "btn_start", "Start Auction"),
        [html.Span(className="material-symbols-outlined", children="refresh"),
         " " + Localization.get_value(translation, "btn_refresh", "Refresh Results")],
        Localization.get_value(translation, "btn_end", "End Auction"),
        Localization.get_value(translation, "btn_restart", "Restart")
    )

@callback(
    Output("ag-matypes", "options"),
    Input("lang", "data")
)
def update_radio_options_localization(lang: str):
    translation = Localization.get_translation(lang, translations_key)
    return [
        {'label': Localization.get_value(translation, "label_materials", "Materials"), 'value': 'Materials'},
        {'label': Localization.get_value(translation, "label_orders", "Orders"), 'value': 'Orders'}
    ]


@callback(
    Output("ag-ass-matypes", "options"),
    Input("lang", "data")
)
def update_ass_radio_localization(lang: str):
    translation = Localization.get_translation(lang, translations_key)
    return [
        {'label': Localization.get_value(translation, "label_yes", "Yes"), 'value': 'Yes'},
        {'label': Localization.get_value(translation, "label_no", "No"), 'value': 'No'}
    ]

#TODO: add performance check
#TODO: add documentation