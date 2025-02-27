"""
test.py
This scripts checks the data returned by the functions.
"""
from data.data_functions import get_equipment_materials, get_equipment_status, get_material_params, get_transition_cost_and_status
import json


if __name__ == "__main__":

    # Notes: the ID of VEA08 is 14; the ID of VEA09 is 15
    equipment1 = 6
    equipment2 = 7
    material1 = '1003941106'

    equipment1_materials = get_equipment_materials(equipment1)
    print(f"---- Equipment {equipment1}'s materials:", equipment1_materials)
    equipment1_status = get_equipment_status(equipment1)
    print(f"---- Equipment {equipment1} status:", equipment1_status)

    equipment2_materials = get_equipment_materials(equipment2)
    print(f"---- Equipment {equipment2}'s materials:", equipment2_materials)
    equipment2_status = get_equipment_status(equipment2)
    print(f"---- Equipment {equipment2} status:", equipment2_status)

    material1_params = get_material_params(material1)
    print(f"---- Material {material1}:", material1_params)

    print(f"---- Equipment {equipment1}'s transition from {equipment1_status['current_coils'][-1]} to {material1}")
    transition = get_transition_cost_and_status(material_params=material1_params, equipment_status=equipment1_status)
    print(f"Result:")
    print(json.dumps(transition, indent=4))

    # material2 = '1003933326'
    # material2_params = get_material_params(material2)
    # print(f"---- Material {material2}:", material2_params)
    # print(f"---- Equipment {equipment1}'s transition from {material1} to {material2}:")
    # equipment1_status = transition[1]
    # transition = get_transition_cost_and_status(material_params=material2_params, equipment_status=equipment1_status)

    print(f"==== TRANSITIONS OF EQUIPMENT {equipment1} TO EVERY MATERIAL OF ITS LIST")
    equipment1_allowed_materials = []
    for equipment_material in equipment1_materials:
        print(
            f"---- Equipment {equipment1}'s transition from {equipment1_status['current_coils'][-1]} to {equipment_material}")
        equipment_material_params = get_material_params(equipment_material)
        transition = get_transition_cost_and_status(material_params=equipment_material_params,
                                                    equipment_status=equipment1_status)
        if transition[0] is not None:
            equipment1_allowed_materials.append(equipment_material)

    print(f"==== TRANSITIONS OF EQUIPMENT {equipment1} TO EVERY MATERIAL OF EQUIPMENT {equipment2}")
    for equipment_material in equipment2_materials:
        print(
            f"---- Equipment {equipment1}'s transition from {equipment1_status['current_coils'][-1]} to {equipment_material}")
        equipment_material_params = get_material_params(equipment_material)
        transition = get_transition_cost_and_status(material_params=equipment_material_params,
                                                    equipment_status=equipment1_status)
        if transition[0] is not None:
            equipment1_allowed_materials.append(equipment_material)

    print(f"==== TRANSITIONS OF EQUIPMENT {equipment2} TO EVERY MATERIAL OF ITS LIST")
    equipment2_allowed_materials = []
    for equipment_material in equipment2_materials:
        print(
            f"---- Equipment {equipment2}'s transition from {equipment2_status['current_coils'][-1]} to {equipment_material}")
        equipment_material_params = get_material_params(equipment_material)
        transition = get_transition_cost_and_status(material_params=equipment_material_params,
                                                    equipment_status=equipment2_status)
        if transition[0] is not None:
            equipment2_allowed_materials.append(equipment_material)

    print(f"==== TRANSITIONS OF EQUIPMENT {equipment2} TO EVERY MATERIAL OF EQUIPMENT {equipment1}")
    for equipment_material in equipment1_materials:
        print(
            f"---- Equipment {equipment2}'s transition from {equipment2_status['current_coils'][-1]} to {equipment_material}")
        equipment_material_params = get_material_params(equipment_material)
        transition = get_transition_cost_and_status(material_params=equipment_material_params,
                                                    equipment_status=equipment2_status)
        if transition[0] is not None:
            equipment2_allowed_materials.append(equipment_material)

    print(f"Equipment {equipment1} allowed materials:", equipment1_allowed_materials)
    print(f"Equipment {equipment2} allowed materials:", equipment2_allowed_materials)
