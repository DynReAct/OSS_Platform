from pydantic import BaseModel, Field
from typing import List, Dict
from enum import Enum
import sys, os
import json, hashlib

class JobStatus(str, Enum):
    I = "Idle"
    L = "Launched"
    G = "Started"
    R = "Running"
    F = "Finished"
    E = "Error"

def hash_object(obj):
    """Serialize the object and return a hash string."""
    obj_str = json.dumps(obj, sort_keys=True)
    return hashlib.sha256(obj_str.encode()).hexdigest()

class Auction(BaseModel):
    """
    Stores and handles information related to an auction requested by the GUI system.

    This class manages the state of the auction, including selected materials,
    equipment, job status, and calculation results.

    Attributes:
        code (str): Unique identifier for the auction reference.
        snapshot (str): Snapshot identifier for the current state.
        helper_text (str): UI display text indicating the current status.
        auction_status (JobStatus): Current state of the job (Idle, Running, etc.).
        msg (str): generic message or error string associated with the auction.
        matype (str): Material type category (e.g., "Orders", "Coils").
        mat_ass_type (str): Material assignment type category.
        equip (List[str]): List of currently selected equipment/plant identifiers.
        all_equip (List[Union[str, dict]]): List of all available equipment options.
        all_objs (List[Union[str, dict]]): List of all available material objects.
        smats (List[str]): List of selected materials (IDs).
        lmats (List[str]): List of available 'Coil' materials (calculated).
        omats (List[str]): List of available 'Order' materials (calculated).
        anmats (List[Union[str, dict]]): List of 'no-resource' material options.
        ass_n_mats (List[str]): Selected 'no-resource' materials.
        amats (List[Union[str, dict]]): List of available assignment materials.
        ass_mats (List[str]): Selected assignment materials.
        resul (Dict[str, List[dict]]): Dictionary storing results keyed by equipment ID.

    Reference:
        Google Python Style Guide: https://google.github.io/styleguide/pyguide.html
    """

    code: str = ""
    snapshot: str = ""
    helper_text: str = "Status of the auction: Not started."
    auction_status: JobStatus = JobStatus.I
    msg: str = ""

    matype: str = "Orders"
    mat_ass_type: str = ""

    equip: List[str] = Field(default_factory=list)
    all_equip: List[str | dict] = Field(default_factory=list)

    all_objs: List[str | dict] = Field(default_factory=list)
    smats: List[str] = Field(default_factory=list)

    lmats: List[str] = Field(default_factory=list)
    omats: List[str] = Field(default_factory=list)

    anmats: List[str | dict] = Field(default_factory=list)
    ass_n_mats: List[str] = Field(default_factory=list)

    amats: List[str | dict] = Field(default_factory=list)
    ass_mats: List[str] = Field(default_factory=list)

    resul: Dict[str, List[dict]] = Field(default_factory=dict)

    class Config:
        use_enum_values = True
        validate_assignment = True

    def set_params(self, htmscr):
        """
        Function parsing the html into UI attributes.

        :param obj htmscr: The html object with the settings selected by the user.
        """
        self.equip = htmscr.__getitem__('ag-resources').value
        if len(htmscr.__getitem__('ag-resources').options) > 0:
            self.all_equip = [j['value'] if isinstance(j, dict) else j for j in htmscr.__getitem__('ag-resources').options]

        if 'ag-matypes' in htmscr:
            self.matype = htmscr.__getitem__('ag-matypes').value
        if 'ag-ass-matypes' in htmscr:
            self.mat_ass_type = htmscr.__getitem__('ag-ass-matypes').value

        if len(htmscr.__getitem__('ag-materials').options) > 0:
            self.all_objs = [j['value'] if isinstance(j, dict) else j for j in htmscr.__getitem__('ag-materials').options]
        if len(htmscr.__getitem__('ag-materials').value) > 0:
            self.smats = htmscr.__getitem__('ag-materials').value

        if 'ag-no-resources' in htmscr:
            if len(htmscr.__getitem__('ag-no-resources').options) > 0:
                self.anmats = htmscr.__getitem__('ag-no-resources').options
            if len(htmscr.__getitem__('ag-no-resources').value) > 0:
                self.ass_n_mats = htmscr.__getitem__('ag-no-resources').value

        if len(htmscr.__getitem__('ag-ass-materials').options) > 0:
            self.amats = [j['value'] if isinstance(j, dict) else j for j in htmscr.__getitem__('ag-ass-materials').options]
        if len(htmscr.__getitem__('ag-ass-materials').value) > 0:
            self.ass_mats = htmscr.__getitem__('ag-ass-materials').value

        self.lmats = []
        self.omats = []

        clean_all_objs = [x if isinstance(x, str) else str(x) for x in self.all_objs]

        if self.matype == 'Coils':
            self.lmats = list(set(clean_all_objs) - set(self.smats))
        else:
            self.omats = list(set(clean_all_objs) - set(self.smats))

        vtxt = htmscr.__getitem__('ag-ref')
        if 'value' in vtxt:
            self.code = vtxt.value

    def set_lists(self, rftxt: str, lmats: list, mtyp: str, smats: list):
        """
        Function setting up the list of materials and plants relevant
        for the auction.

        :param str rftxt: Auction Identification String
        :param list lmats: List of materials interesting to the Auction
        :param str mtyp: Type of object being processed Coils/Orders
        :param list smats: List of equipments interesting to the Auction
        """
        self.code = rftxt
        self.matype = mtyp
        self.smats = smats

        if self.matype == 'Coils':
            self.lmats = lmats
            self.omats = []
        else:
            self.lmats = []
            self.omats = lmats

    def set_materials(self, matype: str, plants: list):
        """
        Function establishing the Auction parameters of
        materials and equipments.

        :param str matype: Either Coils or Orders
        :param list plants: List of equipments involved in the Auction
        """
        self.matype = matype
        self.equip = plants

    def set_ass_materials(self, matype: str, plants: list, ass_mats: str, amats: list):
        """
        Function establishing the Auction parameters of
        assigned materials and equipments.

        :param str matype: Either Coils or Orders
        :param list plants: List of equipments involved in the Auction
        :param str ass_mats: To include assigned materials Yes/No
        :param list amats: List of assigned materials to be included
        """
        self.matype = matype
        self.equip = plants
        self.mat_ass_type = ass_mats
        self.amats = amats

    def set_resul(self, results: Dict[str, List[dict]]):
        """
        Function establising the auction results

        :param dict results: Auction results.
        """
        for equipment in results.keys():
            if equipment in self.resul.keys():
                merged = {}
                for job in self.resul[equipment]:
                    hash_job = hash_object(job)
                    if merged.get(hash_job) is None:
                        merged[hash_job] = job

                self.resul[equipment] = list(merged.values())
            else:
                self.resul[equipment] = results[equipment]

    def set_status(self, job_status: JobStatus):
        """
        Function establising the current status for the auction

        :param JobStatus job_status: Auction status according to the code
        """
        self.auction_status = job_status

    def set_message(self,msg):
        """
        Function establishing the message describing the current status

        :param str msg: Status message.
        """
        self.msg = msg

    def set_codeid(self, code: str):
        """
        Function to setup the code when it requires update

        :param str code: Auction Identification String.
        """
        self.code = code

    def get_params(self):
        """
        Function recovering auction's parameters.

        :returns: tuple(matype,equip,all_equip,smats,all_objs,code,mat_ass_type,amats,ass_mats)
           WHERE
           str      matype    is the type of object being processed Coils/Orders.
           list     equip     is the list of selected equipments.
           list     all_equip is the list of all equipments.
           list     smats     is the list of selected materials.
           list     all_objs  is the list of all materials.
           str      code      is the auction codeId.
           str      mat_ass_type is the reference Yes/No for assigned materials.
           list     amats     is the list of assigned materials.
           list     ass_mats  is the list of selected assigned materials.
        """
        return (self.matype, self.equip, self.all_equip, self.smats, self.all_objs, self.code, self.mat_ass_type, self.amats, self.ass_mats)

    def get_lmats(self) -> List[str]:
        """
        Function returning the list of materials of interest for this Auction

        :returns: List of materials interesting the Auction.

        :rtype: list
        """
        return self.lmats

    def get_omats(self) -> List[str]:
        """
        Function returning the list of materials' orders of interest
        for this Auction.

        :returns: List of materials' orders interesting the Auction.

        :rtype: list
        """
        return self.omats

    def get_smats(self) -> List[str]:
        """
        Function returning the list of materials' orders of interest
        for this Auction.

        :returns: List of materials' orders interesting the Auction.

        :rtype: list
        """
        return self.smats

    def get_amats(self) -> List[str]:
        """
        Function returning the list of equipments of interest already assigned for this Auction

        :returns: List of equipments already assigned interesting the Auction.

        :rtype: list
        """
        return self.amats

    def get_equipments(self) -> List[str]:
        """
        Function returning the list of equipments

        :returns: List of equipments
        :rtype: list
        """
        return self.equip

    def get_codeid(self):
        """
        Function returning the CodeId for the auction.

        :returns: Auction Identification String.

        :rtype: str
        """
        return self.code

    def get_resul(self):
        """
        Function returning the results

        :returns: Return the results
        :rtype: dict
        """
        return self.resul

    def get_status(self):
        """
        Function returning the status according to a scale
        distinguishing when the auction is not launched, launched,
        started or ended.

        :returns: JobStatus according to the code

        :rtype: JobStatus
        """
        return self.auction_status

    def get_message(self):
        """
        Function recovering the message describing the current status

        :returns: message to be returned.

        :rtype: str
        """
        return self.msg

    def get_materials(self):
        """
        Function returning the Auction parameters of materials and equipments

        :returns: Struct of matype (str): Either Coils or Orders,
            equip (list): List of equipments involved in the Auction

        :rtype: struct
        """
        return({self.matype,self.equip})
