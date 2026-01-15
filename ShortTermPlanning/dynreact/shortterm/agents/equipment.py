"""
equipment.py 
First Prototype of Kubernetes oriented solution for the EQUIPMENT agent

Version History:
- 1.0 (2024-03-06): Initial version developed by Rodrigo Castro Freibott.
- 1.1 (2024-11-28): Updates from JOM
- 1.2 (2024-12-14): Updates from JOM Cosmetics to name equipment instead of resource
- 1.3 (2025-11-01): Updates to accomodate energy forecast
- 2.0 (2025-11-03): Integrated REST call to energy estimation service,
                      consistent with the final API (service.py/model_loader.py).
                      
"""

import time, requests, os
from datetime import datetime
from dynreact.shortterm.common import sendmsgtopic, KeySearch
from dynreact.shortterm.common.data.data_functions import get_equipment_status
from dynreact.shortterm.common.data.load_url import DOCKER_REPLICA
from dynreact.shortterm.common.functions import calculate_production_cost, get_new_equipment_status
from dynreact.shortterm.agents.agent import Agent
from dynreact.shortterm.common.handler import DockerManager


class Equipment(Agent):
    """
    Class Equipment supporting the equipment agents.

    Arguments:
        topic     (str): Topic driving the relevant converstaion.
        agent     (str): Name of the agent creating the object.
        status   (dict): Status of the equipment

    """

    def __init__(self, topic: str, agent: str, status: dict, manager=True):

        super().__init__(topic=topic, agent=agent)
        """
           Constructor function for the Equipment Class

        :param str topic: Topic driving the relevant converstaion.
        :param str agent: Name of the agent creating the object.
        :param dict status: Status of the equipment
        :param str manager: Is this instance a base.
        """
        self.action_methods.update({
            'CREATE': self.handle_create_action, 'START': self.handle_start_action,
            'COUNTERBID': self.handle_counterbid_action, 'ASKCONFIRM': self.handle_askconfirm_action,
            'CONFIRM': self.handle_confirm_action, 'ASSIGNED': self.handle_assigned_action
        })
        
        if manager:
            self.handler = DockerManager(tag=f"equipment{DOCKER_REPLICA}")

        self.round_number = 0
        self.status = status
        self.equipment = 0
        self.iter_post_bid = 0
        self.bids = []
        self.last_bid_time = None
        self.bid_to_confirm = dict()
        self.previous_price = None

        # --- START: Load Energy Service Configuration ---
        # This is the base URL, e.g., "http://192.168.110.68:5028"
        self.energy_url_base = KeySearch.search_for_value("ENERGY_URL") 
        # This is the secret token for the X-Token header
        self.energy_token = KeySearch.search_for_value("ENERGY_TOKEN")
        # This is the price per unit (e.g., kWh) to convert prediction to cost
        self.energy_price = KeySearch.search_for_value("ENERGY_PRICE", 0.15) 
        
        self.equipment_id = ""

        if not self.energy_url_base or not self.energy_token:
             if self.verbose > 0:
                self.write_log(msg="WARNING: ENERGY_URL or ENERGY_TOKEN are not set. Energy cost will not be calculated.",
                               identifier="e8a5b0e2-12be-4048-b70f-73917bfe947b",
                               to_stdout=True)
        else:
            try:
                # Extract Equipment ID (e.g., "TD1") from status
                self.equipment_id = self.status.get('id', self.agent.split(':')[-2])
                if not self.equipment_id:
                     raise KeyError("Equipment ID could not be extracted from status or agent name.")
            except Exception as e:
                self.write_log(msg=f"ERROR initializing energy service config: {e}",
                               identifier="e8a5b0e3-12be-4048-b70f-73917bfe947b",
                               to_stdout=True)
        # --- END: Load Energy Service Configuration ---
        if self.verbose > 1:
            self.write_log(msg=f"Finished creating the agent {self.agent} with status {self.status}.",
                           identifier="5e0e90e2-12be-4048-b70f-73917bfe947b",
                           to_stdout=True)
            

    def _load_available_energy_models(self):
        """
        Ask the endpoint /models from the Energy service and filters out
        the relevant models for the equipment.
        """
        models_url = f"{self.energy_url}/models"
        headers = {"X-Token": self.energy_token}
        
        if self.verbose > 1:
            self.write_log(f"Quering the avaialble energy models at {models_url} for equipment {self.equipment_id}...",
                           "e9a8f0e0-12be-4048-b70f-73917bfe947b", to_stdout=True)

        try:
            response = requests.get(models_url, headers=headers, timeout=5)
            response.raise_for_status()
            
            # The service returns a dictionary: {"model_key_1": {...}, "model_key_2": {...}}
            all_model_keys = response.json().keys()
            
            # Filtering the entries of interest to our equipment ID
            self.available_model_keys = [ key for key in all_model_keys if self.equipment_id in key]
            
            if not self.available_model_keys:
                self.write_log(f"WARNING: No energy models found for equipment {self.equipment_id} in {models_url}",
                               "e9a8f0e1-12be-4048-b70f-73917bfe947b", to_stdout=True)
                return
            else:
                if self.verbose > 1:
                    self.write_log(f"Found energy models for {self.equipment_id}: {self.available_model_keys}",
                               "e9a8f0e2-12be-4048-b70f-73917bfe947b", to_stdout=True)
            for key in self.available_model_keys:
                if "ensemble_stack" in key:
                    self.ensemble_model_key = key
                    if self.verbose > 0:
                        self.write_log(f"'ensemble' model preferred found: {key}",
                                       "e9a8f0e2-12be-4048-b70f-73917bfe947b", to_stdout=True)
                    break 
            if not self.ensemble_model_key and self.verbose > 0:
                 self.write_log(f"Model 'ensemble' not found. It will be used the average from: {self.available_model_keys}",
                                "e9a8f0e3-12be-4048-b70f-73917bfe947b", to_stdout=True)            

        except requests.exceptions.RequestException as e:
            self.write_log(f"Error by quering the endpoint /energy models: {e}",
                           "e9a8f0e3-12be-4048-b70f-73917bfe947b", to_stdout=True)
        except Exception as e:
            self.write_log(f"Unexpected Error when loading the models: {e}",
                           "e9a8f0e4-12be-4048-b70f-73917bfe947b", to_stdout=True)
            

    def move_to_next_round(self, material_params: dict):
        """
        Moves the equipment to the next round by updating its status according to the assigned 
        material's parameters, updating its name with the next round number, and starting the round.

        :param dict material_params:
        """
        self.status = get_new_equipment_status(material_params=material_params, 
                                        equipment_status=self.status, verbose=self.verbose)
        roundless_name = self.agent[:self.agent.rfind(":")]
        self.round_number += 1
        self.agent = roundless_name + f":{self.round_number}"
        if self.verbose > 1:
            self.write_log(f"Moved equipment {roundless_name} to round {self.round_number}. New status: {self.status}", "eb019471-fbda-43bb-907f-951e503f366e")

        self.iter_post_bid = 0
        self.bids = []
        self.last_bid_time = None
        self.bid_to_confirm = dict()

        full_msg = dict(
            source=self.agent, dest=self.agent, topic=self.topic, action='START',
            payload=dict(price=self.previous_price)
        )
        self.handle_start_action(full_msg)
        

    def handle_create_action(self, dctmsg: dict) -> str:
        """
        Handles the CREATE action. It clones the master EQUIPMENT for one auction.
        This instruction should only be given to the general EQUIPMENT.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """

        print("Got a create action in equipment")

        if self.handler:

            print("Inside the handler")

            topic = dctmsg['topic']
            payload = dctmsg['payload']
            variables = payload['variables']

            KeySearch.assign_values(new_values=variables)

            equipment = payload['id']
            snapshot = payload['snapshot']
            agent = f"EQUIPMENT:{topic}:{equipment}:0"
            status = get_equipment_status(equipment_id=equipment, snapshot_time=snapshot)
            self.equipment = equipment

            init_kwargs = {
                "topic": topic,
                "agent": agent,
                "status": status,
                "variables": KeySearch.dump_model(),
            }

            self.handler.launch_container(name=f"{topic}_{equipment}", agent="equipment", 
                                          mode="replica", params=init_kwargs, auto_remove=False)

            if self.verbose > 1:
                self.write_log(f"Creating equipment with configuration {init_kwargs}...", 
                               "f886d124-383b-497e-b2a1-841222a3e14d")

            return 'CONTINUE'
        else:
            self.write_log(f"Refuse to create equipment replica from another replica instance.", 
                           "fe2dbc33-7dcb-486a-af35-9e485674fff2")
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            raise Exception(f"{dt} | ERROR: Replicas can't create new instances. Only managers can")


    def handle_start_action(self, dctmsg: dict) -> str:
        """
        Handles the START action. It starts the EQUIPMENT's auction by instructing the 
        MATERIALs to start bidding.
        This instruction should only be given to the EQUIPMENT children of the auction.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        topic = dctmsg['topic']
        payload = dctmsg['payload']
        previous_price = None
        if 'price' in payload:
            previous_price = payload['price']

        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest="MATERIAL:" + topic + ":.*",
            action="BID",
            payload=dict(id=self.agent, status=self.status, 
                         previous_price=previous_price),
            vb=self.verbose
        )
        if self.verbose > 2:
            self.write_log(f"Instructed all MATERIAL:{topic} to bid", 
                           "ce79433f-c90b-42bc-a6d8-83e50f25cb5b")

        # Reset bidding status
        self.iter_post_bid = 0
        self.last_bid_time = time.perf_counter()

        return 'CONTINUE'


    def handle_counterbid_action(self, dctmsg: dict) -> str:
        """
        Handles the COUNTERBID action. It gets the material ID, its parameters, and 
        its bidding price to calculate the profit (price minus producation cost) 
        for the equipment.
        This instruction should only be given to the EQUIPMENT children of the auction.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        payload = dctmsg['payload']
        material_params = payload['material_params']
        bidding_price = payload['price']

        # 1. Calculate Production Cost
        prod_cost = calculate_production_cost(material_params=material_params, 
                                equipment_status=self.status, verbose=self.verbose)
        if prod_cost is None:
            if self.verbose > 1:
                self.write_log(
                    f"Rejected offer from material {payload['id']}. "
                    f"The transition function to this material returns null",
                    "46d5bed6-4e29-4d99-af76-93d008961dbd"
                )
            return 'CONTINUE'

        # --- START: Energy Cost Calculation ---
        # 2. Calculate Energy Cost
        (energy_cost_for_profit, energy_estimations_report) = self._get_energy_cost(
                    material_params=material_params)
        
        # 3. Calculate final Profit
        profit = bidding_price - prod_cost # - energy_cost_for_profit (Not considered)

        bid = dict(
            material=payload['id'], 
            profit=profit, 
            price=bidding_price,
            energy_cost=energy_cost_for_profit,      # <-- Store the cost used for profit
            energy_report=energy_estimations_report, # <-- Store the full report dict
            material_params=material_params          # <-- Store params for confirmation
        )
        # --- END: Energy Cost Calculation ---

        # Reset bidding status
        self.iter_post_bid = 0
        self.last_bid_time = time.perf_counter()

        # Add the bid to the list
        self.bids.append(bid)
        if self.verbose > 1:
            self.write_log(f"Added {bid} to the list of bids, {self.bids}", 
                           "245bb0ae-d579-4fef-a6a1-6625c97afbe1")

        return 'CONTINUE'
    

    def handle_askconfirm_action(self, dctmsg: dict) -> str:
        """
        Handles the ASKCONFIRM action. It asks the material for confirmation 
        to settle the equipment-material assignment.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """

        topic = dctmsg['topic']
        material = dctmsg['payload']['id']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=material,
            action="ASKCONFIRM",
            payload=dict(id=self.agent, costs=self.status["planning"]),
            vb=self.verbose
        )
        return 'CONTINUE'
    

    def handle_confirm_action(self, dctmsg: dict) -> str:
        """
        Handles the CONFIRM action. It receives the confirmation from the material and 
        moves to the next round.
        This instruction should only be given to the EQUIPMENT children of the auction,
        and only from the MATERIAL that the equipment previously asked for confirmation.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        payload = dctmsg['payload']
        material = payload['id']
        material_params = payload['material_params'] # Params from CONFIRM message

        if material != self.bid_to_confirm['material']:
            error_msg = (
                f"The sender of the confirmation {material} does not match "
                f"the pending material {self.bid_to_confirm['material']}"
            )
            if self.verbose > 1:
                self.write_log(f"ERROR: {error_msg}", "8515a8be-49c3-4f18-8748-55126f15bb97")
            raise RuntimeError(error_msg)

        self.previous_price = self.bid_to_confirm['price']

        # --- START: Attach energy data to material_params before moving to next round ---
        
        # Retrieve the cost and report from the winning bid
        energy_cost = self.bid_to_confirm.get('energy_cost', 0.0)
        energy_report = self.bid_to_confirm.get('energy_report', {})
        
        # Attach them to the material_params dictionary
        material_params['energy_cost'] = energy_cost
        material_params['energy_report'] = energy_report
        
        # --- END: Attach energy data ---

        if self.verbose > 1:
            self.write_log(
                f"The equipment will be assigned to material {material} with bid {self.bid_to_confirm}. "
                f"Moving to the next round...",
                "0f906ad0-5526-45de-8a51-bc43a2a5c19d"
            )
        
        # material_params (now including energy data) is passed to update status
        self.move_to_next_round(material_params=material_params)
        return 'CONTINUE'
    

    def handle_assigned_action(self, dctmsg: dict) -> str:
        """
        Handles the ASSIGNED action. It removes the material from the list of bids or,
        if the material matches the pending material, it no longer waits for its confirmation.
        This instruction should only be given to the EQUIPMENT children of the auction.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        payload = dctmsg['payload']
        material = payload['id']

        if self.bid_to_confirm and material == self.bid_to_confirm['material']:
            if self.verbose > 1:
                self.write_log(f"The material {material} has been assigned to another equipment.", 
                               "91efd53e-43a4-47bb-8da8-61aef92b8fe2")
            self.bid_to_confirm = dict()
            return 'CONTINUE'

        for index, bid in enumerate(self.bids):
            if bid['material'] == material:
                self.bids.pop(index)
                if self.verbose > 1:
                    self.write_log(f"Removed the assigned material, {material}, from the list of bids: {self.bids}", "a2646085-16ed-41cb-8b3e-745f5f2d7fae")
        return 'CONTINUE'

    def callback_before_message(self) -> str:
        """
        Checks the bidding and confirmation status
        :return: Status of the callback
        :rtype: str
        """
        if self.last_bid_time is None:
            return 'CONTINUE'

        # A bid has already happened; increment the number of iterations post-bid
        self.iter_post_bid += 1
        time_after_bid = time.perf_counter() - self.last_bid_time
        if (self.verbose > 1) and ((self.iter_post_bid - 1) % 15 == 0):
            self.write_log(
                f"Iteration {self.iter_post_bid - 1} after bid. Passed {time_after_bid:.2f}s after last bid",
                "1055b7fa-32a0-40b5-800a-33ba6bf1820f"
            )

        # Do not proceed if not enough time has passed since the last bid or
        # the equipment is waiting for a material to confirm
        if time_after_bid <  KeySearch.search_for_value("COUNTERBID_WAIT") or self.bid_to_confirm:
            return 'CONTINUE'

        # Kill this equipment child if there are no more materials to ask
        if len(self.bids) == 0:
            if self.verbose > 1:
                self.write_log(
                    f"No more bids to process. The equipment will not be assigned to any material. "
                    f"Killing the agent...",
                    "b6afb95b-91ac-4160-81c1-ac539ad2e472"
                )
            return 'END'

        # Ask the (next) best material for confirmation
        self.bids.sort(key=lambda item: item['profit'])
        best_bid = self.bids.pop()
        if self.verbose > 1:
            self.write_log(f"Removed the best bid, {best_bid}, from the list of bids: {self.bids}", "1ea89f70-2e6c-4840-9bdb-bb89dfc7bff5")

        dctmsg = dict(topic=self.topic, payload=dict(id=best_bid['material']))
        self.process_message(action='ASKCONFIRM', dctmsg=dctmsg)

        self.bid_to_confirm = best_bid
        if self.verbose > 1:
            self.write_log(f"Equipment: Asked material {best_bid['material']} for confirmation.", "8d7d38bc-00cb-486c-8efa-0e46257bf1a2")

        return 'CONTINUE'
    
    def _get_energy_cost(self, material_params: dict) -> tuple[float, dict]:
        """
        Queries the energy REST service to obtain the consumption prediction
        for all coils (components) of a material (order) and converts it into cost.
        
        :return: Total energy cost (float).
        """
        # If not energy models were loaded at __init__ we can't continue.
        if not self.available_model_keys:
            if self.verbose > 1:
                self.write_log("No models are available to calculate the Energy Cost. Returning 0.",
                               "e9a8f0e5-12be-4048-b70f-73917bfe947b", to_stdout=True)
            return 0.0, {}
                
        if not self.energy_url or not self.energy_token:
            if self.verbose > 1:
                self.write_log("Energy service not configured, skipping cost calculation.", 
                               "e9a8f0e1-12be-4048-b70f-73917bfe947b", to_stdout=True)
            return 0.0, {}

        try:
            equipment_id = self.status.get('id', self.agent.split(':')[-2])
            if not equipment_id:
                raise KeyError("Equipment ID not found in status or agent name.")
        except Exception as e:
            self.write_log(f"Error extracting equipment_id: {e}. Cannot call energy service. Energy cost is 0.0", \
                           "e9a8f0e0-12be-4048-b70f-73917bfe947b", to_stdout=True)
            return 0.0, {}
        
        # Assumption: 'coils' are under 'material_params['coils']'
        # Adjust 'coils' if the key is different (e.g., 'components')!
        coils = material_params.get('coils', [])
        if not coils:
            if self.verbose > 1:
                self.write_log(f"No 'coils' found in material_params. Energy cost will be 0.", 
                               "e9a8f0e2-12be-4048-b70f-73917bfe947b", to_stdout=True)
            return 0.0

        headers = {"X-Tolen": self.energy_token} 
        profit_model_key = f"ensemble_stack_{self.equipment_id}"
        url_profit = f"{self.energy_url_base}/energy_estimation?model_key={profit_model_key}"
        url_report = f"{self.energy_url_base}/energy_estimation_all?equipment_id={self.equipment_id}"

        # Mapping: REST service keys -> Keys in your 'coil' object
        # Adjust the right-hand keys according to your actual data model!
        feature_mapping = {
            "Length In": "length_in",
            "Length Out": "length_out",
            "Planned Performance (TD)": "planned_performance_td",
            "Steelgrade": "steelgrade",
            "Thickness-Planned-In (TD)": "thickness_planned_in_td",
            "Thickness-Planned-Out (TD)": "thickness_planned_out_td",
            "Weight Out": "weight_out"
        }
        
        total_energy_prediction = 0.0
        all_estimations_report = {}

        for coil in coils:
            coil_id = coil.get('id', f"unknown_coil_{len(all_estimations_report)}")
            try:
                # 4. Create the payload in the format {"features": {...}}
                features_dict = {
                    key_service: coil[key_local] 
                    for key_service, key_local in feature_mapping.items()
                }
                payload = {"features": features_dict}
                
                # --- 5. Call 1: Get prediction for profit ---
                try:
                    response_profit = requests.post(url_profit, json=payload, 
                                                    headers=headers, timeout=5)
                    response_profit.raise_for_status() 
                    
                    # Parse the 'EnergyPrediction' object
                    prediction = response_profit.json().get('predicted_energy') 
                    
                    if prediction is not None:
                        total_energy_prediction += float(prediction)
                    else:
                        self.write_log(f"Unexpected response from {url_profit}: {response_profit.json()}", 
                                       "e9a8f0e3-12be-4048-b70f-73917bfe947b")
                except Exception as e:
                    self.write_log(f"CRITICAL: Failed to get profit prediction from {url_profit}: {e}. Cost will be 0.", "e9a8f0e4-12be-4048-b70f-73917bfe947b", to_stdout=True)
                    return 0.0, {} # Fail safe: if we can't get the cost, reject the bid.

                # --- 6. Call 2: Get all predictions for reporting ---
                try:
                    response_report = requests.post(url_report, json=payload, headers=headers, timeout=5)
                    response_report.raise_for_status()
                    all_estimations_report[coil_id] = response_report.json()
                except Exception as e:
                    # This is not critical, just log a warning
                    self.write_log(f"WARNING: Failed to get report from {url_report}: {e}", 
                                   "e9a8f0e5-12be-4048-b70f-73917bfe947b")
                    all_estimations_report[coil_id] = {"error": str(e)}

            except KeyError as e:
                self.write_log(f"Missing key {e} in coil data. Cost will be 0.", 
                               "e9a8f0e6-12be-4048-b70f-73917bfe947b")
                return 0.0, {}
            except Exception as e:
                self.write_log(f"Unexpected error processing coil {coil_id}: {e}", 
                               "e9a8f0e7-12be-4048-b70f-73917bfe947b")
                return 0.0, {}

        if self.verbose > 1:
            self.write_log(f"Total energy prediction (for profit): {total_energy_prediction}", 
                           "e9a8f0ea-12be-4048-b70f-73917bfe947b")
        
        # 7. Convert prediction (e.g., kWh) to monetary cost (e.g., EUR)
        total_energy_cost = total_energy_prediction * self.energy_price
        
        return total_energy_cost, all_estimations_report

