import os

import dotenv


class LtpParams:
    """
    Parameters for the long-term planning algorithm.
    """

    debug: bool = False
    "Enable some debugging checks and messages"
    max_iterations: int = 250
    "Maximum number of iterations for the Picos solver. See https://picos-api.gitlab.io/picos/api/picos.modeling.options.html#option-max-iterations."
    disable_shifts_allocator: bool = False
    "Unless this is set to true, the LTP will try to use as few shifts as possible."
    weight_storage_level: float = 1.
    "The optimization tries to keep storage levels close to 50%. This factor can be used to adapt the weight of this target in the objective function"
    weight_storage_level_input: float = 1.
    "Weight factor for the initial storage level of input buffers (feeding equipment in the first process step) in the objective function"
    weight_storage_level_material_final: float = 1.
    "The optimization tries to arrive at an even distribution of material classes in all buffers at the end of the considered period. This factor can be used to adapt the weight of this target in the objective function"
    weight_class_targets: float = 1.
    "The optimization aims for the total production per material class to arrive at the predefined target values. This factor can be used to adapt the weight of this target in the objective function"

    def __init__(self,
        debug: bool|None = None,
        max_iterations: int|None = None,
        disable_shifts_allocator: bool|None= None,
        weight_storage_level: float|None = None,
        weight_storage_level_input: float|None = None,
        weight_storage_level_material_final: float|None = None,
        weight_class_targets: float|None = None
    ):
        dotenv.load_dotenv()
        if debug is None:
            debug = os.getenv("LTP_DEBUG", "false").lower() in ("1", "true")
        self.debug = debug
        if max_iterations is None:
            max_iterations = int(os.getenv("LTP_ITERATIONS", LtpParams.max_iterations))
        self.max_iterations = max_iterations
        if disable_shifts_allocator is None:
            disable_shifts_allocator = os.getenv("LTP_DISABLE_SHIFTS_ALLOCATOR", "false").lower() in ("1", "true")
        self.disable_shifts_allocator = disable_shifts_allocator
        if weight_storage_level is None:
            weight_storage_level = float(os.getenv("LTP_WEIGHT_STORAGE_LEVEL", LtpParams.weight_storage_level))
        self.weight_storage_level = weight_storage_level
        if weight_storage_level_input is None:
            weight_storage_level_input = float(os.getenv("LTP_WEIGHT_STORAGE_LEVEL_INPUT", LtpParams.weight_storage_level_input))
        self.weight_storage_level_input = weight_storage_level_input
        if weight_storage_level_material_final is None:
            weight_storage_level_material_final = float(os.getenv("LTP_WEIGHT_STORAGE_LEVEL_MAT_FINAL", LtpParams.weight_storage_level_material_final))
        self.weight_storage_level_material_final = weight_storage_level_material_final
        if weight_class_targets is None:
            weight_class_targets = float(os.getenv("LTP_WEIGHT_CLASS_TARGETS", LtpParams.weight_class_targets))
        self.weight_class_targets = weight_class_targets

