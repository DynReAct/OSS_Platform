import enum
import sys, os
import json
import hashlib
from collections import defaultdict
from traceback import print_tb


class JobStatus(enum.Enum):
    I = "Idle"
    L = "Launched"
    G = "Started"
    F = "Finished"
    E = "Error"

def hash_object(obj):
    """Serialize the object and return a hash string."""
    obj_str = json.dumps(obj, sort_keys=True)
    return hashlib.sha256(obj_str.encode()).hexdigest()

class Auction:
    """
       This class is responsible of storing and handling information
       related to the auction requested by the GUI system.

    Attributes:
       CodeId (str): String identifying a single auction reference.
                     Any string with less of 15 characters is valid.
                     However, better if white spaces are avoided.

    .. _Google Python Style Guide:
       https://google.github.io/styleguide/pyguide.html
    """


    def __init__(self, code_id: str):
        """ 
        Constructor function for the Auction class

        :param str code_id: Auction Identification String.

        :returns: None

        """
        self.auction_status = JobStatus.I
        self.code          = code_id
        self.matype        = 'Orders'
        self._equip        = []
        self._all_equip    = []
        self._all_objs     = []
        self._smats        = []
        self._lmats        = []
        self._omats        = []
        self._mat_ass_type = ''
        self._amats        = []
        self._ass_mats     = []
        self._resul        = {}

    def get_codeid(self):
        """ 
        Function returning the CodeId for the auction.

        :returns: Auction Identification String.

        :rtype: str
        """

        return(self.code)

    def set_materials(self, matype:str, plants:list):
        """ 
        Function establishing the Auction parameters of
        materials and equipments.

        :param str matype: Either Coils or Orders
        :param list plants: List of equipments involved in the Auction
        """
        self.matype = matype
        self._equip = plants
        return(None)

    def set_ass_materials(self,matype:str, plants:list, ass_mats: str, amats:list):
        """ 
        Function establishing the Auction parameters of
        assigned materials and equipments.

        :param str matype: Either Coils or Orders
        :param list rescs: List of equipments involved in the Auction
        :param str ass_mats: To include assigned materials Yes/No
        :param list amats: List of assigned materials to be included
        """
        self.matype = matype
        self._equip= plants
        self._mat_ass_type = ass_mats
        self._amats = amats
        return(None)

    def get_materials(self):
        """ 
        Function returning the Auction parameters of materials and equipments

        :returns: Struct of matype (str): Either Coils or Orders, 
            _equip (list): List of equipments involved in the Auction

        :rtype: struct
        """
        return({self.matype,self._equip})

    def set_params(self, htmscr):
        """
        Function parsing the html into UI attributes.

        :param obj htmscr: The html object with the settings selected by the user.
        """
        self.matype = htmscr.__getitem__('ag-matypes').value
        self._mat_ass_type = htmscr.__getitem__('ag-ass-matypes').value
        self._equip= htmscr.__getitem__('ag-resources').value
        if len(htmscr.__getitem__('ag-resources').options) > 0:
            self._all_equip = [j['value'] for j in htmscr.__getitem__('ag-resources').options]
        if len(htmscr.__getitem__('ag-materials').options) > 0:
            self._all_objs = [j['value'] for j in htmscr.__getitem__('ag-materials').options]
        if len(htmscr.__getitem__('ag-materials').value)>0:
            self._smats   = htmscr.__getitem__('ag-materials').value
        if len(htmscr.__getitem__('ag-ass-materials').options) > 0:
            self._amats = [j['value'] for j in htmscr.__getitem__('ag-ass-materials').options]
        if len(htmscr.__getitem__('ag-ass-materials').value)>0:
            self._ass_mats   = htmscr.__getitem__('ag-ass-materials').value
        vtxt         = htmscr.__getitem__('ag-ref')
        self._lmats  = self._omats = []
        if self.matype == 'Coils':
            self._lmats  = list(set(self._all_objs) - set(self._smats))
        else:
            self._omats  = list(set(self._all_objs) - set(self._smats))
        if 'value' in vtxt:
            self.code= vtxt.value
        return(None)

    def get_params(self):
        """
        Function recovering auction's parameters.

        :returns: tuple(matype,plnts,all_plnts,objs,all_objs,reftxt,mat_ass_type)
           WHERE
           str     matype    is the type of object being processed Coils/Orders.
           list    _equip    is the list of selected equipments.
           list    all_equip is the list of all equipments.
           list    objs      is the list of selected materials to be discarded.
           list    allobjs   is the list of all materials.
           str     reftxt    is the auction codeId.
           str     mat_ass_type is the reference Yes/No for assigned materials
           list    amats     is the list of assigned materials
           list    ass_mats  is the list of selected assigned materials
        """
        res = (self.matype,self._equip,self._all_equip,self._smats, \
                self._all_objs,self.code, self._mat_ass_type,self._amats,self._ass_mats)
        return(res)


    def set_codeid(self,code: str):
        """ 
        Function to setup the code when it requires update

        :param str CodeId: Auction Identification String.
        """
        self.code = code
        return(None)

    def set_lists(self,rftxt:str, lmats:list,mtyp:str, smats:list):
        """ 
        Function setting up the list of materials and plants relevant
        for the auction.

        :param list lmats: List of materials interesting to the Auction
        :param list omats: List of materials' orders interesting to the Auction
        :param list smats: List of equipments interesting to the Auction
        """
        self.code = rftxt
        self.matype = mtyp
        if self.matype == 'Coils':
            self._lmats = lmats
            self._omats = []
        else:
            self._omats = lmats
            self._lmats = []
        self._smats = smats
        return(None)

    def get_lmats(self):
        """ 
        Function returning the list of materials of interest for this Auction

        :returns: List of materials interesting the Auction.

        :rtype: list
        """
        return(self._lmats)

    def get_omats(self):
        """ 
        Function returning the list of materials' orders of interest 
        for this Auction.

        :returns: List of materials' orders interesting the Auction.

        :rtype: list
        """
        return(self._omats)

    def get_smats(self):
        """ 
        Function returning the list of equipments of interest for this Auction

        :returns: List of equipments interesting the Auction.

        :rtype: list
        """
        return(self._smats)
    
    def get_amats(self):
        """ 
        Function returning the list of equipments of interest already assigned for this Auction

        :returns: List of equipments already assigned interesting the Auction.

        :rtype: list
        """
        return(self._amats)        

    def get_equipments(self):
        """ 
        Function returning the list of equipments 

        :returns: List of equipments
        :rtype: list
        """
        return(self._all_equip)

    def set_resul(self, results: dict):
        """
        Function establising the auction results

        :param dict results: Auction results.
        """

        for equipment in results.keys():

            if equipment in self._resul.keys():

                merged = {}

                for job in self._resul[equipment]:
                    hash_job = hash_object(job)

                    if merged.get(hash_job) is None:
                        merged[hash_job] = job

                for job in results[equipment]:
                    hash_job = hash_object(job)

                    if merged.get(hash_job) is None:
                        merged[hash_job] = job

                self._resul[equipment] = list(merged.values())
            else:
                self._resul[equipment] = results[equipment]


    def get_resul(self):
        """ 
        Function returning the results

        :returns: Return the resutls
        :rtype: dict
        """
        return self._resul


    def set_status(self, job_status: JobStatus):
        """ 
        Function establising the current status for the auction

        :param JobStatus job_status: Auction status according to the following code
                         'L' => Launched, 'G' => Started, 'E' => Ended.
        """

        self.auction_status = job_status

    def get_status(self):
        """ 
        Function returning the status according to a scale
        distinguishing when the auction is not launched, launched,
        started or ended.

        :returns: JobStatus according to the code

        :rtype: JobStatus
        """
        return self.auction_status

    def set_message(self,msg):
        """ 
        Function establishing the message describing the current status

        :param str msg: Status message.
        """
        self._msg = msg
        return(None)


    def get_message(self):
        """ 
        Function recovering the message describing the current status

        :returns: message to be returned.

        :rtype: str
        """
        return(self._msg)
