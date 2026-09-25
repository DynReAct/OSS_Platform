# DynReAct Long-term planning

The long-term planning algorithm uses the Picos modeling language to formulate the LTP as a convex optimization problem
and the Ecos solver for the solution. It can be found in the [LongTermPlanning](https://github.com/DynReAct/OSS_Platform/tree/main/LongTermPlanning)
subproject, with the interface implementation residing in the file [LongTermPlanningImpl.py](https://github.com/DynReAct/OSS_Platform/blob/main/LongTermPlanning/dynreact/ltp/LongTermPlanningImpl.py).

## Configuration

The long-term planning algorithm has several configuration parameters, all of which can be set via environment variables.

```
# Maximum number of iterations for the Picos solver. See https://picos-api.gitlab.io/picos/api/picos.modeling.options.html#option-max-iterations. Default is 250.
LTP_ITERATIONS=100
# The optimization tries to keep storage levels close to 50%. This factor can be used to adapt the weight of this target in the objective function. Default value: 1.
LTP_WEIGHT_STORAGE_LEVEL=2
# The optimization aims for the total production per material class to arrive at the predefined target values. This factor can be used to adapt the weight of this target in the objective function. Default: 1.
LTP_WEIGHT_CLASS_TARGETS=2
# The optimization tries to arrive at an even distribution of material classes in all buffers at the end of the considered period. This factor can be used to adapt the weight of this target in the objective function. Default: 1.
LTP_WEIGHT_STORAGE_LEVEL_MAT_FINAL=2
# Weight factor for the initial storage level of input buffers (feeding equipment in the first process step) in the objective function. Default value: 1.
LTP_WEIGHT_STORAGE_LEVEL_INPUT=2
# Enable some debugging checks and messages
LTP_DEBUG=true
```

These parameters are defined in the source file [LtpParams.py](https://github.com/DynReAct/OSS_Platform/blob/main/LongTermPlanning/dynreact/ltp/LtpParams.py)

## Run tests

In the present folder run

```commandline
python -m unittest discover ./tests 
```


