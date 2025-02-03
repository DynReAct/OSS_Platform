import dotenv
import os


class CostConfig:

    threshold_new_lot: float = 4
    "Create a new lot if transition costs between orders exceed this threshold"

    factor_weight_deviation: float = 75
    "A weight factor for the cost contribution of deviating from the target production weight"

    factor_transition_costs: float = 1
    "A weight factor for the cost contribution of transition costs between orders relative to the number of lots"

    factor_out_of_lot_range: float = 1
    "A weight factor for the cost contribution of lot size violations"

    def __init__(self,
                 threshold_new_lot: float|None = None,
                 factor_weight_deviation: float | None = None,
                 factor_transition_costs: float | None = None,
                 factor_out_of_lot_range: float | None = None
                 ):
        dotenv.load_dotenv()
        if threshold_new_lot is None:
            threshold_new_lot = float(os.getenv("OBJECTIVE_MAX_TRANSITION_COST", CostConfig.threshold_new_lot))
        self.TAllowed = threshold_new_lot
        if factor_weight_deviation is None:
            factor_weight_deviation = float(os.getenv("OBJECTIVE_TARGET_WEIGHT", CostConfig.factor_weight_deviation))
        self.factor_weight_deviation = factor_weight_deviation
        if factor_transition_costs is None:
            factor_transition_costs = float(os.getenv("OBJECTIVE_LOT_TRANSITION_COSTS_SUM",  CostConfig.factor_transition_costs))
        self.factor_transition_costs = factor_transition_costs
        if factor_out_of_lot_range is None:
            factor_out_of_lot_range = float(os.getenv("OBJECTIVE_LOT_SIZE",  CostConfig.factor_out_of_lot_range))
        self.factor_out_of_lot_range = factor_out_of_lot_range
