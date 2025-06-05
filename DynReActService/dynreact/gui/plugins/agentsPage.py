"""
Module agentsPage

Page responsible to present the UI into the global solution

"""

import dash, json, time, re, os
import pandas as pd
#
from dynreact.auction.auction import Auction

from confluent_kafka import Producer, Consumer
# from confluent_kafka.admin import AdminClient

from dash import html, dcc, ctx, callback, Input, Output, State, dash_table
# from dash.exceptions import PreventUpdate
# from dynreact.base.impl.DatetimeUtils import DatetimeUtils
# from dynreact.base.model import Snapshot, Site, Lot, Process, Coil

from dynreact.gui.localization import Localization
# from dynreact.gui.pages.session_state import selected_snapshot, language

from dynreact.app import state

# dash.register_page(__name__, path="/agents")  # now implemented by proxy
translations_key = "agp"
# Setings (From stp_context.json in DynReactService/data)
# params related to kafka config and timing delays
IP, TOPIC_GEN, VB = state.get_stp_context_params()
AW, BW, CW, EW, SMALL_WAIT = state.get_stp_context_timing()

# Recovering the last snapshot selected as well as Site related plants
current  = state.get_snapshot_provider().current_snapshot_id()
auction  = state.get_auction_obj()
res_lst  = [j.name_short for j in  state.get_site().get_process_all_equipment()]

snapshot = state.get_snapshot(current)
#
if auction is not None:
    resul   = auction.get_resul()
    res_all = auction.get_equipments()
    lmats   = auction.get_lmats()
    o_mats  = auction.get_omats()
    s_mats  = auction.get_smats()
    (mat_def,res_def,a_res,s_mats,a_mats,txt_def,mat_ass_def,amats,as_mats) = auction.get_params()
else:
    resul   = pd.DataFrame()
    res_all = []
    lmats   = []
    o_mats  = []
    s_mats  = []
    amats   = []
    as_mats = []
    mat_def = 'Orders'
    res_def = []
    txt_def = ''
    mat_ass_def = 'No'
    auction = Auction('')
#
def layout(*args, **kwargs):
    """
    Function defining the Flask layout for the STP Agents.

    :param str args: Variable args.
    :param dict kwargs: keyworded, variable-length argument dictionary.

    :return: HTML string operated by the UI.
    :rtype: str
    """
    if current is None:
        snpshot = "None"
        mat_def = 'Orders'
        res_def = []
        txt_def = ''
    else:
        snpshot = current.strftime("%Y-%m-%dT%H:%M:%S%z")
        res_all = []
        for k in range(len(res_lst)):
            rt          = {}
            rt['label'] = res_lst[k]
            rt['value'] = res_lst[k]
            res_all.append(rt)
        if auction is not None:
            lmats   = auction.get_lmats()
            o_mats  = auction.get_omats()
            s_mats  = auction.get_smats()
            (mat_def,res_def,a_res,s_mats,a_mats,txt_def, \
                      mat_ass_def,amats,as_mats) = auction.get_params()
            (st_tit,lmats,optdis,optvec) = setMaterials(mat_def, res_def)

    htmscr = html.Div([
        dcc.Location(id="agents-url", refresh=False),
        html.H1("Short term planning", id ="agp-title"),
        html.H2("Interesting Equipments and Materials for: "+ \
                 snpshot, id="ag-page"),
        html.Div([  html.Div("Schedule based on: ",id="ag-cont_item-matypes"), 
                    dcc.RadioItems(options=[
                                {'label':'Materials', 'value': 'Materials'},
                                {'label': 'Orders', 'value':'Orders'} 
                            ], value=mat_def,inline=True, id="ag-matypes",  
                            # labelStyle={'display': 'block'}, persistence=True,persistence_type='session'
                        )], 
                className="agents-selector-matypes", id="ag-sect1"),
        html.Br(),
        html.Div([  html.Div("Targeted Equipments: ",id="ag-cont_item-resources"), 
                    dcc.Checklist(options=res_all, value=res_def, 
                            inline=True, id="ag-resources",
                            # persistence=True,persistence_type='session'
                        )],
                className="agents-selector-resources", id="ag-sect2"),
        html.Br(),
        html.Div([  html.Div(children="Targeted Orders (click to unselect): ",
                      id="ag-cont_item-materials"), 
                    dcc.Checklist(options=lmats, value=s_mats,
                            inline=True, id="ag-materials", # , labelStyle={'display': 'block'}
                            # persistence=True,persistence_type='session'
                        )],
                className="agents-selector-materials", id="ag-sect3", 
                style={'display': 'none'}),
        html.Br(),
        html.Div([  html.Div(children="Include materials/orders assigned to non-targeted resources?: ",
                      id="ag-cont_ass-materials"),
                    dcc.RadioItems(options=[
                                {'label':'Yes', 'value': 'Yes'},
                                {'label': 'No', 'value': 'No'} 
                            ], value=mat_ass_def,inline=True, id="ag-ass-matypes",
                    )],
                className="agents-selector-ass-matypes", id="ag-sect4"),
        html.Br(),
        html.Div([ html.Div(children="Targeted Assigned Orders (click to select): ",
        id="ag-cont_item-ass-materials"), 
        dcc.Checklist(options=amats, value=as_mats,
        inline=True, id="ag-ass-materials", # , labelStyle={'display': 'block'}
        # persistence=True,persistence_type='session'
        )],
        className="agents-selector-ass-materials", id="ag-sect5", 
        style={'display': 'none'}), 
        html.Br(),
        html.Div([
            html.P('Enter the ReferenceName for this simulation:'),
            dcc.Input(id='ag-ref', type='text', debounce=True, value=txt_def),
            html.P(id='ag-err', style={'color': 'red'}),
            html.P(id='ag-out')]),
        html.Br(),
        html.Div([
            html.Button(children='Create Auction', id='ag-submit', n_clicks=0,
                        style={'display': 'block'}),
            html.Button(children='Start Auction', id='ag-start', n_clicks=0,
                        style={'display': 'none'})],
                    style={'display': 'flex', 'justify-content': 'space-between', 
                            'width': '100%'}),
        html.Hr(),
        html.H2("Results:", id="ag-h2section-results", style={'display': 'none'}),
        html.Div([
            dash_table.DataTable(resul.to_dict('records'),[
                    {"name": i, "id": i} for i in resul.columns], 
                    id='ag-results'),
                ], className="agents-results-auction", id="ag-results-tab", 
                style={'display': 'none'}),
        html.Br(id="ag-sep-res-st",hidden=True),
        
        html.H2("Status", id="ag-h2section-status"),
        html.Div([html.Div(children="Status of the auction: Not started.", 
                      id="ag-status")],
                className="agents-status-auction"),
    ])
    auction.set_params(htmscr)
    state.set_auction_obj(auction)
    return(htmscr)

#
@callback(  Output('ag-cont_item-materials','children'),
            Output('ag-materials','options'),
            Output('ag-sect3','style'),
            Output('ag-materials','value'),
            Input( 'ag-matypes','value'),
            Input( 'ag-resources','value'))
def setMaterials(matype, plants):
    """
    Function to prepare the list of materials to use in the aunction

    :param str mattype: Either Materials or Orders.
    :param list plants: List of resources to be part of the auction.

    :return: Tuple od string, list, dictionary and list of materials.
    :rtype: tuple
    """
    if len(matype) > 0 and len(plants) > 0:
        res  = []
        # plts = [int(plants[itr].replace('VEA','')) for itr in range(len(plants))]
        site = state.get_site()
        for ir in plants:
            stg_act = site.get_equipment_by_name(ir).storage_in
            lmts = []
            if matype == 'Materials':
                lmts = snapshot.get_material_equipment(site, ir, stg_act)
            else:
                lmts = snapshot.get_orders_equipment(site, ir, stg_act)
            # lms = lms + sorted(lmts.RetrieveList()['lst'])
        titx= 'Targeted {} (click to unselect from {} entries):'.format(matype,len(lmts))
        for ic in sorted(lmts): #  lms:
            res.append('{"label":"'+str(ic)+'", "value": "'+str(ic)+'"}')
        jres= [json.loads(k) for k in res]
        auction.set_materials(matype,plants)
        return(titx,jres,{'display':'block'},sorted(lmts))
    return('',[],{'display':'none'},[])

#
@callback( Output('ag-cont_item-ass-materials','children'),
           Output('ag-ass-materials','options'),
           Output('ag-sect5','style'),
           Output('ag-ass-materials','value'),
           Input( 'ag-matypes','value'),
           Input( 'ag-resources','value'),
           Input( 'ag-ass-matypes','value'))
def setAssMaterials(matype, plants, ass_mats):
    """
    Function to prepare the list of materials to use in the aunction

    :param str mattype: Either Materials or Orders.
    :param list plants: List of resources to be part of the auction.
    :param list ass_mats: List of materials already assigned

    :return: Tuple of string, list, dictionary and list of materials.
    :rtype: tuple
    """
    if len(matype) > 0 and len(plants) > 0 and len(ass_mats) >0:
        res = []
        site = state.get_site()
        for ir in plants:
            cplnt   = site.get_equipment_by_name(ir)
            stg_act = cplnt.storage_in
            amts = []
            if matype == 'Materials':
                amts = snapshot.get_material_equipment(site, ir, stg_act, cplnt.id)
            else:
                amts = snapshot.get_orders_equipment(site, ir, stg_act,cplnt.id)
            titx= 'Targeted {} (click to select from {} entries):'.format(matype,len(amts))
            for ic in sorted(amts): # lms:
                res.append('{"label":"'+str(ic)+'", "value": "'+str(ic)+'"}')
        jres= [json.loads(k) for k in res]
        auction.set_ass_materials(matype,plants,ass_mats, amts)
        return(titx,jres,{'display':'block'},sorted(amts))
    return('',[],{'display':'none'},[])

#
@callback( Output('ag-status',  'children'),
           Output('ag-start',   'style'),
           Output('ag-start',   'children'),
           Output('ag-submit',  'children'),
            Input('ag-submit',  'n_clicks'),
            Input('ag-start',   'n_clicks'),
            Input('ag-ref',      'value'),
            State('ag-matypes',  'value'),
            State('ag-materials','options'),
            State('ag-materials','value'),
            State('ag-resources', 'value'),
            State('ag-ass-matypes','value'),
            State('ag-ass-materials','value'))
def update_output(nsb_clicks,nst_clicks,reftxt,mtyp,op_mat,lmats,plnts,ass_typ,amats): 
    """
    Refreshing the status of the process.

    :param int nsb_clicks: Number of clicks on the Start button.
    :param int nst_clicks: Number of clicks on the Details button.
    :param str reftext: Topic under which the auction will take place.
    :param str mtype: Either 'Materials' or 'Orders' as selector.
    :param list op_mat: List of materials to be excluded from the auction.
    :param list lmats: List of materials of interest.
    :param list plnts: List of resources of interest.

    :return: Tuple of string for Status, dictionary for plottly options, 
             'name for left button', 'name for right button'.
    :rtype: tuple
    """
    global s_mats, resul
    # Four more outputs are expected to show the Results section ... soon.
    # List of integers ids of resources under analysis
    txt    = 'The auction {} involving {} resource(s) and {} material(s) ' + \
                'is being created now. Button clicked {} times.'
    if reftxt is None:
        return('Status of the auction: Not yet created.',{'display' : 'none'},
                'Start Auction','Create Auction')
    # plts = [int(plnts[itr].replace('VEA','')) for itr in range(len(plnts))]
    if len(reftxt) < 6:
        return('Auction can not be created: Reference must be ' +\
                'larger than 5 chars: {}\n'.format(reftxt), {'display' : 'none'},
                'Start Auction', 'Create Auction')
    if "ag-submit" == ctx.triggered_id:  # Launch agents button clicked ...
        if nst_clicks > 0:  # After having started the auction
            if len(s_mats) > 0: # Auction Process is Ongoing
                # Ask log agent through Kafka the current status
                # resul to be filled with the results found up to now.
                if nst_clicks > 0:
                    producer_config = {"bootstrap.servers": IP}
                    consumer_config = {"bootstrap.servers": IP, "group.id": "UX", \
                                        "auto.offset.reset": "earliest"}
                    producer = Producer(producer_config)
                    consumer = Consumer(consumer_config)
                    consumer.subscribe([ 'DynReact-' + reftxt ])
                    res = ask_results(reftxt, producer, consumer, VB)
                    #
                    return('The auction {} is ongoing: Current values are: {}'.format(
                                reftxt,res), {'display':'block'},'End Auction',
                                'Check Auction')
                else:
                    txt2   = txt.format(reftxt,len(plnts),len(s_mats),nsb_clicks)
                    txt2   = txt2 + 'You must push once the button Start Auction!.'
                    return(txt2, {'display' : 'block'},'Start Auction','Launching Auction')
            else:
                return('There are not items to be scheduled: [{}]'.format(len(s_mats)), 
                       {'display' : 'none'},'Start Auction','Create Auction')
        else: # We must start the auction
            if mtyp == 'Materials':
                # s_mats = [op_mat[j]['value'] for j in range(len(op_mat))]
                # for k in range(len(lmats)): # removing the checked items
                # We do not remove since Jens asked for direct selection (Nov 2024)
                s_mats = lmats
                if ass_typ == 'Yes': # Adding pre-assigned materials to the scheduling
                    s_mats = list(set(lmats + amats))
                auction.set_lists(reftxt,lmats,mtyp,s_mats)
            else:
                # o_mats = [op_mat[j]['value'] for j in range(len(op_mat))]
                # for k in range(len(lmats)): # removing the checked items
                o_mats = lmats
                if ass_typ == 'Yes': # Adding pre-assigned materials to the scheduling
                    o_mats = list(set(lmats + amats))
                s_mats = snapshot.get_material_selected_orders(o_mats,plnts,state.get_site())
                auction.set_lists(reftxt,o_mats,mtyp,s_mats)
            # Now we start launching the auction ...
            # process = multiprocessing.Process(target= start_auction, 
            #                 args= (reftxt, plnts, s_mats, 0))
            # process.start()
            auction.set_status('L')
            state.set_auction_obj(auction)
            start_auction(reftxt, plnts, s_mats, 0) # Launch agents
            txt2   = txt.format(reftxt,len(plnts),len(s_mats),nsb_clicks)
            time.sleep(len(plnts)+5) # waiting some seconds to launch the agents.
            return(txt2, {'display' : 'block'},'Start Auction','Launching Auction')
    #
    if "ag-start" == ctx.triggered_id: # Start auction buton clicked
        if nst_clicks == 1:
            numag = len(plnts)+len(s_mats)
            auction.set_status('G')
            state.set_auction_obj(auction)
            start_ag_auction(reftxt, numag, VB)
            return('Auction effectively Started.',{'display' : 'block'},
                    'End Auction','Check Auction')
        else:
            producer_config = {"bootstrap.servers": IP}
            consumer_config = {"bootstrap.servers": IP, "group.id": "UX", 
                               "auto.offset.reset": "earliest"}
            producer = Producer(producer_config)
            consumer = Consumer(consumer_config)
            consumer.subscribe([reftxt])
            #
            auction.set_status('E')
            state.set_auction_obj(auction)
            end_auction(reftxt, producer, VB)
            return('Auction Ended.',{'display' : 'none'},
                    'End Auction','Check Auction')
    else:
        return('Creating the auction ... ', 
               {'display' : 'none'},'Start Auction','Create Auction')

# Localization
@callback(Output("agp-title", "children"), 
          Input("lang", "data"))
def update_locale(lang: str):
    """
    Consideration for Language Localization

    :param str lang: Acronym for the language to be localized.

    :returns: Localized sentence
    :rtype: str
    """
    translation: dict[str, str]|None = Localization.get_translation(
                    lang, translations_key)
    title = Localization.get_value(translation, "title", "Short term planning")
    return title

# ==============================================================================
# We are supossing that both Main Resource agent and Main Material 
# agent are properly placed on-site.
#
def create_auction(nam: str, resources: list[str], materials: list[str], 
                   producer: Producer, verbose: int, 
                   counterbid_wait: float) -> tuple[str, int]:
    """
    Creating an auction which means to send message to the agent through Kafka.

    :param str nam: Topic for the auction.
    :param list resources: List of interesting resources for the auction.
    :param list materials: List of interesting materials for the auction.
    :param object producer: Kafka object as message source.
    :param int verbose: Verbosity level.
    :param float counterbid_wait: Granted period waiting for last offer.

    :returns: Tuple with the final string used and the number of agents launched.
    :rtype: tuple
    """
    # Keep track of the number of agents created
    num_agents = 0

    # Instruct the general LOG to clone itself to create a new auction
    act = 'DynReact-' + nam
    sendmsgtopic(
        producer=producer,
        tsend=TOPIC_GEN,
        topic=act,
        source="UX",
        dest="LOG:" + TOPIC_GEN,
        action="CREATE",
        payload=dict(msg=f"Created Topic {act}"),
        vb=verbose
    )
    #
    # Instruct the LOG of the auction to write a test message
    msg = "Initial Test"
    sendmsgtopic(
        producer=producer,
        tsend=act,
        topic=act,
        source="UX",
        dest="LOG:" + act,
        action="WRITE",
        payload=dict(msg=msg),
        vb=verbose
    )
    #
    if verbose > 1:
        msg = f"Obtained list of Plants {resources}"
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=act, source="UX", 
            dest="LOG:" + TOPIC_GEN, action="WRITE", payload=dict(msg=msg), vb=verbose
        )
    for resource in resources:
        sendmsgtopic(
            producer=producer,
            tsend=TOPIC_GEN,
            topic=act,
            source="UX",
            dest="RESOURCE:" + TOPIC_GEN,
            action="CREATE",
            payload=dict(id=resource, counterbid_wait=counterbid_wait),
            vb=verbose
        )
        num_agents += 1
    #
    # Clone the master MATERIAL for each material ID
    if verbose > 1:
        msg = f"Obtained list of Materials {materials}"
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=act, source="UX", 
            dest="LOG:" + TOPIC_GEN, action="WRITE", payload=dict(msg=msg), vb=verbose
        )    
    for material in materials:
        sendmsgtopic(
            producer=producer,
            tsend=TOPIC_GEN,
            topic=act,
            source="UX",
            dest="MATERIAL:" + TOPIC_GEN,
            action="CREATE",
            payload=dict(id=str(material)),
            vb=verbose
        )
        num_agents += 1

    return act, num_agents

# We are supossing that both Main Resource agent and Main Material 
# agent are properly placed on-site.
#
def start_auction(topic: str, resources: list, materials: list,
                  verbose: int) -> None:
    """
    Starting the auction creation.

    :param str topic: Topic for the auction.
    :param list resources: List of interesting resources for the auction.
    :param list materials: List of interesting materials for the auction.
    :param int verbose: Verbosity level.

    :returns: Tuple with the final string used and the number of agents launched.
    :rtype: tuple
    """
    # admin_client = AdminClient({"bootstrap.servers": IP})
    producer_config = {"bootstrap.servers": IP}
    producer = Producer(producer_config)
    #
    # Extracting the number from the plant name ...
    # lres     = [int(re.findall(r'\d+',s)[0]) for s in resources]
    # Now the plant is collected from the Site Plants structure 4711/2024 
    lres = [state.get_site().get_equipment_by_name(j).get_equipment_id() for j in resources]
    # We do not launch the queue cleaning
    # We do not launch the general agents, avoiding breaking 
    # other potential auctions ongoing.
    act, n_agents = create_auction( topic, lres, materials, producer, 
                                    verbose=VB, counterbid_wait=BW)
    # cloning_wait   = max(CW,5+len(resources)+int(len(materials)/8))
    # sleep(cloning_wait, producer=producer, verbose=verbose)
    # time to develop the auction
    return(act,n_agents)

#
def start_ag_auction(nam: str, n_agents: int, verbose: int) -> None:
    """
    Effective auction initiation, after auction preparation.

    :param str nam: Topic for the auction.
    :param int n_agents: Expected number of agents launched.
    :param int verbose: Verbosity level.
    """
    producer_config = {"bootstrap.servers": IP}
    producer = Producer(producer_config)
    topic = 'DynReact-' + nam
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="LOG:" + topic,
        action="CHECK",
        payload=dict(num_agents=n_agents),
        vb=verbose
    )
    # sleep(AW, producer=producer, verbose=verbose)
    # end_auction(topic=act, producer=producer, verbose=verbose)
    # sleep(EW, producer=producer, verbose=verbose)
    
# 
def end_auction(nam: str, producer: Producer, verbose: int) -> None:
    """
    Ending an ongoing auction by notifiying the agents to end up.

    :param str nam: Topic for the auction.
    :param object producer: Kafka object as message source.
    :param int verbose: Verbosity level.
    """
    # Instruct all RESOURCE children to exit
    # We can define the destinations of the message using a regex instead of looping through all resource IDs
    # In this case, the regex ".*" matches any sequence of characters; that is, any resource ID
    topic = 'DynReact-' + nam
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="RESOURCE:" + topic + ":.*",
        action="EXIT",
        vb=verbose
    )
    # Instruct all MATERIAL children to exit
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="MATERIAL:" + topic + ":.*",
        action="EXIT",
        vb=verbose
    )
    # Instruct the LOG of the auction to exit
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="LOG:" + topic,
        action="EXIT",
        vb=verbose
    )

    # Instruct all general agents (except the LOG) to exit
    # sendmsgtopic(
    #     producer=producer,
    #     tsend=TOPIC_GEN,
    #     topic=TOPIC_GEN,
    #     source="UX",
    #     dest=f"^(?!.*LOG:{TOPIC_GEN}).*$",
    #     action="EXIT",
    #     vb=verbose
    # )

#
def sleep(seconds: float, producer: Producer, verbose: int):
    """
    Sleep for the specified number of seconds and notify the general LOG about it.      
            
    :param float seconds: Number of seconds to be waited. 
    :param object producer: Kafka object producer.
    :param int verbose: Level of verbosity.
    """
    if verbose > 0:
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=TOPIC_GEN, source="UX", dest="LOG:" + TOPIC_GEN, action="WRITE",
            payload=dict(msg=f"Waiting for {seconds}s..."), vb=verbose
        )
    time.sleep(seconds)

#
def sendmsgtopic(producer: Producer, tsend: str, topic: str, source: str, dest: str,
                 action: str, payload: dict = None, vb: int = 0) -> None:
    """
    Send message to a Kafka topic.

    :param object producer: The Kafka producer instance.
    :param str tsend: The topic to send the message to.
    :param str topic: The topic of the message.
    :param str source: The source of the message.
    :param str dest: The destination of the message.
    :param str action: The action to be performed.
    :param dict payload: The payload of the message. Defaults to {"msg": "-"}
    :param int vb: Verbosity level. Defaults to 0.
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

#
def confirm(err: str, msg: str) -> None:
    """
    Confirms the message delivery and prints an error message if any.

    :param str err: Error message, if any.
    :param str msg: The message being confirmed.
    """
    if err:
        print("Error sending message: " + msg + " [" + err + "]")
    return None

#
def ask_results(nam: str, producer: Producer, consumer: Consumer, 
                verbose: int, wait_answer: float = 2., max_iters: int = 30) -> dict:
    """
    Asks the LOG of the auction to get the results of the auction.

    :param str topic: Topic name of the auction we want to start
    :param object producer: A Kafka Producer instance
    :param object consumer: A Kafka Consumer instance
    :param int verbose: Verbosity level
    :param float wait_answer: Number of seconds to wait for an answer
    :param int max_iters: Maximum iterations with no message (if this parameter is 1, the loop will stop once there are no more messages)
 
    :returns: Object with the structure.
    :rtype: dict
    """
    topic = 'DynReact-' + nam
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="LOG:" + topic,
        action="ASKRESULTS",
        vb=verbose
    )
    if verbose > 0:
        msg = f"Requested results from LOG"
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=topic, source="UX", 
            dest="LOG:" + TOPIC_GEN, action="WRITE",
            payload=dict(msg=msg), vb=verbose
        )

    sleep(wait_answer, producer=producer, verbose=verbose)

    # Consume all messages until reaching a message destined for UX or exhausting the maximum number of iterations
    iter_no_msg = 0
    while iter_no_msg < max_iters:
        message_obj = consumer.poll(timeout=1)
        if message_obj.__str__() == 'None':
            iter_no_msg += 1
            if verbose > 0 and (iter_no_msg - 1) % 5 == 0:
                msg = f"Iteration {iter_no_msg - 1}. No message found."
                sendmsgtopic(
                    producer=producer, tsend=TOPIC_GEN, topic=topic, 
                    source="UX", dest="LOG:" + TOPIC_GEN,
                    action="WRITE", payload=dict(msg=msg), vb=verbose
                )
            time.sleep(1)
        else:
            messtpc = message_obj.topic()
            vals = message_obj.value()
            consumer.commit(message_obj)
            message_is_ok = all([
                messtpc ==  topic, 
                'Subscribed topic not available' not in str(vals), 
                not message_obj.error()])
            if message_is_ok:
                dctmsg = json.loads(vals)
                match = re.search(dctmsg['dest'], "UX")
                action = dctmsg['action'].upper()
                if match and action == "RESULTS":
                    results = dctmsg['payload']
                    if verbose > 0:
                        msg = f"Obtained results: {results}"
                        sendmsgtopic(
                            producer=producer, tsend=TOPIC_GEN, topic=topic, 
                            source="UX", dest="LOG:" + TOPIC_GEN,
                            action="WRITE", payload=dict(msg=msg), vb=verbose
                        )
                    return results

    if verbose > 0:
        msg = f"Did not obtain results after waiting for {wait_answer}s and having {max_iters} iters with no message"
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=topic, source="UX", 
            dest="LOG:" + TOPIC_GEN, action="WRITE",
            payload=dict(msg=msg), vb=verbose
        )
    return dict()
