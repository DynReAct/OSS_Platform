import multiprocessing as mp
import os

import dotenv


class TabuParams:

    ntotal: int = 1000
    "Number of TabuSearch Iterations"
    Expiration: int = 10
    "Tabu List expiration"
    NMinUntilShuffle: int = 10
    "number of local minima to be reached until shuffeling"
    #Path: str = "./out"
    #StoreInitialSolution = True
    "Save Initial solution in output path?"
    #InstantSaveMinimum = True
    "Save new global minimum before shuffeling"

    NParallel = min(mp.cpu_count(), 8)
    "parallel processing -> Set to 1 for debugging"

    # Orders with DueDate < MinDueDate have to be processed
    #MinDueDate = datetime(2020, 6, 1)  # dt.datetime.now() # - dt.timedelta(weeks=2)

    TAllowed = 4
    "Maximum transition cost within lot; cf. new lot costs in cost provider (default: 3, for SimpleCostProvider)"

    CostNaN = 50.0
    "default if cost can not be calculated"

    def __init__(self,
                 ntotal: int|None = None,
                 Expiration: int|None = None,
                 NMinUntilShuffle: int|None = None,
                 #Path: str|None = None,
                 #StoreInitialSolution: bool|None = None,
                # InstantSaveMinimum: bool|None = None,
                 NParallel: int|None = None,
                 #MinDueDate: datetime | None = None,
                 TAllowed: float|None = None,
                 CostNaN: float|None = None
    ):
        dotenv.load_dotenv()
        if ntotal is None:
            ntotal = int(os.getenv("TABU_ITERATIONS", self.ntotal))
        self.ntotal = ntotal
        "Number of TabuSearch Iterations"
        if Expiration is None:
            Expiration = int(os.getenv("TABU_LIST_EXPIRATION", self.Expiration))
        self.Expiration = Expiration
        "Tabu List expiration"
        if NMinUntilShuffle is None:
            NMinUntilShuffle = int(os.getenv("TABU_LOCAL_MIN_UNTIL_SHUFFEL", self.NMinUntilShuffle))
        self.NMinUntilShuffle = NMinUntilShuffle
        "number of local minima to be reached until shuffeling"
        #if Path is None:
        #    Path = os.getenv("TABU_BASE_PATH", self.Path)
        #self.Path = Path
        #if StoreInitialSolution is None:
        #    StoreInitialSolution = os.getenv("TABU_STORE_INITIAL_SOLUTION", str(self.StoreInitialSolution)).lower() == "false"
        #self.StoreInitialSolution = StoreInitialSolution
        "Save Initial solution in output path?"
        #if InstantSaveMinimum is None:
        #    InstantSaveMinimum = os.getenv("TABU_INSTANT_SAVE_MINIMUM", str(self.InstantSaveMinimum)).lower() == "true"
        #self.InstantSaveMinimum = InstantSaveMinimum
        "Save new global minimum before shuffeling"
        if NParallel is None:
            NParallel = int(os.getenv("TABU_NUM_CORES", self.NParallel))
        self.NParallel = NParallel
        "parallel processing -> Set to 1 for debugging"
        #if MinDueDate is None:
        #    MinDueDate = DatetimeUtils.parse_date(os.getenv("TABU_MIN_DUE_DATE")) if os.getenv("TABU_MIN_DUE_DATE") is not None else self.MinDueDate
        #self.MinDueDate = MinDueDate
        if TAllowed is None:
            TAllowed = float(os.getenv("TABU_MAX_TRANSITION_COST", self.TAllowed))
        self.TAllowed = TAllowed
        "Maximum transition cost within lot"
        if CostNaN is None:
            CostNaN = float(os.getenv("TABU_COST_NAN", self.CostNaN))
        self.CostNaN = CostNaN
        "default if cost cannot be calculated"
